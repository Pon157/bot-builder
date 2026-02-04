
import asyncio
import logging
import json
import re
import httpx
import os
import sys
from datetime import datetime
from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ContentType
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("BotCore")

class BotInstance:
    def __init__(self, config_data):
        self.config = config_data
        self.token = config_data.get('token')
        self.bot_id = config_data.get('id')
        
        # Настройки администрирования
        raw_admin_id = config_data.get('adminChatId')
        self.admin_id = int(raw_admin_id) if raw_admin_id and str(raw_admin_id).isdigit() else None
        
        # Настройки Supabase
        self.sb_url = os.getenv("SUPABASE_URL")
        self.sb_key = os.getenv("SUPABASE_KEY")
        
        self.bot = Bot(token=self.token, parse_mode=ParseMode.HTML)
        self.dp = Dispatcher()
        self.router = Router()
        
        # Параметры логики
        self.buttons = config_data.get('buttons', [])
        self.triggers = config_data.get('triggers', [])
        self.welcome_message = config_data.get('welcomeMessage', 'Привет!')
        self.connected_users = config_data.get('connectedUsers', [])
        self.settings = config_data.get('settings', {})
        self.auto_ban_threshold = self.settings.get('autoBanThreshold', 0)
        
        # Очередь для синхронизации БД (чтобы не спамить запросами)
        self.sync_queue = asyncio.Queue()

    async def db_sync_worker(self):
        """Воркер для фоновой записи в БД"""
        async with httpx.AsyncClient() as client:
            headers = {"apikey": self.sb_key, "Authorization": f"Bearer {self.sb_key}"}
            while True:
                task = await self.sync_queue.get()
                action, data = task
                try:
                    if action == "msg":
                        await client.post(f"{self.sb_url.rstrip('/')}/rest/v1/bot_messages", json=data, headers=headers)
                    elif action == "bot_config":
                        await client.patch(f"{self.sb_url.rstrip('/')}/rest/v1/bots?id=eq.{self.bot_id}", json=data, headers=headers)
                except Exception as e:
                    logger.error(f"Sync error: {e}")
                finally:
                    self.sync_queue.task_done()

    async def log_message(self, user_id, name, text, is_admin=False):
        payload = {
            "bot_id": self.bot_id, 
            "user_id": user_id, 
            "first_name": name,
            "message_text": (text[:950] + "...") if text and len(text) > 950 else (text or "[Медиа]"),
            "is_from_admin": is_admin
        }
        await self.sync_queue.put(("msg", payload))

    async def update_user_status(self, user_id, name=None, is_banned=None, warns=None, is_active=True):
        updated = False
        user_obj = None
        for u in self.connected_users:
            if u['id'] == user_id:
                if is_banned is not None: u['is_banned'] = is_banned
                if warns is not None: u['warns'] = warns
                u['is_active'] = is_active
                user_obj = u
                updated = True
                break
        
        if not updated and name:
            user_obj = {
                "id": user_id, "first_name": name, "is_banned": False, 
                "is_active": True, "warns": 0, "joined_at": int(datetime.now().timestamp())
            }
            self.connected_users.append(user_obj)
        
        # Пушим обновление конфига целиком
        await self.sync_queue.put(("bot_config", {"config": {**self.config, "connectedUsers": self.connected_users}}))
        return user_obj

    def get_main_kb(self):
        if not self.buttons: return None
        rows = []
        for i in range(0, len(self.buttons), 2):
            rows.append([KeyboardButton(text=b['text']) for b in self.buttons[i:i+2]])
        return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

    async def register_handlers(self):
        @self.router.message(CommandStart())
        async def cmd_start(m: Message):
            await m.answer(self.welcome_message, reply_markup=self.get_main_kb())
            await self.update_user_status(m.from_user.id, m.from_user.full_name)
            await self.log_message(m.from_user.id, m.from_user.full_name, "/start")

        @self.router.message(Command("help"))
        async def cmd_help(m: Message):
            if m.from_user.id == self.admin_id:
                text = "🛠 <b>Админ-панель:</b>\n\nОтветьте на сообщение юзера текстом или командами:\n" \
                       "• <code>/ban</code> — бан\n" \
                       "• <code>/unban</code> — разбан\n" \
                       "• <code>/warn</code> — +1 варн"
            else:
                text = "<b>🆘 Помощь</b>\n\nНапишите сообщение, и оператор ответит вам."
            await m.answer(text)

        # Обработка команд модерации от админа
        @self.router.message(F.chat.id == self.admin_id, F.reply_to_message, F.text.startswith("/"))
        async def admin_commands(m: Message):
            reply = m.reply_to_message
            match = re.search(r"ID: (\d+)", reply.text or reply.caption or "")
            if not match: return
            
            uid = int(match.group(1))
            cmd = m.text.lower().strip()
            
            if cmd == "/ban":
                await self.update_user_status(uid, is_banned=True)
                try: await self.bot.send_message(uid, "🚫 <b>Вы были заблокированы администратором.</b>")
                except: pass
                await m.reply(f"✅ Пользователь {uid} забанен.")
            
            elif cmd == "/unban":
                await self.update_user_status(uid, is_banned=False)
                try: await self.bot.send_message(uid, "✅ <b>Ваша блокировка снята.</b>")
                except: pass
                await m.reply(f"✅ Пользователь {uid} разблокирован.")
            
            elif cmd == "/warn":
                user = await self.update_user_status(uid)
                new_warns = (user.get('warns', 0)) + 1
                is_auto_ban = self.auto_ban_threshold > 0 and new_warns >= self.auto_ban_threshold
                await self.update_user_status(uid, warns=new_warns, is_banned=is_auto_ban)
                
                msg = f"⚠️ <b>Вам выдано предупреждение ({new_warns}).</b>"
                if is_auto_ban: msg += "\n🚫 Вы автоматически заблокированы."
                try: await self.bot.send_message(uid, msg)
                except: pass
                await m.reply(f"⚠️ Варн выдан. Всего: {new_warns}" + (" [АВТОБАН]" if is_auto_ban else ""))

        # Пересылка ответа админа юзеру
        @self.router.message(F.chat.id == self.admin_id, F.reply_to_message)
        async def admin_reply(m: Message):
            match = re.search(r"ID: (\d+)", m.reply_to_message.text or m.reply_to_message.caption or "")
            if not match: return
            uid = int(match.group(1))
            try:
                await self.bot.copy_message(chat_id=uid, from_chat_id=m.chat.id, message_id=m.message_id)
                await m.react([{"type": "emoji", "emoji": "✅"}])
                await self.log_message(uid, "Admin", m.text or "[Медиа]", is_admin=True)
            except Exception as e:
                await m.reply(f"❌ Ошибка отправки: {e}")

        # Основной хендлер сообщений от юзеров
        @self.router.message()
        async def handle_user_msg(m: Message):
            if m.from_user.id == self.admin_id: return
            
            # Проверка блокировки
            user = await self.update_user_status(m.from_user.id, m.from_user.full_name)
            if user.get('is_banned'): return

            # Логика кнопок и триггеров
            if m.text:
                txt = m.text.lower().strip()
                for b in self.buttons:
                    if b['text'].lower() == txt:
                        return await m.answer(b['response'])
                for t in self.triggers:
                    if t['keyword'].lower() in txt:
                        return await m.answer(t['response'])

            # Livegram: Пересылка админу
            if self.admin_id:
                header = f"📩 <b>Сообщение от</b> {m.from_user.full_name}\nID: <code>{m.from_user.id}</code>"
                if m.from_user.username: header += f"\nUsername: @{m.from_user.username}"
                
                try:
                    await self.bot.send_message(self.admin_id, header)
                    await self.bot.copy_message(chat_id=self.admin_id, from_chat_id=m.chat.id, message_id=m.message_id)
                    await self.log_message(m.from_user.id, m.from_user.full_name, m.text)
                except TelegramForbiddenError:
                    await self.update_user_status(m.from_user.id, is_active=False)
                except Exception as e:
                    logger.error(f"Forwarding error: {e}")

    async def run(self):
        # Запускаем фоновые задачи
        asyncio.create_task(self.db_sync_worker())
        await self.register_handlers()
        self.dp.include_router(self.router)
        logger.info(f"Bot Instance {self.bot_id} is running...")
        await self.dp.start_polling(self.bot)

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    try:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        asyncio.run(BotInstance(cfg).run())
    except Exception as e:
        logger.error(f"FATAL: {e}")
