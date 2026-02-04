
import asyncio
import logging
import json
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

# --- Логирование ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotCore")

def get_anon_id(user_id: int) -> str:
    """Генерация уникального хеша для анонимизации пользователя."""
    return hashlib.md5(str(user_id).encode()).hexdigest()[:6].upper()

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
            logger.error(f"[{self.bot_id}] КРИТИЧЕСКАЯ ОШИБКА: ID администратора не задан или неверен.")

        # Настройки Supabase
        self.sb_url = os.getenv("SUPABASE_URL", "").rstrip('/')
        self.sb_key = os.getenv("SUPABASE_KEY", "")
        
        # AIOGRAM объекты
        self.bot = Bot(token=self.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher()
        self.router = Router()
        
        # Состояние процесса
        self.msg_map = {} # {admin_msg_id: user_id}
        self.user_locks = {} # {user_id: last_msg_time} для анти-спама
        self.connected_users = []
        self.sync_queue = asyncio.Queue()
        self.is_running = True
        
        self.refresh_config(config_data)

    def refresh_config(self, data: dict):
        """Обновление локального конфига из JSON."""
        conf = data.get('config') or data
        self.buttons = conf.get('buttons', [])
        self.triggers = conf.get('triggers', [])
        self.welcome_message = conf.get('welcomeMessage', 'Привет! Оставьте ваше сообщение.')
        self.settings = conf.get('settings', {})
        self.stats = conf.get('stats') or {
            "totalMessages": 0, 
            "incomingToday": 0, 
            "outgoingToday": 0, 
            "history": [],
            "bannedCount": 0
        }
        self.connected_users = conf.get('connectedUsers', [])
        
        # Функциональные переключатели
        self.use_topics = self.settings.get('useTopics', False)
        self.admin_template = self.settings.get('adminMessageTemplate', "")
        self.anti_spam_enabled = self.settings.get('antiSpam', True)
        self.rate_limit = self.settings.get('rateLimit', 2) # сек между соо

    def generate_admin_header(self, m: Message, is_first: bool = False) -> str:
        """Создание заголовка для админа с учетом настроек приватности и шаблонов."""
        if is_first:
            # Логика "Первого обращения" или "Кнопки-заявки"
            if self.admin_template:
                t = self.admin_template
                t = t.replace("{{id}}", str(m.from_user.id))
                t = t.replace("{{name}}", m.from_user.full_name or "Unknown")
                t = t.replace("{{username}}", f"@{m.from_user.username}" if m.from_user.username else "N/A")
                t = t.replace("{{text}}", m.text or m.caption or "[Медиа]")
                return f"🆕 <b>ПЕРВОЕ ОБРАЩЕНИЕ</b>\n\n{t}\n"
            else:
                return (f"🆕 <b>НОВОЕ ОБРАЩЕНИЕ</b>\n"
                        f"👤 Имя: <b>{m.from_user.full_name}</b>\n"
                        f"🆔 ID: <code>{m.from_user.id}</code>\n"
                        f"🔗 User: @{m.from_user.username or 'none'}\n\n")

        # Компактный заголовок для текущего диалога
        s = self.settings
        parts = []
        if s.get('showHeaderName', True): 
            parts.append(f"<b>{m.from_user.full_name}</b>")
        if s.get('showHeaderUsername', True) and m.from_user.username: 
            parts.append(f"(@{m.from_user.username})")
        if s.get('showHeaderId', True): 
            parts.append(f"ID: <code>{m.from_user.id}</code>")
        
        if not parts:
            parts.append(f"👤 Пользователь <code>#{get_anon_id(m.from_user.id)}</code>")
            
        header = " | ".join(parts)
        return f"📩 {header}\n\n"

    async def sync_worker(self):
        """Фоновый процесс для синхронизации с облаком Supabase."""
        async with httpx.AsyncClient() as client:
            headers = {
                "apikey": self.sb_key, 
                "Authorization": f"Bearer {self.sb_key}", 
                "Content-Type": "application/json"
            }
            logger.info(f"[{self.bot_id}] Sync worker started.")
            while self.is_running:
                action, data = await self.sync_queue.get()
                try:
                    if action == "msg":
                        # Сохраняем сообщение в историю для аналитики на фронте
                        await client.post(f"{self.sb_url}/rest/v1/bot_messages", json=data, headers=headers)
                    elif action == "config":
                        # Обновляем JSONB конфиг бота (статистика + пользователи)
                        payload = {
                            "config": {
                                **self.full_config.get("config", {}),
                                "connectedUsers": self.connected_users,
                                "stats": self.stats
                            }
                        }
                        await client.patch(f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}", json=payload, headers=headers)
                except Exception as e:
                    logger.error(f"Sync error: {e}")
                finally:
                    self.sync_queue.task_done()
                await asyncio.sleep(0.1)

    async def get_or_reg_user(self, m: Message):
        """Проверка существования пользователя в базе бота."""
        uid = m.from_user.id
        user = next((u for u in self.connected_users if u['id'] == uid), None)
        is_new = False
        if not user:
            is_new = True
            user = {
                "id": uid, 
                "first_name": m.from_user.first_name, 
                "username": m.from_user.username, 
                "is_banned": False, 
                "is_active": True, 
                "warns": 0, 
                "last_topic_id": None,
                "joined_at": int(time.time()*1000)
            }
            self.connected_users.append(user)
            await self.sync_queue.put(("config", {}))
        return user, is_new

    async def forward_to_admin(self, m: Message, user: dict, force_template: bool = False):
        """Умная пересылка сообщения админу."""
        if not self.admin_id: return

        # Проверка Анти-спама
        now = time.time()
        if self.anti_spam_enabled:
            last_time = self.user_locks.get(user['id'], 0)
            if now - last_time < self.rate_limit:
                return # Игнорируем слишком частые сообщения
            self.user_locks[user['id']] = now

        # Работа с топиками (Форум)
        thread_id = None
        if self.use_topics:
            if not user.get("last_topic_id"):
                try:
                    name = f"{user['first_name']} [{user['id']}]"
                    topic = await self.bot.create_forum_topic(self.admin_id, name)
                    user["last_topic_id"] = topic.message_thread_id
                    await self.sync_queue.put(("config", {}))
                except Exception as e:
                    logger.warning(f"Failed to create topic: {e}")
            thread_id = user.get("last_topic_id")

        header = self.generate_admin_header(m, is_first=force_template)
        
        try:
            # Пересылка контента
            sent_msg = None
            if m.text:
                sent_msg = await self.bot.send_message(self.admin_id, f"{header}{m.text}", message_thread_id=thread_id)
            elif m.sticker:
                await self.bot.send_message(self.admin_id, header, message_thread_id=thread_id)
                sent_msg = await self.bot.send_sticker(self.admin_id, m.sticker.file_id, message_thread_id=thread_id)
            elif m.photo:
                await self.bot.send_message(self.admin_id, header, message_thread_id=thread_id)
                sent_msg = await self.bot.send_photo(self.admin_id, m.photo[-1].file_id, caption=m.caption, message_thread_id=thread_id)
            elif m.voice:
                await self.bot.send_message(self.admin_id, header, message_thread_id=thread_id)
                sent_msg = await self.bot.send_voice(self.admin_id, m.voice.file_id, caption=m.caption, message_thread_id=thread_id)
            elif m.video:
                await self.bot.send_message(self.admin_id, header, message_thread_id=thread_id)
                sent_msg = await self.bot.send_video(self.admin_id, m.video.file_id, caption=m.caption, message_thread_id=thread_id)
            elif m.video_note:
                await self.bot.send_message(self.admin_id, header, message_thread_id=thread_id)
                sent_msg = await self.bot.send_video_note(self.admin_id, m.video_note.file_id, message_thread_id=thread_id)
            elif m.document:
                await self.bot.send_message(self.admin_id, header, message_thread_id=thread_id)
                sent_msg = await self.bot.send_document(self.admin_id, m.document.file_id, caption=m.caption, message_thread_id=thread_id)
            else:
                # Универсальная копия для остальных типов
                await self.bot.send_message(self.admin_id, header, message_thread_id=thread_id)
                sent_msg = await self.bot.copy_message(self.admin_id, m.chat.id, m.message_id, message_thread_id=thread_id)
            
            # Сохраняем в карту для реплаев
            if sent_msg:
                self.msg_map[sent_msg.message_id] = user['id']
                if len(self.msg_map) > 5000: self.msg_map.pop(next(iter(self.msg_map)))
                
        except TelegramForbiddenError:
            logger.error("Бот заблокирован в админ-чате!")
        except Exception as e:
            logger.error(f"Forwarding error: {e}")

    async def handle_admin_reply(self, m: Message):
        """Логика ответа администратора пользователю."""
        target_id = None
        # 1. По реплаю
        if m.reply_to_message:
            target_id = self.msg_map.get(m.reply_to_message.message_id)
        
        # 2. По топику (если реплая нет, но мы в ветке)
        if not target_id and m.message_thread_id:
            u = next((u for u in self.connected_users if u.get("last_topic_id") == m.message_thread_id), None)
            if u: target_id = u["id"]

        if not target_id:
            return # Мы не знаем кому отвечать

        try:
            # Отправляем копию сообщения пользователю
            await self.bot.copy_message(target_id, m.chat.id, m.message_id)
            
            # Статистика
            self.stats["outgoingToday"] = self.stats.get("outgoingToday", 0) + 1
            self.stats["totalMessages"] = self.stats.get("totalMessages", 0) + 1
            
            # Аналитика в БД
            await self.sync_queue.put(("msg", {
                "bot_id": self.bot_id, 
                "user_id": target_id, 
                "first_name": "Администратор", 
                "message_text": m.text or m.caption or "[Медиа ответ]", 
                "is_from_admin": True
            }))
            await self.sync_queue.put(("config", {}))
            
        except TelegramForbiddenError:
            await m.reply("❌ Пользователь заблокировал бота.")
        except Exception as e:
            await m.reply(f"❌ Ошибка отправки: {e}")

    async def register_handlers(self):
        """Регистрация всех сценариев поведения."""
        
        @self.router.message(CommandStart())
        async def cmd_start(m: Message):
            user, is_new = await self.get_or_reg_user(m)
            if user.get("is_banned"): return
            
            await m.answer(self.welcome_message, reply_markup=self.get_kb())
            # Уведомляем админа о новом юзере по шаблону
            await self.forward_to_admin(m, user, force_template=True)

        @self.router.message(F.chat.id == self.admin_id)
        async def admin_input(m: Message):
            # Если админ пишет в свой чат — это либо ответ, либо игнор
            if m.reply_to_message or m.message_thread_id:
                await self.handle_admin_reply(m)

        @self.router.message()
        async def global_handler(m: Message):
            # Игнорируем админа вне контекста ответов
            if m.chat.id == self.admin_id: return
            
            user, is_new = await self.get_or_reg_user(m)
            if user.get("is_banned"): return

            # 1. Проверка Кнопок
            if m.text:
                txt = m.text.lower().strip()
                for b in self.buttons:
                    if b.get('text') and b['text'].lower() == txt:
                        if b.get('type') == 'request':
                            # Специальный режим "Заявка" (шлем по шаблону админу)
                            await self.forward_to_admin(m, user, force_template=True)
                        if b.get('response'):
                            await m.answer(b['response'])
                        return
                
                # 2. Проверка Триггеров
                for t in self.triggers:
                    if t.get('keyword') and t['keyword'].lower() in txt:
                        await m.answer(t['response'])
                        return

            # 3. Обычная пересылка (Livegram Mode)
            # Если юзер новый — используем шаблон, иначе компактный заголовок
            await self.forward_to_admin(m, user, force_template=is_new)
            
            # 4. Аналитика
            self.stats["incomingToday"] = self.stats.get("incomingToday", 0) + 1
            self.stats["totalMessages"] = self.stats.get("totalMessages", 0) + 1
            
            await self.sync_queue.put(("msg", {
                "bot_id": self.bot_id, 
                "user_id": user['id'], 
                "first_name": m.from_user.first_name, 
                "message_text": m.text or m.caption or "[Входящее медиа]", 
                "is_from_admin": False
            }))
            await self.sync_queue.put(("config", {}))

    def get_kb(self):
        """Сборка клавиатуры из конфига."""
        btns = [b for b in self.buttons if b.get('text')]
        if not btns: return None
        # По 2 кнопки в ряд
        keyboard = []
        row = []
        for b in btns:
            row.append(KeyboardButton(text=b['text']))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row: keyboard.append(row)
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

    async def run(self):
        """Основной цикл запуска."""
        asyncio.create_task(self.sync_worker())
        await self.register_handlers()
        self.dp.include_router(self.router)
        logger.info(f"🚀 Бот @{(await self.bot.get_me()).username} запущен.")
        try:
            await self.dp.start_polling(self.bot)
        finally:
            self.is_running = False
            await self.bot.session.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.error("Usage: python bot_core.py <config_path>")
        sys.exit(1)
    
    try:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            config = json.load(f)
        asyncio.run(BotInstance(config).run())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Fatal error: {e}")
