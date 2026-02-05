
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
    is_anon = settings.get('anonymousTopics', False)
    anon_id = get_anon_id(m.from_user.id)
    
    # Если это первый контакт или кнопка И задан шаблон уведомления
    if (is_first or btn_text) and template:
        res = template
        if is_anon:
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

    # Стандартная компактная шапка (используется если шаблон пуст или это обычное сообщение)
    parts = []
    show_name = settings.get('showHeaderName', True)
    show_user = settings.get('showHeaderUsername', True)
    show_id = settings.get('showHeaderId', True)

    if is_anon:
        parts.append(f"👤 <b>Аноним #{anon_id}</b>")
    else:
        if show_name: 
            parts.append(f"<b>{m.from_user.full_name}</b>")
        if show_user and m.from_user.username: 
            parts.append(f"(@{m.from_user.username})")
        if show_id: 
            parts.append(f"ID: <code>{m.from_user.id}</code>")
    
    if not parts:
        parts.append(f"👤 User <code>#{anon_id}</code>")
        
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
        self.stats = {}
        self.buttons = []
        self.triggers = []
        self.welcome_message = ""
        self.admin_template = ""
        self.auto_ban_threshold = 0

        self.refresh_config(config_data)

    def refresh_config(self, data: dict):
        inner_config = data.get('config', {}) if isinstance(data.get('config'), dict) else {}
        flat_data = {**inner_config, **data}
        
        raw_admin = flat_data.get('adminChatId')
        try:
            if raw_admin:
                self.admin_id = int(str(raw_admin).strip())
        except:
            pass

        self.buttons = flat_data.get('buttons', [])
        self.triggers = flat_data.get('triggers', [])
        self.welcome_message = flat_data.get('welcomeMessage', 'Привет!')
        self.settings = flat_data.get('settings', {})
        
        self.use_topics = self.settings.get('useTopics', False)
        self.topic_per_request = self.settings.get('topicPerRequest', False)
        self.admin_template = self.settings.get('adminMessageTemplate', "")
        self.auto_ban_threshold = int(self.settings.get('autoBanThreshold', 0))

        new_users = flat_data.get('connectedUsers', [])
        if not self.connected_users:
            self.connected_users = new_users
        else:
            for nu in new_users:
                found = False
                for ou in self.connected_users:
                    if ou['id'] == nu['id']:
                        ou['is_banned'] = nu.get('is_banned', False)
                        ou['warns'] = nu.get('warns', 0)
                        ou['last_topic_id'] = nu.get('last_topic_id', ou.get('last_topic_id'))
                        found = True
                        break
                if not found:
                    self.connected_users.append(nu)

        self.stats = flat_data.get('stats') or {
            "totalMessages": 0, "incomingToday": 0, "outgoingToday": 0, "history": []
        }
        
        logger.info(f"[{self.bot_id}] Sync Done. Topics={self.use_topics}, Admin={self.admin_id}")

    async def remote_sync_poller(self):
        async with httpx.AsyncClient() as client:
            headers = {"apikey": self.sb_key, "Authorization": f"Bearer {self.sb_key}"}
            while self.is_running:
                await asyncio.sleep(30)
                try:
                    res = await client.get(f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}", headers=headers)
                    if res.status_code == 200 and res.json():
                        self.refresh_config(res.json()[0])
                except Exception as e:
                    logger.error(f"Sync error: {e}")

    async def db_sync_worker(self):
        async with httpx.AsyncClient() as client:
            headers = {
                "apikey": self.sb_key, "Authorization": f"Bearer {self.sb_key}", 
                "Content-Type": "application/json"
            }
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
                            new_config = {
                                **db_config,
                                "connectedUsers": self.connected_users,
                                "stats": self.stats
                            }
                            await client.patch(
                                f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}", 
                                json={"config": new_config}, 
                                headers=headers
                            )
                except Exception as e:
                    logger.error(f"Worker error: {e}")
                finally:
                    self.sync_queue.task_done()

    async def update_counters(self, direction: str):
        self.stats["totalMessages"] = self.stats.get("totalMessages", 0) + 1
        key = "incomingToday" if direction == "incoming" else "outgoingToday"
        self.stats[key] = self.stats.get(key, 0) + 1
        
        today = datetime.now().strftime("%d.%m")
        if "history" not in self.stats or not isinstance(self.stats["history"], list):
            self.stats["history"] = []
        
        found = False
        for pt in self.stats["history"]:
            if pt.get("date") == today:
                pt[direction] = pt.get(direction, 0) + 1
                found = True
                break
        
        if not found:
            self.stats["history"].append({"date": today, "incoming": 0, "outgoing": 0, "totalUsers": len(self.connected_users)})
            if len(self.stats["history"]) > 14: self.stats["history"].pop(0)

    async def log_it(self, user_id, name, text, is_admin=False):
        await self.sync_queue.put(("msg", {
            "bot_id": self.bot_id, "user_id": user_id, "first_name": name,
            "message_text": text[:900] if text else "[Медиа]",
            "is_from_admin": is_admin
        }))
        await self.update_counters("incoming" if not is_admin else "outgoing")
        await self.sync_queue.put(("config", {}))

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
        return user, is_new

    async def ensure_topic(self, user, force_new: bool = False):
        if not self.use_topics or not self.admin_id: 
            return None
            
        if not force_new and user.get("last_topic_id"): 
            return user["last_topic_id"]
        
        try:
            is_anon = self.settings.get('anonymousTopics', False)
            if is_anon:
                topic_name = f"User #{get_anon_id(user['id'])}"
            else:
                topic_name = f"{user['first_name']} [{user['id']}]"
                
            topic = await self.bot.create_forum_topic(self.admin_id, topic_name)
            user["last_topic_id"] = topic.message_thread_id
            self.last_header_time[user['id']] = 0 
            await self.sync_queue.put(("config", {}))
            logger.info(f"Created topic {topic.message_thread_id} for user {user['id']}")
            return topic.message_thread_id
        except Exception as e:
            logger.error(f"Topic creation error: {e}")
            return None

    async def forward_to_admin(self, m: Message, user: dict, is_first: bool = False, btn_text: str = ""):
        if not self.admin_id: return
        
        force_new_topic = self.topic_per_request and (btn_text != "" or is_first)
        thread_id = None
        if self.use_topics:
            thread_id = await self.ensure_topic(user, force_new=force_new_topic)

        now = time.time()
        last_sent = self.last_header_time.get(user['id'], 0)
        
        header = ""
        # КРИТИЧЕСКОЕ ИЗМЕНЕНИЕ:
        # Если топики выключены (self.use_topics == False), мы ВСЕГДА шлем шапку, 
        # чтобы сообщения от разных юзеров в одном чате не перемешивались визуально.
        # Если топики включены, сохраняем логику "раз в 10 минут" или по событию.
        if not self.use_topics or is_first or btn_text or (now - last_sent) > 600:
            header = format_admin_header(self.admin_template, m, self.settings, is_first, btn_text)
            if header: self.last_header_time[user['id']] = now

        try:
            sent = None
            if m.text:
                sent = await self.bot.send_message(self.admin_id, f"{header}{m.text}", message_thread_id=thread_id)
            elif m.photo:
                sent = await self.bot.send_photo(self.admin_id, m.photo[-1].file_id, caption=f"{header}{m.caption or ''}", message_thread_id=thread_id)
            elif m.video:
                sent = await self.bot.send_video(self.admin_id, m.video.file_id, caption=f"{header}{m.caption or ''}", message_thread_id=thread_id)
            elif m.document:
                sent = await self.bot.send_document(self.admin_id, m.document.file_id, caption=f"{header}{m.caption or ''}", message_thread_id=thread_id)
            else:
                if header: await self.bot.send_message(self.admin_id, header, message_thread_id=thread_id)
                sent = await self.bot.copy_message(self.admin_id, m.chat.id, m.message_id, message_thread_id=thread_id)
            
            if sent:
                self.msg_map[sent.message_id] = user['id']
                if len(self.msg_map) > 5000: self.msg_map.pop(next(iter(self.msg_map)))
        except Exception as e:
            logger.error(f"Forward error: {e}")

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
            except Exception as e:
                await m.reply(f"❌ Не удалось отправить: {e}")

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
                cmd_full = m.text.lower().split()
                cmd = cmd_full[0][1:]
                target = None
                
                if m.message_thread_id:
                    target = next((u for u in self.connected_users if u.get("last_topic_id") == m.message_thread_id), None)
                
                if not target and m.reply_to_message:
                    uid = self.msg_map.get(m.reply_to_message.message_id)
                    if uid: target = next((u for u in self.connected_users if u['id'] == uid), None)
                
                if target:
                    uid = target['id']
                    if cmd == "ban":
                        target['is_banned'] = True
                        try: await self.bot.send_message(uid, "🚫 <b>Вы были заблокированы администратором.</b>")
                        except: pass
                        await m.reply(f"✅ Пользователь <code>{uid}</code> забанен.")
                    elif cmd == "unban":
                        target['is_banned'] = False
                        try: await self.bot.send_message(uid, "✅ <b>Ваша блокировка снята администратором.</b>")
                        except: pass
                        await m.reply(f"✅ Пользователь <code>{uid}</code> разбанен.")
                    elif cmd == "warn":
                        target['warns'] = target.get('warns', 0) + 1
                        curr = target['warns']
                        is_auto = self.auto_ban_threshold > 0 and curr >= self.auto_ban_threshold
                        if is_auto: target['is_banned'] = True
                        try:
                            msg = f"⚠️ <b>Вам выдано предупреждение!</b> ({curr}/{self.auto_ban_threshold or '∞'})"
                            if is_auto: msg += "\n\n🚫 Авто-бан за лимит варнов."
                            await self.bot.send_message(uid, msg)
                        except: pass
                        await m.reply(f"✅ Варн ({curr})." + (" [AUTO-BAN]" if is_auto else ""))
                    elif cmd == "unwarn":
                        target['warns'] = max(0, target.get('warns', 0) - 1)
                        await m.reply(f"✅ Варн снят ({target['warns']})")
                    
                    await self.sync_queue.put(("config", {}))
                    return

            if m.reply_to_message or (self.use_topics and m.message_thread_id):
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
                        is_req = b.get('type') == 'request'
                        await self.forward_to_admin(m, user, is_first=is_new, btn_text=b['text'] if is_req else "")
                        if b.get('response'): await m.answer(b['response'])
                        await self.log_it(user['id'], m.from_user.full_name, f"Кнопка: {b['text']}")
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
        rows = []
        for i in range(0, len(vbs), 2):
            rows.append([KeyboardButton(text=b['text']) for b in vbs[i:i+2]])
        return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

    async def run(self):
        asyncio.create_task(self.db_sync_worker())
        asyncio.create_task(self.remote_sync_poller())
        await self.register_handlers()
        self.dp.include_router(self.router)
        logger.info(f"🚀 Инстанс {self.bot_id} запущен (Топики: {self.use_topics})")
        await self.dp.start_polling(self.bot)

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    try:
        with open(sys.argv[1], 'r', encoding='utf-8') as f: cfg = json.load(f)
        asyncio.run(BotInstance(cfg).run())
    except Exception as e:
        logger.error(f"FATAL ERROR: {e}")
