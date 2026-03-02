"""
free_bot_core.py — BotEngine Free Plan v5
==========================================
ИСПРАВЛЕНО:
  1. Единый @router.message() — нет lambda-фильтра, admin_id проверяется внутри
  2. Кнопки и триггеры — ПЕРВЫМИ, до любого forwardAll
  3. После одной команды бот не зависает — bc_wait чистится через .pop()
  4. Счётчик рассылок персистентен: читается из БД при старте, пишется в БД после каждой
  5. /stats, /whois, /ban, /unban, /warn, /unwarn — всё работает
  6. Заголовки сообщений берутся из settings (firstMessageHeader и т.д.)
  7. Топики: useTopics, topicPerRequest, anonymousTopics — применяются
  8. Рассылка: copy_message — любой тип медиа (стикеры, голосовые, фото и т.д.)
  9. push_state: дебаунс 5 сек + принудительный после важных операций
 10. config_sync_loop каждые 30 сек — только настройки, не трогает users/stats
 11. Нет лимита памяти, ботов, кнопок, триггеров
 12. drop_pending_updates при старте
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
from typing import Dict, Optional, Any, Callable

from aiogram import Bot, Dispatcher, Router, BaseMiddleware
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.filters import CommandStart, ChatMemberUpdatedFilter
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
    ReplyKeyboardRemove, ChatMemberUpdated,
)
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("FreeBotCore")


# ═══════════════════════════════════════════════════════════
# MIDDLEWARE
# ═══════════════════════════════════════════════════════════

class BanMiddleware(BaseMiddleware):
    def __init__(self, inst):
        self.inst = inst
        super().__init__()

    async def __call__(self, handler: Callable, event: Any, data: Dict) -> Any:
        fu = getattr(event, "from_user", None)
        if fu:
            u = next((x for x in self.inst.users if x.get("id") == fu.id), None)
            if u and u.get("is_banned"):
                try:
                    if isinstance(event, Message):
                        await event.answer("🚫 <b>Вы заблокированы в этом боте.</b>")
                    elif isinstance(event, CallbackQuery):
                        await event.answer("🚫 Вы заблокированы.", show_alert=True)
                except Exception:
                    pass
                return
        return await handler(event, data)


# ═══════════════════════════════════════════════════════════
# ХЕЛПЕРЫ
# ═══════════════════════════════════════════════════════════

def anon_id(uid: int) -> str:
    return hashlib.md5(str(uid).encode()).hexdigest()[:6].upper()


def build_header(m: Message, stg: dict, is_first: bool = False, btn_text: str = "") -> str:
    uid     = m.from_user.id
    is_anon = stg.get("anonymousTopics", False)

    if is_anon:
        user_info = f"👤 <b>Аноним #{anon_id(uid)}</b>"
    else:
        parts = []
        if stg.get("showHeaderName", True) and m.from_user.full_name:
            parts.append(f"<b>{m.from_user.full_name}</b>")
        if stg.get("showHeaderUsername", True) and m.from_user.username:
            parts.append(f"(@{m.from_user.username})")
        if stg.get("showHeaderId", True):
            parts.append(f"ID: <code>{uid}</code>")
        user_info = " | ".join(parts) if parts else f"ID: <code>{uid}</code>"

    if btn_text:
        hdr = stg.get("ticketMessageHeader", "🆘 <b>ЗАЯВКА:</b>")
        hdr = hdr.replace("{btn}", btn_text) if "{btn}" in hdr else hdr.rstrip(":") + f" [{btn_text}]:"
    elif is_first:
        hdr = stg.get("firstMessageHeader", "🆕 <b>ПЕРВОЕ ОБРАЩЕНИЕ:</b>")
    else:
        hdr = stg.get("commonMessageHeader", "📩 <b>СООБЩЕНИЕ:</b>")

    return f"{hdr}\n{user_info}\n\n"


# ═══════════════════════════════════════════════════════════
# ОСНОВНОЙ КЛАСС
# ═══════════════════════════════════════════════════════════

class FreeBotInstance:

    def __init__(self, raw_config: dict):
        self.bot_id = raw_config.get("id")
        self.token  = raw_config.get("token")

        self.sb_url  = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.sb_key  = os.getenv("SUPABASE_KEY", "")
        self.sb_hdrs = {
            "apikey":        self.sb_key,
            "Authorization": f"Bearer {self.sb_key}",
            "Content-Type":  "application/json",
        }
        self.server_url = os.getenv("SERVER_BASE_URL", "http://localhost:8000")

        self.tg     = Bot(token=self.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp     = Dispatcher()
        self.router = Router()

        # Runtime — не сбрасываются при reload конфига
        self.msg_map: Dict[int, int]  = {}   # admin_msg_id → user_id
        self.flood:   Dict[int, float] = {}
        self.bc_wait: Dict[int, bool]  = {}  # admin_id → ждёт сообщение для рассылки
        self.mg_buf:  Dict[str, dict]  = {}  # media group buffer

        self._last_push: float = 0.0
        self.is_running: bool  = True

        # Данные бота
        self.users: list = []
        self.stats: dict = {}
        self.stg:   dict = {}

        # Настройки
        self.admin_id:      Optional[int] = None
        self.use_topics:    bool  = False
        self.topic_per_req: bool  = False
        self.forward_all:   bool  = False
        self.fwd_native:    bool  = False
        self.rate_limit:    float = 1.0
        self.ban_thr:       int   = 3
        self.buttons:       list  = []
        self.triggers:      list  = []
        self.welcome:       str   = "Здравствуйте!"
        self.welcome_photo: str   = ""
        self.welcome_inline: list = []
        self.ad_enabled:    bool  = True

        # Счётчик рассылок (персистентный через stats)
        self._bc_today_count: int = 0
        self._bc_today_date:  str = ""

        self._apply_config(raw_config)

    # ─────────────────────────────────────────────────────
    # КОНФИГ
    # ─────────────────────────────────────────────────────

    def _apply_config(self, raw: dict):
        cfg = raw.get("config") or {}
        if isinstance(cfg, str):
            try:    cfg = json.loads(cfg)
            except: cfg = {}
        full = {**raw, **cfg}

        admin_raw = full.get("adminChatId") or full.get("admin_chat_id")
        if admin_raw:
            try: self.admin_id = int(str(admin_raw).strip())
            except ValueError: pass

        stg = full.get("settings") or {}
        self.stg           = stg
        self.use_topics    = bool(stg.get("useTopics", False))
        self.topic_per_req = bool(stg.get("topicPerRequest", False))
        self.forward_all   = bool(stg.get("forwardAll", False))
        self.fwd_native    = bool(stg.get("forwardMessages", False))
        self.rate_limit    = float(stg.get("rateLimit", 1.0))
        self.ban_thr       = int(stg.get("autoBanThreshold", 3))

        self.buttons        = list(full.get("buttons", []) or [])
        self.triggers       = list(full.get("triggers", []) or [])
        self.welcome        = full.get("welcomeMessage", "Здравствуйте!") or "Здравствуйте!"
        self.welcome_photo  = full.get("welcomePhoto", "") or ""
        self.welcome_inline = list(full.get("welcomeInline", []) or [])
        self.ad_enabled     = bool(raw.get("ad_enabled", True))

        if not self.users:
            self.users = list(full.get("connectedUsers") or [])

        if not self.stats:
            s = full.get("stats") or {}
            self.stats = {
                "totalMessages":   int(s.get("totalMessages", 0)),
                "incomingToday":   int(s.get("incomingToday", 0)),
                "outgoingToday":   int(s.get("outgoingToday", 0)),
                "bannedCount":     int(s.get("bannedCount", 0)),
                "activeUsers24h":  int(s.get("activeUsers24h", 0)),
                "broadcastsToday": int(s.get("broadcastsToday", 0)),
                "broadcastsTotal": int(s.get("broadcastsTotal", 0)),
                "history":         list(s.get("history") or []),
            }
            # Восстанавливаем счётчик рассылок из stats (персистентность)
            today = datetime.now().strftime("%d.%m")
            self._bc_today_date  = today
            self._bc_today_count = int(s.get("broadcastsToday", 0))

    def _reload_settings(self, cfg: dict):
        """Обновляет только настройки. НЕ трогает users и stats."""
        stg = cfg.get("settings") or {}
        self.stg           = stg
        self.use_topics    = bool(stg.get("useTopics", False))
        self.topic_per_req = bool(stg.get("topicPerRequest", False))
        self.forward_all   = bool(stg.get("forwardAll", False))
        self.fwd_native    = bool(stg.get("forwardMessages", False))
        self.rate_limit    = float(stg.get("rateLimit", 1.0))
        self.ban_thr       = int(stg.get("autoBanThreshold", 3))

        if "buttons"       in cfg: self.buttons        = list(cfg["buttons"] or [])
        if "triggers"      in cfg: self.triggers       = list(cfg["triggers"] or [])
        if "welcomeMessage" in cfg: self.welcome       = cfg["welcomeMessage"] or "Здравствуйте!"
        if "welcomePhoto"  in cfg: self.welcome_photo  = cfg["welcomePhoto"] or ""
        if "welcomeInline" in cfg: self.welcome_inline = list(cfg["welcomeInline"] or [])

        admin_raw = cfg.get("adminChatId") or cfg.get("admin_chat_id")
        if admin_raw:
            try: self.admin_id = int(str(admin_raw).strip())
            except ValueError: pass

    # ─────────────────────────────────────────────────────
    # РЕКЛАМА
    # ─────────────────────────────────────────────────────

    async def get_ad(self) -> Optional[dict]:
        if not self.ad_enabled:
            return None
        try:
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.get(
                    f"{self.server_url}/api/ads/active",
                    params={"bot_id": self.bot_id},
                )
                if r.status_code == 200:
                    return r.json().get("ad")
        except Exception:
            pass
        return None

    # ─────────────────────────────────────────────────────
    # КЛАВИАТУРЫ
    # ─────────────────────────────────────────────────────

    def kb_reply(self):
        active = [b for b in self.buttons if b.get("text")]
        if not active:
            return ReplyKeyboardRemove()
        rows = []
        for i in range(0, len(active), 2):
            rows.append([KeyboardButton(text=b["text"]) for b in active[i:i+2]])
        return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

    def kb_inline(self, btns: list) -> Optional[InlineKeyboardMarkup]:
        if not btns:
            return None
        rows = []
        for i in range(0, len(btns), 2):
            row = [
                InlineKeyboardButton(text=b["text"], url=b.get("url", "https://t.me"))
                for b in btns[i:i+2] if b.get("text")
            ]
            if row:
                rows.append(row)
        return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None

    # ─────────────────────────────────────────────────────
    # ТОПИКИ
    # ─────────────────────────────────────────────────────

    async def get_thread(self, user: dict, force_new: bool = False) -> Optional[int]:
        if not self.use_topics or not self.admin_id:
            return None
        existing = user.get("last_topic_id")
        if existing and not force_new:
            return existing
        try:
            name  = user.get("first_name", "User")
            uname = user.get("username")
            title = name + (f" @{uname}" if uname else f" #{user['id']}")
            t = await self.tg.create_forum_topic(self.admin_id, title[:128])
            user["last_topic_id"] = t.message_thread_id
            return t.message_thread_id
        except Exception as e:
            log.warning(f"get_thread: {e}")
            return None

    # ─────────────────────────────────────────────────────
    # ПЕРЕСЫЛКА К АДМИНУ
    # ─────────────────────────────────────────────────────

    async def forward_to_admin(self, m: Message, user: dict,
                               is_first: bool = False, btn_text: str = ""):
        if not self.admin_id:
            return

        force = self.topic_per_req and (btn_text or is_first)
        tid   = await self.get_thread(user, force_new=force)

        # Нативный forward (без заголовка)
        if self.fwd_native and not btn_text and not is_first:
            try:
                sent = await self.tg.forward_message(
                    self.admin_id, m.chat.id, m.message_id, message_thread_id=tid)
                if sent:
                    self.msg_map[sent.message_id] = user["id"]
            except TelegramBadRequest as e:
                if "thread" in str(e).lower():
                    user["last_topic_id"] = None
                    tid2 = await self.get_thread(user, force_new=True)
                    try:
                        sent = await self.tg.forward_message(
                            self.admin_id, m.chat.id, m.message_id, message_thread_id=tid2)
                        if sent:
                            self.msg_map[sent.message_id] = user["id"]
                    except Exception:
                        pass
                else:
                    log.error(f"fwd_native: {e}")
            except Exception as e:
                log.error(f"fwd_native: {e}")
            return

        # copy_message с заголовком
        header = build_header(m, self.stg, is_first, btn_text)

        async def _send():
            nonlocal tid
            sent = None
            try:
                if m.photo:
                    sent = await self.tg.send_photo(
                        self.admin_id, m.photo[-1].file_id,
                        caption=(header + (m.caption or ""))[:1024],
                        message_thread_id=tid)
                elif m.video:
                    sent = await self.tg.send_video(
                        self.admin_id, m.video.file_id,
                        caption=(header + (m.caption or ""))[:1024],
                        message_thread_id=tid)
                elif m.document:
                    sent = await self.tg.send_document(
                        self.admin_id, m.document.file_id,
                        caption=(header + (m.caption or ""))[:1024],
                        message_thread_id=tid)
                elif m.sticker or m.voice or m.video_note or m.audio:
                    await self.tg.send_message(
                        self.admin_id, header.strip(),
                        message_thread_id=tid, parse_mode="HTML")
                    sent = await self.tg.copy_message(
                        self.admin_id, m.chat.id, m.message_id, message_thread_id=tid)
                else:
                    txt  = (header + (m.text or ""))[:4096]
                    sent = await self.tg.send_message(
                        self.admin_id, txt,
                        message_thread_id=tid, parse_mode="HTML")
                if sent:
                    self.msg_map[sent.message_id] = user["id"]
            except TelegramBadRequest as e:
                if "thread" in str(e).lower():
                    user["last_topic_id"] = None
                    tid = await self.get_thread(user, force_new=True)
                    try:
                        txt  = (header + (m.text or ""))[:4096]
                        sent = await self.tg.send_message(
                            self.admin_id, txt, parse_mode="HTML")
                        if sent:
                            self.msg_map[sent.message_id] = user["id"]
                    except Exception:
                        pass
                else:
                    log.error(f"fwd_copy TelegramBadRequest: {e}")
            except Exception as e:
                log.error(f"fwd_copy: {e}")

        await _send()

    # ─────────────────────────────────────────────────────
    # ПОЛЬЗОВАТЕЛЬ
    # ─────────────────────────────────────────────────────

    def get_or_create_user(self, m: Message):
        uid  = m.from_user.id
        user = next((u for u in self.users if u["id"] == uid), None)
        is_new = False
        if not user:
            user = {
                "id":         uid,
                "first_name": m.from_user.first_name or "",
                "username":   m.from_user.username   or "",
                "joined_at":  int(time.time()),
                "last_seen":  int(time.time()),
                "is_banned":  False,
                "warns":      0,
                "is_active":  True,
            }
            self.users.append(user)
            is_new = True
        else:
            user["last_seen"]  = int(time.time())
            user["first_name"] = m.from_user.first_name or user.get("first_name", "")
            user["username"]   = m.from_user.username   or user.get("username", "")
        return user, is_new

    async def check_flood(self, uid: int) -> bool:
        if self.rate_limit <= 0:
            return False
        now = time.time()
        if now - self.flood.get(uid, 0) < self.rate_limit:
            return True
        self.flood[uid] = now
        return False

    # ─────────────────────────────────────────────────────
    # СТАТИСТИКА
    # ─────────────────────────────────────────────────────

    async def log_msg(self, uid: int, name: str, text: str, is_admin: bool = False):
        self.stats["totalMessages"] = self.stats.get("totalMessages", 0) + 1
        key = "outgoingToday" if is_admin else "incomingToday"
        self.stats[key] = self.stats.get(key, 0) + 1
        if not is_admin:
            for u in self.users:
                if u["id"] == uid:
                    u["last_seen"]  = int(time.time())
                    u["first_name"] = name
                    break
        asyncio.create_task(self._write_log(uid, name, text, is_admin))
        asyncio.create_task(self._push_state())

    async def _write_log(self, uid: int, name: str, text: str, is_admin: bool):
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                await c.post(
                    f"{self.sb_url}/rest/v1/bot_messages",
                    json={
                        "bot_id":        self.bot_id,
                        "user_id":       uid,
                        "first_name":    name,
                        "message_text":  (text or "")[:950],
                        "is_from_admin": is_admin,
                    },
                    headers={**self.sb_hdrs, "Prefer": "return=minimal"},
                )
        except Exception:
            pass

    # ─────────────────────────────────────────────────────
    # БД
    # ─────────────────────────────────────────────────────

    async def _push_state(self):
        """Дебаунс 5 сек."""
        now = time.time()
        if now - self._last_push < 5.0:
            return
        self._last_push = now
        await self._do_push()

    async def _push_force(self):
        """Без дебаунса — для важных операций (бан, рассылка и т.д.)."""
        self._last_push = 0.0
        await self._do_push()

    async def _do_push(self):
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(
                    f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}&select=config",
                    headers=self.sb_hdrs)
                if r.status_code != 200 or not r.json():
                    log.warning(f"_do_push: не нашёл бота {self.bot_id}")
                    return
                old_cfg = r.json()[0].get("config") or {}
                new_cfg = {**old_cfg, "connectedUsers": self.users, "stats": self.stats}
                pr = await c.patch(
                    f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                    json={"config": new_cfg},
                    headers={**self.sb_hdrs, "Prefer": "return=minimal"})
                if pr.status_code not in (200, 204):
                    log.warning(f"_do_push patch: {pr.status_code} {pr.text[:200]}")
        except Exception as e:
            log.error(f"_do_push: {e}")

    # ─────────────────────────────────────────────────────
    # РАССЫЛКА
    # ─────────────────────────────────────────────────────

    def _bc_get_today(self) -> int:
        today = datetime.now().strftime("%d.%m")
        if self._bc_today_date != today:
            self._bc_today_date  = today
            self._bc_today_count = 0
            self.stats["broadcastsToday"] = 0
        return self._bc_today_count

    def _bc_increment(self):
        today = datetime.now().strftime("%d.%m")
        if self._bc_today_date != today:
            self._bc_today_date  = today
            self._bc_today_count = 0
        self._bc_today_count += 1
        self.stats["broadcastsToday"] = self._bc_today_count
        self.stats["broadcastsTotal"] = self.stats.get("broadcastsTotal", 0) + 1
        hist = self.stats.get("history", [])
        if hist and hist[-1].get("date") == today:
            hist[-1]["broadcasts"] = hist[-1].get("broadcasts", 0) + 1

    async def do_broadcast(self, m: Message, active_users: list, src_msg_id: int):
        sent_c = err_c = 0
        status = await m.reply(
            f"🚀 <b>Рассылаю {len(active_users)} получателям...</b>")
        for user in active_users:
            try:
                await self.tg.copy_message(
                    chat_id=int(user["id"]),
                    from_chat_id=m.chat.id,
                    message_id=src_msg_id)
                sent_c += 1
                await asyncio.sleep(0.05)
            except TelegramForbiddenError:
                user["is_active"] = False
                err_c += 1
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
                try:
                    await self.tg.copy_message(int(user["id"]), m.chat.id, src_msg_id)
                    sent_c += 1
                except Exception:
                    err_c += 1
            except Exception as e:
                log.debug(f"bc send {user['id']}: {e}")
                err_c += 1

        self._bc_increment()
        # Сохраняем счётчик в БД сразу после рассылки
        await self._push_force()

        try:
            await status.edit_text(
                f"✅ <b>Рассылка завершена!</b>\n\n"
                f"👤 Доставлено: <b>{sent_c}</b>\n"
                f"🚫 Ошибок: <b>{err_c}</b>\n"
                f"📊 Рассылок сегодня: <b>{self._bc_get_today()}</b>")
        except Exception:
            pass

    # ─────────────────────────────────────────────────────
    # КОМАНДЫ АДМИНИСТРАТОРА
    # ─────────────────────────────────────────────────────

    async def handle_admin_cmd(self, m: Message) -> bool:
        if not m.text:
            return False
        txt = m.text.strip()
        if not (txt.startswith("/") or txt.startswith("!")):
            return False

        parts = txt.split()
        cmd   = parts[0][1:].lower()

        if cmd == "start":
            return True  # игнорируем /start в admin chat

        # /stats
        if cmd == "stats":
            total  = len(self.users)
            banned = sum(1 for u in self.users if u.get("is_banned"))
            active = sum(1 for u in self.users if u.get("is_active", True) and not u.get("is_banned"))
            await m.reply(
                f"📊 <b>Статистика бота</b>\n\n"
                f"👥 Всего: <b>{total}</b>\n"
                f"✅ Активных: <b>{active}</b>\n"
                f"🚫 Забанено: <b>{banned}</b>\n"
                f"📨 Сообщений всего: <b>{self.stats.get('totalMessages', 0)}</b>\n"
                f"📢 Рассылок сегодня: <b>{self._bc_get_today()}</b>\n"
                f"📢 Рассылок всего: <b>{self.stats.get('broadcastsTotal', 0)}</b>")
            return True

        # /broadcast
        if cmd == "broadcast":
            actives = [u for u in self.users if not u.get("is_banned") and u.get("is_active", True)]
            if not actives:
                await m.reply("Нет активных пользователей.")
                return True
            if m.reply_to_message:
                await self.do_broadcast(m, actives, m.reply_to_message.message_id)
            else:
                self.bc_wait[m.from_user.id] = True
                await m.reply(
                    "📢 <b>Режим рассылки включён</b>\n\n"
                    "Следующим сообщением отправьте то, что нужно разослать.\n"
                    "Поддерживается любой тип: текст, фото, видео, стикер, голосовое, документ.")
            return True

        # Команды с target_user
        target = None
        if m.message_thread_id:
            target = next(
                (u for u in self.users if u.get("last_topic_id") == m.message_thread_id), None)
        if not target and m.reply_to_message:
            mapped = self.msg_map.get(m.reply_to_message.message_id)
            if mapped:
                target = next((u for u in self.users if int(u["id"]) == int(mapped)), None)
        if not target and len(parts) > 1:
            try:
                did = int(parts[1])
                target = next((u for u in self.users if int(u["id"]) == did), None)
                if not target and cmd in ("ban", "unban"):
                    target = {
                        "id": did, "first_name": f"User#{did}", "username": None,
                        "is_banned": False, "warns": 0, "is_active": True,
                        "joined_at": int(time.time()), "last_seen": int(time.time()),
                    }
                    self.users.append(target)
                elif not target:
                    await m.reply(f"Пользователь <code>{did}</code> не найден.")
                    return True
            except ValueError:
                pass

        if not target:
            return False

        uid = target["id"]

        if cmd == "whois":
            un   = target.get("username")
            name = target.get("first_name", "—") + (f" (@{un})" if un else "")
            jt   = (datetime.fromtimestamp(target["joined_at"]).strftime("%d.%m.%Y %H:%M")
                    if target.get("joined_at") else "—")
            ls   = (datetime.fromtimestamp(target["last_seen"]).strftime("%d.%m.%Y %H:%M")
                    if target.get("last_seen") else "—")
            await m.reply(
                f"🔍 <b>Пользователь</b> <code>{uid}</code>\n\n"
                f"👤 {name}\n"
                f"🚫 Забанен: {'Да' if target.get('is_banned') else 'Нет'}\n"
                f"⚠️ Варнов: {target.get('warns', 0)}/{self.ban_thr or '∞'}\n"
                f"✅ Активен: {'Да' if target.get('is_active', True) else 'Нет'}\n"
                f"📅 Зашёл: {jt}\n"
                f"🕐 Последний раз: {ls}")
            return True

        if cmd == "ban":
            target["is_banned"] = True
            self.stats["bannedCount"] = self.stats.get("bannedCount", 0) + 1
            await self._push_force()
            try: await self.tg.send_message(uid, "🚫 <b>Доступ к боту ограничен администратором.</b>")
            except Exception: pass
            await m.reply(f"✅ <code>{uid}</code> заблокирован.")
            return True

        if cmd == "unban":
            target["is_banned"] = False
            target["warns"]     = 0
            self.stats["bannedCount"] = max(0, self.stats.get("bannedCount", 1) - 1)
            await self._push_force()
            try: await self.tg.send_message(uid, "✅ <b>Ваш доступ восстановлен.</b>")
            except Exception: pass
            await m.reply(f"✅ <code>{uid}</code> разблокирован.")
            return True

        if cmd == "warn":
            target["warns"] = target.get("warns", 0) + 1
            if self.ban_thr > 0 and target["warns"] >= self.ban_thr:
                target["is_banned"] = True
                self.stats["bannedCount"] = self.stats.get("bannedCount", 0) + 1
                msg   = f"🚨 <b>АВТО-БАН</b> <code>{uid}</code>. Варнов: {target['warns']}/{self.ban_thr}"
                notif = f"🚫 Авто-бан: лимит предупреждений ({target['warns']}/{self.ban_thr}) исчерпан."
            else:
                msg   = f"⚠️ Варн <code>{uid}</code>. Всего: {target['warns']}/{self.ban_thr or '∞'}"
                notif = f"⚠️ Предупреждение! ({target['warns']}/{self.ban_thr or '∞'})"
            await self._push_force()
            try: await self.tg.send_message(uid, notif)
            except Exception: pass
            await m.reply(msg)
            return True

        if cmd == "unwarn":
            target["warns"] = max(0, target.get("warns", 0) - 1)
            await self._push_force()
            await m.reply(f"✅ Варн снят. У <code>{uid}</code>: {target['warns']}")
            return True

        return False

    # ─────────────────────────────────────────────────────
    # ФОНОВЫЕ ЗАДАЧИ
    # ─────────────────────────────────────────────────────

    async def config_sync_loop(self):
        await asyncio.sleep(30)
        while self.is_running:
            try:
                async with httpx.AsyncClient(timeout=8) as c:
                    r = await c.get(
                        f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}&select=config",
                        headers=self.sb_hdrs)
                    if r.status_code == 200 and r.json():
                        cfg = r.json()[0].get("config") or {}
                        self._reload_settings(cfg)
                        log.debug(
                            f"[{self.bot_id}] synced: btns={len(self.buttons)} "
                            f"trgs={len(self.triggers)} topics={self.use_topics} "
                            f"fwdAll={self.forward_all} admin={self.admin_id}")
            except Exception as e:
                log.error(f"config_sync_loop: {e}")
            await asyncio.sleep(30)

    async def stats_rotator(self):
        while self.is_running:
            try:
                now   = datetime.now()
                today = now.strftime("%d.%m")
                ago24 = int((now - timedelta(days=1)).timestamp())
                active = sum(1 for u in self.users if u.get("last_seen", 0) > ago24)
                self.stats["activeUsers24h"] = active

                hist = self.stats.setdefault("history", [])
                if not hist:
                    hist.append({
                        "date": today, "incoming": 0, "outgoing": 0,
                        "totalUsers": len(self.users), "activeUsers": active, "broadcasts": 0})

                if hist[-1].get("date") != today:
                    hist[-1].update({
                        "incoming":    self.stats.get("incomingToday", 0),
                        "outgoing":    self.stats.get("outgoingToday", 0),
                        "totalUsers":  len(self.users),
                        "activeUsers": active,
                    })
                    self.stats["incomingToday"]   = 0
                    self.stats["outgoingToday"]   = 0
                    self.stats["broadcastsToday"] = 0
                    self._bc_today_count = 0
                    self._bc_today_date  = today
                    hist.append({
                        "date": today, "incoming": 0, "outgoing": 0,
                        "totalUsers": len(self.users), "activeUsers": active, "broadcasts": 0})
                    self.stats["history"] = hist[-14:]

                hist[-1].update({
                    "incoming":    self.stats.get("incomingToday", 0),
                    "outgoing":    self.stats.get("outgoingToday", 0),
                    "totalUsers":  len(self.users),
                    "activeUsers": active,
                })
                await self._push_force()
            except Exception as e:
                log.error(f"stats_rotator: {e}")
            await asyncio.sleep(60)

    # ─────────────────────────────────────────────────────
    # HANDLERS
    # ─────────────────────────────────────────────────────

    async def setup_handlers(self):
        self.router.message.middleware(BanMiddleware(self))
        self.router.callback_query.middleware(BanMiddleware(self))

        @self.router.my_chat_member(
            ChatMemberUpdatedFilter(member_status_changed=ChatMemberStatus.KICKED))
        async def _on_blocked(ev: ChatMemberUpdated):
            uid  = ev.from_user.id
            user = next((u for u in self.users if u["id"] == uid), None)
            if user:
                user["is_active"] = False
                asyncio.create_task(self._push_state())
                if self.admin_id:
                    try:
                        await self.tg.send_message(
                            self.admin_id,
                            f"🔴 <b>{ev.from_user.full_name}</b> заблокировал бота.",
                            message_thread_id=user.get("last_topic_id"))
                    except Exception:
                        pass

        @self.router.message(CommandStart())
        async def _on_start(m: Message):
            if self.admin_id and m.chat.id == self.admin_id:
                return
            user, _ = self.get_or_create_user(m)
            if user.get("is_banned"):
                await m.answer("🚫 <b>Вы заблокированы в этом боте.</b>")
                return
            reply_kb  = self.kb_reply()
            inline_kb = self.kb_inline(self.welcome_inline)
            main_kb   = inline_kb or reply_kb
            ad        = await self.get_ad() if self.ad_enabled else None
            welcome   = self.welcome or "Здравствуйте!"
            ad_text   = ad.get("text", "") if ad else ""
            ad_media  = (ad.get("media_url") or "") if ad else ""
            combined  = f"{welcome}\n\n─────────────────\n📢 <b>Реклама</b>\n{ad_text}" if ad else welcome
            try:
                if self.welcome_photo:
                    await m.answer_photo(self.welcome_photo, caption=combined[:1024], reply_markup=main_kb)
                    if ad_media and ad_media != self.welcome_photo:
                        await m.answer_photo(ad_media, caption=f"📢 {ad_text}"[:1024])
                elif ad_media:
                    await m.answer(welcome, reply_markup=main_kb)
                    await m.answer_photo(ad_media, caption=f"📢 <b>Реклама</b>\n{ad_text}"[:1024])
                else:
                    await m.answer(combined, reply_markup=main_kb)
            except Exception as e:
                log.warning(f"start send: {e}")
                try: await m.answer(welcome, reply_markup=reply_kb)
                except Exception: pass
            await self.log_msg(user["id"], m.from_user.full_name, "/start")

        # ── ГЛАВНЫЙ HANDLER ─────────────────────────────────────────────
        @self.router.message()
        async def _on_message(m: Message):

            # ════════════ ВЕТКА АДМИНИСТРАТОРА ════════════
            if self.admin_id and m.chat.id == self.admin_id:

                # Команды
                if await self.handle_admin_cmd(m):
                    return

                # Режим рассылки — bc_wait сбрасывается через .pop()
                # Это значит: только ОДНО следующее сообщение уйдёт в рассылку
                if self.bc_wait.pop(m.from_user.id, False):
                    actives = [u for u in self.users if not u.get("is_banned") and u.get("is_active", True)]
                    if actives:
                        await self.do_broadcast(m, actives, m.message_id)
                    else:
                        await m.reply("Нет активных пользователей.")
                    return

                # Ответ пользователю
                target_uid = None
                if m.message_thread_id:
                    u = next((x for x in self.users if x.get("last_topic_id") == m.message_thread_id), None)
                    if u: target_uid = u["id"]
                if not target_uid and m.reply_to_message:
                    target_uid = self.msg_map.get(m.reply_to_message.message_id)

                if target_uid:
                    try:
                        await self.tg.copy_message(target_uid, m.chat.id, m.message_id)
                        await self.log_msg(target_uid, "Admin", m.text or "[Медиа]", is_admin=True)
                    except TelegramForbiddenError:
                        await m.reply("❌ Пользователь заблокировал бота.")
                    except Exception as e:
                        await m.reply(f"❌ Ошибка: {e}")
                return
            # ══════ конец ветки администратора ══════

            # ════════════ ВЕТКА ПОЛЬЗОВАТЕЛЯ ════════════
            user, is_new = self.get_or_create_user(m)
            if user.get("is_banned"):
                try: await m.answer("🚫 <b>Вы заблокированы в этом боте.</b>")
                except Exception: pass
                return

            uid = user["id"]

            # Media group
            if m.media_group_id:
                gid = m.media_group_id
                if gid not in self.mg_buf:
                    self.mg_buf[gid] = {
                        "msgs": [], "user": user, "is_new": is_new,
                        "in_ticket": bool(user.get("_in_ticket")),
                    }
                    async def _flush(gid=gid):
                        await asyncio.sleep(1.2)
                        buf = self.mg_buf.pop(gid, None)
                        if not buf or not buf["msgs"]: return
                        if not (buf["in_ticket"] or self.forward_all or buf["is_new"]): return
                        if not self.admin_id: return
                        try:
                            from aiogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument
                            first = buf["msgs"][0]
                            hdr   = build_header(first, self.stg, buf["is_new"])
                            items = []
                            for i, msg in enumerate(buf["msgs"]):
                                cap = ((hdr if i == 0 else "") + (msg.caption or ""))[:1024]
                                if msg.photo:
                                    items.append(InputMediaPhoto(media=msg.photo[-1].file_id, caption=cap or None, parse_mode="HTML"))
                                elif msg.video:
                                    items.append(InputMediaVideo(media=msg.video.file_id, caption=cap or None, parse_mode="HTML"))
                                elif msg.document:
                                    items.append(InputMediaDocument(media=msg.document.file_id, caption=cap or None, parse_mode="HTML"))
                            if items:
                                await self.tg.send_media_group(
                                    self.admin_id, items,
                                    message_thread_id=buf["user"].get("last_topic_id"))
                        except Exception as e:
                            log.error(f"mg_flush: {e}")
                        await self.log_msg(buf["user"]["id"], buf["msgs"][0].from_user.full_name, "[МедиаГруппа]")
                    asyncio.create_task(_flush())
                self.mg_buf[gid]["msgs"].append(m)
                return

            # Антиспам
            if await self.check_flood(uid):
                return

            # Активный тикет
            if user.get("_in_ticket"):
                close_label = user.get("_ticket_close_label", "Закрыть обращение")
                if m.text and m.text.strip() in (close_label, "Закрыть обращение"):
                    user.pop("_in_ticket", None)
                    user.pop("_ticket_close_label", None)
                    asyncio.create_task(self._push_state())
                    if self.admin_id:
                        try:
                            nl = user.get("first_name", str(uid))
                            if user.get("username"): nl += f" (@{user['username']})"
                            await self.tg.send_message(
                                self.admin_id,
                                f"🔒 Обращение закрыто.\n{nl} | ID: <code>{uid}</code>",
                                message_thread_id=user.get("last_topic_id"))
                        except Exception: pass
                    await m.answer("🔒 Обращение закрыто.", reply_markup=self.kb_reply())
                    return
                await self.forward_to_admin(m, user)
                await self.log_msg(uid, m.from_user.full_name, m.text or "[Медиа]")
                return

            # ══ КНОПКИ и ТРИГГЕРЫ — ВСЕГДА ДО forwardAll ══
            if m.text:
                clean = m.text.strip()
                lower = clean.lower()

                if clean in ("⬅️ Назад", "Назад"):
                    await m.answer("Главное меню:", reply_markup=self.kb_reply())
                    return

                btn_match = next(
                    (b for b in self.buttons if b.get("text", "").lower() == lower), None)
                if btn_match:
                    btype = btn_match.get("type", "default")
                    if btype == "ticket":
                        user["_in_ticket"]         = True
                        user["_ticket_close_label"] = "Закрыть обращение"
                        await self.forward_to_admin(m, user, btn_text=btn_match["text"])
                        resp = btn_match.get("response", "Ваше обращение принято. Ожидайте ответа оператора.")
                        close_kb = ReplyKeyboardMarkup(
                            keyboard=[[KeyboardButton(text="Закрыть обращение")]],
                            resize_keyboard=True)
                        await m.answer(
                            f"{resp}\n\nПишите — все сообщения доставят оператору.",
                            reply_markup=close_kb)
                    else:
                        resp  = btn_match.get("response", "")
                        ikb   = self.kb_inline(btn_match.get("inline", []))
                        await m.answer(resp or "✅", reply_markup=ikb or self.kb_reply())
                    await self.log_msg(uid, m.from_user.full_name, f"КНОПКА: {btn_match['text']}")
                    return

                for trig in self.triggers:
                    kw = trig.get("keyword", "")
                    if kw and kw.lower() in lower:
                        await m.answer(trig.get("response") or "✅")
                        await self.log_msg(uid, m.from_user.full_name, f"ТРИГГЕР: {kw}")
                        return

            # Форвард: первое обращение или forward_all
            if is_new or self.forward_all:
                await self.forward_to_admin(m, user, is_first=is_new)
                await self.log_msg(uid, m.from_user.full_name, m.text or "[Медиа]")
            else:
                await m.answer(
                    "Воспользуйтесь меню или нажмите кнопку для связи с оператором.",
                    reply_markup=self.kb_reply())

        @self.router.callback_query(lambda c: c.data == "ticket_close")
        async def _on_cb_close(cb: CallbackQuery):
            uid  = cb.from_user.id
            user = next((u for u in self.users if u["id"] == uid), None)
            if user:
                user.pop("_in_ticket", None)
                asyncio.create_task(self._push_state())
                if self.admin_id:
                    try:
                        nl = user.get("first_name", str(uid))
                        if user.get("username"): nl += f" (@{user['username']})"
                        await self.tg.send_message(
                            self.admin_id,
                            f"🔒 Обращение закрыто.\n{nl} | ID: <code>{uid}</code>",
                            message_thread_id=user.get("last_topic_id"))
                    except Exception: pass
            try: await cb.message.delete()
            except Exception: pass
            try: await cb.answer("Обращение закрыто.")
            except Exception: pass
            try: await self.tg.send_message(uid, "🔒 <b>Обращение закрыто.</b>", reply_markup=self.kb_reply())
            except Exception: pass

    # ─────────────────────────────────────────────────────
    # ЗАГРУЗКА ИЗ БД И ЗАПУСК
    # ─────────────────────────────────────────────────────

    async def load_from_db(self):
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(
                    f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                    headers=self.sb_hdrs)
                if r.status_code == 200 and r.json():
                    row = r.json()[0]
                    rc  = row.get("config") or {}
                    if isinstance(rc, str):
                        try: rc = json.loads(rc)
                        except Exception: rc = {}
                    self._apply_config({**row, "config": rc})
                    log.info(
                        f"✅ [{self.bot_id}] Загружен: users={len(self.users)} "
                        f"btns={len(self.buttons)} trgs={len(self.triggers)} "
                        f"admin={self.admin_id} topics={self.use_topics} "
                        f"fwdAll={self.forward_all} bc_today={self._bc_today_count}")
                else:
                    log.error(f"load_from_db: бот {self.bot_id} не найден (status={r.status_code})")
        except Exception as e:
            log.error(f"load_from_db: {e}")

    async def run(self):
        log.info(f"[FREE] Бот {self.bot_id} стартует...")
        await self.load_from_db()
        asyncio.create_task(self.config_sync_loop())
        asyncio.create_task(self.stats_rotator())
        await self.setup_handlers()
        self.dp.include_router(self.router)
        log.info(
            f"[FREE] {self.bot_id} готов | users={len(self.users)} "
            f"btns={len(self.buttons)} trgs={len(self.triggers)} "
            f"admin={self.admin_id} topics={self.use_topics} fwdAll={self.forward_all}")
        try:
            await self.dp.start_polling(
                self.tg,
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query", "my_chat_member"])
        finally:
            self.is_running = False
            await self.tg.session.close()


# ═══════════════════════════════════════════════════════════
# ТОЧКА ВХОДА
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("INFO: worker script. Sleeping.", flush=True)
        import signal
        _ev = asyncio.Event()
        signal.signal(signal.SIGTERM, lambda *_: _ev.set())
        signal.signal(signal.SIGINT,  lambda *_: _ev.set())
        asyncio.run(_ev.wait())
        sys.exit(0)

    async def _main():
        try:
            with open(sys.argv[1], encoding="utf-8") as f:
                cfg = json.load(f)
            await FreeBotInstance(cfg).run()
        except Exception as e:
            log.error(f"FATAL: {e}", exc_info=True)
            sys.exit(1)

    asyncio.run(_main())
