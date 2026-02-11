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

# --- ДОБАВЛЕНО: Загрузка переменных из .env ---
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Если библиотека не установлена, бот просто продолжит работу, 
    # надеясь на системные переменные
    pass

# Импорты vkbottle
from vkbottle import BaseMiddleware, Bot, CtxStorage
from vkbottle.bot import Message
from vkbottle.dispatch.rules import ABCRule
from vkbottle import Keyboard, KeyboardButtonColor, Text
from vkbottle.exception_factory import VKAPIError

# --- ГЛОБАЛЬНАЯ КОНФИГУРАЦИЯ ЛОГИРОВАНИЯ ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotCoreEngineVK")

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_anon_id(user_id: int) -> str:
    """Генерация короткого хеша для анонимности"""
    return hashlib.md5(str(user_id).encode()).hexdigest()[:6].upper()

def format_admin_header(user: dict, settings: dict, is_first: bool = False, btn_text: str = "") -> str:
    """Формирование заголовка сообщения для админа (текст)"""
    is_anon = settings.get('anonymousTopics', False)
    uid = user['id']
    anon_tag = f"#{get_anon_id(uid)}"
    
    if is_anon:
        user_info = f"👤 Аноним {anon_tag}"
    else:
        info_parts = []
        if settings.get('showHeaderName', True):
            name = user.get('first_name', "Пользователь")
            info_parts.append(f"{name}")
        
        if settings.get('showHeaderUsername', True) and user.get('domain'):
             info_parts.append(f"(@{user['domain']})")
            
        if settings.get('showHeaderId', True):
            info_parts.append(f"ID: {uid}")
            
        user_info = " | ".join(info_parts) if info_parts else f"Юзер {anon_tag}"

    status_line = ""
    if btn_text:
        status_line = settings.get('ticketMessageHeader', "🆘 ЗАЯВКА")
        if "{btn}" in status_line:
            status_line = status_line.replace("{btn}", btn_text)
        elif "[Кнопка" not in status_line:
            status_line += f" [Кнопка: {btn_text}]:"
    elif is_first:
        status_line = settings.get('firstMessageHeader', "🆕 ПЕРВОЕ ОБРАЩЕНИЕ:")
    else:
        status_line = settings.get('commonMessageHeader', "📩 СООБЩЕНИЕ:")

    return f"{status_line}\n{user_info}\n⬇️⬇️⬇️"

# --- MIDDLEWARE ---
class LicenseMiddleware(BaseMiddleware[Message]):
    async def pre(self):
        bot_instance = getattr(self.event.ctx_api, "bot_instance_ref", None)
        
        if bot_instance and getattr(bot_instance, 'license_expired', False):
            await self.event.answer("❌ Лицензия этого бота истекла.\nПожалуйста, продлите её в панели управления.")
            self.stop("License expired")

    async def post(self):
        pass

# --- ОСНОВНОЙ КЛАСС БОТА ---
class BotInstance:
    def __init__(self, config_data: dict):
        self.bot_id = config_data.get('id')
        self.token = config_data.get('token')
        
        self.license_expired = False 
        
        # --- ИСПРАВЛЕНО: Теперь ключи подтягиваются корректно ---
        self.sb_url = os.getenv("SUPABASE_URL")
        self.sb_key = os.getenv("SUPABASE_KEY")

        if not self.sb_url:
            # Фолбек на конфиг, если в .env пусто
            self.sb_url = config_data.get("config", {}).get("api_url", "http://localhost:8000")
        
        if not self.sb_key:
            logger.warning(f"⚠️ [{self.bot_id}] SUPABASE_KEY не найден в окружении!")
            self.sb_key = "" # Чтобы не падал конкатенатор заголовков

        self.sb_url = self.sb_url.rstrip('/')
        
        # Инициализация бота VK
        self.bot = Bot(token=self.token)
        # Сохраняем ссылку на себя внутри API объекта
        self.bot.api.bot_instance_ref = self
        
        self.msg_map = {} 
        self.flood_cache = {}
        self.is_running = True
        self.sync_queue = asyncio.Queue()
        
        # Применяем стартовый конфиг
        self.apply_config(config_data)

    async def register_event(self, is_incoming: bool = True):
        """Обновляет статистику в памяти и отправляет в Supabase"""
        try:
            today = datetime.now().strftime("%d.%m")
            
            # 1. Проверяем наличие stats в конфиге
            if not isinstance(self.config.get("stats"), dict):
                self.config["stats"] = {"history": [], "totalMessages": 0}
            
            st = self.config["stats"]
            
            # 2. Обновляем счетчики (гарантируем наличие ключей через get)
            st["totalMessages"] = st.get("totalMessages", 0) + 1
            
            if is_incoming:
                st["incomingToday"] = st.get("incomingToday", 0) + 1
                # Если ключа outgoingToday нет, инициализируем его нулем
                if "outgoingToday" not in st: st["outgoingToday"] = 0
            else:
                st["outgoingToday"] = st.get("outgoingToday", 0) + 1
                if "incomingToday" not in st: st["incomingToday"] = 0

            # 3. Работа с историей
            history = st.get("history", [])
            if not isinstance(history, list): history = []
            
            day_entry = next((item for item in history if item.get("date") == today), None)

            if day_entry:
                if is_incoming:
                    day_entry["incoming"] = day_entry.get("incoming", 0) + 1
                else:
                    day_entry["outgoing"] = day_entry.get("outgoing", 0) + 1
            else:
                history.append({
                    "date": today, 
                    "incoming": 1 if is_incoming else 0, 
                    "outgoing": 0 if is_incoming else 1,
                    "totalUsers": len(self.config.get("connectedUsers", [])),
                    "activeUsers": 1
                })

            st["history"] = history[-14:] # Только последние 14 дней
            self.config["stats"] = st # Сохраняем обратно в объект

            # 4. Отправка в БД
            async with httpx.AsyncClient() as client:
                resp = await client.patch(
                    f"{self.supabase_url}/rest/v1/bots?id=eq.{self.bot_id}",
                    headers=self.headers,
                    json={"stats": st}
                )
                if resp.status_code not in [200, 201, 204]:
                    logger.error(f"⚠️ Ошибка записи статы в БД: {resp.text}")

        except Exception as e:
            logger.error(f"❌ Ошибка обновления статистики: {e}", exc_info=True)
    async def update_stats(self, is_incoming: bool = True):
        """Обновляет статистику в памяти и отправляет в Supabase"""
        try:
            today = datetime.now().strftime("%d.%m")
            # Берем текущую статику из памяти (которую мы синхронизировали)
            stats = self.config.get("stats", {})
            if not isinstance(stats, dict): 
                stats = {}
            
            # Общие счетчики
            stats["totalMessages"] = stats.get("totalMessages", 0) + 1
            if is_incoming:
                stats["incomingToday"] = stats.get("incomingToday", 0) + 1
            else:
                stats["outgoingToday"] = stats.get("outgoingToday", 0) + 1

            # Работа с историей для графиков
            history = stats.get("history", [])
            if not isinstance(history, list):
                history = []
                
            day_entry = next((item for item in history if item.get("date") == today), None)

            if day_entry:
                if is_incoming: 
                    day_entry["incoming"] = day_entry.get("incoming", 0) + 1
                else: 
                    day_entry["outgoing"] = day_entry.get("outgoing", 0) + 1
            else:
                history.append({
                    "date": today,
                    "incoming": 1 if is_incoming else 0,
                    "outgoing": 0 if is_incoming else 1,
                    "totalUsers": len(self.config.get("connectedUsers", [])),
                    "activeUsers": 1
                })
            
            stats["history"] = history[-14:] # Храним только 2 недели
            self.config["stats"] = stats

            # Сохраняем в базу (Supabase)
            async with httpx.AsyncClient() as client:
                await client.patch(
                    f"{self.supabase_url}/rest/v1/bots?id=eq.{self.bot_id}",
                    headers=self.headers,
                    json={"stats": stats}
                )
        except Exception as e:
            logger.error(f"Error updating stats: {e}", exc_info=True)
    async def license_checker_logic(self):
        try:
            curr_time = int(time.time() * 1000)
            if self.license_expires_at and self.license_expires_at < curr_time:
                if not self.license_expired:
                    logger.warning(f" [!] Лицензия {self.bot_id} истекла!")
                    self.license_expired = True 
                    
                    async with httpx.AsyncClient() as client:
                        headers = {"apikey": self.sb_key, "Authorization": f"Bearer {self.sb_key}"}
                        await client.patch(
                            f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                            json={"status": "IDLE"},
                            headers=headers
                        )
            else:
                self.license_expired = False
        except Exception as e:
            logger.error(f"Ошибка в license_checker_logic: {e}")

    async def license_checker(self):
        logger.info(f"[*] Мониторинг лицензии для {self.bot_id} запущен")
        while self.is_running:
            await self.license_checker_logic()
            await asyncio.sleep(120)

    def apply_config(self, data: dict):
        """Парсинг конфигурации для VK-бота (с поддержкой vk_group_id)"""
        raw_cfg = data.get('config', {}) if isinstance(data.get('config'), dict) else {}
        full_cfg = {**data, **raw_cfg} 
        
        # 1. Читаем VK Group ID (пытаемся найти во всех вариантах написания)
        self.vk_group_id = full_cfg.get('vk_group_id') or full_cfg.get('vkGroupId')

        # 2. Читаем Admin Chat ID
        try:
            # Ищем и новый формат (admin_chat_id), и старый (adminChatId)
            admin_id_raw = full_cfg.get('admin_chat_id') or full_cfg.get('adminChatId')
            self.admin_chat_id = int(str(admin_id_raw).strip()) if admin_id_raw else None
        except ValueError:
            self.admin_chat_id = None

        # 3. Основные настройки
        self.buttons = full_cfg.get('buttons', [])
        self.triggers = full_cfg.get('triggers', [])
        self.welcome_text = full_cfg.get('welcomeMessage', 'Здравствуйте!')
        self.settings = full_cfg.get('settings', {})
        
        # Настройки лимитов
        self.rate_limit = float(self.settings.get('rateLimit', 1.0))
        self.auto_ban_limit = int(self.settings.get('autoBanThreshold', 3))
        self.users_list = full_cfg.get('connectedUsers', [])
        self.license_expires_at = full_cfg.get('license_expires_at', 0)
        
        # 4. Обработка статистики
        incoming_stats = full_cfg.get('stats')
        if isinstance(incoming_stats, dict):
            self.stats_data = {
                "totalMessages": incoming_stats.get("totalMessages", 0),
                "incomingToday": incoming_stats.get("incomingToday", 0),
                "outgoingToday": incoming_stats.get("outgoingToday", 0),
                "bannedCount": incoming_stats.get("bannedCount", 0),
                "activeUsers24h": incoming_stats.get("activeUsers24h", 0),
                "history": incoming_stats.get("history", [])
            }
        else:
            self.stats_data = {
                "totalMessages": 0, "incomingToday": 0, "outgoingToday": 0,
                "bannedCount": 0, "history": [], "activeUsers24h": 0
            }

        # 5. Инициализация истории, если она пуста
        now = datetime.now()
        current_date = now.strftime("%d.%m")
        if not self.stats_data["history"]:
            self.stats_data["history"] = [{
                "date": current_date, "incoming": 0, "outgoing": 0,
                "totalUsers": len(self.users_list), "activeUsers": 0
            }]

    async def daily_stats_rotator(self):
        while self.is_running:
            try:
                now = datetime.now()
                current_date = now.strftime("%d.%m")
                
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

                if history[-1]["date"] != current_date:
                    history[-1]["incoming"] = self.stats_data.get("incomingToday", 0)
                    history[-1]["outgoing"] = self.stats_data.get("outgoingToday", 0)
                    history[-1]["totalUsers"] = len(self.users_list)
                    history[-1]["activeUsers"] = active_count
                    
                    self.stats_data["incomingToday"] = 0
                    self.stats_data["outgoingToday"] = 0
                    
                    new_point = {
                        "date": current_date,
                        "incoming": 0, "outgoing": 0,
                        "totalUsers": len(self.users_list),
                        "activeUsers": active_count
                    }
                    history.append(new_point)
                    self.stats_data["history"] = history[-14:]
                    history = self.stats_data["history"]
                
                last_point = history[-1]
                last_point["incoming"] = self.stats_data.get("incomingToday", 0)
                last_point["outgoing"] = self.stats_data.get("outgoingToday", 0)
                last_point["totalUsers"] = len(self.users_list)
                last_point["activeUsers"] = active_count

                await self.sync_queue.put(("sync_state", None))
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Rotator Error: {e}")
                await asyncio.sleep(60)

    async def database_sync_worker(self):
        """Воркер синхронизации для ВК: защищает кнопки и настройки от затирания"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Предварительная проверка URL для избежания ошибок протокола
            if not self.sb_url or not self.sb_url.startswith("http"):
                logger.warning(f"⚠️ SUPABASE_URL некорректен ('{self.sb_url}'). Попытка восстановить из конфига...")
                # Пытаемся взять api_url из конфига как запасной вариант
                self.sb_url = os.getenv("SERVER_URL", "http://localhost:8000").rstrip('/')

            headers = {
                "apikey": self.sb_key,
                "Authorization": f"Bearer {self.sb_key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            }
            
            while self.is_running:
                try:
                    # Ждем задачу из очереди
                    item = await asyncio.wait_for(self.sync_queue.get(), timeout=1.0)
                    if not isinstance(item, tuple):
                        self.sync_queue.task_done()
                        continue

                    action, payload = item

                    # 1. Логирование сообщений
                    if action == "log_message":
                        if self.sb_url.startswith("http"):
                            await client.post(f"{self.sb_url}/rest/v1/bot_messages", json=payload, headers=headers)
                        else:
                            logger.error("❌ Невозможно логировать: отсутствует базовый URL")

                    # 2. Синхронизация состояния (основная логика)
                    elif action == "sync_state":
                        if not self.sb_url or not self.sb_url.startswith("http"):
                            logger.error(f"❌ ОШИБКА: Некорректный URL для синхронизации: '{self.sb_url}'")
                            self.sync_queue.task_done()
                            continue
        
                        # Получаем актуальный конфиг из базы
                        res = await client.get(
                            f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                            headers=headers
                        )

                        if res.status_code == 200 and res.json():
                            remote_data = res.json()[0]
                            remote_config = remote_data.get("config", {})

                            # Объединяем локальные данные со свежими из БД
                            new_config = {
                                **remote_config,            # Конфиг из БД (кнопки, триггеры) приоритетнее
                                "stats": self.stats_data,    # Но статы берем локальные (текущие)
                                "connectedUsers": self.users_list,
                                "vk_group_id": getattr(self, 'vk_group_id', None),
                                "admin_chat_id": self.admin_chat_id,
                                "adminChatId": self.admin_chat_id
                            }

                            # Патчим базу объединенным конфигом
                            await client.patch(
                                f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                                json={"config": new_config},
                                headers=headers
                            )

                            # Обновляем память бота, чтобы он сразу видел изменения из админки
                            self.apply_config({
                                **remote_data,
                                "config": remote_config
                            })

                    self.sync_queue.task_done()
                    
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"🚨 VK Sync Worker Error: {e}")
                    try:
                        self.sync_queue.task_done()
                    except:
                        pass
                        
    async def check_antispam(self, user_id: int) -> bool:
        if self.rate_limit <= 0: return False
        now = time.time()
        last_time = self.flood_cache.get(user_id, 0)
        if now - last_time < self.rate_limit: return True
        self.flood_cache[user_id] = now
        return False

    async def log_and_update(self, uid: int, name: str, text: str, is_admin: bool = False):
        await self.sync_queue.put(("log_message", {
            "bot_id": self.bot_id, 
            "user_id": uid, 
            "first_name": name,
            "message_text": text[:950] if text else "[Медиа]", 
            "is_from_admin": is_admin
        }))
        
        self.stats_data["totalMessages"] = self.stats_data.get("totalMessages", 0) + 1
        stat_key = "outgoingToday" if is_admin else "incomingToday"
        self.stats_data[stat_key] = self.stats_data.get(stat_key, 0) + 1
        
        if not is_admin:
            for u in self.users_list:
                if u['id'] == uid:
                    u['last_seen'] = int(time.time())
                    u['first_name'] = name 
                    break
        
        await self.sync_queue.put(("sync_state", None))

    async def get_user_state(self, m: Message):
        uid = m.from_id
        user = next((u for u in self.users_list if u['id'] == uid), None)
        is_first_time = False
        
        # Получаем инфо о юзере из API
        user_info = (await self.bot.api.users.get(user_ids=[uid]))[0]
        full_name = f"{user_info.first_name} {user_info.last_name}"
        
        if not user:
            is_first_time = True
            user = {
                "id": uid, 
                "first_name": full_name, 
                "username": user_info.domain, 
                "domain": user_info.domain,
                "is_banned": False, 
                "is_active": True, 
                "warns": 0, 
                "joined_at": int(time.time()),
                "last_seen": int(time.time()),
            }
            self.users_list.append(user)
            await self.sync_queue.put(("sync_state", None))
        else:
            user["last_seen"] = int(time.time())
            if not user.get("is_active", True):
                user["is_active"] = True
                await self.sync_queue.put(("sync_state", None))
            
        return user, is_first_time

    async def forward_to_admin(self, m: Message, user: dict, is_first: bool = False, btn_text: str = ""):
        if not self.admin_chat_id: return
        header_text = format_admin_header(user, self.settings, is_first, btn_text)
        
        try:
            # В ВК пересылка сообщений между чатами требует указания peer_id источника.
            # forward_messages работает только внутри одного диалога.
            # Используем forward с указанием peer_id исходного чата (от кого пришло).
            sent_msg_id = await self.bot.api.messages.send(
                peer_id=self.admin_chat_id,
                message=header_text,
                forward={
                    "peer_id": m.peer_id,
                    "message_ids": [m.id],
                    "is_reply": False
                },
                random_id=0
            )

            # Сохраняем маппинг: ID сообщения у админа -> ID пользователя
            self.msg_map[sent_msg_id] = user['id']

        except Exception as e:
            logger.error(f"Forwarding Error: {e}")

    async def admin_control_logic(self, m: Message):
        # Проверяем, является ли сообщение командой
        if not m.text or not (m.text.startswith("/") or m.text.startswith("!")): return False
        
        cmd_parts = m.text.lower().split()
        command = cmd_parts[0][1:]
        target_user = None
        
        # Логика определения цели (кому выдать бан)
        # 1. Если это реплай на сообщение бота (где бот переслал сообщение юзера)
        if m.reply_message:
            # Пробуем найти по msg_map
            uid = self.msg_map.get(m.reply_message.id)
            if uid:
                target_user = next((u for u in self.users_list if u['id'] == uid), None)
            
            # Если не нашли в map (старое сообщение), пробуем достать из forward_messages внутри reply
            if not target_user and m.reply_message.fwd_messages:
                original_sender = m.reply_message.fwd_messages[0].from_id
                target_user = next((u for u in self.users_list if u['id'] == original_sender), None)
        
        # 2. Если ID указан явно в аргументах (!ban 12345)
        if not target_user and len(cmd_parts) > 1:
            try:
                manual_id = int(cmd_parts[1])
                target_user = next((u for u in self.users_list if u['id'] == manual_id), None)
            except: pass

        if not target_user: return False

        uid = target_user['id']
        if command == "ban":
            target_user["is_banned"] = True
            self.stats_data["bannedCount"] = self.stats_data.get("bannedCount", 0) + 1
            await self.sync_queue.put(("sync_state", None))
            try: await self.bot.api.messages.send(peer_id=uid, message="🚫 Доступ ограничен администратором.", random_id=0)
            except: pass
            await m.answer(f"✅ Пользователь {uid} заблокирован.")
            return True
        elif command == "unban":
            target_user["is_banned"] = False
            self.stats_data["bannedCount"] = max(0, self.stats_data.get("bannedCount", 1) - 1)
            await self.sync_queue.put(("sync_state", None))
            try: await self.bot.api.messages.send(peer_id=uid, message="✅ Ваш доступ восстановлен администратором.", random_id=0)
            except: pass
            await m.answer(f"✅ Пользователь {uid} разблокирован.")
            return True
        elif command == "warn":
            target_user["warns"] = target_user.get("warns", 0) + 1
            await self.sync_queue.put(("sync_state", None))
            if self.auto_ban_limit > 0 and target_user["warns"] >= self.auto_ban_limit:
                target_user["is_banned"] = True
                self.stats_data["bannedCount"] = self.stats_data.get("bannedCount", 0) + 1
                await self.sync_queue.put(("sync_state", None))
                try: await self.bot.api.messages.send(peer_id=uid, message=f"🚫 Авто-бан: Лимит варнов ({target_user['warns']}) исчерпан.", random_id=0)
                except: pass
                await m.answer(f"🚨 АВТО-БАН! Юзер {uid} (Варнов: {target_user['warns']}).")
            else:
                try: await self.bot.api.messages.send(peer_id=uid, message=f"⚠️ Предупреждение! ({target_user['warns']}/{self.auto_ban_limit})", random_id=0)
                except: pass
                await m.answer(f"⚠️ Варн выдан. Всего: {target_user['warns']}/{self.auto_ban_limit}")
            return True
        elif command == "unwarn":
            target_user["warns"] = max(0, target_user.get("warns", 0) - 1)
            await self.sync_queue.put(("sync_state", None))
            await m.answer(f"✅ Предупреждение снято. Текущее: {target_user['warns']}")
            return True
        return False

    def get_main_keyboard(self):
        active_btns = [b for b in self.buttons if b.get('text')]
        if not active_btns: return Keyboard().get_json()
        
        kb = Keyboard(one_time=False, inline=False)
        # Разбиваем по 2 кнопки в ряд
        for i, btn in enumerate(active_btns):
            if i % 2 == 0 and i != 0:
                kb.row()
            kb.add(Text(btn['text']), color=KeyboardButtonColor.PRIMARY)
            
        return kb.get_json()

    async def core_handlers_setup(self):
        self.bot.labeler.message_view.register_middleware(LicenseMiddleware)
        
        # Обработка команд админа
        @self.bot.on.message(text=["/ban <item>", "/unban <item>", "/warn <item>", "/unwarn <item>", "!ban", "!unban", "!warn", "!unwarn"])
        async def admin_cmd_handler(m: Message, item: Optional[str] = None):
             if m.from_id == self.admin_chat_id:
                 await self.admin_control_logic(m)

        # Обработка ответов админа (Reply)
        @self.bot.on.message(func=lambda m: m.from_id == self.admin_chat_id and m.reply_message is not None)
        async def handle_admin_reply(m: Message):
            # Проверяем команды еще раз, чтобы не дублировать логику
            if m.text and (m.text.startswith("/") or m.text.startswith("!")):
                res = await self.admin_control_logic(m)
                if res: return

            target_id = self.msg_map.get(m.reply_message.id)
            if not target_id and m.reply_message.fwd_messages:
                 # Пытаемся достать ID из пересланного, если msg_map очистился (после перезагрузки)
                 target_id = m.reply_message.fwd_messages[0].from_id

            if target_id:
                try:
                    # В ВК нет метода "copy_message" 1-в-1, проще всего отправить текст
                    # или переслать сообщение админа юзеру.
                    # Перешлем сообщение админа юзеру, чтобы он видел контекст.
                    # Либо просто отправим текст/медиа.
                    
                    if m.text:
                        await self.bot.api.messages.send(peer_id=target_id, message=m.text, random_id=0)
                    elif m.attachments:
                        # Если есть вложения, лучше переслать сообщение целиком,
                        # так как загрузка медиа по новой - сложный процесс.
                        await self.bot.api.messages.send(
                            peer_id=target_id, 
                            message="✉️ Ответ поддержки:",
                            forward_messages=[m.id],
                            random_id=0
                        )
                    else:
                        await self.bot.api.messages.send(
                            peer_id=target_id, 
                            message="✉️",
                            forward_messages=[m.id],
                            random_id=0
                        )
                    
                    await self.log_and_update(target_id, "Admin", m.text or "[Медиа]", is_admin=True)
                except VKAPIError[901]: # Cant write to user
                    await m.answer("❌ Ошибка: Пользователь запретил сообщения.")
                    user = next((u for u in self.users_list if u['id'] == target_id), None)
                    if user:
                        user["is_active"] = False
                        await self.sync_queue.put(("sync_state", None))
                except Exception as e:
                    await m.answer(f"❌ Ошибка: {e}")
            else:
                await m.answer("⚠️ Не удалось определить получателя (возможно, старое сообщение).")

        # Обработка сообщений пользователя
        @self.bot.on.message()
        async def handle_user_input(m: Message):
            if self.admin_chat_id and m.from_id == self.admin_chat_id:
                # Если админ пишет просто текст без реплая - игнорируем или считаем заметкой
                return
            
            user, is_new = await self.get_user_state(m)
            if user.get("is_banned") or await self.check_antispam(user['id']): return
            
            if m.text:
                clean_text = m.text.lower().strip()
                
                # Обработка START (включая стандартную кнопку VK "Начать")
                if clean_text in ["start", "/start", "начать"]:
                    await m.answer(self.welcome_text, keyboard=self.get_main_keyboard())
                    await self.log_and_update(user['id'], user['first_name'], "/start")
                    return

                # КНОПКИ
                for btn in self.buttons:
                    if btn.get('text') and btn['text'].lower() == clean_text:
                        if btn.get('type') == 'request': 
                            await self.forward_to_admin(m, user, btn_text=btn['text'])
                        if btn.get('response'): 
                            await m.answer(btn['response'])
                        await self.log_and_update(user['id'], user['first_name'], f"КНОПКА: {btn['text']}")
                        return
                
                # ТРИГГЕРЫ
                for trig in self.triggers:
                    if trig.get('keyword') and trig['keyword'].lower() in clean_text:
                        await m.answer(trig['response'])
                        await self.log_and_update(user['id'], user['first_name'], f"ТРИГГЕР: {trig['keyword']}")
                        return
            
            # Если ничего не совпало - пересылаем админу
            await self.forward_to_admin(m, user, is_first=is_new)
            await self.log_and_update(user['id'], user['first_name'], m.text or "[Медиа]")

    async def run_instance(self):
        """
        Основной метод запуска логики бота.
        Вызывается из блока __main__.
        """
        logger.info(f"[*] Бот VK {self.bot_id} запускается...")
        
        # --- ПРОВЕРКА ТОКЕНА ---
        try:
            # Делаем пробный запрос к API ВК для валидации токена
            response = await self.bot.api.groups.get_by_id()
            
            # Безопасно извлекаем имя группы (поддержка разных версий vkbottle)
            if isinstance(response, list):
                group_name = response[0].name
            else:
                group_name = response.groups[0].name

            logger.info(f"✅ Токен валиден! Работаем от имени группы: {group_name}")
        except Exception as e:
            logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА ТОКЕНА: {e}")
            logger.error("Проверь: 1. Токен (расшифрован ли?). 2. Long Poll (включен ли в ВК?).")
            return 
        # -----------------------

        # Инициализация логики (лицензия, хендлеры)
        await self.license_checker_logic()
        await self.core_handlers_setup()

        logger.info(f"[*] Бот VK {self.bot_id} готов. AdminID: {self.admin_chat_id}")

        # Устанавливаем флаг работы перед запуском задач
        self.is_running = True

        # Запускаем фоновые задачи
        asyncio.create_task(self.database_sync_worker())
        asyncio.create_task(self.daily_stats_rotator())
        asyncio.create_task(self.license_checker())

        logger.info("🚀 Запуск Long Poll поллинга...")
        
        try:
            # Запускаем поллинг как отдельную задачу
            asyncio.create_task(self.bot.run_polling())
            
            # БЛОКИРУЮЩИЙ ЦИКЛ (Wait Loop)
            # Это «якорь», который удерживает процесс от завершения.
            # Пока само приложение не будет остановлено, мы спим здесь.
            while self.is_running:
                await asyncio.sleep(1)
                
        except Exception as e:
            if "close a running event loop" not in str(e):
                logger.error(f"🚨 Ошибка в жизненном цикле бота: {e}")
        finally:
            self.is_running = False
            logger.warning(f"⚠️ Поллинг бота {self.bot_id} завершен.")

# ==========================================================
# БЛОК ЗАПУСКА СКРИПТА
# ==========================================================
if __name__ == "__main__":
    import sys
    import json
    import asyncio

    # Проверка аргументов командной строки
    if len(sys.argv) < 2:
        print("Usage: python3 vkbot_core.py <config_path>")
        sys.exit(1)

    cfg_path = sys.argv[1]
    
    # Загружаем конфигурацию бота из JSON файла
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Не удалось прочитать конфиг {cfg_path}: {e}")
        sys.exit(1)

    # 1. Инициализируем объект бота (имя класса должно совпадать с твоим)
    instance = BotInstance(config) 

    # 2. Создаем и настраиваем цикл событий (Event Loop)
    # Это предотвращает ошибки "No current event loop"
    loop = asyncio.get_event_loop()

    async def main():
        """Обертка для запуска асинхронного метода инстанса"""
        await instance.run_instance()

    try:
        # Запускаем выполнение и держим процесс открытым
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем (Ctrl+C)")
    except Exception as e:
        logger.error(f"🚨 Критическая ошибка при работе: {e}", exc_info=True)
    finally:
        # Пытаемся корректно завершить оставшиеся задачи
        try:
            # Даем небольшую паузу для завершения фоновых задач
            loop.run_until_complete(asyncio.sleep(0.1))
        except:
            pass
        
        if not loop.is_closed():
            loop.close()
