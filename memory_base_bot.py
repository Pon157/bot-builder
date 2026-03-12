"""
memory_base_bot.py
================================================================================
Отдельный бот-сервис для проверки пользователей через MemoryBase антиспам-базу.

Архитектура:
  1. Принимает команды: чек <user_id_или_@username>
  2. Парсит ответ MemoryBase бота (@MemoryBaseBot)
  3. Сохраняет результат в Supabase таблицу memory_base_cache
  4. Основные боты читают кэш из БД и принимают решение о блокировке

Таблица memory_base_cache в Supabase:
  - user_id: bigint (primary key)
  - username: text
  - status: text  (clean / in_base / not_found)
  - reasons: text[] (массив причин: "Мошенник", "Плохой админ", etc.)
  - raw_text: text (полный ответ MemoryBase)
  - checked_at: timestamp
  - expires_at: timestamp (кэш действует 24 часа)

Переменные .env:
  MEMORY_BASE_BOT_TOKEN — токен этого бота-чекера
  MEMORY_BASE_CHAT_ID — ID чата куда MemoryBase шлёт ответы (для парсинга)
  SUPABASE_URL, SUPABASE_KEY — как всегда
  ADMIN_CHAT_ID — для отправки уведомлений об ошибках
  DVR_CHANNEL_ID — ID канала DVR рейд-проекта для мониторинга
  DVR_ADMIN_TOPIC_ID — ID топика в чате администраторов для DVR-уведомлений
  BOTS_API_URL — URL вашего сервера для остановки ботов (https://dialogengine.webtm.ru)

================================================================================
"""

import asyncio
import logging
import os
import sys
import json
import re
import httpx
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple

from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MemoryBaseBot")

# ── Константы ──────────────────────────────────────────────────────────────────
MEMORY_BASE_BOT_TOKEN = os.getenv("MEMORY_BASE_BOT_TOKEN", "")
SUPABASE_URL          = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY          = os.getenv("SUPABASE_KEY", "")
BOTS_API_URL          = os.getenv("BOTS_API_URL", "https://dialogengine.webtm.ru")
ADMIN_SECRET          = os.getenv("ADMIN_TOKEN", "")
DVR_CHANNEL_ID        = int(os.getenv("DVR_CHANNEL_ID", "0"))       # Канал DVR
ADMIN_CHECK_CHAT_ID   = int(os.getenv("ADMIN_CHECK_CHAT_ID", "-1003772028132"))  # Чат для проверок
ADMIN_CHECK_TOPIC_ID  = int(os.getenv("ADMIN_CHECK_TOPIC_ID", "2"))  # 2-й топик
DVR_ADMIN_TOPIC_ID    = int(os.getenv("DVR_ADMIN_TOPIC_ID", "4"))    # 4-й топик

# Известные причины MemoryBase с их категориями
MB_REASON_MAP = {
    "мошенник":       "scammer",
    "плохой админ":   "bad_admin",
    "плохой владелец":"bad_owner",
    "петушара":       "bad_behavior",
    "спамер":         "spammer",
    "рейдер":         "raider",
}

# Кэш pending-запросов: user_id -> asyncio.Future
_pending: Dict[str, asyncio.Future] = {}
_pending_lock = asyncio.Lock()

# ── Supabase хелпер ────────────────────────────────────────────────────────────
def _sb_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }

async def sb_upsert_check(user_id: int, username: str, status: str,
                          reasons: List[str], raw_text: str):
    """Сохранить результат проверки в кэш БД."""
    expires = (datetime.utcnow() + timedelta(hours=24)).isoformat()
    payload = {
        "user_id":    user_id,
        "username":   username or "",
        "status":     status,
        "reasons":    reasons,
        "raw_text":   raw_text[:2000],
        "checked_at": datetime.utcnow().isoformat(),
        "expires_at": expires,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{SUPABASE_URL}/rest/v1/memory_base_cache",
                headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                json=payload
            )
        logger.info(f"[MB] Saved check: user={user_id} status={status} reasons={reasons}")
    except Exception as e:
        logger.error(f"[MB] sb_upsert error: {e}")

async def sb_get_check(user_id: int) -> Optional[dict]:
    """Получить свежий кэш проверки (не старше 24ч)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{SUPABASE_URL}/rest/v1/memory_base_cache",
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}", "select": "*"}
            )
            if r.status_code == 200 and r.json():
                row = r.json()[0]
                expires_at = row.get("expires_at", "")
                if expires_at:
                    try:
                        exp = datetime.fromisoformat(expires_at.replace("Z",""))
                        if datetime.utcnow() < exp:
                            return row
                    except Exception:
                        pass
    except Exception as e:
        logger.error(f"[MB] sb_get error: {e}")
    return None

async def get_all_bot_usernames() -> List[Dict]:
    """Получить список всех активных ботов с их username."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{SUPABASE_URL}/rest/v1/bots",
                headers=_sb_headers(),
                params={"status": "eq.RUNNING", "select": "id,name,config"}
            )
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.error(f"[DVR] get_bots error: {e}")
    return []

async def stop_bot_via_api(bot_id: str) -> bool:
    """Остановить бот через API сервера."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{BOTS_API_URL}/api/bots/stop",
                json={"bot_id": bot_id},
                headers={"X-Admin-Token": ADMIN_SECRET}
            )
            return r.status_code in [200, 201, 204]
    except Exception as e:
        logger.error(f"[DVR] stop_bot error: {e}")
        return False

# ── Парсер ответов MemoryBase ──────────────────────────────────────────────────
def parse_memory_base_response(text: str) -> Tuple[str, List[str]]:
    """
    Парсит ответ MemoryBase бота.
    
    Форматы:
    🟡 — Человека нет в базе!  → status=clean
    🟢 — Не найден  → status=clean
    🔴 — Человек есть в базе! + Причина → status=in_base
    
    Возвращает (status, reasons)
    """
    text_lower = text.lower()
    
    # Чистые статусы
    if any(p in text_lower for p in [
        "нет в базе", "не найден", "пользователь не найден",
        "на него не поступало жалоб", "🟡", "🟢"
    ]):
        return "clean", []
    
    # В базе
    if any(p in text_lower for p in ["есть в базе", "человек есть", "🔴"]):
        reasons = []
        # Ищем строку "Причина:"
        reason_match = re.search(r'причина[:\s]+(.+?)(?:\n|📖|$)', text, re.IGNORECASE)
        if reason_match:
            reason_text = reason_match.group(1).strip()
            # Нормализуем причину
            reason_clean = re.sub(r'[^\w\sа-яёА-ЯЁ]', '', reason_text).strip().lower()
            # Ищем совпадения с известными причинами
            matched = False
            for mb_reason, category in MB_REASON_MAP.items():
                if mb_reason in reason_clean:
                    reasons.append(category)
                    matched = True
            if not matched and reason_text:
                # Добавляем сырую причину если не распознана
                reasons.append(f"other:{reason_text[:50]}")
        
        if not reasons:
            reasons.append("other:unknown")
        
        return "in_base", reasons
    
    return "not_found", []

# ── Основной класс сервиса ─────────────────────────────────────────────────────
class MemoryBaseBotService:
    def __init__(self):
        self.bot = Bot(
            token=MEMORY_BASE_BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        self.dp = Dispatcher()
        self.router = Router()
        self._mb_bot_id = 7494934422  # ID бота @MemoryBaseBot (уточни если изменился)
        
    async def check_user(self, user_id: Optional[int] = None,
                         username: Optional[str] = None) -> dict:
        """
        Проверяет пользователя через MemoryBase.
        Сначала проверяет кэш БД. Если нет — отправляет запрос боту.
        
        Возвращает:
        {
          "status": "clean" | "in_base" | "not_found" | "error",
          "reasons": [...],
          "raw_text": "...",
          "user_id": ...,
          "username": "..."
        }
        """
        # 1. Пробуем кэш
        if user_id:
            cached = await sb_get_check(user_id)
            if cached:
                logger.info(f"[MB] Cache hit for user {user_id}")
                return {
                    "status":   cached["status"],
                    "reasons":  cached.get("reasons", []),
                    "raw_text": cached.get("raw_text", ""),
                    "user_id":  user_id,
                    "username": cached.get("username", ""),
                    "from_cache": True
                }
        
        # 2. Отправляем запрос в MemoryBase
        query = str(user_id) if user_id else f"@{username.lstrip('@')}"
        
        # Ключ для pending
        key = str(user_id or username)
        
        future = asyncio.get_event_loop().create_future()
        async with _pending_lock:
            _pending[key] = future
        
        try:
            # Отправляем команду чек
            await self.bot.send_message(
                chat_id=ADMIN_CHECK_CHAT_ID,
                text=f"чек {query}",
                message_thread_id=ADMIN_CHECK_TOPIC_ID
            )
            
            # Ждём ответ (таймаут 15 сек)
            raw_text = await asyncio.wait_for(future, timeout=15.0)
            status, reasons = parse_memory_base_response(raw_text)
            
            # Сохраняем в кэш
            await sb_upsert_check(
                user_id  = user_id or 0,
                username = username or "",
                status   = status,
                reasons  = reasons,
                raw_text = raw_text
            )
            
            return {
                "status":   status,
                "reasons":  reasons,
                "raw_text": raw_text,
                "user_id":  user_id,
                "username": username or "",
                "from_cache": False
            }
        except asyncio.TimeoutError:
            logger.warning(f"[MB] Timeout checking {query}")
            # При таймауте считаем что чистый (не блокируем)
            return {"status": "error", "reasons": [], "raw_text": "timeout",
                    "user_id": user_id, "username": username or ""}
        except Exception as e:
            logger.error(f"[MB] check_user error: {e}")
            return {"status": "error", "reasons": [], "raw_text": str(e),
                    "user_id": user_id, "username": username or ""}
        finally:
            async with _pending_lock:
                _pending.pop(key, None)

    def setup_handlers(self):
        """Регистрация обработчиков."""
        
        # Слушаем ответы MemoryBase бота в чате проверок
        @self.router.message(F.chat.id == ADMIN_CHECK_CHAT_ID,
                              F.forward_from.id == self._mb_bot_id)
        async def on_mb_forward(m: Message):
            """Ловим пересланные от MemoryBase сообщения."""
            await self._handle_mb_response(m.text or m.caption or "")

        # Ловим обычные сообщения от MemoryBase в топике
        @self.router.message(F.chat.id == ADMIN_CHECK_CHAT_ID,
                              F.from_user.id == self._mb_bot_id)
        async def on_mb_message(m: Message):
            """Ловим прямые ответы от MemoryBase бота."""
            await self._handle_mb_response(m.text or m.caption or "")

        # DVR мониторинг — ловим посты в DVR канале
        if DVR_CHANNEL_ID:
            @self.router.channel_post(F.chat.id == DVR_CHANNEL_ID)
            async def on_dvr_post(m: Message):
                """Мониторинг DVR рейд-канала."""
                await self._handle_dvr_post(m)
            
            @self.router.message(F.forward_from_chat.id == DVR_CHANNEL_ID)
            async def on_dvr_forward(m: Message):
                """Пересланный пост из DVR канала."""
                await self._handle_dvr_post(m)

        # Команда /check для ручной проверки (только в чате администраторов)
        @self.router.message(Command("check"))
        async def cmd_check(m: Message):
            """Ручная проверка: /check <user_id или @username>"""
            parts = m.text.split(maxsplit=1)
            if len(parts) < 2:
                await m.reply("Использование: /check <user_id> или /check @username")
                return
            
            query = parts[1].strip()
            is_id = query.lstrip("-").isdigit()
            
            status_msg = await m.reply("🔍 Проверяю по MemoryBase...")
            
            if is_id:
                result = await self.check_user(user_id=int(query))
            else:
                result = await self.check_user(username=query.lstrip("@"))
            
            await status_msg.edit_text(self._format_check_result(result))

    async def _handle_mb_response(self, text: str):
        """Обработка ответа MemoryBase — резолвим pending future."""
        if not text:
            return
        
        # Пытаемся найти user_id или username в ответе MemoryBase
        # Формат: 🔴 @username / [user_id]
        id_match = re.search(r'\[(\d+)\]', text)
        uname_match = re.search(r'@(\w+)', text)
        
        async with _pending_lock:
            # Ищем по ID
            if id_match:
                key = id_match.group(1)
                if key in _pending and not _pending[key].done():
                    _pending[key].set_result(text)
                    return
            
            # Ищем по username
            if uname_match:
                key = uname_match.group(1)
                if key in _pending and not _pending[key].done():
                    _pending[key].set_result(text)
                    return
            
            # Если не нашли конкретный ключ — резолвим первый pending
            for k, fut in list(_pending.items()):
                if not fut.done():
                    fut.set_result(text)
                    break

    async def _handle_dvr_post(self, m: Message):
        """
        Обработка поста из DVR канала.
        DVR — рейд-проект. Если в посте упоминается юзернейм нашего бота,
        нужно немедленно его остановить и уведомить администратора.
        """
        post_text = m.text or m.caption or ""
        if not post_text:
            return
        
        logger.info(f"[DVR] New post detected: {post_text[:100]}")
        
        # Получаем все активные боты
        bots = await get_all_bot_usernames()
        if not bots:
            return
        
        # Ищем упоминания юзернеймов наших ботов в посте DVR
        mentioned_bots = []
        post_lower = post_text.lower()
        
        for bot_rec in bots:
            cfg = bot_rec.get("config", {}) or {}
            bot_username = cfg.get("botUsername") or cfg.get("bot_username") or ""
            bot_name = bot_rec.get("name", "")
            
            if bot_username:
                username_clean = bot_username.lower().lstrip("@")
                if username_clean in post_lower or f"@{username_clean}" in post_lower:
                    mentioned_bots.append(bot_rec)
        
        if not mentioned_bots:
            logger.info("[DVR] Post doesn't mention our bots.")
            return
        
        # Останавливаем каждый упомянутый бот
        stopped = []
        failed  = []
        for bot_rec in mentioned_bots:
            bid  = bot_rec["id"]
            name = bot_rec.get("name", bid)
            ok   = await stop_bot_via_api(bid)
            if ok:
                stopped.append(name)
                logger.warning(f"[DVR] Stopped bot {bid} ({name})")
            else:
                failed.append(name)
                logger.error(f"[DVR] Failed to stop bot {bid} ({name})")
        
        # Уведомляем администраторов
        if ADMIN_CHECK_CHAT_ID and DVR_ADMIN_TOPIC_ID:
            stopped_str = "\n".join(f"• {n}" for n in stopped) if stopped else "—"
            failed_str  = "\n".join(f"• {n}" for n in failed) if failed else "—"
            
            notify_text = (
                f"🚨 <b>DVR РЕЙД-АТАКА ОБНАРУЖЕНА!</b>\n\n"
                f"📢 Пост в рейд-канале упоминает ваших ботов.\n\n"
                f"✅ <b>Остановлено:</b>\n{stopped_str}\n\n"
                f"❌ <b>Не удалось остановить:</b>\n{failed_str}\n\n"
                f"🔗 <b>Восстановите работу после спада активности на:</b>\n"
                f"<a href=\"https://dialogengine.webtm.ru\">dialogengine.webtm.ru</a>\n\n"
                f"📝 <b>Текст поста DVR:</b>\n<blockquote>{post_text[:500]}</blockquote>"
            )
            
            try:
                await self.bot.send_message(
                    chat_id=ADMIN_CHECK_CHAT_ID,
                    text=notify_text,
                    message_thread_id=DVR_ADMIN_TOPIC_ID,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            except Exception as e:
                logger.error(f"[DVR] notify error: {e}")

    def _format_check_result(self, result: dict) -> str:
        """Форматирует результат проверки в читаемый текст."""
        status   = result.get("status", "error")
        reasons  = result.get("reasons", [])
        uid      = result.get("user_id")
        username = result.get("username", "")
        
        user_str = ""
        if uid:    user_str += f"ID: <code>{uid}</code>"
        if username: user_str += f"  @{username}"
        
        if status == "clean":
            return f"✅ <b>MemoryBase: Чисто</b>\n{user_str}\nПользователь не найден в базе."
        elif status == "in_base":
            reasons_readable = {
                "scammer":      "Мошенник ⛔️",
                "bad_admin":    "Плохой админ ❌",
                "bad_owner":    "Плохой владелец ❌",
                "bad_behavior": "Петушара 🐔",
                "spammer":      "Спамер 🚫",
                "raider":       "Рейдер 💥",
            }
            reasons_str = "\n".join(
                f"• {reasons_readable.get(r, r)}"
                for r in reasons
                if not r.startswith("other:")
            )
            other_reasons = [r.replace("other:", "") for r in reasons if r.startswith("other:")]
            if other_reasons:
                reasons_str += "\n• " + "\n• ".join(other_reasons)
            
            return (
                f"🔴 <b>MemoryBase: В базе!</b>\n{user_str}\n\n"
                f"<b>Причины:</b>\n{reasons_str or '— не определено'}\n\n"
                f"<a href=\"https://t.me/MemoryBaseBot\">MemoryBase</a>"
            )
        elif status == "not_found":
            return f"🟡 <b>MemoryBase: Не найден</b>\n{user_str}"
        else:
            return f"⚠️ <b>MemoryBase: Ошибка проверки</b>\n{user_str}"

    async def run(self):
        """Запуск бота."""
        if not MEMORY_BASE_BOT_TOKEN:
            logger.error("MEMORY_BASE_BOT_TOKEN не задан в .env!")
            return
        
        self.setup_handlers()
        self.dp.include_router(self.router)
        
        logger.info("[*] MemoryBase checker bot запущен")
        logger.info(f"[*] Проверки в чате: {ADMIN_CHECK_CHAT_ID}, топик: {ADMIN_CHECK_TOPIC_ID}")
        if DVR_CHANNEL_ID:
            logger.info(f"[*] DVR мониторинг: канал {DVR_CHANNEL_ID}, уведомления в топик {DVR_ADMIN_TOPIC_ID}")
        
        try:
            await self.dp.start_polling(self.bot)
        finally:
            await self.bot.session.close()


# ── HTTP API для основных ботов ────────────────────────────────────────────────
# Основные боты обращаются к Supabase напрямую через sb_get_check.
# memory_base_bot.py запускается как отдельный процесс и заполняет кэш.
# Для принудительного запроса проверки (без кэша) основной бот может
# POST на /api/mb/check (реализовано в server.py).

if __name__ == "__main__":
    service = MemoryBaseBotService()
    asyncio.run(service.run())
