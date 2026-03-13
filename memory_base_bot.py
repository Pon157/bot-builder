"""
memory_base_bot.py  v2
================================================================================
ИСПРАВЛЕННАЯ АРХИТЕКТУРА:

  FLOW MEMORYBASE:
  1. bot_core.py (MemoryBaseMiddleware) → INSERT в mb_check_queue (status=pending)
  2. memory_base_bot.py polling-ом тянет задачи из mb_check_queue
  3. Пишет "чек <user_id>" в топик 2 чата администраторов
  4. Ловит ЛЮБОЕ сообщение в топике 2 с паттернами MemoryBase в тексте
     (не фильтруем по from_user — aiogram не видит другие боты в группе,
      зато видит их сообщения если наш бот — администратор группы)
  5. Парсит ответ, POST в memory_base_cache
  6. Помечает задачу done
  7. bot_core.py при следующей проверке GET из memory_base_cache видит результат

  FLOW DVR:
  - Кто-то пересылает пост из DVR-канала в ТОПИК 4
  - Фильтр СТРОГО: chat_id=ADMIN_CHAT_ID AND message_thread_id=DVR_ADMIN_TOPIC_ID
  - Ищем username наших ботов → останавливаем → уведомляем

ВАЖНО для работы MB-ответов:
  Наш чекер-бот должен быть АДМИНИСТРАТОРОМ группы с правом
  "Читать сообщения" (в Telegram это права бота в группе).
  Тогда aiogram получит сообщения от @MemoryBaseBot через polling.

ПЕРЕМЕННЫЕ .env:
  MEMORY_BASE_BOT_TOKEN  — токен чекер-бота
  ADMIN_CHAT_ID          — ID чата администраторов (-1003772028132)
  MB_CHECK_TOPIC_ID      — топик для проверок (2)
  DVR_ADMIN_TOPIC_ID     — топик для DVR-постов (4)
  SUPABASE_URL, SUPABASE_KEY
  BOTS_API_URL           — https://dialogengine.webtm.ru
  ADMIN_TOKEN            — секрет для API остановки ботов
================================================================================
"""

import asyncio
import logging
import os
import re
import sys
import secrets
import httpx
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple

from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.client.default import DefaultBotProperties

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MemoryBaseBot")

# ── Конфиг ────────────────────────────────────────────────────────────────────
MEMORY_BASE_BOT_TOKEN = os.getenv("MEMORY_BASE_BOT_TOKEN", "")
SUPABASE_URL          = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY          = os.getenv("SUPABASE_KEY", "")
BOTS_API_URL          = os.getenv("BOTS_API_URL", "https://dialogengine.webtm.ru")
ADMIN_TOKEN           = os.getenv("ADMIN_TOKEN", "")
ADMIN_CHAT_ID         = int(os.getenv("ADMIN_CHECK_CHAT_ID", os.getenv("ADMIN_CHAT_ID", "-1003772028132")))
MB_CHECK_TOPIC_ID     = int(os.getenv("ADMIN_CHECK_TOPIC_ID", os.getenv("MB_CHECK_TOPIC_ID", "2")))
DVR_ADMIN_TOPIC_ID    = int(os.getenv("DVR_ADMIN_TOPIC_ID", "4"))

QUEUE_POLL_INTERVAL = 2.0    # сек между опросами очереди
MB_RESPONSE_TIMEOUT = 30.0   # сек ожидания ответа MemoryBase
CACHE_TTL           = 86400  # 24 часа

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


async def sb_get_pending_checks() -> List[dict]:
    """Получить задачи со статусом pending из mb_check_queue."""
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


async def sb_update_queue(row_id: str, upd: dict):
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            await c.patch(
                f"{SUPABASE_URL}/rest/v1/mb_check_queue",
                headers={**_sb_h(), "Prefer": "return=minimal"},
                params={"id": f"eq.{row_id}"},
                json=upd
            )
    except Exception as e:
        logger.error(f"[MB] sb_update_queue error: {e}")


async def sb_save_cache(user_id: int, username: str,
                        status: str, reasons: List[str], raw_text: str):
    """Сохранить результат в memory_base_cache (upsert по user_id)."""
    expires = (datetime.utcnow() + timedelta(seconds=CACHE_TTL)).isoformat()
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
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{SUPABASE_URL}/rest/v1/memory_base_cache",
                headers={**_sb_h(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                json=payload
            )
            if r.status_code not in [200, 201, 204]:
                logger.error(f"[MB] sb_save_cache error {r.status_code}: {r.text}")
            else:
                logger.info(f"[MB] Cached user={user_id} status={status} reasons={reasons}")
    except Exception as e:
        logger.error(f"[MB] sb_save_cache exception: {e}")


async def get_all_running_bots() -> List[dict]:
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{SUPABASE_URL}/rest/v1/bots",
                headers=_sb_h(),
                params={"status": "eq.RUNNING", "select": "id,name,config"}
            )
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.error(f"[DVR] get_all_running_bots error: {e}")
    return []


async def stop_bot_via_api(bot_id: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{BOTS_API_URL}/api/bots/stop",
                json={"bot_id": bot_id},
                headers={"X-Admin-Token": ADMIN_TOKEN,
                         "Content-Type": "application/json"}
            )
            return r.status_code in [200, 201, 204]
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
            raw = m.group(1).strip()
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
    """Извлекает user_id из строки вида '🔴 @name / [12345678]'."""
    m = re.search(r'\[(\d{5,})\]', text)
    return m.group(1) if m else None


def _is_mb_pattern(text: str) -> bool:
    """Проверяет, похож ли текст на ответ MemoryBase."""
    low = text.lower()
    return any(p in low for p in [
        "нет в базе", "не найден", "есть в базе",
        "не поступало жалоб", "🔴", "🟡", "🟢",
        "человек есть", "человека нет", "memorybase"
    ])


# ══════════════════════════════════════════════════════════════════════════════
# СЕРВИС
# ══════════════════════════════════════════════════════════════════════════════

class MemoryBaseBotService:

    def __init__(self):
        self.bot = Bot(
            token=MEMORY_BASE_BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        self.dp         = Dispatcher()
        self.router     = Router()
        self.is_running = True

    # ── Воркер очереди ────────────────────────────────────────────────────────

    async def queue_worker(self):
        """Поллинг mb_check_queue → выполнение проверок."""
        logger.info("[MB] Queue worker started")
        while self.is_running:
            try:
                tasks = await sb_get_pending_checks()
                for task in tasks:
                    row_id   = task["id"]
                    user_id  = int(task["user_id"])
                    username = task.get("username", "")

                    # Помечаем processing сразу
                    await sb_update_queue(row_id, {"status": "processing"})

                    asyncio.create_task(
                        self._do_check(row_id, user_id, username)
                    )
            except Exception as e:
                logger.error(f"[MB] queue_worker error: {e}")

            await asyncio.sleep(QUEUE_POLL_INTERVAL)

    async def _do_check(self, row_id: str, user_id: int, username: str):
        """
        Выполняет одну проверку:
        1. Пишет "чек <user_id>" в топик 2
        2. Ждёт когда on_mb_topic_message зарезолвит Future
        3. Парсит, сохраняет в кэш, помечает done
        """
        key = str(user_id)
        logger.info(f"[MB] Starting check: user={user_id}")

        loop   = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()

        async with _pending_lock:
            # Не дублируем если уже ждём
            if key in _pending and not _pending[key].done():
                logger.info(f"[MB] Already pending for {key}, skipping duplicate")
                await sb_update_queue(row_id, {"status": "done"})
                return
            _pending[key] = future

        try:
            # Пишем запрос в топик 2
            await self.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=f"чек {user_id}",
                message_thread_id=MB_CHECK_TOPIC_ID
            )
            logger.info(f"[MB] Sent 'чек {user_id}' → topic {MB_CHECK_TOPIC_ID}")

            # Ждём ответа из обработчика on_mb_topic_message
            raw_text = await asyncio.wait_for(future, timeout=MB_RESPONSE_TIMEOUT)

        except asyncio.TimeoutError:
            logger.warning(f"[MB] Timeout for user {user_id}")
            await sb_update_queue(row_id, {"status": "error", "error_text": "timeout"})
            async with _pending_lock:
                _pending.pop(key, None)
            return

        except Exception as e:
            logger.error(f"[MB] _do_check exception for {user_id}: {e}")
            await sb_update_queue(row_id, {"status": "error", "error_text": str(e)[:200]})
            async with _pending_lock:
                _pending.pop(key, None)
            return

        finally:
            async with _pending_lock:
                _pending.pop(key, None)

        # Парсим и сохраняем
        status, reasons = parse_mb_response(raw_text)
        logger.info(f"[MB] Parsed: user={user_id} status={status} reasons={reasons}")

        await sb_save_cache(user_id, username, status, reasons, raw_text)
        await sb_update_queue(row_id, {"status": "done"})

    # ── Обработчики ──────────────────────────────────────────────────────────

    def setup_handlers(self):

        # ── ДИАГНОСТИКА через middleware (не блокирует цепочку) ───────────────

        from aiogram import BaseMiddleware
        from typing import Callable, Awaitable, Any

        class DebugMiddleware(BaseMiddleware):
            async def __call__(self, handler: Callable, event: Message, data: dict) -> Any:
                logger.info(
                    f"[ALL] chat={event.chat.id} thread={event.message_thread_id} "
                    f"from={event.from_user.id if event.from_user else 'none'} "
                    f"fwd_chat={event.forward_from_chat.id if event.forward_from_chat else '-'} "
                    f"text={((event.text or event.caption or '')[:60])!r}"
                )
                return await handler(event, data)

        self.router.message.middleware(DebugMiddleware())

        # ── ТОПИК 2: ловим ВСЕ сообщения в MB-топике ────────────────────────
        # Строго фильтруем: chat_id == ADMIN_CHAT_ID и thread_id == MB_CHECK_TOPIC_ID
        # Пропускаем свои собственные запросы "чек X"
        # Резолвим pending Future когда видим ответ-паттерн MemoryBase

        @self.router.message(
            F.chat.id == ADMIN_CHAT_ID,
            F.message_thread_id == MB_CHECK_TOPIC_ID
        )
        async def on_mb_topic_message(m: Message):
            text = (m.text or m.caption or "").strip()

            # DEBUG: логируем все входящие в топик 2 для диагностики
            logger.info(
                f"[MB DEBUG] topic={m.message_thread_id} "
                f"from={m.from_user.id if m.from_user else 'chan'} "
                f"text={text[:80]!r}"
            )

            if not text:
                return

            # Пропускаем СВОИ запросы
            if re.match(r'^чек\s+\d+', text, re.IGNORECASE):
                logger.debug(f"[MB] Skipping own request: {text[:40]}")
                return

            # Проверяем паттерн MemoryBase
            if not _is_mb_pattern(text):
                logger.debug(f"[MB] Not MB pattern, skipping: {text[:60]!r}")
                return

            logger.info(f"[MB] MB response in topic {MB_CHECK_TOPIC_ID}: {text[:100]}")

            # Извлекаем user_id из ответа
            uid_from_text = extract_uid_from_mb(text)

            async with _pending_lock:
                resolved = False

                # Резолвим по конкретному user_id если нашли в тексте
                if uid_from_text and uid_from_text in _pending:
                    fut = _pending[uid_from_text]
                    if not fut.done():
                        fut.set_result(text)
                        logger.info(f"[MB] Resolved future for uid={uid_from_text}")
                        resolved = True

                # Иначе — резолвим первый незавершённый Future
                if not resolved:
                    for key, fut in list(_pending.items()):
                        if not fut.done():
                            fut.set_result(text)
                            logger.info(f"[MB] Resolved first pending future (key={key})")
                            break

        # ── ТОПИК 4: DVR — строго фильтруем по thread_id ────────────────────
        # Сюда попадают ТОЛЬКО сообщения из топика 4 (DVR-уведомлений)
        # Никакой другой топик не затрагивается

        @self.router.message(
            F.chat.id == ADMIN_CHAT_ID,
            F.message_thread_id == DVR_ADMIN_TOPIC_ID
        )
        async def on_dvr_topic_message(m: Message):
            text = (m.text or m.caption or "").strip()

            # DEBUG: логируем ВСЁ что приходит в топик 4
            logger.info(
                f"[DVR DEBUG] topic={m.message_thread_id} "
                f"from={m.from_user.id if m.from_user else 'chan'} "
                f"fwd_chat={m.forward_from_chat.id if m.forward_from_chat else None} "
                f"text={text[:60]!r}"
            )

            if not text:
                return

            # Ищем: либо пересланное из другого чата/канала, либо паттерны рейда в тексте
            is_forwarded_from_channel = (m.forward_from_chat is not None)
            has_raid_pattern = any(p in text.lower() for p in [
                "рейд", "raid", "флуд", "flood", "атак", "спам", "spam"
            ])

            if not is_forwarded_from_channel and not has_raid_pattern:
                logger.debug(f"[DVR] Not a raid signal, skipping")
                return

            logger.info(f"[DVR] Raid signal in topic {DVR_ADMIN_TOPIC_ID}: {text[:120]}")
            await _handle_dvr(self.bot, text)

        # ── /check — ручная проверка ─────────────────────────────────────────

        @self.router.message(Command("check"))
        async def cmd_check(m: Message):
            parts = (m.text or "").split(maxsplit=1)
            if len(parts) < 2:
                await m.reply("Использование: /check <user_id>")
                return

            query = parts[1].strip().lstrip("@")
            if not query.isdigit():
                await m.reply("❌ Передайте числовой user_id")
                return

            uid = int(query)
            sm  = await m.reply("🔍 Проверяю...")

            # Создаём задачу в очереди
            row_id = f"mbq_{secrets.token_hex(6)}"
            try:
                async with httpx.AsyncClient(timeout=8) as c:
                    await c.post(
                        f"{SUPABASE_URL}/rest/v1/mb_check_queue",
                        headers={**_sb_h(), "Prefer": "return=minimal"},
                        json={"id": row_id, "user_id": uid,
                              "username": "", "status": "pending",
                              "created_at": datetime.utcnow().isoformat()}
                    )
            except Exception as e:
                await sm.edit_text(f"❌ Ошибка постановки в очередь: {e}")
                return

            # Ждём результата (поллинг кэша)
            deadline = time.time() + 35
            result   = None
            while time.time() < deadline:
                await asyncio.sleep(2)
                try:
                    async with httpx.AsyncClient(timeout=5) as c:
                        r = await c.get(
                            f"{SUPABASE_URL}/rest/v1/memory_base_cache",
                            headers=_sb_h(),
                            params={"user_id": f"eq.{uid}", "select": "*"}
                        )
                        if r.status_code == 200 and r.json():
                            result = r.json()[0]
                            break
                except Exception:
                    pass

            if result:
                status  = result.get("status", "not_found")
                reasons = result.get("reasons", [])
                await sm.edit_text(_fmt({"status": status, "reasons": reasons,
                                         "user_id": uid, "username": result.get("username", "")}))
            else:
                await sm.edit_text("⏱ Таймаут — MemoryBase не ответил вовремя")

    # ── Запуск ────────────────────────────────────────────────────────────────

    async def run(self):
        if not MEMORY_BASE_BOT_TOKEN:
            logger.error("MEMORY_BASE_BOT_TOKEN не задан в .env!")
            return

        self.setup_handlers()
        self.dp.include_router(self.router)

        logger.info(f"[*] MemoryBase Bot запущен")
        logger.info(f"[*] Чат={ADMIN_CHAT_ID} | MB топик={MB_CHECK_TOPIC_ID} | DVR топик={DVR_ADMIN_TOPIC_ID}")

        asyncio.create_task(self.queue_worker())

        # ВАЖНО: allowed_updates должен включать "message" и "channel_post"
        # Чтобы получать сообщения от @MemoryBaseBot в группе, наш бот
        # ОБЯЗАН быть АДМИНИСТРАТОРОМ группы — иначе Telegram не шлёт
        # сообщения от других ботов нашему боту.
        try:
            await self.dp.start_polling(
                self.bot,
                allowed_updates=["message", "channel_post",
                                  "edited_message", "callback_query"]
            )
        finally:
            self.is_running = False
            await self.bot.session.close()


# ══════════════════════════════════════════════════════════════════════════════
# DVR HANDLER (вынесен наружу для чистоты)
# ══════════════════════════════════════════════════════════════════════════════

async def _handle_dvr(bot: Bot, text: str):
    """Ищем наших ботов в тексте DVR-поста и останавливаем."""
    bots = await get_all_running_bots()
    if not bots:
        return

    text_lower = text.lower()
    mentioned  = []

    for br in bots:
        cfg  = br.get("config") or {}
        uname = (
            cfg.get("botUsername") or cfg.get("bot_username") or
            cfg.get("username") or ""
        ).lower().lstrip("@")

        if uname and (uname in text_lower or f"@{uname}" in text_lower):
            mentioned.append(br)
            logger.warning(f"[DVR] Mentioned bot: {br.get('name')} (@{uname})")

    if not mentioned:
        logger.info("[DVR] No our bots found in post")
        return

    stopped, failed = [], []
    for br in mentioned:
        ok = await stop_bot_via_api(br["id"])
        (stopped if ok else failed).append(br.get("name", br["id"]))

    s_str = "\n".join(f"  • {n}" for n in stopped) or "  —"
    f_str = "\n".join(f"  • {n}" for n in failed)  or "  —"

    text_out = (
        f"🚨 <b>DVR: Рейд-атака!</b>\n\n"
        f"✅ <b>Остановлено:</b>\n{s_str}\n\n"
        f"❌ <b>Не удалось:</b>\n{f_str}\n\n"
        f"Восстановите работу на:\n"
        f"<a href=\"https://dialogengine.webtm.ru\">dialogengine.webtm.ru</a>"
    )
    try:
        await bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=text_out,
            message_thread_id=DVR_ADMIN_TOPIC_ID,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"[DVR] notify error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# ФОРМАТИРОВАНИЕ
# ══════════════════════════════════════════════════════════════════════════════

def _fmt(r: dict) -> str:
    HR = {
        "scammer": "Мошенник ⛔️", "bad_admin": "Плохой админ ❌",
        "bad_owner": "Плохой владелец ❌", "bad_behavior": "Петушара 🐔",
        "spammer": "Спамер 🚫", "raider": "Рейдер 💥",
    }
    uid  = r.get("user_id")
    un   = r.get("username", "")
    st   = r.get("status", "error")
    reas = r.get("reasons", [])

    u = (f"ID: <code>{uid}</code>" if uid else "") + (f"  @{un}" if un else "")

    if st == "clean":
        return f"✅ <b>MemoryBase: Чисто</b>\n{u}\nНе найден в базе."
    if st == "in_base":
        lines = "\n".join(f"• {HR.get(x, x)}" for x in reas if not x.startswith("other:"))
        other = [x.replace("other:", "") for x in reas if x.startswith("other:")]
        if other:
            lines += "\n• " + "\n• ".join(other)
        return f"🔴 <b>MemoryBase: В базе!</b>\n{u}\n\n<b>Причины:</b>\n{lines or '—'}"
    return f"🟡 <b>MemoryBase: Нет данных</b>\n{u}"


if __name__ == "__main__":
    asyncio.run(MemoryBaseBotService().run())
