"""
free_bot_core.py
================================================================================
ИСПРАВЛЕНИЯ v6:
  • /start: inlineButtons теперь читаются из config["inlineButtons"] (новый формат),
    поддерживает тип "url" (URL-кнопка) и "message" (callback с текстом).
    Старый welcomeInline (только url) тоже поддерживается для обратной совместимости.
  • reload_config_from_remote: синхронизирует inlineButtons при горячей перезагрузке.
  • build_welcome_inline: отдельный метод, строит InlineKeyboardMarkup из
    нового формата [{id, text, type:"url"|"message", value}].
  • handle_start: корректно отправляет reply_kb ПОСЛЕ inline-кнопок (два
    сообщения), так как Telegram не позволяет смешивать reply и inline в одном.
  • Все исправления v5 сохранены.
================================================================================
"""

import asyncio
import logging
import json
import httpx
import os
import sys
import hashlib
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any, Callable

from aiogram import Bot, Dispatcher, Router, F, BaseMiddleware
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.filters import CommandStart, Command, ChatMemberUpdatedFilter
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
    ReplyKeyboardRemove, ChatMemberUpdated
)
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("FreeBotCore")


# ════════════════════════════════════════════════════════════════════════════════
# MIDDLEWARE
# ════════════════════════════════════════════════════════════════════════════════

class BanMiddleware(BaseMiddleware):
    def __init__(self, bot_instance):
        self.bi = bot_instance
        super().__init__()

    async def __call__(self, handler: Callable, event: Any, data: Dict) -> Any:
        user_tg = getattr(event, "from_user", None)
        if user_tg:
            user = next((u for u in self.bi.users_list if u.get("id") == user_tg.id), None)
            if user and user.get("is_banned"):
                is_admin = (user_tg.id in self.bi.admin_ids) if self.bi.admin_ids else False
                if is_admin:
                    # Пропускаем callback с разбаном
                    if isinstance(event, CallbackQuery) and event.data == "selfunban":
                        return await handler(event, data)
                    unban_kb = InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔓 Разбанить себя", callback_data="selfunban")
                    ]])
                    try:
                        if isinstance(event, Message):
                            await event.answer(
                                "⚠️ <b>Вы случайно забанили себя (администратора).</b>\n"
                                "Нажмите кнопку ниже, чтобы снять блокировку:",
                                reply_markup=unban_kb
                            )
                        elif isinstance(event, CallbackQuery):
                            await event.answer("⚠️ Вы забанили себя. Напишите /start чтобы разбаниться.", show_alert=True)
                    except Exception:
                        pass
                    return
                if isinstance(event, Message):
                    try:
                        await event.answer("🚫 <b>Вы заблокированы в этом боте.</b>")
                    except Exception:
                        pass
                elif isinstance(event, CallbackQuery):
                    try:
                        await event.answer("🚫 Вы заблокированы.", show_alert=True)
                    except Exception:
                        pass
                return
        return await handler(event, data)


# ════════════════════════════════════════════════════════════════════════════════
# MEMORY BASE MIDDLEWARE
# ════════════════════════════════════════════════════════════════════════════════

class MemoryBaseMiddleware(BaseMiddleware):
    """
    Проверяет пользователей по антиспам-базе MemoryBase.
    Работает через кэш в Supabase (таблица memory_base_cache).
    """
    def __init__(self, bot_instance):
        self.bi = bot_instance
        super().__init__()

    async def __call__(self, handler: Callable, event: Any, data: Dict) -> Any:
        settings = getattr(self.bi, 'settings', {})
        _uid = getattr(getattr(event, 'from_user', None), 'id', '?')
        logger.info(f"[MB] middleware called uid={_uid} enabled={settings.get('memoryBaseEnabled')} settings_keys={list(settings.keys())[:5]}")
        if not settings.get('memoryBaseEnabled', False):
            return await handler(event, data)

        user_tg = getattr(event, 'from_user', None)
        if not user_tg:
            return await handler(event, data)

        user_id = user_tg.id

        if user_id in (self.bi.admin_ids or set()):
            return await handler(event, data)

        if isinstance(event, CallbackQuery) and event.data and event.data.startswith("mb_unban_"):
            return await handler(event, data)

        user_rec = next((u for u in self.bi.users_list if u.get('id') == user_id), None)

        # ── Локальный TTL-кэш: не ходим в Supabase чаще раза в 5 минут ──────
        # Исключение: если mb_restricted=True — перепроверяем каждые 5 мин (вдруг разбанили)
        MB_LOCAL_TTL = 300  # 5 минут
        last_mb_check = user_rec.get('last_mb_check', 0) if user_rec else 0
        mb_restricted = user_rec.get('mb_restricted', False) if user_rec else False

        if user_rec and not mb_restricted and (time.time() - last_mb_check < MB_LOCAL_TTL):
            # Знаем статус, он свежий и пользователь чист — пропускаем без запроса
            return await handler(event, data)

        # ── Проверяем актуальный статус в Supabase ──────────────────────────
        # Только если: новый пользователь / кэш устарел / пользователь был заблокирован
        try:
            sb_url = self.bi.sb_url
            h = self.bi.headers
            async with httpx.AsyncClient(timeout=5) as _c:
                _r = await _c.get(
                    f"{sb_url}/rest/v1/memory_base_cache",
                    headers=h,
                    params={"user_id": f"eq.{user_id}", "select": "status,reasons,expires_at"}
                )
                if _r.status_code == 200:
                    _rows = _r.json()
                    if _rows:
                        _cache_row = _rows[0]
                        _status  = _cache_row.get('status', 'not_found')
                        _reasons = _cache_row.get('reasons', [])
                        logger.info(f"[MB] uid={user_id} supabase status={_status} reasons={_reasons}")

                        if _status == 'in_base':
                            _block_reasons = settings.get('memoryBaseBlockReasons', [])
                            _should_block  = (not _block_reasons or any(r in _block_reasons for r in _reasons))
                            if _should_block:
                                if user_rec:
                                    user_rec['mb_restricted'] = True
                                    user_rec['mb_reasons']    = _reasons
                                if isinstance(event, Message):
                                    await event.answer(
                                        "🚫 <b>Доступ ограничен.</b>\n\n"
                                        "Вы находитесь в антиспам-базе "
                                        "<a href=\"https://t.me/MemoryBaseBot\">MemoryBase</a>.\n"
                                        "Для восстановления доступа обратитесь к владельцу бота."
                                    )
                                elif isinstance(event, CallbackQuery):
                                    await event.answer("🚫 Доступ ограничен (MemoryBase).", show_alert=True)
                                _already_notified = user_rec.get('mb_notified', False) if user_rec else False
                                if self.bi.admin_chat_id and not _already_notified:
                                    try:
                                        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                                        _rh = {"scammer":"Мошенник ⛔️","bad_admin":"Плохой админ ❌",
                                               "bad_owner":"Плохой владелец ❌","bad_behavior":"Нарушитель 🐔",
                                               "spammer":"Спамер 🚫","raider":"Рейдер 💥"}
                                        _rt = ", ".join(_rh.get(r,r) for r in _reasons if not r.startswith("other:"))
                                        _ot = [r.replace("other:","") for r in _reasons if r.startswith("other:")]
                                        if _ot: _rt += (", " if _rt else "") + ", ".join(_ot)
                                        _nm = user_tg.full_name or f"User {user_id}"
                                        _un = f" (@{user_tg.username})" if user_tg.username else ""
                                        _is_start = isinstance(event, Message) and bool(getattr(event, 'text', '') or '') and (event.text or '').strip().startswith("/start")
                                        _act = "написал /start" if _is_start else "написал сообщение"
                                        _kb = InlineKeyboardMarkup(inline_keyboard=[[
                                            InlineKeyboardButton(text="✅ Разрешить доступ", callback_data=f"mb_unban_{user_id}")
                                        ]])
                                        await self.bi.bot.send_message(
                                            self.bi.admin_chat_id,
                                            f"🔴 <b>MemoryBase: пользователь в базе</b>\n\n"
                                            f"👤 {_nm}{_un}\n🆔 <code>{user_id}</code>\n"
                                            f"📌 <b>Причина(ы):</b> {_rt or '—'}\n\n"
                                            f"Пользователь {_act} и был заблокирован.\n"
                                            f"Если хотите разрешить ему писать — нажмите кнопку ниже 👇",
                                            reply_markup=_kb,
                                        )
                                        if user_rec:
                                            user_rec['mb_notified'] = True
                                            await self.bi.sync_queue.put(("sync_state", None))
                                    except Exception as _ne:
                                        logger.warning(f"[MB] admin notify error: {_ne}")
                                return  # БЛОКИРУЕМ
                        else:
                            # Статус clean/not_found — снимаем локальный флаг если был
                            if user_rec and user_rec.get('mb_restricted'):
                                user_rec['mb_restricted'] = False
                                user_rec['mb_reasons']    = []
                            # Обновляем метку — при следующем сообщении не будем ходить в Supabase
                            if user_rec:
                                user_rec['last_mb_check'] = int(time.time())
                        # Запись есть — проверяем нужна ли перепроверка (раз в 24ч)
                        if time.time() - last_mb_check < 86400:
                            return await handler(event, data)
                        # Иначе — ставим в очередь на перепроверку
                    else:
                        # Записи нет — первичная проверка
                        logger.info(f"[MB] uid={user_id} no cache row — queuing check")
                else:
                    logger.warning(f"[MB] supabase check failed {_r.status_code} — пропускаем")
                    return await handler(event, data)
        except Exception as _e:
            logger.warning(f"[MB] supabase pre-check error: {_e} — пропускаем")
            return await handler(event, data)

        # Уведомляем пользователя что идёт проверка
        wait_msg = None
        try:
            if isinstance(event, Message):
                wait_msg = await event.answer(
                    "🔍 <b>Проверяю вас по базе пользователей в Memory Base...</b>\nПожалуйста, подождите."
                )
        except Exception:
            pass

        # Ждём результат (блокируем до ответа чекера)
        should_block = await self._check_and_restrict(event, user_tg, user_rec, settings)

        if wait_msg:
            try:
                await wait_msg.delete()
            except Exception:
                pass

        if should_block:
            return
        return await handler(event, data)

    async def _check_and_restrict(self, event: Any, user_tg, user_rec: Optional[dict], settings: dict):
        user_id = user_tg.id
        sb_url = self.bi.sb_url
        headers = self.bi.headers
        try:
            import logging as _log
            _log.getLogger("MB").info(f"[MB] _check_and_restrict started for user_id={user_id}")
            # ── ШАГ 1: Ставим задачу в очередь для чекер-бота ─────────────
            async with httpx.AsyncClient(timeout=10) as client:
                rq = await client.get(
                    f"{sb_url}/rest/v1/mb_check_queue",
                    headers=headers,
                    params={
                        "user_id": f"eq.{user_id}",
                        "status":  "in.(pending,processing)",
                        "select":  "id"
                    }
                )
                logger.info(f"[MB] queue check status={rq.status_code} existing={rq.json()}")
                if rq.status_code == 200 and not rq.json():
                    ins = await client.post(
                        f"{sb_url}/rest/v1/mb_check_queue",
                        headers={**headers, "Content-Type": "application/json",
                                 "Prefer": "return=representation"},
                        json={
                            "user_id":    user_id,
                            "username":   user_tg.username or "",
                            "status":     "pending",
                            "created_at": datetime.utcnow().isoformat(),
                        }
                    )
                    logger.info(f"[MB] queue insert status={ins.status_code} body={ins.text[:200]}")
                else:
                    logger.info(f"[MB] task already in queue for user={user_id}, waiting...")

            # ── ШАГ 2: Поллим кэш до 30 сек ─────────────────────────────
            import time as _time
            deadline = _time.time() + 30
            row = None
            while _time.time() < deadline:
                await asyncio.sleep(3)  # было 2, уменьшает число запросов при ожидании
                async with httpx.AsyncClient(timeout=8) as client:
                    r = await client.get(
                        f"{sb_url}/rest/v1/memory_base_cache",
                        headers=headers,
                        params={"user_id": f"eq.{user_id}", "select": "*"}
                    )
                    if r.status_code == 200 and r.json():
                        row = r.json()[0]
                        logger.info(f"[MB] cache hit for user={user_id}: {row.get('status')}")
                        break
                    logger.debug(f"[MB] cache miss for user={user_id}, retrying...")

            if row is None:
                if user_rec:
                    user_rec['last_mb_check'] = int(_time.time())
                return False

            status  = row.get('status', 'clean')
            reasons = row.get('reasons', [])

            if user_rec:
                user_rec['last_mb_check'] = int(time.time())

            if status != 'in_base':
                return False

            block_reasons = settings.get('memoryBaseBlockReasons', [])
            should_block = (not block_reasons or any(r in block_reasons for r in reasons))

            if not should_block:
                return False

            if user_rec:
                user_rec['mb_restricted'] = True
                user_rec['mb_reasons']    = reasons
            else:
                user_rec = {
                    "id": user_id, "first_name": user_tg.first_name or "",
                    "username": user_tg.username or "", "is_banned": False,
                    "mb_restricted": True, "mb_reasons": reasons, "warns": 0,
                    "joined_at": int(time.time()), "last_seen": int(time.time()),
                    "last_mb_check": int(time.time()), "last_topic_id": None,
                }
                self.bi.users_list.append(user_rec)

            await self.bi._push_state()

            reasons_human = {
                "scammer": "Мошенник ⛔️", "bad_admin": "Плохой админ ❌",
                "bad_owner": "Плохой владелец ❌", "bad_behavior": "Нарушитель 🐔",
                "spammer": "Спамер 🚫", "raider": "Рейдер 💥",
            }
            r_text = ", ".join(reasons_human.get(r, r) for r in reasons if not r.startswith("other:"))
            other  = [r.replace("other:", "") for r in reasons if r.startswith("other:")]
            if other:
                r_text += (", " if r_text else "") + ", ".join(other)

            try:
                await self.bi.bot.send_message(
                    user_id,
                    f"🚫 <b>Ваш доступ к боту ограничен.</b>\n\n"
                    f"Вы найдены в антиспам-базе "
                    f"<a href=\"https://t.me/MemoryBaseBot\">MemoryBase</a>.\n"
                    f"<b>Причина:</b> {r_text or '—'}\n\n"
                    f"Для восстановления доступа обратитесь к владельцу бота."
                )
            except Exception:
                pass

            already_notified = user_rec.get('mb_notified', False) if user_rec else False
            if self.bi.admin_chat_id and not already_notified:
                try:
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                    name_str  = user_tg.full_name or f"User {user_id}"
                    uname_str = f" (@{user_tg.username})" if user_tg.username else ""
                    is_start  = (isinstance(event, Message) and event.text and event.text.strip().startswith("/start"))
                    action_str = "написал /start" if is_start else "написал сообщение"
                    unban_kb  = InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="✅ Разрешить доступ", callback_data=f"mb_unban_{user_id}")
                    ]])
                    await self.bi.bot.send_message(
                        self.bi.admin_chat_id,
                        f"🔴 <b>MemoryBase: пользователь в базе</b>\n\n"
                        f"👤 {name_str}{uname_str}\n🆔 <code>{user_id}</code>\n"
                        f"📌 <b>Причина(ы):</b> {r_text or '—'}\n\n"
                        f"Пользователь {action_str} и был заблокирован.\n"
                        f"Если хотите разрешить ему писать — нажмите кнопку ниже 👇",
                        reply_markup=unban_kb
                    )
                    if user_rec:
                        user_rec['mb_notified'] = True
                        await self.bi.sync_queue.put(("sync_state", None))
                except Exception as e:
                    logger.warning(f"[MB] admin notify error: {e}")
            return True  # Заблокирован

        except Exception as e:
            logger.error(f"[MB] free _check_and_restrict error: {e}")
            return False


# ════════════════════════════════════════════════════════════════════════════════
# ХЕЛПЕРЫ
# ════════════════════════════════════════════════════════════════════════════════

def get_anon_id(user_id: int) -> str:
    return hashlib.md5(str(user_id).encode()).hexdigest()[:6].upper()


def format_admin_header(m: Message, settings: dict, is_first: bool = False, btn_text: str = "") -> str:
    is_anon = settings.get("anonymousTopics", False)
    uid     = m.from_user.id
    anon    = f"#{get_anon_id(uid)}"

    if is_anon:
        user_info = f"👤 <b>Аноним {anon}</b>"
    else:
        parts = []
        if settings.get("showHeaderName", True):
            name = m.from_user.full_name or "Пользователь"
            parts.append(f"<b>{name}</b>")
        if settings.get("showHeaderUsername", True) and m.from_user.username:
            parts.append(f"(@{m.from_user.username})")
        if settings.get("showHeaderId", True):
            parts.append(f"ID: <code>{uid}</code>")
        user_info = " | ".join(parts) if parts else f"Юзер {anon}"

    if btn_text:
        hdr = settings.get("ticketMessageHeader", "🆘 <b>ЗАЯВКА</b>")
        hdr = hdr.replace("{btn}", btn_text)
    elif is_first:
        hdr = settings.get("firstMessageHeader", "🆕 <b>ПЕРВОЕ ОБРАЩЕНИЕ:</b>")
    else:
        hdr = settings.get("commonMessageHeader", "📩 <b>СООБЩЕНИЕ:</b>")

    return f"{hdr}\n{user_info}\n\n"


# ════════════════════════════════════════════════════════════════════════════════
# ОСНОВНОЙ КЛАСС
# ════════════════════════════════════════════════════════════════════════════════

class FreeBotInstance:
    def __init__(self, config_data: dict):
        self.bot_id = config_data.get("id")
        self.token  = config_data.get("token")

        self.sb_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.sb_key = os.getenv("SUPABASE_KEY", "")
        self.headers = {
            "apikey":        self.sb_key,
            "Authorization": f"Bearer {self.sb_key}",
            "Content-Type":  "application/json",
        }

        self.bot    = Bot(token=self.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp     = Dispatcher()

        self.admin_router = Router()
        self.user_router  = Router()

        self.msg_map:            Dict[int, int]  = {}
        self.user_to_admin_map:  Dict[tuple, int] = {}  # (user_id, user_msg_id) → admin_msg_id
        self.flood_cache:        Dict[int, float] = {}
        self.broadcast_cache:    Dict[int, str]   = {}
        self.media_group_buffer: Dict[str, dict]  = {}
        self.is_running   = True
        self.config       = config_data
        self._broadcast_day: Dict = {"date": "", "count": 0}
        self._last_push: float = 0.0

        self.users_list = []
        self.stats_data = {}

        self.apply_config(config_data)

    # ─────────────────────────────────────────────────────────────────────────
    # ПАРСИНГ КОНФИГА
    # ─────────────────────────────────────────────────────────────────────────

    def apply_config(self, data: dict):
        raw_cfg = data.get("config") or {}
        if isinstance(raw_cfg, str):
            try:
                raw_cfg = json.loads(raw_cfg)
            except Exception:
                raw_cfg = {}

        admin_raw = (
            raw_cfg.get("adminChatId") or
            raw_cfg.get("admin_chat_id") or
            data.get("adminChatId") or
            data.get("admin_chat_id")
        )
        try:
            self.admin_chat_id = int(str(admin_raw).strip()) if admin_raw else None
        except (ValueError, TypeError):
            self.admin_chat_id = None

        # Личные Telegram ID владельцев/администраторов бота
        raw_admin_ids = raw_cfg.get("adminIds") or data.get("adminIds") or []
        self.admin_ids: set = set(int(x) for x in raw_admin_ids if x)

        self.settings       = raw_cfg.get("settings") or {}
        self.use_topics     = self.settings.get("useTopics", False)
        self.topic_per_req  = self.settings.get("topicPerRequest", False)
        self.forward_all    = self.settings.get("forwardAll", False)
        self.forward_native = self.settings.get("forwardMessages", False)
        self.rate_limit     = float(self.settings.get("rateLimit", 1.0))
        self.auto_ban_limit = int(self.settings.get("autoBanThreshold", 3))

        # ── MemoryBase антиспам ──
        self.mb_enabled       = self.settings.get("memoryBaseEnabled", False)
        self.mb_block_reasons = self.settings.get("memoryBaseBlockReasons", [])

        # ── DVR мониторинг ──
        self.dvr_enabled = self.settings.get("dvrEnabled", False)

        self.buttons  = raw_cfg.get("buttons")  or []
        self.triggers = raw_cfg.get("triggers") or []

        self.welcome_text   = raw_cfg.get("welcomeMessage", "Здравствуйте!")
        self.welcome_photo  = raw_cfg.get("welcomePhoto", "")

        # FIX v6: поддерживаем новый формат inlineButtons [{id, text, type, value}]
        # и старый welcomeInline [{text, url}] для обратной совместимости
        self.inline_buttons = raw_cfg.get("inlineButtons") or raw_cfg.get("welcomeInline") or []

        if not self.users_list:
            self.users_list = raw_cfg.get("connectedUsers") or []

        self.ad_enabled      = data.get("ad_enabled", True)
        self.server_base_url = os.getenv("SERVER_BASE_URL", "http://localhost:8000")

        # adminIds: список ID кто может делать рассылки (пусто = все)
        raw_admin_ids = raw_cfg.get("adminIds") or raw_cfg.get("admin_ids") or []
        try:
            self.admin_ids: List[int] = [int(x) for x in raw_admin_ids if str(x).strip().isdigit()]
        except Exception:
            self.admin_ids = []

        if not self.stats_data:
            st = raw_cfg.get("stats") or {}
            self.stats_data = {
                "totalMessages":   st.get("totalMessages", 0),
                "incomingToday":   st.get("incomingToday", 0),
                "outgoingToday":   st.get("outgoingToday", 0),
                "bannedCount":     st.get("bannedCount", 0),
                "activeUsers24h":  st.get("activeUsers24h", 0),
                "broadcastsToday": st.get("broadcastsToday", 0),
                "broadcastsTotal": st.get("broadcastsTotal", 0),
                "history":         st.get("history", []),
            }
            _today = datetime.now().strftime("%d.%m")
            self._broadcast_day = {"date": _today, "count": int(self.stats_data.get("broadcastsToday", 0))}

    def reload_config_from_remote(self, remote_cfg: dict):
        admin_raw = (
            remote_cfg.get("adminChatId") or
            remote_cfg.get("admin_chat_id")
        )
        if admin_raw:
            try:
                self.admin_chat_id = int(str(admin_raw).strip())
            except (ValueError, TypeError):
                pass

        stg = remote_cfg.get("settings") or self.settings
        self.settings       = stg
        self.use_topics     = stg.get("useTopics", False)
        self.topic_per_req  = stg.get("topicPerRequest", False)
        self.forward_all    = stg.get("forwardAll", False)
        self.forward_native = stg.get("forwardMessages", False)
        self.rate_limit     = float(stg.get("rateLimit", 1.0))
        self.auto_ban_limit = int(stg.get("autoBanThreshold", 3))

        if "buttons" in remote_cfg:
            self.buttons = remote_cfg["buttons"] or []
        if "triggers" in remote_cfg:
            self.triggers = remote_cfg["triggers"] or []

        if "welcomeMessage" in remote_cfg:
            self.welcome_text = remote_cfg["welcomeMessage"]
        if "welcomePhoto" in remote_cfg:
            self.welcome_photo = remote_cfg["welcomePhoto"]

        # FIX v6: горячая перезагрузка inlineButtons
        if "inlineButtons" in remote_cfg:
            self.inline_buttons = remote_cfg["inlineButtons"] or []
        elif "welcomeInline" in remote_cfg:
            self.inline_buttons = remote_cfg["welcomeInline"] or []

        # adminIds
        if "adminIds" in remote_cfg or "admin_ids" in remote_cfg:
            raw = remote_cfg.get("adminIds") or remote_cfg.get("admin_ids") or []
            try:
                self.admin_ids = [int(x) for x in raw if str(x).strip().isdigit()]
            except Exception:
                pass

        logger.debug(
            f"[{self.bot_id}] reload: buttons={len(self.buttons)}, "
            f"triggers={len(self.triggers)}, forwardAll={self.forward_all}, "
            f"useTopics={self.use_topics}, admin={self.admin_chat_id}, "
            f"inlineButtons={len(self.inline_buttons)}"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # КЛАВИАТУРЫ
    # ─────────────────────────────────────────────────────────────────────────

    def get_main_keyboard(self):
        active = [b for b in self.buttons if b.get("text")]
        if not active:
            return ReplyKeyboardRemove()
        rows = []
        for i in range(0, len(active), 2):
            rows.append([KeyboardButton(text=b["text"]) for b in active[i:i+2]])
        return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

    def build_inline_from_list(self, buttons: list) -> Optional[InlineKeyboardMarkup]:
        """Старый метод: [{text, url}] → InlineKeyboardMarkup (только URL-кнопки)."""
        if not buttons:
            return None
        rows = []
        for i in range(0, len(buttons), 2):
            rows.append([
                InlineKeyboardButton(text=b["text"], url=b.get("url", "https://t.me"))
                for b in buttons[i:i+2] if b.get("text")
            ])
        return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None

    def build_welcome_inline(self) -> Optional[InlineKeyboardMarkup]:
        """
        FIX v6: Строит инлайн-клавиатуру под стартовым сообщением из нового формата.
        Поддерживает тип "url" (открыть ссылку) и "message" (callback_data с текстом).
        Старый формат [{text, url}] также поддерживается для обратной совместимости.
        """
        buttons = self.inline_buttons
        if not buttons:
            return None

        rows = []
        for i in range(0, len(buttons), 2):
            row = []
            for btn in buttons[i:i+2]:
                text = btn.get("text", "").strip()
                if not text:
                    continue
                btn_type = btn.get("type", "url")
                value    = btn.get("value", "") or btn.get("url", "")

                if btn_type == "url" and value:
                    # Добавляем https:// если нет схемы
                    if value and not value.startswith(("http://", "https://", "tg://")):
                        value = "https://" + value
                    row.append(InlineKeyboardButton(text=text, url=value))
                elif btn_type == "message" and value:
                    # callback_data — бот отправит это сообщение когда юзер нажмёт
                    # используем префикс "inl_msg:" чтобы хендлер понял что делать
                    cb_data = f"inl_msg:{value[:60]}"  # Telegram limit 64 bytes
                    row.append(InlineKeyboardButton(text=text, callback_data=cb_data))
                # else: пропускаем кнопку без значения
            if row:
                rows.append(row)

        return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None

    # ─────────────────────────────────────────────────────────────────────────
    # ТОПИКИ
    # ─────────────────────────────────────────────────────────────────────────

    async def resolve_thread(self, user: dict, force_new: bool = False) -> Optional[int]:
        if not self.use_topics or not self.admin_chat_id:
            return None

        existing_tid = user.get("last_topic_id")
        if existing_tid and not force_new:
            return existing_tid

        try:
            name  = user.get("first_name") or "Пользователь"
            uname = user.get("username")
            topic_name = f"{name}" + (f" (@{uname})" if uname else f" [{user.get('id')}]")
            if len(topic_name) > 128:
                topic_name = topic_name[:128]
            topic = await self.bot.create_forum_topic(self.admin_chat_id, topic_name)
            user["last_topic_id"] = topic.message_thread_id
            logger.info(f"[{self.bot_id}] Создан топик {topic.message_thread_id} для {user.get('id')}")
            return topic.message_thread_id
        except Exception as e:
            logger.warning(f"[{self.bot_id}] resolve_thread error: {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # ФОРВАРД АДМИНУ
    # ─────────────────────────────────────────────────────────────────────────

    async def forward_to_admin(self, m: Message, user: dict, is_first: bool = False, btn_text: str = ""):
        if not self.admin_chat_id:
            return

        # topicPerRequest: новый топик только при явном открытии тикета (btn_text заполнен)
        # При forward_all — один топик на юзера, переиспользуем существующий
        # is_first — создаём топик только если у юзера его ещё нет вообще
        existing_tid = user.get("last_topic_id")
        if self.topic_per_req and btn_text:
            force_new = True   # явное открытие тикета → новый топик
        elif not existing_tid:
            force_new = False  # нет топика → resolve_thread создаст первый
        else:
            force_new = False  # топик уже есть → используем
        thread_id = await self.resolve_thread(user, force_new=force_new)

        if self.forward_native and not btn_text and not is_first:
            try:
                sent = await self.bot.forward_message(
                    chat_id=self.admin_chat_id,
                    from_chat_id=m.chat.id,
                    message_id=m.message_id,
                    message_thread_id=thread_id,
                )
                if sent:
                    self.msg_map[sent.message_id] = user["id"]
                    self.user_to_admin_map[(user["id"], m.message_id)] = sent.message_id
            except TelegramBadRequest as e:
                err_str = str(e).lower()
                if "message thread not found" in err_str or "thread" in err_str:
                    user["last_topic_id"] = None
                    thread_id = await self.resolve_thread(user, force_new=True)
                    try:
                        sent = await self.bot.forward_message(
                            self.admin_chat_id, m.chat.id, m.message_id,
                            message_thread_id=thread_id
                        )
                        if sent:
                            self.msg_map[sent.message_id] = user["id"]
                            self.user_to_admin_map[(user["id"], m.message_id)] = sent.message_id
                    except Exception:
                        pass
                else:
                    logger.error(f"forward_to_admin(native) TelegramBadRequest: {e}")
            except Exception as e:
                logger.error(f"forward_to_admin(native) error: {e}")
            return

        header = format_admin_header(m, self.settings, is_first, btn_text)
        cap    = (header + (m.caption or ""))[:1024]

        async def _do_send(tid: Optional[int]) -> Optional[Any]:
            if m.photo:
                asyncio.create_task(self._save_media_to_db(user["id"], "photo", m.photo[-1].file_id))
                return await self.bot.send_photo(
                    self.admin_chat_id, photo=m.photo[-1].file_id,
                    caption=cap, parse_mode="HTML",
                    message_thread_id=tid,
                )
            elif m.video:
                asyncio.create_task(self._save_media_to_db(user["id"], "video", m.video.file_id))
                return await self.bot.send_video(
                    self.admin_chat_id, video=m.video.file_id,
                    caption=cap, parse_mode="HTML",
                    message_thread_id=tid,
                )
            elif m.document:
                asyncio.create_task(self._save_media_to_db(user["id"], "document", m.document.file_id))
                return await self.bot.send_document(
                    self.admin_chat_id, document=m.document.file_id,
                    caption=cap, parse_mode="HTML",
                    message_thread_id=tid,
                )
            elif m.audio or m.voice or m.sticker or m.video_note:
                await self.bot.send_message(
                    self.admin_chat_id, header.strip(),
                    message_thread_id=tid, parse_mode="HTML"
                )
                if m.voice:
                    asyncio.create_task(self._save_media_to_db(user["id"], "voice", m.voice.file_id))
                return await self.bot.copy_message(
                    self.admin_chat_id, m.chat.id, m.message_id,
                    message_thread_id=tid
                )
            else:
                txt = (header + (m.text or ""))[:4096]
                return await self.bot.send_message(
                    self.admin_chat_id, txt,
                    message_thread_id=tid, parse_mode="HTML"
                )

        async def _send():
            nonlocal thread_id
            try:
                s = await _do_send(thread_id)
                if s:
                    self.msg_map[s.message_id] = user["id"]
                    self.user_to_admin_map[(user["id"], m.message_id)] = s.message_id
            except TelegramBadRequest as e:
                err_str = str(e).lower()
                if "message thread not found" in err_str or "thread" in err_str:
                    logger.warning(
                        f"[{self.bot_id}] Thread {thread_id} not found, "
                        f"creating new for uid={user.get('id')}"
                    )
                    user["last_topic_id"] = None
                    thread_id = await self.resolve_thread(user, force_new=True)
                    try:
                        s2 = await _do_send(thread_id)
                        if s2:
                            self.msg_map[s2.message_id] = user["id"]
                            self.user_to_admin_map[(user["id"], m.message_id)] = s2.message_id
                    except Exception as e2:
                        logger.error(f"forward_to_admin retry error: {e2}")
                else:
                    logger.error(f"forward_to_admin TelegramBadRequest: {e}")
            except Exception as e:
                logger.error(f"forward_to_admin error: {e}")

        await _send()

    # ─────────────────────────────────────────────────────────────────────────
    # СОСТОЯНИЕ ПОЛЬЗОВАТЕЛЯ
    # ─────────────────────────────────────────────────────────────────────────

    async def get_user_state(self, m: Message):
        uid  = m.from_user.id
        user = next((u for u in self.users_list if u["id"] == uid), None)
        is_new = False
        if not user:
            user = {
                "id":         uid,
                "first_name": m.from_user.first_name or "",
                "username":   m.from_user.username or "",
                "joined_at":  int(time.time()),
                "last_seen":  int(time.time()),
                "is_banned":  False,
                "warns":      0,
                "is_active":  True,
            }
            self.users_list.append(user)
            is_new = True
        else:
            user["last_seen"]  = int(time.time())
            user["first_name"] = m.from_user.first_name or user.get("first_name", "")
            user["username"]   = m.from_user.username or user.get("username", "")
        return user, is_new

    # ─────────────────────────────────────────────────────────────────────────
    # РЕКЛАМА
    # ─────────────────────────────────────────────────────────────────────────

    async def get_active_ad(self) -> Optional[dict]:
        if not self.ad_enabled:
            return None
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(
                    f"{self.server_base_url}/api/ads/active",
                    params={"bot_id": self.bot_id}
                )
                if r.status_code == 200:
                    return r.json().get("ad")
        except Exception as e:
            logger.warning(f"[FREE] Реклама недоступна: {e}")
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # РАССЫЛКА
    # ─────────────────────────────────────────────────────────────────────────

    def _broadcast_today_count(self) -> int:
        today = datetime.now().strftime("%d.%m")
        if self._broadcast_day.get("date") != today:
            self._broadcast_day = {"date": today, "count": 0}
        return self._broadcast_day["count"]

    def _broadcast_increment(self):
        today = datetime.now().strftime("%d.%m")
        if self._broadcast_day.get("date") != today:
            self._broadcast_day = {"date": today, "count": 0}
        self._broadcast_day["count"] += 1
        self.stats_data["broadcastsToday"] = self._broadcast_day["count"]
        self.stats_data["broadcastsTotal"] = self.stats_data.get("broadcastsTotal", 0) + 1
        history = self.stats_data.get("history", [])
        if history and history[-1].get("date") == today:
            history[-1]["broadcasts"] = history[-1].get("broadcasts", 0) + 1

    # ─────────────────────────────────────────────────────────────────────────
    # ПРОВЕРКА ПРАВ АДМИНИСТРАТОРА
    # ─────────────────────────────────────────────────────────────────────────

    def is_admin(self, user_id: int) -> bool:
        """Может ли пользователь делать рассылки? По умолчанию — все, если adminIds не задан."""
        if not self.admin_ids:
            return True
        return user_id in self.admin_ids

    # ─────────────────────────────────────────────────────────────────────────
    # АНТИСПАМ
    # ─────────────────────────────────────────────────────────────────────────

    async def check_antispam(self, user_id: int) -> bool:
        if self.rate_limit <= 0:
            return False
        now = time.time()
        if now - self.flood_cache.get(user_id, 0) < self.rate_limit:
            return True
        self.flood_cache[user_id] = now
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # СТАТИСТИКА
    # ─────────────────────────────────────────────────────────────────────────

    async def log_and_update(self, uid: int, name: str, text: str, is_admin: bool = False):
        self.stats_data["totalMessages"] = self.stats_data.get("totalMessages", 0) + 1
        key = "outgoingToday" if is_admin else "incomingToday"
        self.stats_data[key] = self.stats_data.get(key, 0) + 1

        if not is_admin:
            for u in self.users_list:
                if u["id"] == uid:
                    u["last_seen"]  = int(time.time())
                    u["first_name"] = name
                    break

        asyncio.create_task(self._log_message(uid, name, text, is_admin))
        asyncio.create_task(self._push_state())

    async def _log_message(self, uid: int, name: str, text: str, is_admin: bool):
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f"{self.sb_url}/rest/v1/bot_messages",
                    json={
                        "bot_id":        self.bot_id,
                        "user_id":       uid,
                        "first_name":    name,
                        "message_text":  text[:950] if text else "[Медиа]",
                        "is_from_admin": is_admin,
                    },
                    headers={**self.headers, "Content-Type": "application/json",
                            "Prefer": "return=minimal"}
                )
        except Exception:
            pass

    async def _save_media_to_db(self, user_id: int, media_type: str, file_id: str):
        """Сохраняет file_id медиа от пользователя в таблицу bot_media."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f"{self.sb_url}/rest/v1/bot_media",
                    json={
                        "bot_id":     self.bot_id,
                        "user_id":    user_id,
                        "media_type": media_type,
                        "file_id":    file_id,
                    },
                    headers={**self.headers, "Content-Type": "application/json",
                            "Prefer": "return=minimal"}
                )
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────────
    # СОХРАНЕНИЕ В БД
    # ─────────────────────────────────────────────────────────────────────────

    async def _push_state(self):
        now = time.time()
        if now - self._last_push < 5.0:
            return
        self._last_push = now
        await self._do_push()

    async def _push_state_immediate(self):
        self._last_push = time.time()
        await self._do_push()

    async def _do_push(self):
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                res = await client.get(
                    f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}&select=config",
                    headers=self.headers
                )
                if res.status_code != 200 or not res.json():
                    logger.warning(f"_do_push: не смогли прочитать конфиг бота {self.bot_id}")
                    return
                remote_cfg = res.json()[0].get("config") or {}
                new_cfg = {
                    **remote_cfg,
                    "connectedUsers": self.users_list,
                    "stats":          self.stats_data,
                }
                patch_res = await client.patch(
                    f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                    json={"config": new_cfg},
                    headers={**self.headers, "Content-Type": "application/json",
                            "Prefer": "return=minimal"}
                )
                if patch_res.status_code not in (200, 201, 204):
                    logger.error(f"_do_push patch failed: {patch_res.status_code} {patch_res.text[:200]}")
        except Exception as e:
            logger.debug(f"_do_push error (non-fatal): {e}")

    async def _save_to_db(self):
        await self._push_state_immediate()

    # ─────────────────────────────────────────────────────────────────────────
    # ПЕРИОДИЧЕСКАЯ СИНХРОНИЗАЦИЯ КОНФИГА
    # ─────────────────────────────────────────────────────────────────────────

    async def dvr_notify_worker(self):
        """Поллим dvr_events и отправляем уведомления о DVR-рейде."""
        if not self.admin_chat_id:
            return
        while True:
            try:
                async with httpx.AsyncClient(timeout=8) as c:
                    r = await c.get(
                        f"{self.sb_url}/rest/v1/dvr_events",
                        headers={"apikey": self.sb_key, "Authorization": f"Bearer {self.sb_key}"},
                        params={"bot_id": f"eq.{self.bot_id}", "status": "eq.pending", "select": "*"}
                    )
                    if r.status_code == 200 and r.json():
                        for ev in r.json():
                            try:
                                bot_username = ev.get("bot_username", "")
                                await self.bot.send_message(
                                    self.admin_chat_id,
                                    f"🚨 <b>Система безопасности Dialoge Engine</b>\n\n"
                                    f"Обнаружена рейдерская атака на вашего бота"
                                    f"{f' <b>@{bot_username}</b>' if bot_username else ''}.\n\n"
                                    f"✅ Бот был автоматически <b>остановлен</b> для защиты.\n\n"
                                    f"Восстановите работу на: "
                                    f"<a href=\"https://dialogengine.webtm.ru\">dialogengine.webtm.ru</a>"
                                )
                                await c.patch(
                                    f"{self.sb_url}/rest/v1/dvr_events",
                                    headers={"apikey": self.sb_key, "Authorization": f"Bearer {self.sb_key}",
                                             "Content-Type": "application/json", "Prefer": "return=minimal"},
                                    params={"id": f"eq.{ev['id']}"},
                                    json={"status": "done"}
                                )
                                logger.info(f"[DVR] ✅ Notify sent to {self.admin_chat_id}")
                            except Exception as e:
                                logger.warning(f"[DVR] notify error: {e}")
            except Exception as e:
                logger.warning(f"[DVR] worker error: {e}")
            await asyncio.sleep(30)  # DVR-события редкие, 5с — расточительство ресурсов

    async def config_sync_loop(self):
        await asyncio.sleep(30)
        while self.is_running:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    res = await client.get(
                        f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                        headers=self.headers
                    )
                    if res.status_code == 200 and res.json():
                        row = res.json()[0]
                        remote_cfg = row.get("config", {}) or {}
                        self.reload_config_from_remote(remote_cfg)
                        logger.debug(
                            f"[{self.bot_id}] Config reloaded: "
                            f"buttons={len(self.buttons)}, triggers={len(self.triggers)}, "
                            f"forwardAll={self.forward_all}, "
                            f"inlineButtons={len(self.inline_buttons)}"
                        )
            except Exception as e:
                logger.error(f"config_sync_loop error: {e}")
            await asyncio.sleep(30)

    # ─────────────────────────────────────────────────────────────────────────
    # РОТАТОР СТАТИСТИКИ
    # ─────────────────────────────────────────────────────────────────────────

    async def daily_stats_rotator(self):
        while self.is_running:
            try:
                now          = datetime.now()
                current_date = now.strftime("%d.%m")
                day_ago      = int((now - timedelta(days=1)).timestamp())
                active_count = sum(1 for u in self.users_list if u.get("last_seen", 0) > day_ago)
                self.stats_data["activeUsers24h"] = active_count

                history = self.stats_data.setdefault("history", [])
                if not history:
                    history.append({
                        "date": current_date, "incoming": 0, "outgoing": 0,
                        "totalUsers": len(self.users_list), "activeUsers": active_count,
                        "broadcasts": 0
                    })

                if history[-1]["date"] != current_date:
                    history[-1].update({
                        "incoming":    self.stats_data.get("incomingToday", 0),
                        "outgoing":    self.stats_data.get("outgoingToday", 0),
                        "totalUsers":  len(self.users_list),
                        "activeUsers": active_count,
                    })
                    self.stats_data["incomingToday"]  = 0
                    self.stats_data["outgoingToday"]  = 0
                    self.stats_data["broadcastsToday"] = 0
                    self._broadcast_day = {"date": current_date, "count": 0}
                    history.append({
                        "date": current_date, "incoming": 0, "outgoing": 0,
                        "totalUsers": len(self.users_list), "activeUsers": active_count,
                        "broadcasts": 0
                    })
                    self.stats_data["history"] = history[-14:]

                history[-1].update({
                    "incoming":    self.stats_data.get("incomingToday", 0),
                    "outgoing":    self.stats_data.get("outgoingToday", 0),
                    "totalUsers":  len(self.users_list),
                    "activeUsers": active_count,
                })

                self._last_push = 0
                await self._push_state()

            except Exception as e:
                logger.error(f"Rotator error: {e}")
            await asyncio.sleep(60)

    # ─────────────────────────────────────────────────────────────────────────
    # КОМАНДЫ МОДЕРАЦИИ
    # ─────────────────────────────────────────────────────────────────────────

    async def admin_control_logic(self, m: Message) -> bool:
        if not m.text or not (m.text.startswith("/") or m.text.startswith("!")):
            return False

        cmd_parts = m.text.split()
        command   = cmd_parts[0][1:].lower()

        if command == "stats":
            total  = len(self.users_list)
            banned = sum(1 for u in self.users_list if u.get("is_banned"))
            active = sum(1 for u in self.users_list if u.get("is_active", True) and not u.get("is_banned"))
            bc_day = self._broadcast_today_count()
            await m.reply(
                f"📊 <b>Статистика бота</b>\n\n"
                f"👥 Всего пользователей: <b>{total}</b>\n"
                f"✅ Активных: <b>{active}</b>\n"
                f"🚫 Заблокировано: <b>{banned}</b>\n"
                f"📢 Рассылок сегодня: <b>{bc_day}</b>"
            )
            return True

        elif command == "broadcast":
            if not self.is_admin(m.from_user.id):
                await m.reply("🚫 У вас нет прав для рассылки.")
                return True
            active_users = [u for u in self.users_list if not u.get("is_banned") and u.get("is_active", True)]
            if not active_users:
                await m.reply("Нет активных пользователей для рассылки.")
                return True
            if m.reply_to_message:
                source_msg_id = m.reply_to_message.message_id
                await self._do_broadcast(m, active_users, source_msg_id)
            else:
                self.broadcast_cache[m.chat.id] = {
                    "user_id": m.from_user.id,
                    "active_users": active_users
                }
                await m.reply(
                    f"📢 <b>Режим рассылки</b>\n"
                    f"Пришлите следующим сообщением то, что хотите разослать.\n\n"
                    f"<i>Поддерживаются: текст, фото, видео, документы, стикеры и любые медиа</i>"
                )
            return True

        target_user = None
        if m.message_thread_id:
            target_user = next(
                (u for u in self.users_list if u.get("last_topic_id") == m.message_thread_id), None
            )
        if not target_user and m.reply_to_message:
            uid_from_map = self.msg_map.get(m.reply_to_message.message_id)
            if uid_from_map:
                target_user = next(
                    (u for u in self.users_list if int(u["id"]) == int(uid_from_map)), None
                )
        if not target_user and len(cmd_parts) > 1:
            try:
                direct_id = int(cmd_parts[1])
                target_user = next(
                    (u for u in self.users_list if int(u["id"]) == direct_id), None
                )
                if not target_user and command in ("ban", "unban"):
                    target_user = {
                        "id": direct_id, "first_name": f"User#{direct_id}",
                        "username": None, "is_banned": False,
                        "warns": 0, "joined_at": int(time.time()), "last_seen": int(time.time()),
                    }
                    self.users_list.append(target_user)
                elif not target_user:
                    await m.reply(f"Пользователь <code>{direct_id}</code> не найден.")
                    return True
            except ValueError:
                pass

        if not target_user:
            return False

        uid       = target_user["id"]
        ban_limit = self.settings.get("autoBanThreshold", 3)

        if command == "whois":
            uname     = target_user.get("username")
            name_line = target_user.get("first_name", "—")
            if uname:
                name_line += f" (@{uname})"
            joined    = datetime.fromtimestamp(target_user.get("joined_at", 0)).strftime("%d.%m.%Y %H:%M") if target_user.get("joined_at") else "—"
            last_seen = datetime.fromtimestamp(target_user.get("last_seen", 0)).strftime("%d.%m.%Y %H:%M") if target_user.get("last_seen") else "—"
            await m.reply(
                f"🔍 <b>Пользователь <code>{uid}</code>:</b>\n\n"
                f"Имя: {name_line}\n"
                f"Забанен: {'Да' if target_user.get('is_banned') else 'Нет'}\n"
                f"Варнов: {target_user.get('warns', 0)}\n"
                f"Зашёл: {joined}\n"
                f"Активность: {last_seen}"
            )
            return True

        elif command == "ban":
            # Защита: нельзя забанить администратора
            if uid in self.admin_ids:
                await m.reply("⛔ <b>Нельзя забанить администратора бота.</b>")
                return True
            target_user["is_banned"] = True
            self.stats_data["bannedCount"] = self.stats_data.get("bannedCount", 0) + 1
            await self._save_to_db()
            try:
                await self.bot.send_message(uid, "🚫 <b>Доступ к боту ограничен администратором.</b>")
            except Exception:
                pass
            await m.reply(f"✅ Пользователь <code>{uid}</code> заблокирован.")
            return True

        elif command == "unban":
            target_user["is_banned"] = False
            target_user["warns"]     = 0
            self.stats_data["bannedCount"] = max(0, self.stats_data.get("bannedCount", 1) - 1)
            await self._save_to_db()
            try:
                await self.bot.send_message(uid, "✅ <b>Ваш доступ восстановлен.</b>")
            except Exception:
                pass
            await m.reply(f"✅ Пользователь <code>{uid}</code> разблокирован.")
            return True

        elif command == "warn":
            # Защита: нельзя выдать варн администратору
            if uid in self.admin_ids:
                await m.reply("⛔ <b>Нельзя выдать варн администратору бота.</b>")
                return True
            target_user["warns"] = target_user.get("warns", 0) + 1
            if ban_limit > 0 and target_user["warns"] >= ban_limit:
                target_user["is_banned"] = True
                self.stats_data["bannedCount"] = self.stats_data.get("bannedCount", 0) + 1
                msg   = f"🚨 <b>АВТО-БАН!</b> <code>{uid}</code>. Варнов: {target_user['warns']}/{ban_limit}"
                notif = f"🚫 <b>Авто-бан:</b> лимит предупреждений ({target_user['warns']}/{ban_limit}) исчерпан."
            else:
                msg   = f"⚠️ Варн <code>{uid}</code>. Всего: {target_user['warns']}/{ban_limit or '∞'}"
                notif = f"⚠️ <b>Предупреждение!</b> ({target_user['warns']}/{ban_limit or '∞'})"
            await self._save_to_db()
            try:
                await self.bot.send_message(uid, notif)
            except Exception:
                pass
            await m.reply(msg)
            return True

        elif command == "unwarn":
            target_user["warns"] = max(0, target_user.get("warns", 0) - 1)
            await self._save_to_db()
            await m.reply(f"✅ Варн снят. У <code>{uid}</code>: {target_user['warns']}")
            return True

        return False

    # ─────────────────────────────────────────────────────────────────────────
    # РАССЫЛКА
    # ─────────────────────────────────────────────────────────────────────────

    async def _do_broadcast(self, m: Message, active_users: list, source_msg_id: int):
        sent_c, err_c = 0, 0
        status_msg = await m.reply(
            f"🚀 <b>Рассылаю {len(active_users)} получателям...</b>"
        )
        for user in active_users:
            try:
                await self.bot.copy_message(
                    chat_id=int(user["id"]),
                    from_chat_id=m.chat.id,
                    message_id=source_msg_id
                )
                sent_c += 1
                await asyncio.sleep(0.04)
            except TelegramForbiddenError:
                user["is_active"] = False
                err_c += 1
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
                try:
                    await self.bot.copy_message(int(user["id"]), m.chat.id, source_msg_id)
                    sent_c += 1
                except Exception:
                    err_c += 1
            except Exception as e:
                    logger.error(f"broadcast send error for {user['id']}: {e}")
                    err_c += 1

        self._broadcast_increment()
        new_today = self._broadcast_today_count()
        await self._save_to_db()
        try:
            await status_msg.edit_text(
                f"✅ <b>Рассылка завершена!</b>\n\n"
                f"👤 Доставлено: <b>{sent_c}</b>\n"
                f"🚫 Ошибки: <b>{err_c}</b>\n"
                f"📊 Рассылок сегодня: <b>{new_today}</b>"
            )
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────────
    # ЗАГРУЗКА КОНФИГА ПРИ СТАРТЕ
    # ─────────────────────────────────────────────────────────────────────────

    async def sync_database_logic(self):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(
                    f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                    headers=self.headers
                )
                if res.status_code == 200 and res.json():
                    row = res.json()[0]
                    self.apply_config(row)

                    cleaned = 0
                    for u in self.users_list:
                        if u.get("_in_ticket"):
                            u.pop("_in_ticket", None)
                            u.pop("_ticket_close_label", None)
                            cleaned += 1
                    if cleaned:
                        logger.info(f"[{self.bot_id}] Сброшено {cleaned} тикетов при старте")

                    logger.info(
                        f"✅ [{self.bot_id}] Конфиг загружен: "
                        f"кнопок={len(self.buttons)}, триггеров={len(self.triggers)}, "
                        f"users={len(self.users_list)}, "
                        f"admin_chat={self.admin_chat_id}, "
                        f"forwardAll={self.forward_all}, "
                        f"useTopics={self.use_topics}, "
                        f"topicPerRequest={self.topic_per_req}, "
                        f"inlineButtons={len(self.inline_buttons)}"
                    )
        except Exception as e:
            logger.error(f"sync_database_logic error: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # РЕГИСТРАЦИЯ HANDLERS
    # ─────────────────────────────────────────────────────────────────────────

    async def core_handlers_setup(self):
        self.admin_router.message.middleware(BanMiddleware(self))
        self.user_router.message.middleware(BanMiddleware(self))
        self.user_router.callback_query.middleware(BanMiddleware(self))

        # MemoryBase — проверка антиспам-базы
        self.user_router.message.middleware(MemoryBaseMiddleware(self))
        self.user_router.callback_query.middleware(MemoryBaseMiddleware(self))

        # ── 1. Пользователь заблокировал бота ──────────────────────────────
        @self.user_router.my_chat_member(
            ChatMemberUpdatedFilter(member_status_changed=ChatMemberStatus.KICKED)
        )
        async def on_user_blocked(event: ChatMemberUpdated):
            uid  = event.from_user.id
            user = next((u for u in self.users_list if u["id"] == uid), None)
            if user:
                user["is_active"] = False
                await self._push_state_immediate()
                if self.admin_chat_id:
                    try:
                        await self.bot.send_message(
                            self.admin_chat_id,
                            f"🔴 <b>{event.from_user.full_name}</b> заблокировал бота.",
                            message_thread_id=user.get("last_topic_id"),
                        )
                    except Exception:
                        pass

        # ── 2. /start ────────────────────────────────────────────────────────
        @self.user_router.message(CommandStart())
        async def handle_start(m: Message):
            if self.admin_chat_id and m.chat.id == self.admin_chat_id:
                return

            user, is_new = await self.get_user_state(m)
            if user.get("is_banned"):
                if m.from_user.id in self.admin_ids:
                    unban_kb = InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔓 Разбанить себя", callback_data="selfunban")
                    ]])
                    await m.answer(
                        "⚠️ <b>Вы случайно забанили себя (администратора).</b>\n"
                        "Нажмите кнопку ниже, чтобы снять блокировку:",
                        reply_markup=unban_kb
                    )
                else:
                    await m.answer("🚫 <b>Вы заблокированы в этом боте.</b>")
                return

            reply_kb  = self.get_main_keyboard()
            inline_kb = self.build_welcome_inline()

            ad       = await self.get_active_ad() if self.ad_enabled else None
            welcome  = self.welcome_text or "Здравствуйте!"

            # Встраиваем рекламу прямо в приветственное сообщение
            if ad and ad.get("text"):
                combined = f"{welcome}\n\n─────────────────\n📢 <b>Реклама</b>\n{ad['text']}"
            else:
                combined = welcome

            # Если есть инлайн-кнопки — отправляем с ними, reply_kb отдельно без текста
            try:
                if self.welcome_photo:
                    await m.answer_photo(
                        photo=self.welcome_photo,
                        caption=combined[:1024],
                        reply_markup=inline_kb if inline_kb else reply_kb,
                    )
                    if inline_kb and self.buttons:
                        # Показываем reply-клавиатуру без лишнего текста
                        try:
                            await m.answer("\u200b", reply_markup=reply_kb)
                        except Exception:
                            pass
                    # Если реклама содержит медиа отдельное
                    if ad and ad.get("media_url") and ad["media_url"] != self.welcome_photo:
                        try:
                            await m.answer_photo(
                                photo=ad["media_url"],
                                caption=f"📢 {ad['text']}"[:1024]
                            )
                        except Exception:
                            pass
                else:
                    await m.answer(text=combined, reply_markup=inline_kb if inline_kb else reply_kb)
                    if inline_kb and self.buttons:
                        try:
                            await m.answer("\u200b", reply_markup=reply_kb)
                        except Exception:
                            pass
                    # Если реклама содержит медиа — показываем отдельно
                    if ad and ad.get("media_url"):
                        try:
                            await m.answer_photo(
                                photo=ad["media_url"],
                                caption=f"📢 {ad['text']}"[:1024]
                            )
                        except Exception:
                            pass
            except Exception as e:
                logger.warning(f"handle_start send error: {e}")
                try:
                    await m.answer(text=welcome, reply_markup=reply_kb)
                except Exception:
                    pass

            await self.log_and_update(user["id"], m.from_user.full_name, "/start")

        # ── 3а. Саморазбан администратора ───────────────────────────────────
        @self.user_router.callback_query(lambda c: c.data == "selfunban")
        async def handle_selfunban(cb: CallbackQuery):
            uid_cb = cb.from_user.id
            if uid_cb not in self.admin_ids:
                try:
                    await cb.answer("⛔ Эта кнопка только для администратора.", show_alert=True)
                except Exception:
                    pass
                return
            user_cb = next((u for u in self.users_list if u.get("id") == uid_cb), None)
            if user_cb:
                user_cb["is_banned"] = False
                user_cb["warns"] = 0
                await self._push_state_immediate()
            try:
                await cb.message.edit_text("✅ <b>Блокировка снята. Вы снова администратор бота.</b>")
                await cb.answer("✅ Разбан выполнен!", show_alert=False)
            except Exception:
                pass

        # ── MemoryBase разбан (только для администраторов) ──
        @self.user_router.callback_query(lambda c: c.data and c.data.startswith("mb_unban_"))
        async def handle_mb_unban(cb: CallbackQuery):
            uid_cb = cb.from_user.id
            if uid_cb not in (self.admin_ids or set()):
                await cb.answer("⛔ Только для администраторов.", show_alert=True)
                return
            try:
                target_uid = int(cb.data.split("mb_unban_")[1])
            except (IndexError, ValueError):
                await cb.answer("❌ Ошибка.", show_alert=True)
                return
            target = next((u for u in self.users_list if u.get('id') == target_uid), None)
            if target:
                target['mb_restricted'] = False
                target['mb_notified']    = False
                target['mb_reasons']    = []
                target['last_mb_check'] = 0
                await self._push_state()

            # ── Удаляем запись из memory_base_cache в Supabase ──
            # Иначе при следующем сообщении middleware снова заблокирует
            try:
                async with httpx.AsyncClient(timeout=8) as _uc:
                    _del = await _uc.patch(
                        f"{self.sb_url}/rest/v1/memory_base_cache",
                        headers={
                            "apikey": self.headers.get("apikey", ""),
                            "Authorization": self.headers.get("Authorization", ""),
                            "Content-Type": "application/json",
                            "Prefer": "return=minimal"
                        },
                        params={"user_id": f"eq.{target_uid}"},
                        json={"status": "clean", "reasons": []}
                    )
                    logger.info(f"[MB] cache unban → clean for uid={target_uid} status={_del.status_code}")
            except Exception as _de:
                logger.warning(f"[MB] cache delete error: {_de}")

            try:
                await self.bot.send_message(
                    target_uid,
                    "✅ <b>Доступ восстановлен!</b>\n\n"
                    "Администратор бота разрешил вам пользоваться ботом.\n"
                    "Нажмите /start чтобы начать."
                )
            except Exception:
                pass
            try:
                await cb.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            await cb.answer("✅ Пользователь разбанен.", show_alert=True)

        # ── 3. FIX v6: Callback-обработчик для инлайн-кнопок типа "message" ─
        @self.user_router.callback_query(lambda c: c.data and c.data.startswith("inl_msg:"))
        async def handle_inline_msg_button(cb: CallbackQuery):
            """Когда юзер нажал инлайн-кнопку типа "message" — отправляем текст боту."""
            try:
                await cb.answer()
            except Exception:
                pass
            text_to_send = cb.data[len("inl_msg:"):]
            if not text_to_send:
                return
            uid  = cb.from_user.id
            user = next((u for u in self.users_list if u["id"] == uid), None)
            if not user:
                user = {
                    "id":         uid,
                    "first_name": cb.from_user.first_name or "",
                    "username":   cb.from_user.username or "",
                    "joined_at":  int(time.time()),
                    "last_seen":  int(time.time()),
                    "is_banned":  False,
                    "warns":      0,
                    "is_active":  True,
                }
                self.users_list.append(user)
            # Ищем совпадение с кнопками/триггерами
            lower = text_to_send.lower()
            matched_btn = next(
                (b for b in self.buttons if b.get("text", "").strip().lower() == lower), None
            )
            if matched_btn:
                resp = matched_btn.get("response", "") or "✅"
                try:
                    await cb.message.answer(resp, reply_markup=self.get_main_keyboard())
                except Exception:
                    pass
                await self.log_and_update(uid, cb.from_user.full_name, f"ИНЛАЙН-КНОПКА: {text_to_send}")
            else:
                # Просто пересылаем текст как обычное сообщение в тикет/чат
                if self.admin_chat_id:
                    header = (
                        f"💬 <b>Инлайн-кнопка:</b> {text_to_send}\n"
                        f"<b>{cb.from_user.full_name}</b> | ID: <code>{uid}</code>\n\n"
                    )
                    try:
                        await self.bot.send_message(
                            self.admin_chat_id, header,
                            message_thread_id=user.get("last_topic_id"),
                        )
                    except Exception:
                        pass
                try:
                    await cb.message.answer("✅", reply_markup=self.get_main_keyboard())
                except Exception:
                    pass
                await self.log_and_update(uid, cb.from_user.full_name, f"ИНЛАЙН-КНОПКА: {text_to_send}")

        # ── 4. СООБЩЕНИЯ ОТ АДМИНИСТРАТОРА ──────────────────────────────────
        @self.admin_router.message(lambda m: bool(self.admin_chat_id and m.chat.id == self.admin_chat_id))
        async def admin_input(m: Message):
            if m.text and (m.text.startswith("/") or m.text.startswith("!")):
                handled = await self.admin_control_logic(m)
                if handled:
                    return
                # Если команда не распознана — всё равно не отправляем пользователю
                return

            bc = self.broadcast_cache.get(m.chat.id)
            if bc:
                del self.broadcast_cache[m.chat.id]
                active_users = bc.get("active_users") or [
                    u for u in self.users_list
                    if not u.get("is_banned") and u.get("is_active", True)
                ]
                if not active_users:
                    await m.reply("Нет активных пользователей.")
                    return
                await self._do_broadcast(m, active_users, m.message_id)
                return

            target_id = None
            if m.message_thread_id:
                u = next((u for u in self.users_list
                          if u.get("last_topic_id") == m.message_thread_id), None)
                if u:
                    target_id = u["id"]
            if not target_id and m.reply_to_message:
                target_id = self.msg_map.get(m.reply_to_message.message_id)

            if target_id:
                try:
                    sent = await self.bot.copy_message(target_id, m.chat.id, m.message_id)
                    if sent:
                        # Сохраняем маппинг: сообщение пользователю ← сообщение от админа
                        self.user_to_admin_map[(target_id, sent.message_id)] = m.message_id
                        self.msg_map[m.message_id] = target_id
                    await self.log_and_update(target_id, "Admin", m.text or "[Медиа]", is_admin=True)
                except TelegramForbiddenError:
                    await m.reply("❌ Пользователь заблокировал бота.")
                except Exception as e:
                    await m.reply(f"❌ Ошибка: {e}")

        # ── 4а. Редактирование сообщения администратором → обновить у пользователя
        @self.admin_router.edited_message(lambda m: bool(self.admin_chat_id and m.chat.id == self.admin_chat_id))
        async def admin_edited_message(m: Message):
            # Команды не обрабатываем
            if m.text and (m.text.startswith("/") or m.text.startswith("!")):
                return
            admin_msg_id = m.message_id
            # Получаем target_id из msg_map (сохраняется при отправке админом)
            target_id = self.msg_map.get(admin_msg_id)
            # Ищем user_msg_id: ключ в user_to_admin_map где value == admin_msg_id
            user_msg_id = next(
                (umid for (uid, umid), amid in self.user_to_admin_map.items()
                 if amid == admin_msg_id),
                None
            )
            if not target_id and user_msg_id:
                target_id = next(
                    (uid for (uid, umid) in self.user_to_admin_map
                     if umid == user_msg_id and self.user_to_admin_map.get((uid, umid)) == admin_msg_id),
                    None
                )
            if target_id and user_msg_id:
                try:
                    if m.text:
                        await self.bot.edit_message_text(
                            chat_id=target_id,
                            message_id=user_msg_id,
                            text=m.text,
                            parse_mode="HTML"
                        )
                    elif m.caption is not None:
                        await self.bot.edit_message_caption(
                            chat_id=target_id,
                            message_id=user_msg_id,
                            caption=m.caption,
                            parse_mode="HTML"
                        )
                except TelegramBadRequest as e:
                    logger.warning(f"Admin edit → user failed: {e}")
                except Exception as e:
                    logger.warning(f"Admin edit → user error: {e}")

        # ── 4б. Редактирование сообщения пользователем → обновить у админа
        @self.user_router.edited_message()
        async def user_edited_message(m: Message):
            if self.admin_chat_id and m.chat.id == self.admin_chat_id:
                return
            uid = m.from_user.id
            admin_msg_id = self.user_to_admin_map.get((uid, m.message_id))
            if admin_msg_id and self.admin_chat_id:
                try:
                    if m.text:
                        await self.bot.edit_message_text(
                            chat_id=self.admin_chat_id,
                            message_id=admin_msg_id,
                            text=m.text,
                            parse_mode="HTML"
                        )
                    elif m.caption is not None:
                        await self.bot.edit_message_caption(
                            chat_id=self.admin_chat_id,
                            message_id=admin_msg_id,
                            caption=m.caption,
                            parse_mode="HTML"
                        )
                except TelegramBadRequest as e:
                    logger.warning(f"User edit → admin failed: {e}")
                except Exception as e:
                    logger.warning(f"User edit → admin error: {e}")

        # ── 5. Закрытие тикета (callback) ───────────────────────────────────
        @self.user_router.callback_query(lambda c: c.data == "ticket_close")
        async def on_ticket_close(cb: CallbackQuery):
            uid_cb  = cb.from_user.id
            user_cb = next((u for u in self.users_list if u["id"] == uid_cb), None)
            if user_cb:
                user_cb.pop("_in_ticket", None)
                await self._push_state_immediate()
                if self.admin_chat_id:
                    try:
                        name_line = user_cb.get("first_name", str(uid_cb))
                        if user_cb.get("username"):
                            name_line += f" (@{user_cb['username']})"
                        await self.bot.send_message(
                            self.admin_chat_id,
                            f"Обращение закрыто пользователем.\n{name_line} | ID: <code>{uid_cb}</code>",
                            message_thread_id=user_cb.get("last_topic_id"),
                        )
                    except Exception:
                        pass
            try:
                await cb.message.delete()
            except Exception:
                pass
            try:
                await cb.answer("Обращение закрыто.")
            except Exception:
                pass
            try:
                await self.bot.send_message(
                    uid_cb, "<b>Обращение закрыто.</b>",
                    reply_markup=self.get_main_keyboard()
                )
            except Exception:
                pass

        # ── 6. ВСЕ СООБЩЕНИЯ ОТ ПОЛЬЗОВАТЕЛЕЙ ──────────────────────────────
        @self.user_router.message()
        async def user_input(m: Message):
            if self.admin_chat_id and m.chat.id == self.admin_chat_id:
                return

            user, is_new = await self.get_user_state(m)
            if user.get("is_banned"):
                if m.from_user.id in self.admin_ids:
                    unban_kb = InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔓 Разбанить себя", callback_data="selfunban")
                    ]])
                    try:
                        await m.answer(
                            "⚠️ <b>Вы случайно забанили себя (администратора).</b>\n"
                            "Нажмите кнопку ниже, чтобы снять блокировку:",
                            reply_markup=unban_kb
                        )
                    except Exception:
                        pass
                else:
                    try:
                        await m.answer("🚫 <b>Вы заблокированы в этом боте.</b>")
                    except Exception:
                        pass
                return

            uid = user["id"]

            # ── Защита от медиа-спама (аудио/файлы без текста) ──────────────
            # Используем отдельный rate-limit для медиа-сообщений
            is_media = bool(m.audio or m.voice or m.document or m.sticker or m.video_note)
            if is_media and not user.get("_in_ticket") and not self.forward_all:
                now = time.time()
                media_key = f"media_{uid}"
                last_media = self.flood_cache.get(media_key, 0)
                media_rate = max(self.rate_limit, 3.0)  # минимум 3 сек между медиа вне тикета
                if now - last_media < media_rate:
                    return  # молча игнорируем — не отвечаем чтобы не провоцировать
                self.flood_cache[media_key] = now

            logger.info(
                f"[MSG] uid={uid} text={repr(m.text or '[media]')} | "
                f"buttons={len(self.buttons)} triggers={len(self.triggers)} "
                f"forwardAll={self.forward_all} in_ticket={user.get('_in_ticket')} is_new={is_new}"
            )

            # ── Media group ─────────────────────────────────────────────────
            if m.media_group_id:
                gid = m.media_group_id
                if gid not in self.media_group_buffer:
                    self.media_group_buffer[gid] = {
                        "messages": [], "user": user,
                        "is_first": is_new, "in_ticket": user.get("_in_ticket", False),
                    }
                    async def _flush(group_id=gid):
                        await asyncio.sleep(1.0)
                        buf = self.media_group_buffer.pop(group_id, None)
                        if not buf or not buf["messages"]:
                            return

                        # Сохраняем все медиа в БД
                        for msg in buf["messages"]:
                            if msg.photo:
                                asyncio.create_task(self._save_media_to_db(buf["user"]["id"], "photo", msg.photo[-1].file_id))
                            elif msg.video:
                                asyncio.create_task(self._save_media_to_db(buf["user"]["id"], "video", msg.video.file_id))
                            elif msg.document:
                                asyncio.create_task(self._save_media_to_db(buf["user"]["id"], "document", msg.document.file_id))

                        should_forward = buf["in_ticket"] or self.forward_all or buf["is_first"]

                        if should_forward and self.admin_chat_id:
                            first_m = buf["messages"][0]
                            header  = format_admin_header(first_m, self.settings, buf["is_first"])
                            try:
                                from aiogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument
                                items = []
                                for i, msg in enumerate(buf["messages"]):
                                    cap = (header if i == 0 else "") + (msg.caption or "")
                                    if msg.photo:
                                        items.append(InputMediaPhoto(media=msg.photo[-1].file_id, caption=cap[:1024] or None, parse_mode="HTML"))
                                    elif msg.video:
                                        items.append(InputMediaVideo(media=msg.video.file_id, caption=cap[:1024] or None, parse_mode="HTML"))
                                    elif msg.document:
                                        items.append(InputMediaDocument(media=msg.document.file_id, caption=cap[:1024] or None, parse_mode="HTML"))
                                if items:
                                    # Топик: только если нет существующего
                                    existing_mg_tid = buf["user"].get("last_topic_id")
                                    force_mg = self.topic_per_req and buf["in_ticket"] and not existing_mg_tid
                                    mg_tid   = await self.resolve_thread(buf["user"], force_new=force_mg)
                                    await self.bot.send_media_group(
                                        self.admin_chat_id, items,
                                        message_thread_id=mg_tid
                                    )
                            except Exception as e:
                                logger.error(f"MediaGroup flush error: {e}")

                        await self.log_and_update(buf["user"]["id"], buf["messages"][0].from_user.full_name, f"[МедиаГруппа: {len(buf['messages'])} файл(ов)]")

                        # Если не в тикете и не forwardAll — подсказать про тикет
                        if not should_forward:
                            ticket_buttons = [b for b in self.buttons if b.get("type") == "ticket"]
                            if ticket_buttons:
                                hint = f'Чтобы отправить файлы оператору, воспользуйтесь кнопкой «{ticket_buttons[0]["text"]}».'
                                try:
                                    await self.bot.send_message(buf["user"]["id"], hint, reply_markup=self.get_main_keyboard())
                                except Exception:
                                    pass

                    asyncio.create_task(_flush())
                self.media_group_buffer[gid]["messages"].append(m)
                return

            # ── Антиспам ────────────────────────────────────────────────────
            if await self.check_antispam(uid):
                return

            # ── Кнопки и триггеры ───────────────────────────────────────────
            if m.text:
                clean = m.text.strip()
                lower = clean.lower()

                close_label = user.get("_ticket_close_label", "Закрыть обращение")
                if clean in (close_label, "Закрыть обращение", "⬅️ Назад", "Назад"):
                    was_in_ticket = user.get("_in_ticket", False)
                    user.pop("_in_ticket", None)
                    user.pop("_ticket_close_label", None)
                    if was_in_ticket:
                        await self._push_state_immediate()
                        if self.admin_chat_id:
                            try:
                                name_line = user.get("first_name", str(uid))
                                if user.get("username"):
                                    name_line += f" (@{user['username']})"
                                await self.bot.send_message(
                                    self.admin_chat_id,
                                    f"Обращение закрыто пользователем.\n{name_line} | ID: <code>{uid}</code>",
                                    message_thread_id=user.get("last_topic_id"),
                                )
                            except Exception:
                                pass
                        await m.answer("Обращение закрыто.", reply_markup=self.get_main_keyboard())
                    else:
                        await m.answer("Главное меню:", reply_markup=self.get_main_keyboard())
                    return

                matched_btn = next(
                    (b for b in self.buttons if b.get("text", "").strip().lower() == lower),
                    None
                )
                if matched_btn:
                    btn_type = matched_btn.get("type", "default")

                    if user.get("_in_ticket") and btn_type != "ticket":
                        await self.forward_to_admin(m, user)
                        await self.log_and_update(uid, m.from_user.full_name, m.text or "[Медиа]")
                        return

                    if btn_type == "ticket":
                        user["_in_ticket"]          = True
                        user["_ticket_close_label"] = "Закрыть обращение"
                        await self.forward_to_admin(m, user, btn_text=matched_btn["text"])
                        resp     = matched_btn.get("response") or "Ваше обращение принято. Ожидайте ответа оператора."
                        close_kb = ReplyKeyboardMarkup(
                            keyboard=[[KeyboardButton(text="Закрыть обращение")]],
                            resize_keyboard=True
                        )
                        await m.answer(
                            f"{resp}\n\nВы можете продолжать писать — сообщения будут доставлены оператору.",
                            reply_markup=close_kb
                        )
                    else:
                        resp      = matched_btn.get("response", "")
                        inline_kb = self.build_inline_from_list(matched_btn.get("inline", []))
                        await m.answer(
                            resp or "✅",
                            reply_markup=inline_kb if inline_kb else self.get_main_keyboard()
                        )

                    await self.log_and_update(uid, m.from_user.full_name, f"КНОПКА: {matched_btn['text']}")
                    return

                for trig in self.triggers:
                    kw = trig.get("keyword", "").strip()
                    if kw and kw.lower() in lower:
                        resp = trig.get("response") or "✅"
                        await m.answer(resp)
                        await self.log_and_update(uid, m.from_user.full_name, f"ТРИГГЕР: {kw}")
                        return

            if user.get("_in_ticket"):
                await self.forward_to_admin(m, user)
                await self.log_and_update(uid, m.from_user.full_name, m.text or "[Медиа]")
                return

            if is_new or self.forward_all:
                await self.forward_to_admin(m, user, is_first=is_new)
                await self.log_and_update(uid, m.from_user.full_name, m.text or "[Медиа]")
                return

            # Режим без forwardAll — сообщение только через тикет
            ticket_buttons = [b for b in self.buttons if b.get("type") == "ticket"]
            if ticket_buttons:
                hint = f'Чтобы связаться с нами, воспользуйтесь кнопкой «{ticket_buttons[0]["text"]}».'
            elif self.buttons:
                hint = "Воспользуйтесь кнопками меню."
            else:
                hint = "Чтобы связаться с оператором, сначала откройте обращение."
            try:
                await m.answer(hint, reply_markup=self.get_main_keyboard())
            except Exception:
                pass
            await self.log_and_update(uid, m.from_user.full_name, m.text or "[Медиа]")

    # ─────────────────────────────────────────────────────────────────────────
    # ЗАПУСК
    # ─────────────────────────────────────────────────────────────────────────

    async def run_instance(self):
        logger.info(f"[FREE] Бот {self.bot_id} стартует...")

        await self.sync_database_logic()

        asyncio.create_task(self.config_sync_loop())
        asyncio.create_task(self.daily_stats_rotator())

        await self.core_handlers_setup()

        self.dp.include_router(self.admin_router)
        self.dp.include_router(self.user_router)

        logger.info(
            f"[FREE] Бот {self.bot_id} готов. "
            f"Кнопок: {len(self.buttons)}, "
            f"Триггеров: {len(self.triggers)}, "
            f"Users: {len(self.users_list)}, "
            f"admin_chat: {self.admin_chat_id}, "
            f"forwardAll={self.forward_all}, "
            f"inlineButtons={len(self.inline_buttons)}"
        )

        try:
            # Сбрасываем webhook — иначе getUpdates (polling) даёт TelegramConflictError
            await self.bot.delete_webhook(drop_pending_updates=True)
            await self.dp.start_polling(
                self.bot,
                drop_pending_updates=True,
                allowed_updates=["message", "edited_message", "callback_query", "my_chat_member"]
            )
        finally:
            self.is_running = False
            await self.bot.session.close()


# ════════════════════════════════════════════════════════════════════════════════
# ТОЧКА ВХОДА
# ════════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("INFO: free_bot_core.py is a worker script. "
              "Started by server.py with config path argument.\n"
              "Sleeping to prevent PM2 restart loop...", flush=True)
        import signal
        stop_event = asyncio.Event()
        def _sig(*_): stop_event.set()
        signal.signal(signal.SIGTERM, _sig)
        signal.signal(signal.SIGINT, _sig)
        async def _idle():
            await stop_event.wait()
        asyncio.run(_idle())
        sys.exit(0)

    async def main():
        cfg_path = sys.argv[1]
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            instance = FreeBotInstance(config)
            await instance.run_instance()
        except Exception as e:
            logger.error(f"FATAL: {e}", exc_info=True)

    asyncio.run(main())
