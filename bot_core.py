
import asyncio
import logging
import json
import re
import httpx
import os
import sys
import hashlib
import time
from datetime import datetime
from typing import Dict, Optional, List, Any, Union

from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode, ContentType
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
    InputFile, BufferedInputFile
)
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter

# --- Настройка логирования ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotCore")

def get_anon_id(user_id: int) -> str:
    return hashlib.md5(str(user_id).encode()).hexdigest()[:6].upper()

def format_admin_header(template: str, m: Message, settings: dict, is_first: bool = False, btn_text: str = "") -> str:
    """Формирование заголовка сообщения для администратора."""
    is_anon_global = settings.get('anonymousTopics', False)
    anon_id = get_anon_id(m.from_user.id)
    
    # Если это первый контакт или нажата кнопка-заявка, используем шаблон
    if (is_first or btn_text) and template:
        res = template
        if is_anon_global:
            res = res.replace("{{id}}", f"#{anon_id}")
            res = res.replace("{{name}}", "Аноним")
            res = res.replace("{{username}}", "@hidden")
        else:
            res = res.replace("{{id}}", str(m.from_user.id))
            res = res.replace("{{name}}", m.from_user.full_name or "User")
            res = res.replace("{{username}}", f"@{m.from_user.username}" if m.from_user.username else "none")
            
        res = res.replace("{{button}}", btn_text or "—")
        res = res.replace("{{text}}", m.text or m.caption or "[Медиа]")
        
        prefix = "🆕 <b>НОВОЕ ОБРАЩЕНИЕ</b>" if not btn_text else f"📩 <b>ЗАЯВКА: {btn_text}</b>"
        return f"{prefix}\n\n{res}\n\n"

    # Обычный заголовок сообщения
    parts = []
    if is_anon_global:
        parts.append(f"👤 <b>Аноним #{anon_id}</b>")
    else:
        show_name = settings.get('showHeaderName', True)
        show_user = settings.get('showHeaderUsername', True)
        show_id = settings.get('showHeaderId', True)
        
        # Fallback на Anon ID если всё выключено
        if not show_name and not show_user and not show_id:
            parts.append(f"👤 <b>User #{anon_id}</b>")
        else:
            if show_name: parts.append(f"<b>{m.from_user.full_name}</b>")
            if show_user and m.from_user.username: parts.append(f"(@{m.from_user.username})")
            if show_id: parts.append(f"ID: <code>{m.from_user.id}</code>")
    
    return f"📩 {' | '.join(parts)}\n\n"

class BotInstance:
    def __init__(self, config_data: dict):
        self.bot_id = config_data.get('id')
        self.token = config_data.get('token')
        self.sb_url = os.getenv("SUPABASE_URL", "").rstrip('/')
        self.sb_key = os.getenv("SUPABASE_KEY", "")
        
        self.bot = Bot(token=self.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher()
        self.router = Router()
        
        self.msg_map = {} 
        self.user_flood_cache = {} 
        self.is_running = True
        self.license_active = True
        
        self.admin_id = None
        self.connected_users = []
        self.sync_queue = asyncio.Queue()
        
        self.refresh_config(config_data)

    def refresh_config(self, data: dict):
        inner_config = data.get('config', {}) if isinstance(data.get('config'), dict) else {}
        flat_data = {**inner_config, **data}
        
        try:
            raw_admin = flat_data.get('adminChatId')
            if raw_admin: self.admin_id = int(str(raw_admin).strip())
        except: pass

        self.buttons = flat_data.get('buttons', [])
        self.triggers = flat_data.get('triggers', [])
        self.welcome_message = flat_data.get('welcomeMessage', 'Привет!')
        self.settings = flat_data.get('settings', {})
        self.license_expires_at = int(flat_data.get('license_expires_at', 0))
        
        self.use_topics = self.settings.get('useTopics', False)
        self.topic_per_request = self.settings.get('topicPerRequest', False)
        self.admin_template = self.settings.get('adminMessageTemplate', "")
        
        self.rate_limit = float(self.settings.get('rateLimit', 1.0)) 
        self.auto_ban_threshold = int(self.settings.get('autoBanThreshold', 3))

        self.connected_users = flat_data.get('connectedUsers', [])
        self.stats = flat_data.get('stats') or {"totalMessages": 0, "incomingToday": 0, "outgoingToday": 0, "history": []}

    async def check_flood(self, user_id: int) -> bool:
        if self.rate_limit <= 0: return False
        now = time.time()
        last_sent = self.user_flood_cache.get(user_id, 0)
        if now - last_sent < self.rate_limit: return True
        self.user_flood_cache[user_id] = now
        return False

    async def update_user_status(self, user_id: int, **kwargs):
        updated = False
        for u in self.connected_users:
            if u['id'] == user_id:
                for k, v in kwargs.items(): 
                    if u.get(k) != v:
                        u[k] = v
                        updated = True
                break
        if updated:
            await self.sync_queue.put(("config", {}))

    async def notify_admin_about_event(self, text: str, thread_id: int = None):
        """Отправка системного уведомления администратору."""
        if not self.admin_id: return
        try:
            await self.bot.send_message(self.admin_id, f"ℹ️ <b>Система:</b>\n{text}", message_thread_id=thread_id)
        except: pass

    async def db_sync_worker(self):
        async with httpx.AsyncClient() as client:
            headers = {"apikey": self.sb_key, "Authorization": f"Bearer {self.sb_key}", "Content-Type": "application/json"}
            while self.is_running:
                action, data = await self.sync_queue.get()
                try:
                    if action == "msg":
                        await client.post(f"{self.sb_url}/rest/v1/bot_messages", json=data, headers=headers)
                    elif action == "config":
                        res = await client.get(f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}", headers=headers)
                        if res.status_code == 200 and res.json():
                            db_bot = res.json()[0]
                            db_config = db_bot.get("config", {})
                            new_config = {**db_config, "connectedUsers": self.connected_users, "stats": self.stats}
                            await client.patch(f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}", json={"config": new_config}, headers=headers)
                except Exception as e: logger.error(f"Worker sync error: {e}")
                finally: self.sync_queue.task_done()

    async def update_counters(self, direction: str):
        self.stats["totalMessages"] = self.stats.get("totalMessages", 0) + 1
        key = "incomingToday" if direction == "incoming" else "outgoingToday"
        self.stats[key] = self.stats.get(key, 0) + 1
        today = datetime.now().strftime("%d.%m")
        if "history" not in self.stats: self.stats["history"] = []
        found = False
        for pt in self.stats["history"]:
            if pt.get("date") == today:
                pt[direction] = pt.get(direction, 0) + 1
                pt["totalUsers"] = len(self.connected_users)
                pt["activeUsers"] = len([u for u in self.connected_users if u.get('is_active', True) and not u.get('is_banned')])
                found = True
                break
        if not found:
            self.stats["history"].append({"date": today, "incoming": 1 if direction == "incoming" else 0, "outgoing": 1 if direction == "outgoing" else 0, "totalUsers": len(self.connected_users), "activeUsers": len([u for u in self.connected_users if u.get('is_active', True)])})

    async def log_it(self, user_id, name, text, is_admin=False):
        await self.sync_queue.put(("msg", {"bot_id": self.bot_id, "user_id": user_id, "first_name": name, "message_text": text[:900] if text else "[Медиа]", "is_from_admin": is_admin}))
        await self.update_counters("incoming" if not is_admin else "outgoing")

    async def get_user(self, m: Message):
        uid = m.from_user.id
        user = next((u for u in self.connected_users if u['id'] == uid), None)
        is_new = False
        if not user:
            is_new = True
            user = {"id": uid, "first_name": m.from_user.first_name, "username": m.from_user.username, "is_banned": False, "is_active": True, "warns": 0, "joined_at": int(time.time())}
            self.connected_users.append(user)
            await self.sync_queue.put(("config", {}))
        elif not user.get("is_active", True):
            user["is_active"] = True
            await self.sync_queue.put(("config", {}))
        return user, is_new

    async def ensure_topic(self, user, force_new: bool = False):
        if not self.use_topics or not self.admin_id: return None
        if not force_new and user.get("last_topic_id"): return user["last_topic_id"]
        try:
            topic_name = f"User #{get_anon_id(user['id'])}" if self.settings.get('anonymousTopics', False) else f"{user['first_name']} [{user['id']}]"
            topic = await self.bot.create_forum_topic(self.admin_id, topic_name)
            user["last_topic_id"] = topic.message_thread_id
            await self.sync_queue.put(("config", {}))
            return topic.message_thread_id
        except: return None

    async def forward_to_admin(self, m: Message, user: dict, is_first: bool = False, btn_text: str = ""):
        if not self.admin_id: return
        force_new_topic = self.topic_per_request and (btn_text != "" or is_first)
        thread_id = await self.ensure_topic(user, force_new=force_new_topic) if self.use_topics else None
        header = format_admin_header(self.admin_template, m, self.settings, is_first, btn_text)
        try:
            if m.text: sent = await self.bot.send_message(self.admin_id, f"{header}{m.text}", message_thread_id=thread_id)
            elif m.photo: sent = await self.bot.send_photo(self.admin_id, m.photo[-1].file_id, caption=f"{header}{m.caption or ''}", message_thread_id=thread_id)
            elif m.video: sent = await self.bot.send_video(self.admin_id, m.video.file_id, caption=f"{header}{m.caption or ''}", message_thread_id=thread_id)
            else:
                if header: await self.bot.send_message(self.admin_id, header, message_thread_id=thread_id)
                sent = await self.bot.copy_message(self.admin_id, m.chat.id, m.message_id, message_thread_id=thread_id)
            
            if sent: self.msg_map[sent.message_id] = user['id']
        except Exception as e: logger.error(f"Forward error: {e}")

    async def handle_admin_reply(self, m: Message):
        target_id = None
        if m.message_thread_id:
            u = next((u for u in self.connected_users if u.get("last_topic_id") == m.message_thread_id), None)
            if u: target_id = u["id"]
        if not target_id and m.reply_to_message:
            target_id = self.msg_map.get(m.reply_to_message.message_id)
            if not target_id:
                match = re.search(r"ID: (\d+)", m.reply_to_message.text or m.reply_to_message.caption or "")
                if match: target_id = int(match.group(1))
        if target_id:
            try:
                await self.bot.copy_message(target_id, m.chat.id, m.message_id)
                await self.log_it(target_id, "Admin", m.text or "[Медиа]", is_admin=True)
            except TelegramForbiddenError:
                await self.update_user_status(target_id, is_active=False)
                await m.reply("⚠️ <b>Ошибка:</b> Юзер заблокировал бота. Статус в CRM обновлен.")
                if self.settings.get('notifyOnBlock', True):
                    await self.notify_admin_about_event(f"Пользователь {target_id} заблокировал бота.", thread_id=m.message_thread_id)
            except Exception as e: await m.reply(f"❌ Ошибка отправки: {e}")

    async def register_handlers(self):
        @self.router.message(CommandStart())
        async def cmd_start(m: Message):
            if not self.license_active: return
            user, is_new = await self.get_user(m)
            if user.get("is_banned"): return
            await m.answer(self.welcome_message, reply_markup=self.get_kb())
            await self.log_it(user['id'], m.from_user.full_name, "/start")
            
            if is_new and self.settings.get('notifyOnStart', True):
                await self.notify_admin_about_event(f"Новый пользователь: {m.from_user.full_name} (@{m.from_user.username or '—'})")

        @self.router.message(F.chat.id == self.admin_id)
        async def admin_input(m: Message):
            if not self.license_active: return
            
            # --- КОМАНДЫ МОДЕРАЦИИ (Должны быть в приоритете) ---
            if m.text and (m.text.startswith("/") or m.text.startswith("!")):
                cmd_full = m.text.lower().split()
                cmd = cmd_full[0][1:]
                target = None
                
                # Поиск цели команды
                if m.message_thread_id:
                    target = next((u for u in self.connected_users if u.get("last_topic_id") == m.message_thread_id), None)
                if not target and m.reply_to_message:
                    uid = self.msg_map.get(m.reply_to_message.message_id)
                    if uid: target = next((u for u in self.connected_users if u['id'] == uid), None)
                
                if target:
                    uid = target['id']
                    if cmd == "ban":
                        await self.update_user_status(uid, is_banned=True)
                        try: await self.bot.send_message(uid, "🚫 <b>Ваш доступ к боту заблокирован администратором.</b>")
                        except: pass
                        await m.reply(f"✅ Пользователь {uid} забанен.")
                        return # Прерываем, чтобы текст команды не улетел юзеру
                    elif cmd == "unban":
                        await self.update_user_status(uid, is_banned=False)
                        try: await self.bot.send_message(uid, "✅ <b>Ваш доступ восстановлен.</b>")
                        except: pass
                        await m.reply(f"✅ Пользователь {uid} разбанен.")
                        return
                    elif cmd == "warn":
                        new_warns = (target.get("warns", 0)) + 1
                        await self.update_user_status(uid, warns=new_warns)
                        if self.auto_ban_threshold > 0 and new_warns >= self.auto_ban_threshold:
                            await self.update_user_status(uid, is_banned=True)
                            try: await self.bot.send_message(uid, f"🚫 <b>Авто-бан:</b> Лимит варнов ({new_warns}) превышен.")
                            except: pass
                            await m.reply(f"🚨 <b>Авто-бан!</b> У юзера {uid} уже {new_warns} варнов.")
                        else:
                            try: await self.bot.send_message(uid, f"⚠️ <b>Предупреждение!</b> У вас {new_warns} варнов из {self.auto_ban_threshold}.")
                            except: pass
                            await m.reply(f"⚠️ Варн выдан ({new_warns}/{self.auto_ban_threshold}).")
                        return
                    elif cmd == "unwarn":
                        new_warns = max(0, target.get("warns", 0) - 1)
                        await self.update_user_status(uid, warns=new_warns)
                        await m.reply(f"✅ Варн снят ({new_warns} осталось).")
                        return

            # --- ОБЫЧНЫЙ ОТВЕТ (Если не команда) ---
            if m.reply_to_message or (self.use_topics and m.message_thread_id):
                await self.handle_admin_reply(m)

        @self.router.message()
        async def global_handler(m: Message):
            if not self.license_active: return
            if self.admin_id and m.chat.id == self.admin_id: return
            user, is_new = await self.get_user(m)
            if user.get("is_banned"): return
            if await self.check_flood(user['id']): return

            if m.text:
                txt = m.text.lower().strip()
                for b in self.buttons:
                    if b.get('text') and b['text'].lower() == txt:
                        is_req = b.get('type') == 'request'
                        await self.forward_to_admin(m, user, is_first=is_new, btn_text=b['text'] if is_req else "")
                        if b.get('response'): await m.answer(b['response'])
                        await self.log_it(user['id'], m.from_user.full_name, f"BTN: {b['text']}")
                        return
                for t in self.triggers:
                    if t.get('keyword') and t['keyword'].lower() in txt:
                        await m.answer(t['response'])
                        await self.log_it(user['id'], m.from_user.full_name, f"TRIGGER: {t['keyword']}")
                        return
            
            await self.forward_to_admin(m, user, is_first=is_new)
            await self.log_it(user['id'], m.from_user.full_name, m.text or "[Медиа]")

    def get_kb(self):
        vbs = [b for b in self.buttons if b.get('text')]
        if not vbs: return None
        rows = []
        for i in range(0, len(vbs), 2):
            rows.append([KeyboardButton(text=b['text']) for b in vbs[i:i+2]])
        return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

    async def run(self):
        asyncio.create_task(self.db_sync_worker())
        await self.register_handlers()
        self.dp.include_router(self.router)
        await self.dp.start_polling(self.bot)

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    try:
        with open(sys.argv[1], 'r', encoding='utf-8') as f: cfg = json.load(f)
        asyncio.run(BotInstance(cfg).run())
    except Exception as e: logger.error(f"FATAL: {e}")
