
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

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotCore")

def format_msg(template: str, m: Message, btn_text: str = "", extra_text: str = "") -> str:
    """Форматирует текст уведомления для админа на основе шаблона."""
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
        
        # Обработка ID админ-чата (может быть отрицательным для групп)
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
        
        # Инициализация состояния
        self.refresh_config(config_data)
        self.sync_queue = asyncio.Queue()
        self.is_running = True

    def refresh_config(self, data):
        """Обновляет локальные переменные из переданного конфига."""
        conf = data.get('config') or data
        self.buttons = conf.get('buttons', [])
        self.triggers = conf.get('triggers', [])
        self.welcome_message = conf.get('welcomeMessage', 'Привет!')
        self.connected_users = conf.get('connectedUsers', [])
        self.subscribers = conf.get('subscribers', [])
        self.settings = conf.get('settings', {})
        self.stats = conf.get('stats', {
            "totalMessages": 0, "incomingToday": 0, "outgoingToday": 0, 
            "bannedCount": 0, "history": [], "activeUsers24h": 0
        })
        self.auto_ban_threshold = self.settings.get('autoBanThreshold', 0)
        self.use_topics = self.settings.get('useTopics', False)
        self.topic_per_request = self.settings.get('topicPerRequest', False)
        self.anonymous_topics = self.settings.get('anonymousTopics', False)
        self.admin_template = self.settings.get('adminMessageTemplate', "")

    async def stats_history_manager(self):
        """Задача для поддержания актуальности точек на графике."""
        while self.is_running:
            today = datetime.now().strftime("%d.%m")
            history = self.stats.get("history", [])
            
            # Проверяем, есть ли запись за сегодня
            found = False
            for point in history:
                if point.get("date") == today:
                    point["totalUsers"] = len(self.connected_users)
                    found = True
                    break
            
            if not found:
                new_point = {
                    "date": today,
                    "incoming": 0,
                    "outgoing": 0,
                    "totalUsers": len(self.connected_users),
                    "activeUsers": 0
                }
                history.append(new_point)
                if len(history) > 14: history.pop(0)
                self.stats["history"] = history
                logger.info(f"[*] New stats point created for {today}")
                await self.sync_queue.put(("bot_config", {}))
            
            await asyncio.sleep(3600) # Проверка раз в час

    async def remote_sync_task(self):
        """Периодически тянет баны/варны из БД Супабейз."""
        async with httpx.AsyncClient() as client:
            headers = {"apikey": self.sb_key, "Authorization": f"Bearer {self.sb_key}"}
            while self.is_running:
                await asyncio.sleep(15) 
                try:
                    res = await client.get(f"{self.sb_url.rstrip('/')}/rest/v1/bots?id=eq.{self.bot_id}", headers=headers)
                    if res.status_code == 200 and res.json():
                        remote_data = res.json()[0]
                        remote_conf = remote_data.get('config') or {}
                        remote_users = remote_conf.get('connectedUsers', [])
                        
                        # Обновляем только критические данные, чтобы не ломать thread_id
                        for ru in remote_users:
                            local_u = next((u for u in self.connected_users if u['id'] == ru['id']), None)
                            if local_u:
                                local_u['is_banned'] = ru.get('is_banned', False)
                                local_u['warns'] = ru.get('warns', 0)
                            else:
                                self.connected_users.append(ru)
                        
                        self.settings = remote_conf.get('settings', self.settings)
                        self.topic_per_request = self.settings.get('topicPerRequest', False)
                        self.anonymous_topics = self.settings.get('anonymousTopics', False)
                        # logger.info("Remote sync: OK")
                except Exception as e:
                    logger.error(f"Remote sync error: {e}")

    async def db_sync_worker(self):
        """Отправляет изменения в БД из очереди (сообщения и конфиг)."""
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
                    logger.error(f"DB Worker Error: {e}")
                finally:
                    self.sync_queue.task_done()

    async def update_stats(self, direction: str):
        """Инкрементирует счетчики статистики."""
        self.stats["totalMessages"] = self.stats.get("totalMessages", 0) + 1
        key = "incomingToday" if direction == "incoming" else "outgoingToday"
        self.stats[key] = self.stats.get(key, 0) + 1
        
        today = datetime.now().strftime("%d.%m")
        history = self.stats.get("history", [])
        if history and history[-1]["date"] == today:
            history[-1][direction] = history[-1].get(direction, 0) + 1
            history[-1]["totalUsers"] = len(self.connected_users)
        
        await self.sync_queue.put(("bot_config", {}))

    async def log_message(self, user_id, name, text, is_admin=False):
        """Логирует сообщение в базу данных."""
        payload = {
            "bot_id": self.bot_id, "user_id": user_id, "first_name": name,
            "message_text": (text[:950] + "...") if text and len(text) > 950 else (text or "[Медиа]"),
            "is_from_admin": is_admin
        }
        await self.sync_queue.put(("msg", payload))
        await self.update_stats("incoming" if not is_admin else "outgoing")

    async def get_or_create_user(self, m: Message):
        """Находит юзера в списке или создает нового."""
        user_id = m.from_user.id
        user_obj = next((u for u in self.connected_users if u['id'] == user_id), None)
        if not user_obj:
            user_obj = {
                "id": user_id, "first_name": m.from_user.first_name, "username": m.from_user.username,
                "is_banned": False, "is_active": True, "warns": 0, 
                "joined_at": int(datetime.now().timestamp()), "thread_id": None
            }
            self.connected_users.append(user_obj)
            if user_id not in self.subscribers: self.subscribers.append(user_id)
            await self.sync_queue.put(("bot_config", {}))
        return user_obj

    async def create_new_topic(self, user, suffix=""):
        """Принудительно создает новый топик в супергруппе."""
        if not self.admin_id: return None
        try:
            if self.anonymous_topics:
                sys_id = hashlib.md5(str(user['id']).encode()).hexdigest()[:4].upper()
                name = f"User #{sys_id}"
            else:
                name = f"{user['first_name']} [{user['id']}]"
            
            if suffix: name = f"{suffix} | {name}"
            
            topic = await self.bot.create_forum_topic(self.admin_id, name)
            return topic.message_thread_id
        except Exception as e:
            logger.error(f"Topic creation failed: {e}")
            return None

    async def ensure_thread(self, user):
        """Обеспечивает наличие топика для юзера (если включены топики)."""
        if not self.admin_id or not self.use_topics: return None
        if user.get("thread_id"): return user["thread_id"]
        
        tid = await self.create_new_topic(user)
        if tid:
            user["thread_id"] = tid
            await self.sync_queue.put(("bot_config", {}))
        return tid

    def get_main_kb(self):
        """Генерирует Reply-клавиатуру из кнопок конфига."""
        vbs = [b for b in self.buttons if b.get('text')]
        if not vbs: return None
        rows = []
        for i in range(0, len(vbs), 2):
            rows.append([KeyboardButton(text=b['text']) for b in vbs[i:i+2]])
        return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

    async def register_handlers(self):
        @self.router.message(CommandStart())
        async def cmd_start(m: Message):
            user = await self.get_or_create_user(m)
            if user.get("is_banned"): return
            await m.answer(format_msg(self.welcome_message, m), reply_markup=self.get_main_kb())
            await self.log_message(m.from_user.id, m.from_user.full_name, "/start")

        @self.router.message(Command("warn", "unwarn", "ban", "unban"))
        async def admin_moderation(m: Message):
            """Команды модерации от админа."""
            if not self.admin_id or m.chat.id != self.admin_id: return
            target_user = None
            
            # Поиск юзера по топику или по реплаю
            if m.message_thread_id:
                target_user = next((u for u in self.connected_users if u.get("thread_id") == m.message_thread_id), None)
            if not target_user and m.reply_to_message:
                match = re.search(r"ID: (\d+)", m.reply_to_message.text or m.reply_to_message.caption or "")
                if match: target_user = next((u for u in self.connected_users if u["id"] == int(match.group(1))), None)

            if not target_user: 
                return await m.reply("❌ Юзер не найден. Подождите синхронизации или ответьте на его сообщение.")
            
            cmd = m.text.split()[0].replace("/", "").lower()
            uid = target_user['id']
            
            if cmd == "warn":
                target_user['warns'] = target_user.get('warns', 0) + 1
                ban = self.auto_ban_threshold > 0 and target_user['warns'] >= self.auto_ban_threshold
                target_user['is_banned'] = ban
                try: await self.bot.send_message(uid, f"⚠️ Предупреждение ({target_user['warns']}/{self.auto_ban_threshold})" + ("\n🚫 Бан." if ban else ""))
                except: pass
                await m.reply(f"✅ Варн выдан. Всего: {target_user['warns']}")
            elif cmd == "unwarn":
                target_user['warns'] = max(0, target_user.get('warns', 0) - 1)
                await m.reply(f"✅ Варн снят. Осталось: {target_user['warns']}")
            elif cmd == "ban":
                target_user['is_banned'] = True
                try: await self.bot.send_message(uid, "🚫 Вы заблокированы.")
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
            """Ответ админа пользователю."""
            if m.is_topic_message and not m.reply_to_message: return
            
            tid = m.message_thread_id
            target_id = None
            
            # Сначала пробуем найти по топику
            u = next((u for u in self.connected_users if u.get("thread_id") == tid), None)
            if u: target_id = u["id"]
            
            # Если не вышло (например, топик временный), ищем ID в тексте сообщения, на которое ответили
            if not target_id:
                txt = m.reply_to_message.text or m.reply_to_message.caption or ""
                match = re.search(r"ID: (\d+)", txt)
                if match: target_id = int(match.group(1))
            
            if target_id:
                try:
                    await self.bot.copy_message(target_id, m.chat.id, m.message_id)
                    await self.log_message(target_id, "Админ", m.text or "[Медиа]", is_admin=True)
                except Exception as e: 
                    await m.reply(f"❌ Не удалось отправить ответ: {e}")

        @self.router.message()
        async def main_handler(m: Message):
            """Главный обработчик входящих от пользователей."""
            if self.admin_id and m.chat.id == self.admin_id: return
            user = await self.get_or_create_user(m)
            if user.get("is_banned"): return

            # Обработка кнопок и триггеров
            if m.text:
                low = m.text.lower().strip()
                for btn in self.buttons:
                    if btn.get("text") and btn["text"].lower() == low:
                        # Логика заявки/запроса
                        if btn.get("type") == "request" and self.admin_id:
                            # Если стоит галка "топик на каждый запрос"
                            if self.topic_per_request:
                                thread_id = await self.create_new_topic(user, suffix=f"ЗАЯВКА: {btn['text']}")
                            else:
                                thread_id = await self.ensure_thread(user)
                            
                            info = format_msg(btn.get("adminTemplate", self.admin_template), m, btn['text'])
                            await self.bot.send_message(self.admin_id, info, message_thread_id=thread_id)
                        
                        await m.answer(btn.get("response", "Запрос отправлен."), reply_markup=self.get_main_kb())
                        await self.log_message(m.from_user.id, m.from_user.full_name, f"Кнопка: {btn['text']}")
                        return
                
                # Триггеры (ключевые слова)
                for t in self.triggers:
                    if t.get("keyword") and t["keyword"].lower() in low:
                        await m.answer(t["response"])
                        await self.log_message(m.from_user.id, m.from_user.full_name, f"Триггер: {t['keyword']}")
                        return

            # Пересылка админу (обычное сообщение)
            if self.admin_id:
                thread = await self.ensure_thread(user)
                header = format_msg(self.admin_template, m)
                await self.bot.send_message(self.admin_id, header, message_thread_id=thread)
                await self.bot.copy_message(self.admin_id, m.chat.id, m.message_id, message_thread_id=thread)
                await self.log_message(m.from_user.id, m.from_user.full_name, m.text or "[Медиа]")

    async def run(self):
        """Запуск инстанса."""
        asyncio.create_task(self.db_sync_worker())
        asyncio.create_task(self.remote_sync_task())
        asyncio.create_task(self.stats_history_manager())
        await self.register_handlers()
        self.dp.include_router(self.router)
        logger.info(f"[*] Бот @{(await self.bot.get_me()).username} запущен.")
        await self.dp.start_polling(self.bot)

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    try:
        with open(sys.argv[1], 'r', encoding='utf-8') as f: cfg = json.load(f)
        asyncio.run(BotInstance(cfg).run())
    except Exception as e: 
        logger.error(f"FATAL ERROR: {e}")
