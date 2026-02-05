
import asyncio
import logging
import json
import re
import httpx
import os
import sys
import hashlib
import time
import signal
from datetime import datetime
from typing import Dict, Optional, List, Any, Union

from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode, ContentType
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
    InputFile, BufferedInputFile
)
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter

# --- Настройка логирования ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotCore")

def get_anon_id(user_id: int) -> str:
    """Генерация короткого хеша для анонимных обращений."""
    return hashlib.md5(str(user_id).encode()).hexdigest()[:6].upper()

def format_admin_header(template: str, m: Message, settings: dict, is_first: bool = False, btn_text: str = "") -> str:
    """Форматирование заголовка сообщения для администратора."""
    is_anon = settings.get('anonymousTopics', False)
    anon_id = get_anon_id(m.from_user.id)
    
    # Если есть кастомный шаблон (обычно для первого сообщения)
    if (is_first or btn_text) and template:
        res = template
        if is_anon:
            res = res.replace("{{id}}", f"#{anon_id}").replace("{{name}}", "Аноним").replace("{{username}}", "@hidden")
        else:
            res = res.replace("{{id}}", str(m.from_user.id))
            res = res.replace("{{name}}", m.from_user.full_name or "User")
            res = res.replace("{{username}}", f"@{m.from_user.username}" if m.from_user.username else "none")
            
        res = res.replace("{{button}}", btn_text or "—").replace("{{text}}", m.text or m.caption or "[Медиа]")
        prefix = "🆕 <b>НОВОЕ ОБРАЩЕНИЕ</b>" if not btn_text else f"📩 <b>ЗАЯВКА: {btn_text}</b>"
        return f"{prefix}\n\n{res}\n\n"

    # Стандартный заголовок
    parts = []
    if is_anon:
        parts.append(f"👤 <b>Аноним #{anon_id}</b>")
    else:
        if settings.get('showHeaderName', True): parts.append(f"<b>{m.from_user.full_name}</b>")
        if settings.get('showHeaderUsername', True) and m.from_user.username: parts.append(f"(@{m.from_user.username})")
        if settings.get('showHeaderId', True): parts.append(f"ID: <code>{m.from_user.id}</code>")
    
    if not parts: parts.append(f"👤 User <code>#{anon_id}</code>")
    return f"📩 {' | '.join(parts)}\n\n"

class BotInstance:
    def __init__(self, config_data: dict):
        self.bot_id = config_data.get('id')
        self.token = config_data.get('token')
        self.sb_url = os.getenv("SUPABASE_URL", "").rstrip('/')
        self.sb_key = os.getenv("SUPABASE_KEY", "")
        
        # Инициализация бота
        self.bot = Bot(token=self.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher()
        self.router = Router()
        
        self.last_header_time = {} # Для контроля частоты заголовков
        self.connected_users = []
        self.sync_queue = asyncio.Queue()
        self.is_running = True
        
        # Конфигурационные параметры
        self.admin_id = None
        self.use_topics = False
        self.topic_per_request = False
        self.settings = {}
        self.stats = {
            "totalMessages": 0, "incomingToday": 0, "outgoingToday": 0, "history": []
        }
        self.buttons = []
        self.triggers = []
        self.welcome_message = ""
        self.admin_template = ""
        self.auto_ban_threshold = 0

        self.refresh_config(config_data, initial=True)

    def refresh_config(self, data: dict, initial: bool = False):
        """Обновление локальных параметров из входящего конфига (БД или файл)."""
        inner_config = data.get('config', {}) if isinstance(data.get('config'), dict) else {}
        flat_data = {**inner_config, **data}
        
        try:
            raw_admin = flat_data.get('adminChatId')
            if raw_admin: self.admin_id = int(str(raw_admin).strip())
        except: pass

        self.buttons = flat_data.get('buttons', [])
        self.triggers = flat_data.get('triggers', [])
        self.welcome_message = flat_data.get('welcomeMessage', 'Привет!')
        self.settings = flat_data.get('settings', {})
        self.use_topics = self.settings.get('useTopics', False)
        self.topic_per_request = self.settings.get('topicPerRequest', False)
        self.admin_template = self.settings.get('adminMessageTemplate', "")
        self.auto_ban_threshold = int(self.settings.get('autoBanThreshold', 0))

        # Умное слияние пользователей (чтобы не затереть новые данные в памяти старыми из БД)
        new_users_list = flat_data.get('connectedUsers', [])
        if initial:
            self.connected_users = new_users_list
        else:
            local_map = {u['id']: u for u in self.connected_users}
            for remote_u in new_users_list:
                uid = remote_u['id']
                if uid in local_map:
                    # Сервер/Панель имеет приоритет по статусам (бан/лив)
                    local_map[uid]['is_active'] = remote_u.get('is_active', True)
                    local_map[uid]['is_banned'] = remote_u.get('is_banned', False)
                    local_map[uid]['warns'] = remote_u.get('warns', 0)
                else:
                    self.connected_users.append(remote_u)

        # Синхронизация статистики
        incoming_stats = flat_data.get('stats')
        if incoming_stats and isinstance(incoming_stats, dict):
            self.stats["totalMessages"] = max(self.stats.get("totalMessages", 0), int(incoming_stats.get("totalMessages", 0)))
            self.stats["incomingToday"] = int(incoming_stats.get("incomingToday", 0))
            self.stats["outgoingToday"] = int(incoming_stats.get("outgoingToday", 0))
            if incoming_stats.get("history"):
                self.stats["history"] = incoming_stats["history"]
        
        if not self.stats.get("history"): self.stats["history"] = []

    async def mark_user_inactive(self, user_id: int):
        """Помечает юзера как заблокировавшего бота (Лив)."""
        for u in self.connected_users:
            if u['id'] == user_id:
                if u.get('is_active', True):
                    u['is_active'] = False
                    logger.info(f"User {user_id} detected as INACTIVE")
                    await self.sync_queue.put(("config", {}))
                break

    async def update_counters(self, direction: str):
        """Обновление статистики сообщений и истории для графиков."""
        self.stats["totalMessages"] += 1
        key = "incomingToday" if direction == "incoming" else "outgoingToday"
        self.stats[key] += 1
        
        today = datetime.now().strftime("%d.%m")
        # Живые: активны (не удалили бота) И не забанены нами
        active_count = len([u for u in self.connected_users if u.get('is_active', True) and not u.get('is_banned', False)])
        total_count = len(self.connected_users)
        
        history = self.stats.get("history", [])
        found = False
        for pt in history:
            if pt.get("date") == today:
                pt[direction] = pt.get(direction, 0) + 1
                pt["totalUsers"] = total_count
                pt["activeUsers"] = active_count
                found = True
                break
        
        if not found:
            history.append({
                "date": today, 
                "incoming": 1 if direction=="incoming" else 0, 
                "outgoing": 1 if direction=="outgoing" else 0, 
                "totalUsers": total_count,
                "activeUsers": active_count
            })
            if len(history) > 14: history.pop(0)
        
        self.stats["history"] = history
        await self.sync_queue.put(("config", {}))

    async def log_it(self, user_id, name, text, is_admin=False):
        """Сохранение сообщения в таблицу логов Supabase."""
        await self.sync_queue.put(("msg", {
            "bot_id": self.bot_id, "user_id": user_id, "first_name": name,
            "message_text": text[:900] if text else "[Медиа]",
            "is_from_admin": is_admin
        }))
        await self.update_counters("incoming" if not is_admin else "outgoing")

    # --- Воркеры синхронизации ---
    async def remote_sync_poller(self):
        """Периодический опрос БД для получения команд из панели управления."""
        async with httpx.AsyncClient() as client:
            headers = {"apikey": self.sb_key, "Authorization": f"Bearer {self.sb_key}"}
            while self.is_running:
                await asyncio.sleep(5) # Быстрый опрос для моментальной модерации
                try:
                    res = await client.get(f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}", headers=headers)
                    if res.status_code == 200 and res.json():
                        self.refresh_config(res.json()[0])
                except Exception as e:
                    logger.error(f"Sync error: {e}")

    async def db_sync_worker(self):
        """Пуш локальных изменений (сообщения, стата, новые юзеры) в БД."""
        async with httpx.AsyncClient() as client:
            headers = {"apikey": self.sb_key, "Authorization": f"Bearer {self.sb_key}", "Content-Type": "application/json"}
            while self.is_running:
                try:
                    action, data = await self.sync_queue.get()
                    if action == "msg":
                        await client.post(f"{self.sb_url}/rest/v1/bot_messages", json=data, headers=headers)
                    elif action == "config":
                        # Получаем актуальный конфиг перед патчем, чтобы не затереть изменения сервера
                        res = await client.get(f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}", headers=headers)
                        if res.status_code == 200 and res.json():
                            db_bot = res.json()[0]
                            db_config = db_bot.get("config", {})
                            new_config = {**db_config, "connectedUsers": self.connected_users, "stats": self.stats}
                            await client.patch(f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}", json={"config": new_config}, headers=headers)
                    self.sync_queue.task_done()
                except Exception as e:
                    logger.error(f"Worker sync error: {e}")
                    await asyncio.sleep(2)

    # --- Обработка логики ---
    async def get_user(self, m: Message):
        uid = m.from_user.id
        user = next((u for u in self.connected_users if u['id'] == uid), None)
        is_new = False
        if not user:
            is_new = True
            user = {
                "id": uid, "first_name": m.from_user.first_name, "username": m.from_user.username,
                "is_banned": False, "is_active": True, "warns": 0, "last_topic_id": None,
                "joined_at": int(time.time())
            }
            self.connected_users.append(user)
            await self.sync_queue.put(("config", {}))
        else:
            # Если юзер пишет сам — значит он не заблокировал бота
            if not user.get('is_active', True):
                user['is_active'] = True
                await self.sync_queue.put(("config", {}))
        return user, is_new

    async def ensure_topic(self, user, force_new: bool = False):
        if not self.use_topics or not self.admin_id: return None
        if not force_new and user.get("last_topic_id"): return user["last_topic_id"]
        try:
            is_anon = self.settings.get('anonymousTopics', False)
            topic_name = f"User #{get_anon_id(user['id'])}" if is_anon else f"{user['first_name']} [{user['id']}]"
            topic = await self.bot.create_forum_topic(self.admin_id, topic_name)
            user["last_topic_id"] = topic.message_thread_id
            await self.sync_queue.put(("config", {}))
            return topic.message_thread_id
        except Exception: return None

    async def forward_to_admin(self, m: Message, user: dict, is_first: bool = False, btn_text: str = ""):
        if not self.admin_id: return
        thread_id = await self.ensure_topic(user, force_new=(self.topic_per_request and (btn_text != "" or is_first))) if self.use_topics else None

        now = time.time()
        header = ""
        # Показываем заголовок если: новый юзер, нажата кнопка-заявка или прошло > 10 минут
        if not self.use_topics or is_first or btn_text or (now - self.last_header_time.get(user['id'], 0)) > 600:
            header = format_admin_header(self.admin_template, m, self.settings, is_first, btn_text)
            if header: self.last_header_time[user['id']] = now

        try:
            if m.text: await self.bot.send_message(self.admin_id, f"{header}{m.text}", message_thread_id=thread_id)
            elif m.photo: await self.bot.send_photo(self.admin_id, m.photo[-1].file_id, caption=f"{header}{m.caption or ''}", message_thread_id=thread_id)
            elif m.video: await self.bot.send_video(self.admin_id, m.video.file_id, caption=f"{header}{m.caption or ''}", message_thread_id=thread_id)
            elif m.document: await self.bot.send_document(self.admin_id, m.document.file_id, caption=f"{header}{m.caption or ''}", message_thread_id=thread_id)
            else:
                if header: await self.bot.send_message(self.admin_id, header, message_thread_id=thread_id)
                await self.bot.copy_message(self.admin_id, m.chat.id, m.message_id, message_thread_id=thread_id)
        except TelegramForbiddenError:
            await self.mark_user_inactive(user['id'])
        except Exception: pass

    async def handle_admin_reply(self, m: Message):
        target_id = None
        # Поиск по топику
        if m.message_thread_id:
            u = next((u for u in self.connected_users if u.get("last_topic_id") == m.message_thread_id), None)
            if u: target_id = u["id"]
        # Поиск по ответу (Reply) в обычном чате
        if not target_id and m.reply_to_message:
            match = re.search(r"ID: (\d+)", m.reply_to_message.text or m.reply_to_message.caption or "")
            if match: target_id = int(match.group(1))

        if target_id:
            try:
                await self.bot.copy_message(target_id, m.chat.id, m.message_id)
                await self.log_it(target_id, "Admin", m.text or "[Медиа]", is_admin=True)
            except TelegramForbiddenError:
                await self.mark_user_inactive(target_id)
                await m.reply("❌ Пользователь удалил бота. Доставка невозможна.")
            except Exception as e: await m.reply(f"❌ Ошибка доставки: {e}")

    async def register_handlers(self):
        @self.router.message(CommandStart())
        async def cmd_start(m: Message):
            user, is_new = await self.get_user(m)
            if user.get("is_banned"): return
            await m.answer(self.welcome_message, reply_markup=self.get_kb())
            await self.log_it(user['id'], m.from_user.full_name, "/start")

        @self.router.message(F.chat.id == self.admin_id)
        async def admin_input(m: Message):
            # Модерация через команды
            if m.text and (m.text.startswith("/") or m.text.startswith("!")):
                cmd = m.text.lower().split()[0][1:]
                target = None
                # Ищем цель команды в топике или по реплаю
                if m.message_thread_id: target = next((u for u in self.connected_users if u.get("last_topic_id") == m.message_thread_id), None)
                if not target and m.reply_to_message:
                    match = re.search(r"ID: (\d+)", m.reply_to_message.text or m.reply_to_message.caption or "")
                    if match: target = next((u for u in self.connected_users if u['id'] == int(match.group(1))), None)
                
                if target:
                    if cmd == "ban": target['is_banned'] = True
                    elif cmd == "unban": target['is_banned'] = False
                    elif cmd == "warn": 
                        target['warns'] = target.get('warns', 0) + 1
                        if self.auto_ban_threshold > 0 and target['warns'] >= self.auto_ban_threshold: target['is_banned'] = True
                    elif cmd == "unwarn":
                        target['warns'] = max(0, target.get('warns', 0) - 1)
                    
                    await self.sync_queue.put(("config", {}))
                    await m.reply(f"✅ Команда <b>{cmd}</b> выполнена для юзера {target['id']}.\nТекущий статус: {'BAN' if target['is_banned'] else 'OK'} | Warns: {target['warns']}")
                    return
            # Обычный ответ
            await self.handle_admin_reply(m)

        @self.router.message()
        async def global_handler(m: Message):
            if self.admin_id and m.chat.id == self.admin_id: return
            user, is_new = await self.get_user(m)
            if user.get("is_banned"): return
            
            if m.text:
                txt = m.text.lower().strip()
                # Обработка кнопок меню
                for b in self.buttons:
                    if b.get('text') and b['text'].lower() == txt:
                        await self.forward_to_admin(m, user, is_first=is_new, btn_text=b['text'] if b.get('type')=='request' else "")
                        if b.get('response'): await m.answer(b['response'])
                        await self.log_it(user['id'], m.from_user.full_name, f"Меню: {b['text']}")
                        return
                # Обработка триггеров (ключевых слов)
                for t in self.triggers:
                    if t.get('keyword') and t['keyword'].lower() in txt:
                        await m.answer(t['response'])
                        await self.log_it(user['id'], m.from_user.full_name, f"Trigger: {t['keyword']}")
                        return
            
            # Пересылка обычного сообщения
            await self.forward_to_admin(m, user, is_first=is_new)
            await self.log_it(user['id'], m.from_user.full_name, m.text or "[Медиа]")

    def get_kb(self):
        vbs = [b for b in self.buttons if b.get('text')]
        if not vbs: return None
        rows = [[KeyboardButton(text=vbs[i]['text'])] for i in range(len(vbs))]
        return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

    async def shutdown(self, signal_type):
        self.is_running = False
        await self.sync_queue.put(("config", {}))
        await asyncio.sleep(1.5)
        await self.bot.session.close()
        sys.exit(0)

    async def run(self):
        loop = asyncio.get_running_loop()
        for s in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(s, lambda sig=s: asyncio.create_task(self.shutdown(sig)))
        
        # Запуск фоновых процессов
        asyncio.create_task(self.db_sync_worker())
        asyncio.create_task(self.remote_sync_poller())
        
        await self.register_handlers()
        self.dp.include_router(self.router)
        logger.info(f"✨ Бот {self.bot_id} запущен и синхронизирован.")
        await self.dp.start_polling(self.bot)

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    try:
        with open(sys.argv[1], 'r', encoding='utf-8') as f: cfg = json.load(f)
        asyncio.run(BotInstance(cfg).run())
    except Exception as e: 
        logger.error(f"CRITICAL ERROR: {e}")
