
import asyncio
import logging
import json
import httpx
import os
import sys
import hashlib
import time
from datetime import datetime
from typing import Dict, Optional, List, Any

from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode, ContentType
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
    InputMediaPhoto, InputMediaVideo, InputMediaAudio, InputMediaDocument
)
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter

# --- Настройка логирования ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("BotCore")

def get_anon_id(user_id: int) -> str:
    """Генерация короткого читаемого ID для анонимных топиков."""
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
            logger.error(f"[{self.bot_id}] Ошибка: ID администратора некорректен.")

        # API Supabase (из переменных окружения или конфига)
        self.sb_url = os.getenv("SUPABASE_URL", "").rstrip('/')
        self.sb_key = os.getenv("SUPABASE_KEY", "")
        
        # Инициализация Bot API
        self.bot = Bot(token=self.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher()
        self.router = Router()
        
        # Внутреннее состояние
        self.msg_map = {} # {admin_msg_id: user_id}
        self.connected_users = []
        self.sync_queue = asyncio.Queue()
        self.is_running = True
        
        self.refresh_config(config_data)

    def refresh_config(self, data: dict):
        """Обновление настроек из JSON-файла или БД."""
        conf = data.get('config') or data
        self.buttons = conf.get('buttons', [])
        self.triggers = conf.get('triggers', [])
        self.welcome_message = conf.get('welcomeMessage', 'Привет! Напишите нам сообщение.')
        self.settings = conf.get('settings', {})
        self.stats = conf.get('stats') or {"totalMessages": 0, "incomingToday": 0, "outgoingToday": 0}
        
        # Загружаем существующих пользователей
        self.connected_users = conf.get('connectedUsers', [])

        # Флаги Livegram режима
        self.use_topics = self.settings.get('useTopics', False)
        self.anonymous_topics = self.settings.get('anonymousTopics', False)
        self.admin_template = self.settings.get('adminMessageTemplate', "")

    def render_admin_header(self, m: Message) -> str:
        """Рендерит заголовок сообщения для админа на основе шаблона или настроек."""
        if self.admin_template:
            t = self.admin_template
            t = t.replace("{{id}}", str(m.from_user.id))
            t = t.replace("{{name}}", m.from_user.full_name)
            t = t.replace("{{username}}", f"@{m.from_user.username}" if m.from_user.username else "N/A")
            t = t.replace("{{text}}", m.text or m.caption or "[Медиа]")
            return t + "\n"
        
        # Логика на основе чекбоксов, если шаблон пуст
        s = self.settings
        parts = []
        if s.get('showHeaderName', True): parts.append(f"<b>{m.from_user.full_name}</b>")
        if s.get('showHeaderUsername', True) and m.from_user.username: parts.append(f"(@{m.from_user.username})")
        if s.get('showHeaderId', True): parts.append(f"ID: <code>{m.from_user.id}</code>")
        
        header = " | ".join(parts) if parts else f"User #{get_anon_id(m.from_user.id)}"
        return f"📩 {header}\n\n"

    async def db_sync_worker(self):
        """Фоновый воркер для сохранения данных в Supabase без блокировки основного цикла."""
        async with httpx.AsyncClient() as client:
            headers = {"apikey": self.sb_key, "Authorization": f"Bearer {self.sb_key}", "Content-Type": "application/json"}
            while self.is_running:
                task = await self.sync_queue.get()
                action, data = task
                try:
                    if action == "msg":
                        await client.post(f"{self.sb_url}/rest/v1/bot_messages", json=data, headers=headers)
                    elif action == "bot_config":
                        # Сохраняем состояние пользователей и статистики в JSONB поле config
                        cfg = self.full_config.get("config", {})
                        cfg["connectedUsers"] = self.connected_users
                        cfg["stats"] = self.stats
                        await client.patch(f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}", json={"config": cfg}, headers=headers)
                except Exception as e:
                    logger.error(f"Sync Worker Error: {e}")
                finally:
                    self.sync_queue.task_done()

    async def get_or_create_user(self, m: Message):
        """Возвращает данные юзера или создает нового в локальном кеше."""
        uid = m.from_user.id
        user = next((u for u in self.connected_users if str(u['id']) == str(uid)), None)
        if not user:
            user = {
                "id": uid, "first_name": m.from_user.first_name, 
                "username": m.from_user.username, "is_banned": False, 
                "is_active": True, "warns": 0, "last_topic_id": None
            }
            self.connected_users.append(user)
            await self.sync_queue.put(("bot_config", {}))
        return user

    async def ensure_topic(self, user: dict) -> Optional[int]:
        """Создает топик в группе админа, если он включен и еще не создан."""
        if not self.admin_id or not self.use_topics: return None
        if user.get("last_topic_id"): return user["last_topic_id"]
        try:
            # Анонимное или обычное имя топика
            name = f"User #{get_anon_id(user['id'])}" if self.anonymous_topics else f"{user['first_name']} [{user['id']}]"
            topic = await self.bot.create_forum_topic(self.admin_id, name)
            user["last_topic_id"] = topic.message_thread_id
            await self.sync_queue.put(("bot_config", {}))
            return topic.message_thread_id
        except Exception as e:
            logger.error(f"Forum Error: {e}")
            return None

    async def forward_to_admin(self, m: Message, user: dict):
        """Универсальная функция пересылки любого контента админу."""
        if not self.admin_id: return
        
        thread = await self.ensure_topic(user)
        header = self.render_admin_header(m)
        
        try:
            if not self.use_topics:
                # В обычном режиме шлем текст + медиа по отдельности (или копией)
                if m.text: 
                    sent = await self.bot.send_message(self.admin_id, f"{header}{m.text}")
                else:
                    await self.bot.send_message(self.admin_id, header)
                    sent = await self.bot.copy_message(self.admin_id, m.chat.id, m.message_id)
            else:
                # В топиках шлем просто чистую копию для удобства диалога
                sent = await self.bot.copy_message(self.admin_id, m.chat.id, m.message_id, message_thread_id=thread)
            
            # Маппим ID сообщения, чтобы знать, кому отвечать
            self.msg_map[sent.message_id] = user['id']
            # Удаляем старые записи из мапы, если она слишком большая
            if len(self.msg_map) > 1000: self.msg_map.pop(next(iter(self.msg_map)))
            
        except Exception as e:
            logger.error(f"Forwarding Error: {e}")

    async def handle_admin_reply(self, m: Message):
        """Логика ответа админа: находит юзера по реплаю или топику."""
        target_id = None
        
        # 1. Проверяем реплей
        if m.reply_to_message:
            target_id = self.msg_map.get(m.reply_to_message.message_id)
            
        # 2. Если не нашли по реплею, пробуем по топику (если включены)
        if not target_id and m.message_thread_id:
            u = next((u for u in self.connected_users if u.get("last_topic_id") == m.message_thread_id), None)
            if u: target_id = u["id"]
        
        if not target_id:
            return await m.reply("❌ Не удалось определить получателя. Ответьте на пересланное сообщение или пишите в топике.")

        try:
            # Копируем сообщение пользователю (поддерживает все типы контента)
            sent = await self.bot.copy_message(target_id, m.chat.id, m.message_id)
            self.msg_map[sent.message_id] = target_id # Для цепочки ответов
            
            self.stats["outgoingToday"] = self.stats.get("outgoingToday", 0) + 1
            await self.sync_queue.put(("msg", {
                "bot_id": self.bot_id, "user_id": target_id, "first_name": "Администратор", 
                "message_text": m.text or m.caption or "[Медиа]", "is_from_admin": True
            }))
        except Exception as e:
            await m.reply(f"❌ Ошибка доставки: {e}")

    async def register_handlers(self):
        
        @self.router.message(CommandStart())
        async def cmd_start(m: Message):
            user = await self.get_or_create_user(m)
            if user.get("is_banned"): return
            await m.answer(self.welcome_message, reply_markup=self.get_main_kb())

        @self.router.message(Command("ban", "unban", "warn"))
        async def admin_moderation(m: Message):
            if not self.admin_id or m.chat.id != self.admin_id: return
            
            # Ищем юзера для модерации
            target_user = None
            if m.message_thread_id:
                target_user = next((u for u in self.connected_users if u.get("last_topic_id") == m.message_thread_id), None)
            if not target_user and m.reply_to_message:
                tid = self.msg_map.get(m.reply_to_message.message_id)
                if tid: target_user = next((u for u in self.connected_users if u['id'] == tid), None)
            
            if not target_user: return await m.reply("❌ Пользователь не определен.")
            
            cmd = m.text.split()[0].lower()
            if "ban" in cmd: target_user["is_banned"] = True
            elif "unban" in cmd: target_user["is_banned"] = False
            elif "warn" in cmd: target_user["warns"] = target_user.get("warns", 0) + 1
            
            await self.sync_queue.put(("bot_config", {}))
            await m.reply(f"✅ Действие выполнено для {target_user['first_name']} ({target_user['id']})")

        @self.router.message(F.chat.id == self.admin_id)
        async def admin_messages(m: Message):
            # Если это ответ в группе админа — обрабатываем как ответ пользователю
            if m.reply_to_message or m.message_thread_id:
                await self.handle_admin_reply(m)

        @self.router.message()
        async def universal_user_handler(m: Message):
            # Игнорируем сообщения от самого админа в его чате (если не реплей)
            if self.admin_id and m.chat.id == self.admin_id: return
            
            user = await self.get_or_create_user(m)
            if user.get("is_banned"): return

            # Проверка кастомных кнопок и триггеров
            if m.text:
                txt = m.text.lower().strip()
                # 1. Кнопки меню
                for b in self.buttons:
                    if b.get('text') and b['text'].lower() == txt:
                        if b.get('type') == 'request':
                            # Специальный тип: отправка уведомления админу о нажатии
                            await self.forward_to_admin(m, user)
                        if b.get('response'):
                            await m.answer(b['response'])
                        return
                
                # 2. Триггеры ключевых слов
                for t in self.triggers:
                    if t.get('keyword') and t['keyword'].lower() in txt:
                        await m.answer(t['response'])
                        return

            # Основная логика Livegram: пересылка сообщения админу
            await self.forward_to_admin(m, user)

            # Обновление статистики
            self.stats["incomingToday"] = self.stats.get("incomingToday", 0) + 1
            self.stats["totalMessages"] = self.stats.get("totalMessages", 0) + 1
            
            # Логируем сообщение в БД
            await self.sync_queue.put(("msg", {
                "bot_id": self.bot_id, "user_id": user['id'], "first_name": m.from_user.first_name,
                "message_text": m.text or m.caption or f"[{m.content_type}]", "is_from_admin": False
            }))

    def get_main_kb(self):
        """Генерирует Reply-клавиатуру на основе настроек."""
        btns = [b for b in self.buttons if b.get('text')]
        if not btns: return None
        # По 2 кнопки в ряд
        keyboard = []
        for i in range(0, len(btns), 2):
            row = [KeyboardButton(text=btns[i]['text'])]
            if i + 1 < len(btns): row.append(KeyboardButton(text=btns[i+1]['text']))
            keyboard.append(row)
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

    async def run(self):
        """Точка входа в процесс бота."""
        asyncio.create_task(self.db_sync_worker())
        await self.register_handlers()
        self.dp.include_router(self.router)
        logger.info(f"✨ Бот @{(await self.bot.get_me()).username} успешно запущен!")
        await self.dp.start_polling(self.bot)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.critical("Не указан путь к файлу конфигурации.")
        sys.exit(1)
    
    with open(sys.argv[1], 'r', encoding='utf-8') as f:
        config = json.load(f)
        
    instance = BotInstance(config)
    try:
        asyncio.run(instance.run())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
