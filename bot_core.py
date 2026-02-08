import asyncio
import logging
import json
import httpx
import os
import sys
import hashlib
import time
import shutil
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any, Union

# Импорты aiogram 3.x
from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode, ContentType, ChatMemberStatus
from aiogram.filters import CommandStart, Command, ChatMemberUpdatedFilter
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
    ReplyKeyboardRemove, ForumTopicCreated, ChatMemberUpdated,
    FSInputFile, PhotoSize
)
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter

# ==========================================
# 0. НАСТРОЙКА ОКРУЖЕНИЯ И ЛОГИРОВАНИЯ
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(BASE_DIR, "bot_core_critical.log"), encoding='utf-8')
    ]
)
logger = logging.getLogger("UltimateBotCore")

# ==========================================
# 1. ВСПОМОГАТЕЛЬНЫЕ УТИЛИТЫ
# ==========================================
def generate_short_id(user_id: int) -> str:
    """Генерация уникального короткого ID для анонимных топиков"""
    return hashlib.md5(str(user_id).encode()).hexdigest()[:8].upper()

def get_timestamp():
    """ISO формат времени"""
    return datetime.now().isoformat()

# ==========================================
# 2. ЯДРО СИСТЕМЫ ПЕРЕСЫЛКИ И ОФОРМЛЕНИЯ
# ==========================================
class MessageFormatter:
    @staticmethod
    def get_admin_header(m: Message, settings: dict, is_first: bool = False, btn_label: str = "") -> str:
        """Создает детальную шапку сообщения для администратора"""
        is_anon = settings.get('anonymousTopics', False)
        uid = m.from_user.id
        
        if is_anon:
            user_info = f"👤 <b>Анонимный клиент</b> [<code>{generate_short_id(uid)}</code>]"
        else:
            name = m.from_user.full_name
            username = f"(@{m.from_user.username})" if m.from_user.username else ""
            user_info = f"👤 <b>{name}</b> {username}\n🆔 ID: <code>{uid}</code>"

        # Определяем тип события
        if btn_label:
            event_type = f"⚡️ <b>КНОПКА: {btn_label}</b>"
        elif is_first:
            event_type = settings.get('firstMessageHeader', "🆕 <b>НОВОЕ ОБРАЩЕНИЕ</b>")
        else:
            event_type = settings.get('commonMessageHeader', "📩 <b>СООБЩЕНИЕ</b>")
            
        separator = "—" * 20
        return f"{event_type}\n{user_info}\n{separator}\n\n"

# ==========================================
# 3. ОСНОВНОЙ КЛАСС БОТА
# ==========================================
class AdvancedBotInstance:
    def __init__(self, raw_config: dict):
        # Базовые поля
        self.bot_id = raw_config.get('id')
        self.token = raw_config.get('token')
        
        # Инстансы aiogram
        self.bot = Bot(
            token=self.token, 
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        self.dp = Dispatcher()
        self.router = Router()
        
        # Внутреннее состояние
        self.is_running = True
        self.msg_history_map: Dict[int, int] = {}  # admin_msg_id -> user_id
        self.antiflood_data: Dict[int, float] = {}
        self.db_buffer = []
        self.buffer_lock = asyncio.Lock()
        
        # Загрузка и разбор конфига
        self.parse_config(raw_config)
        
        # Настройка Supabase (из окружения)
        self.sb_url = os.getenv("SUPABASE_URL", "").rstrip('/')
        self.sb_key = os.getenv("SUPABASE_KEY", "")

    def parse_config(self, data: dict):
        """Парсинг настроек и конфигурации из БД"""
        c = data.get('config', {})
        if isinstance(c, str):
            c = json.loads(c)
            
        self.admin_chat_id = int(str(c.get('adminChatId', 0))) if c.get('adminChatId') else None
        self.welcome_text = c.get('welcomeMessage', 'Добро пожаловать!')
        self.welcome_img = c.get('welcomeImage')
        
        self.buttons = c.get('buttons', [])
        self.triggers = c.get('triggers', [])
        self.channels = c.get('channels', [])
        
        self.settings = c.get('settings', {
            'useTopics': False,
            'anonymousTopics': False,
            'forwardToAdmin': True,
            'antiSpam': True,
            'rateLimit': 1.0,
            'autoApprove': False
        })
        
        self.users = c.get('connectedUsers', [])
        self.stats = c.get('stats', {
            'total_msgs': 0, 
            'unique_users': len(self.users),
            'last_reset': datetime.now().strftime('%Y-%m-%d')
        })

    # --- МЕХАНИЗМЫ СОХРАНЕНИЯ МЕДИА ---
    async def download_media(self, message: Message, folder: str = "triggers") -> Optional[str]:
        """Скачивает медиафайл и возвращает локальный путь"""
        try:
            target_dir = os.path.join(UPLOADS_DIR, folder)
            os.makedirs(target_dir, exist_ok=True)
            
            file_id = None
            ext = ".jpg"
            
            if message.photo:
                file_id = message.photo[-1].file_id
            elif message.document:
                file_id = message.document.file_id
                ext = os.path.splitext(message.document.file_name)[1]
            
            if not file_id:
                return None
                
            file = await self.bot.get_file(file_id)
            file_name = f"{uuid.uuid4()}{ext}"
            file_path = os.path.join(target_dir, file_name)
            
            await self.bot.download_file(file.file_path, file_path)
            # Возвращаем путь относительно корня проекта для сохранения в БД
            return f"uploads/{folder}/{file_name}"
        except Exception as e:
            logger.error(f"Error downloading media: {e}")
            return None

    # --- РАБОТА С БАЗОЙ ДАННЫХ (SUPABASE) ---
    async def sync_loop(self):
        """Фоновый цикл синхронизации данных (сообщения + конфиг)"""
        logger.info(f"[*] Sync Loop started for Bot ID {self.bot_id}")
        async with httpx.AsyncClient(timeout=20.0) as client:
            headers = {
                "apikey": self.sb_key,
                "Authorization": f"Bearer {self.sb_key}",
                "Content-Type": "application/json"
            }
            while self.is_running:
                try:
                    await asyncio.sleep(15) # Интервал синхронизации
                    
                    # 1. Сброс накопленных сообщений
                    async with self.buffer_lock:
                        if self.db_buffer:
                            await client.post(
                                f"{self.sb_url}/rest/v1/bot_messages",
                                json=self.db_buffer, headers=headers
                            )
                            self.db_buffer = []

                    # 2. Сохранение текущего состояния бота
                    update_data = {
                        "config": {
                            "adminChatId": self.admin_chat_id,
                            "welcomeMessage": self.welcome_text,
                            "welcomeImage": self.welcome_img,
                            "buttons": self.buttons,
                            "triggers": self.triggers,
                            "channels": self.channels,
                            "settings": self.settings,
                            "connectedUsers": self.users,
                            "stats": self.stats
                        }
                    }
                    await client.patch(
                        f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                        json=update_data, headers=headers
                    )
                except Exception as e:
                    logger.error(f"Global Sync Error: {e}")

    async def log_message(self, user_id: int, user_name: str, text: str, is_admin: bool = False):
        """Добавляет сообщение в буфер для последующей отправки в БД"""
        self.stats['total_msgs'] += 1
        entry = {
            "bot_id": self.bot_id,
            "user_id": str(user_id),
            "user_name": user_name,
            "content": text[:1500],
            "is_admin": is_admin,
            "timestamp": get_timestamp()
        }
        async with self.buffer_lock:
            self.db_buffer.append(entry)

    # --- УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ ---
    async def get_user_profile(self, m: Message):
        uid = m.from_user.id
        user = next((u for u in self.users if u['id'] == uid), None)
        is_new = False
        
        if not user:
            is_new = True
            user = {
                "id": uid,
                "name": m.from_user.full_name,
                "username": m.from_user.username,
                "joined_at": get_timestamp(),
                "topic_id": None,
                "is_blocked": False,
                "tags": []
            }
            self.users.append(user)
            self.stats['unique_users'] = len(self.users)
            logger.info(f"New user: {uid}")
            
        return user, is_new

    async def check_memberships(self, user_id: int) -> bool:
        """Проверка обязательных подписок"""
        if not self.channels: return True
        for channel in self.channels:
            try:
                chat_id = channel.get('id')
                member = await self.bot.get_chat_member(chat_id, user_id)
                if member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]:
                    return False
            except Exception as e:
                logger.warning(f"Check membership error ({chat_id}): {e}")
                continue
        return True

    # --- ЛОГИКА ПЕРЕСЫЛКИ СООБЩЕНИЙ ---
    async def relay_to_admin(self, m: Message, user: dict, is_first: bool = False, btn_text: str = ""):
        """Метод пересылки контента админу (с топиками и антифлудом)"""
        if not self.admin_chat_id: return

        # Проверка Анти-спама
        if self.settings.get('antiSpam'):
            now = time.time()
            last_msg_time = self.antiflood_data.get(user['id'], 0)
            if now - last_msg_time < self.settings.get('rateLimit', 1.0):
                return
            self.antiflood_data[user['id']] = now

        header = MessageFormatter.get_admin_header(m, self.settings, is_first, btn_text)
        
        # Обработка топиков
        thread_id = None
        if self.settings.get('useTopics'):
            if not user.get('topic_id'):
                try:
                    topic_title = f"{user['name']} | {generate_short_id(user['id'])}"
                    new_topic = await self.bot.create_forum_topic(self.admin_chat_id, topic_title)
                    user['topic_id'] = new_topic.message_thread_id
                except Exception as e:
                    logger.error(f"Topic creation failed: {e}")
            thread_id = user.get('topic_id')

        try:
            sent_msg = None
            if m.text:
                sent_msg = await self.bot.send_message(self.admin_chat_id, f"{header}{m.text}", message_thread_id=thread_id)
            elif m.photo:
                sent_msg = await self.bot.send_photo(self.admin_chat_id, m.photo[-1].file_id, caption=f"{header}{m.caption or ''}", message_thread_id=thread_id)
            elif m.voice:
                await self.bot.send_message(self.admin_chat_id, f"{header}🎤 Голосовое сообщение:", message_thread_id=thread_id)
                sent_msg = await self.bot.copy_message(self.admin_chat_id, m.chat.id, m.message_id, message_thread_id=thread_id)
            elif m.video:
                await self.bot.send_message(self.admin_chat_id, f"{header}📹 Видео:", message_thread_id=thread_id)
                sent_msg = await self.bot.copy_message(self.admin_chat_id, m.chat.id, m.message_id, message_thread_id=thread_id)
            else:
                await self.bot.send_message(self.admin_chat_id, f"{header}📎 Вложение:", message_thread_id=thread_id)
                sent_msg = await self.bot.copy_message(self.admin_chat_id, m.chat.id, m.message_id, message_thread_id=thread_id)

            if sent_msg:
                self.msg_history_map[sent_msg.message_id] = user['id']
                # Очистка старой карты (память)
                if len(self.msg_history_map) > 5000:
                    first_key = next(iter(self.msg_history_map))
                    del self.msg_history_map[first_key]
                    
        except TelegramForbiddenError:
            logger.error("Admin chat unreachable!")
        except Exception as e:
            logger.error(f"Relay Error: {e}")

    # --- РЕГИСТРАЦИЯ ХЕНДЛЕРОВ ---
    async def setup_handlers(self):
        
        @self.router.message(CommandStart())
        async def handle_start(m: Message):
            user, is_new = await self.get_user_profile(m)
            
            # Проверка подписки
            if not await self.check_memberships(user['id']):
                kb_list = []
                for ch in self.channels:
                    btn = InlineKeyboardButton(text=f"Подписаться на {ch.get('name', 'канал')}", url=f"https://t.me/{ch.get('id').replace('@','')}")
                    kb_list.append([btn])
                kb_list.append([InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub")])
                
                return await m.answer(
                    "⚠️ <b>Для работы с ботом необходимо подписаться:</b>",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list)
                )

            keyboard = self.generate_markup()
            
            # Отправка приветствия
            if self.welcome_img:
                img_path = os.path.join(BASE_DIR, self.welcome_img.lstrip('/'))
                if os.path.exists(img_path):
                    await m.answer_photo(FSInputFile(img_path), caption=self.welcome_text, reply_markup=keyboard)
                else:
                    await m.answer(self.welcome_text, reply_markup=keyboard)
            else:
                await m.answer(self.welcome_text, reply_markup=keyboard)

            if is_new:
                await self.relay_to_admin(m, user, is_first=True)
            await self.log_message(user['id'], user['name'], "/start")

        @self.router.callback_query(F.data == "check_sub")
        async def on_check_sub(c: CallbackQuery):
            if await self.check_memberships(c.from_user.id):
                await c.message.delete()
                await handle_start(c.message)
            else:
                await c.answer("❌ Вы не подписаны на все каналы!", show_alert=True)

        @self.router.message(F.chat.id == self.admin_chat_id)
        async def on_admin_reply(m: Message):
            """Логика ответов админа"""
            target_id = None
            
            # 1. По reply
            if m.reply_to_message:
                target_id = self.msg_history_map.get(m.reply_to_message.message_id)
            
            # 2. По топику (если нет в мапе)
            if not target_id and m.message_thread_id:
                u_ref = next((u for u in self.users if u.get('topic_id') == m.message_thread_id), None)
                if u_ref: target_id = u_ref['id']

            if not target_id: return

            try:
                # Специальные команды в админке
                if m.text == "/ban":
                    for u in self.users:
                        if u['id'] == target_id: u['is_blocked'] = True
                    return await m.reply("🚫 Пользователь заблокирован.")
                
                if m.text == "/unban":
                    for u in self.users:
                        if u['id'] == target_id: u['is_blocked'] = False
                    return await m.reply("✅ Пользователь разблокирован.")

                # Проброс ответа пользователю
                await self.bot.copy_message(target_id, m.chat.id, m.message_id)
                await self.log_message(target_id, "ADMIN_REPLY", m.text or "[Медиа]", is_admin=True)
                
            except Exception as e:
                await m.reply(f"❌ Доставка не удалась: {e}")

        @self.router.message()
        async def on_user_message(m: Message):
            """Главный процессор входящих сообщений"""
            if m.chat.id == self.admin_chat_id: return
            
            user, is_new = await self.get_user_profile(m)
            if user.get('is_blocked'): return
            
            input_text = (m.text or m.caption or "").strip()

            # --- 1. ПРОВЕРКА КНОПОК ---
            for btn in self.buttons:
                if btn.get('text') == input_text:
                    resp = btn.get('response', '...')
                    btn_photo = btn.get('photo')
                    
                    if btn_photo:
                        p = os.path.join(BASE_DIR, btn_photo.lstrip('/'))
                        if os.path.exists(p):
                            await m.answer_photo(FSInputFile(p), caption=resp)
                        else: await m.answer(resp)
                    else:
                        await m.answer(resp)
                    
                    if btn.get('type') == 'request':
                        await self.relay_to_admin(m, user, btn_text=input_text)
                    
                    await self.log_message(user['id'], user['name'], f"КНОПКА: {input_text}")
                    return

            # --- 2. ПРОВЕРКА ТРИГГЕРОВ (АВТООТВЕТЫ) ---
            for trg in self.triggers:
                keyword = trg.get('keyword', '').lower()
                if keyword and keyword in input_text.lower():
                    trg_resp = trg.get('response', '')
                    trg_photo = trg.get('photo')
                    
                    if trg_photo:
                        tp = os.path.join(BASE_DIR, trg_photo.lstrip('/'))
                        if os.path.exists(tp):
                            await m.answer_photo(FSInputFile(tp), caption=trg_resp)
                        else: await m.answer(trg_resp)
                    else:
                        await m.answer(trg_resp)
                    
                    await self.log_message(user['id'], user['name'], f"ТРИГГЕР: {keyword}")
                    return

            # --- 3. ПЕРЕСЫЛКА АДМИНУ ---
            if self.settings.get('forwardToAdmin', True):
                await self.relay_to_admin(m, user, is_first=is_new)
            
            await self.log_message(user['id'], user['name'], input_text or "[Медиа/Файл]")

    # --- ИНТЕРФЕЙСНЫЕ МЕТОДЫ ---
    def generate_markup(self):
        """Создает динамическую клавиатуру"""
        active = [b for b in self.buttons if b.get('text')]
        if not active: return ReplyKeyboardRemove()
        
        rows = []
        # Группируем по 2 кнопки в ряд
        for i in range(0, len(active), 2):
            row = [KeyboardButton(text=btn['text']) for btn in active[i:i+2]]
            rows.append(row)
            
        return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

    async def start(self):
        """Запуск инстанса бота"""
        # Инициализация задач
        asyncio.create_task(self.sync_loop())
        
        # Регистрация роутеров
        await self.setup_handlers()
        self.dp.include_router(self.router)
        
        logger.info(f"[*] Engine online: Bot ID {self.bot_id}")
        try:
            # Сброс вебхука перед поллингом
            await self.bot.delete_webhook(drop_pending_updates=True)
            await self.dp.start_polling(self.bot)
        except Exception as e:
            logger.critical(f"Bot Polling Fatal Error: {e}")
        finally:
            self.is_running = False
            await self.bot.session.close()

# ==========================================
# 4. ВХОД В ПРОГРАММУ
# ==========================================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Error: Missing config file argument.")
        sys.exit(1)
        
    cfg_file = sys.argv[1]
    if not os.path.exists(cfg_file):
        print(f"Error: Config {cfg_file} not found.")
        sys.exit(1)
        
    try:
        with open(cfg_file, 'r', encoding='utf-8') as f:
            full_config = json.load(f)
            
        # Запуск асинхронного ядра
        engine = AdvancedBotInstance(full_config)
        asyncio.run(engine.start())
        
    except KeyboardInterrupt:
        print("\nShutdown by user.")
    except Exception as e:
        print(f"Startup Crash: {e}")
        logging.exception(e)
