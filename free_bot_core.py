"""
free_bot_core.py
════════════════════════════════════════════════════════════════════════════════
Самостоятельный запускальщик free-плана ботов для BotEngine.

Отличия от bot_core.py:
  • Лимит: 2 кнопки, 2 триггера (enforced при старте)
  • Лимит рассылки: 10 получателей в день (счётчик сбрасывается в полночь)
  • Нет ИИ-ассистента, нет flow-логики, нет sandbox-кода
  • Реклама в /start: GET /api/ads/active → показываем после welcome
  • Memory watchdog: следит за RSS каждые 30 с, останавливает при превышении 25 МБ
  • Полная поддержка ping-pong (форвард к админу, ответ из топика/реплая)
  • Полная поддержка тикетов (type='ticket')
  • Полные команды модерации: /ban /unban /warn /unwarn /whois /stats
  • /broadcast — рассылка с лимитом 10/день
  • Аналитика: те же счётчики что у pro (stats, history)
  • Лицензия: бессрочно (free боты не проверяют license_expires_at)
  • Синхронизация с Supabase через ту же очередь sync_queue

Запуск (сервер делает это автоматически):
    python3 free_bot_core.py active_bots/cfg_<bot_id>.json
════════════════════════════════════════════════════════════════════════════════
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
from typing import Dict, Optional, List, Any, Callable, Awaitable

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

# ── КОНСТАНТЫ ОГРАНИЧЕНИЙ ────────────────────────────────────────────────────
FREE_MAX_BUTTONS   = 2
FREE_MAX_TRIGGERS  = 2
FREE_MEMORY_MB     = 25
FREE_BROADCAST_DAY = 10       # максимум рассылок (запусков /broadcast) в день

# ── ЛОГИРОВАНИЕ ──────────────────────────────────────────────────────────────
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
                    await event.answer("🚫 <b>Вы заблокированы в этом боте.</b>")
                elif isinstance(event, CallbackQuery):
                    await event.answer("🚫 Вы заблокированы.", show_alert=True)
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
        elif "[Кнопка" not in hdr:
            hdr += f" [Кнопка: {btn_text}]:"
    elif is_first:
        hdr = settings.get("firstMessageHeader",  "🆕 <b>ПЕРВОЕ ОБРАЩЕНИЕ:</b>")
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

        self.msg_map:           Dict[int, int]  = {}   # admin_msg_id → user_id
        self.flood_cache:       Dict[int, float] = {}
        self.broadcast_cache:   Dict[int, str]   = {}
        self.media_group_buffer: Dict[str, dict] = {}

        self.is_running    = True
        self.sync_queue    = asyncio.Queue()
        self.config        = config_data

        # Broadcast daily counter: {"date": "dd.mm", "count": N}
        self._broadcast_day: Dict = {"date": "", "count": 0}

        self.apply_config(config_data)

    # ─────────────────────────────────────────────────────────────────────────
    # ПАРСИНГ КОНФИГА
    # ─────────────────────────────────────────────────────────────────────────

    def apply_config(self, data: dict):
        raw_cfg  = data.get("config", {}) if isinstance(data.get("config"), dict) else {}
        full_cfg = {**data, **raw_cfg}

        admin_raw        = full_cfg.get("admin_chat_id") or full_cfg.get("adminChatId")
        self.admin_chat_id = int(str(admin_raw).strip()) if admin_raw else None

        self.settings    = full_cfg.get("settings", {})
        self.use_topics  = self.settings.get("useTopics", False)
        self.topic_per_req = self.settings.get("topicPerRequest", False)
        self.forward_all = self.settings.get("forwardAll", False)

        # ── Enforce FREE limits ───────────────────────────────────────────────
        raw_buttons  = full_cfg.get("buttons", [])
        raw_triggers = full_cfg.get("triggers", [])
        if len(raw_buttons) > FREE_MAX_BUTTONS:
            logger.warning(f"[FREE] {self.bot_id}: кнопок {len(raw_buttons)} > {FREE_MAX_BUTTONS}, обрезаю")
            raw_buttons = raw_buttons[:FREE_MAX_BUTTONS]
        if len(raw_triggers) > FREE_MAX_TRIGGERS:
            logger.warning(f"[FREE] {self.bot_id}: триггеров {len(raw_triggers)} > {FREE_MAX_TRIGGERS}, обрезаю")
            raw_triggers = raw_triggers[:FREE_MAX_TRIGGERS]

        self.buttons       = raw_buttons
        self.triggers      = raw_triggers
        self.welcome_text  = full_cfg.get("welcomeMessage", "Здравствуйте!")
        self.welcome_photo = full_cfg.get("welcomePhoto", "")
        self.welcome_inline = full_cfg.get("welcomeInline", [])
        self.rate_limit    = float(self.settings.get("rateLimit", 1.0))
        self.auto_ban_limit = int(self.settings.get("autoBanThreshold", 3))
        self.users_list    = full_cfg.get("connectedUsers", [])

        # Free план: реклама всегда включена
        self.ad_enabled      = data.get("ad_enabled", True)
        self.memory_limit_mb = data.get("memory_limit_mb", FREE_MEMORY_MB)
        self.server_base_url = os.getenv("SERVER_BASE_URL", "http://localhost:8000")

        # Статистика
        st = full_cfg.get("stats", {})
        self.stats_data = {
            "totalMessages":  st.get("totalMessages", 0),
            "incomingToday":  st.get("incomingToday", 0),
            "outgoingToday":  st.get("outgoingToday", 0),
            "bannedCount":    st.get("bannedCount", 0),
            "activeUsers24h": st.get("activeUsers24h", 0),
            "history":        st.get("history", []),
        }

        if not hasattr(self, "ai_context_cache"):
            self.ai_context_cache: Dict = {}

    # ─────────────────────────────────────────────────────────────────────────
    # РЕКЛАМА
    # ─────────────────────────────────────────────────────────────────────────

    async def get_active_ad(self) -> Optional[dict]:
        """Получить одно активное рекламное объявление с сервера."""
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

    async def send_ad_to_user(self, m: Message):
        """Отправить рекламный блок пользователю после welcome."""
        ad = await self.get_active_ad()
        if not ad:
            return
        ad_text = (
            "─────────────────\n"
            "📢 <b>Реклама</b>\n"
            f"{ad['text']}\n"
            "─────────────────"
        )
        try:
            if ad.get("media_url"):
                await m.answer_photo(photo=ad["media_url"], caption=ad_text, parse_mode="HTML")
            else:
                await m.answer(ad_text, parse_mode="HTML", disable_web_page_preview=True)
        except Exception as e:
            logger.warning(f"[FREE] Не удалось отправить рекламу: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # ПАМЯТЬ
    # ─────────────────────────────────────────────────────────────────────────

    def _current_rss_mb(self) -> int:
        try:
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) // 1024
        except Exception:
            pass
        return 0

    async def _memory_watchdog(self):
        """Следит за RSS памяти и останавливает бота при превышении лимита."""
        if not self.memory_limit_mb or self.memory_limit_mb <= 0:
            return
        logger.info(f"[FREE] Memory watchdog: лимит {self.memory_limit_mb} МБ")
        while self.is_running:
            await asyncio.sleep(30)
            rss = self._current_rss_mb()
            if rss > self.memory_limit_mb:
                logger.warning(
                    f"[FREE] {self.bot_id}: RSS {rss} МБ > лимит {self.memory_limit_mb} МБ. Останавливаю."
                )
                if self.admin_chat_id:
                    try:
                        await self.bot.send_message(
                            self.admin_chat_id,
                            f"⚠️ <b>Free-план: бот достиг лимита памяти</b> ({rss} МБ).\n"
                            f"Бот временно остановлен. Перейдите на Pro для снятия ограничений.",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass
                self.is_running = False
                break

    # ─────────────────────────────────────────────────────────────────────────
    # РАССЫЛКА (broadcast daily limit)
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
    # ТОПИКИ (форум-режим)
    # ─────────────────────────────────────────────────────────────────────────

    async def resolve_thread(self, user: dict, force_new: bool = False) -> Optional[int]:
        if not self.use_topics or not self.admin_chat_id:
            return None

        existing_tid = user.get("last_topic_id")
        if existing_tid and not force_new:
            return existing_tid

        try:
            name = user.get("first_name", "Пользователь")
            username = user.get("username")
            title = f"{name}" + (f" @{username}" if username else f" #{user['id']}")
            topic = await self.bot.create_forum_topic(
                chat_id=self.admin_chat_id,
                name=title[:128]
            )
            user["last_topic_id"] = topic.message_thread_id
            await self.sync_queue.put(("sync_state", None))
            return topic.message_thread_id
        except TelegramBadRequest as e:
            logger.warning(f"resolve_thread error: {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # ФОРВАРД К АДМИНУ
    # ─────────────────────────────────────────────────────────────────────────

    async def forward_to_admin(self, m: Message, user: dict,
                               is_first: bool = False,
                               btn_text: str = "",
                               is_ai_request: bool = False):
        if not self.admin_chat_id:
            return

        force_new = self.topic_per_req and (btn_text or is_first)
        thread_id = await self.resolve_thread(user, force_new=force_new)
        if not thread_id and self.use_topics:
            thread_id = await self.resolve_thread(user, force_new=True)

        header = format_admin_header(m, self.settings, is_first, btn_text)

        try:
            if m.photo:
                sent = await self.bot.send_photo(
                    self.admin_chat_id,
                    photo=m.photo[-1].file_id,
                    caption=header + (m.caption or ""),
                    message_thread_id=thread_id,
                )
            elif m.video:
                sent = await self.bot.send_video(
                    self.admin_chat_id,
                    video=m.video.file_id,
                    caption=header + (m.caption or ""),
                    message_thread_id=thread_id,
                )
            elif m.document:
                sent = await self.bot.send_document(
                    self.admin_chat_id,
                    document=m.document.file_id,
                    caption=header + (m.caption or ""),
                    message_thread_id=thread_id,
                )
            elif m.voice:
                await self.bot.send_message(self.admin_chat_id, header.strip(), message_thread_id=thread_id)
                sent = await self.bot.copy_message(self.admin_chat_id, m.chat.id, m.message_id, message_thread_id=thread_id)
            elif m.sticker:
                await self.bot.send_message(self.admin_chat_id, header.strip(), message_thread_id=thread_id)
                sent = await self.bot.copy_message(self.admin_chat_id, m.chat.id, m.message_id, message_thread_id=thread_id)
            else:
                text = header + (m.text or "")
                sent = await self.bot.send_message(
                    self.admin_chat_id, text,
                    message_thread_id=thread_id,
                    parse_mode="HTML"
                )

            if sent:
                self.msg_map[sent.message_id] = user["id"]

        except TelegramBadRequest as e:
            if "message thread not found" in str(e):
                user["last_topic_id"] = None
                new_tid = await self.resolve_thread(user, force_new=True)
                if new_tid:
                    await self.forward_to_admin(m, user, is_first, btn_text, is_ai_request)
            else:
                logger.error(f"forward_to_admin error: {e}")
        except Exception as e:
            logger.error(f"forward_to_admin error: {e}")

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
            user["last_seen"] = int(time.time())
        return user, is_new

    # ─────────────────────────────────────────────────────────────────────────
    # ЛОГИРОВАНИЕ И СТАТИСТИКА
    # ─────────────────────────────────────────────────────────────────────────

    async def log_and_update(self, uid: int, name: str, text: str, is_admin: bool = False):
        await self.sync_queue.put(("log_message", {
            "bot_id":        self.bot_id,
            "user_id":       uid,
            "first_name":    name,
            "message_text":  text[:950] if text else "[Медиа]",
            "is_from_admin": is_admin,
        }))
        self.stats_data["totalMessages"] = self.stats_data.get("totalMessages", 0) + 1
        key = "outgoingToday" if is_admin else "incomingToday"
        self.stats_data[key] = self.stats_data.get(key, 0) + 1
        if not is_admin:
            for u in self.users_list:
                if u["id"] == uid:
                    u["last_seen"] = int(time.time())
                    u["name"] = name
                    break
        await self.sync_queue.put(("sync_state", None))

    # ─────────────────────────────────────────────────────────────────────────
    # СОХРАНЕНИЕ В БД (прямой патч)
    # ─────────────────────────────────────────────────────────────────────────

    async def _save_to_db(self):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.get(
                    f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                    headers=self.headers
                )
                if res.status_code == 200 and res.json():
                    remote_cfg = res.json()[0].get("config", {}) or {}
                    new_cfg = {
                        **remote_cfg,
                        "connectedUsers": self.users_list,
                        "stats":          self.stats_data,
                    }
                    await client.patch(
                        f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                        json={"config": new_cfg},
                        headers=self.headers
                    )
            await self.sync_queue.put(("sync_state", None))
        except Exception as e:
            logger.error(f"_save_to_db error: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # КОМАНДЫ МОДЕРАЦИИ (полный набор как у pro)
    # ─────────────────────────────────────────────────────────────────────────

    async def admin_control_logic(self, m: Message) -> bool:
        if not m.text or not (m.text.startswith("/") or m.text.startswith("!")):
            return False

        cmd_parts = m.text.split()
        command   = cmd_parts[0][1:].lower()

        # ── STATS ────────────────────────────────────────────────────────────
        if command == "stats":
            total  = len(self.users_list)
            banned = self.stats_data.get("bannedCount", 0)
            bc_day = self._broadcast_today_count()
            await m.reply(
                f"📊 <b>Статистика бота</b> <i>(Free)</i>:\n\n"
                f"👥 Всего пользователей: {total}\n"
                f"🚫 Заблокировано: {banned}\n"
                f"📢 Рассылок сегодня: {bc_day}/{FREE_BROADCAST_DAY}"
            )
            return True

        # ── BROADCAST ─────────────────────────────────────────────────────────
        elif command == "broadcast":
            today_count = self._broadcast_today_count()
            if today_count >= FREE_BROADCAST_DAY:
                await m.reply(
                    f"⛔ <b>Лимит рассылки исчерпан.</b>\n"
                    f"Free-план: {FREE_BROADCAST_DAY} рассылок в день.\n"
                    f"Уже запущено: {today_count}\n\n"
                    f"♻️ Лимит обнуляется в полночь.\n"
                    f"Для снятия ограничений — <b>перейдите на Pro</b>."
                )
                return True

            active_users = [u for u in self.users_list if not u.get("is_banned") and u.get("is_active", True)]

            if not active_users:
                await m.reply("Нет активных пользователей для рассылки.")
                return True

            if m.reply_to_message:
                target_msg_id = m.reply_to_message.message_id
                sent_c, err_c = 0, 0
                status_msg = await m.reply(
                    f"🚀 <b>Запускаю рассылку...</b>\n"
                    f"Получателей: {len(active_users)}\n"
                    f"<i>Free-план: {FREE_BROADCAST_DAY} рассылок/день, использовано {today_count}</i>"
                )
                for user in active_users:
                    try:
                        await self.bot.copy_message(
                            chat_id=int(user["id"]),
                            from_chat_id=m.chat.id,
                            message_id=target_msg_id
                        )
                        sent_c += 1
                        await asyncio.sleep(0.07)
                    except TelegramForbiddenError:
                        user["is_active"] = False
                        err_c += 1
                    except Exception:
                        err_c += 1

                self._broadcast_increment()   # считаем 1 рассылку, а не кол-во получателей
                new_today = self._broadcast_today_count()
                await status_msg.edit_text(
                    f"✅ <b>Рассылка завершена!</b>\n\n"
                    f"👤 Доставлено: {sent_c}\n"
                    f"🚫 Ошибки: {err_c}\n"
                    f"📊 Рассылок сегодня: {new_today}/{FREE_BROADCAST_DAY}"
                )
                await self._save_to_db()
            else:
                self.broadcast_cache[m.from_user.id] = "WAITING"
                remaining = FREE_BROADCAST_DAY - today_count
                await m.reply(
                    f"📢 <b>Режим рассылки</b> <i>(Free: осталось {remaining} из {FREE_BROADCAST_DAY} рассылок)</i>\n"
                    f"Пришлите сообщение (текст/фото/видео) для рассылки."
                )
            return True

        # ── КОМАНДЫ МОДЕРАЦИИ (требуют target_user) ───────────────────────────

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

        # /whois
        if command == "whois":
            uname = target_user.get("username")
            name_line = target_user.get("first_name", "—")
            if uname:
                name_line += f" (@{uname})"
            joined   = datetime.fromtimestamp(target_user.get("joined_at", 0)).strftime("%d.%m.%Y %H:%M") if target_user.get("joined_at") else "—"
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

        # /ban
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

        # /unban
        elif command == "unban":
            target_user["is_banned"] = False
            target_user["warns"] = 0
            self.stats_data["bannedCount"] = max(0, self.stats_data.get("bannedCount", 1) - 1)
            await self._save_to_db()
            try:
                await self.bot.send_message(uid, "✅ <b>Ваш доступ восстановлен.</b>")
            except Exception:
                pass
            await m.reply(f"✅ Пользователь <code>{uid}</code> разблокирован.")
            return True

        # /warn
        elif command == "warn":
            target_user["warns"] = target_user.get("warns", 0) + 1
            if target_user["warns"] >= ban_limit and ban_limit > 0:
                target_user["is_banned"] = True
                self.stats_data["bannedCount"] = self.stats_data.get("bannedCount", 0) + 1
                msg = f"🚨 <b>АВТО-БАН!</b> Юзер <code>{uid}</code>. Варнов: {target_user['warns']}/{ban_limit}"
                notif = f"🚫 <b>Авто-бан:</b> лимит предупреждений ({target_user['warns']}/{ban_limit}) исчерпан."
            else:
                msg  = f"⚠️ Варн выдан <code>{uid}</code>. Всего: {target_user['warns']}/{ban_limit if ban_limit else '∞'}"
                notif = f"⚠️ <b>Предупреждение!</b> ({target_user['warns']}/{ban_limit if ban_limit else '∞'})"
            await self._save_to_db()
            try:
                await self.bot.send_message(uid, notif)
            except Exception:
                pass
            await m.reply(msg)
            return True

        # /unwarn
        elif command == "unwarn":
            target_user["warns"] = max(0, target_user.get("warns", 0) - 1)
            await self._save_to_db()
            await m.reply(f"✅ Варн снят. Теперь у <code>{uid}</code>: {target_user['warns']}")
            return True

        return False

    # ─────────────────────────────────────────────────────────────────────────
    # SYNC WORKER
    # ─────────────────────────────────────────────────────────────────────────

    async def database_sync_worker(self):
        async with httpx.AsyncClient(timeout=10.0) as client:
            hdrs = {**self.headers, "Prefer": "return=minimal"}
            while self.is_running:
                try:
                    item = await asyncio.wait_for(self.sync_queue.get(), timeout=1.0)
                    action, payload = item

                    if action == "log_message":
                        await client.post(
                            f"{self.sb_url}/rest/v1/bot_messages",
                            json=payload, headers=hdrs
                        )

                    elif action == "sync_state":
                        res = await client.get(
                            f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                            headers=hdrs
                        )
                        if res.status_code == 200 and res.json():
                            remote_data = res.json()[0]
                            remote_cfg  = remote_data.get("config", {}) or {}
                            new_cfg = {
                                **remote_cfg,
                                "stats":          self.stats_data,
                                "connectedUsers": self.users_list,
                            }
                            await client.patch(
                                f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                                json={"config": new_cfg}, headers=hdrs
                            )
                            # Обновляем кнопки/триггеры из БД (не затирая users_list)
                            saved_users = self.users_list
                            saved_stats = self.stats_data
                            self.apply_config({"config": remote_cfg})
                            self.users_list  = saved_users
                            self.stats_data  = saved_stats

                    self.sync_queue.task_done()
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Sync Worker error: {e}")
                    try:
                        self.sync_queue.task_done()
                    except Exception:
                        pass

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
                    self.apply_config({**remote, "config": rc})
                    logger.info(
                        f"✅ [{self.bot_id}] Конфиг загружен: "
                        f"кнопок={len(self.buttons)}, триггеров={len(self.triggers)}"
                    )
        except Exception as e:
            logger.error(f"sync_database_logic error: {e}")

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

                history = self.stats_data.get("history", [])
                if not history:
                    history = [{"date": current_date, "incoming": 0, "outgoing": 0,
                                "totalUsers": len(self.users_list), "activeUsers": active_count}]
                    self.stats_data["history"] = history

                if history[-1]["date"] != current_date:
                    history[-1].update({
                        "incoming":    self.stats_data.get("incomingToday", 0),
                        "outgoing":    self.stats_data.get("outgoingToday", 0),
                        "totalUsers":  len(self.users_list),
                        "activeUsers": active_count,
                    })
                    self.stats_data["incomingToday"] = 0
                    self.stats_data["outgoingToday"] = 0
                    history.append({"date": current_date, "incoming": 0, "outgoing": 0,
                                    "totalUsers": len(self.users_list), "activeUsers": active_count})
                    self.stats_data["history"] = history[-14:]

                history[-1].update({
                    "incoming":    self.stats_data.get("incomingToday", 0),
                    "outgoing":    self.stats_data.get("outgoingToday", 0),
                    "totalUsers":  len(self.users_list),
                    "activeUsers": active_count,
                })
                await self.sync_queue.put(("sync_state", None))
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Rotator error: {e}")
                await asyncio.sleep(60)

    # ─────────────────────────────────────────────────────────────────────────
    # HANDLERS SETUP
    # ─────────────────────────────────────────────────────────────────────────

    async def core_handlers_setup(self):
        self.router.message.middleware(BanMiddleware(self))
        self.router.callback_query.middleware(BanMiddleware(self))

        # ── 1. Пользователь заблокировал бота ────────────────────────────────
        @self.router.my_chat_member(
            ChatMemberUpdatedFilter(member_status_changed=ChatMemberStatus.KICKED)
        )
        async def on_user_blocked(event: ChatMemberUpdated):
            uid  = event.from_user.id
            user = next((u for u in self.users_list if u["id"] == uid), None)
            if user:
                user["is_active"] = False
                await self.sync_queue.put(("sync_state", None))
                if self.admin_chat_id:
                    try:
                        await self.bot.send_message(
                            self.admin_chat_id,
                            f"🔴 Пользователь <b>{event.from_user.full_name}</b> заблокировал бота.",
                            message_thread_id=user.get("last_topic_id"),
                        )
                    except Exception:
                        pass

        # ── 2. /start ─────────────────────────────────────────────────────────
        @self.router.message(CommandStart())
        async def handle_start(m: Message):
            user, is_new = await self.get_user_state(m)
            if user.get("is_banned"):
                await m.answer("🚫 <b>Вы заблокированы в этом боте.</b>")
                return

            reply_kb  = self.get_main_keyboard()
            inline_kb = self.build_inline_from_list(self.welcome_inline)

            try:
                if self.welcome_photo:
                    await m.answer_photo(
                        photo=self.welcome_photo,
                        caption=self.welcome_text,
                        reply_markup=inline_kb if inline_kb else reply_kb,
                    )
                else:
                    await m.answer(
                        text=self.welcome_text,
                        reply_markup=inline_kb if inline_kb else reply_kb,
                    )
            except Exception:
                await m.answer(text=self.welcome_text, reply_markup=reply_kb)

            # FREE: показываем рекламу после welcome
            await self.send_ad_to_user(m)

            await self.log_and_update(user["id"], m.from_user.full_name, "/start")

        # ── 3. Сообщения от АДМИНА ────────────────────────────────────────────
        @self.router.message(F.chat.id == self.admin_chat_id)
        async def admin_input(m: Message):
            # Команды (/, !)
            if m.text and (m.text.startswith("/") or m.text.startswith("!")):
                await self.admin_control_logic(m)
                return

            # Режим ожидания рассылки (после /broadcast без реплая)
            if self.broadcast_cache.get(m.from_user.id) == "WAITING":
                del self.broadcast_cache[m.from_user.id]
                today_count = self._broadcast_today_count()
                if today_count >= FREE_BROADCAST_DAY:
                    await m.reply(
                        f"⛔ Лимит рассылки исчерпан ({FREE_BROADCAST_DAY} рассылок/день).\n"
                        f"Обновится в полночь."
                    )
                    return

                active_users = [u for u in self.users_list if not u.get("is_banned") and u.get("is_active", True)]

                if not active_users:
                    await m.reply("Нет активных пользователей.")
                    return

                sent_c, err_c = 0, 0
                status_msg = await m.reply(
                    f"🚀 Рассылаю {len(active_users)} получателям…\n"
                    f"<i>(Free-план: {FREE_BROADCAST_DAY} рассылок/день, использовано {today_count})</i>"
                )
                for user in active_users:
                    try:
                        await self.bot.copy_message(
                            chat_id=int(user["id"]),
                            from_chat_id=m.chat.id,
                            message_id=m.message_id
                        )
                        sent_c += 1
                        await asyncio.sleep(0.07)
                    except TelegramForbiddenError:
                        user["is_active"] = False
                        err_c += 1
                    except Exception:
                        err_c += 1

                self._broadcast_increment()   # +1 рассылка
                new_today = self._broadcast_today_count()
                await status_msg.edit_text(
                    f"✅ <b>Рассылка завершена!</b>\n\n"
                    f"👤 Доставлено: {sent_c}\n"
                    f"🚫 Ошибки: {err_c}\n"
                    f"📊 Рассылок сегодня: {new_today}/{FREE_BROADCAST_DAY}"
                )
                await self._save_to_db()
                return

            # Ответ пользователю (через реплай или топик)
            target_id = None
            if m.message_thread_id:
                u = next((u for u in self.users_list if u.get("last_topic_id") == m.message_thread_id), None)
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

        # ── 4. Закрытие тикета inline ─────────────────────────────────────────
        @self.router.callback_query(lambda c: c.data == "ticket_close")
        async def on_ticket_close(cb: CallbackQuery):
            uid_cb = cb.from_user.id
            user_cb = next((u for u in self.users_list if u["id"] == uid_cb), None)
            if user_cb:
                user_cb.pop("_in_ticket", None)
                await self.sync_queue.put(("sync_state", None))
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
                    uid_cb,
                    "<b>Обращение закрыто.</b>",
                    reply_markup=self.get_main_keyboard()
                )
            except Exception:
                pass

        # ── 5. Сообщения от пользователей ────────────────────────────────────
        @self.router.message()
        async def user_input(m: Message):
            if self.admin_chat_id and m.chat.id == self.admin_chat_id:
                return

            user, is_new = await self.get_user_state(m)
            if user.get("is_banned"):
                await m.answer("🚫 <b>Вы заблокированы в этом боте.</b>")
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
                                    from aiogram.types import (
                                        InputMediaPhoto, InputMediaVideo,
                                        InputMediaDocument, InputMediaAudio
                                    )
                                    items = []
                                    for i, msg in enumerate(buf["messages"]):
                                        cap = (header if i == 0 else "") + (msg.caption or "")
                                        if msg.photo:
                                            items.append(InputMediaPhoto(media=msg.photo[-1].file_id, caption=cap or None, parse_mode="HTML"))
                                        elif msg.video:
                                            items.append(InputMediaVideo(media=msg.video.file_id, caption=cap or None, parse_mode="HTML"))
                                        elif msg.document:
                                            items.append(InputMediaDocument(media=msg.document.file_id, caption=cap or None, parse_mode="HTML"))
                                    if items:
                                        tid = buf["user"].get("last_topic_id")
                                        await self.bot.send_media_group(self.admin_chat_id, items, message_thread_id=tid)
                                except Exception as e:
                                    logger.error(f"MediaGroup flush error: {e}")
                            await self.log_and_update(buf["user"]["id"], first_m.from_user.full_name, "[МедиаГруппа]")
                    asyncio.create_task(_flush())
                self.media_group_buffer[gid]["messages"].append(m)
                return

            # Антиспам
            if await self.check_antispam(uid):
                return

            # Режим активного тикета
            if user.get("_in_ticket"):
                close_label = user.get("_ticket_close_label", "Закрыть обращение")
                if m.text and m.text.strip() in (close_label, "Закрыть обращение"):
                    user.pop("_in_ticket", None)
                    user.pop("_ticket_close_label", None)
                    await self.sync_queue.put(("sync_state", None))
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
                await self.forward_to_admin(m, user)
                await self.log_and_update(uid, m.from_user.full_name, m.text or "[Медиа]")
                return

            if m.text:
                clean = m.text.strip()
                lower = clean.lower()

                # Кнопка "Назад"
                if clean in ("⬅️ Назад", "Назад"):
                    await m.answer("Главное меню:", reply_markup=self.get_main_keyboard())
                    return

                # Кнопки меню
                matched_btn = next(
                    (b for b in self.buttons if b.get("text", "").lower() == lower), None
                )
                if matched_btn:
                    btn_type = matched_btn.get("type", "default")

                    if btn_type == "ticket":
                        # Тикетная кнопка: открываем тикет
                        user["_in_ticket"] = True
                        user["_ticket_close_label"] = "Закрыть обращение"
                        await self.forward_to_admin(m, user, btn_text=matched_btn["text"])
                        resp  = matched_btn.get("response", "Ваше обращение принято. Ожидайте ответа оператора.")
                        close_kb = ReplyKeyboardMarkup(
                            keyboard=[[KeyboardButton(text="Закрыть обращение")]],
                            resize_keyboard=True
                        )
                        await m.answer(
                            f"{resp}\n\nВы можете продолжать писать — сообщения будут доставлены оператору.",
                            reply_markup=close_kb
                        )
                    else:
                        # Обычная кнопка
                        resp = matched_btn.get("response", "")
                        inline_links = matched_btn.get("inline", [])
                        inline_kb = self.build_inline_from_list(inline_links)
                        await m.answer(
                            resp or "✅",
                            reply_markup=inline_kb if inline_kb else self.get_main_keyboard()
                        )

                    await self.log_and_update(uid, m.from_user.full_name, f"КНОПКА: {matched_btn['text']}")
                    return

                # Триггеры
                for trig in self.triggers:
                    if trig.get("keyword") and trig["keyword"].lower() in lower:
                        await m.answer(trig.get("response") or "")
                        await self.log_and_update(uid, m.from_user.full_name, f"ТРИГГЕР: {trig['keyword']}")
                        return

            # Форвард первого обращения / режим forward_all
            if is_new:
                await self.forward_to_admin(m, user, is_first=True)
                await self.log_and_update(uid, m.from_user.full_name, m.text or "[Медиа]")
            elif self.forward_all:
                await self.forward_to_admin(m, user)
                await self.log_and_update(uid, m.from_user.full_name, m.text or "[Медиа]")
            else:
                await m.answer(
                    "Пожалуйста, воспользуйтесь меню или нажмите кнопку для открытия обращения.",
                    reply_markup=self.get_main_keyboard()
                )

    # ─────────────────────────────────────────────────────────────────────────
    # ЗАПУСК
    # ─────────────────────────────────────────────────────────────────────────

    async def run_instance(self):
        logger.info(f"[FREE] Бот {self.bot_id} стартует...")

        # Начальная загрузка конфига
        await self.sync_database_logic()

        # Фоновые задачи
        asyncio.create_task(self.database_sync_worker())
        asyncio.create_task(self.daily_stats_rotator())
        asyncio.create_task(self._memory_watchdog())

        # Handlers
        await self.core_handlers_setup()
        self.dp.include_router(self.router)

        logger.info(
            f"[FREE] Бот {self.bot_id} готов. "
            f"Кнопок: {len(self.buttons)}/{FREE_MAX_BUTTONS}, "
            f"Триггеров: {len(self.triggers)}/{FREE_MAX_TRIGGERS}, "
            f"Реклама: {'вкл' if self.ad_enabled else 'выкл'}, "
            f"Память: {self.memory_limit_mb} МБ"
        )

        try:
            await self.dp.start_polling(self.bot)
        finally:
            self.is_running = False
            await self.bot.session.close()


# ════════════════════════════════════════════════════════════════════════════════
# ТОЧКА ВХОДА
# ════════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 2:
        # PM2 запустил free_bot_core.py напрямую без конфига.
        # Это нормально — просто ждём, не выходим с кодом 1
        # (иначе PM2 будет бесконечно перезапускать).
        # Настоящий запуск всегда идёт от server.py с аргументом cfg_path.
        print("INFO: free_bot_core.py is a worker script. "
              "It should be started by server.py with a config path argument.\n"
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
