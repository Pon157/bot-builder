
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

from fastapi import FastAPI, HTTPException, Header, Request, Depends, BackgroundTasks, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ParseMode, ContentType
from aiogram.filters import CommandStart, Command
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

# --- ИНИЦИАЛИЗАЦИЯ ОКРУЖЕНИЯ (.env) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_env_vars():
    """Загрузка переменных из .env"""
    env_path = os.path.join(BASE_DIR, '.env')
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8-sig') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        parts = line.split('=', 1)
                        if len(parts) == 2:
                            key, value = parts
                            os.environ[key.strip()] = value.strip().strip('"').strip("'")
            return True
        except Exception as e:
            print(f"Error loading .env: {e}")
    return False

load_env_vars()

# Импорт сервиса почты
try:
    from email_service import EmailService
except ImportError:
    class EmailService:
        @staticmethod
        def send_verification_code(e, c): return False
        @staticmethod
        def send_password_reset(e, c): return False

# --- КОНФИГУРАЦИЯ ---
DB_FILE = os.path.join(BASE_DIR, "database.json")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotEngine.Core")

# --- МОДЕЛИ ДАННЫХ (PYDANTIC) ---
class AuthRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    code: str

class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    newPassword: str

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
    settings: Dict[str, Any] = {}
    connectedUsers: List[Any] = []

class BroadcastRequest(BaseModel):
    botIds: List[str]
    message: str

class LicenseActivateRequest(BaseModel):
    botId: str
    key: str

# --- ДВИЖОК БАЗЫ ДАННЫХ ---
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

# --- УПРАВЛЕНИЕ ЗАПУЩЕННЫМИ БОТАМИ ---
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

# --- ВОРКЕР AIOGRAM ---
async def start_bot_worker(bot_id: str, token: str):
    logger.info(f"Starting worker for bot {bot_id}")
    session = AiohttpSession()
    bot = Bot(token=token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    active_bots[bot_id] = bot
    dp = Dispatcher()
    
    def get_config():
        return next((b for b in db_content["bots"] if b["id"] == bot_id), None)

    def log_event(text: str, level: str = "info"):
        cfg = get_config()
        if cfg:
            if "logs" not in cfg: cfg["logs"] = []
            cfg["logs"].insert(0, format_log_entry(text, level))
            cfg["logs"] = cfg["logs"][:100]

    def update_msg_stats(direction: str):
        cfg = get_config()
        if not cfg: return
        if "stats" not in cfg: 
            cfg["stats"] = {"totalMessages": 0, "incomingToday": 0, "outgoingToday": 0, "history": []}
        
        cfg["stats"]["totalMessages"] += 1
        today_str = datetime.now().strftime("%d.%m")
        history = cfg["stats"].get("history", [])
        day_stat = next((h for h in history if h["date"] == today_str), None)
        
        if not day_stat:
            day_stat = {"date": today_str, "incoming": 0, "outgoing": 0, "totalUsers": len(cfg.get("connectedUsers", []))}
            history.append(day_stat)
        
        if direction == "in":
            cfg["stats"]["incomingToday"] += 1
            day_stat["incoming"] += 1
        else:
            cfg["stats"]["outgoingToday"] += 1
            day_stat["outgoing"] += 1
            
        cfg["stats"]["history"] = history[-14:]
        save_db()

    @dp.message(CommandStart())
    async def handle_start(m: Message):
        cfg = get_config()
        if not cfg or not check_license(cfg): return
        
        if "connectedUsers" not in cfg: cfg["connectedUsers"] = []
        user = next((u for u in cfg["connectedUsers"] if u["id"] == m.from_user.id), None)
        if not user:
            user = {
                "id": m.from_user.id, "first_name": m.from_user.first_name, "username": m.from_user.username,
                "joined_at": int(time.time() * 1000), "is_banned": False, "is_active": True, "warns": 0, "thread_id": None
            }
            cfg["connectedUsers"].append(user)
        else:
            user["is_active"] = True
        
        if "subscribers" not in cfg: cfg["subscribers"] = []
        if m.from_user.id not in cfg["subscribers"]: cfg["subscribers"].append(m.from_user.id)
        
        save_db()
        log_event(f"User {m.from_user.id} started the bot", "system")
        update_msg_stats("out")

        buttons = cfg.get("buttons", [])
        reply_markup = None
        if buttons:
            kb_list = [[KeyboardButton(text=btn.text)] for btn in buttons if btn.text]
            reply_markup = ReplyKeyboardMarkup(keyboard=kb_list, resize_keyboard=True)

        await m.answer(cfg.get("welcomeMessage", "Привет!"), reply_markup=reply_markup)

    @dp.message()
    async def main_handler(m: Message):
        cfg = get_config()
        if not cfg or not check_license(cfg): return
        admin_chat = cfg.get("adminChatId")
        if not admin_chat: return

        # АДМИН
        if str(m.chat.id) == str(admin_chat):
            target_id = None
            if m.message_thread_id:
                u = next((u for u in cfg.get("connectedUsers", []) if u.get("thread_id") == m.message_thread_id), None)
                if u: target_id = u["id"]
            if not target_id and m.reply_to_message:
                reply_text = m.reply_to_message.text or m.reply_to_message.caption or ""
                match = re.search(r"ID: (\d+)", reply_text)
                if match: target_id = int(match.group(1))

            if target_id:
                try:
                    await bot.copy_message(chat_id=target_id, from_chat_id=m.chat.id, message_id=m.message_id)
                    log_event(f"Admin replied to {target_id}", "outgoing")
                    update_msg_stats("out")
                except Exception as e:
                    await m.reply(f"❌ Ошибка отправки: {e}")
            return

        # ПОЛЬЗОВАТЕЛЬ
        user = next((u for u in cfg.get("connectedUsers", []) if u["id"] == m.from_user.id), None)
        if not user or user.get("is_banned"): return

        if m.text:
            text_low = m.text.lower()
            for btn in cfg.get("buttons", []):
                if btn.text.lower() == text_low:
                    if btn.type == "request":
                        tmpl = btn.adminTemplate or "📩 Обращение: {{button}}\nОт: {{name}} (ID: {{id}})"
                        header = tmpl.replace("{{button}}", btn.text)\
                                    .replace("{{name}}", m.from_user.full_name)\
                                    .replace("{{id}}", str(m.from_user.id))\
                                    .replace("{{username}}", f"@{m.from_user.username}" if m.from_user.username else "N/A")
                        await bot.send_message(admin_chat, header, message_thread_id=user.get("thread_id"))
                    await m.answer(btn.response)
                    log_event(f"User clicked button: {btn.text}", "incoming")
                    update_msg_stats("in")
                    return
            
            for trig in cfg.get("triggers", []):
                if trig.keyword.lower() in text_low:
                    await m.answer(trig.response)
                    update_msg_stats("in")
                    return

        # ПЕРЕСЫЛКА (Livegram)
        try:
            if cfg.get("settings", {}).get("useTopics") and not user.get("thread_id"):
                try:
                    topic = await bot.create_forum_topic(admin_chat, f"{m.from_user.full_name} | {m.from_user.id}")
                    user["thread_id"] = topic.message_thread_id
                    save_db()
                except: pass

            if not user.get("thread_id"):
                header = f"📩 <b>От:</b> {m.from_user.full_name}\n🆔 ID: <code>{m.from_user.id}</code>"
                await bot.send_message(admin_chat, header)
            
            await bot.copy_message(chat_id=admin_chat, from_chat_id=m.chat.id, message_id=m.message_id, message_thread_id=user.get("thread_id"))
            log_event(f"Forwarded msg from {m.from_user.id}", "incoming")
            update_msg_stats("in")
        except Exception as e:
            logger.error(f"Forward Error: {e}")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await session.close()
        active_bots.pop(bot_id, None)

# --- API ---
api_router = APIRouter()

@api_router.get("/ping")
async def ping():
    return {"status": "ok", "active": len(active_bots)}

@api_router.post("/auth/request-verification")
async def request_verif(req: Dict[str, str], background_tasks: BackgroundTasks):
    email = req.get("email", "").lower().strip()
    if not email: raise HTTPException(400, "Email required")
    code = "".join([str(random.randint(0, 9)) for _ in range(6)])
    db_content["verification_codes"][email] = {"code": code, "expires": time.time() + 600}
    background_tasks.add_task(EmailService.send_verification_code, email, code)
    return {"status": "ok"}

@api_router.post("/auth/register")
async def register(req: RegisterRequest):
    email = req.email.lower().strip()
    v = db_content["verification_codes"].get(email)
    if not v or v["code"] != req.code: raise HTTPException(400, "Код неверен")
    if any(u["email"] == email for u in db_content["users"]): raise HTTPException(400, "Email занят")
    user = {"id": str(uuid.uuid4()), "username": req.username, "email": email, "password": req.password, "balance": 0, "licenseExpiresAt": int((datetime.now() + timedelta(days=3)).timestamp() * 1000)}
    db_content["users"].append(user)
    save_db()
    return user

@api_router.post("/auth/login")
async def login(req: AuthRequest):
    email = req.email.lower().strip()
    u = next((u for u in db_content["users"] if u["email"] == email and u["password"] == req.password), None)
    if not u: raise HTTPException(401, "Invalid credentials")
    return u

@api_router.post("/auth/forgot-password")
async def forgot_password(req: Dict[str, str], background_tasks: BackgroundTasks):
    email = req.get("email", "").lower().strip()
    user = next((u for u in db_content["users"] if u["email"] == email), None)
    if not user: raise HTTPException(404, "User not found")
    code = "".join([str(random.randint(0, 9)) for _ in range(6)])
    db_content["verification_codes"][email] = {"code": code, "expires": time.time() + 600}
    background_tasks.add_task(EmailService.send_password_reset, email, code)
    return {"status": "ok"}

@api_router.post("/auth/reset-password")
async def reset_password(req: ResetPasswordRequest):
    email = req.email.lower().strip()
    v = db_content["verification_codes"].get(email)
    if not v or v["code"] != req.code: raise HTTPException(400, "Bad code")
    user = next((u for u in db_content["users"] if u["email"] == email), None)
    if user:
        user["password"] = req.newPassword
        save_db()
        return {"status": "ok"}
    raise HTTPException(404)

@api_router.get("/bots/{user_id}")
async def get_bots(user_id: str):
    user_bots = [b for b in db_content["bots"] if str(b["ownerId"]) == str(user_id)]
    for b in user_bots:
        b["status"] = "RUNNING" if is_bot_active(b["id"]) else "IDLE"
    return user_bots

@api_router.post("/bots/save")
async def save_bot(bot_data: BotSaveRequest):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == bot_data.id), -1)
    new_data = bot_data.dict()
    if idx >= 0:
        old = db_content["bots"][idx]
        new_data.update({"logs": old.get("logs", []), "stats": old.get("stats", {}), "licenseExpiresAt": old.get("licenseExpiresAt", 0), "subscribers": old.get("subscribers", [])})
        db_content["bots"][idx] = new_data
    else:
        new_data.update({"logs": [], "stats": {"totalMessages": 0, "history": []}, "licenseExpiresAt": int((datetime.now() + timedelta(days=3)).timestamp() * 1000), "subscribers": []})
        db_content["bots"].append(new_data)
    save_db()
    return {"status": "ok"}

@api_router.post("/bots/start/{bot_id}")
async def start_bot_api(bot_id: str):
    cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not cfg or not check_license(cfg): raise HTTPException(403)
    if not is_bot_active(bot_id):
        active_tasks[bot_id] = asyncio.create_task(start_bot_worker(bot_id, cfg["token"]))
    return {"status": "ok"}

@api_router.post("/bots/stop/{bot_id}")
async def stop_bot_api(bot_id: str):
    task = active_tasks.pop(bot_id, None)
    if task: task.cancel()
    return {"status": "ok"}

@api_router.delete("/bots/delete/{bot_id}")
async def delete_bot_api(bot_id: str):
    await stop_bot_api(bot_id)
    db_content["bots"] = [b for b in db_content["bots"] if b["id"] != bot_id]
    save_db()
    return {"status": "ok"}

@api_router.post("/license/activate")
async def activate(req: LicenseActivateRequest):
    bot_cfg = next((b for b in db_content["bots"] if b["id"] == req.botId), None)
    key_obj = next((k for k in db_content["issued_keys"] if k["key"] == req.key and not k.get("used")), None)
    if not bot_cfg or not key_obj: raise HTTPException(400)
    now = int(time.time() * 1000)
    bot_cfg["licenseExpiresAt"] = max(bot_cfg.get("licenseExpiresAt", now), now) + (key_obj["months"] * 30 * 24 * 3600 * 1000)
    key_obj["used"] = True
    save_db()
    return {"status": "ok", "newExpiry": bot_cfg["licenseExpiresAt"]}

@api_router.post("/admin/generate-key")
async def gen_key(req: Dict[str, int], x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET: raise HTTPException(403)
    key = f"BOT-{req.get('months', 1)}-{secrets.token_hex(4).upper()}"
    db_content["issued_keys"].append({"key": key, "months": req.get("months", 1), "used": False})
    save_db()
    return {"key": key}

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_db()
    for b in db_content["bots"]:
        if b.get("status") == "RUNNING" and check_license(b):
            active_tasks[b["id"]] = asyncio.create_task(start_bot_worker(b["id"], b["token"]))
    yield
    for t in active_tasks.values(): t.cancel()

app = FastAPI(title="BotEngine Pro", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(api_router, prefix="/api")

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
