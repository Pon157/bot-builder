
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
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any, Union

from fastapi import FastAPI, HTTPException, Header, Request, Depends, BackgroundTasks, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from aiogram import Bot, Dispatcher, types, F
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

# --- ИНИЦИАЛИЗАЦИЯ ОКРУЖЕНИЯ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_env_vars():
    env_path = os.path.join(BASE_DIR, '.env')
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8-sig') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        parts = line.split('=', 1)
                        if len(parts) == 2:
                            k, v = parts
                            os.environ[k.strip()] = v.strip().strip('"').strip("'")
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

# --- МОДЕЛИ ДАННЫХ ---
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

# --- ДВИЖОК БД ---
db_content = {
    "users": [], 
    "bots": [], 
    "issued_keys": [], 
    "verification_codes": {}, 
    "system_stats": {"total_runs": 0, "api_calls": 0}
}

def save_db():
    try:
        temp = db_content.copy()
        # Очистка просроченных кодов
        temp["verification_codes"] = {k: v for k, v in db_content["verification_codes"].items() if v["expires"] > time.time()}
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(temp, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Save DB Error: {e}")

def load_db():
    global db_content
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                db_content.update(data)
                logger.info(f"DB Loaded: {len(db_content['users'])} users, {len(db_content['bots'])} bots")
        except Exception as e:
            logger.error(f"Load DB Error: {e}")

# --- УПРАВЛЕНИЕ БОТАМИ ---
active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}

def is_bot_active(bot_id: str) -> bool:
    return bot_id in active_tasks and not active_tasks[bot_id].done()

def check_license(bot_cfg: dict) -> bool:
    expires = bot_cfg.get("licenseExpiresAt", 0)
    return int(expires) > int(time.time() * 1000)

# --- WORKER (LIVEGRAM CORE) ---
async def start_bot_worker(bot_id: str, token: str):
    logger.info(f"Worker for bot {bot_id} started")
    session = AiohttpSession()
    bot = Bot(token=token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    active_bots[bot_id] = bot
    dp = Dispatcher()
    
    def get_cfg(): 
        return next((b for b in db_content["bots"] if b["id"] == bot_id), None)

    def log_evt(msg: str, lvl: str = "info"):
        c = get_cfg()
        if c:
            if "logs" not in c: c["logs"] = []
            c["logs"].insert(0, {"id": str(uuid.uuid4()), "timestamp": int(time.time()*1000), "type": lvl, "text": msg})
            c["logs"] = c["logs"][:100]

    def update_stats(direction: str):
        c = get_cfg()
        if not c: return
        if "stats" not in c: 
            c["stats"] = {"totalMessages": 0, "incomingToday": 0, "outgoingToday": 0, "history": []}
        
        c["stats"]["totalMessages"] += 1
        today = datetime.now().strftime("%d.%m")
        history = c["stats"].get("history", [])
        day_stat = next((h for h in history if h["date"] == today), None)
        
        if not day_stat:
            day_stat = {
                "date": today, "incoming": 0, "outgoing": 0, 
                "totalUsers": len(c.get("connectedUsers", [])),
                "activeUsers": 0
            }
            history.append(day_stat)
        
        if direction == "in": day_stat["incoming"] += 1
        else: day_stat["outgoing"] += 1
            
        c["stats"]["history"] = history[-14:]
        save_db()

    # --- HANDLERS ---
    
    @dp.message(CommandStart())
    async def h_start(m: Message):
        cfg = get_cfg()
        if not cfg or not check_license(cfg): return
        
        users = cfg.get("connectedUsers", [])
        u = next((u for u in users if u["id"] == m.from_user.id), None)
        
        if not u:
            u = {
                "id": m.from_user.id, "first_name": m.from_user.first_name, "username": m.from_user.username, 
                "joined_at": int(time.time()*1000), "is_active": True, "is_banned": False, "warns": 0, "thread_id": None
            }
            users.append(u)
            cfg["connectedUsers"] = users
        else:
            u["is_active"] = True

        if "subscribers" not in cfg: cfg["subscribers"] = []
        if m.from_user.id not in cfg["subscribers"]: cfg["subscribers"].append(m.from_user.id)
        
        log_evt(f"User {m.from_user.id} started bot", "system")
        update_stats("out")
        
        btns = cfg.get("buttons", [])
        reply_markup = None
        if btns:
            kb = [[KeyboardButton(text=b["text"])] for b in btns if b.get("text")]
            reply_markup = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
            
        await m.answer(cfg.get("welcomeMessage", "Привет!"), reply_markup=reply_markup)

    @dp.message(F.content_type.in_({
        ContentType.TEXT, ContentType.PHOTO, ContentType.VIDEO, 
        ContentType.VOICE, ContentType.AUDIO, ContentType.DOCUMENT, 
        ContentType.STICKER, ContentType.VIDEO_NOTE, ContentType.ANIMATION
    }))
    async def h_main(m: Message):
        cfg = get_cfg()
        if not cfg or not check_license(cfg): return
        admin = cfg.get("adminChatId")
        if not admin: return

        # 1. ЛОГИКА АДМИНА (ОТВЕТ ЮЗЕРУ)
        if str(m.chat.id) == str(admin):
            tid = None
            # А) По топику
            if m.message_thread_id:
                u = next((u for u in cfg.get("connectedUsers", []) if u.get("thread_id") == m.message_thread_id), None)
                if u: tid = u["id"]
            
            # Б) По реплаю (Livegram Style)
            if not tid and m.reply_to_message:
                r_text = m.reply_to_message.text or m.reply_to_message.caption or ""
                match = re.search(r"ID: (\d+)", r_text)
                if match: tid = int(match.group(1))
            
            if tid:
                try:
                    await bot.copy_message(chat_id=tid, from_chat_id=m.chat.id, message_id=m.message_id)
                    log_evt(f"Admin replied to {tid}", "outgoing")
                    update_stats("out")
                except TelegramForbiddenError:
                    await m.reply("❌ Бот заблокирован пользователем.")
                except Exception as e: 
                    await m.reply(f"❌ Ошибка: {e}")
            return

        # 2. ЛОГИКА ЮЗЕРА (ПЕРЕСЫЛКА АДМИНУ)
        u = next((u for u in cfg.get("connectedUsers", []) if u["id"] == m.from_user.id), None)
        if not u:
            u = {"id": m.from_user.id, "first_name": m.from_user.first_name, "username": m.from_user.username, "joined_at": int(time.time()*1000), "is_active": True, "is_banned": False, "warns": 0, "thread_id": None}
            if "connectedUsers" not in cfg: cfg["connectedUsers"] = []
            cfg["connectedUsers"].append(u)
            
        if u.get("is_banned"): return

        # Проверка кнопок и триггеров
        if m.text:
            text_low = m.text.lower()
            for btn in cfg.get("buttons", []):
                if btn.get("text", "").lower() == text_low:
                    if btn.get("type") == "request":
                        tmpl = btn.get("adminTemplate") or "📩 Обращение: {{button}}\nОт: {{name}} (ID: {{id}})"
                        header = tmpl.replace("{{button}}", btn["text"]).replace("{{name}}", m.from_user.full_name).replace("{{id}}", str(m.from_user.id))
                        await bot.send_message(admin, header, message_thread_id=u.get("thread_id"))
                    await m.answer(btn.get("response", ""))
                    log_evt(f"User clicked: {btn.get('text')}", "incoming")
                    update_stats("in")
                    return
            
            for trg in cfg.get("triggers", []):
                if trg.get("keyword", "").lower() in text_low:
                    await m.answer(trg.get("response", ""))
                    update_stats("in")
                    return

        # ПЕРЕСЫЛКА (LIVEGRAM MODE)
        try:
            # Создание топика
            if cfg.get("settings", {}).get("useTopics") and not u.get("thread_id"):
                try:
                    topic = await bot.create_forum_topic(admin, f"{m.from_user.full_name} | {m.from_user.id}")
                    u["thread_id"] = topic.message_thread_id
                    save_db()
                    await bot.send_message(admin, f"🆕 <b>Новый диалог</b>\n👤 Юзер: {m.from_user.full_name}\n🆔 ID: <code>{m.from_user.id}</code>", message_thread_id=u["thread_id"])
                except Exception as e: logger.error(f"Topic Error: {e}")

            # Заголовок (если без топиков)
            if not u.get("thread_id"):
                header = f"📩 <b>Сообщение от:</b> {m.from_user.full_name}\n🆔 ID: <code>{m.from_user.id}</code>"
                await bot.send_message(admin, header)
            
            # Копируем сообщение
            await bot.copy_message(chat_id=admin, from_chat_id=m.chat.id, message_id=m.message_id, message_thread_id=u.get("thread_id"))
            log_evt(f"Forwarded from {m.from_user.id}", "incoming")
            update_stats("in")
        except Exception as e:
            logger.error(f"Global forward error: {e}")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await session.close()
        active_bots.pop(bot_id, None)

# --- API ---
app = FastAPI(title="BotEngine Pro Server")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

api = APIRouter()

@api.get("/ping")
async def ping(): return {"status": "ok", "active": len(active_bots)}

@api.post("/auth/request-verification")
async def req_ver(req: Dict[str, str], bg: BackgroundTasks):
    email = req.get("email", "").lower().strip()
    if not email: raise HTTPException(400, "Email required")
    code = "".join([str(random.randint(0, 9)) for _ in range(6)])
    db_content["verification_codes"][email] = {"code": code, "expires": time.time() + 600}
    bg.add_task(EmailService.send_verification_code, email, code)
    logger.info(f"Generated code {code} for {email}")
    return {"status": "ok"}

@api.post("/auth/register")
@api.post("/auth/verify-and-register") # Фикс 404
async def register(req: RegisterRequest):
    email = req.email.lower().strip()
    v = db_content["verification_codes"].get(email)
    
    if not v:
        logger.warning(f"Registration failed: No code found for {email}")
        raise HTTPException(400, "Код не был отправлен или истек")
    
    if v["code"] != req.code:
        logger.warning(f"Registration failed: Wrong code for {email}. Expected {v['code']}, got {req.code}")
        raise HTTPException(400, "Неверный код подтверждения")
        
    if any(u["email"] == email for u in db_content["users"]):
        raise HTTPException(400, "Email уже занят")
        
    user = {
        "id": str(uuid.uuid4()), "username": req.username, "email": email, "password": req.password, 
        "balance": 0, "licenseExpiresAt": int((datetime.now() + timedelta(days=3)).timestamp()*1000)
    }
    db_content["users"].append(user)
    save_db()
    return user

@api.post("/auth/login")
async def login(req: AuthRequest):
    email = req.email.lower().strip()
    u = next((u for u in db_content["users"] if u["email"] == email and u["password"] == req.password), None)
    if not u: raise HTTPException(401, "Invalid credentials")
    return u

@api.get("/bots/{uid}")
async def get_bots(uid: str):
    user_bots = [b for b in db_content["bots"] if str(b["ownerId"]) == str(uid)]
    for b in user_bots: b["status"] = "RUNNING" if is_bot_active(b["id"]) else "IDLE"
    return user_bots

@api.post("/bots/save")
async def save_bot_api(bdata: BotSaveRequest):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == bdata.id), -1)
    new_d = bdata.dict()
    if idx >= 0:
        old = db_content["bots"][idx]
        new_d.update({"logs": old.get("logs", []), "stats": old.get("stats", {}), "licenseExpiresAt": old.get("licenseExpiresAt", 0), "subscribers": old.get("subscribers", [])})
        db_content["bots"][idx] = new_d
    else:
        new_d.update({"logs": [], "stats": {"totalMessages": 0, "history": []}, "licenseExpiresAt": int((datetime.now() + timedelta(days=3)).timestamp()*1000), "subscribers": []})
        db_content["bots"].append(new_d)
    save_db()
    return {"status": "ok"}

@api.post("/bots/start/{bid}")
async def start_api(bid: str):
    c = next((b for b in db_content["bots"] if b["id"] == bid), None)
    if not c or not check_license(c): raise HTTPException(403, "License error")
    if not is_bot_active(bid): active_tasks[bid] = asyncio.create_task(start_bot_worker(bid, c["token"]))
    return {"status": "ok"}

@api.post("/bots/stop/{bid}")
async def stop_api(bid: str):
    t = active_tasks.pop(bid, None)
    if t: t.cancel()
    return {"status": "ok"}

@api.delete("/bots/delete/{bid}")
async def del_api(bid: str):
    await stop_api(bid)
    db_content["bots"] = [b for b in db_content["bots"] if b["id"] != bid]
    save_db()
    return {"status": "ok"}

@api.post("/broadcast")
async def broadcast_api(req: BroadcastRequest):
    res = {"success": 0, "failed": 0}
    for bid in req.botIds:
        bot = active_bots.get(bid)
        cfg = next((b for b in db_content["bots"] if b["id"] == bid), None)
        if not bot or not cfg: continue
        subs = cfg.get("subscribers", [])
        for sid in subs:
            try:
                await bot.send_message(sid, req.message)
                res["success"] += 1
                await asyncio.sleep(0.05)
            except: res["failed"] += 1
    return res

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_db()
    for b in db_content["bots"]:
        if b.get("status") == "RUNNING" and check_license(b):
            active_tasks[b["id"]] = asyncio.create_task(start_bot_worker(b["id"], b["token"]))
    yield
    for t in active_tasks.values(): t.cancel()

app.router.lifespan_context = lifespan
app.include_router(api, prefix="/api")
app.include_router(api)

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
