
import asyncio
import logging
import json
import re
import httpx
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ContentType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BotCore")

class BotInstance:
    def __init__(self, config_data):
        self.config = config_data
        self.token = config_data.get('token')
        self.admin_id = int(config_data.get('adminChatId')) if config_data.get('adminChatId') else None
        self.bot_id = config_data.get('id')
        self.sb_url = os.getenv("SUPABASE_URL")
        self.sb_key = os.getenv("SUPABASE_KEY")
        
        self.bot = Bot(token=self.token, parse_mode=ParseMode.HTML)
        self.dp = Dispatcher()
        self.router = Router()
        
        self.buttons = config_data.get('buttons', [])
        self.triggers = config_data.get('triggers', [])
        self.welcome_message = config_data.get('welcomeMessage', 'Привет!')
        self.connected_users = config_data.get('connectedUsers', [])
        self.auto_ban_threshold = config_data.get('settings', {}).get('autoBanThreshold', 0)

    async def sync_db(self, action="users", user_id=None, name=None, text=None, is_admin=False, warns=None, is_banned=None):
        """Синхронизация данных с Supabase"""
        if not self.sb_url or not self.sb_key: return

        async with httpx.AsyncClient() as client:
            headers = {"apikey": self.sb_key, "Authorization": f"Bearer {self.sb_key}"}
            
            # Логирование сообщений
            if action == "msg":
                payload = {
                    "bot_id": self.bot_id, "user_id": user_id, "first_name": name,
                    "message_text": text[:1000] if text else "[Медиа]", "is_from_admin": is_admin
                }
                await client.post(f"{self.sb_url}/rest/v1/bot_messages", json=payload, headers=headers)
            
            # Синхронизация списка юзеров в конфиге бота
            if action == "users":
                found = False
                for u in self.connected_users:
                    if u['id'] == user_id:
                        if is_banned is not None: u['is_banned'] = is_banned
                        if warns is not None: u['warns'] = warns
                        found = True; break
                if not found:
                    self.connected_users.append({
                        "id": user_id, "first_name": name, "is_banned": False, 
                        "is_active": True, "warns": 0, "joined_at": int(datetime.now().timestamp())
                    })
                
                await client.patch(
                    f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                    json={"config": {**self.config, "connectedUsers": self.connected_users}},
                    headers=headers
                )

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
            await self.sync_db(action="users", user_id=m.from_user.id, name=m.from_user.full_name)
            await self.sync_db(action="msg", user_id=m.from_user.id, name=m.from_user.full_name, text="/start")

        @self.router.message(Command("help"))
        async def cmd_help(m: Message):
            if m.from_user.id == self.admin_id:
                text = "🛠 <b>Админ-панель Модерации:</b>\n\n" \
                       "Используйте в ответ (reply) на сообщение пользователя:\n" \
                       "• <code>/ban</code> — полная блокировка\n" \
                       "• <code>/unban</code> — разблокировка\n" \
                       "• <code>/warn</code> — выдать предупреждение\n" \
                       "• <code>/unwarn</code> — снять предупреждение\n\n" \
                       "Просто напишите текст в ответ, чтобы отправить его юзеру."
            else:
                text = "<b>🆘 Помощь</b>\n\nНапишите ваш вопрос в чат. Администратор ответит вам при первой возможности."
            await m.answer(text)

        @self.router.message(F.chat.id == self.admin_id, F.reply_to_message)
        async def admin_action_handler(m: Message):
            # Извлекаем ID юзера из заголовка пересланного сообщения
            reply = m.reply_to_message
            target_id_match = re.search(r"ID: (\d+)", reply.text or reply.caption or "")
            if not target_id_match: return await m.reply("❌ Не удалось найти ID пользователя в сообщении.")
            
            uid = int(target_id_match.group(1))
            user_data = next((u for u in self.connected_users if u['id'] == uid), None)
            
            cmd = m.text.lower().strip() if m.text else ""
            
            if cmd == "/ban":
                await self.sync_db(user_id=uid, is_banned=True)
                return await m.reply(f"🚫 Пользователь {uid} забанен.")
            
            if cmd == "/unban":
                await self.sync_db(user_id=uid, is_banned=False)
                return await m.reply(f"✅ Пользователь {uid} разбанен.")
            
            if cmd == "/warn":
                curr_warns = (user_data.get('warns', 0) if user_data else 0) + 1
                is_ban = self.auto_ban_threshold > 0 and curr_warns >= self.auto_ban_threshold
                await self.sync_db(user_id=uid, warns=curr_warns, is_banned=is_ban)
                msg = f"⚠️ Выдан варн ({curr_warns})."
                if is_ban: msg += " Достигнут лимит — АВТОБАН."
                return await m.reply(msg)

            if cmd == "/unwarn":
                curr_warns = max(0, (user_data.get('warns', 0) if user_data else 0) - 1)
                await self.sync_db(user_id=uid, warns=curr_warns)
                return await m.reply(f"🛡 Варн снят. Теперь: {curr_warns}")

            # Если не команда — значит ответ пользователю
            try:
                await self.bot.copy_message(chat_id=uid, from_chat_id=m.chat.id, message_id=m.message_id)
                await m.reply("✅ Доставлено")
                await self.sync_db(action="msg", user_id=uid, name="Admin", text=m.text or "[Media]", is_admin=True)
            except Exception as e:
                await m.reply(f"❌ Ошибка отправки: {e}")

        @self.router.message()
        async def main_handler(m: Message):
            uid = m.from_user.id
            if uid == self.admin_id: return

            # Проверка бана
            user_data = next((u for u in self.connected_users if u['id'] == uid), None)
            if user_data and user_data.get('is_banned'): return

            # 1. Кнопки и триггеры
            if m.text:
                txt = m.text.lower()
                for b in self.buttons:
                    if b['text'].lower() == txt:
                        await m.answer(b['response'])
                        await self.sync_db(action="msg", user_id=uid, name=m.from_user.full_name, text=f"Button: {b['text']}")
                        return
                for t in self.triggers:
                    if t['keyword'].lower() in txt:
                        await m.answer(t['response'])
                        await self.sync_db(action="msg", user_id=uid, name=m.from_user.full_name, text=f"Trigger: {t['keyword']}")
                        return

            # 2. Livegram Пересылка Админу
            if self.admin_id:
                header = f"📩 <b>Сообщение от юзера</b>\n" \
                         f"Имя: {m.from_user.full_name}\n" \
                         f"ID: <code>{uid}</code>"
                if m.from_user.username: header += f"\nЮзер: @{m.from_user.username}"
                
                try:
                    await self.bot.send_message(self.admin_id, header)
                    # copy_message идеально подходит для всех типов медиа
                    await self.bot.copy_message(chat_id=self.admin_id, from_chat_id=m.chat.id, message_id=m.message_id)
                    await self.sync_db(action="msg", user_id=uid, name=m.from_user.full_name, text=m.text)
                except Exception as e:
                    logger.error(f"Forward error: {e}")

    async def run(self):
        await self.register_handlers()
        self.dp.include_router(self.router)
        logger.info(f"Bot {self.bot_id} started...")
        await self.dp.start_polling(self.bot)

if __name__ == "__main__":
    import sys
    with open(sys.argv[1], 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    asyncio.run(BotInstance(cfg).run())
