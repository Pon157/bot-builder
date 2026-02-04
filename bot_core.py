
import asyncio
import logging
import json
import re
import httpx
import os
import sys
import hashlib
from datetime import datetime
from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ContentType
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotCore")

def format_msg(template: str, m: Message, btn_text: str = "", extra_text: str = "") -> str:
    if not template: 
        return f"📩 <b>Сообщение от {m.from_user.full_name}</b>\nID: <code>{m.from_user.id}</code>"
    res = template.replace("{{id}}", str(m.from_user.id))
    res = res.replace("{{name}}", m.from_user.full_name or "User")
    res = res.replace("{{username}}", f"@{m.from_user.username}" if m.from_user.username else "none")
    res = res.replace("{{button}}", btn_text)
    res = res.replace("{{text}}", extra_text or m.text or "[Медиа]")
    return res

class BotInstance:
    def __init__(self, config_data):
        self.config = config_data
        self.token = config_data.get('token')
        self.bot_id = config_data.get('id')
        self.owner_id = config_data.get('owner_id')
        
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
        
        self.refresh_config(config_data)
        self.sync_queue = asyncio.Queue()
        self.is_running = True

    def refresh_config(self, data):
        conf = data.get('config') or data
        self.buttons = conf.get('buttons', [])
        self.triggers = conf.get('triggers', [])
        self.welcome_message = conf.get('welcomeMessage', 'Привет!')
        
        # Умное обновление списка пользователей
        new_users = conf.get('connectedUsers', [])
        if not hasattr(self, 'connected_users'):
            self.connected_users = new_users
        else:
            # Обновляем только тех, кто изменился в БД (варны, баны), но сохраняем thread_id из памяти
            for nu in new_users:
                found = False
                for ou in self.connected_users:
                    if ou['id'] == nu['id']:
                        ou['is_banned'] = nu.get('is_banned', False)
                        ou['warns'] = nu.get('warns', 0)
                        # Не затираем last_topic_id если он есть в памяти
                        found = True
                        break
                if not found:
                    self.connected_users.append(nu)

        self.subscribers = conf.get('subscribers', [])
        self.settings = conf.get('settings', {})
        
        new_stats = conf.get('stats', {})
        if not hasattr(self, 'stats'):
            self.stats = {"totalMessages": 0, "incomingToday": 0, "outgoingToday": 0, "bannedCount": 0, "history": [], "activeUsers24h": 0}
        
        if new_stats.get('totalMessages', 0) > self.stats.get('totalMessages', 0):
            self.stats = new_stats

        self.auto_ban_threshold = self.settings.get('autoBanThreshold', 0)
        self.use_topics = self.settings.get('useTopics', False)
        self.topic_per_request = self.settings.get('topicPerRequest', False)
        self.anonymous_topics = self.settings.get('anonymousTopics', False)
        self.admin_template = self.settings.get('adminMessageTemplate', "")

    async def stats_history_manager(self):
        while self.is_running:
            today = datetime.now().strftime("%d.%m")
            history = self.stats.get("history", [])
            found = False
            for point in history:
                if point.get("date") == today:
                    point["totalUsers"] = len(self.connected_users)
                    found = True
                    break
            if not found:
                history.append({"date": today, "incoming": 0, "outgoing": 0, "totalUsers": len(self.connected_users), "activeUsers": 0})
                if len(history) > 14: history.pop(0)
                self.stats["history"] = history
            await self.sync_queue.put(("bot_config", {}))
            await asyncio.sleep(30)

    async def remote_sync_task(self):
        async with httpx.AsyncClient() as client:
            headers = {"apikey": self.sb_key, "Authorization": f"Bearer {self.sb_key}"}
            while self.is_running:
                await asyncio.sleep(10) 
                try:
                    res = await client.get(f"{self.sb_url.rstrip('/')}/rest/v1/bots?id=eq.{self.bot_id}", headers=headers)
                    if res.status_code == 200 and res.json():
                        self.refresh_config(res.json()[0])
                except Exception as e:
                    logger.error(f"Sync error: {e}")

    async def db_sync_worker(self):
        async with httpx.AsyncClient() as client:
            headers = {"apikey": self.sb_key, "Authorization": f"Bearer {self.sb_key}", "Content-Type": "application/json"}
            while self.is_running:
                task = await self.sync_queue.get()
                action, data = task
                try:
                    if action == "msg":
                        await client.post(f"{self.sb_url.rstrip('/')}/rest/v1/bot_messages", json=data, headers=headers)
                    elif action == "bot_config":
                        payload = {
                            "config": {
                                **self.config.get("config", {}),
                                "connectedUsers": self.connected_users,
                                "subscribers": self.subscribers,
                                "stats": self.stats,
                                "settings": self.settings,
                                "welcomeMessage": self.welcome_message,
                                "buttons": self.buttons,
                                "triggers": self.triggers
                            }
                        }
                        await client.patch(f"{self.sb_url.rstrip('/')}/rest/v1/bots?id=eq.{self.bot_id}", json=payload, headers=headers)
                except Exception as e:
                    logger.error(f"DB Worker error: {e}")
                finally:
                    self.sync_queue.task_done()

    async def update_stats(self, direction: str):
        self.stats["totalMessages"] = self.stats.get("totalMessages", 0) + 1
        key = "incomingToday" if direction == "incoming" else "outgoingToday"
        self.stats[key] = self.stats.get(key, 0) + 1
        today = datetime.now().strftime("%d.%m")
        for point in self.stats.get("history", []):
            if point.get("date") == today:
                point[direction] = point.get(direction, 0) + 1
                point["totalUsers"] = len(self.connected_users)
        # Пуш будет в stats_history_manager

    async def log_message(self, user_id, name, text, is_admin=False):
        payload = {
            "bot_id": self.bot_id, "user_id": user_id, "first_name": name,
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
                "id": user_id, "first_name": m.from_user.first_name, "username": m.from_user.username,
                "is_banned": False, "is_active": True, "warns": 0, 
                "joined_at": int(datetime.now().timestamp()), "last_topic_id": None
            }
            self.connected_users.append(user_obj)
            if user_id not in self.subscribers: self.subscribers.append(user_id)
        return user_obj

    async def create_new_topic(self, user, suffix=""):
        if not self.admin_id: return None
        try:
            name = f"User #{hashlib.md5(str(user['id']).encode()).hexdigest()[:4].upper()}" if self.anonymous_topics else f"{user['first_name']} [{user['id']}]"
            if suffix: name = f"{suffix} | {name}"
            topic = await self.bot.create_forum_topic(self.admin_id, name)
            # Обновляем последний активный топик для юзера
            user['last_topic_id'] = topic.message_thread_id
            await self.sync_queue.put(("bot_config", {}))
            return topic.message_thread_id
        except Exception as e:
            logger.error(f"Topic Error: {e}")
            return None

    async def ensure_active_topic(self, user):
        """Возвращает текущий активный топик или создает новый общий."""
        if not self.admin_id or not self.use_topics: return None
        if user.get("last_topic_id"): return user["last_topic_id"]
        return await self.create_new_topic(user)

    async def register_handlers(self):
        @self.router.message(CommandStart())
        async def cmd_start(m: Message):
            user = await self.get_or_create_user(m)
            if user.get("is_banned"): return
            await m.answer(format_msg(self.welcome_message, m), reply_markup=self.get_main_kb())
            await self.log_message(m.from_user.id, m.from_user.full_name, "/start")

        @self.router.message(Command("warn", "unwarn", "ban", "unban"))
        async def admin_moderation(m: Message):
            if not self.admin_id or m.chat.id != self.admin_id: return
            target_user = None
            if m.message_thread_id:
                # Ищем юзера, у которого ЭТОТ топик был последним активным
                target_user = next((u for u in self.connected_users if u.get("last_topic_id") == m.message_thread_id), None)
            
            if not target_user and m.reply_to_message:
                match = re.search(r"ID: (\d+)", m.reply_to_message.text or m.reply_to_message.caption or "")
                if match: target_user = next((u for u in self.connected_users if u["id"] == int(match.group(1))), None)

            if not target_user: return await m.reply("❌ Юзер не найден в этом топике.")
            
            cmd = m.text.split()[0].replace("/", "").lower()
            uid = target_user['id']
            if cmd == "warn":
                target_user['warns'] = target_user.get('warns', 0) + 1
                ban = self.auto_ban_threshold > 0 and target_user['warns'] >= self.auto_ban_threshold
                target_user['is_banned'] = ban
                try: await self.bot.send_message(uid, f"⚠️ <b>Вам выдано предупреждение!</b>\nВсего: {target_user['warns']}/{self.auto_ban_threshold or '∞'}")
                except: pass
                await m.reply(f"✅ Варн выдан. Текущее кол-во: {target_user['warns']}")
            elif cmd == "unwarn":
                target_user['warns'] = max(0, target_user.get('warns', 0) - 1)
                await m.reply(f"✅ Варн снят. Осталось: {target_user['warns']}")
            elif cmd == "ban":
                target_user['is_banned'] = True
                try: await self.bot.send_message(uid, "🚫 Вы заблокированы администратором.")
                except: pass
                await m.reply("✅ Забанен.")
            elif cmd == "unban":
                target_user['is_banned'] = False
                try: await self.bot.send_message(uid, "✅ Разблокированы.")
                except: pass
                await m.reply("✅ Разбанен.")
            await self.sync_queue.put(("bot_config", {}))

        @self.router.message(F.chat.id == self.admin_id, F.reply_to_message)
        async def admin_reply(m: Message):
            if m.is_topic_message and not m.reply_to_message: return
            tid = m.message_thread_id
            target_id = None
            # Ищем юзера по топику
            u = next((u for u in self.connected_users if u.get("last_topic_id") == tid), None)
            if u: target_id = u["id"]
            if not target_id:
                match = re.search(r"ID: (\d+)", m.reply_to_message.text or m.reply_to_message.caption or "")
                if match: target_id = int(match.group(1))
            
            if target_id:
                try:
                    await self.bot.copy_message(target_id, m.chat.id, m.message_id)
                    await self.log_message(target_id, "Админ", m.text or "[Медиа]", is_admin=True)
                except Exception as e: await m.reply(f"❌ Ошибка: {e}")

        @self.router.message()
        async def main_handler(m: Message):
            if self.admin_id and m.chat.id == self.admin_id: return
            user = await self.get_or_create_user(m)
            if user.get("is_banned"): return

            # Обработка кнопок
            if m.text:
                low = m.text.lower().strip()
                for btn in self.buttons:
                    if btn.get("text") and btn["text"].lower() == low:
                        if btn.get("type") == "request" and self.admin_id:
                            # ПРИНУДИТЕЛЬНО создаем НОВЫЙ топик для каждой заявки
                            t_id = await self.create_new_topic(user, suffix=f"ЗАЯВКА: {btn['text']}")
                            await self.bot.send_message(self.admin_id, format_msg(btn.get("adminTemplate", self.admin_template), m, btn['text']), message_thread_id=t_id)
                        
                        await m.answer(btn.get("response", "Принято."), reply_markup=self.get_main_kb())
                        await self.log_message(m.from_user.id, m.from_user.full_name, f"Кнопка: {btn['text']}")
                        return
                for t in self.triggers:
                    if t.get("keyword") and t["keyword"].lower() in low:
                        await m.answer(t["response"])
                        await self.log_message(m.from_user.id, m.from_user.full_name, f"Триггер: {t['keyword']}")
                        return

            # Обычное сообщение -> в последний активный топик
            if self.admin_id:
                thread = await self.ensure_active_topic(user)
                header = format_msg(self.admin_template, m)
                await self.bot.send_message(self.admin_id, header, message_thread_id=thread)
                await self.bot.copy_message(self.admin_id, m.chat.id, m.message_id, message_thread_id=thread)
                await self.log_message(m.from_user.id, m.from_user.full_name, m.text or "[Медиа]")

    async def run(self):
        asyncio.create_task(self.db_sync_worker())
        asyncio.create_task(self.remote_sync_task())
        asyncio.create_task(self.stats_history_manager())
        await self.register_handlers()
        self.dp.include_router(self.router)
        await self.dp.start_polling(self.bot)

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    try:
        with open(sys.argv[1], 'r', encoding='utf-8') as f: cfg = json.load(f)
        asyncio.run(BotInstance(cfg).run())
    except Exception as e: logger.error(f"FATAL: {e}")
