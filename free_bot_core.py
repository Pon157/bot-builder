"""
free_bot_core.py  v4
═══════════════════════════════════════════════════════════════════════════════
Исправления v4:
  • admin_input: без lambda-фильтра (работает даже если admin_chat_id загружен позже)
  • кнопки/триггеры: работают при forwardAll=True (проверяются ДО форварда)
  • /stats, /whois — полноценные команды
  • заголовки сообщений: читаются из settings (там где сохраняются)
  • топики: сохраняются и применяются корректно
  • рассылка: copy_message поддерживает любой тип медиа (стикеры, фото, и т.д.)
  • дебаунс push_state — бот не зависает
  • нет memory watchdog
  • нет лимитов кнопок/триггеров/ботов
  • drop_pending_updates при старте
═══════════════════════════════════════════════════════════════════════════════
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
log = logging.getLogger("FreeBotCore")


# ════════════════════════════════════════════════════════════════════════════
# MIDDLEWARE — бан
# ════════════════════════════════════════════════════════════════════════════

class BanMiddleware(BaseMiddleware):
    def __init__(self, bi): self.bi = bi; super().__init__()
    async def __call__(self, handler: Callable, event: Any, data: Dict) -> Any:
        u = getattr(event, "from_user", None)
        if u:
            usr = next((x for x in self.bi.users if x.get("id") == u.id), None)
            if usr and usr.get("is_banned"):
                try:
                    if isinstance(event, Message): await event.answer("🚫 <b>Вы заблокированы.</b>")
                    elif isinstance(event, CallbackQuery): await event.answer("🚫 Заблокированы.", show_alert=True)
                except Exception: pass
                return
        return await handler(event, data)


# ════════════════════════════════════════════════════════════════════════════
# ХЕЛПЕРЫ
# ════════════════════════════════════════════════════════════════════════════

def anon_id(uid: int) -> str:
    return hashlib.md5(str(uid).encode()).hexdigest()[:6].upper()

def make_header(m: Message, stg: dict, is_first: bool = False, btn: str = "") -> str:
    uid = m.from_user.id
    is_anon = stg.get("anonymousTopics", False)
    if is_anon:
        info = f"👤 <b>Аноним #{anon_id(uid)}</b>"
    else:
        parts = []
        if stg.get("showHeaderName", True) and m.from_user.full_name:
            parts.append(f"<b>{m.from_user.full_name}</b>")
        if stg.get("showHeaderUsername", True) and m.from_user.username:
            parts.append(f"(@{m.from_user.username})")
        if stg.get("showHeaderId", True):
            parts.append(f"ID: <code>{uid}</code>")
        info = " | ".join(parts) if parts else f"ID: <code>{uid}</code>"

    if btn:
        hdr = stg.get("ticketMessageHeader", "🆘 <b>ЗАЯВКА:</b>")
        hdr = hdr.replace("{btn}", btn) if "{btn}" in hdr else f"{hdr} [{btn}]:"
    elif is_first:
        hdr = stg.get("firstMessageHeader", "🆕 <b>ПЕРВОЕ ОБРАЩЕНИЕ:</b>")
    else:
        hdr = stg.get("commonMessageHeader", "📩 <b>СООБЩЕНИЕ:</b>")
    return f"{hdr}\n{info}\n\n"


# ════════════════════════════════════════════════════════════════════════════
# ОСНОВНОЙ КЛАСС
# ════════════════════════════════════════════════════════════════════════════

class FreeBotInstance:

    def __init__(self, cfg: dict):
        self.bot_id = cfg.get("id")
        self.token  = cfg.get("token")
        self.sb_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.sb_key = os.getenv("SUPABASE_KEY", "")
        self.sb_hdrs = {
            "apikey": self.sb_key,
            "Authorization": f"Bearer {self.sb_key}",
            "Content-Type":  "application/json",
        }
        self.server_url = os.getenv("SERVER_BASE_URL", "http://localhost:8000")

        self.tg   = Bot(token=self.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp   = Dispatcher()
        self.router = Router()

        # Runtime maps (не сбрасываются при перезагрузке конфига)
        self.msg_map:    Dict[int, int]  = {}   # admin_msg_id → user_id
        self.flood:      Dict[int, float] = {}
        self.bc_waiting: Dict[int, bool]  = {}  # admin_id → ждёт сообщения для рассылки
        self.mgbuf:      Dict[str, dict]  = {}  # media group buffer

        # Broadcast daily counter
        self._bc_day = {"date": "", "count": 0}
        self._last_push: float = 0.0
        self.is_running = True

        # Инициализируем из конфига
        self.users:      list = []
        self.stats:      dict = {}
        self._apply(cfg)

    # ─────────────────────────────────────────────────────────────────────
    # КОНФИГ
    # ─────────────────────────────────────────────────────────────────────

    def _apply(self, raw: dict):
        """Применяет конфиг из row БД (или файла). Вызывается при старте."""
        cfg = raw.get("config") or {}
        if isinstance(cfg, str):
            try: cfg = json.loads(cfg)
            except: cfg = {}
        full = {**raw, **cfg}   # raw имеет приоритет над cfg для id/token/etc, но cfg перекрывает остальное

        # Токен / id — не трогаем если уже есть
        if not getattr(self, "bot_id", None): self.bot_id = raw.get("id")
        if not getattr(self, "token", None):  self.token  = raw.get("token")

        admin_raw = full.get("adminChatId") or full.get("admin_chat_id") or full.get("adminId")
        self.admin_id = int(str(admin_raw).strip()) if admin_raw else None

        stg = full.get("settings") or {}
        self.stg          = stg
        self.use_topics   = bool(stg.get("useTopics"))
        self.topic_per_req = bool(stg.get("topicPerRequest"))
        self.forward_all  = bool(stg.get("forwardAll"))
        self.fwd_native   = bool(stg.get("forwardMessages"))   # нативный forward
        self.rate_limit   = float(stg.get("rateLimit", 1.0))
        self.ban_thr      = int(stg.get("autoBanThreshold", 3))

        self.buttons  = full.get("buttons",  []) or []
        self.triggers = full.get("triggers", []) or []
        self.welcome  = full.get("welcomeMessage", "Здравствуйте!") or "Здравствуйте!"
        self.welcome_photo = full.get("welcomePhoto", "") or ""
        self.welcome_inline = full.get("welcomeInline", []) or []
        self.ad_enabled = raw.get("ad_enabled", True)

        # users и stats — только при первом вызове (не перезатираем runtime)
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

    def _reload_settings(self, cfg: dict):
        """
        Обновляет только настройки из объекта config (без users/stats).
        Вызывается из config_sync_loop каждые 30 сек.
        """
        stg = cfg.get("settings") or {}
        self.stg          = stg
        self.use_topics   = bool(stg.get("useTopics"))
        self.topic_per_req = bool(stg.get("topicPerRequest"))
        self.forward_all  = bool(stg.get("forwardAll"))
        self.fwd_native   = bool(stg.get("forwardMessages"))
        self.rate_limit   = float(stg.get("rateLimit", 1.0))
        self.ban_thr      = int(stg.get("autoBanThreshold", 3))

        self.buttons  = cfg.get("buttons",  self.buttons) or []
        self.triggers = cfg.get("triggers", self.triggers) or []
        self.welcome  = cfg.get("welcomeMessage", self.welcome) or self.welcome
        self.welcome_photo  = cfg.get("welcomePhoto",  self.welcome_photo) or ""
        self.welcome_inline = cfg.get("welcomeInline", self.welcome_inline) or []

        admin_raw = cfg.get("adminChatId") or cfg.get("admin_chat_id")
        if admin_raw:
            try: self.admin_id = int(str(admin_raw).strip())
            except: pass

    # ─────────────────────────────────────────────────────────────────────
    # РЕКЛАМА
    # ─────────────────────────────────────────────────────────────────────

    async def get_ad(self) -> Optional[dict]:
        if not self.ad_enabled: return None
        try:
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.get(f"{self.server_url}/api/ads/active", params={"bot_id": self.bot_id})
                if r.status_code == 200: return r.json().get("ad")
        except: pass
        return None

    # ─────────────────────────────────────────────────────────────────────
    # КЛАВИАТУРЫ
    # ─────────────────────────────────────────────────────────────────────

    def kb_main(self):
        active = [b for b in self.buttons if b.get("text")]
        if not active: return ReplyKeyboardRemove()
        rows = []
        for i in range(0, len(active), 2):
            rows.append([KeyboardButton(text=b["text"]) for b in active[i:i+2]])
        return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

    def kb_inline(self, btns: list) -> Optional[InlineKeyboardMarkup]:
        if not btns: return None
        rows = []
        for i in range(0, len(btns), 2):
            r = [InlineKeyboardButton(text=b["text"], url=b.get("url","https://t.me")) for b in btns[i:i+2] if b.get("text")]
            if r: rows.append(r)
        return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None

    # ─────────────────────────────────────────────────────────────────────
    # ТОПИКИ
    # ─────────────────────────────────────────────────────────────────────

    async def get_thread(self, user: dict, force_new=False) -> Optional[int]:
        if not self.use_topics or not self.admin_id: return None
        existing = user.get("last_topic_id")
        if existing and not force_new: return existing
        try:
            n  = user.get("first_name", "User")
            un = user.get("username")
            title = f"{n}" + (f" @{un}" if un else f" #{user['id']}")
            t = await self.tg.create_forum_topic(self.admin_id, title[:128])
            user["last_topic_id"] = t.message_thread_id
            return t.message_thread_id
        except Exception as e:
            log.warning(f"get_thread: {e}"); return None

    # ─────────────────────────────────────────────────────────────────────
    # ФОРВАРД К АДМИНУ
    # ─────────────────────────────────────────────────────────────────────

    async def fwd_admin(self, m: Message, user: dict, is_first=False, btn=""):
        if not self.admin_id: return
        force = self.topic_per_req and (btn or is_first)
        tid   = await self.get_thread(user, force_new=force)

        # Нативный форвард (без заголовка)
        if self.fwd_native and not btn and not is_first:
            try:
                s = await self.tg.forward_message(self.admin_id, m.chat.id, m.message_id, message_thread_id=tid)
                if s: self.msg_map[s.message_id] = user["id"]
            except TelegramBadRequest as e:
                if "thread" in str(e).lower():
                    user["last_topic_id"] = None
                    tid2 = await self.get_thread(user, force_new=True)
                    try:
                        s = await self.tg.forward_message(self.admin_id, m.chat.id, m.message_id, message_thread_id=tid2)
                        if s: self.msg_map[s.message_id] = user["id"]
                    except Exception: pass
                else: log.error(f"fwd_admin native: {e}")
            except Exception as e: log.error(f"fwd_admin native: {e}")
            return

        # copy_message с заголовком
        hdr = make_header(m, self.stg, is_first, btn)

        async def _try_send():
            nonlocal tid
            try:
                s = None
                if m.photo:
                    s = await self.tg.send_photo(self.admin_id, m.photo[-1].file_id,
                        caption=(hdr + (m.caption or ""))[:1024], message_thread_id=tid)
                elif m.video:
                    s = await self.tg.send_video(self.admin_id, m.video.file_id,
                        caption=(hdr + (m.caption or ""))[:1024], message_thread_id=tid)
                elif m.document:
                    s = await self.tg.send_document(self.admin_id, m.document.file_id,
                        caption=(hdr + (m.caption or ""))[:1024], message_thread_id=tid)
                elif m.sticker or m.voice or m.video_note or m.audio:
                    await self.tg.send_message(self.admin_id, hdr.strip(),
                        message_thread_id=tid, parse_mode="HTML")
                    s = await self.tg.copy_message(self.admin_id, m.chat.id, m.message_id, message_thread_id=tid)
                else:
                    txt = (hdr + (m.text or ""))[:4096]
                    s = await self.tg.send_message(self.admin_id, txt,
                        message_thread_id=tid, parse_mode="HTML")
                if s: self.msg_map[s.message_id] = user["id"]
            except TelegramBadRequest as e:
                if "thread" in str(e).lower():
                    user["last_topic_id"] = None
                    tid = await self.get_thread(user, force_new=True)
                    try:
                        txt = (hdr + (m.text or ""))[:4096]
                        s = await self.tg.send_message(self.admin_id, txt, parse_mode="HTML")
                        if s: self.msg_map[s.message_id] = user["id"]
                    except Exception: pass
                else: log.error(f"fwd_admin: {e}")
            except Exception as e: log.error(f"fwd_admin: {e}")

        await _try_send()

    # ─────────────────────────────────────────────────────────────────────
    # ПОЛЬЗОВАТЕЛЬ
    # ─────────────────────────────────────────────────────────────────────

    def get_user(self, m: Message):
        uid  = m.from_user.id
        user = next((u for u in self.users if u["id"] == uid), None)
        is_new = False
        if not user:
            user = {
                "id":        uid,
                "first_name": m.from_user.first_name or "",
                "username":   m.from_user.username or "",
                "joined_at":  int(time.time()),
                "last_seen":  int(time.time()),
                "is_banned":  False,
                "warns":      0,
                "is_active":  True,
            }
            self.users.append(user)
            is_new = True
        else:
            user["last_seen"]   = int(time.time())
            user["first_name"]  = m.from_user.first_name or user.get("first_name","")
            user["username"]    = m.from_user.username   or user.get("username","")
        return user, is_new

    async def flood_check(self, uid: int) -> bool:
        if self.rate_limit <= 0: return False
        now = time.time()
        if now - self.flood.get(uid, 0) < self.rate_limit: return True
        self.flood[uid] = now; return False

    # ─────────────────────────────────────────────────────────────────────
    # СТАТИСТИКА
    # ─────────────────────────────────────────────────────────────────────

    def stat_inc(self, is_admin=False):
        self.stats["totalMessages"] = self.stats.get("totalMessages",0) + 1
        key = "outgoingToday" if is_admin else "incomingToday"
        self.stats[key] = self.stats.get(key,0) + 1

    async def do_log(self, uid: int, name: str, text: str, is_admin=False):
        self.stat_inc(is_admin)
        asyncio.create_task(self._log_msg(uid, name, text, is_admin))
        asyncio.create_task(self._push())

    async def _log_msg(self, uid, name, text, is_admin):
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                await c.post(f"{self.sb_url}/rest/v1/bot_messages",
                    json={"bot_id": self.bot_id, "user_id": uid,
                          "first_name": name, "message_text": (text or "")[:950],
                          "is_from_admin": is_admin},
                    headers={**self.sb_hdrs, "Prefer": "return=minimal"})
        except: pass

    # ─────────────────────────────────────────────────────────────────────
    # БД
    # ─────────────────────────────────────────────────────────────────────

    async def _push(self):
        """Сохраняет users и stats в БД. Дебаунс 5 сек."""
        now = time.time()
        if now - self._last_push < 5.0: return
        self._last_push = now
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get(f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}&select=config",
                    headers=self.sb_hdrs)
                if r.status_code != 200 or not r.json(): return
                old_cfg = r.json()[0].get("config") or {}
                new_cfg = {**old_cfg, "connectedUsers": self.users, "stats": self.stats}
                await c.patch(f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                    json={"config": new_cfg},
                    headers={**self.sb_hdrs, "Prefer": "return=minimal"})
        except Exception as e: log.debug(f"_push: {e}")

    async def _push_force(self):
        """Принудительный сброс дебаунса + сохранение."""
        self._last_push = 0
        await self._push()

    # ─────────────────────────────────────────────────────────────────────
    # BROADCAST
    # ─────────────────────────────────────────────────────────────────────

    def _bc_count(self) -> int:
        today = datetime.now().strftime("%d.%m")
        if self._bc_day.get("date") != today: self._bc_day = {"date": today, "count": 0}
        return self._bc_day["count"]

    def _bc_inc(self):
        today = datetime.now().strftime("%d.%m")
        if self._bc_day.get("date") != today: self._bc_day = {"date": today, "count": 0}
        self._bc_day["count"] += 1
        self.stats["broadcastsToday"] = self._bc_day["count"]
        self.stats["broadcastsTotal"] = self.stats.get("broadcastsTotal",0) + 1

    async def do_broadcast(self, m: Message, users: list, src_id: int):
        sent = err = 0
        sm = await m.reply(f"🚀 <b>Рассылаю {len(users)} получателям...</b>")
        for u in users:
            try:
                await self.tg.copy_message(int(u["id"]), m.chat.id, src_id)
                sent += 1
                await asyncio.sleep(0.05)
            except TelegramForbiddenError:
                u["is_active"] = False; err += 1
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
                try:
                    await self.tg.copy_message(int(u["id"]), m.chat.id, src_id); sent += 1
                except: err += 1
            except Exception as e:
                log.debug(f"bc send {u['id']}: {e}"); err += 1
        self._bc_inc()
        await self._push_force()
        try:
            await sm.edit_text(
                f"✅ <b>Рассылка завершена!</b>\n\n"
                f"👤 Доставлено: <b>{sent}</b>\n"
                f"🚫 Ошибок: <b>{err}</b>\n"
                f"📊 Рассылок сегодня: <b>{self._bc_count()}</b>")
        except: pass

    # ─────────────────────────────────────────────────────────────────────
    # КОМАНДЫ МОДЕРАЦИИ
    # ─────────────────────────────────────────────────────────────────────

    async def do_admin_cmd(self, m: Message) -> bool:
        if not m.text: return False
        txt = m.text.strip()
        if not (txt.startswith("/") or txt.startswith("!")): return False

        parts = txt.split()
        cmd   = parts[0][1:].lower()

        # ── /stats ───────────────────────────────────────────────────────
        if cmd == "stats":
            total  = len(self.users)
            banned = sum(1 for u in self.users if u.get("is_banned"))
            active = sum(1 for u in self.users if u.get("is_active",True) and not u.get("is_banned"))
            bc     = self._bc_count()
            await m.reply(
                f"📊 <b>Статистика бота</b>\n\n"
                f"👥 Всего пользователей: <b>{total}</b>\n"
                f"✅ Активных: <b>{active}</b>\n"
                f"🚫 Заблокировано: <b>{banned}</b>\n"
                f"📢 Рассылок сегодня: <b>{bc}</b>\n"
                f"📨 Сообщений всего: <b>{self.stats.get('totalMessages',0)}</b>")
            return True

        # ── /broadcast ───────────────────────────────────────────────────
        if cmd == "broadcast":
            active_users = [u for u in self.users if not u.get("is_banned") and u.get("is_active",True)]
            if not active_users:
                await m.reply("Нет активных пользователей."); return True
            if m.reply_to_message:
                await self.do_broadcast(m, active_users, m.reply_to_message.message_id)
            else:
                self.bc_waiting[m.from_user.id] = True
                await m.reply(
                    f"📢 <b>Режим рассылки</b>\n"
                    f"Следующим сообщением пришлите то, что хотите разослать.\n"
                    f"<i>Поддерживается любой тип: текст, фото, видео, стикер, голосовой и т.д.</i>")
            return True

        # ── Команды требующие target_user ────────────────────────────────
        target = None
        if m.message_thread_id:
            target = next((u for u in self.users if u.get("last_topic_id") == m.message_thread_id), None)
        if not target and m.reply_to_message:
            uid_map = self.msg_map.get(m.reply_to_message.message_id)
            if uid_map:
                target = next((u for u in self.users if int(u["id"]) == int(uid_map)), None)
        if not target and len(parts) > 1:
            try:
                did = int(parts[1])
                target = next((u for u in self.users if int(u["id"]) == did), None)
                if not target and cmd in ("ban","unban"):
                    target = {"id": did, "first_name": f"User#{did}", "username": None,
                               "is_banned": False, "warns": 0, "joined_at": int(time.time()), "last_seen": int(time.time())}
                    self.users.append(target)
                elif not target:
                    await m.reply(f"Пользователь <code>{did}</code> не найден."); return True
            except ValueError: pass

        if not target: return False

        uid = target["id"]

        if cmd == "whois":
            un   = target.get("username")
            name = target.get("first_name","—") + (f" (@{un})" if un else "")
            jt   = datetime.fromtimestamp(target.get("joined_at",0)).strftime("%d.%m.%Y %H:%M") if target.get("joined_at") else "—"
            ls   = datetime.fromtimestamp(target.get("last_seen",0)).strftime("%d.%m.%Y %H:%M")  if target.get("last_seen") else "—"
            await m.reply(
                f"🔍 <b>Пользователь</b> <code>{uid}</code>\n\n"
                f"👤 {name}\n"
                f"🚫 Забанен: {'Да' if target.get('is_banned') else 'Нет'}\n"
                f"⚠️ Варнов: {target.get('warns',0)}/{self.ban_thr or '∞'}\n"
                f"📅 Зашёл: {jt}\n"
                f"🕐 Активен: {ls}")
            return True

        if cmd == "ban":
            target["is_banned"] = True
            self.stats["bannedCount"] = self.stats.get("bannedCount",0) + 1
            await self._push_force()
            try: await self.tg.send_message(uid, "🚫 <b>Доступ к боту ограничен.</b>")
            except: pass
            await m.reply(f"✅ <code>{uid}</code> заблокирован.")
            return True

        if cmd == "unban":
            target["is_banned"] = False; target["warns"] = 0
            self.stats["bannedCount"] = max(0, self.stats.get("bannedCount",1) - 1)
            await self._push_force()
            try: await self.tg.send_message(uid, "✅ <b>Доступ восстановлен.</b>")
            except: pass
            await m.reply(f"✅ <code>{uid}</code> разблокирован.")
            return True

        if cmd == "warn":
            target["warns"] = target.get("warns",0) + 1
            if self.ban_thr > 0 and target["warns"] >= self.ban_thr:
                target["is_banned"] = True
                self.stats["bannedCount"] = self.stats.get("bannedCount",0) + 1
                msg = f"🚨 <b>АВТО-БАН</b> <code>{uid}</code> ({target['warns']}/{self.ban_thr} варнов)"
                notif = f"🚫 Авто-бан: лимит предупреждений исчерпан."
            else:
                msg   = f"⚠️ Варн <code>{uid}</code>: {target['warns']}/{self.ban_thr or '∞'}"
                notif = f"⚠️ Предупреждение! ({target['warns']}/{self.ban_thr or '∞'})"
            await self._push_force()
            try: await self.tg.send_message(uid, notif)
            except: pass
            await m.reply(msg); return True

        if cmd == "unwarn":
            target["warns"] = max(0, target.get("warns",0) - 1)
            await self._push_force()
            await m.reply(f"✅ Варн снят. У <code>{uid}</code>: {target['warns']}")
            return True

        return False

    # ─────────────────────────────────────────────────────────────────────
    # ФОНОВЫЕ ЗАДАЧИ
    # ─────────────────────────────────────────────────────────────────────

    async def config_sync_loop(self):
        """Каждые 30 сек читает конфиг из БД и обновляет настройки."""
        await asyncio.sleep(30)
        while self.is_running:
            try:
                async with httpx.AsyncClient(timeout=8) as c:
                    r = await c.get(f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}&select=config",
                        headers=self.sb_hdrs)
                    if r.status_code == 200 and r.json():
                        cfg = r.json()[0].get("config") or {}
                        self._reload_settings(cfg)
                        log.debug(f"[{self.bot_id}] config reloaded: btns={len(self.buttons)} trgs={len(self.triggers)} topics={self.use_topics} fwdAll={self.forward_all}")
            except Exception as e: log.error(f"config_sync_loop: {e}")
            await asyncio.sleep(30)

    async def stats_rotator(self):
        """Каждую минуту обновляет статистику и пушит в БД."""
        while self.is_running:
            try:
                now  = datetime.now()
                date = now.strftime("%d.%m")
                ago  = int((now - timedelta(days=1)).timestamp())
                active = sum(1 for u in self.users if u.get("last_seen",0) > ago)
                self.stats["activeUsers24h"] = active

                hist = self.stats.setdefault("history", [])
                if not hist:
                    hist.append({"date": date, "incoming": 0, "outgoing": 0,
                                 "totalUsers": len(self.users), "activeUsers": active, "broadcasts": 0})
                if hist[-1]["date"] != date:
                    hist[-1].update({"incoming": self.stats.get("incomingToday",0),
                                     "outgoing": self.stats.get("outgoingToday",0),
                                     "totalUsers": len(self.users), "activeUsers": active})
                    self.stats["incomingToday"] = self.stats["outgoingToday"] = self.stats["broadcastsToday"] = 0
                    self._bc_day = {"date": date, "count": 0}
                    hist.append({"date": date, "incoming": 0, "outgoing": 0,
                                 "totalUsers": len(self.users), "activeUsers": active, "broadcasts": 0})
                    self.stats["history"] = hist[-14:]
                hist[-1].update({"incoming": self.stats.get("incomingToday",0),
                                 "outgoing": self.stats.get("outgoingToday",0),
                                 "totalUsers": len(self.users), "activeUsers": active})
                await self._push_force()
            except Exception as e: log.error(f"stats_rotator: {e}")
            await asyncio.sleep(60)

    # ─────────────────────────────────────────────────────────────────────
    # HANDLERS
    # ─────────────────────────────────────────────────────────────────────

    async def setup(self):
        self.router.message.middleware(BanMiddleware(self))
        self.router.callback_query.middleware(BanMiddleware(self))

        # ── Заблокировал бота ─────────────────────────────────────────────
        @self.router.my_chat_member(
            ChatMemberUpdatedFilter(member_status_changed=ChatMemberStatus.KICKED))
        async def _blocked(ev: ChatMemberUpdated):
            uid = ev.from_user.id
            u   = next((x for x in self.users if x["id"] == uid), None)
            if u:
                u["is_active"] = False
                asyncio.create_task(self._push())
                if self.admin_id:
                    try: await self.tg.send_message(self.admin_id,
                        f"🔴 <b>{ev.from_user.full_name}</b> заблокировал бота.",
                        message_thread_id=u.get("last_topic_id"))
                    except: pass

        # ── /start ────────────────────────────────────────────────────────
        @self.router.message(CommandStart())
        async def _start(m: Message):
            user, _ = self.get_user(m)
            if user.get("is_banned"):
                await m.answer("🚫 <b>Вы заблокированы.</b>"); return

            reply_kb  = self.kb_main()
            inline_kb = self.kb_inline(self.welcome_inline)
            main_kb   = inline_kb or reply_kb

            ad      = await self.get_ad() if self.ad_enabled else None
            welcome = self.welcome or "Здравствуйте!"
            if ad:
                ad_text  = ad.get("text","")
                ad_media = ad.get("media_url","") or ""
                combined = f"{welcome}\n\n─────────────────\n📢 <b>Реклама</b>\n{ad_text}"
            else:
                combined = welcome; ad_text = ""; ad_media = ""

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
                log.warning(f"_start send: {e}")
                try: await m.answer(welcome, reply_markup=reply_kb)
                except: pass

            await self.do_log(user["id"], m.from_user.full_name, "/start")

        # ── Все сообщения (единый handler — сам разбирает источник) ───────
        @self.router.message()
        async def _all(m: Message):

            # ── СООБЩЕНИЯ ОТ АДМИНИСТРАТОРА ──────────────────────────────
            if self.admin_id and m.chat.id == self.admin_id:
                # Команды
                if await self.do_admin_cmd(m): return

                # Режим рассылки
                if self.bc_waiting.pop(m.from_user.id, False):
                    actives = [u for u in self.users if not u.get("is_banned") and u.get("is_active",True)]
                    if actives: await self.do_broadcast(m, actives, m.message_id)
                    else: await m.reply("Нет активных пользователей.")
                    return

                # Ответ пользователю через топик или реплай
                tid = None
                if m.message_thread_id:
                    u = next((x for x in self.users if x.get("last_topic_id") == m.message_thread_id), None)
                    if u: tid = u["id"]
                if not tid and m.reply_to_message:
                    tid = self.msg_map.get(m.reply_to_message.message_id)

                if tid:
                    try:
                        await self.tg.copy_message(tid, m.chat.id, m.message_id)
                        await self.do_log(tid, "Admin", m.text or "[Медиа]", is_admin=True)
                    except TelegramForbiddenError:
                        await m.reply("❌ Пользователь заблокировал бота.")
                    except Exception as e:
                        await m.reply(f"❌ Ошибка: {e}")
                return  # ← всё от admin_id — обработано

            # ── СООБЩЕНИЯ ОТ ПОЛЬЗОВАТЕЛЕЙ ───────────────────────────────
            user, is_new = self.get_user(m)
            if user.get("is_banned"):
                try: await m.answer("🚫 <b>Вы заблокированы.</b>")
                except: pass
                return

            uid = user["id"]

            # Media group
            if m.media_group_id:
                gid = m.media_group_id
                if gid not in self.mgbuf:
                    self.mgbuf[gid] = {"msgs": [], "user": user, "is_new": is_new, "in_ticket": user.get("_in_ticket",False)}
                    async def _flush(gid=gid):
                        await asyncio.sleep(1.0)
                        buf = self.mgbuf.pop(gid, None)
                        if not buf or not buf["msgs"]: return
                        if not (buf["in_ticket"] or self.forward_all or buf["is_new"]): return
                        if not self.admin_id: return
                        try:
                            from aiogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument
                            first = buf["msgs"][0]
                            hdr   = make_header(first, self.stg, buf["is_new"])
                            items = []
                            for i, msg in enumerate(buf["msgs"]):
                                cap = ((hdr if i==0 else "") + (msg.caption or ""))[:1024]
                                if msg.photo:   items.append(InputMediaPhoto(media=msg.photo[-1].file_id, caption=cap or None, parse_mode="HTML"))
                                elif msg.video: items.append(InputMediaVideo(media=msg.video.file_id,   caption=cap or None, parse_mode="HTML"))
                                elif msg.document: items.append(InputMediaDocument(media=msg.document.file_id, caption=cap or None, parse_mode="HTML"))
                            if items:
                                await self.tg.send_media_group(self.admin_id, items,
                                    message_thread_id=buf["user"].get("last_topic_id"))
                        except Exception as e: log.error(f"mg flush: {e}")
                        await self.do_log(buf["user"]["id"], buf["msgs"][0].from_user.full_name, "[МедиаГруппа]")
                    asyncio.create_task(_flush())
                self.mgbuf[gid]["msgs"].append(m)
                return

            # Антиспам
            if await self.flood_check(uid): return

            # ── ТИКЕТ: активный ──────────────────────────────────────────
            if user.get("_in_ticket"):
                close = user.get("_ticket_close_label","Закрыть обращение")
                if m.text and m.text.strip() in (close, "Закрыть обращение"):
                    user.pop("_in_ticket", None); user.pop("_ticket_close_label", None)
                    asyncio.create_task(self._push())
                    if self.admin_id:
                        try:
                            n = user.get("first_name",str(uid))
                            if user.get("username"): n += f" (@{user['username']})"
                            await self.tg.send_message(self.admin_id,
                                f"Обращение закрыто.\n{n} | ID: <code>{uid}</code>",
                                message_thread_id=user.get("last_topic_id"))
                        except: pass
                    await m.answer("Обращение закрыто.", reply_markup=self.kb_main()); return
                await self.fwd_admin(m, user)
                await self.do_log(uid, m.from_user.full_name, m.text or "[Медиа]")
                return

            # ── КНОПКИ И ТРИГГЕРЫ — всегда до forwardAll ─────────────────
            if m.text:
                clean = m.text.strip()
                lower = clean.lower()

                if clean in ("⬅️ Назад", "Назад"):
                    await m.answer("Главное меню:", reply_markup=self.kb_main()); return

                btn_match = next((b for b in self.buttons if b.get("text","").lower() == lower), None)
                if btn_match:
                    btype = btn_match.get("type","default")
                    if btype == "ticket":
                        user["_in_ticket"] = True
                        user["_ticket_close_label"] = "Закрыть обращение"
                        await self.fwd_admin(m, user, btn=btn_match["text"])
                        resp = btn_match.get("response","Ваше обращение принято. Ожидайте ответа.")
                        close_kb = ReplyKeyboardMarkup(
                            keyboard=[[KeyboardButton(text="Закрыть обращение")]],
                            resize_keyboard=True)
                        await m.answer(f"{resp}\n\nПишите — сообщения доставят оператору.", reply_markup=close_kb)
                    else:
                        resp  = btn_match.get("response","")
                        ikb   = self.kb_inline(btn_match.get("inline",[]))
                        await m.answer(resp or "✅", reply_markup=ikb or self.kb_main())
                    await self.do_log(uid, m.from_user.full_name, f"КНОПКА: {btn_match['text']}")
                    return

                # Триггеры
                for trig in self.triggers:
                    kw = trig.get("keyword","")
                    if kw and kw.lower() in lower:
                        await m.answer(trig.get("response") or "✅")
                        await self.do_log(uid, m.from_user.full_name, f"ТРИГГЕР: {kw}")
                        return

            # ── ФОРВАРД: первое обращение или forwardAll ──────────────────
            if is_new or self.forward_all:
                await self.fwd_admin(m, user, is_first=is_new)
                await self.do_log(uid, m.from_user.full_name, m.text or "[Медиа]")
            else:
                await m.answer("Воспользуйтесь меню или нажмите кнопку.", reply_markup=self.kb_main())

        # ── Закрытие тикета inline ────────────────────────────────────────
        @self.router.callback_query(lambda c: c.data == "ticket_close")
        async def _cb_close(cb: CallbackQuery):
            uid = cb.from_user.id
            u   = next((x for x in self.users if x["id"] == uid), None)
            if u:
                u.pop("_in_ticket", None)
                asyncio.create_task(self._push())
                if self.admin_id:
                    try:
                        n = u.get("first_name",str(uid))
                        if u.get("username"): n += f" (@{u['username']})"
                        await self.tg.send_message(self.admin_id,
                            f"Обращение закрыто.\n{n} | ID: <code>{uid}</code>",
                            message_thread_id=u.get("last_topic_id"))
                    except: pass
            try: await cb.message.delete()
            except: pass
            try: await cb.answer("Закрыто.")
            except: pass
            try: await self.tg.send_message(uid, "Обращение закрыто.", reply_markup=self.kb_main())
            except: pass

    # ─────────────────────────────────────────────────────────────────────
    # ЗАГРУЗКА КОНФИГА ПРИ СТАРТЕ
    # ─────────────────────────────────────────────────────────────────────

    async def load_from_db(self):
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                    headers=self.sb_hdrs)
                if r.status_code == 200 and r.json():
                    row = r.json()[0]
                    rc  = row.get("config") or {}
                    if isinstance(rc, str):
                        try: rc = json.loads(rc)
                        except: rc = {}
                    self._apply({**row, "config": rc})
                    log.info(f"✅ [{self.bot_id}] loaded: btns={len(self.buttons)} trgs={len(self.triggers)} users={len(self.users)} admin={self.admin_id} topics={self.use_topics}")
        except Exception as e: log.error(f"load_from_db: {e}")

    # ─────────────────────────────────────────────────────────────────────
    # ЗАПУСК
    # ─────────────────────────────────────────────────────────────────────

    async def run(self):
        log.info(f"[FREE] Бот {self.bot_id} стартует...")
        await self.load_from_db()

        asyncio.create_task(self.config_sync_loop())
        asyncio.create_task(self.stats_rotator())

        await self.setup()
        self.dp.include_router(self.router)

        log.info(f"[FREE] {self.bot_id} готов: btns={len(self.buttons)} trgs={len(self.triggers)} "
                 f"users={len(self.users)} admin={self.admin_id} topics={self.use_topics} fwdAll={self.forward_all}")
        try:
            await self.dp.start_polling(
                self.tg,
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query", "my_chat_member"])
        finally:
            self.is_running = False
            await self.tg.session.close()


# ════════════════════════════════════════════════════════════════════════════
# ТОЧКА ВХОДА
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("INFO: free_bot_core.py — worker script, started by server.py. Sleeping.", flush=True)
        import signal
        ev = asyncio.Event()
        signal.signal(signal.SIGTERM, lambda *_: ev.set())
        signal.signal(signal.SIGINT,  lambda *_: ev.set())
        asyncio.run(ev.wait())
        sys.exit(0)

    async def main():
        try:
            with open(sys.argv[1], encoding="utf-8") as f:
                cfg = json.load(f)
            await FreeBotInstance(cfg).run()
        except Exception as e:
            log.error(f"FATAL: {e}", exc_info=True)

    asyncio.run(main())
