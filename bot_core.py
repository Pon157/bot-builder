
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
from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ContentType
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotCore")

def get_anon_id(user_id: int) -> str:
    """Генерирует уникальный хеш-ID для анонимности."""
    return hashlib.md5(str(user_id).encode()).hexdigest()[:5].upper()

def format_msg(template: str, m: Message, settings: dict, is_anon: bool = False, btn_text: str = "") -> str:
    """Форматирует информационную 'шапку' для админа."""
    show_id = settings.get('showHeaderId', True)
    show_name = settings.get('showHeaderName', True)
    show_user = settings.get('showHeaderUsername', True)
    
    # Принудительная анонимность если все выключено в настройках
    force_anon = not (show_id or show_name or show_user) or is_anon

    content_preview = m.text or m.caption or "[Медиа]"
    if len(content_preview) > 100: content_preview = content_preview[:97] + "..."

    # Обработка шаблона
    if template and template.strip():
        res = template
        res = res.replace("{{id}}", str(m.from_user.id))
        if force_anon:
            res = res.replace("{{name}}", f"User #{get_anon_id(m.from_user.id)}")
            res = res.replace("{{username}}", "hidden")
        else:
            res = res.replace("{{name}}", m.from_user.full_name or "User")
            res = res.replace("{{username}}", f"@{m.from_user.username}" if m.from_user.username else "none")
        res = res.replace("{{button}}", btn_text or "—")
        res = res.replace("{{text}}", content_preview)
        return res

    # Стандартная шапка
    parts = []
    if force_anon:
        parts.append(f"👤 <b>User #{get_anon_id(m.from_user.id)}</b>")
    else:
        if show_name: parts.append(f"<b>{m.from_user.full_name}</b>")
        if show_user and m.from_user.username: parts.append(f"(@{m.from_user.username})")
    
    if show_id or force_anon:
        parts.append(f"ID: <code>{m.from_user.id}</code>")

    header = "📩 " + " | ".join(parts)
    if btn_text: header += f"\n🔘 Кнопка: <b>{btn_text}</b>"
    header += f"\n\n{content_preview}"
    return header

class BotInstance:
    def __init__(self, config_data):
        self.config = config_data
        self.token = config_data.get('token')
        self.bot_id = config_data.get('id')
        
        raw_admin_id = config_data.get('adminChatId')
        try:
            self.admin_id = int(str(raw_admin_id).strip()) if raw_admin_id else None
        except:
            self.admin_id = None
        
        self.sb_url = os.getenv("SUPABASE_URL")
        self.sb_key = os.getenv("SUPABASE_KEY")
        
        self.bot = Bot(token=self.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher()
        self.router = Router()
        
        # Кэш в памяти
        self.msg_map = {} 
        self.last_header_user_id = None
        self.last_header_time = {} 
        self.connected_users = []
        
        self.refresh_config(config_data)
        self.sync_queue = asyncio.Queue()
        self.is_running = True

    def refresh_config(self, data):
        conf = data.get('config') or data
        self.buttons = conf.get('buttons', [])
        self.triggers = conf.get('triggers', [])
        self.welcome_message = conf.get('welcomeMessage', 'Привет!')
        incoming_users = conf.get('connectedUsers', [])
        
        # Умный мерж пользователей (чтобы не затирать last_topic_id)
        local_map = {str(u['id']): u for u in self.connected_users}
        for iu in incoming_users:
            uid = str(iu['id'])
            if uid in local_map:
                local_map[uid].update({
                    'is_banned': iu.get('is_banned', local_map[uid].get('is_banned')),
                    'warns': iu.get('warns', local_map[uid].get('warns')),
                    'is_active': iu.get('is_active', local_map[uid].get('is_active', True)),
                    'last_topic_id': iu.get('last_topic_id', local_map[uid].get('last_topic_id'))
                })
            else:
                local_map[uid] = iu
        self.connected_users = list(local_map.values())

        self.settings = conf.get('settings', {})
        self.use_topics = self.settings.get('useTopics', False)
        self.topic_per_request = self.settings.get('topicPerRequest', False)
        self.anonymous_topics = self.settings.get('anonymousTopics', False)
        self.admin_template = self.settings.get('adminMessageTemplate', "")
        self.auto_ban_threshold = self.settings.get('autoBanThreshold', 0)
        self.stats = conf.get('stats', {})

    async def db_sync_worker(self):
        """Фоновый воркер для связи с Supabase."""
        async with httpx.AsyncClient() as client:
            headers = {"apikey": self.sb_key, "Authorization": f"Bearer {self.sb_key}", "Content-Type": "application/json"}
            while self.is_running:
                task = await self.sync_queue.get()
                action, data = task
                try:
                    if action == "msg":
                        # Запись сообщения для вкладки 'Диалоги'
                        await client.post(f"{self.sb_url.rstrip('/')}/rest/v1/bot_messages", json=data, headers=headers)
                    elif action == "bot_config":
                        # Синхронизация настроек и списка юзеров
                        payload = {"config": {**self.config.get("config", {}), "connectedUsers": self.connected_users, "stats": self.stats}}
                        await client.patch(f"{self.sb_url.rstrip('/')}/rest/v1/bots?id=eq.{self.bot_id}", json=payload, headers=headers)
                except Exception as e:
                    logger.error(f"Sync Error: {e}")
                finally:
                    self.sync_queue.task_done()

    async def get_or_create_user(self, m: Message):
        user_id = m.from_user.id
        user = next((u for u in self.connected_users if str(u['id']) == str(user_id)), None)
        if not user:
            user = {
                "id": user_id, 
                "first_name": m.from_user.first_name, 
                "username": m.from_user.username, 
                "is_banned": False, 
                "is_active": True, 
                "warns": 0, 
                "joined_at": int(time.time()), 
                "last_topic_id": None
            }
            self.connected_users.append(user)
            await self.sync_queue.put(("bot_config", {}))
        return user

    async def create_new_topic(self, user, suffix=""):
        if not self.admin_id: return None
        try:
            name = f"User #{get_anon_id(user['id'])}" if self.anonymous_topics else f"{user['first_name']} [{user['id']}]"
            if suffix: name = f"{suffix} | {name}"
            topic = await self.bot.create_forum_topic(self.admin_id, name)
            user['last_topic_id'] = topic.message_thread_id
            await self.sync_queue.put(("bot_config", {}))
            return topic.message_thread_id
        except Exception as e:
            logger.error(f"Forum Error: {e}")
            return None

    async def ensure_active_topic(self, user):
        if not self.admin_id or not self.use_topics: return None
        if user.get("last_topic_id"): return user["last_topic_id"]
        return await self.create_new_topic(user)

    async def register_handlers(self):
        @self.router.message(CommandStart())
        async def cmd_start(m: Message):
            user = await self.get_or_create_user(m)
            if user.get("is_banned"): return
            await m.answer(self.welcome_message, reply_markup=self.get_main_kb())

        @self.router.message(Command("warn", "unwarn", "ban", "unban"))
        async def admin_moderation(m: Message):
            if not self.admin_id or m.chat.id != self.admin_id: return
            target_user = None
            
            # 1. Поиск по топику
            if m.message_thread_id:
                target_user = next((u for u in self.connected_users if str(u.get("last_topic_id")) == str(m.message_thread_id)), None)
            
            # 2. Поиск по реплаю
            if not target_user and m.reply_to_message:
                target_id = self.msg_map.get(m.reply_to_message.message_id)
                if target_id: target_user = next((u for u in self.connected_users if str(u["id"]) == str(target_id)), None)

            if not target_user: return await m.reply("❌ Пользователь не найден. Используйте команду в топике или ответом на сообщение.")
            
            cmd = m.text.split()[0].replace("/", "").lower()
            uid = target_user['id']
            if cmd == "warn":
                target_user['warns'] = target_user.get('warns', 0) + 1
                ban = self.auto_ban_threshold > 0 and target_user['warns'] >= self.auto_ban_threshold
                if ban: target_user['is_banned'] = True
                try: await self.bot.send_message(uid, f"⚠️ Вы получили предупреждение ({target_user['warns']})")
                except: pass
                await m.reply(f"✅ Варн выдан ({target_user['warns']})")
            elif cmd == "ban":
                target_user['is_banned'] = True
                try: await self.bot.send_message(uid, "🚫 Доступ ограничен.")
                except: pass
                await m.reply("✅ Забанен.")
            elif cmd == "unban":
                target_user['is_banned'] = False
                await m.reply("✅ Разбанен.")
            await self.sync_queue.put(("bot_config", {}))

        @self.router.message(F.chat.id == self.admin_id, F.reply_to_message)
        async def admin_reply(m: Message):
            target_id = self.msg_map.get(m.reply_to_message.message_id)
            
            # Поиск через топик или текст (ID: 123)
            if not target_id and m.message_thread_id:
                u = next((u for u in self.connected_users if str(u.get("last_topic_id")) == str(m.message_thread_id)), None)
                if u: target_id = u["id"]
            
            if not target_id:
                txt = (m.reply_to_message.text or "") + (m.reply_to_message.caption or "")
                match = re.search(r"ID:\s*(\d+)", txt)
                if match: target_id = int(match.group(1))

            if target_id:
                try:
                    sent = await self.bot.copy_message(target_id, m.chat.id, m.message_id)
                    self.msg_map[sent.message_id] = target_id 
                    # Логируем ответ админа в БД
                    await self.sync_queue.put(("msg", {
                        "bot_id": self.bot_id, "user_id": target_id, "first_name": "Admin",
                        "message_text": m.text or m.caption or "[Медиа]", "is_from_admin": True
                    }))
                except Exception as e:
                    await m.reply(f"❌ Ошибка: {e}")
            else:
                await m.reply("❌ Не удалось найти получателя.")

        @self.router.message()
        async def main_handler(m: Message):
            if self.admin_id and m.chat.id == self.admin_id: return
            user = await self.get_or_create_user(m)
            if user.get("is_banned"): return

            # 1. Запись сообщения в БД для панели Диалоги
            await self.sync_queue.put(("msg", {
                "bot_id": self.bot_id, "user_id": user['id'], "first_name": m.from_user.first_name,
                "message_text": m.text or m.caption or "[Медиа]", "is_from_admin": False
            }))

            # 2. Обработка кнопок
            if m.text:
                low = m.text.lower().strip()
                for btn in self.buttons:
                    if btn.get("text") and btn["text"].lower() == low:
                        # Если кнопка - заявка, ВСЕГДА шлем шапку (заявку)
                        if btn.get("type") == "request" and self.admin_id:
                            thread = await self.create_new_topic(user, suffix="ЗАЯВКА") if self.topic_per_request else await self.ensure_active_topic(user)
                            header = format_msg(btn.get("adminTemplate"), m, self.settings, is_anon=self.anonymous_topics, btn_text=btn['text'])
                            sent_req = await self.bot.send_message(self.admin_id, header, message_thread_id=thread)
                            self.msg_map[sent_req.message_id] = user['id']
                        
                        if btn.get("response"):
                            await m.answer(btn["response"])
                        return
                
                # 3. Триггеры
                for trig in self.triggers:
                    if trig.get("keyword") and trig["keyword"].lower() in low:
                        await m.answer(trig.get("response", "..."))
                        return

            # 4. Пересылка админу (с автоматической шапкой для новых диалогов)
            if self.admin_id:
                now = time.time()
                thread = await self.ensure_active_topic(user)
                
                # Логика шапки: если без топиков, шлем ее при первом контакте или раз в 10 мин
                should_send_header = False
                if not self.use_topics:
                    if self.last_header_user_id != user['id'] or (now - self.last_header_time.get(user['id'], 0) > 600):
                        should_send_header = True
                
                if should_send_header:
                    header_text = format_msg(self.admin_template, m, self.settings, is_anon=self.anonymous_topics)
                    sent_h = await self.bot.send_message(self.admin_id, header_text, message_thread_id=thread)
                    self.msg_map[sent_h.message_id] = user['id']
                    self.last_header_user_id = user['id']
                    self.last_header_time[user['id']] = now

                # Само сообщение (копия)
                sent_msg = await self.bot.copy_message(self.admin_id, m.chat.id, m.message_id, message_thread_id=thread)
                self.msg_map[sent_msg.message_id] = user['id']
                
                # Ограничение памяти
                if len(self.msg_map) > 5000:
                    self.msg_map.pop(next(iter(self.msg_map)))

    def get_main_kb(self):
        vbs = [b for b in self.buttons if b.get('text')]
        if not vbs: return None
        return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=b['text'])] for b in vbs], resize_keyboard=True)

    async def run(self):
        asyncio.create_task(self.db_sync_worker())
        await self.register_handlers()
        self.dp.include_router(self.router)
        await self.dp.start_polling(self.bot)

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    with open(sys.argv[1], 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    asyncio.run(BotInstance(cfg).run())
