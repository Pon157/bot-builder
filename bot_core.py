
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
from typing import Dict, Optional, List

from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode, ContentType
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
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

# --- Утилиты ---
def get_anon_id(user_id: int) -> str:
    return hashlib.md5(str(user_id).encode()).hexdigest()[:6].upper()

def format_header(m: Message, settings: dict, is_anon: bool = False) -> str:
    """Формирует информационную строку о пользователе."""
    s = settings
    show_id = s.get('showHeaderId', True)
    show_name = s.get('showHeaderName', True)
    show_user = s.get('showHeaderUsername', True)
    
    # Если включена анонимность в настройках топика или глобально
    if is_anon:
        return f"👤 <b>User #{get_anon_id(m.from_user.id)}</b>"

    parts = []
    if show_name:
        parts.append(f"<b>{m.from_user.full_name}</b>")
    if show_user and m.from_user.username:
        parts.append(f"(@{m.from_user.username})")
    if show_id:
        parts.append(f"ID: <code>{m.from_user.id}</code>")
    
    return "📩 " + " | ".join(parts) if parts else "📩 Сообщение"

class RateLimiter:
    """Простая защита от флуда."""
    def __init__(self, limit: float = 0.8):
        self.limit = limit
        self.users = {}

    def is_rate_limited(self, user_id: int) -> bool:
        now = time.time()
        last_time = self.users.get(user_id, 0)
        if now - last_time < self.limit:
            return True
        self.users[user_id] = now
        return False

class BotInstance:
    def __init__(self, config_data: dict):
        self.config = config_data
        self.token = config_data.get('token')
        self.bot_id = config_data.get('id')
        
        # Настройка админа
        raw_admin = config_data.get('adminChatId')
        try:
            self.admin_id = int(str(raw_admin).strip()) if raw_admin else None
        except:
            self.admin_id = None
            logger.error(f"[{self.bot_id}] Неверный ID администратора.")

        # API Supabase
        self.sb_url = os.getenv("SUPABASE_URL", "").rstrip('/')
        self.sb_key = os.getenv("SUPABASE_KEY", "")
        
        # Инициализация бота
        self.bot = Bot(token=self.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher()
        self.router = Router()
        self.limiter = RateLimiter()
        
        # Состояние
        self.msg_map = {} # {admin_msg_id: user_id}
        self.connected_users = []
        self.sync_queue = asyncio.Queue()
        self.is_running = True
        
        self.refresh_config(config_data)

    def refresh_config(self, data: dict):
        """Обновление конфига без перезагрузки процесса."""
        conf = data.get('config') or data
        self.buttons = conf.get('buttons', [])
        self.triggers = conf.get('triggers', [])
        self.welcome_message = conf.get('welcomeMessage', 'Привет!')
        self.settings = conf.get('settings', {})
        self.stats = conf.get('stats') or {
            "totalMessages": 0, "incomingToday": 0, "outgoingToday": 0, "bannedCount": 0, "history": []
        }
        
        # Мерж юзеров
        inc_users = conf.get('connectedUsers', [])
        local_users = {str(u['id']): u for u in self.connected_users}
        for u in inc_users:
            uid = str(u['id'])
            if uid in local_users:
                local_users[uid].update(u)
            else:
                local_users[uid] = u
        self.connected_users = list(local_users.values())

        # Настройки режима
        self.use_topics = self.settings.get('useTopics', False)
        self.anonymous_topics = self.settings.get('anonymousTopics', False)
        self.topic_per_request = self.settings.get('topicPerRequest', False)
        self.auto_ban_threshold = self.settings.get('autoBanThreshold', 0)

    async def db_sync_worker(self):
        """Фоновая синхронизация с Supabase."""
        async with httpx.AsyncClient() as client:
            headers = {
                "apikey": self.sb_key, 
                "Authorization": f"Bearer {self.sb_key}", 
                "Content-Type": "application/json"
            }
            while self.is_running:
                task = await self.sync_queue.get()
                action, data = task
                try:
                    if action == "msg":
                        await client.post(f"{self.sb_url}/rest/v1/bot_messages", json=data, headers=headers)
                    elif action == "bot_config":
                        payload = {
                            "config": {
                                **self.config.get("config", {}),
                                "connectedUsers": self.connected_users,
                                "stats": self.stats
                            }
                        }
                        await client.patch(f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}", json=payload, headers=headers)
                except Exception as e:
                    logger.error(f"Sync error: {e}")
                finally:
                    self.sync_queue.task_done()

    async def get_user(self, m: Message):
        uid = m.from_user.id
        user = next((u for u in self.connected_users if str(u['id']) == str(uid)), None)
        if not user:
            user = {
                "id": uid, "first_name": m.from_user.first_name, 
                "username": m.from_user.username, "is_banned": False, 
                "is_active": True, "warns": 0, "joined_at": int(time.time()), 
                "last_topic_id": None
            }
            self.connected_users.append(user)
            await self.sync_queue.put(("bot_config", {}))
        return user

    async def ensure_topic(self, user: dict) -> Optional[int]:
        if not self.admin_id or not self.use_topics: return None
        if user.get("last_topic_id"): return user["last_topic_id"]
        
        try:
            name = f"User #{get_anon_id(user['id'])}" if self.anonymous_topics else f"{user['first_name']} [{user['id']}]"
            topic = await self.bot.create_forum_topic(self.admin_id, name)
            user["last_topic_id"] = topic.message_thread_id
            await self.sync_queue.put(("bot_config", {}))
            return topic.message_thread_id
        except Exception as e:
            logger.error(f"Forum Error: {e}")
            return None

    async def register_handlers(self):
        
        @self.router.message(CommandStart())
        async def cmd_start(m: Message):
            user = await self.get_user(m)
            if user.get("is_banned"): return
            await m.answer(self.welcome_message, reply_markup=self.get_main_kb())

        @self.router.message(Command("warn", "unwarn", "ban", "unban"))
        async def admin_moderation(m: Message):
            if not self.admin_id or m.chat.id != self.admin_id: return
            
            target_user = None
            # 1. Поиск по топику
            if m.message_thread_id:
                target_user = next((u for u in self.connected_users if u.get("last_topic_id") == m.message_thread_id), None)
            
            # 2. Поиск по реплаю
            if not target_user and m.reply_to_message:
                target_id = self.msg_map.get(m.reply_to_message.message_id)
                if target_id:
                    target_user = next((u for u in self.connected_users if str(u['id']) == str(target_id)), None)
            
            if not target_user:
                return await m.reply("❌ Не удалось определить пользователя.")

            cmd = m.text.split()[0].replace("/", "").lower()
            if cmd == "warn":
                target_user["warns"] = target_user.get("warns", 0) + 1
                if self.auto_ban_threshold > 0 and target_user["warns"] >= self.auto_ban_threshold:
                    target_user["is_banned"] = True
                await m.reply(f"⚠️ Варн выдан. Всего: {target_user['warns']}")
                try: await self.bot.send_message(target_user['id'], f"⚠️ Вам выдано предупреждение ({target_user['warns']})")
                except: pass
            elif cmd == "ban":
                target_user["is_banned"] = True
                await m.reply("🚫 Пользователь заблокирован.")
            elif cmd == "unban":
                target_user["is_banned"] = False
                await m.reply("✅ Пользователь разблокирован.")
            
            await self.sync_queue.put(("bot_config", {}))

        @self.router.message(F.chat.id == self.admin_id, F.reply_to_message)
        async def admin_reply(m: Message):
            """Логика ответа администратора."""
            # Пытаемся найти ID юзера в кэше или через топик
            target_id = self.msg_map.get(m.reply_to_message.message_id)
            if not target_id and m.message_thread_id:
                u = next((u for u in self.connected_users if u.get("last_topic_id") == m.message_thread_id), None)
                if u: target_id = u["id"]
            
            if not target_id:
                # Последний шанс: парсим ID из текста сообщения (если это была текстовая шапка)
                text = (m.reply_to_message.text or "") + (m.reply_to_message.caption or "")
                match = re.search(r"ID:\s*(\d+)", text)
                if match: target_id = int(match.group(1))

            if target_id:
                try:
                    sent = await self.bot.copy_message(target_id, m.chat.id, m.message_id)
                    # Сохраняем для возможности цепочки ответов
                    self.msg_map[sent.message_id] = target_id
                    
                    self.stats["outgoingToday"] += 1
                    self.stats["totalMessages"] += 1
                    await self.sync_queue.put(("msg", {
                        "bot_id": self.bot_id, "user_id": target_id, "first_name": "Admin",
                        "message_text": m.text or m.caption or "[Медиа]", "is_from_admin": True
                    }))
                except TelegramForbiddenError:
                    await m.reply("❌ Пользователь заблокировал бота.")
                except Exception as e:
                    await m.reply(f"❌ Ошибка отправки: {e}")
            else:
                await m.reply("❌ Не удалось найти получателя.")

        @self.router.message()
        async def main_handler(m: Message):
            if self.admin_id and m.chat.id == self.admin_id: return
            
            if self.limiter.is_rate_limited(m.from_user.id): return

            user = await self.get_user(m)
            if user.get("is_banned"): return
            user["is_active"] = True

            # Статистика
            self.stats["incomingToday"] += 1
            self.stats["totalMessages"] += 1
            await self.sync_queue.put(("msg", {
                "bot_id": self.bot_id, "user_id": user['id'], "first_name": m.from_user.first_name,
                "message_text": m.text or m.caption or "[Медиа]", "is_from_admin": False
            }))

            # 1. Проверка триггеров и кнопок
            if m.text:
                txt = m.text.lower().strip()
                # Кнопки
                for b in self.buttons:
                    if b.get('text') and b['text'].lower() == txt:
                        if b.get('type') == 'request' and self.admin_id:
                            # Специальный режим заявки
                            thread = await self.ensure_topic(user)
                            info = format_header(m, self.settings, self.anonymous_topics)
                            msg_text = f"{info}\n\n🔥 <b>ПОСТУПИЛА ЗАЯВКА</b>\nКнопка: {b['text']}"
                            sent = await self.bot.send_message(self.admin_id, msg_text, message_thread_id=thread)
                            self.msg_map[sent.message_id] = user['id']
                        if b.get('response'):
                            await m.answer(b['response'])
                        return
                
                # Триггеры
                for t in self.triggers:
                    if t.get('keyword') and t['keyword'].lower() in txt:
                        await m.answer(t.get('response', '...'))
                        return

            # 2. Пересылка админу (Unified Bubble Logic)
            if self.admin_id:
                thread = await self.ensure_topic(user)
                info = format_header(m, self.settings, self.anonymous_topics)

                try:
                    if not self.use_topics:
                        # Режим "Один пузырь" (без топиков)
                        if m.text:
                            sent = await self.bot.send_message(self.admin_id, f"{info}\n\n{m.text}", message_thread_id=thread)
                        elif m.caption or any([m.photo, m.video, m.audio, m.document, m.animation]):
                            cap = f"{info}\n\n{m.caption or ''}"
                            sent = await self.bot.copy_message(self.admin_id, m.chat.id, m.message_id, caption=cap, message_thread_id=thread)
                        else:
                            # Стикеры, Кружки, Голос (без подписей) - шлем инфо отдельно
                            await self.bot.send_message(self.admin_id, info, message_thread_id=thread)
                            sent = await self.bot.copy_message(self.admin_id, m.chat.id, m.message_id, message_thread_id=thread)
                    else:
                        # В топиках шлем чистую копию (там и так понятно кто пишет)
                        sent = await self.bot.copy_message(self.admin_id, m.chat.id, m.message_id, message_thread_id=thread)

                    self.msg_map[sent.message_id] = user['id']
                except Exception as e:
                    logger.error(f"Forwarding error: {e}")

                # Чистка кэша
                if len(self.msg_map) > 5000:
                    del self.msg_map[next(iter(self.msg_map))]

    def get_main_kb(self):
        btns = [b for b in self.buttons if b.get('text')]
        if not btns: return None
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=b['text'])] for b in btns], 
            resize_keyboard=True
        )

    async def run(self):
        logger.info(f"[{self.bot_id}] Запуск...")
        asyncio.create_task(self.db_sync_worker())
        await self.register_handlers()
        self.dp.include_router(self.router)
        await self.dp.start_polling(self.bot)

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    with open(sys.argv[1], 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    asyncio.run(BotInstance(cfg).run())
