
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
    """Генерация короткого хеша для анонимных диалогов."""
    return hashlib.md5(str(user_id).encode()).hexdigest()[:6].upper()

def format_admin_header(template: str, m: Message, settings: dict, is_first: bool = False, btn_text: str = "") -> str:
    """Формирование заголовка сообщения для администратора."""
    # Если это первый контакт или спец-заявка - используем ТОЛЬКО шаблон пользователя
    if is_first:
        if not template:
            return "" # Если шаблона нет, возвращаем пустую строку (сигнал не слать ничего)
        
        res = template.replace("{{id}}", str(m.from_user.id))
        res = res.replace("{{name}}", m.from_user.full_name or "User")
        res = res.replace("{{username}}", f"@{m.from_user.username}" if m.from_user.username else "none")
        res = res.replace("{{button}}", btn_text or "—")
        res = res.replace("{{text}}", m.text or m.caption or "[Медиа]")
        return res

    # Иначе - компактный Livegram-заголовок на основе настроек чекбоксов
    parts = []
    if settings.get('showHeaderName', True): 
        parts.append(f"<b>{m.from_user.full_name}</b>")
    if settings.get('showHeaderUsername', True) and m.from_user.username: 
        parts.append(f"(@{m.from_user.username})")
    if settings.get('showHeaderId', True): 
        parts.append(f"ID: <code>{m.from_user.id}</code>")
    
    if not parts:
        parts.append(f"👤 User <code>#{get_anon_id(m.from_user.id)}</code>")
        
    return f"📩 {' | '.join(parts)}\n\n"

class BotInstance:
    def __init__(self, config_data: dict):
        self.full_config = config_data
        self.token = config_data.get('token')
        self.bot_id = config_data.get('id')
        
        # Настройка админа
        raw_admin = config_data.get('adminChatId')
        try:
            self.admin_id = int(str(raw_admin).strip()) if raw_admin else None
        except:
            self.admin_id = None
            logger.error(f"[{self.bot_id}] КРИТИЧЕСКАЯ ОШИБКА: ID администратора неверен.")

        # API Supabase
        self.sb_url = os.getenv("SUPABASE_URL", "").rstrip('/')
        self.sb_key = os.getenv("SUPABASE_KEY", "")
        
        # AIOGRAM
        self.bot = Bot(token=self.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher()
        self.router = Router()
        
        # Состояние процесса
        self.msg_map = {} # {admin_msg_id: user_id}
        self.last_header_time = {} # {user_id: timestamp}
        self.connected_users = []
        self.sync_queue = asyncio.Queue()
        self.is_running = True
        
        self.refresh_config(config_data)

    def refresh_config(self, data: dict):
        """Обновление конфига с умным мержем пользователей."""
        conf = data.get('config') or data
        self.buttons = conf.get('buttons', [])
        self.triggers = conf.get('triggers', [])
        self.welcome_message = conf.get('welcomeMessage', 'Привет! Напишите нам.')
        self.settings = conf.get('settings', {})
        
        # Мерж юзеров (чтобы не потерять данные о банах из панели)
        new_users = conf.get('connectedUsers', [])
        if not hasattr(self, 'connected_users') or not self.connected_users:
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

        # Статистика
        self.stats = conf.get('stats') or {
            "totalMessages": 0, "incomingToday": 0, "outgoingToday": 0, 
            "history": [], "bannedCount": 0
        }
        
        self.use_topics = self.settings.get('useTopics', False)
        self.admin_template = self.settings.get('adminMessageTemplate', "")
        self.auto_ban_threshold = self.settings.get('autoBanThreshold', 0)

    async def sync_stats_worker(self):
        """Фоновый менеджер истории статистики."""
        while self.is_running:
            today = datetime.now().strftime("%d.%m")
            history = self.stats.get("history", [])
            
            # Проверяем наличие записи на сегодня
            found = False
            for point in history:
                if point.get("date") == today:
                    point["totalUsers"] = len(self.connected_users)
                    found = True
                    break
            
            if not found:
                history.append({
                    "date": today, "incoming": 0, "outgoing": 0, 
                    "totalUsers": len(self.connected_users)
                })
                if len(history) > 14: history.pop(0)
                self.stats["history"] = history
            
            # Раз в минуту пушим состояние в БД
            await self.sync_queue.put(("config", {}))
            await asyncio.sleep(60)

    async def remote_sync_poller(self):
        """Периодическое получение изменений из БД (например, баны из UI)."""
        async with httpx.AsyncClient() as client:
            headers = {"apikey": self.sb_key, "Authorization": f"Bearer {self.sb_key}"}
            while self.is_running:
                await asyncio.sleep(20)
                try:
                    res = await client.get(f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}", headers=headers)
                    if res.status_code == 200 and res.json():
                        self.refresh_config(res.json()[0])
                except Exception as e:
                    logger.error(f"Remote poller error: {e}")

    async def db_sync_worker(self):
        """Главный воркер записи в Supabase."""
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
                        # Синхронизация всего состояния бота
                        payload = {
                            "config": {
                                **self.full_config.get("config", {}),
                                "connectedUsers": self.connected_users,
                                "stats": self.stats,
                                "settings": self.settings
                            }
                        }
                        await client.patch(f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}", json=payload, headers=headers)
                except Exception as e:
                    logger.error(f"DB Worker Sync Error: {e}")
                finally:
                    self.sync_queue.task_done()

    async def update_counters(self, direction: str):
        """Обновление счетчиков в памяти."""
        self.stats["totalMessages"] = self.stats.get("totalMessages", 0) + 1
        key = "incomingToday" if direction == "incoming" else "outgoingToday"
        self.stats[key] = self.stats.get(key, 0) + 1
        
        today = datetime.now().strftime("%d.%m")
        for pt in self.stats.get("history", []):
            if pt.get("date") == today:
                pt[direction] = pt.get(direction, 0) + 1
                break

    async def log_it(self, user_id, name, text, is_admin=False):
        """Логирование сообщения в очередь."""
        await self.sync_queue.put(("msg", {
            "bot_id": self.bot_id, "user_id": user_id, "first_name": name,
            "message_text": text[:900] if text else "[Медиа]",
            "is_from_admin": is_admin
        }))
        await self.update_counters("incoming" if not is_admin else "outgoing")

    async def get_user(self, m: Message):
        """Получение или регистрация пользователя."""
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

    async def ensure_topic(self, user):
        """Создание топика для форума."""
        if not self.use_topics or not self.admin_id: return None
        if user.get("last_topic_id"): return user["last_topic_id"]
        
        try:
            name = f"{user['first_name']} [{user['id']}]"
            topic = await self.bot.create_forum_topic(self.admin_id, name)
            user["last_topic_id"] = topic.message_thread_id
            self.last_header_time[user['id']] = 0 # Сброс хедера для нового топика
            await self.sync_queue.put(("config", {}))
            return topic.message_thread_id
        except: return None

    async def forward_to_admin(self, m: Message, user: dict, is_first: bool = False, btn_text: str = ""):
        """Умная пересылка контента администратору."""
        if not self.admin_id: return
        
        thread_id = await self.ensure_topic(user)
        now = time.time()
        last_sent = self.last_header_time.get(user['id'], 0)
        
        # Отправляем инфо-заголовок если прошло > 10 мин или это первый контакт
        header = format_admin_header(self.admin_template, m, self.settings, is_first, btn_text)
        
        # Если header не пустой, отправляем его
        if header and (is_first or (now - last_sent) > 600):
            await self.bot.send_message(self.admin_id, header, message_thread_id=thread_id)
            self.last_header_time[user['id']] = now

        try:
            sent = await self.bot.copy_message(self.admin_id, m.chat.id, m.message_id, message_thread_id=thread_id)
            self.msg_map[sent.message_id] = user['id']
            if len(self.msg_map) > 5000: self.msg_map.pop(next(iter(self.msg_map)))
        except Exception as e:
            logger.error(f"Forward error: {e}")

    async def handle_admin_reply(self, m: Message):
        """Обработка ответов админа (реплаи и топики)."""
        target_id = None
        # 1. По топику
        if m.message_thread_id:
            u = next((u for u in self.connected_users if u.get("last_topic_id") == m.message_thread_id), None)
            if u: target_id = u["id"]
        
        # 2. По реплаю (если топик не нашел или выключен)
        if not target_id and m.reply_to_message:
            target_id = self.msg_map.get(m.reply_to_message.message_id)
            if not target_id:
                # Поиск ID в тексте сообщения ( fallback )
                match = re.search(r"ID: (\d+)", m.reply_to_message.text or m.reply_to_message.caption or "")
                if match: target_id = int(match.group(1))

        if target_id:
            try:
                await self.bot.copy_message(target_id, m.chat.id, m.message_id)
                await self.log_it(target_id, "Admin", m.text or "[Медиа]", is_admin=True)
            except Exception as e:
                await m.reply(f"❌ Ошибка отправки: {e}")

    async def register_handlers(self):
        @self.router.message(CommandStart())
        async def cmd_start(m: Message):
            user, is_new = await self.get_user(m)
            if user.get("is_banned"): return
            await m.answer(self.welcome_message, reply_markup=self.get_kb())
            await self.forward_to_admin(m, user, is_first=True)
            await self.log_it(user['id'], m.from_user.full_name, "/start")

        @self.router.message(F.chat.id == self.admin_id)
        async def admin_input(m: Message):
            # Модерация через команды
            if m.text and m.text.startswith(("/", "!")):
                cmd_parts = m.text.lower().split()
                cmd = cmd_parts[0][1:]
                target_user = None
                
                if m.message_thread_id:
                    target_user = next((u for u in self.connected_users if u.get("last_topic_id") == m.message_thread_id), None)
                
                if target_user:
                    if cmd == "ban":
                        target_user['is_banned'] = True
                        await m.reply("🚫 Пользователь забанен.")
                    elif cmd == "unban":
                        target_user['is_banned'] = False
                        await m.reply("✅ Разбанен.")
                    elif cmd == "warn":
                        target_user['warns'] = target_user.get('warns', 0) + 1
                        await m.reply(f"⚠️ Варн выдан ({target_user['warns']})")
                    await self.sync_queue.put(("config", {}))
                    return

            # Если это не команда - значит ответ юзеру
            if m.reply_to_message or m.message_thread_id:
                await self.handle_admin_reply(m)

        @self.router.message()
        async def global_handler(m: Message):
            if self.admin_id and m.chat.id == self.admin_id: return
            user, is_new = await self.get_user(m)
            if user.get("is_banned"): return

            # Проверка кнопок и триггеров
            if m.text:
                txt = m.text.lower().strip()
                for b in self.buttons:
                    if b.get('text') and b['text'].lower() == txt:
                        if b.get('type') == 'request':
                            await self.forward_to_admin(m, user, is_first=True, btn_text=b['text'])
                        if b.get('response'):
                            await m.answer(b['response'])
                        await self.log_it(user['id'], m.from_user.full_name, f"BTN: {b['text']}")
                        return
                for t in self.triggers:
                    if t.get('keyword') and t['keyword'].lower() in txt:
                        await m.answer(t['response'])
                        await self.log_it(user['id'], m.from_user.full_name, f"TRG: {t['keyword']}")
                        return

            # Обычный форвард
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
        asyncio.create_task(self.sync_stats_worker())
        asyncio.create_task(self.remote_sync_poller())
        await self.register_handlers()
        self.dp.include_router(self.router)
        logger.info(f"🚀 Бот {self.bot_id} запущен.")
        await self.dp.start_polling(self.bot)

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    with open(sys.argv[1], 'r', encoding='utf-8') as f: cfg = json.load(f)
    asyncio.run(BotInstance(cfg).run())
