
import asyncio
import logging
import json
import re
import httpx
import os
import sys
import hashlib
import time
import signal
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
    is_anon = settings.get('anonymousTopics', False)
    anon_id = get_anon_id(m.from_user.id)
    
    if (is_first or btn_text) and template:
        res = template
        if is_anon:
            res = res.replace("{{id}}", f"#{anon_id}").replace("{{name}}", "Аноним").replace("{{username}}", "@hidden")
        else:
            res = res.replace("{{id}}", str(m.from_user.id))
            res = res.replace("{{name}}", m.from_user.full_name or "User")
            res = res.replace("{{username}}", f"@{m.from_user.username}" if m.from_user.username else "none")
            
        res = res.replace("{{button}}", btn_text or "—").replace("{{text}}", m.text or m.caption or "[Медиа]")
        prefix = "🆕 <b>НОВОЕ ОБРАЩЕНИЕ</b>" if not btn_text else f"📩 <b>ЗАЯВКА: {btn_text}</b>"
        return f"{prefix}\n\n{res}\n\n"

    parts = []
    if is_anon:
        parts.append(f"👤 <b>Аноним #{anon_id}</b>")
    else:
        if settings.get('showHeaderName', True): parts.append(f"<b>{m.from_user.full_name}</b>")
        if settings.get('showHeaderUsername', True) and m.from_user.username: parts.append(f"(@{m.from_user.username})")
        if settings.get('showHeaderId', True): parts.append(f"ID: <code>{m.from_user.id}</code>")
    
    if not parts: parts.append(f"👤 User <code>#{anon_id}</code>")
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
        self.last_header_time = {} 
        self.connected_users = []
        self.sync_queue = asyncio.Queue()
        self.is_running = True
        
        self.admin_id = None
        self.use_topics = False
        self.topic_per_request = False
        self.settings = {}
        self.stats = {
            "totalMessages": 0, "incomingToday": 0, "outgoingToday": 0, "history": []
        }
        self.buttons = []
        self.triggers = []
        self.welcome_message = ""
        self.admin_template = ""
        self.auto_ban_threshold = 0

        self.refresh_config(config_data, initial=True)

    def refresh_config(self, data: dict, initial: bool = False):
        old_users = {u['id']: u for u in self.connected_users}
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
        self.use_topics = self.settings.get('useTopics', False)
        self.topic_per_request = self.settings.get('topicPerRequest', False)
        self.admin_template = self.settings.get('adminMessageTemplate', "")
        self.auto_ban_threshold = int(self.settings.get('autoBanThreshold', 0))

        # Обновление списка юзеров
        self.connected_users = flat_data.get('connectedUsers', [])

        if not initial:
            for u in self.connected_users:
                old_u = old_users.get(u['id'])
                if old_u:
                    if u.get('is_banned') and not old_u.get('is_banned'):
                        asyncio.create_task(self.notify_user(u['id'], "🚫 <b>Доступ ограничен.</b>\nВы заблокированы администратором."))
                    elif not u.get('is_banned') and old_u.get('is_banned'):
                        asyncio.create_task(self.notify_user(u['id'], "✅ <b>Доступ восстановлен.</b>\nВы снова можете отправлять сообщения."))

        # Обновление статистики
        incoming_stats = flat_data.get('stats')
        if incoming_stats and isinstance(incoming_stats, dict):
            # Синхронизируем общие счетчики
            self.stats["totalMessages"] = max(self.stats.get("totalMessages", 0), int(incoming_stats.get("totalMessages", 0)))
            self.stats["incomingToday"] = int(incoming_stats.get("incomingToday", 0))
            self.stats["outgoingToday"] = int(incoming_stats.get("outgoingToday", 0))
            
            if incoming_stats.get("history"):
                self.stats["history"] = incoming_stats["history"]
        
        if not self.stats.get("history"): self.stats["history"] = []

    async def notify_user(self, user_id: int, text: str):
        try:
            await self.bot.send_message(user_id, text)
        except TelegramForbiddenError:
            await self.mark_user_inactive(user_id)
        except Exception: pass

    async def mark_user_inactive(self, user_id: int):
        """Помечает пользователя как 'Лив' (заблокировал бота)."""
        for u in self.connected_users:
            if u['id'] == user_id:
                if u.get('is_active', True):
                    u['is_active'] = False
                    logger.info(f"User {user_id} marked as INACTIVE (blocked bot)")
                    await self.sync_queue.put(("config", {}))
                break

    async def remote_sync_poller(self):
        """Опрос БД для синхронизации модерации и конфига."""
        async with httpx.AsyncClient() as client:
            headers = {"apikey": self.sb_key, "Authorization": f"Bearer {self.sb_key}"}
            while self.is_running:
                await asyncio.sleep(5)
                try:
                    res = await client.get(f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}", headers=headers)
                    if res.status_code == 200 and res.json():
                        self.refresh_config(res.json()[0])
                except Exception as e:
                    logger.error(f"Sync error: {e}")

    async def db_sync_worker(self):
        """Пуш изменений в Supabase."""
        async with httpx.AsyncClient() as client:
            headers = {"apikey": self.sb_key, "Authorization": f"Bearer {self.sb_key}", "Content-Type": "application/json"}
            while self.is_running:
                try:
                    action, data = await self.sync_queue.get()
                    if action == "msg":
                        await client.post(f"{self.sb_url}/rest/v1/bot_messages", json=data, headers=headers)
                    elif action == "config":
                        # Перед сохранением берем актуальный конфиг из базы, чтобы не затереть чужие изменения
                        res = await client.get(f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}", headers=headers)
                        if res.status_code == 200 and res.json():
                            db_bot = res.json()[0]
                            db_config = db_bot.get("config", {})
                            # Сливаем локальных юзеров и стату
                            new_config = {**db_config, "connectedUsers": self.connected_users, "stats": self.stats}
                            await client.patch(f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}", json={"config": new_config}, headers=headers)
                    self.sync_queue.task_done()
                except Exception as e:
                    logger.error(f"Worker error: {e}")
                    await asyncio.sleep(2)

    async def update_counters(self, direction: str):
        self.stats["totalMessages"] += 1
        key = "incomingToday" if direction == "incoming" else "outgoingToday"
        self.stats[key] += 1
        
        today = datetime.now().strftime("%d.%m")
        # Считаем живых: активны (не удалили бота) И не забанены нами
        active_count = len([u for u in self.connected_users if u.get('is_active', True) and not u.get('is_banned', False)])
        total_count = len(self.connected_users)
        
        history = self.stats.get("history", [])
        found = False
        for pt in history:
            if pt.get("date") == today:
                pt[direction] = pt.get(direction, 0) + 1
                pt["totalUsers"] = total_count
                pt["activeUsers"] = active_count
                found = True
                break
        
        if not found:
            history.append({
                "date": today, 
                "incoming": 1 if direction=="incoming" else 0, 
                "outgoing": 1 if direction=="outgoing" else 0, 
                "totalUsers": total_count,
                "activeUsers": active_count
            })
            if len(history) > 14: history.pop(0)
        
        self.stats["history"] = history
        await self.sync_queue.put(("config", {}))

    async def log_it(self, user_id, name, text, is_admin=False):
        await self.sync_queue.put(("msg", {
            "bot_id": self.bot_id, "user_id": user_id, "first_name": name,
            "message_text": text[:900] if text else "[Медиа]",
            "is_from_admin": is_admin
        }))
        await self.update_counters("incoming" if not is_admin else "outgoing")

    async def get_user(self, m: Message):
        uid = m.from_user.id
        user = next((u for u in self.connected_users if u['id'] == uid), None)
        is_new = False
        if not user:
            is_new = True
            user = {
                "id": uid, "first_name": m.from_user.first_name, "username": m.from_user.username,
                "is_banned": False, "is_active": True, "warns": 0, "last_topic_id": None,
                "joined_at": int(time.time())
            }
            self.connected_users.append(user)
            await self.sync_queue.put(("config", {}))
        else:
            # Если юзер написал нам, значит он разблокировал бота
            if not user.get('is_active', True):
                user['is_active'] = True
                await self.sync_queue.put(("config", {}))
        return user, is_new

    async def forward_to_admin(self, m: Message, user: dict, is_first: bool = False, btn_text: str = ""):
        if not self.admin_id: return
        thread_id = None
        if self.use_topics:
            force_new = self.topic_per_request and (btn_text != "" or is_first)
            thread_id = await self.ensure_topic(user, force_new=force_new)

        now = time.time()
        header = ""
        if not self.use_topics or is_first or btn_text or (now - self.last_header_time.get(user['id'], 0)) > 600:
            header = format_admin_header(self.admin_template, m, self.settings, is_first, btn_text)
            if header: self.last_header_time[user['id']] = now

        try:
            if m.text: await self.bot.send_message(self.admin_id, f"{header}{m.text}", message_thread_id=thread_id)
            elif m.photo: await self.bot.send_photo(self.admin_id, m.photo[-1].file_id, caption=f"{header}{m.caption or ''}", message_thread_id=thread_id)
            elif m.video: await self.bot.send_video(self.admin_id, m.video.file_id, caption=f"{header}{m.caption or ''}", message_thread_id=thread_id)
            elif m.document: await self.bot.send_document(self.admin_id, m.document.file_id, caption=f"{header}{m.caption or ''}", message_thread_id=thread_id)
            else:
                if header: await self.bot.send_message(self.admin_id, header, message_thread_id=thread_id)
                await self.bot.copy_message(self.admin_id, m.chat.id, m.message_id, message_thread_id=thread_id)
        except TelegramForbiddenError:
            await self.mark_user_inactive(user['id'])
        except Exception: pass

    async def ensure_topic(self, user, force_new: bool = False):
        if not self.use_topics or not self.admin_id: return None
        if not force_new and user.get("last_topic_id"): return user["last_topic_id"]
        try:
            is_anon = self.settings.get('anonymousTopics', False)
            topic_name = f"User #{get_anon_id(user['id'])}" if is_anon else f"{user['first_name']} [{user['id']}]"
            topic = await self.bot.create_forum_topic(self.admin_id, topic_name)
            user["last_topic_id"] = topic.message_thread_id
            await self.sync_queue.put(("config", {}))
            return topic.message_thread_id
        except Exception: return None

    async def handle_admin_reply(self, m: Message):
        target_id = None
        if m.message_thread_id:
            u = next((u for u in self.connected_users if u.get("last_topic_id") == m.message_thread_id), None)
            if u: target_id = u["id"]
        if not target_id and m.reply_to_message:
            match = re.search(r"ID: (\d+)", m.reply_to_message.text or m.reply_to_message.caption or "")
            if match: target_id = int(match.group(1))

        if target_id:
            try:
                await self.bot.copy_message(target_id, m.chat.id, m.message_id)
                await self.log_it(target_id, "Admin", m.text or "[Медиа]", is_admin=True)
            except TelegramForbiddenError:
                await self.mark_user_inactive(target_id)
                await m.reply("❌ Бот заблокирован пользователем. Сообщение не доставлено.")
            except Exception as e: await m.reply(f"❌ Ошибка: {e}")

    async def register_handlers(self):
        @self.router.message(CommandStart())
        async def cmd_start(m: Message):
            user, is_new = await self.get_user(m)
            if user.get("is_banned"): return
            await m.answer(self.welcome_message, reply_markup=self.get_kb())
            await self.log_it(user['id'], m.from_user.full_name, "/start")

        @self.router.message(F.chat.id == self.admin_id)
        async def admin_input(m: Message):
            if m.text and m.text.startswith(("/", "!")):
                cmd = m.text.lower().split()[0][1:]
                target = None
                if m.message_thread_id: target = next((u for u in self.connected_users if u.get("last_topic_id") == m.message_thread_id), None)
                if not target and m.reply_to_message:
                    match = re.search(r"ID: (\d+)", m.reply_to_message.text or m.reply_to_message.caption or "")
                    if match: target = next((u for u in self.connected_users if u['id'] == int(match.group(1))), None)
                
                if target:
                    if cmd == "ban": target['is_banned'] = True
                    elif cmd == "unban": target['is_banned'] = False
                    elif cmd == "warn": 
                        target['warns'] = target.get('warns', 0) + 1
                        if self.auto_ban_threshold > 0 and target['warns'] >= self.auto_ban_threshold: target['is_banned'] = True
                    elif cmd == "unwarn":
                        target['warns'] = max(0, target.get('warns', 0) - 1)
                    
                    await self.sync_queue.put(("config", {}))
                    await m.reply("✅ Изменения применены")
                    return
            await self.handle_admin_reply(m)

        @self.router.message()
        async def global_handler(m: Message):
            if self.admin_id and m.chat.id == self.admin_id: return
            user, is_new = await self.get_user(m)
            if user.get("is_banned"): return
            if m.text:
                txt = m.text.lower().strip()
                for b in self.buttons:
                    if b.get('text') and b['text'].lower() == txt:
                        await self.forward_to_admin(m, user, is_first=is_new, btn_text=b['text'] if b.get('type')=='request' else "")
                        if b.get('response'): await m.answer(b['response'])
                        await self.log_it(user['id'], m.from_user.full_name, f"Меню: {b['text']}")
                        return
                for t in self.triggers:
                    if t.get('keyword') and t['keyword'].lower() in txt:
                        await m.answer(t['response'])
                        await self.log_it(user['id'], m.from_user.full_name, f"Триггер: {t['keyword']}")
                        return
            await self.forward_to_admin(m, user, is_first=is_new)
            await self.log_it(user['id'], m.from_user.full_name, m.text or "[Медиа]")

    def get_kb(self):
        vbs = [b for b in self.buttons if b.get('text')]
        if not vbs: return None
        rows = [[KeyboardButton(text=vbs[i]['text'])] for i in range(len(vbs))]
        return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

    async def shutdown(self, signal_type):
        self.is_running = False
        await self.sync_queue.put(("config", {}))
        await asyncio.sleep(1)
        await self.bot.session.close()
        sys.exit(0)

    async def run(self):
        loop = asyncio.get_running_loop()
        for s in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(s, lambda sig=s: asyncio.create_task(self.shutdown(sig)))
        asyncio.create_task(self.db_sync_worker())
        asyncio.create_task(self.remote_sync_poller())
        await self.register_handlers()
        self.dp.include_router(self.router)
        logger.info(f"🚀 Бот {self.bot_id} готов к работе.")
        await self.dp.start_polling(self.bot)

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    try:
        with open(sys.argv[1], 'r', encoding='utf-8') as f: cfg = json.load(f)
        asyncio.run(BotInstance(cfg).run())
    except Exception as e: logger.error(f"FATAL: {e}")
