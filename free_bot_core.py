"""
free_bot_core.py
================================================================================
Запускальщик free-плана ботов для BotEngine.
Ключевые исправления v3:
  • Нет лимита памяти (убран memory watchdog)
  • Нет лимита количества ботов
  • sync_state НЕ вызывает apply_config — это устраняло race condition
    (кнопки/настройки "забывались" после каждого сообщения)
  • Бот перезагружает конфиг только при явном config_reload сигнале
  • Кнопки/триггеры работают при forwardAll=True
  • Рассылка стикеров, медиа — полная поддержка copy_message
  • Счётчик пользователей правильный (len(users_list))
  • broadcast без лимита (FREE_BROADCAST_DAY убран)
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
            parts.append(f"<b>{m.from_user.full_name or 'Пользователь'}</b>")
        if settings.get("showHeaderUsername", True) and m.from_user.username:
            parts.append(f"(@{m.from_user.username})")
        if settings.get("showHeaderId", True):
            parts.append(f"ID: <code>{uid}</code>")
        user_info = " | ".join(parts) if parts else f"Юзер {anon}"

    if btn_text:
        hdr = settings.get("ticketMessageHeader", "🆘 <b>ЗАЯВКА</b>")
        if "{btn}" in hdr:
            hdr = hdr.replace("{btn}", btn_text)
        else:
            hdr += f" [{btn_text}]:"
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
        self.router = Router()

        self.msg_map:            Dict[int, int]  = {}
        self.flood_cache:        Dict[int, float] = {}
        self.broadcast_cache:    Dict[int, str]   = {}
        self.media_group_buffer: Dict[str, dict]  = {}
        self.is_running   = True
        self.sync_queue   = asyncio.Queue()
        self.config       = config_data
        self._broadcast_day: Dict = {"date": "", "count": 0}
        self._last_push: float = 0.0  # дебаунс для _push_state

        self.apply_config(config_data)

    # ─────────────────────────────────────────────────────────────────────────
    # ПАРСИНГ КОНФИГА
    # ─────────────────────────────────────────────────────────────────────────

    def apply_config(self, data: dict):
        """Применяет конфиг. Вызывается только при старте и явном config_reload."""
        raw_cfg  = data.get("config", {}) if isinstance(data.get("config"), dict) else {}
        full_cfg = {**data, **raw_cfg}

        admin_raw = full_cfg.get("admin_chat_id") or full_cfg.get("adminChatId")
        self.admin_chat_id = int(str(admin_raw).strip()) if admin_raw else None

        self.settings      = full_cfg.get("settings", {})
        self.use_topics    = self.settings.get("useTopics", False)
        self.topic_per_req = self.settings.get("topicPerRequest", False)
        self.forward_all   = self.settings.get("forwardAll", False)
        self.forward_native = self.settings.get("forwardMessages", False)  # нативный forward

        self.buttons       = full_cfg.get("buttons",  [])
        self.triggers      = full_cfg.get("triggers", [])
        self.welcome_text  = full_cfg.get("welcomeMessage", "Здравствуйте!")
        self.welcome_photo = full_cfg.get("welcomePhoto", "")
        self.welcome_inline = full_cfg.get("welcomeInline", [])
        self.rate_limit    = float(self.settings.get("rateLimit", 1.0))
        self.auto_ban_limit = int(self.settings.get("autoBanThreshold", 3))

        # users_list инициализируем только при первом вызове
        if not hasattr(self, "users_list"):
            self.users_list = full_cfg.get("connectedUsers", [])

        self.ad_enabled      = data.get("ad_enabled", True)
        self.server_base_url = os.getenv("SERVER_BASE_URL", "http://localhost:8000")

        # stats инициализируем только при первом вызове
        if not hasattr(self, "stats_data"):
            st = full_cfg.get("stats", {})
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

    def reload_config_from_remote(self, remote_cfg: dict):
        """
        Обновляет только настройки (кнопки, триггеры, тексты) из БД.
        НЕ трогает users_list и stats_data — они хранятся в памяти и пишутся в БД, не наоборот.
        """
        full = remote_cfg  # уже развёрнутый config dict

        admin_raw = full.get("adminChatId") or full.get("admin_chat_id")
        if admin_raw:
            self.admin_chat_id = int(str(admin_raw).strip())

        stg = full.get("settings", self.settings)
        self.settings       = stg
        self.use_topics     = stg.get("useTopics", False)
        self.topic_per_req  = stg.get("topicPerRequest", False)
        self.forward_all    = stg.get("forwardAll", False)
        self.forward_native = stg.get("forwardMessages", False)
        self.rate_limit     = float(stg.get("rateLimit", 1.0))
        self.auto_ban_limit = int(stg.get("autoBanThreshold", 3))

        if "buttons" in full:
            self.buttons = full["buttons"]
        if "triggers" in full:
            self.triggers = full["triggers"]
        if "welcomeMessage" in full:
            self.welcome_text = full["welcomeMessage"]
        if "welcomePhoto" in full:
            self.welcome_photo = full["welcomePhoto"]

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
        if not buttons:
            return None
        rows = []
        for i in range(0, len(buttons), 2):
            rows.append([
                InlineKeyboardButton(text=b["text"], url=b.get("url", "https://t.me"))
                for b in buttons[i:i+2] if b.get("text")
            ])
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
            name  = user.get("first_name", "Пользователь")
            uname = user.get("username")
            title = f"{name}" + (f" @{uname}" if uname else f" #{user['id']}")
            topic = await self.bot.create_forum_topic(
                chat_id=self.admin_chat_id, name=title[:128]
            )
            user["last_topic_id"] = topic.message_thread_id
            return topic.message_thread_id
        except TelegramBadRequest as e:
            logger.warning(f"resolve_thread error: {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # ФОРВАРД К АДМИНУ
    # ─────────────────────────────────────────────────────────────────────────

    async def forward_to_admin(self, m: Message, user: dict,
                               is_first: bool = False, btn_text: str = ""):
        if not self.admin_chat_id:
            return

        force_new = self.topic_per_req and (btn_text or is_first)
        thread_id = await self.resolve_thread(user, force_new=force_new)

        # Нативный форвард (без заголовка)
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
                    except Exception:
                        pass
                else:
                    logger.error(f"forward_to_admin(native) TelegramBadRequest: {e}")
            except Exception as e:
                logger.error(f"forward_to_admin(native) error: {e}")
            return

        # copy_message с заголовком
        header = format_admin_header(m, self.settings, is_first, btn_text)

        async def _send():
            nonlocal thread_id
            try:
                if m.photo:
                    s = await self.bot.send_photo(
                        self.admin_chat_id, photo=m.photo[-1].file_id,
                        caption=(header + (m.caption or ""))[:1024],
                        message_thread_id=thread_id,
                    )
                elif m.video:
                    s = await self.bot.send_video(
                        self.admin_chat_id, video=m.video.file_id,
                        caption=(header + (m.caption or ""))[:1024],
                        message_thread_id=thread_id,
                    )
                elif m.document:
                    s = await self.bot.send_document(
                        self.admin_chat_id, document=m.document.file_id,
                        caption=(header + (m.caption or ""))[:1024],
                        message_thread_id=thread_id,
                    )
                elif m.audio:
                    await self.bot.send_message(
                        self.admin_chat_id, header.strip(),
                        message_thread_id=thread_id, parse_mode="HTML"
                    )
                    s = await self.bot.copy_message(
                        self.admin_chat_id, m.chat.id, m.message_id,
                        message_thread_id=thread_id
                    )
                elif m.voice:
                    await self.bot.send_message(
                        self.admin_chat_id, header.strip(),
                        message_thread_id=thread_id, parse_mode="HTML"
                    )
                    s = await self.bot.copy_message(
                        self.admin_chat_id, m.chat.id, m.message_id,
                        message_thread_id=thread_id
                    )
                elif m.sticker:
                    await self.bot.send_message(
                        self.admin_chat_id, header.strip(),
                        message_thread_id=thread_id, parse_mode="HTML"
                    )
                    s = await self.bot.copy_message(
                        self.admin_chat_id, m.chat.id, m.message_id,
                        message_thread_id=thread_id
                    )
                elif m.video_note:
                    await self.bot.send_message(
                        self.admin_chat_id, header.strip(),
                        message_thread_id=thread_id, parse_mode="HTML"
                    )
                    s = await self.bot.copy_message(
                        self.admin_chat_id, m.chat.id, m.message_id,
                        message_thread_id=thread_id
                    )
                else:
                    # Текст
                    txt = (header + (m.text or ""))[:4096]
                    s = await self.bot.send_message(
                        self.admin_chat_id, txt,
                        message_thread_id=thread_id, parse_mode="HTML"
                    )
                if s:
                    self.msg_map[s.message_id] = user["id"]
            except TelegramBadRequest as e:
                err_str = str(e).lower()
                if "message thread not found" in err_str or "thread" in err_str:
                    user["last_topic_id"] = None
                    thread_id = await self.resolve_thread(user, force_new=True)
                    # retry без темы
                    try:
                        txt = (header + (m.text or ""))[:4096]
                        s = await self.bot.send_message(
                            self.admin_chat_id, txt, parse_mode="HTML"
                        )
                        if s:
                            self.msg_map[s.message_id] = user["id"]
                    except Exception:
                        pass
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
    # СТАТИСТИКА
    # ─────────────────────────────────────────────────────────────────────────

    async def log_and_update(self, uid: int, name: str, text: str, is_admin: bool = False):
        # Обновляем счётчики в памяти
        self.stats_data["totalMessages"] = self.stats_data.get("totalMessages", 0) + 1
        key = "outgoingToday" if is_admin else "incomingToday"
        self.stats_data[key] = self.stats_data.get(key, 0) + 1

        if not is_admin:
            for u in self.users_list:
                if u["id"] == uid:
                    u["last_seen"]  = int(time.time())
                    u["first_name"] = name
                    break

        # Логируем в БД асинхронно (не блокируем обработку сообщений)
        asyncio.create_task(self._log_message(uid, name, text, is_admin))
        # Пушим state с дебаунсом (не каждый раз)
        asyncio.create_task(self._push_state())

    async def _log_message(self, uid: int, name: str, text: str, is_admin: bool):
        """Пишет сообщение в bot_messages. Ошибки не критичны."""
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
                    headers={**self.headers, "Prefer": "return=minimal"}
                )
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────────
    # СОХРАНЕНИЕ В БД
    # ─────────────────────────────────────────────────────────────────────────

    async def _push_state(self):
        """Пушит users_list и stats в БД с дебаунсом 5 секунд."""
        now = time.time()
        # Дебаунс: не чаще 1 раза в 5 секунд
        if hasattr(self, '_last_push') and now - self._last_push < 5.0:
            return
        self._last_push = now
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                res = await client.get(
                    f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}&select=config",
                    headers=self.headers
                )
                if res.status_code != 200 or not res.json():
                    return
                remote_cfg = res.json()[0].get("config") or {}
                new_cfg = {
                    **remote_cfg,
                    "connectedUsers": self.users_list,
                    "stats":          self.stats_data,
                }
                await client.patch(
                    f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                    json={"config": new_cfg},
                    headers={**self.headers, "Prefer": "return=minimal"}
                )
        except Exception as e:
            logger.debug(f"_push_state error (non-fatal): {e}")

    async def _save_to_db(self):
        """Явное синхронное сохранение (для команд /ban, /broadcast и т.п.)."""
        await self._push_state()

    # ─────────────────────────────────────────────────────────────────────────
    # ПЕРИОДИЧЕСКАЯ СИНХРОНИЗАЦИЯ (конфиг из БД → reload_config_from_remote)
    # ─────────────────────────────────────────────────────────────────────────

    async def config_sync_loop(self):
        """
        Каждые 30 секунд читает конфиг из БД и обновляет кнопки/настройки.
        НЕ трогает users_list и stats_data — они живут в памяти.
        """
        await asyncio.sleep(30)  # первый запуск через 30с после старта
        while self.is_running:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    res = await client.get(
                        f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                        headers=self.headers
                    )
                    if res.status_code == 200 and res.json():
                        remote_cfg = res.json()[0].get("config", {}) or {}
                        self.reload_config_from_remote(remote_cfg)
                        logger.debug(
                            f"[{self.bot_id}] Config reloaded: "
                            f"buttons={len(self.buttons)}, triggers={len(self.triggers)}, "
                            f"forwardAll={self.forward_all}"
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

                # Принудительный сброс дебаунса — гарантируем сохранение каждую минуту
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

        # /stats
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

        # /broadcast
        elif command == "broadcast":
            active_users = [u for u in self.users_list if not u.get("is_banned") and u.get("is_active", True)]

            if not active_users:
                await m.reply("Нет активных пользователей для рассылки.")
                return True

            if m.reply_to_message:
                target_msg_id = m.reply_to_message.message_id
                await self._do_broadcast(m, active_users, target_msg_id)
            else:
                self.broadcast_cache[m.from_user.id] = "WAITING"
                await m.reply(
                    f"📢 <b>Режим рассылки</b>\n"
                    f"Ответьте на это сообщение реплаем, либо пришлите следующим сообщением то, что хотите разослать.\n\n"
                    f"<i>Поддерживаются: текст, фото, видео, документы, стикеры и любые медиа</i>"
                )
            return True

        # Команды модерации — ищем target_user
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
            uname    = target_user.get("username")
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
    # РАССЫЛКА — отдельный метод
    # ─────────────────────────────────────────────────────────────────────────

    async def _do_broadcast(self, m: Message, active_users: list, source_msg_id: int):
        sent_c, err_c = 0, 0
        bc_count = self._broadcast_today_count()
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
                await asyncio.sleep(0.04)  # ~25 msg/s
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
                logger.debug(f"broadcast send error for {user['id']}: {e}")
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
        """Разовая загрузка конфига при старте."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(
                    f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                    headers=self.headers
                )
                if res.status_code == 200 and res.json():
                    remote = res.json()[0]
                    rc     = remote.get("config") or {}
                    if isinstance(rc, str):
                        try:
                            rc = json.loads(rc)
                        except Exception:
                            rc = {}
                    # При старте применяем полный конфиг
                    self.apply_config({**remote, "config": rc})
                    logger.info(
                        f"✅ [{self.bot_id}] Конфиг загружен: "
                        f"кнопок={len(self.buttons)}, триггеров={len(self.triggers)}, "
                        f"users={len(self.users_list)}, "
                        f"forwardAll={self.forward_all}"
                    )
        except Exception as e:
            logger.error(f"sync_database_logic error: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # HANDLERS
    # ─────────────────────────────────────────────────────────────────────────

    async def core_handlers_setup(self):
        self.router.message.middleware(BanMiddleware(self))
        self.router.callback_query.middleware(BanMiddleware(self))

        # 1. Пользователь заблокировал бота
        @self.router.my_chat_member(
            ChatMemberUpdatedFilter(member_status_changed=ChatMemberStatus.KICKED)
        )
        async def on_user_blocked(event: ChatMemberUpdated):
            uid  = event.from_user.id
            user = next((u for u in self.users_list if u["id"] == uid), None)
            if user:
                user["is_active"] = False
                await self._push_state()
                if self.admin_chat_id:
                    try:
                        await self.bot.send_message(
                            self.admin_chat_id,
                            f"🔴 <b>{event.from_user.full_name}</b> заблокировал бота.",
                            message_thread_id=user.get("last_topic_id"),
                        )
                    except Exception:
                        pass

        # 2. /start
        @self.router.message(CommandStart())
        async def handle_start(m: Message):
            user, is_new = await self.get_user_state(m)
            if user.get("is_banned"):
                await m.answer("🚫 <b>Вы заблокированы в этом боте.</b>")
                return

            reply_kb  = self.get_main_keyboard()
            inline_kb = self.build_inline_from_list(self.welcome_inline)
            main_kb   = inline_kb if inline_kb else reply_kb

            ad       = await self.get_active_ad() if self.ad_enabled else None
            welcome  = self.welcome_text or "Здравствуйте!"
            ad_text  = ""
            ad_media = ""

            if ad:
                ad_text  = ad.get("text", "")
                ad_media = ad.get("media_url", "") or ""
                combined = f"{welcome}\n\n─────────────────\n📢 <b>Реклама</b>\n{ad_text}"
            else:
                combined = welcome

            try:
                if self.welcome_photo:
                    await m.answer_photo(
                        photo=self.welcome_photo,
                        caption=combined[:1024],
                        reply_markup=main_kb,
                    )
                    if ad and ad_media and ad_media != self.welcome_photo:
                        await m.answer_photo(photo=ad_media, caption=f"📢 {ad_text}"[:1024])
                elif ad and ad_media:
                    await m.answer(text=welcome, reply_markup=main_kb)
                    await m.answer_photo(photo=ad_media, caption=f"📢 <b>Реклама</b>\n{ad_text}"[:1024])
                else:
                    await m.answer(text=combined, reply_markup=main_kb)
            except Exception as e:
                logger.warning(f"handle_start send error: {e}")
                try:
                    await m.answer(text=welcome, reply_markup=reply_kb)
                except Exception:
                    pass

            await self.log_and_update(user["id"], m.from_user.full_name, "/start")

        # 3. Сообщения от АДМИНА
        # Используем lambda вместо F.chat.id чтобы поддерживать динамическое admin_chat_id
        @self.router.message(lambda m: self.admin_chat_id and m.chat.id == self.admin_chat_id)
        async def admin_input(m: Message):
            # Команды
            if m.text and (m.text.startswith("/") or m.text.startswith("!")):
                await self.admin_control_logic(m)
                return

            # Режим ожидания рассылки
            if self.broadcast_cache.get(m.from_user.id) == "WAITING":
                del self.broadcast_cache[m.from_user.id]
                active_users = [u for u in self.users_list
                                if not u.get("is_banned") and u.get("is_active", True)]
                if not active_users:
                    await m.reply("Нет активных пользователей.")
                    return
                await self._do_broadcast(m, active_users, m.message_id)
                return

            # Ответ пользователю (топик или реплай)
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
                    await self.bot.copy_message(target_id, m.chat.id, m.message_id)
                    await self.log_and_update(target_id, "Admin", m.text or "[Медиа]", is_admin=True)
                except TelegramForbiddenError:
                    await m.reply("❌ Пользователь заблокировал бота.")
                except Exception as e:
                    await m.reply(f"❌ Ошибка: {e}")

        # 4. Закрытие тикета
        @self.router.callback_query(lambda c: c.data == "ticket_close")
        async def on_ticket_close(cb: CallbackQuery):
            uid_cb  = cb.from_user.id
            user_cb = next((u for u in self.users_list if u["id"] == uid_cb), None)
            if user_cb:
                user_cb.pop("_in_ticket", None)
                await self._push_state()
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

        # 5. Все сообщения от пользователей
        @self.router.message()
        async def user_input(m: Message):
            # Пропускаем сообщения из admin_chat
            if self.admin_chat_id and m.chat.id == self.admin_chat_id:
                return

            user, is_new = await self.get_user_state(m)
            if user.get("is_banned"):
                try:
                    await m.answer("🚫 <b>Вы заблокированы в этом боте.</b>")
                except Exception:
                    pass
                return

            uid = user["id"]

            # Media group
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
                        if buf["in_ticket"] or self.forward_all or buf["is_first"]:
                            first_m = buf["messages"][0]
                            header  = format_admin_header(first_m, self.settings, buf["is_first"])
                            if self.admin_chat_id:
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
                                        await self.bot.send_media_group(
                                            self.admin_chat_id, items,
                                            message_thread_id=buf["user"].get("last_topic_id")
                                        )
                                except Exception as e:
                                    logger.error(f"MediaGroup flush error: {e}")
                            await self.log_and_update(buf["user"]["id"], first_m.from_user.full_name, "[МедиаГруппа]")
                    asyncio.create_task(_flush())
                self.media_group_buffer[gid]["messages"].append(m)
                return

            # Антиспам
            if await self.check_antispam(uid):
                return

            # ── Тикет: активный режим ───────────────────────────────────────
            if user.get("_in_ticket"):
                close_label = user.get("_ticket_close_label", "Закрыть обращение")
                if m.text and m.text.strip() in (close_label, "Закрыть обращение"):
                    user.pop("_in_ticket", None)
                    user.pop("_ticket_close_label", None)
                    await self._push_state()
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
                    return
                # В тикете — форвардим
                await self.forward_to_admin(m, user)
                await self.log_and_update(uid, m.from_user.full_name, m.text or "[Медиа]")
                return

            # ── Кнопки и триггеры — ВСЕГДА ДО forwardAll ──────────────────
            if m.text:
                clean = m.text.strip()
                lower = clean.lower()

                # Кнопка "Назад"
                if clean in ("⬅️ Назад", "Назад"):
                    await m.answer("Главное меню:", reply_markup=self.get_main_keyboard())
                    return

                # Reply-кнопки меню
                matched_btn = next(
                    (b for b in self.buttons if b.get("text", "").lower() == lower), None
                )
                if matched_btn:
                    btn_type = matched_btn.get("type", "default")
                    if btn_type == "ticket":
                        user["_in_ticket"]         = True
                        user["_ticket_close_label"] = "Закрыть обращение"
                        await self.forward_to_admin(m, user, btn_text=matched_btn["text"])
                        resp     = matched_btn.get("response", "Ваше обращение принято. Ожидайте ответа оператора.")
                        close_kb = ReplyKeyboardMarkup(
                            keyboard=[[KeyboardButton(text="Закрыть обращение")]],
                            resize_keyboard=True
                        )
                        await m.answer(
                            f"{resp}\n\nВы можете продолжать писать — сообщения будут доставлены оператору.",
                            reply_markup=close_kb
                        )
                    else:
                        resp       = matched_btn.get("response", "")
                        inline_kb  = self.build_inline_from_list(matched_btn.get("inline", []))
                        await m.answer(
                            resp or "✅",
                            reply_markup=inline_kb if inline_kb else self.get_main_keyboard()
                        )
                    await self.log_and_update(uid, m.from_user.full_name, f"КНОПКА: {matched_btn['text']}")
                    return

                # Триггеры
                for trig in self.triggers:
                    if trig.get("keyword") and trig["keyword"].lower() in lower:
                        await m.answer(trig.get("response") or "✅")
                        await self.log_and_update(uid, m.from_user.full_name, f"ТРИГГЕР: {trig['keyword']}")
                        return

            # ── Форвард: первое обращение или forwardAll ───────────────────
            if is_new or self.forward_all:
                await self.forward_to_admin(m, user, is_first=is_new)
                await self.log_and_update(uid, m.from_user.full_name, m.text or "[Медиа]")
            else:
                # Нет кнопок, нет тикета, нет forwardAll — показываем меню
                await m.answer(
                    "Воспользуйтесь меню или нажмите кнопку для связи с оператором.",
                    reply_markup=self.get_main_keyboard()
                )

    # ─────────────────────────────────────────────────────────────────────────
    # ЗАПУСК
    # ─────────────────────────────────────────────────────────────────────────

    async def run_instance(self):
        logger.info(f"[FREE] Бот {self.bot_id} стартует...")

        await self.sync_database_logic()

        asyncio.create_task(self.config_sync_loop())   # перезагружает настройки каждые 30с
        asyncio.create_task(self.daily_stats_rotator())

        await self.core_handlers_setup()
        self.dp.include_router(self.router)

        logger.info(
            f"[FREE] Бот {self.bot_id} готов. "
            f"Кнопок: {len(self.buttons)}, "
            f"Триггеров: {len(self.triggers)}, "
            f"Users: {len(self.users_list)}, "
            f"forwardAll={self.forward_all}"
        )

        try:
            await self.dp.start_polling(
                self.bot,
                drop_pending_updates=True,   # не обрабатываем накопившиеся пока бот был offline
                allowed_updates=["message", "callback_query", "my_chat_member"]
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
