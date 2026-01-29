
import asyncio
import logging
import json
import os
import time
import re
import uuid
import secrets
import sys
import random
import io
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any, Union

from fastapi import FastAPI, HTTPException, Header, Request, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ParseMode, ContentType
from aiogram.filters import CommandStart, Command, MagicData
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
    ForumTopicCreated
)
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import (
    TelegramForbiddenError, TelegramBadRequest, 
    TelegramRetryAfter, TelegramNetworkError
)

import uvicorn
from email_service import EmailService

# --- CONFIGURATION & LOGGING ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "database.json")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotEngine.Core")

# --- DATA MODELS (PYDANTIC) ---
class AuthRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    code: str

class BotSettings(BaseModel):
    useTopics: bool = False
    topicPerRequest: bool = False
    forwardToAdmin: bool = True
    antiSpam: bool = True
    rateLimit: int = 15
    autoBanThreshold: int = 0

class BotButton(BaseModel):
    text: str
    response: str
    type: str = "message"
    adminTemplate: Optional[str] = None

class BotTrigger(BaseModel):
    keyword: str
    response: str

class BotSaveRequest(BaseModel):
    id: str
    ownerId: str
    name: str
    token: str
    adminChatId: Optional[str] = ""
    welcomeMessage: str = "Привет!"
    buttons: List[BotButton] = []
    triggers: List[BotTrigger] = []
    settings: BotSettings = BotSettings()
    connectedUsers: List[Any] = []

class BroadcastRequest(BaseModel):
    botIds: List[str]
    message: str

class LicenseActivateRequest(BaseModel):
    botId: str
    key: str

# --- DATABASE ENGINE ---
db_content = {
    "users": [], 
    "bots": [], 
    "issued_keys": [], 
    "verification_codes": {},
    "system_stats": {"total_runs": 0, "api_calls": 0}
}

def save_db():
    try:
        temp_db = db_content.copy()
        # Чистим временные данные перед сохранением
        temp_db["verification_codes"] = {
            k: v for k, v in db_content["verification_codes"].items() 
            if v["expires"] > time.time()
        }
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(temp_db, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save database: {e}")

def load_db():
    global db_content
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                db_content.update(data)
                logger.info(f"Database loaded: {len(db_content['users'])} users, {len(db_content['bots'])} bots")
        except Exception as e:
            logger.error(f"Failed to load database: {e}")

# --- BOT RUNTIME MANAGER ---
active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}

def is_bot_active(bot_id: str) -> bool:
    return bot_id in active_tasks and not active_tasks[bot_id].done()

def check_license(bot_cfg: dict) -> bool:
    expires = bot_cfg.get("licenseExpiresAt", 0)
    return int(expires) > int(time.time() * 1000)

def format_log_entry(msg: str, level: str = "info"):
    return {
        "id": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "type": level,
        "text": msg
    }

# --- AIOGRAM WORKER ---
async def start_bot_worker(bot_id: str, token: str):
    logger.info(f"Starting worker for bot {bot_id}")
    session = AiohttpSession()
    bot = Bot(token=token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    active_bots[bot_id] = bot
    dp = Dispatcher()
    
    # Резолвим конфиг из "БД"
    def get_config():
        return next((b for b in db_content["bots"] if b["id"] == bot_id), None)

    # Хелпер для логов
    def log_event(text: str, level: str = "info"):
        cfg = get_config()
        if cfg:
            if "logs" not in cfg: cfg["logs"] = []
            cfg["logs"].insert(0, format_log_entry(text, level))
            cfg["logs"] = cfg["logs"][:100]

    # --- HANDLERS ---
    @dp.message(CommandStart())
    async def handle_start(m: Message):
        cfg = get_config()
        if not cfg or not check_license(cfg): return
        
        # Регистрация/Обновление пользователя
        if "connectedUsers" not in cfg: cfg["connectedUsers"] = []
        user = next((u for u in cfg["connectedUsers"] if u["id"] == m.from_user.id), None)
        if not user:
            user = {
                "id": m.from_user.id, 
                "first_name": m.from_user.first_name, 
                "username": m.from_user.username,
                "joined_at": int(time.time() * 1000),
                "is_banned": False,
                "is_active": True,
                "warns": 0,
                "thread_id": None
            }
            cfg["connectedUsers"].append(user)
            cfg["usersCount"] = len(cfg["connectedUsers"])
        else:
            user["is_active"] = True
            user["first_name"] = m.from_user.first_name
            user["username"] = m.from_user.username
        
        if "subscribers" not in cfg: cfg["subscribers"] = []
        if m.from_user.id not in cfg["subscribers"]: cfg["subscribers"].append(m.from_user.id)
        
        save_db()
        log_event(f"User {m.from_user.id} started the bot", "system")

        if user.get("is_banned"): return

        # Клавиатура
        buttons = cfg.get("buttons", [])
        if buttons:
            kb_list = [[KeyboardButton(text=btn["text"])] for btn in buttons if btn.get("text")]
            reply_markup = ReplyKeyboardMarkup(keyboard=kb_list, resize_keyboard=True)
        else:
            reply_markup = None

        await m.answer(cfg.get("welcomeMessage", "Привет!"), reply_markup=reply_markup)

    @dp.message(F.content_type.in_({ContentType.TEXT, ContentType.PHOTO, ContentType.VIDEO, ContentType.VOICE, ContentType.AUDIO, ContentType.DOCUMENT, ContentType.STICKER}))
    async def main_handler(m: Message):
        cfg = get_config()
        if not cfg or not check_license(cfg): return
        
        admin_chat = cfg.get("adminChatId")
        if not admin_chat: return

        # 1. ОБРАБОТКА АДМИНА
        if str(m.chat.id) == str(admin_chat):
            target_user_id = None
            
            # Поиск по топику
            if m.message_thread_id:
                u = next((u for u in cfg.get("connectedUsers", []) if u.get("thread_id") == m.message_thread_id), None)
                if u: target_user_id = u["id"]
            
            # Поиск по Reply (резервный вариант)
            if not target_user_id and m.reply_to_message:
                reply_text = m.reply_to_message.text or m.reply_to_message.caption or ""
                match = re.search(r"ID: (\d+)", reply_text)
                if match: target_user_id = int(match.group(1))

            if target_user_id:
                try:
                    await bot.copy_message(chat_id=target_user_id, from_chat_id=m.chat.id, message_id=m.message_id)
                    log_event(f"Admin replied to {target_user_id}", "outgoing")
                    # Статистика
                    if "stats" not in cfg: cfg["stats"] = {"totalMessages": 0, "outgoingToday": 0}
                    cfg["stats"]["totalMessages"] = cfg.get("stats", {}).get("totalMessages", 0) + 1
                    cfg["stats"]["outgoingToday"] = cfg.get("stats", {}).get("outgoingToday", 0) + 1
                except Exception as e:
                    await m.reply(f"❌ Ошибка отправки: {e}")
            return

        # 2. ОБРАБОТКА ПОЛЬЗОВАТЕЛЯ
        user = next((u for u in cfg.get("connectedUsers", []) if u["id"] == m.from_user.id), None)
        if not user or user.get("is_banned"): return

        # Проверка кнопок (только для текста)
        if m.text:
            text_low = m.text.lower()
            # Кнопки
            for btn in cfg.get("buttons", []):
                if btn["text"].lower() == text_low:
                    if btn.get("type") == "request":
                        header = f"📩 <b>Обращение по кнопке:</b> {btn['text']}\n👤 {m.from_user.full_name}\n🆔 ID: <code>{m.from_user.id}</code>"
                        await bot.send_message(admin_chat, header, message_thread_id=user.get("thread_id"))
                    await m.answer(btn["response"])
                    log_event(f"User clicked button: {btn['text']}", "incoming")
                    return
            
            # Триггеры
            for trig in cfg.get("triggers", []):
                if trig["keyword"].lower() in text_low:
                    await m.answer(trig["response"])
                    log_event(f"Trigger fired: {trig['keyword']}", "info")
                    return

        # Пересылка в админ-чат (Livegram Mode)
        try:
            # Создание топика если нужно
            if cfg.get("settings", {}).get("useTopics") and not user.get("thread_id"):
                try:
                    topic = await bot.create_forum_topic(admin_chat, f"{m.from_user.full_name} | {m.from_user.id}")
                    user["thread_id"] = topic.message_thread_id
                    save_db()
                    await bot.send_message(admin_chat, f"🆕 <b>Новый диалог открыт</b>\nЮзер: {m.from_user.full_name}\nID: <code>{m.from_user.id}</code>", message_thread_id=user["thread_id"])
                except Exception as e:
                    log_event(f"Forum Topic error: {e}", "error")

            # Сама пересылка
            if not user.get("thread_id"):
                header = f"📩 <b>Сообщение от юзера</b>\n👤 {m.from_user.full_name}\n🆔 ID: <code>{m.from_user.id}</code>\n"
                await bot.send_message(admin_chat, header)
            
            await bot.copy_message(chat_id=admin_chat, from_chat_id=m.chat.id, message_id=m.message_id, message_thread_id=user.get("thread_id"))
            
            # Статистика
            if "stats" not in cfg: cfg["stats"] = {"totalMessages": 0, "incomingToday": 0}
            cfg["stats"]["totalMessages"] = cfg.get("stats", {}).get("totalMessages", 0) + 1
            cfg["stats"]["incomingToday"] = cfg.get("stats", {}).get("incomingToday", 0) + 1
            log_event(f"Forwarded message from {m.from_user.id}", "incoming")
            save_db()
        except Exception as e:
            logger.error(f"Forwarding failed: {e}")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        log_event(f"Polling error: {e}", "error")
    finally:
        await session.close()
        active_bots.pop(bot_id, None)

# --- FASTAPI APPLICATION ---
api = APIRouter()

@api.get("/ping")
async def ping():
    return {"status": "online", "timestamp": time.time(), "active_bots": len(active_bots)}

# --- AUTHENTICATION ---
@api.post("/auth/request-verification")
async def request_verif(req: Dict[str, str]):
    email = req.get("email", "").lower().strip()
    if not email: raise HTTPException(400, "Email is required")
    
    code = "".join([str(random.randint(0, 9)) for _ in range(6)])
    db_content["verification_codes"][email] = {
        "code": code, 
        "expires": time.time() + 600
    }
    
    success = EmailService.send_verification_code(email, code)
    if not success:
        logger.warning(f"SMTP Failed for {email}. Debug code: {code}")
        return {"status": "ok", "debug": "Email server offline, code printed to console"}
    
    return {"status": "ok"}

@api_router.post("/auth/register")
async def register(req: RegisterRequest):
    email = req.email.lower().strip()
    verif = db_content["verification_codes"].get(email)
    
    if not verif or verif["code"] != req.code or verif["expires"] < time.time():
        raise HTTPException(400, "Неверный или просроченный код подтверждения")
    
    if any(u["email"] == email for u in db_content["users"]):
        raise HTTPException(400, "Пользователь с таким Email уже зарегистрирован")
    
    new_user = {
        "id": str(uuid.uuid4()),
        "username": req.username,
        "email": email,
        "password": req.password,
        "balance": 0,
        "licenseExpiresAt": int((datetime.now() + timedelta(days=3)).timestamp() * 1000)
    }
    db_content["users"].append(new_user)
    save_db()
    return new_user

@api_router.post("/auth/login")
async def login(req: AuthRequest):
    email = req.email.lower().strip()
    u = next((u for u in db_content["users"] if u["email"] == email and u["password"] == req.password), None)
    if not u: raise HTTPException(401, "Неверный Email или пароль")
    return u

# --- BOT MANAGEMENT ---
@api_router.get("/bots/{user_id}")
async def get_user_bots(user_id: str):
    user_bots = [b for b in db_content["bots"] if str(b["ownerId"]) == str(user_id)]
    for b in user_bots:
        b["status"] = "RUNNING" if is_bot_active(b["id"]) else "IDLE"
        if "logs" not in b: b["logs"] = []
    return user_bots

@api_router.post("/bots/save")
async def api_save_bot(bot_data: BotSaveRequest):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == bot_data.id), -1)
    
    new_data = bot_data.dict()
    if idx >= 0:
        # Сохраняем логи и старые данные, которые не приходят с фронта в полном объеме
        old_data = db_content["bots"][idx]
        new_data["logs"] = old_data.get("logs", [])
        new_data["stats"] = old_data.get("stats", {})
        new_data["subscribers"] = old_data.get("subscribers", [])
        new_data["licenseExpiresAt"] = old_data.get("licenseExpiresAt", 0)
        db_content["bots"][idx] = new_data
    else:
        new_data["logs"] = [format_log_entry("Bot configuration created", "system")]
        new_data["stats"] = {"totalMessages": 0, "incomingToday": 0, "outgoingToday": 0}
        new_data["subscribers"] = []
        new_data["licenseExpiresAt"] = int((datetime.now() + timedelta(days=3)).timestamp() * 1000)
        db_content["bots"].append(new_data)
    
    save_db()
    return {"status": "ok"}

@api_router.post("/bots/start/{bot_id}")
async def api_start_bot(bot_id: str):
    cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not cfg: raise HTTPException(404, "Бот не найден")
    if not check_license(cfg): raise HTTPException(403, "Срок действия лицензии истек")
    
    if is_bot_active(bot_id): return {"status": "already_running"}
    
    task = asyncio.create_task(start_bot_worker(bot_id, cfg["token"]))
    active_tasks[bot_id] = task
    return {"status": "ok"}

@api_router.post("/bots/stop/{bot_id}")
async def api_stop_bot(bot_id: str):
    task = active_tasks.pop(bot_id, None)
    if task: task.cancel()
    if bot_id in active_bots: del active_bots[bot_id]
    return {"status": "ok"}

@api_router.delete("/bots/delete/{bot_id}")
async def api_delete_bot(bot_id: str):
    await api_stop_bot(bot_id)
    db_content["bots"] = [b for b in db_content["bots"] if b["id"] != bot_id]
    save_db()
    return {"status": "ok"}

# --- BROADCAST ---
@api_router.post("/broadcast")
async def api_broadcast(req: BroadcastRequest):
    results = {"success": 0, "failed": 0, "errors": []}
    
    for bot_id in req.botIds:
        bot = active_bots.get(bot_id)
        cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not bot or not cfg: continue
        
        subs = cfg.get("subscribers", [])
        for sub_id in subs:
            try:
                await bot.send_message(sub_id, req.message)
                results["success"] += 1
                await asyncio.sleep(0.05) # Лимит во избежание флуда
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
                await bot.send_message(sub_id, req.message)
                results["success"] += 1
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(str(e))
                
    return results

# --- LICENSE SYSTEM ---
@api_router.post("/license/activate")
async def api_activate_license(req: LicenseActivateRequest):
    bot_cfg = next((b for b in db_content["bots"] if b["id"] == req.botId), None)
    key_obj = next((k for k in db_content["issued_keys"] if k["key"] == req.key and not k.get("used")), None)
    
    if not bot_cfg or not key_obj:
        raise HTTPException(400, "Неверный ключ активации или ID бота")
    
    now_ms = int(time.time() * 1000)
    current_expiry = max(bot_cfg.get("licenseExpiresAt", now_ms), now_ms)
    new_expiry = current_expiry + (key_obj["months"] * 30 * 24 * 3600 * 1000)
    
    bot_cfg["licenseExpiresAt"] = new_expiry
    key_obj["used"] = True
    key_obj["used_by_bot"] = req.botId
    key_obj["activated_at"] = now_ms
    
    save_db()
    return {"status": "ok", "newExpiry": new_expiry}

@api_router.post("/admin/generate-key")
async def api_gen_key(req: Dict[str, int], x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET: raise HTTPException(403, "Доступ запрещен")
    
    months = req.get("months", 1)
    new_key = f"BOT-{months}-{secrets.token_hex(4).upper()}"
    db_content["issued_keys"].append({
        "key": new_key, 
        "months": months, 
        "used": False,
        "created_at": int(time.time() * 1000)
    })
    save_db()
    return {"key": new_key}

# --- SYSTEM LIFECYCLE ---
@asynccontextmanager
async def lifespan_mgr(app: FastAPI):
    load_db()
    # Автоматический перезапуск ботов, которые были запущены
    for b in db_content["bots"]:
        if b.get("status") == "RUNNING" and check_license(b):
            logger.info(f"Auto-restarting bot {b['name']} ({b['id']})")
            active_tasks[b["id"]] = asyncio.create_task(start_bot_worker(b["id"], b["token"]))
    
    yield
    # Завершение работы
    logger.info("Server shutting down, stopping all bots...")
    for tid, task in active_tasks.items():
        task.cancel()
    logger.info("Cleanup complete")

# --- APP INIT ---
app = FastAPI(
    title="BotEngine Pro API",
    version="2.5.0",
    lifespan=lifespan_mgr
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api, prefix="/api")
app.include_router(api) # Fallback

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
