import asyncio
import logging
import json
import httpx
import os
import sys
import hashlib
import time
import re
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any, Union, Callable, Awaitable

# Добавили BaseMiddleware
from aiogram import Bot, Dispatcher, Router, F, BaseMiddleware
from aiogram.enums import ParseMode, ContentType, ChatMemberStatus
from aiogram.filters import CommandStart, Command, ChatMemberUpdatedFilter
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
    ReplyKeyboardRemove, ForumTopicCreated, ChatMemberUpdated
)
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter

from dotenv import load_dotenv
load_dotenv()

class LicenseMiddleware(BaseMiddleware):
    def __init__(self, bot_instance):
        self.bot_instance = bot_instance
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        # Если лицензия помечена как истекшая
        if getattr(self.bot_instance, 'license_expired', False):
            await event.answer("❌ <b>Лицензия этого бота истекла.</b>\nПожалуйста, продлите её в панели управления.")
            return # Дальше код обработчиков не идет
        return await handler(event, data)

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
        
        # 1. ОБЯЗАТЕЛЬНО: Объявляем переменную сразу, чтобы Middleware её видел
        self.license_expired = False 
        
        self.sb_url = os.getenv("SUPABASE_URL", "").rstrip('/')
        self.sb_key = os.getenv("SUPABASE_KEY", "")
        
        # Авторизационные заголовки для БД
        self.headers = {
            "apikey": self.sb_key,
            "Authorization": f"Bearer {self.sb_key}",
            "Content-Type": "application/json"
        }
        
        # Берем токен из конфига/окружения
        self.bot = Bot(token=self.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher()
        self.router = Router()
        
        self.msg_map = {}
        self.flood_cache = {}
        self.is_running = True
        self.sync_queue = asyncio.Queue()
        self.broadcast_cache = {} 
        
        # Сохраняем ссылку на конфиг для работы register_event
        self.config = config_data 
        
        # Сначала парсим конфиг, чтобы подгрузить настройки
        self.apply_config(config_data)

    async def register_event(self, is_incoming: bool = True):
        """Обновляет статистику в памяти и отправляет в Supabase"""
        try:
            today = datetime.now().strftime("%d.%m")
            
            # 1. Проверяем наличие stats в конфиге
            if not isinstance(self.config.get("stats"), dict):
                self.config["stats"] = {"history": [], "totalMessages": 0}
            
            st = self.config["stats"]
            
            # 2. Обновляем счетчики
            st["totalMessages"] = st.get("totalMessages", 0) + 1
            
            if is_incoming:
                st["incomingToday"] = st.get("incomingToday", 0) + 1
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

            st["history"] = history[-14:] 
            self.config["stats"] = st 

            # 4. Отправка в БД
            async with httpx.AsyncClient() as client:
                resp = await client.patch(
                    f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
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
        #Вынесли логику в отдельный метод, чтобы вызывать её при старте
        try:
            curr_time = int(time.time() * 1000)
            if self.license_expires_at and self.license_expires_at < curr_time:
                # Проверяем через getattr для безопасности или просто по флагу
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
        """Теперь воркер просто крутит логику в цикле"""
        logger.info(f"[*] Мониторинг лицензии для {self.bot_id} запущен")
        while self.is_running:
            await self.license_checker_logic()
            await asyncio.sleep(120)

    def apply_config(self, data: dict):
        """Парсинг конфигурации с приоритетом новых полей"""
        raw_cfg = data.get('config', {}) if isinstance(data.get('config'), dict) else {}
        full_cfg = {**data, **raw_cfg} 
        
        self.vk_group_id = full_cfg.get('vk_group_id') or full_cfg.get('vkGroupId')

        # Читаем Admin ID
        admin_id_raw = full_cfg.get('admin_chat_id') or full_cfg.get('adminChatId')
        self.admin_chat_id = int(str(admin_id_raw).strip()) if admin_id_raw else None

        # Настройки безопасности и тем
        self.settings = full_cfg.get('settings', {})
        self.use_topics = self.settings.get('useTopics', False)
        self.topic_per_req = self.settings.get('topicPerRequest', False)
        
        # Кнопки и триггеры
        self.buttons = full_cfg.get('buttons', [])
        self.triggers = full_cfg.get('triggers', [])
        self.welcome_text = full_cfg.get('welcomeMessage', 'Здравствуйте!')
        
        self.rate_limit = float(self.settings.get('rateLimit', 1.0))
        self.auto_ban_limit = int(self.settings.get('autoBanThreshold', 3))
        self.users_list = full_cfg.get('connectedUsers', [])
        self.license_expires_at = full_cfg.get('license_expires_at', 0)

        # ── ИИ-конфиг (ПОДПРАВЛЕННЫЙ) ──
        ai_cfg = full_cfg.get('ai', {}) or {}
        self.ai_enabled       = ai_cfg.get('enabled', False)
        self.ai_mode          = ai_cfg.get('mode', 'all')      # 'all' | 'button' | 'command' | 'off'
        self.ai_button_name   = ai_cfg.get('buttonName', 'ИИ-ассистент')
        self.ai_system_prompt = ai_cfg.get('systemPrompt', 'Ты полезный ИИ-ассистент.')
        self.ai_max_tokens    = int(ai_cfg.get('maxTokensPerReply', 800))
        self.ai_context_len   = int(ai_cfg.get('contextMessages', 6))
        
        # Модель: если в Timeweb настроен GPT-4o, лучше по умолчанию ставить её
        self.ai_model         = ai_cfg.get('model', 'gpt-4o')

        # Ключ: Берем ТОЛЬКО из .env (игнорируем то, что ввел юзер в панели)
        # [2025-12-23] Remember to take the token from the .env file.
        self.qwen_api_key     = os.getenv('TIMEWEB_API_KEY') or os.getenv('QWEN_API_KEY')

        # URL Агента: Формируем динамически на основе твоего ID агента
        # Если в .env нет ID, используем твой текущий как запасной
        agent_id = os.getenv('TIMEWEB_AGENT_ID', '14ce55f9-dce2-4f2d-ad98-ff2cffe19ca2')
        self.ai_url = f"https://agent.timeweb.cloud/api/v1/cloud-ai/agents/{agent_id}/v1/chat/completions"

        # Контекст диалогов: {user_id: [{"role":..,"content":..}]}
        if not hasattr(self, 'ai_context_cache'):
            self.ai_context_cache: Dict[int, List[dict]] = {}

        # ── Стартовое медиа и инлайн-кнопки ──
        self.welcome_photo    = full_cfg.get('welcomePhoto', '')   # file_id или URL
        self.welcome_inline   = full_cfg.get('welcomeInline', [])  # [{text, url}]

        # ── If/else логика кнопок ──
        # buttons теперь могут содержать children: [{text, response, type, children:[...]}]
        # и triggerFlow: {...}
        
        # Статистика
        incoming_stats = full_cfg.get('stats', {})
        self.stats_data = {
            "totalMessages": incoming_stats.get("totalMessages", 0),
            "incomingToday": incoming_stats.get("incomingToday", 0),
            "outgoingToday": incoming_stats.get("outgoingToday", 0),
            "bannedCount": incoming_stats.get("bannedCount", 0),
            "activeUsers24h": incoming_stats.get("activeUsers24h", 0),
            "history": incoming_stats.get("history", [])
        }

    # ─────────────────────────────────────────────
    # AI / QWEN INTEGRATION
    # ─────────────────────────────────────────────
    async def ai_call(self, user_id: int, user_text: str) -> Optional[str]:
        """Вызов Qwen API через прокси Timeweb с контекстом диалога."""
        # Проверяем наличие ключа и URL
        if not self.qwen_api_key or not self.ai_url:
            logger.error("AI Error: Ключ или URL не настроены в .env")
            return None

        # Добавляем сообщение в контекст
        ctx = self.ai_context_cache.setdefault(user_id, [])
        ctx.append({"role": "user", "content": user_text})
        
        # Обрезаем контекст
        if len(ctx) > self.ai_context_len * 2:
            ctx = ctx[-(self.ai_context_len * 2):]
            self.ai_context_cache[user_id] = ctx

        messages = [{"role": "system", "content": self.ai_system_prompt}] + ctx

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # ИСПОЛЬЗУЕМ self.ai_url вместо жесткой ссылки на aliyuncs
                resp = await client.post(
                    self.ai_url, 
                    headers={
                        "Authorization": f"Bearer {self.qwen_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.ai_model,
                        "messages": messages,
                        "max_tokens": self.ai_max_tokens,
                        "temperature": 0.7
                    }
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    answer = data["choices"][0]["message"]["content"]
                    usage = data.get("usage", {})
                    total = usage.get("total_tokens", 0)
                    
                    ctx.append({"role": "assistant", "content": answer})
                    asyncio.create_task(self._deduct_tokens(user_id, usage, total))
                    return answer
                else:
                    # Теперь ошибка в логах покажет реальный статус (например, если токен пустой)
                    logger.error(f"AI API error {resp.status_code}: {resp.text}")
                    return None
        except Exception as e:
            logger.error(f"AI call error: {e}")
            return None
            
    async def _deduct_tokens(self, user_id: int, usage: dict, total: int):
        """Списывает токены с баланса бота в БД."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                headers = {
                    "apikey": self.sb_key,
                    "Authorization": f"Bearer {self.sb_key}",
                    "Content-Type": "application/json"
                }
                # Атомарное обновление баланса через функцию БД
                await client.post(
                    f"{self.sb_url}/rest/v1/rpc/deduct_ai_tokens",
                    headers=headers,
                    json={"p_bot_id": self.bot_id, "p_amount": total}
                )
                # Лог расхода
                await client.post(
                    f"{self.sb_url}/rest/v1/ai_token_usage_log",
                    headers={**headers, "Prefer": "return=minimal"},
                    json={
                        "bot_id": self.bot_id,
                        "user_id": user_id,
                        "prompt_tokens":   usage.get("prompt_tokens", 0),
                        "response_tokens": usage.get("completion_tokens", 0),
                        "total_tokens":    total,
                        "model":           self.ai_model
                    }
                )
        except Exception as e:
            logger.warning(f"Token deduct error: {e}")

    async def check_ai_tokens(self) -> int:
        """Возвращает остаток токенов бота. 0 если нет баланса."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                headers = {"apikey": self.sb_key, "Authorization": f"Bearer {self.sb_key}"}
                r = await client.get(
                    f"{self.sb_url}/rest/v1/ai_token_balances?bot_id=eq.{self.bot_id}",
                    headers=headers
                )
                if r.status_code == 200 and r.json():
                    return r.json()[0].get("tokens_balance", 0)
        except Exception:
            pass
        return 0

    def clear_ai_context(self, user_id: int):
        """Сбросить контекст диалога с ИИ для пользователя."""
        self.ai_context_cache.pop(user_id, None)

    # ─────────────────────────────────────────────
    # IF/ELSE BUTTON FLOW HELPERS
    # ─────────────────────────────────────────────
    def get_button_by_text(self, text: str, buttons=None) -> Optional[dict]:
        """Рекурсивно ищет кнопку по тексту (включая дочерние)."""
        if buttons is None:
            buttons = self.buttons
        for b in buttons:
            if b.get('text', '').lower() == text.lower():
                return b
            # Рекурсивный поиск в children
            children = b.get('children', [])
            if children:
                found = self.get_button_by_text(text, children)
                if found:
                    return found
        return None

    def build_keyboard_from_buttons(self, buttons: list):
        """Строит ReplyKeyboardMarkup из списка кнопок."""
        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
        active = [b for b in buttons if b.get('text')]
        if not active:
            return ReplyKeyboardRemove()
        rows = []
        for i in range(0, len(active), 2):
            rows.append([KeyboardButton(text=b['text']) for b in active[i:i+2]])
        return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

    def build_inline_from_list(self, buttons: list) -> Optional[InlineKeyboardMarkup]:
        """Строит InlineKeyboardMarkup из [{text, url}]."""
        if not buttons:
            return None
        rows = []
        for i in range(0, len(buttons), 2):
            rows.append([
                InlineKeyboardButton(text=b['text'], url=b.get('url', 'https://t.me'))
                for b in buttons[i:i+2] if b.get('text')
            ])
        return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None

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
                    # Ждем задачу из очереди (например, "sync_state")
                    item = await asyncio.wait_for(self.sync_queue.get(), timeout=1.0)
                    action, payload = item
                    
                    if action == "log_message":
                        await client.post(f"{self.sb_url}/rest/v1/bot_messages", json=payload, headers=headers)
                    
                    elif action == "sync_state":
                        # 1. ПОЛУЧАЕМ актуальный конфиг из базы прямо сейчас
                        # Это нужно, чтобы не затереть изменения из админки
                        res = await client.get(
                            f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}", 
                            headers=headers
                        )
                        
                        if res.status_code == 200 and res.json():
                            remote_data = res.json()[0]
                            remote_config = remote_data.get("config", {})
                            
                            # 2. ОБЪЕДИНЯЕМ данные
                            # Мы оставляем кнопки, триггеры и настройки из БАЗЫ (админки)
                            # Но обновляем статистику и список пользователей из ПАМЯТИ бота
                            new_config = {
                                **remote_config, # Всё что в базе (кнопки, темы, приветствие)
                                "stats": self.stats_data, # Статистика от бота
                                "connectedUsers": self.users_list, # Юзеры от бота
                                "admin_chat_id": self.admin_chat_id,
                                "adminChatId": self.admin_chat_id
                            }

                            # 3. ОТПРАВЛЯЕМ обратно
                            await client.patch(
                                f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}", 
                                json={"config": new_config}, 
                                headers=headers
                            )
                            
                            # 4. ОБНОВЛЯЕМ ПАМЯТЬ БОТА
                            # Чтобы бот сразу узнал о новых кнопках из админки
                            self.apply_config({"config": remote_config})
                    
                    self.sync_queue.task_done()
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Sync Worker Error: {e}")
                    try: self.sync_queue.task_done()
                    except: pass
        
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
        # --- 0. ЗАЩИТА: Проверка прав по adminIds и admin_chat_id ---
        admin_ids = self.config.get("adminIds", [])
        
        is_admin = (
            m.from_user.id in admin_ids or 
            str(m.from_user.id) in map(str, admin_ids) or
            m.from_user.id == self.admin_chat_id
        )

        if not is_admin:
            return False

        # Проверка на наличие текста команды (/ или !)
        if not m.text or not (m.text.startswith("/") or m.text.startswith("!")): 
            return False
        
        cmd_parts = m.text.split()
        command = cmd_parts[0][1:].lower()
        
        # --- 1. ГЛОБАЛЬНЫЕ КОМАНДЫ ---
        
        # 📢 РАССЫЛКА (Broadcast)
        if command == "broadcast":
            # Вариант А: Мгновенная рассылка по реплаю
            if m.reply_to_message:
                target_msg_id = m.reply_to_message.message_id
                sent_count, err_count = 0, 0
                status_msg = await m.reply("🚀 <b>Запускаю полную рассылку...</b>")
                
                all_users = self.config.get("connectedUsers", [])
                
                for user in all_users:
                    try:
                        u_id = int(user['id'])
                        # Теперь НЕ пропускаем админа, чтобы ты видел результат
                        await self.bot.copy_message(
                            chat_id=u_id,
                            from_chat_id=m.chat.id,
                            message_id=target_msg_id
                        )
                        sent_count += 1
                        await asyncio.sleep(0.05) # Защита от Flood Limit
                    except Exception:
                        err_count += 1
                        user["is_active"] = False

                await status_msg.edit_text(
                    f"✅ <b>Рассылка завершена!</b>\n\n"
                    f"👤 Успешно доставлено: {sent_count}\n"
                    f"🚫 Ошибки (блокировки): {err_count}"
                )
                await self.sync_queue.put(("sync_state", None))
                return True

            # Вариант Б: Режим ожидания текста/медиа
            else:
                self.broadcast_cache[m.from_user.id] = "WAITING"
                await m.reply(
                    "📢 <b>Режим рассылки активирован.</b>\n\n"
                    "Пришлите следующим сообщением то, что нужно разослать (текст, фото или видео).\n"
                    "Я использую это для создания рассылки."
                )
                return True

        # 📊 СТАТИСТИКА
        elif command == "stats":
            total_users = len(self.config.get("connectedUsers", []))
            banned = self.stats_data.get("bannedCount", 0)
            await m.reply(
                f"📊 <b>Статистика бота:</b>\n\n"
                f"👥 Всего пользователей: {total_users}\n"
                f"🚫 Заблокировано: {banned}"
            )
            return True

        # --- 2. ПОИСК ЦЕЛЕВОГО ПОЛЬЗОВАТЕЛЯ (для бан/варн) ---
        target_user = None
        users_list = self.config.get("connectedUsers", [])
        
        # Поиск по топику (если пишем в ветке пользователя)
        if m.message_thread_id:
            target_user = next((u for u in users_list if u.get("last_topic_id") == m.message_thread_id), None)
        
        # Поиск по реплаю на пересланное ботом сообщение
        if not target_user and m.reply_to_message:
            uid = self.msg_map.get(m.reply_to_message.message_id)
            if uid:
                target_user = next((u for u in users_list if int(u['id']) == int(uid)), None)
        
        # Если команда требует пользователя, но он не найден — выходим
        if not target_user: 
            # Если это была просто команда админа без контекста пользователя,
            # мы возвращаем False, чтобы другие хендлеры могли сработать
            return False

        uid = target_user['id']
        ban_limit = self.config.get("settings", {}).get("autoBanThreshold", 3)
        
        # --- 3. КОМАНДЫ МОДЕРАЦИИ ---

        # 🚫 БАН
        if command == "ban":
            target_user["is_banned"] = True
            self.stats_data["bannedCount"] = self.stats_data.get("bannedCount", 0) + 1
            await self.sync_queue.put(("sync_state", None))
            try: await self.bot.send_message(uid, "🚫 <b>Доступ к боту ограничен администратором.</b>")
            except: pass
            await m.reply(f"✅ Пользователь <code>{uid}</code> заблокирован.")
            return True
        
        # 🟢 РАЗБАН
        elif command == "unban":
            target_user["is_banned"] = False
            self.stats_data["bannedCount"] = max(0, self.stats_data.get("bannedCount", 1) - 1)
            await self.sync_queue.put(("sync_state", None))
            try: await self.bot.send_message(uid, "✅ <b>Ваш доступ к боту восстановлен администратором.</b>")
            except: pass
            await m.reply(f"✅ Пользователь <code>{uid}</code> разблокирован.")
            return True

        # ⚠️ ВАРН (Предупреждение)
        elif command == "warn":
            target_user["warns"] = target_user.get("warns", 0) + 1
            await self.sync_queue.put(("sync_state", None))
            
            if target_user["warns"] >= ban_limit:
                target_user["is_banned"] = True
                self.stats_data["bannedCount"] = self.stats_data.get("bannedCount", 0) + 1
                try: await self.bot.send_message(uid, f"🚫 <b>Авто-бан:</b> Лимит предупреждений ({target_user['warns']}/{ban_limit}) исчерпан.")
                except: pass
                await m.reply(f"🚨 <b>АВТО-БАН!</b>\nЮзер: <code>{uid}</code>\nВарнов: {target_user['warns']}/{ban_limit}")
            else:
                try: await self.bot.send_message(uid, f"⚠️ <b>Предупреждение!</b> ({target_user['warns']}/{ban_limit})")
                except: pass
                await m.reply(f"⚠️ Варн выдан пользователю <code>{uid}</code>. Всего: {target_user['warns']}/{ban_limit}")
            return True
            
        # 🔄 СНЯТЬ ВАРН
        elif command == "unwarn" or command == "unwarn":
            target_user["warns"] = max(0, target_user.get("warns", 0) - 1)
            await self.sync_queue.put(("sync_state", None))
            await m.reply(f"✅ Предупреждение снято. Текущее кол-во варнов у <code>{uid}</code>: {target_user['warns']}")
            return True
            
        return False
        
    async def core_handlers_setup(self):
        # 0. Мидлварь для проверки лицензии
        self.router.message.middleware(LicenseMiddleware(self))

        # 1. Обработка блокировки бота пользователем
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
                    try: 
                        await self.bot.send_message(self.admin_chat_id, text, message_thread_id=thread_id)
                    except: 
                        pass
            logger.info(f"[!] Пользователь {user_id} заблокировал бота.")

        # 2. Команда /start
        @self.router.message(CommandStart())
        async def handle_start_msg(m: Message):
            user, is_new = await self.get_user_state(m)
            if user.get("is_banned"):
                return

            reply_kb  = self.get_main_keyboard()
            inline_kb = self.build_inline_from_list(self.welcome_inline)

            try:
                if self.welcome_photo:
                    await m.answer_photo(
                        photo=self.welcome_photo,
                        caption=self.welcome_text,
                        reply_markup=inline_kb if inline_kb else reply_kb
                    )
                else:
                    await m.answer(
                        text=self.welcome_text, 
                        reply_markup=inline_kb if inline_kb else reply_kb
                    )
            except Exception as _pe:
                logger.warning(f"start msg error: {_pe}")
                await m.answer(text=self.welcome_text, reply_markup=reply_kb)

            await self.log_and_update(user['id'], m.from_user.full_name, "/start")

        # 2.1 Обработка нажатия инлайн-кнопок (Закрыть ИИ)
        @self.router.callback_query(F.data == "ai_close")
        async def handle_ai_close(call: CallbackQuery):
            user, _ = await self.get_user_state(call.message)
            user.pop('_ai_session', None)
            await call.message.answer("Диалог с ИИ завершен.", reply_markup=self.get_main_keyboard())
            await call.answer()

        # 3. Ввод от админа (Команды и Ответы)
        @self.router.message(F.chat.id == self.admin_chat_id)
        async def admin_input_router(m: Message):
            if m.text and (m.text.startswith("/") or m.text.startswith("!")):
                if await self.admin_control_logic(m):
                    return

            target_id = None
            if m.message_thread_id:
                u = next((u for u in self.users_list if u.get("last_topic_id") == m.message_thread_id), None)
                if u: target_id = u["id"]
            
            if not target_id and m.reply_to_message:
                target_id = self.msg_map.get(m.reply_to_message.message_id)
            
            if target_id:
                try:
                    await self.bot.copy_message(target_id, m.chat.id, m.message_id)
                    await self.log_and_update(target_id, "Admin", m.text or "[Медиа]", is_admin=True)
                except TelegramForbiddenError:
                    await m.reply("Ошибка: Пользователь заблокировал бота.")
                except Exception as e:
                    await m.reply(f"Ошибка: {e}")

        # 4. Сообщения от обычных пользователей
        @self.router.message()
        async def user_input_router(m: Message):
            if self.admin_chat_id and m.chat.id == self.admin_chat_id:
                return

            user, is_new = await self.get_user_state(m)
            if user.get("is_banned") or await self.check_antispam(user['id']):
                return

            uid = user['id']

            if m.text:
                clean_text = m.text.strip()
                clean_lower = clean_text.lower()
                ai_btn_text = self.config.get('ai_button_text', 'ИИ-ассистент')

                # ── 1. Кнопка "Назад" (универсальный сброс) ──
                if clean_text == "⬅️ Назад":
                    user.pop('_ai_session', None)
                    await m.answer("Главное меню:", reply_markup=self.get_main_keyboard())
                    return

                # ── 2. Активация ИИ (команды или кнопка) ──
                if clean_lower in ('/ai', '/gpt', '/nn') or clean_text == ai_btn_text:
                    if self.ai_enabled and self.ai_mode in ('command', 'all', 'button'):
                        bal = await self.check_ai_tokens()
                        if bal <= 0:
                            await m.answer("AI-токены закончились. Обратитесь к администратору.")
                            return
                        user['_ai_session'] = True
                        close_kb = InlineKeyboardMarkup(inline_keyboard=[[
                            InlineKeyboardButton(text="Закрыть диалог с ИИ", callback_data="ai_close")
                        ]])
                        await m.answer("ИИ-ассистент активирован. Задайте вопрос.", reply_markup=close_kb)
                    else:
                        await m.answer("ИИ-ассистент не подключён.")
                    return

                # ── 3. Сброс ИИ через команду ──
                if clean_lower == '/reset_ai':
                    self.clear_ai_context(uid)
                    user.pop('_ai_session', None)
                    await m.answer("Контекст и сессия ИИ сброшены.", reply_markup=self.get_main_keyboard())
                    return

                # ── 4. Логика кнопок меню (children) ──
                matched_btn = self.get_button_by_text(clean_text)
                if matched_btn:
                    user.pop('_ai_session', None) # Выключаем ИИ при нажатии кнопки меню
                    
                    children = matched_btn.get('children', [])
                    if children:
                        # Подменю + кнопка Назад
                        child_kb = self.build_keyboard_from_buttons(children + [{"text": "⬅️ Назад"}])
                        await m.answer(matched_btn.get('response') or "Выберите вариант:", reply_markup=child_kb)
                    else:
                        # Обычная кнопка
                        if matched_btn.get('type') == 'request':
                            await self.forward_to_admin(m, user, btn_text=matched_btn['text'])
                        
                        resp = matched_btn.get('response', 'Принято!')
                        await m.answer(resp, reply_markup=self.get_main_keyboard())
                    
                    await self.log_and_update(uid, m.from_user.full_name, f"КНОПКА: {matched_btn['text']}")
                    return

                # ── 5. Обработка ИИ (если сессия активна) ──
                if user.get('_ai_session'):
                    bal = await self.check_ai_tokens()
                    if bal <= 0:
                        user.pop('_ai_session', None)
                        await m.answer("Токены кончились. Режим ИИ выключен.", reply_markup=self.get_main_keyboard())
                        return
                    
                    if hasattr(self, 'handle_ai_request'):
                        await self.handle_ai_request(m, user)
                    return

            # ── 6. Если ничего не подошло — шлем админу ──
            await self.forward_to_admin(m, user)

                # ── ТРИГГЕРЫ ──
                triggered = False
                for trig in self.triggers:
                    if trig.get('keyword') and trig['keyword'].lower() in clean_lower:
                        resp_text = trig.get('response', '')
                        # Если у триггера есть children-кнопки
                        trig_children = trig.get('children', [])
                        if trig_children:
                            child_kb = self.build_keyboard_from_buttons(trig_children)
                            await m.answer(resp_text or "Выберите:", reply_markup=child_kb)
                        else:
                            await m.answer(resp_text)
                        await self.log_and_update(uid, m.from_user.full_name, f"ТРИГГЕР: {trig['keyword']}")
                        triggered = True
                        break

                if triggered:
                    return

                # ── ИИ-АССИСТЕНТ ──
                if self.ai_enabled and self.ai_mode == 'all':
                    # Проверяем баланс токенов
                    bal = await self.check_ai_tokens()
                    if bal > 0:
                        thinking = await m.answer("🤖 Думаю...")
                        answer = await self.ai_call(uid, clean_text)
                        if answer:
                            await thinking.delete()
                            await m.answer(answer)
                            await self.log_and_update(uid, m.from_user.full_name, f"AI: {clean_text[:50]}")
                            return
                        else:
                            await thinking.delete()
                    else:
                        await m.answer("⚠️ Лимит AI-токенов исчерпан. Обратитесь к администратору.")
                        return

            # ── КНОПКА ИИ — нажали кнопку «ИИ-ассистент» из клавиатуры ──
            if m.text and m.text.strip() == self.ai_button_name:
                if self.ai_enabled and self.ai_mode == 'button':
                    bal = await self.check_ai_tokens()
                    if bal <= 0:
                        await m.answer("⚠️ AI-токены закончились. Обратитесь к администратору.")
                        return
                    user['_ai_session'] = True
                    close_kb = InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="✖ Закрыть диалог с ИИ", callback_data="ai_close")
                    ]])
                    await m.answer(
                        "🤖 <b>ИИ-ассистент активирован.</b>\nЗадайте вопрос:",
                        reply_markup=close_kb
                    )
                    return

            # ── АКТИВНАЯ AI-СЕССИЯ — обрабатываем любое сообщение ──
            if user.get('_ai_session') and self.ai_enabled and m.text:
                bal = await self.check_ai_tokens()
                if bal <= 0:
                    user.pop('_ai_session', None)
                    await m.answer("⚠️ AI-токены закончились. Сессия закрыта.", reply_markup=self.get_main_keyboard())
                    return
                close_kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="✖ Закрыть диалог с ИИ", callback_data="ai_close")
                ]])
                thinking = await m.answer("🤖 Думаю...")
                answer_text = await self.ai_call(uid, m.text)
                await thinking.delete()
                if answer_text:
                    await m.answer(answer_text, reply_markup=close_kb)
                    await self.log_and_update(uid, m.from_user.full_name, f"AI: {m.text[:50]}")
                else:
                    await m.answer("⚠️ Ошибка ИИ, попробуйте ещё раз.", reply_markup=close_kb)
                return

            # ── Пересылка сообщения администратору ──
            await self.forward_to_admin(m, user, is_first=is_new)
            await self.log_and_update(uid, m.from_user.full_name, m.text or "[Медиа]")

        # 5. Закрытие AI-сессии (inline callback «✖ Закрыть диалог с ИИ»)
        @self.router.callback_query(lambda c: c.data == 'ai_close')
        async def on_ai_close(cb: CallbackQuery):
            uid_cb = cb.from_user.id
            user_cb = next((u for u in self.users_list if u['id'] == uid_cb), None)
            if user_cb:
                user_cb.pop('_ai_session', None)
                self.clear_ai_context(uid_cb)
            try:
                await cb.message.delete()
            except Exception:
                pass
            await cb.answer("Диалог с ИИ закрыт.")
            try:
                await self.bot.send_message(
                    uid_cb,
                    "✅ Диалог с ИИ завершён.",
                    reply_markup=self.get_main_keyboard()
                )
            except Exception:
                pass

    def get_main_keyboard(self):
        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
        active_btns = [b for b in self.buttons if b.get('text')]
        # Добавляем AI-кнопку если режим 'button'
        if self.ai_enabled and self.ai_mode == 'button' and self.ai_button_name:
            active_btns = active_btns + [{'text': self.ai_button_name}]
        if not active_btns: return ReplyKeyboardRemove()
        keyboard_rows = []
        for i in range(0, len(active_btns), 2):
            keyboard_rows.append([KeyboardButton(text=b['text']) for b in active_btns[i:i+2]])
        return ReplyKeyboardMarkup(keyboard=keyboard_rows, resize_keyboard=True)

    async def run_instance(self):
        # 1. Принудительно ждем первой синхронизации базы и проверки лицензии
        # Вместо create_task вызываем их напрямую через await ОДИН раз
        logger.info(f"[*] Бот {self.bot_id} проверяет данные перед запуском...")
        
        try:
            # Выполняем ОДИН цикл проверки лицензии и базы ДО запуска поллинга
            await self.license_checker_logic() # Проверка лицензии
            await self.sync_database_logic()   # Загрузка настроек и кнопок
        except Exception as e:
            logger.error(f"Ошибка при первичной загрузке данных: {e}")

        # 2. Теперь запускаем их как фоновые задачи для обновления в будущем
        asyncio.create_task(self.database_sync_worker())
        asyncio.create_task(self.daily_stats_rotator())
        asyncio.create_task(self.license_checker())
        
        # 3. Настраиваем хендлеры и роутеры
        await self.core_handlers_setup()
        self.dp.include_router(self.router)
        
        logger.info(f"[*] Бот {self.bot_id} готов к работе. Лицензия: {'Истекла' if self.license_expired else 'ОК'}")
        
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
