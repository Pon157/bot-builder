
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
    ReplyKeyboardRemove, ForumTopicCreated
)
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter

# --- ГЛОБАЛЬНАЯ КОНФИГУРАЦИЯ ЛОГИРОВАНИЯ ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotCoreEngine")

def get_anon_id(user_id: int) -> str:
    """Генерирует уникальный короткий хеш для анонимного режима (Anon ID)."""
    return hashlib.md5(str(user_id).encode()).hexdigest()[:6].upper()

def format_admin_header(m: Message, settings: dict, is_first: bool = False, btn_text: str = "") -> str:
    """
    Сборка шапки сообщения для администратора. 
    Учитывает настройки анонимности, отображения ID, Имени и Юзернейма.
    """
    is_anon = settings.get('anonymousTopics', False)
    uid = m.from_user.id
    anon_tag = f"#{get_anon_id(uid)}"
    
    if is_anon:
        user_info = f"👤 <b>Аноним {anon_tag}</b>"
    else:
        info_parts = []
        if settings.get('showHeaderName', True):
            name = m.from_user.full_name or "Пользователь"
            info_parts.append(f"<b>{name}</b>")
        
        if settings.get('showHeaderUsername', True) and m.from_user.username:
            info_parts.append(f"(@{m.from_user.username})")
            
        if settings.get('showHeaderId', True):
            info_parts.append(f"ID: <code>{uid}</code>")
            
        user_info = " | ".join(info_parts) if info_parts else f"Юзер {anon_tag}"

    # Определение статуса (Тикет, Первое сообщение или обычный текст)
    if btn_text:
        status_line = f"🆘 <b>ЗАЯВКА [Кнопка: {btn_text}]:</b>"
    elif is_first:
        status_line = "🆕 <b>ПЕРВОЕ ОБРАЩЕНИЕ:</b>"
    else:
        status_line = "📩 <b>СООБЩЕНИЕ:</b>"

    return f"{status_line}\n{user_info}\n\n"

class BotInstance:
    def __init__(self, config_data: dict):
        self.bot_id = config_data.get('id')
        self.token = config_data.get('token')
        self.sb_url = os.getenv("SUPABASE_URL", "").rstrip('/')
        self.sb_key = os.getenv("SUPABASE_KEY", "")
        
        # Инициализация бота с поддержкой HTML и Forum
        self.bot = Bot(token=self.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher()
        self.router = Router()
        
        # Внутренние механизмы
        self.msg_map = {} # Связка admin_message_id -> user_id
        self.flood_cache = {} # user_id -> last_message_time
        self.is_running = True
        self.sync_queue = asyncio.Queue()
        
        self.apply_config(config_data)

    def apply_config(self, data: dict):
        """Применяет настройки из JSON-конфигурации."""
        raw_cfg = data.get('config', {}) if isinstance(data.get('config'), dict) else {}
        full_cfg = {**raw_cfg, **data}
        
        try:
            admin_id_raw = full_cfg.get('adminChatId')
            self.admin_chat_id = int(str(admin_id_raw).strip()) if admin_id_raw else None
        except ValueError:
            self.admin_chat_id = None
            logger.error(f"Invalid adminChatId: {admin_id_raw}")

        self.buttons = full_cfg.get('buttons', [])
        self.triggers = full_cfg.get('triggers', [])
        self.welcome_text = full_cfg.get('welcomeMessage', 'Здравствуйте!')
        self.settings = full_cfg.get('settings', {})
        
        # Настройки модерации и форума
        self.use_topics = self.settings.get('useTopics', False)
        self.topic_per_req = self.settings.get('topicPerRequest', False)
        self.rate_limit = float(self.settings.get('rateLimit', 1.0))
        self.auto_ban_limit = int(self.settings.get('autoBanThreshold', 3))
        
        self.users_list = full_cfg.get('connectedUsers', [])
        self.stats_data = full_cfg.get('stats') or {
            "totalMessages": 0, "incomingToday": 0, "outgoingToday": 0, "history": []
        }

    async def database_sync_worker(self):
        """Фоновый воркер для синхронизации состояния с БД Supabase."""
        async with httpx.AsyncClient() as client:
            headers = {
                "apikey": self.sb_key, 
                "Authorization": f"Bearer {self.sb_key}",
                "Content-Type": "application/json"
            }
            while self.is_running:
                action, payload = await self.sync_queue.get()
                try:
                    if action == "log_message":
                        await client.post(f"{self.sb_url}/rest/v1/bot_messages", json=payload, headers=headers)
                    elif action == "sync_state":
                        update_payload = {
                            "config": {
                                "connectedUsers": self.users_list, 
                                "stats": self.stats_data, 
                                "settings": self.settings
                            }
                        }
                        await client.patch(f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}", json=update_payload, headers=headers)
                except Exception as e:
                    logger.error(f"Database Sync Error: {e}")
                finally:
                    self.sync_queue.task_done()

    async def check_antispam(self, user_id: int) -> bool:
        """Проверка на флуд (интервал между сообщениями)."""
        if self.rate_limit <= 0: return False
        now = time.time()
        last_time = self.flood_cache.get(user_id, 0)
        if now - last_time < self.rate_limit:
            return True # Заблокировать (слишком часто)
        self.flood_cache[user_id] = now
        return False

    async def log_and_update(self, uid: int, name: str, text: str, is_admin: bool = False):
        """Запись сообщения в БД и обновление CRM статистики."""
        await self.sync_queue.put(("log_message", {
            "bot_id": self.bot_id, 
            "user_id": uid, 
            "first_name": name,
            "message_text": text[:950] if text else "[Медиа-файл]", 
            "is_from_admin": is_admin
        }))
        
        self.stats_data["totalMessages"] = self.stats_data.get("totalMessages", 0) + 1
        stat_key = "outgoingToday" if is_admin else "incomingToday"
        self.stats_data[stat_key] = self.stats_data.get(stat_key, 0) + 1
        
        await self.sync_queue.put(("sync_state", None))

    async def get_user_state(self, m: Message):
        """Получает объект пользователя или создает его при первом обращении."""
        uid = m.from_user.id
        user = next((u for u in self.users_list if u['id'] == uid), None)
        is_first_time = False
        
        if not user:
            is_first_time = True
            user = {
                "id": uid, 
                "first_name": m.from_user.first_name, 
                "username": m.from_user.username, 
                "is_banned": False, 
                "is_active": True, 
                "warns": 0, 
                "joined_at": int(time.time()),
                "last_topic_id": None
            }
            self.users_list.append(user)
            await self.sync_queue.put(("sync_state", None))
        elif not user.get("is_active", True):
            user["is_active"] = True
            await self.sync_queue.put(("sync_state", None))
            
        return user, is_first_time

    async def resolve_thread(self, user: dict, force_new: bool = False):
        """Находит или создает ветку (Topic) для Forum групп."""
        if not self.use_topics or not self.admin_chat_id: return None
        
        if not force_new and user.get("last_topic_id"):
            return user["last_topic_id"]
            
        try:
            is_anon = self.settings.get('anonymousTopics', False)
            topic_name = f"#{get_anon_id(user['id'])}" if is_anon else f"{user['first_name']} [{user['id']}]"
            
            new_topic = await self.bot.create_forum_topic(self.admin_chat_id, topic_name)
            user["last_topic_id"] = new_topic.message_thread_id
            await self.sync_queue.put(("sync_state", None))
            return new_topic.message_thread_id
        except Exception as e:
            logger.error(f"Topic Creation Error: {e}")
            return None

    async def forward_to_admin(self, m: Message, user: dict, is_first: bool = False, btn_text: str = ""):
        """Пересылка сообщения администратору с формированием шапки."""
        if not self.admin_chat_id: return
        
        # Определяем, нужно ли создавать новый топик (для тикетов или первого входа)
        force_new_topic = self.topic_per_req and (btn_text != "" or is_first)
        thread_id = await self.resolve_thread(user, force_new=force_new_topic)
        
        header_text = format_admin_header(m, self.settings, is_first, btn_text)
        
        try:
            sent_msg = None
            if m.text:
                sent_msg = await self.bot.send_message(
                    self.admin_chat_id, 
                    f"{header_text}{m.text}", 
                    message_thread_id=thread_id
                )
            elif m.photo:
                sent_msg = await self.bot.send_photo(
                    self.admin_chat_id, 
                    m.photo[-1].file_id, 
                    caption=f"{header_text}{m.caption or ''}", 
                    message_thread_id=thread_id
                )
            elif m.video:
                sent_msg = await self.bot.send_video(
                    self.admin_chat_id, 
                    m.video.file_id, 
                    caption=f"{header_text}{m.caption or ''}", 
                    message_thread_id=thread_id
                )
            else:
                # Для документов, стикеров и прочего - сначала шапку, потом само сообщение
                if header_text:
                    await self.bot.send_message(self.admin_chat_id, header_text, message_thread_id=thread_id)
                sent_msg = await self.bot.copy_message(
                    self.admin_chat_id, 
                    m.chat.id, 
                    m.message_id, 
                    message_thread_id=thread_id
                )
            
            if sent_msg:
                # Запоминаем ID сообщения админа, чтобы знать, кому отвечать реплаем
                self.msg_map[sent_msg.message_id] = user['id']
                
        except Exception as e:
            logger.error(f"Forwarding Critical Error: {e}")

    async def admin_control_logic(self, m: Message):
        """Логика команд модерации прямо из чата (реплаем или в топике)."""
        if not m.text or not (m.text.startswith("/") or m.text.startswith("!")):
            return False
            
        cmd_parts = m.text.lower().split()
        command = cmd_parts[0][1:] # ban, warn, unban и т.д.
        
        target_user = None
        # Поиск юзера по топику
        if m.message_thread_id:
            target_user = next((u for u in self.users_list if u.get("last_topic_id") == m.message_thread_id), None)
        
        # Поиск юзера по реплаю
        if not target_user and m.reply_to_message:
            uid = self.msg_map.get(m.reply_to_message.message_id)
            if uid:
                target_user = next((u for u in self.users_list if u['id'] == uid), None)
                
        if not target_user: return False

        uid = target_user['id']
        if command == "ban":
            target_user["is_banned"] = True
            await self.sync_queue.put(("sync_state", None))
            try: await self.bot.send_message(uid, "🚫 <b>Доступ ограничен администратором.</b>")
            except: pass
            await m.reply(f"✅ Пользователь {uid} заблокирован.")
            return True
        elif command == "unban":
            target_user["is_banned"] = False
            await self.sync_queue.put(("sync_state", None))
            await m.reply(f"✅ Пользователь {uid} разблокирован.")
            return True
        elif command == "warn":
            target_user["warns"] = target_user.get("warns", 0) + 1
            await self.sync_queue.put(("sync_state", None))
            
            if self.auto_ban_limit > 0 and target_user["warns"] >= self.auto_ban_limit:
                target_user["is_banned"] = True
                await self.sync_queue.put(("sync_state", None))
                try: await self.bot.send_message(uid, f"🚫 <b>Авто-бан:</b> Лимит предупреждений ({target_user['warns']}) исчерпан.")
                except: pass
                await m.reply(f"🚨 <b>АВТО-БАН!</b> Пользователь {uid} забанен (Варнов: {target_user['warns']}).")
            else:
                try: await self.bot.send_message(uid, f"⚠️ <b>Предупреждение!</b> ({target_user['warns']}/{self.auto_ban_limit})")
                except: pass
                await m.reply(f"⚠️ Предупреждение выдано. Всего: {target_user['warns']}/{self.auto_ban_limit}")
            return True
            
        return False

    async def core_handlers_setup(self):
        """Регистрация всех обработчиков aiogram."""
        
        @self.router.message(CommandStart())
        async def handle_start(m: Message):
            user, is_new = await self.get_user_state(m)
            if user.get("is_banned"): return
            
            await m.answer(self.welcome_text, reply_markup=self.get_main_keyboard())
            await self.forward_to_admin(m, user, is_first=is_new)
            await self.log_and_update(user['id'], m.from_user.full_name, "/start")

        @self.router.message(F.chat.id == self.admin_chat_id)
        async def handle_admin_input(m: Message):
            # 1. Проверка команд модерации
            if await self.admin_control_logic(m): return
            
            # 2. Обычный ответ пользователю
            target_id = None
            if m.message_thread_id:
                u = next((u for u in self.users_list if u.get("last_topic_id") == m.message_thread_id), None)
                if u: target_id = u["id"]
            
            if not target_id and m.reply_to_message:
                target_id = self.msg_map.get(m.reply_to_message.message_id)
                
            if target_id:
                try:
                    await self.bot.copy_message(target_id, m.chat.id, m.message_id)
                    await self.log_and_update(target_id, "Admin", m.text or "[Медиа]", is_admin=True)
                except TelegramForbiddenError:
                    # Уведомление о том, что бот заблокирован пользователем
                    await m.reply("❌ <b>Ошибка:</b> Пользователь заблокировал бота или удалил чат.")
                    u = next((u for u in self.users_list if u['id'] == target_id), None)
                    if u: 
                        u["is_active"] = False
                        await self.sync_queue.put(("sync_state", None))

        @self.router.message()
        async def handle_user_input(m: Message):
            if self.admin_chat_id and m.chat.id == self.admin_chat_id: return
            
            user, is_new = await self.get_user_state(m)
            if user.get("is_banned"): return
            
            # Анти-спам
            if await self.check_antispam(user['id']): return

            # Обработка текстовых триггеров и кнопок
            if m.text:
                clean_text = m.text.lower().strip()
                
                # Поиск по кнопкам
                for btn in self.buttons:
                    if btn.get('text') and btn['text'].lower() == clean_text:
                        if btn.get('type') == 'request':
                            await self.forward_to_admin(m, user, btn_text=btn['text'])
                        if btn.get('response'):
                            await m.answer(btn['response'])
                        await self.log_and_update(user['id'], m.from_user.full_name, f"КНОПКА: {btn['text']}")
                        return
                
                # Поиск по триггерам
                for trig in self.triggers:
                    if trig.get('keyword') and trig['keyword'].lower() in clean_text:
                        await m.answer(trig['response'])
                        await self.log_and_update(user['id'], m.from_user.full_name, f"ТРИГГЕР: {trig['keyword']}")
                        return

            # Если ничего не сработало — просто пересылаем
            await self.forward_to_admin(m, user, is_first=is_new)
            await self.log_and_update(user['id'], m.from_user.full_name, m.text or "[Медиа]")

    def get_main_keyboard(self):
        """Сборка Reply-клавиатуры из настроек инстанса."""
        active_btns = [b for b in self.buttons if b.get('text')]
        if not active_btns: return ReplyKeyboardRemove()
        
        keyboard_rows = []
        # Размещаем по 2 кнопки в ряд
        for i in range(0, len(active_btns), 2):
            row = [KeyboardButton(text=b['text']) for b in active_btns[i:i+2]]
            keyboard_rows.append(row)
            
        return ReplyKeyboardMarkup(keyboard=keyboard_rows, resize_keyboard=True)

    async def run_instance(self):
        """Запуск цикла событий инстанса."""
        asyncio.create_task(self.database_sync_worker())
        await self.core_handlers_setup()
        self.dp.include_router(self.router)
        logger.info(f"[*] Бот-инстанс {self.bot_id} успешно инициализирован.")
        try:
            await self.dp.start_polling(self.bot)
        finally:
            self.is_running = False
            await self.bot.session.close()

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    try:
        with open(sys.argv[1], 'r', encoding='utf-8') as config_file:
            instance_cfg = json.load(config_file)
        asyncio.run(BotInstance(instance_cfg).run_instance())
    except Exception as fatal_error:
        logger.error(f"КРИТИЧЕСКИЙ СБОЙ ЯДРА: {fatal_error}")
