
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

# Настройка логирования для вывода в консоль панели
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotCore")

def get_anon_id(user_id: int) -> str:
    """Генерирует короткий уникальный ID для анонимных пользователей."""
    return hashlib.md5(str(user_id).encode()).hexdigest()[:5].upper()

def format_msg(template: str, m: Message, settings: dict, is_anon: bool = False, btn_text: str = "") -> str:
    """Форматирует заголовок сообщения для администратора."""
    show_id = settings.get('showHeaderId', True)
    show_name = settings.get('showHeaderName', True)
    show_user = settings.get('showHeaderUsername', True)
    
    # Если все настройки отображения выключены - принудительно анонимный режим
    force_anon = not (show_id or show_name or show_user) or is_anon

    content_preview = m.text or m.caption or "[Медиа-файл]"
    if len(content_preview) > 80: content_preview = content_preview[:77] + "..."

    # 1. Если задан пользовательский шаблон
    if template and template.strip():
        res = template
        res = res.replace("{{id}}", str(m.from_user.id))
        if force_anon:
            res = res.replace("{{name}}", f"User #{get_anon_id(m.from_user.id)}")
            res = res.replace("{{username}}", "hidden")
        else:
            res = res.replace("{{name}}", m.from_user.full_name or "User")
            res = res.replace("{{username}}", f"@{m.from_user.username}" if m.from_user.username else "none")
        res = res.replace("{{button}}", btn_text)
        res = res.replace("{{text}}", content_preview)
        return res

    # 2. Стандартный системный заголовок
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
        
        # Очистка ID админа от лишних пробелов
        raw_admin_id = config_data.get('adminChatId')
        try:
            self.admin_id = int(str(raw_admin_id).strip()) if raw_admin_id else None
        except:
            self.admin_id = None
            logger.error(f"Неверный ID администратора: {raw_admin_id}")
        
        self.sb_url = os.getenv("SUPABASE_URL")
        self.sb_key = os.getenv("SUPABASE_KEY")
        
        self.bot = Bot(token=self.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher()
        self.router = Router()
        
        # Карта связей для реплаев (message_id -> user_id)
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
        
        # Синхронизация локального списка пользователей
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
        """Воркер для синхронизации данных с Supabase."""
        async with httpx.AsyncClient() as client:
            headers = {"apikey": self.sb_key, "Authorization": f"Bearer {self.sb_key}", "Content-Type": "application/json"}
            while self.is_running:
                task = await self.sync_queue.get()
                action, data = task
                try:
                    if action == "msg":
                        await client.post(f"{self.sb_url.rstrip('/')}/rest/v1/bot_messages", json=data, headers=headers)
                    elif action == "bot_config":
                        payload = {"config": {**self.config.get("config", {}), "connectedUsers": self.connected_users, "stats": self.stats}}
                        await client.patch(f"{self.sb_url.rstrip('/')}/rest/v1/bots?id=eq.{self.bot_id}", json=payload, headers=headers)
                except Exception as e:
                    logger.error(f"Ошибка БД: {e}")
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
            logger.error(f"Ошибка создания топика: {e}")
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
            
            # Поиск юзера по топику или по реплаю
            if m.message_thread_id:
                target_user = next((u for u in self.connected_users if str(u.get("last_topic_id")) == str(m.message_thread_id)), None)
            
            if not target_user and m.reply_to_message:
                target_id = self.msg_map.get(m.reply_to_message.message_id)
                if target_id: target_user = next((u for u in self.connected_users if str(u["id"]) == str(target_id)), None)

            if not target_user: return await m.reply("❌ Не удалось определить пользователя для действия.")
            
            cmd = m.text.split()[0].replace("/", "").lower()
            uid = target_user['id']
            if cmd == "warn":
                target_user['warns'] = target_user.get('warns', 0) + 1
                should_ban = self.auto_ban_threshold > 0 and target_user['warns'] >= self.auto_ban_threshold
                if should_ban: target_user['is_banned'] = True
                try: await self.bot.send_message(uid, f"⚠️ Вы получили предупреждение. Всего: {target_user['warns']}")
                except: pass
                await m.reply(f"✅ Предупреждение выдано. Всего: {target_user['warns']}" + (" (Юзер забанен автоматически)" if should_ban else ""))
            elif cmd == "ban":
                target_user['is_banned'] = True
                try: await self.bot.send_message(uid, "🚫 Доступ к боту ограничен администратором.")
                except: pass
                await m.reply("✅ Пользователь заблокирован.")
            elif cmd == "unban":
                target_user['is_banned'] = False
                await m.reply("✅ Пользователь разблокирован.")
            await self.sync_queue.put(("bot_config", {}))

        @self.router.message(F.chat.id == self.admin_id, F.reply_to_message)
        async def admin_reply(m: Message):
            target_id = self.msg_map.get(m.reply_to_message.message_id)
            
            # Если нет в карте, ищем по топику
            if not target_id and m.message_thread_id:
                u = next((u for u in self.connected_users if str(u.get("last_topic_id")) == str(m.message_thread_id)), None)
                if u: target_id = u["id"]
            
            # Крайний случай: поиск ID в тексте сообщения
            if not target_id:
                full_text = (m.reply_to_message.text or "") + (m.reply_to_message.caption or "")
                match = re.search(r"ID:\s*(\d+)", full_text)
                if match: target_id = int(match.group(1))

            if target_id:
                try:
                    sent = await self.bot.copy_message(target_id, m.chat.id, m.message_id)
                    self.msg_map[sent.message_id] = target_id 
                except Exception as e:
                    await m.reply(f"❌ Ошибка отправки пользователю: {e}")
            else:
                await m.reply("❌ Получатель не найден. Ответьте на сообщение с ID или в топике пользователя.")

        @self.router.message()
        async def main_handler(m: Message):
            # Игнорируем сообщения от самого админа, если это не реплаи (они выше)
            if self.admin_id and m.chat.id == self.admin_id: return
            
            user = await self.get_or_create_user(m)
            if user.get("is_banned"): return

            # Логика кнопок и триггеров
            if m.text:
                low = m.text.lower().strip()
                # 1. Проверка кнопок
                for btn in self.buttons:
                    if btn.get("text") and btn["text"].lower() == low:
                        if btn.get("type") == "request" and self.admin_id:
                            thread = await self.create_new_topic(user, suffix="ЗАЯВКА") if self.topic_per_request else await self.ensure_active_topic(user)
                            header = format_msg(btn.get("adminTemplate"), m, self.settings, is_anon=self.anonymous_topics, btn_text=btn['text'])
                            sent = await self.bot.send_message(self.admin_id, header, message_thread_id=thread)
                            self.msg_map[sent.message_id] = user['id']
                        await m.answer(btn.get("response", "Принято."))
                        return
                
                # 2. Проверка триггеров
                for trig in self.triggers:
                    if trig.get("keyword") and trig["keyword"].lower() in low:
                        await m.answer(trig.get("response", "..."))
                        return

            # Пересылка администратору
            if self.admin_id:
                now = time.time()
                thread = await self.ensure_active_topic(user)
                
                # Нужно ли слать заголовок (для режима без топиков)
                should_send_header = False
                if not self.use_topics:
                    # Присылаем шапку, если сменился юзер или прошло 10 минут
                    if self.last_header_user_id != user['id'] or (now - self.last_header_time.get(user['id'], 0) > 600):
                        should_send_header = True
                
                if should_send_header:
                    header = format_msg(self.admin_template, m, self.settings, is_anon=self.anonymous_topics)
                    sent_h = await self.bot.send_message(self.admin_id, header, message_thread_id=thread)
                    self.msg_map[sent_h.message_id] = user['id']
                    self.last_header_user_id = user['id']
                    self.last_header_time[user['id']] = now

                # Копируем сообщение админу (сохраняя медиа, стикеры и т.д.)
                try:
                    sent_m = await self.bot.copy_message(self.admin_id, m.chat.id, m.message_id, message_thread_id=thread)
                    self.msg_map[sent_m.message_id] = user['id']
                except Exception as e:
                    logger.error(f"Ошибка пересылки админу: {e}")
                
                # Очистка памяти msg_map
                if len(self.msg_map) > 5000:
                    first_key = next(iter(self.msg_map))
                    del self.msg_map[first_key]

    def get_main_kb(self):
        vbs = [b for b in self.buttons if b.get('text')]
        if not vbs: return None
        return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=b['text'])] for b in vbs], resize_keyboard=True)

    async def run(self):
        logger.info(f"Запуск инстанса бота {self.bot_id}...")
        asyncio.create_task(self.db_sync_worker())
        await self.register_handlers()
        self.dp.include_router(self.router)
        try:
            await self.dp.start_polling(self.bot)
        except Exception as e:
            logger.error(f"Критическая ошибка polling: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    try:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        asyncio.run(BotInstance(cfg).run())
    except Exception as e:
        logger.critical(f"Ошибка при старте ядра: {e}")
