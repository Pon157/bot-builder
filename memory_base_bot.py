"""
memory_base_bot.py  v3 — Pyrogram
================================================================================
Переписан с aiogram на Pyrogram.

Почему Pyrogram:
  - Видит сообщения от ДРУГИХ БОТОВ без прав администратора (user-режим или bot+admin)
  - Нет разницы между message/channel_post — всё одно событие
  - Нет проблем с порядком хендлеров
  - Прямой доступ к любым апдейтам без allowed_updates

FLOW MEMORYBASE:
  1. bot_core.py → INSERT в mb_check_queue (pending)
  2. queue_worker тянет задачи
  3. Пишет "чек <user_id>" в топик MB_CHECK_TOPIC_ID
  4. Pyrogram ловит ВСЕ сообщения в топике — включая от @MemoryBaseBot
  5. Парсит → POST в memory_base_cache
  6. Помечает задачу done

FLOW DVR:
  - Любой пост/пересылка в топик DVR_ADMIN_TOPIC_ID с @username бота
  - Останавливаем бота через API

ПЕРЕМЕННЫЕ .env:
  MEMORY_BASE_BOT_TOKEN   — токен бота (для Pyrogram Bot)
  PYROGRAM_API_ID         — api_id из my.telegram.org
  PYROGRAM_API_HASH       — api_hash из my.telegram.org
  ADMIN_CHECK_CHAT_ID     — ID супергруппы (-1003772028132)
  MB_CHECK_TOPIC_ID       — топик для чека (2)
  DVR_ADMIN_TOPIC_ID      — топик для DVR (4)
  SUPABASE_URL, SUPABASE_KEY
  BOTS_API_URL            — https://dialogengine.webtm.ru
  ADMIN_TOKEN             — секрет для API остановки
================================================================================
"""

import asyncio
import logging
import os
import re
import sys
import httpx

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Tuple

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait

from dotenv import load_dotenv
load_dotenv()

# Расшифровка токенов ботов (Fernet, ключ из ENCRYPTION_KEY)
try:
    from cryptography.fernet import Fernet
    _E_KEY = os.getenv("ENCRYPTION_KEY", "")
    _cipher = Fernet(_E_KEY.encode()) if _E_KEY else None
except Exception:
    _cipher = None

def decrypt_token(val: str) -> str:
    """Расшифровывает токен бота. Если не зашифрован — возвращает как есть."""
    if not val:
        return ""
    if _cipher is None:
        return val
    try:
        return _cipher.decrypt(val.encode()).decode()
    except Exception:
        return val  # уже расшифрован или не нужна расшифровка

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MemoryBaseBot")

# Подавляем спам Peer id invalid из Pyrogram для чужих чатов
logging.getLogger("pyrogram.client").setLevel(logging.ERROR)

# ── Конфиг ────────────────────────────────────────────────────────────────────
BOT_TOKEN    = os.getenv("MEMORY_BASE_BOT_TOKEN", "")
API_ID       = int(os.getenv("PYROGRAM_API_ID", "0"))
API_HASH     = os.getenv("PYROGRAM_API_HASH", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
BOTS_API_URL = os.getenv("BOTS_API_URL", "https://dialogengine.webtm.ru")
ADMIN_TOKEN  = os.getenv("ADMIN_TOKEN", "")

ADMIN_CHAT_ID      = int(os.getenv("ADMIN_CHECK_CHAT_ID") or os.getenv("ADMIN_CHAT_ID") or "0")
MB_CHECK_TOPIC_ID  = int(os.getenv("MB_CHECK_TOPIC_ID", "2"))
DVR_ADMIN_TOPIC_ID = int(os.getenv("DVR_ADMIN_TOPIC_ID", "4"))

QUEUE_POLL_INTERVAL = 2.0
MB_RESPONSE_TIMEOUT = 30.0
CACHE_TTL           = 86400

MB_REASON_MAP = {
    "мошенник":        "scammer",
    "плохой админ":    "bad_admin",
    "плохой владелец": "bad_owner",
    "петушара":        "bad_behavior",
    "спамер":          "spammer",
    "рейдер":          "raider",
}

# Ожидающие ответа: str(user_id) → asyncio.Future
_pending: Dict[str, asyncio.Future] = {}
_pending_lock = asyncio.Lock()

# ══════════════════════════════════════════════════════════════════════════════
# SUPABASE
# ══════════════════════════════════════════════════════════════════════════════

def _sb_h() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


async def sb_get_pending() -> List[dict]:
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{SUPABASE_URL}/rest/v1/mb_check_queue",
                headers=_sb_h(),
                params={"status": "eq.pending", "order": "created_at.asc",
                        "limit": "5", "select": "*"}
            )
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.error(f"[MB] sb_get_pending error: {e}")
    return []


async def sb_update_queue(row_id, upd: dict):
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.patch(
                f"{SUPABASE_URL}/rest/v1/mb_check_queue",
                headers={**_sb_h(), "Prefer": "return=minimal"},
                params={"id": f"eq.{row_id}"},
                json=upd
            )
            if r.status_code not in (200, 204):
                logger.error(f"[MB] sb_update_queue {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.error(f"[MB] sb_update_queue error: {e}")


async def sb_save_cache(user_id: int, username: str,
                        status: str, reasons: List[str], raw_text: str):
    expires = (datetime.now(timezone.utc) + timedelta(seconds=CACHE_TTL)).isoformat()
    payload = {
        "user_id":    user_id,
        "username":   username or "",
        "status":     status,
        "reasons":    reasons,
        "raw_text":   raw_text[:2000],
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{SUPABASE_URL}/rest/v1/memory_base_cache",
                headers={**_sb_h(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                json=payload
            )
            if r.status_code not in (200, 201, 204):
                logger.error(f"[MB] sb_save_cache error {r.status_code}: {r.text}")
            else:
                logger.info(f"[MB] ✅ Cached uid={user_id} status={status} reasons={reasons}")
    except Exception as e:
        logger.error(f"[MB] sb_save_cache exception: {e}")


async def sb_reset_stale_processing():
    """Сбрасываем задачи зависшие в processing > 2 мин обратно в pending."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.patch(
                f"{SUPABASE_URL}/rest/v1/mb_check_queue",
                headers={**_sb_h(), "Prefer": "return=minimal"},
                params={"status": "eq.processing", "updated_at": f"lt.{cutoff}"},
                json={"status": "pending"}
            )
            if r.status_code in (200, 204):
                logger.info("[MB] Stale tasks reset")
    except Exception as e:
        logger.warning(f"[MB] reset_stale error: {e}")


async def get_all_running_bots() -> List[dict]:
    """Возвращает все боты (RUNNING + IDLE) для DVR поиска по username."""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{SUPABASE_URL}/rest/v1/bots",
                headers=_sb_h(),
                params={"select": "id,name,config,status"}
            )
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.error(f"[DVR] get_all_bots error: {e}")
    return []


# Кеш username-ов ботов: bot_id → username
_bot_username_cache: Dict[str, str] = {}


async def resolve_bot_username(bot_id: str, token: str, bot_username_hint: str = "") -> Optional[str]:
    """Получаем username бота. Сначала из botUsername в конфиге, потом через getMe."""
    if bot_id in _bot_username_cache:
        return _bot_username_cache[bot_id]

    # Приоритет 1: botUsername из конфига (сохранён во фронтенде)
    hint = bot_username_hint.lower().lstrip("@").strip()
    if hint:
        _bot_username_cache[bot_id] = hint
        logger.info(f"[DVR] username from config: @{hint} for bot_id={bot_id}")
        return hint

    # Приоритет 2: getMe через токен
    if not token:
        return None
    raw_token = decrypt_token(token)
    if not raw_token:
        return None
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"https://api.telegram.org/bot{raw_token}/getMe")
            if r.status_code == 200:
                data = r.json()
                uname = data.get("result", {}).get("username", "").lower()
                if uname:
                    _bot_username_cache[bot_id] = uname
                    logger.info(f"[DVR] resolved via getMe: @{uname} for bot_id={bot_id}")
                    return uname
    except Exception as e:
        logger.warning(f"[DVR] getMe error for {bot_id}: {e}")
    return None


async def notify_bot_owner(app: Client, bot_record: dict, bot_username: str):
    """Уведомляем владельца бота о рейде в его admin_chat_id."""
    cfg = bot_record.get("config") or {}
    admin_chat_id = cfg.get("admin_chat_id") or cfg.get("adminChatId")
    if not admin_chat_id:
        logger.warning(f"[DVR] no admin_chat_id for bot {bot_record.get('id')}")
        return
    try:
        # Уведомление отправляем через токен САМОГО бота-воркера
        token = decrypt_token(cfg.get("token", ""))
        if not token:
            logger.warning(f"[DVR] no token for bot {bot_record.get('id')}, skipping owner notify")
            return
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": int(admin_chat_id),
                    "text": (
                        "🚨 <b>Система безопасности Dialoge Engine</b>\n\n"
                        f"Обнаружена рейдерская атака на вашего бота <b>@{bot_username}</b>.\n\n"
                        "✅ Бот был автоматически <b>остановлен</b> для защиты.\n\n"
                        "Восстановите работу бота на:\n"
                        '<a href="https://dialogengine.webtm.ru">dialogengine.webtm.ru</a>'
                    ),
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                }
            )
            if r.status_code == 200:
                logger.info(f"[DVR] owner notified via bot @{bot_username} → chat {admin_chat_id}")
            else:
                logger.warning(f"[DVR] sendMessage failed: {r.status_code} {r.text[:100]}")
    except Exception as e:
        logger.warning(f"[DVR] owner notify error for {bot_record.get('id')}: {e}")


async def notify_bot_owner(app: Client, bot_record: dict, bot_username: str):
    """Уведомляем владельца бота о рейде в его admin_chat_id."""
    cfg = bot_record.get("config") or {}
    admin_chat_id = cfg.get("admin_chat_id") or cfg.get("adminChatId")
    bot_name = bot_record.get("name") or bot_username
    if not admin_chat_id:
        logger.warning(f"[DVR] no admin_chat_id for bot {bot_record.get('id')}")
        return
    try:
        await app.send_message(
            chat_id=int(admin_chat_id),
            text=(
                f"🚨 <b>Система безопасности Dialoge Engine</b>\n\n"
                f"Обнаружена рейдерская атака на вашего бота "
                f"<b>@{bot_username}</b>.\n\n"
                f"✅ Бот был автоматически <b>остановлен</b> для защиты.\n\n"
                f"Восстановите работу бота на:\n"
                f"<a href=\"https://dialogengine.webtm.ru\">dialogengine.webtm.ru</a>"
            ),
            disable_web_page_preview=True
        )
        logger.info(f"[DVR] owner notified for bot {bot_record.get('id')} → chat {admin_chat_id}")
    except Exception as e:
        logger.warning(f"[DVR] owner notify error for {bot_record.get('id')}: {e}")


async def stop_bot_via_api(bot_id: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{BOTS_API_URL}/api/bots/stop/{bot_id}",
                headers={"X-Admin-Token": ADMIN_TOKEN, "Content-Type": "application/json"}
            )
            if r.status_code in (200, 201, 204):
                return True
            logger.error(f"[DVR] stop_bot {bot_id} failed: {r.status_code} {r.text[:100]}")
            return False
    except Exception as e:
        logger.error(f"[DVR] stop_bot error: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# ПАРСЕР
# ══════════════════════════════════════════════════════════════════════════════

def parse_mb_response(text: str) -> Tuple[str, List[str]]:
    if not text:
        return "not_found", []
    low = text.lower()

    if any(p in low for p in ["нет в базе", "не найден", "не поступало жалоб", "🟡", "🟢"]):
        return "clean", []

    if any(p in low for p in ["есть в базе", "🔴"]):
        reasons = []
        m = re.search(r'причина[:\s]+([^\n📖]+)', text, re.IGNORECASE)
        if m:
            raw   = m.group(1).strip()
            clean = re.sub(r'[^\w\s]', '', raw, flags=re.UNICODE).strip().lower()
            matched = False
            for kw, cat in MB_REASON_MAP.items():
                if kw in clean:
                    reasons.append(cat)
                    matched = True
            if not matched and raw:
                reasons.append(f"other:{raw[:60]}")
        return "in_base", reasons or ["other:unknown"]

    return "not_found", []


def extract_uid_from_mb(text: str) -> Optional[str]:
    m = re.search(r'\[(\d{5,})\]', text)
    return m.group(1) if m else None


def _is_mb_pattern(text: str) -> bool:
    low = text.lower()
    return any(p in low for p in [
        "нет в базе", "не найден", "есть в базе",
        "не поступало жалоб", "🔴", "🟡", "🟢",
        "человек есть", "человека нет", "memorybase", "memory base",
        "в базе данных", "чист", "жалоб нет", "найден в базе",
    ])


# ══════════════════════════════════════════════════════════════════════════════
# DVR HANDLER
# ══════════════════════════════════════════════════════════════════════════════

async def send_direct_notify(bot_record: dict, bot_username: str):
    """Отправляет уведомление владельцу напрямую через API Telegram."""
    owner_id = bot_record.get("user_id")
    token = bot_record.get("config", {}).get("token")
    if not owner_id or not token:
        return False

    text = (
        f"🚨 <b>ВНИМАНИЕ: Ваш бот @{bot_username} под атакой!</b>\n\n"
        f"Бот был автоматически <b>ОСТАНОВЛЕН</b>, так как его имя "
        f"появилось в списках DVR (рейд-атака).\n\n"
        f"Запустить бота можно в панели управления после завершения атаки."
    )
    
    try:
        # Используем временный клиент, чтобы отправить сообщение от имени самого бота
        async with httpx.AsyncClient() as client:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {"chat_id": owner_id, "text": text, "parse_mode": "HTML"}
            r = await client.post(url, json=payload, timeout=5)
            return r.status_code == 200
    except Exception as e:
        logger.error(f"[DVR] Ошибка уведомления владельца {owner_id}: {e}")
        return False

async def handle_dvr(app: Client, text: str):
    """
    Централизованная обработка DVR. 
    Сама находит, сама уведомляет, сама останавливает и отчитывается в чат админов.
    """
    _bot_username_cache.clear()
    bots = await get_all_running_bots()
    if not bots:
        return

    mentioned_usernames = set(re.findall(r'@(\w+)', text.lower()))
    if not mentioned_usernames:
        return

    matched = []
    tasks = []
    for br in bots:
        cfg = br.get("config") or {}
        tasks.append((br, resolve_bot_username(br["id"], cfg.get("token"), cfg.get("bot_username", ""))))

    for br, coro in tasks:
        uname = await coro
        if uname and uname.lower() in mentioned_usernames:
            matched.append((br, uname))

    if not matched:
        return

    stopped, failed = [], []

    for br, uname in matched:
        # 1. Прямое уведомление владельца (через Bot API напрямую)
        notified = await send_direct_notify(br, uname)
        if notified:
            logger.info(f"[DVR] Владелец @{uname} уведомлен напрямую.")
        
        # 2. Остановка бота через наш серверный API
        ok = await stop_bot_via_api(br["id"])
        if ok:
            stopped.append(uname)
            logger.warning(f"[DVR] Бот @{uname} остановлен.")
        else:
            failed.append(uname)
            logger.error(f"[DVR] Не удалось остановить @{uname}")

    # 3. ОТЧЕТ В ЧАТ АДМИНОВ (То, что у вас пропало)
    if stopped or failed:
        s_str = "\n".join(f"  • @{u}" for u in stopped) or "  —"
        f_str = "\n".join(f"  • @{u}" for u in failed) or "  —"
        
        text_out = (
            f"🚨 <b>DVR: Система защиты сработала!</b>\n\n"
            f"✅ <b>Остановлены боты ({len(stopped)}):</b>\n{s_str}\n\n"
            f"❌ <b>Ошибка остановки ({len(failed)}):</b>\n{f_str}\n\n"
            f"<i>Результат: Владельцы оповещены. Работа ботов прекращена.</i>"
        )
        
        try:
            # Отправляем отчет в ваш 4-й топик
            await app.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=text_out,
                reply_to_message_id=DVR_ADMIN_TOPIC_ID,
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"[DVR] Ошибка отправки отчета в админ-чат: {e}")
          
# ══════════════════════════════════════════════════════════════════════════════
# ОСНОВНОЙ СЕРВИС
# ══════════════════════════════════════════════════════════════════════════════

class MemoryBaseBotService:

    def __init__(self):
        # Если задан PYROGRAM_SESSION_STRING — используем готовую строку сессии
        # Если задан MEMORY_BASE_BOT_TOKEN — bot-режим
        # Иначе — интерактивная авторизация по номеру телефона (user-режим)
        session_string = os.getenv("PYROGRAM_SESSION_STRING", "")
        if session_string:
            # Строка сессии — запускается без интерактива, удобно для сервера
            self.app = Client(
                name="memory_base_checker",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=session_string,
            )
            logger.info("[*] Режим: user (session string)")
        elif BOT_TOKEN:
            # Bot-режим — НЕ видит сообщения от других ботов без admin прав
            self.app = Client(
                name="memory_base_checker",
                bot_token=BOT_TOKEN,
                api_id=API_ID,
                api_hash=API_HASH,
            )
            logger.info("[*] Режим: bot token")
        else:
            # User-режим — интерактивный вход по номеру телефона
            # Сессия сохранится в memory_base_checker.session
            # После первого входа перезапускать не нужно
            self.app = Client(
                name="memory_base_checker",
                api_id=API_ID,
                api_hash=API_HASH,
            )
            logger.info("[*] Режим: user (интерактивный вход)")
        self.is_running = True

    # ── Воркер очереди ────────────────────────────────────────────────────────

    async def queue_worker(self):
        logger.info("[MB] Queue worker started")
        iteration = 0
        while self.is_running:
            try:
                iteration += 1
                if iteration % 30 == 1:
                    await sb_reset_stale_processing()

                tasks = await sb_get_pending()
                for task in tasks:
                    row_id   = task["id"]
                    user_id  = int(task["user_id"])
                    username = task.get("username", "")
                    logger.info(f"[MB] Task id={row_id} user={user_id}")
                    await sb_update_queue(row_id, {"status": "processing"})
                    asyncio.create_task(self._do_check(row_id, user_id, username))
            except Exception as e:
                logger.error(f"[MB] queue_worker error: {e}")

            await asyncio.sleep(QUEUE_POLL_INTERVAL)

    # ── Проверка пользователя ─────────────────────────────────────────────────

    async def _do_check(self, row_id, user_id: int, username: str):
        key = str(user_id)
        loop = asyncio.get_event_loop()

        try:
            logger.info(f"[MB] Starting check: user={user_id}")

            # Создаём Future для ожидания ответа
            async with _pending_lock:
                if key in _pending and not _pending[key].done():
                    logger.info(f"[MB] Already pending for {user_id}, skip")
                    await sb_update_queue(row_id, {"status": "done"})
                    return
                fut = loop.create_future()
                _pending[key] = fut

            # Отправляем "чек user_id" в топик MB
            try:
                await self.app.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=f"чек {user_id}",
                    reply_to_message_id=MB_CHECK_TOPIC_ID
                )
                logger.info(f"[MB] Sent 'чек {user_id}' → topic {MB_CHECK_TOPIC_ID}")
            except FloodWait as e:
                logger.warning(f"[MB] FloodWait {e.value}s")
                await asyncio.sleep(e.value)
                await self.app.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=f"чек {user_id}",
                    reply_to_message_id=MB_CHECK_TOPIC_ID
                )

            # Ждём ответ от @MemoryBaseBot
            try:
                raw_text = await asyncio.wait_for(fut, timeout=MB_RESPONSE_TIMEOUT)
                logger.info(f"[MB] Got response for {user_id}: {raw_text[:80]!r}")
            except asyncio.TimeoutError:
                logger.warning(f"[MB] Timeout waiting for {user_id}")
                await sb_update_queue(row_id, {"status": "error", "error_text": "timeout"})
                return
            finally:
                async with _pending_lock:
                    _pending.pop(key, None)

            # Парсим и сохраняем
            status, reasons = parse_mb_response(raw_text)
            logger.info(f"[MB] Parsed: uid={user_id} status={status} reasons={reasons}")
            await sb_save_cache(user_id, username, status, reasons, raw_text)
            await sb_update_queue(row_id, {"status": "done"})

        except Exception as e:
            logger.error(f"[MB] _do_check exception for {user_id}: {e}")
            await sb_update_queue(row_id, {"status": "error", "error_text": str(e)[:200]})
            async with _pending_lock:
                _pending.pop(key, None)

    # ── Запуск ────────────────────────────────────────────────────────────────

    async def run(self):
        if not BOT_TOKEN:
            logger.error("MEMORY_BASE_BOT_TOKEN не задан!")
            return
        if not API_ID or not API_HASH:
            logger.error("PYROGRAM_API_ID / PYROGRAM_API_HASH не заданы!")
            return

        logger.info(f"[*] MemoryBase Bot (Pyrogram) запускается")
        logger.info(f"[*] Чат={ADMIN_CHAT_ID} | MB топик={MB_CHECK_TOPIC_ID} | DVR топик={DVR_ADMIN_TOPIC_ID}")

        # ── Единый хендлер для всего нашего чата ─────────────────────────────
        # Pyrogram 2.0.106 в user-режиме не передаёт message_thread_id для топиков
        # поэтому различаем MB и DVR по содержимому сообщения

        @self.app.on_message(
            filters.create(lambda _, __, m: getattr(m.chat, "id", None) == ADMIN_CHAT_ID)
        )
        async def on_admin_chat(client: Client, msg: Message):
            text   = (msg.text or msg.caption or "").strip()
            thread = getattr(msg, "message_thread_id", None)
            sender = (getattr(msg.from_user, "username", None) or
                      getattr(msg.sender_chat, "username", None) or
                      str(getattr(msg.from_user, "id", "?") if msg.from_user else "?"))
            logger.info(f"[CHAT] thread={thread} from=@{sender} text={text[:80]!r}")

            # Пропускаем наши собственные "чек X"
            if re.match(r'^чек\s+\d+', text, re.IGNORECASE):
                return

            # ── Ответ от @MemoryBaseBot → резолвим Future ─────────────────
            if _is_mb_pattern(text) or extract_uid_from_mb(text):
                uid_from_text = extract_uid_from_mb(text)
                async with _pending_lock:
                    if uid_from_text and uid_from_text in _pending:
                        fut = _pending[uid_from_text]
                        if not fut.done():
                            fut.set_result(text)
                            logger.info(f"[MB] ✅ Resolved uid={uid_from_text}")
                            return
                    for k, fut in list(_pending.items()):
                        if not fut.done():
                            fut.set_result(text)
                            logger.info(f"[MB] ✅ Resolved first pending key={k}")
                            return
                return  # MB паттерн но нет ожидающих — игнорируем

            # ── DVR: сообщение содержит @username → проверяем наших ботов ──
            fwd = msg.forward_from_chat
            if "@" in text or fwd:
                logger.info(f"[DVR] обрабатываем: {text[:60]!r}")
                await handle_dvr(self.app, text)

        # Запускаем воркер и polling
        async with self.app:
            me = await self.app.get_me()
            logger.info(f"[*] ✅ Авторизован как @{me.username} id={me.id}")

            # Подавляем Peer id invalid для чужих чатов
            asyncio.get_event_loop().set_exception_handler(
                lambda loop, ctx: None if "Peer id invalid" in str(ctx.get("exception", "")) else loop.default_exception_handler(ctx)
            )
            # Резолвим наш чат через get_dialogs
            self._chat_peer = ADMIN_CHAT_ID
            try:
                logger.info("[*] Сканирую диалоги...")
                async for dialog in self.app.get_dialogs():
                    if dialog.chat.id == ADMIN_CHAT_ID:
                        logger.info(f"[*] ✅ Чат: {dialog.chat.title!r}")
                        break
                else:
                    logger.error("[*] ❌ Чат не найден в диалогах!")
            except Exception as e:
                logger.error(f"[*] ❌ get_dialogs: {e}")

            asyncio.create_task(self.queue_worker())

            logger.info("[*] Pyrogram polling started — ловим ВСЕ сообщения включая от ботов")
            await asyncio.Event().wait()  # держим app живым


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    service = MemoryBaseBotService()
    await service.run()


async def generate_session_string():
    """
    Запусти python3 memory_base_bot.py --gen-session
    Введи номер телефона и код — получишь SESSION_STRING для .env
    """
    print("=== Генерация SESSION_STRING для user-режима ===")
    print(f"API_ID={API_ID}, API_HASH={'*' * 8 if API_HASH else 'НЕ ЗАДАН'}")
    app = Client(
        name="session_gen",
        api_id=API_ID,
        api_hash=API_HASH,
    )
    async with app:
        session = await app.export_session_string()
        print("\n✅ Твоя SESSION_STRING (добавь в .env):")
        print(f"PYROGRAM_SESSION_STRING={session}")
        print("\nПосле добавления в .env убери MEMORY_BASE_BOT_TOKEN из запуска чекера,")
        print("или оставь — user-режим имеет приоритет.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--gen-session":
        asyncio.run(generate_session_string())
    else:
        asyncio.run(main())
