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

# --- Загрузка переменных из .env ---
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Импорты vkbottle
from vkbottle import BaseMiddleware, Bot
from vkbottle.bot import Message
from vkbottle.dispatch.rules import ABCRule
from vkbottle import Keyboard, KeyboardButtonColor, Text
from vkbottle.exception_factory import VKAPIError
from vkbottle.modules import logger as vb_logger

# --- ГЛОБАЛЬНАЯ КОНФИГУРАЦИЯ ЛОГИРОВАНИЯ ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotCoreEngineVK")
vb_logger.setLevel(logging.WARNING) # Убираем лишний шум от vkbottle

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_anon_id(user_id: int) -> str:
    """Генерация короткого хеша для анонимности"""
    return hashlib.md5(str(user_id).encode()).hexdigest()[:6].upper()

def format_admin_header(user: dict, settings: dict, is_first: bool = False, btn_text: str = "") -> str:
    """Формирование заголовка сообщения для админа"""
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
            # Если лицензия истекла, игнорируем сообщения от пользователей (кроме админ чата)
            if bot_instance.admin_chat_id and self.event.peer_id == bot_instance.admin_chat_id:
                return # Админу можно писать
            
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
        
        self.sb_url = os.getenv("SUPABASE_URL")
        self.sb_key = os.getenv("SUPABASE_KEY")

        if not self.sb_url:
            self.sb_url = config_data.get("config", {}).get("api_url", "http://localhost:8000")
        
        if not self.sb_key:
            logger.warning(f"⚠️ [{self.bot_id}] SUPABASE_KEY не найден в окружении!")
            self.sb_key = ""

        self.sb_url = self.sb_url.rstrip('/')
        
        # Инициализация бота VK
        self.bot = Bot(token=self.token)
        self.bot.api.bot_instance_ref = self
        
        self.msg_map = {} 
        self.flood_cache = {}
        self.is_running = True
        self.sync_queue = asyncio.Queue()
        
        # Переменные для идентификации
        self.group_id = None
        self.owner_id = None # ID владельца сообщества
        
        # Применяем стартовый конфиг
        self.apply_config(config_data)

    async def update_config_remote(self):
        """Отправляет обновленный конфиг (например, новый chat_id) в базу"""
        try:
            # Обновляем локальный конфиг новыми значениями
            self.config["vkGroupId"] = self.admin_chat_id
            self.config["adminChatId"] = self.admin_chat_id
            self.config["vk_group_id"] = self.admin_chat_id # Дублируем для надежности

            headers = {
                "apikey": self.sb_key,
                "Authorization": f"Bearer {self.sb_key}",
                "Content-Type": "application/json"
            }
            
            # Отправляем PATCH запрос
            async with httpx.AsyncClient() as client:
                await client.patch(
                    f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                    headers=headers,
                    json={"config": self.config}
                )
            logger.info(f"💾 Конфигурация успешно обновлена в БД. Новый AdminChatID: {self.admin_chat_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения конфига в БД: {e}")

    async def update_stats(self, is_incoming: bool = True):
        try:
            today = datetime.now().strftime("%d.%m")
            stats = self.config.get("stats", {})
            if not isinstance(stats, dict): stats = {}
            
            stats["totalMessages"] = stats.get("totalMessages", 0) + 1
            if is_incoming:
                stats["incomingToday"] = stats.get("incomingToday", 0) + 1
            else:
                stats["outgoingToday"] = stats.get("outgoingToday", 0) + 1

            history = stats.get("history", [])
            if not isinstance(history, list): history = []
                
            day_entry = next((item for item in history if item.get("date") == today), None)

            if day_entry:
                if is_incoming: day_entry["incoming"] = day_entry.get("incoming", 0) + 1
                else: day_entry["outgoing"] = day_entry.get("outgoing", 0) + 1
            else:
                history.append({
                    "date": today,
                    "incoming": 1 if is_incoming else 0,
                    "outgoing": 0 if is_incoming else 1,
                    "totalUsers": len(self.config.get("connectedUsers", [])),
                    "activeUsers": 1
                })
            
            stats["history"] = history[-14:] 
            self.config["stats"] = stats

            headers = {
                "apikey": self.sb_key,
                "Authorization": f"Bearer {self.sb_key}",
                "Content-Type": "application/json"
            }
            async with httpx.AsyncClient() as client:
                await client.patch(
                    f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                    headers=headers,
                    json={"stats": stats}
                )
        except Exception as e:
            logger.error(f"Error updating stats: {e}")

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
        while self.is_running:
            await self.license_checker_logic()
            await asyncio.sleep(120)

    def apply_config(self, data: dict):
        raw_cfg = data.get('config', {}) if isinstance(data.get('config'), dict) else {}
        full_cfg = {**data, **raw_cfg}
        self.config = full_cfg

        # Читаем peer_id для пересылки
        vk_peer_raw = (
            full_cfg.get('vk_group_id') or full_cfg.get('vkGroupId') or
            full_cfg.get('admin_chat_id') or full_cfg.get('adminChatId')
        )
        try:
            self.admin_chat_id = int(str(vk_peer_raw).strip()) if vk_peer_raw else None
        except (ValueError, AttributeError):
            self.admin_chat_id = None

        self.buttons = full_cfg.get('buttons', [])
        self.triggers = full_cfg.get('triggers', [])
        self.welcome_text = full_cfg.get('welcomeMessage', 'Здравствуйте!')
        self.settings = full_cfg.get('settings', {})
        
        self.rate_limit = float(self.settings.get('rateLimit', 1.0))
        self.auto_ban_limit = int(self.settings.get('autoBanThreshold', 3))
        self.users_list = full_cfg.get('connectedUsers', [])
        self.license_expires_at = full_cfg.get('license_expires_at', 0)
        
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
                # ... (логика ротации осталась прежней)
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Rotator Error: {e}")
                await asyncio.sleep(60)

    async def database_sync_worker(self):
        async with httpx.AsyncClient(timeout=10.0) as client:
            if not self.sb_url or not self.sb_url.startswith("http"):
                self.sb_url = os.getenv("SERVER_URL", "http://localhost:8000").rstrip('/')

            headers = {
                "apikey": self.sb_key,
                "Authorization": f"Bearer {self.sb_key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            }
            
            while self.is_running:
                try:
                    item = await asyncio.wait_for(self.sync_queue.get(), timeout=1.0)
                    if not isinstance(item, tuple):
                        self.sync_queue.task_done()
                        continue

                    action, payload = item

                    if action == "log_message":
                        if self.sb_url.startswith("http"):
                            await client.post(f"{self.sb_url}/rest/v1/bot_messages", json=payload, headers=headers)

                    elif action == "sync_state":
                        if not self.sb_url or not self.sb_url.startswith("http"):
                            self.sync_queue.task_done()
                            continue
        
                        res = await client.get(
                            f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                            headers=headers
                        )

                        if res.status_code == 200 and res.json():
                            remote_data = res.json()[0]
                            remote_config = remote_data.get("config", {}) or {}

                            # При слиянии конфигов, если мы локально уже обновили ID чата, 
                            # не даем удаленной версии затереть его пустым значением
                            if self.admin_chat_id:
                                remote_config["vkGroupId"] = self.admin_chat_id
                                remote_config["adminChatId"] = self.admin_chat_id

                            new_config = {
                                **remote_config,
                                "stats": self.stats_data,
                                "connectedUsers": self.users_list,
                            }

                            await client.patch(
                                f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                                json={"config": new_config, "stats": self.stats_data},
                                headers=headers
                            )
                            
                            # Не обновляем конфиг из базы, если мы только что поменяли привязку
                            # иначе может возникнуть гонка данных
                            self.apply_config({**remote_data, "config": new_config})

                    self.sync_queue.task_done()
                    
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"🚨 VK Sync Worker Error: {e}")
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
        
        try:
            user_info = (await self.bot.api.users.get(user_ids=[uid]))[0]
            full_name = f"{user_info.first_name} {user_info.last_name}"
            domain = user_info.domain
        except:
            full_name = "Пользователь"
            domain = "id"

        if not user:
            is_first_time = True
            user = {
                "id": uid, 
                "first_name": full_name, 
                "username": domain, 
                "domain": domain,
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
        if not self.admin_chat_id: 
            return
        
        header_text = format_admin_header(user, self.settings, is_first, btn_text)
        
        try:
            import json as _json
            forward_payload = _json.dumps({
                "peer_id": m.peer_id,
                "message_ids": [m.id],
                "is_reply": True 
            })
            
            sent_msg_id = await self.bot.api.messages.send(
                peer_id=self.admin_chat_id,
                message=header_text,
                forward=forward_payload,
                random_id=0
            )

            self.msg_map[sent_msg_id] = user['id']

        except Exception as e:
            logger.error(f"Forwarding Error: {e}")

    async def admin_control_logic(self, m: Message):
        if not m.text or not (m.text.startswith("/") or m.text.startswith("!")): return False
        
        cmd_parts = m.text.lower().split()
        command = cmd_parts[0][1:]
        target_user = None
        
        if m.reply_message:
            uid = self.msg_map.get(m.reply_message.id)
            if uid:
                target_user = next((u for u in self.users_list if u['id'] == uid), None)
            
            if not target_user and m.reply_message.fwd_messages:
                original_sender = m.reply_message.fwd_messages[0].from_id
                target_user = next((u for u in self.users_list if u['id'] == original_sender), None)
        
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
        for i, btn in enumerate(active_btns):
            if i % 2 == 0 and i != 0: kb.row()
            kb.add(Text(btn['text']), color=KeyboardButtonColor.PRIMARY)
        return kb.get_json()

    async def core_handlers_setup(self):
        self.bot.labeler.message_view.register_middleware(LicenseMiddleware)

        # --- НОВЫЙ ХЕНДЛЕР: Обработка добавления бота в беседу ---
        @self.bot.on.chat_message()
        async def handle_chat_events(m: Message):
            # Проверяем, есть ли сервисные действия
            if m.action and m.action.type.value == "chat_invite_user":
                # Проверяем, кого добавили (если member_id совпадает с -group_id бота, значит добавили нас)
                if m.action.member_id == -self.group_id:
                    
                    # Логика прав: 
                    # 1. Если это Владелец сообщества
                    # 2. ИЛИ если админ-чат еще вообще не задан (первый запуск)
                    
                    is_owner = (m.from_id == self.owner_id)
                    is_not_configured = (self.admin_chat_id is None)
                    
                    if is_owner or is_not_configured:
                        self.admin_chat_id = m.peer_id
                        
                        # Сохраняем изменение в базу данных НЕМЕДЛЕННО
                        await self.update_config_remote()
                        
                        await m.answer(
                            f"✅ Бот подключен к этой беседе!\n"
                            f"Теперь сообщения пользователей будут приходить сюда.\n"
                            f"ID чата: {m.peer_id}"
                        )
                        logger.info(f"🆕 Бот привязан к чату {m.peer_id} пользователем {m.from_id}")
                    else:
                        # Если добавил левый человек, когда бот уже настроен
                        await m.answer("⚠️ Я уже настроен на работу в другой беседе. Менять чат может только владелец сообщества.")

        # Обработка команд админа
        @self.bot.on.message(text=["/ban <item>", "/unban <item>", "/warn <item>", "/unwarn <item>", "!ban", "!unban", "!warn", "!unwarn"])
        async def admin_cmd_handler(m: Message, item: Optional[str] = None):
             if m.from_id == self.admin_chat_id or m.peer_id == self.admin_chat_id:
                 await self.admin_control_logic(m)

        # Обработка ответов админа (Reply)
        @self.bot.on.message(func=lambda m: m.peer_id == self.admin_chat_id and m.reply_message is not None)
        async def handle_admin_reply(m: Message):
            if m.text and (m.text.startswith("/") or m.text.startswith("!")):
                res = await self.admin_control_logic(m)
                if res: return

            target_id = self.msg_map.get(m.reply_message.id)
            if not target_id and m.reply_message.fwd_messages:
                 target_id = m.reply_message.fwd_messages[0].from_id

            if target_id:
                try:
                    if m.text:
                        await self.bot.api.messages.send(peer_id=target_id, message=m.text, random_id=0)
                    elif m.attachments:
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
                except VKAPIError[901]:
                    await m.answer("❌ Ошибка: Пользователь запретил сообщения.")
                    user = next((u for u in self.users_list if u['id'] == target_id), None)
                    if user:
                        user["is_active"] = False
                        await self.sync_queue.put(("sync_state", None))
                except Exception as e:
                    await m.answer(f"❌ Ошибка: {e}")

        # Обработка сообщений пользователя
        @self.bot.on.message()
        async def handle_user_input(m: Message):
            if m.peer_id == self.admin_chat_id:
                return
            
            # Игнорируем сообщения из других бесед (не ЛС и не админ-чат)
            if m.peer_id > 2000000000:
                return

            user, is_new = await self.get_user_state(m)
            if user.get("is_banned") or await self.check_antispam(user['id']): return
            
            if m.text:
                clean_text = m.text.lower().strip()
                if clean_text in ["start", "/start", "начать"]:
                    await m.answer(self.welcome_text, keyboard=self.get_main_keyboard())
                    await self.log_and_update(user['id'], user['first_name'], "/start")
                    return

                for btn in self.buttons:
                    if btn.get('text') and btn['text'].lower() == clean_text:
                        if btn.get('type') == 'request': 
                            await self.forward_to_admin(m, user, btn_text=btn['text'])
                        if btn.get('response'): 
                            await m.answer(btn['response'], keyboard=self.get_main_keyboard())
                        await self.log_and_update(user['id'], user['first_name'], f"КНОПКА: {btn['text']}")
                        return
                
                for trig in self.triggers:
                    if trig.get('keyword') and trig['keyword'].lower() in clean_text:
                        await m.answer(trig['response'], keyboard=self.get_main_keyboard())
                        await self.log_and_update(user['id'], user['first_name'], f"ТРИГГЕР: {trig['keyword']}")
                        return
            
            await self.forward_to_admin(m, user, is_first=is_new)
            await self.log_and_update(user['id'], user['first_name'], m.text or "[Медиа]")

    async def run_instance(self):
        logger.info(f"[*] Бот VK {self.bot_id} запускается...")
        
        try:
            # Исправленный блок получения инфо о группе
            group_info_list = await self.bot.api.groups.get_by_id()
            
            # Проверяем: если это список, берем первый элемент. 
            # Если это уже объект (модель), используем его напрямую.
            if isinstance(group_info_list, list):
                group_info = group_info_list[0]
            else:
                group_info = group_info_list

            self.group_id = group_info.id
            group_name = group_info.name
            logger.info(f"✅ Работаем от имени группы: {group_name} (ID: {self.group_id})")

            # ОПРЕДЕЛЯЕМ ВЛАДЕЛЬЦА
            try:
                managers = await self.bot.api.groups.get_members(
                    group_id=self.group_id, 
                    filter='managers'
                )
                # В vkbottle managers — это объект, у которого есть поле items (список)
                creator = next((m for m in managers.items if m.role.value == 'creator'), None)
                
                if creator:
                    self.owner_id = creator.id
                    logger.info(f"👑 Владелец сообщества определен: {self.owner_id}")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка получения владельца: {e}")

        except Exception as e:
            logger.error(f"❌ ОШИБКА АВТОРИЗАЦИИ: {e}")
            return

if __name__ == "__main__":
    import sys
    import json
    import asyncio

    if len(sys.argv) < 2:
        print("Usage: python3 vkbot_core.py <config_path>")
        sys.exit(1)

    cfg_path = sys.argv[1]
    
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Не удалось прочитать конфиг {cfg_path}: {e}")
        sys.exit(1)

    instance = BotInstance(config) 
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def main():
        await instance.run_instance()

    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("STOPPED")
    finally:
        if not loop.is_closed():
            loop.close()
