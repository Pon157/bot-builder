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
        
        # Username в ВК редко используется как ID, но добавим, если есть domain
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

    # Убираем HTML теги, так как ВК их специфично понимает, оставим чистый текст
    # или минимальную разметку, если нужно.
    return f"{status_line}\n{user_info}\n⬇️⬇️⬇️"

# --- MIDDLEWARE ---
class LicenseMiddleware(BaseMiddleware[Message]):
    async def pre(self):
        # Доступ к инстансу через ctx_storage или атрибут бота,
        # но проще передать инстанс при инициализации, если vkbottle это позволяет.
        # Здесь мы используем глобальный доступ к инстансу через self.event.ctx_storage,
        # но надежнее будет проверить атрибут у самого объекта (хак).
        
        bot_instance = getattr(self.event.ctx_api, "bot_instance_ref", None)
        
        if bot_instance and getattr(bot_instance, 'license_expired', False):
            await self.event.answer("❌ Лицензия этого бота истекла.\nПожалуйста, продлите её в панели управления.")
            self.stop("License expired") # Останавливаем обработку

    async def post(self):
        pass

# --- ОСНОВНОЙ КЛАСС БОТА ---
class BotInstance:
    def __init__(self, config_data: dict):
        self.bot_id = config_data.get('id')
        self.token = config_data.get('token')
        
        self.license_expired = False 
        
        self.sb_url = os.getenv("SUPABASE_URL", "").rstrip('/')
        self.sb_key = os.getenv("SUPABASE_KEY", "")
        
        # Инициализация бота VK
        self.bot = Bot(token=self.token)
        # Сохраняем ссылку на себя внутри API объекта, чтобы достать в Middleware
        self.bot.api.bot_instance_ref = self
        
        self.msg_map = {} # map: admin_msg_id -> user_id
        self.flood_cache = {}
        self.is_running = True
        self.sync_queue = asyncio.Queue()
        
        self.apply_config(config_data)

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
        raw_cfg = data.get('config', {}) if isinstance(data.get('config'), dict) else {}
        full_cfg = {**data, **raw_cfg} 
        
        try:
            admin_id_raw = full_cfg.get('adminChatId')
            # В ВК ID пользователя - это int.
            self.admin_chat_id = int(str(admin_id_raw).strip()) if admin_id_raw else None
        except ValueError:
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
        async with httpx.AsyncClient(timeout=10.0) as client:
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
            # В ВК "пересылка" делается через forward_messages=[id]
            # Мы отправляем сообщение админу, прикрепляя оригинальное сообщение
            sent_msg_id = await self.bot.api.messages.send(
                peer_id=self.admin_chat_id,
                message=header_text,
                forward_messages=[m.id],
                random_id=0
            )
            
            # Сохраняем маппинг: ID сообщения у админа -> ID пользователя
            # Это нужно, чтобы админ мог ответить реплаем
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
                
                # Обработка START
                if clean_text == "start" or clean_text == "/start":
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
        logger.info(f"[*] Бот VK {self.bot_id} запускается...")
        
        try:
            await self.license_checker_logic() 
            # В VK не нужно отдельно грузить базу перед пуллингом так жестко, но оставим логику
        except Exception as e:
            logger.error(f"Ошибка Init: {e}")

        asyncio.create_task(self.database_sync_worker())
        asyncio.create_task(self.daily_stats_rotator())
        asyncio.create_task(self.license_checker())
        
        await self.core_handlers_setup()
        
        logger.info(f"[*] Бот VK {self.bot_id} готов. AdminID: {self.admin_chat_id}")
        
        try: 
            # vkbottle запускает свой луп, но нам нужно встроиться в существующий asyncio.run
            await self.bot.run_polling()
        except Exception as e:
             logger.error(f"Polling Error: {e}")
        finally:
            self.is_running = False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 bot_core_vk.py <config_path>")
        sys.exit(1)
        
    async def main():
        cfg_path = sys.argv[1]
        try:
            with open(cfg_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            instance = BotInstance(config)
            await instance.run_instance()
            
        except Exception as e:
            logger.error(f"FATAL ERROR: {e}")

    asyncio.run(main())
