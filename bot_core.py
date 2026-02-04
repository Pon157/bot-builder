
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
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("BotCore")

def format_msg(template: str, m: Message, btn_text: str = "") -> str:
    if not template: return f"📩 Сообщение от {m.from_user.id}"
    res = template.replace("{{id}}", str(m.from_user.id))
    res = res.replace("{{name}}", m.from_user.full_name or "User")
    res = res.replace("{{username}}", f"@{m.from_user.username}" if m.from_user.username else "none")
    res = res.replace("{{button}}", btn_text)
    return res

class BotInstance:
    def __init__(self, config_data):
        self.config = config_data
        self.token = config_data.get('token')
        self.bot_id = config_data.get('id')
        self.owner_id = config_data.get('owner_id')
        
        # Настройки администрирования
        raw_admin_id = config_data.get('adminChatId')
        self.admin_id = int(raw_admin_id) if raw_admin_id and str(raw_admin_id).strip().lstrip('-').isdigit() else None
        
        # Настройки Supabase
        self.sb_url = os.getenv("SUPABASE_URL")
        self.sb_key = os.getenv("SUPABASE_KEY")
        
        self.bot = Bot(token=self.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher()
        self.router = Router()
        
        # Параметры логики из конфига
        self.buttons = config_data.get('buttons', [])
        self.triggers = config_data.get('triggers', [])
        self.welcome_message = config_data.get('welcomeMessage', 'Привет!')
        self.connected_users = config_data.get('connectedUsers', [])
        self.subscribers = config_data.get('subscribers', [])
        self.settings = config_data.get('settings', {})
        self.stats = config_data.get('stats', {
            "totalMessages": 0, "incomingToday": 0, "outgoingToday": 0, 
            "bannedCount": 0, "history": [], "activeUsers24h": 0
        })
        
        self.auto_ban_threshold = self.settings.get('autoBanThreshold', 0)
        self.use_topics = self.settings.get('useTopics', False)
        self.topic_per_request = self.settings.get('topicPerRequest', False)
        
        # Очередь для синхронизации БД
        self.sync_queue = asyncio.Queue()

    async def db_sync_worker(self):
        """Воркер для фоновой записи в БД Supabase"""
        async with httpx.AsyncClient() as client:
            headers = {"apikey": self.sb_key, "Authorization": f"Bearer {self.sb_key}", "Content-Type": "application/json"}
            while True:
                task = await self.sync_queue.get()
                action, data = task
                try:
                    if action == "msg":
                        await client.post(f"{self.sb_url.rstrip('/')}/rest/v1/bot_messages", json=data, headers=headers)
                    elif action == "bot_config":
                        # Синхронизируем весь объект конфига в колонку config
                        payload = {
                            "config": {
                                **self.config.get("config", {}), # Сохраняем остальные поля
                                "connectedUsers": self.connected_users,
                                "subscribers": self.subscribers,
                                "stats": self.stats
                            }
                        }
                        await client.patch(f"{self.sb_url.rstrip('/')}/rest/v1/bots?id=eq.{self.bot_id}", json=payload, headers=headers)
                except Exception as e:
                    logger.error(f"Sync error: {e}")
                finally:
                    self.sync_queue.task_done()

    async def update_stats(self, direction: str):
        self.stats["totalMessages"] = self.stats.get("totalMessages", 0) + 1
        key = "incomingToday" if direction == "incoming" else "outgoingToday"
        self.stats[key] = self.stats.get(key, 0) + 1
        await self.sync_queue.put(("bot_config", {}))

    async def log_message(self, user_id, name, text, is_admin=False):
        payload = {
            "bot_id": self.bot_id, 
            "user_id": user_id, 
            "first_name": name,
            "message_text": (text[:950] + "...") if text and len(text) > 950 else (text or "[Медиа]"),
            "is_from_admin": is_admin
        }
        await self.sync_queue.put(("msg", payload))
        await self.update_stats("incoming" if not is_admin else "outgoing")

    async def get_or_create_user(self, m: Message):
        user_id = m.from_user.id
        user_obj = next((u for u in self.connected_users if u['id'] == user_id), None)
        
        if not user_obj:
            user_obj = {
                "id": user_id, 
                "first_name": m.from_user.first_name, 
                "username": m.from_user.username,
                "is_banned": False, 
                "is_active": True, 
                "warns": 0, 
                "joined_at": int(datetime.now().timestamp()),
                "thread_id": None
            }
            self.connected_users.append(user_obj)
            if user_id not in self.subscribers:
                self.subscribers.append(user_id)
            await self.sync_queue.put(("bot_config", {}))
        
        return user_obj

    async def update_user(self, user_id, **kwargs):
        for u in self.connected_users:
            if u['id'] == user_id:
                u.update(kwargs)
                break
        await self.sync_queue.put(("bot_config", {}))

    def get_main_kb(self):
        if not self.buttons: return None
        # Фильтруем пустые кнопки
        valid_buttons = [b for b in self.buttons if b.get('text')]
        if not valid_buttons: return None
        
        rows = []
        for i in range(0, len(valid_buttons), 2):
            rows.append([KeyboardButton(text=b['text']) for b in valid_buttons[i:i+2]])
        return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

    async def register_handlers(self):
        @self.router.message(CommandStart())
        async def cmd_start(m: Message):
            user = await self.get_or_create_user(m)
            if user.get("is_banned"): return
            
            msg = format_msg(self.welcome_message, m)
            await m.answer(msg, reply_markup=self.get_main_kb())
            await self.log_message(m.from_user.id, m.from_user.full_name, "/start")

        @self.router.message(Command("warn", "unwarn", "ban", "unban"))
        async def admin_moderation(m: Message):
            if not self.admin_id or m.chat.id != self.admin_id: return

            target_user = None
            # 1. Поиск по топику (Thread ID)
            if m.message_thread_id:
                target_user = next((u for u in self.connected_users if u.get("thread_id") == m.message_thread_id), None)
            
            # 2. Поиск по реплаю (извлекаем ID из текста сообщения-заголовка)
            if not target_user and m.reply_to_message:
                content = m.reply_to_message.text or m.reply_to_message.caption or ""
                match = re.search(r"ID: (\d+)", content)
                if match:
                    uid = int(match.group(1))
                    target_user = next((u for u in self.connected_users if u["id"] == uid), None)

            if not target_user:
                return await m.reply("❌ Пользователь не найден. Используйте команду в топике пользователя или ответом на сообщение с его ID.")

            cmd = m.text.split()[0].replace("/", "").lower()
            uid = target_user['id']

            if cmd == "warn":
                new_warns = target_user.get("warns", 0) + 1
                is_auto_ban = self.auto_ban_threshold > 0 and new_warns >= self.auto_ban_threshold
                await self.update_user(uid, warns=new_warns, is_banned=is_auto_ban)
                
                txt = f"⚠️ <b>Вам выдано предупреждение!</b>\nВсего варнов: {new_warns}"
                if self.auto_ban_threshold > 0: txt += f" / {self.auto_ban_threshold}"
                if is_auto_ban: txt += "\n🚫 Вы были автоматически заблокированы за превышение лимита."
                
                try: await self.bot.send_message(uid, txt)
                except: pass
                await m.reply(f"✅ Варн выдан пользователю {uid}. Всего: {new_warns}" + (" [АВТОБАН]" if is_auto_ban else ""))

            elif cmd == "unwarn":
                new_warns = max(0, target_user.get("warns", 0) - 1)
                await self.update_user(uid, warns=new_warns)
                try: await self.bot.send_message(uid, f"ℹ️ <b>С вас снято предупреждение администратором.</b>\nОсталось варнов: {new_warns}")
                except: pass
                await m.reply(f"✅ Варн снят. У пользователя {uid} осталось: {new_warns}")

            elif cmd == "ban":
                await self.update_user(uid, is_banned=True)
                try: await self.bot.send_message(uid, "🚫 <b>Вы были заблокированы администратором.</b>")
                except: pass
                await m.reply(f"✅ Пользователь {uid} заблокирован.")

            elif cmd == "unban":
                await self.update_user(uid, is_banned=False)
                try: await self.bot.send_message(uid, "✅ <b>Вы были разблокированы администратором!</b>")
                except: pass
                await m.reply(f"✅ Пользователь {uid} разблокирован.")

        @self.router.message(F.chat.id == self.admin_id, F.reply_to_message)
        async def admin_reply(m: Message):
            # Игнорируем системные сообщения в топиках
            if m.is_topic_message and not m.reply_to_message: return
            
            target_id = None
            # Если сообщение в топике - ищем владельца топика
            if m.message_thread_id:
                u = next((u for u in self.connected_users if u.get("thread_id") == m.message_thread_id), None)
                if u: target_id = u["id"]
            
            # Если не в топике или не нашли - ищем ID в реплае
            if not target_id and m.reply_to_message:
                content = m.reply_to_message.text or m.reply_to_message.caption or ""
                match = re.search(r"ID: (\d+)", content)
                if match: target_id = int(match.group(1))
            
            if target_id:
                try:
                    await self.bot.copy_message(target_id, m.chat.id, m.message_id)
                    await self.log_message(target_id, "Admin", m.text or "[Медиа]", is_admin=True)
                except Exception as e:
                    await m.reply(f"❌ Ошибка отправки пользователю {target_id}: {e}")

        @self.router.message()
        async def main_handler(m: Message):
            # Игнорируем сообщения от админа, если они не являются реплаями (обработаны выше)
            if self.admin_id and m.chat.id == self.admin_id: return
            
            user = await self.get_or_create_user(m)
            if user.get("is_banned"): return

            # 1. Обработка кнопок
            if m.text:
                low = m.text.lower().strip()
                for btn in self.buttons:
                    if btn.get("text") and btn["text"].lower() == low:
                        # Кнопка типа "request" (заявка)
                        if btn.get("type") == "request" and self.admin_id:
                            if (self.topic_per_request or self.use_topics) and not user.get("thread_id"):
                                try:
                                    topic = await self.bot.create_forum_topic(self.admin_id, f"Ticket: {m.from_user.first_name} [{m.from_user.id}]")
                                    await self.update_user(user['id'], thread_id=topic.message_thread_id)
                                    user['thread_id'] = topic.message_thread_id
                                except: pass
                            
                            admin_txt = format_msg(btn.get("adminTemplate", "👤 Новая заявка через кнопку: {{button}}\nID: {{id}}"), m, btn['text'])
                            await self.bot.send_message(self.admin_id, admin_txt, message_thread_id=user.get("thread_id"))
                        
                        # Обычный ответ на кнопку
                        await m.answer(btn.get("response", "Запрос принят."), reply_markup=self.get_main_kb())
                        await self.log_message(m.from_user.id, m.from_user.full_name, f"Нажата кнопка: {btn['text']}")
                        return

                # 2. Обработка триггеров (автоответы)
                for t in self.triggers:
                    if t.get("keyword") and t["keyword"].lower() in low:
                        await m.answer(t["response"], reply_markup=self.get_main_kb())
                        await self.log_message(m.from_user.id, m.from_user.full_name, f"Сработал триггер: {t['keyword']}")
                        return

            # 3. Livegram Mode (Пересылка администратору)
            if self.admin_id:
                # Если включены топики и у юзера его еще нет - создаем
                if self.use_topics and not user.get("thread_id"):
                    try:
                        topic = await self.bot.create_forum_topic(self.admin_id, f"{m.from_user.full_name} [{m.from_user.id}]")
                        await self.update_user(user['id'], thread_id=topic.message_thread_id)
                        user['thread_id'] = topic.message_thread_id
                    except Exception as e:
                        logger.error(f"Failed to create topic: {e}")

                header = f"📩 <b>Сообщение от</b> {m.from_user.full_name}\nID: <code>{m.from_user.id}</code>"
                if m.from_user.username: header += f"\nUsername: @{m.from_user.username}"
                
                try:
                    # Отправляем заголовок и само сообщение (копируем)
                    await self.bot.send_message(self.admin_id, header, message_thread_id=user.get("thread_id"))
                    await self.bot.copy_message(self.admin_id, m.chat.id, m.message_id, message_thread_id=user.get("thread_id"))
                    await self.log_message(m.from_user.id, m.from_user.full_name, m.text or "[Медиа]")
                except TelegramForbiddenError:
                    await self.update_user(user['id'], is_active=False)
                except Exception as e:
                    logger.error(f"Forwarding error: {e}")

    async def run(self):
        # Запуск фонового воркера синхронизации
        sync_task = asyncio.create_task(self.db_sync_worker())
        await self.register_handlers()
        self.dp.include_router(self.router)
        logger.info(f"Bot Instance {self.bot_id} (Engine) starting polling...")
        try:
            await self.dp.start_polling(self.bot)
        finally:
            sync_task.cancel()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.error("Usage: python bot_core.py <config_path>")
        sys.exit(1)
    
    config_path = sys.argv[1]
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        
        asyncio.run(BotInstance(cfg).run())
    except Exception as e:
        logger.error(f"FATAL ERROR: {e}")
