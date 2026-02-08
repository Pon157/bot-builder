import asyncio
import logging
import json
import httpx
import os
import sys
import hashlib
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any, Union

from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode, ContentType, ChatMemberStatus
from aiogram.filters import CommandStart, Command, ChatMemberUpdatedFilter
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
    ReplyKeyboardRemove, ForumTopicCreated, ChatMemberUpdated
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

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_anon_id(user_id: int) -> str:
    """Генерация короткого хеша для анонимности"""
    return hashlib.md5(str(user_id).encode()).hexdigest()[:6].upper()

def format_admin_header(m: Message, settings: dict, is_first: bool = False, btn_text: str = "") -> str:
    """Формирование заголовка сообщения для админа"""
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

    status_line = ""
    if btn_text:
        status_line = settings.get('ticketMessageHeader', "🆘 <b>ЗАЯВКА</b>")
        if "{btn}" in status_line:
            status_line = status_line.replace("{btn}", btn_text)
        elif "[Кнопка" not in status_line:
            status_line += f" [Кнопка: {btn_text}]:"
    elif is_first:
        status_line = settings.get('firstMessageHeader', "🆕 <b>ПЕРВОЕ ОБРАЩЕНИЕ:</b>")
    else:
        status_line = settings.get('commonMessageHeader', "📩 <b>СООБЩЕНИЕ:</b>")

    return f"{status_line}\n{user_info}\n\n"

# --- ОСНОВНОЙ КЛАСС БОТА ---
class BotInstance:
    def __init__(self, config_data: dict):
        self.bot_id = config_data.get('id')
        self.token = config_data.get('token')
        # Токен из .env уже подгружен в систему, но aiogram инициализируется здесь
        self.sb_url = os.getenv("SUPABASE_URL", "").rstrip('/')
        self.sb_key = os.getenv("SUPABASE_KEY", "")
        
        self.bot = Bot(token=self.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher()
        self.router = Router()
        
        self.msg_map = {}
        self.flood_cache = {}
        self.is_running = True
        
        # Очередь для моментальной синхронизации
        self.sync_queue = asyncio.Queue()
        
        self.apply_config(config_data)

def apply_config(self, data: dict):
        """Парсинг конфигурации и инициализация статистики (UTC версия)"""
        raw_cfg = data.get('config', {}) if isinstance(data.get('config'), dict) else {}
        full_cfg = {**data, **raw_cfg} 
        
        try:
            admin_id_raw = full_cfg.get('adminChatId')
            self.admin_chat_id = int(str(admin_id_raw).strip()) if admin_id_raw else None
        except ValueError:
            self.admin_chat_id = None

        self.buttons = full_cfg.get('buttons', [])
        self.triggers = full_cfg.get('triggers', [])
        self.welcome_text = full_cfg.get('welcomeMessage', 'Здравствуйте!')
        self.settings = full_cfg.get('settings', {})
        
        self.use_topics = self.settings.get('useTopics', False)
        self.topic_per_req = self.settings.get('topicPerRequest', False)
        self.rate_limit = float(self.settings.get('rateLimit', 1.0))
        self.auto_ban_limit = int(self.settings.get('autoBanThreshold', 3))
        
        self.users_list = full_cfg.get('connectedUsers', [])
        
        # --- ИНИЦИАЛИЗАЦИЯ СТАТИСТИКИ ---
        # Мы НЕ создаем статы с нуля, а вытягиваем их из пришедшего конфига (Supabase)
        incoming_stats = full_cfg.get('stats')
        if isinstance(incoming_stats, dict):
            # Если stats есть в БД, берем их как основу
            self.stats_data = {
                "totalMessages": incoming_stats.get("totalMessages", 0),
                "incomingToday": incoming_stats.get("incomingToday", 0),
                "outgoingToday": incoming_stats.get("outgoingToday", 0),
                "bannedCount": incoming_stats.get("bannedCount", 0),
                "activeUsers24h": incoming_stats.get("activeUsers24h", 0),
                "history": incoming_stats.get("history", [])
            }
        else:
            # Если в БД совсем пусто (первый запуск бота)
            self.stats_data = {
                "totalMessages": 0,
                "incomingToday": 0,
                "outgoingToday": 0,
                "bannedCount": 0,
                "history": [],
                "activeUsers24h": 0
            }

        # --- ИНИЦИАЛИЗАЦИЯ ИСТОРИИ (UTC) ---
        now = datetime.now() # Оставляем системный UTC
        current_date = now.strftime("%d.%m")
        
        if not self.stats_data["history"]:
            self.stats_data["history"] = [{
                "date": current_date,
                "incoming": 0,
                "outgoing": 0,
                "totalUsers": len(self.users_list),
                "activeUsers": 0
            }]

    async def daily_stats_rotator(self):
        """
        Ротация статистики с корректным сохранением данных при смене дня.
        """
        while self.is_running:
            try:
                now = datetime.now()
                current_date = now.strftime("%d.%m")
                
                # Подсчет активных пользователей
                day_ago = int((now - timedelta(days=1)).timestamp())
                active_count = sum(1 for u in self.users_list if u.get('last_seen', 0) > day_ago)
                self.stats_data["activeUsers24h"] = active_count

                history = self.stats_data.get("history", [])
                if not history:
                    history = [{
                        "date": current_date, "incoming": 0, "outgoing": 0,
                        "totalUsers": len(self.users_list), "activeUsers": active_count
                    }]
                    self.stats_data["history"] = history

                # ПРОВЕРКА СМЕНЫ ДНЯ
                if history[-1]["date"] != current_date:
                    # 1. ФИКСИРУЕМ финальные данные в последнюю точку ВЧЕРАШНЕГО дня
                    # Это гарантирует, что в Supabase улетят полные цифры за вчера
                    history[-1]["incoming"] = self.stats_data.get("incomingToday", 0)
                    history[-1]["outgoing"] = self.stats_data.get("outgoingToday", 0)
                    history[-1]["totalUsers"] = len(self.users_list)
                    history[-1]["activeUsers"] = active_count
                    
                    # 2. Только после сохранения обнуляем суточные счетчики
                    self.stats_data["incomingToday"] = 0
                    self.stats_data["outgoingToday"] = 0
                    
                    # 3. Создаем НОВУЮ точку для сегодняшнего дня (с нулями)
                    new_point = {
                        "date": current_date,
                        "incoming": 0,
                        "outgoing": 0,
                        "totalUsers": len(self.users_list),
                        "activeUsers": active_count
                    }
                    history.append(new_point)
                    
                    # Оставляем 14 дней
                    self.stats_data["history"] = history[-14:]
                    # Важно обновить локальную ссылку после среза
                    history = self.stats_data["history"]
                
                # 4. ОБНОВЛЕНИЕ ТЕКУЩЕГО ДНЯ (Real-time)
                # Это работает всегда, обновляя самую последнюю запись в истории
                last_point = history[-1]
                last_point["incoming"] = self.stats_data.get("incomingToday", 0)
                last_point["outgoing"] = self.stats_data.get("outgoingToday", 0)
                last_point["totalUsers"] = len(self.users_list)
                last_point["activeUsers"] = active_count

                # Отправляем на синхронизацию в Supabase
                await self.sync_queue.put(("sync_state", None))
                
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Rotator Error: {e}")
                await asyncio.sleep(60)
                
    async def database_sync_worker(self):
        """Воркер синхронизации с защитой от падения"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {
                "apikey": self.sb_key,
                "Authorization": f"Bearer {self.sb_key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            }
            while self.is_running:
                try:
                    # Безопасное получение из очереди
                    item = await asyncio.wait_for(self.sync_queue.get(), timeout=1.0)
                    
                    # Проверка на "битые" данные в очереди
                    if not isinstance(item, tuple): 
                        self.sync_queue.task_done()
                        continue
                    
                    action, payload = item
                    
                    if action == "log_message":
                        await client.post(f"{self.sb_url}/rest/v1/bot_messages", json=payload, headers=headers)
                    
                    elif action == "sync_state":
                        update_payload = {
                            "config": {
                                "connectedUsers": self.users_list,
                                "stats": self.stats_data,
                                "settings": self.settings,
                                "buttons": self.buttons,
                                "triggers": self.triggers,
                                "welcomeMessage": self.welcome_text,
                                "adminChatId": self.admin_chat_id
                            }
                        }
                        await client.patch(
                            f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}", 
                            json=update_payload, 
                            headers=headers
                        )
                    
                    self.sync_queue.task_done()
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Sync Worker Error: {e}")
                    # Обязательно сообщаем очереди, что задача "выполнена" (даже с ошибкой), иначе очередь зависнет
                    try: self.sync_queue.task_done()
                    except: pass

    async def check_antispam(self, user_id: int) -> bool:
        if self.rate_limit <= 0: return False
        now = time.time()
        last_time = self.flood_cache.get(user_id, 0)
        if now - last_time < self.rate_limit: return True
        self.flood_cache[user_id] = now
        return False

    async def log_and_update(self, uid: int, name: str, text: str, is_admin: bool = False):
        """Логирование и обновление статистики для графиков"""
        # Лог сообщения
        await self.sync_queue.put(("log_message", {
            "bot_id": self.bot_id, 
            "user_id": uid, 
            "first_name": name,
            "message_text": text[:950] if text else "[Медиа]", 
            "is_from_admin": is_admin
        }))
        
        # Обновление счетчиков
        self.stats_data["totalMessages"] = self.stats_data.get("totalMessages", 0) + 1
        stat_key = "outgoingToday" if is_admin else "incomingToday"
        self.stats_data[stat_key] = self.stats_data.get(stat_key, 0) + 1
        
        # Обновление пользователя
        if not is_admin:
            for u in self.users_list:
                if u['id'] == uid:
                    u['last_seen'] = int(time.time())
                    u['name'] = name # Обновляем имя, если изменилось
                    break
        
        # Сразу пушим обновление для графиков
        await self.sync_queue.put(("sync_state", None))

    async def get_user_state(self, m: Message):
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
                "last_seen": int(time.time()),
                "last_topic_id": None
            }
            self.users_list.append(user)
            await self.sync_queue.put(("sync_state", None))
        else:
            user["last_seen"] = int(time.time())
            if not user.get("is_active", True):
                user["is_active"] = True
                await self.sync_queue.put(("sync_state", None))
            
        return user, is_first_time

    async def resolve_thread(self, user: dict, force_new: bool = False):
        if not self.use_topics or not self.admin_chat_id: return None
        if not force_new and user.get("last_topic_id"): return user["last_topic_id"]
        try:
            is_anon = self.settings.get('anonymousTopics', False)
            topic_name = f"#{get_anon_id(user['id'])}" if is_anon else f"{user['first_name']} [{user['id']}]"
            new_topic = await self.bot.create_forum_topic(self.admin_chat_id, topic_name)
            user["last_topic_id"] = new_topic.message_thread_id
            await self.sync_queue.put(("sync_state", None))
            return new_topic.message_thread_id
        except Exception as e:
            logger.error(f"Topic Error: {e}")
            return None

    async def forward_to_admin(self, m: Message, user: dict, is_first: bool = False, btn_text: str = ""):
        if not self.admin_chat_id: return
        force_new_topic = self.topic_per_req and (btn_text != "" or is_first)
        thread_id = await self.resolve_thread(user, force_new=force_new_topic)
        header_text = format_admin_header(m, self.settings, is_first, btn_text)
        
        try:
            sent_msg = None
            if m.text:
                sent_msg = await self.bot.send_message(self.admin_chat_id, f"{header_text}{m.text}", message_thread_id=thread_id)
            elif m.photo:
                sent_msg = await self.bot.send_photo(self.admin_chat_id, m.photo[-1].file_id, caption=f"{header_text}{m.caption or ''}", message_thread_id=thread_id)
            elif m.video:
                sent_msg = await self.bot.send_video(self.admin_chat_id, m.video.file_id, caption=f"{header_text}{m.caption or ''}", message_thread_id=thread_id)
            elif m.voice:
                sent_msg = await self.bot.send_voice(self.admin_chat_id, m.voice.file_id, caption=f"{header_text}{m.caption or ''}", message_thread_id=thread_id)
            else:
                if header_text:
                    await self.bot.send_message(self.admin_chat_id, header_text, message_thread_id=thread_id)
                sent_msg = await self.bot.copy_message(self.admin_chat_id, m.chat.id, m.message_id, message_thread_id=thread_id)
            
            if sent_msg:
                self.msg_map[sent_msg.message_id] = user['id']
                
        except Exception as e:
            logger.error(f"Forwarding Error: {e}")

    async def admin_control_logic(self, m: Message):
        if not m.text or not (m.text.startswith("/") or m.text.startswith("!")): return False
        
        cmd_parts = m.text.lower().split()
        command = cmd_parts[0][1:]
        target_user = None
        
        if m.message_thread_id:
            target_user = next((u for u in self.users_list if u.get("last_topic_id") == m.message_thread_id), None)
        if not target_user and m.reply_to_message:
            uid = self.msg_map.get(m.reply_to_message.message_id)
            if uid:
                target_user = next((u for u in self.users_list if u['id'] == uid), None)
        
        if not target_user: return False

        uid = target_user['id']
        if command == "ban":
            target_user["is_banned"] = True
            self.stats_data["bannedCount"] = self.stats_data.get("bannedCount", 0) + 1
            await self.sync_queue.put(("sync_state", None))
            try: await self.bot.send_message(uid, "🚫 <b>Доступ ограничен администратором.</b>")
            except: pass
            await m.reply(f"✅ Пользователь {uid} заблокирован.")
            return True
        elif command == "unban":
            target_user["is_banned"] = False
            self.stats_data["bannedCount"] = max(0, self.stats_data.get("bannedCount", 1) - 1)
            await self.sync_queue.put(("sync_state", None))
            try: await self.bot.send_message(uid, "✅ <b>Ваш доступ восстановлен администратором.</b>")
            except: pass
            await m.reply(f"✅ Пользователь {uid} разблокирован.")
            return True
        elif command == "warn":
            target_user["warns"] = target_user.get("warns", 0) + 1
            await self.sync_queue.put(("sync_state", None))
            if self.auto_ban_limit > 0 and target_user["warns"] >= self.auto_ban_limit:
                target_user["is_banned"] = True
                self.stats_data["bannedCount"] = self.stats_data.get("bannedCount", 0) + 1
                await self.sync_queue.put(("sync_state", None))
                try: await self.bot.send_message(uid, f"🚫 <b>Авто-бан:</b> Лимит варнов ({target_user['warns']}) исчерпан.")
                except: pass
                await m.reply(f"🚨 АВТО-БАН! Юзер {uid} (Варнов: {target_user['warns']}).")
            else:
                try: await self.bot.send_message(uid, f"⚠️ <b>Предупреждение!</b> ({target_user['warns']}/{self.auto_ban_limit})")
                except: pass
                await m.reply(f"⚠️ Варн выдан. Всего: {target_user['warns']}/{self.auto_ban_limit}")
            return True
        elif command == "unwarn":
            target_user["warns"] = max(0, target_user.get("warns", 0) - 1)
            await self.sync_queue.put(("sync_state", None))
            await m.reply(f"✅ Предупреждение снято. Текущее: {target_user['warns']}")
            return True
        return False

    async def core_handlers_setup(self):
        @self.router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=ChatMemberStatus.KICKED))
        async def on_user_blocked_bot(event: ChatMemberUpdated):
            user_id = event.from_user.id
            user = next((u for u in self.users_list if u['id'] == user_id), None)
            if user:
                user["is_active"] = False
                await self.sync_queue.put(("sync_state", None))
                if self.admin_chat_id:
                    thread_id = user.get("last_topic_id")
                    text = f"🔴 <b>Внимание!</b>\nПользователь <b>{event.from_user.full_name}</b> (@{event.from_user.username or '---'}) заблокировал бота."
                    try: await self.bot.send_message(self.admin_chat_id, text, message_thread_id=thread_id)
                    except: pass
            logger.info(f"[!] Пользователь {user_id} заблокировал бота.")

        @self.router.message(CommandStart())
        async def handle_start(m: Message):
            user, is_new = await self.get_user_state(m)
            if user.get("is_banned"): return
            await m.answer(self.welcome_text, reply_markup=self.get_main_keyboard())
            await self.log_and_update(user['id'], m.from_user.full_name, "/start")

        @self.router.message(F.chat.id == self.admin_chat_id)
        async def handle_admin_input(m: Message):
            if m.text and (m.text.startswith("/") or m.text.startswith("!")):
                await self.admin_control_logic(m)
                return

            target_id = None
            if m.message_thread_id:
                u = next((u for u in self.users_list if u.get("last_topic_id") == m.message_thread_id), None)
                if u: target_id = u["id"]
            if not target_id and m.reply_to_message:
                target_id = self.msg_map.get(m.reply_to_message.message_id)
            
            if target_id:
                try:
                    try:
                        await self.bot.copy_message(target_id, m.chat.id, m.message_id)
                    except TelegramForbiddenError:
                        await m.reply("❌ <b>Ошибка:</b> Пользователь заблокировал бота.")
                        user = next((u for u in self.users_list if u['id'] == target_id), None)
                        if user:
                            user["is_active"] = False
                            await self.sync_queue.put(("sync_state", None))
                        return
                    except Exception:
                        if m.text: await self.bot.send_message(target_id, m.text)
                        elif m.photo: await self.bot.send_photo(target_id, m.photo[-1].file_id, caption=m.caption)
                        elif m.video: await self.bot.send_video(target_id, m.video.file_id, caption=m.caption)
                        elif m.voice: await self.bot.send_voice(target_id, m.voice.file_id)
                        else: await self.bot.forward_message(target_id, m.chat.id, m.message_id)
                    
                    await self.log_and_update(target_id, "Admin", m.text or "[Медиа]", is_admin=True)
                except Exception as e:
                    await m.reply(f"❌ <b>Ошибка:</b> {e}")

        @self.router.message()
        async def handle_user_input(m: Message):
            if self.admin_chat_id and m.chat.id == self.admin_chat_id: return
            
            user, is_new = await self.get_user_state(m)
            if user.get("is_banned") or await self.check_antispam(user['id']): return
            
            if m.text:
                clean_text = m.text.lower().strip()
                for btn in self.buttons:
                    if btn.get('text') and btn['text'].lower() == clean_text:
                        if btn.get('type') == 'request': 
                            await self.forward_to_admin(m, user, btn_text=btn['text'])
                        if btn.get('response'): 
                            await m.answer(btn['response'])
                        await self.log_and_update(user['id'], m.from_user.full_name, f"КНОПКА: {btn['text']}")
                        return
                for trig in self.triggers:
                    if trig.get('keyword') and trig['keyword'].lower() in clean_text:
                        await m.answer(trig['response'])
                        await self.log_and_update(user['id'], m.from_user.full_name, f"ТРИГГЕР: {trig['keyword']}")
                        return
            
            await self.forward_to_admin(m, user, is_first=is_new)
            await self.log_and_update(user['id'], m.from_user.full_name, m.text or "[Медиа]")

    def get_main_keyboard(self):
        active_btns = [b for b in self.buttons if b.get('text')]
        if not active_btns: return ReplyKeyboardRemove()
        keyboard_rows = []
        for i in range(0, len(active_btns), 2):
            keyboard_rows.append([KeyboardButton(text=b['text']) for b in active_btns[i:i+2]])
        return ReplyKeyboardMarkup(keyboard=keyboard_rows, resize_keyboard=True)

    async def run_instance(self):
        asyncio.create_task(self.database_sync_worker())
        asyncio.create_task(self.daily_stats_rotator())
        await self.core_handlers_setup()
        self.dp.include_router(self.router)
        logger.info(f"[*] Бот {self.bot_id} запущен.")
        try: 
            await self.dp.start_polling(self.bot)
        finally:
            self.is_running = False
            await self.bot.session.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 bot_core.py <config_path>")
        sys.exit(1)
        
    async def main():
        # Читаем конфиг из JSON-файла, который создал server.py
        cfg_path = sys.argv[1]
        try:
            with open(cfg_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Инициализируем и запускаем
            instance = BotInstance(config)
            await instance.run_instance()
            
        except Exception as e:
            logger.error(f"FATAL ERROR: {e}")

    asyncio.run(main())
