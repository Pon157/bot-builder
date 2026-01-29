
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
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException, Header, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ContentType
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter
import uvicorn

# --- Инициализация логирования ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotEngine.Server")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "database.json")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")

# Попытка импорта сервиса почты
try:
    from email_service import EmailService
except ImportError:
    class EmailService:
        @staticmethod
        def send_verification_code(e, c): logger.info(f"DEBUG: Code for {e}: {c}"); return True
        @staticmethod
        def send_password_reset(e, c): logger.info(f"DEBUG: Reset for {e}: {c}"); return True

# --- База данных ---
db_content = {
    "users": [], 
    "bots": [], 
    "issued_keys": [], 
    "verification_codes": {} 
}

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db_content, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"❌ DB Save Error: {e}")

def load_db():
    global db_content
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                for key in db_content.keys():
                    if key in loaded: db_content[key] = loaded[key]
        except Exception as e:
            logger.error(f"❌ DB Load Error: {e}")

# --- Модели API ---
class AuthRequest(BaseModel):
    email: str
    password: str

class VerifyRegisterRequest(BaseModel):
    email: str
    code: str
    password: str
    username: str

class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    newPassword: str

class BroadcastRequest(BaseModel):
    botIds: List[str]
    message: str

class KeyGenRequest(BaseModel):
    months: int

# --- Bot Worker Logic (Livegram Mode) ---
active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}

async def bot_worker(bot_id: str, token: str):
    logger.info(f"🤖 Starting worker for bot {bot_id}")
    session = AiohttpSession()
    bot = Bot(token=token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    active_bots[bot_id] = bot
    dp = Dispatcher()
    
    def log_event(cfg, msg_type, text):
        if "logs" not in cfg: cfg["logs"] = []
        log_entry = {
            "id": str(uuid.uuid4()),
            "timestamp": int(time.time() * 1000),
            "type": msg_type,
            "text": text
        }
        cfg["logs"].insert(0, log_entry)
        cfg["logs"] = cfg["logs"][:50] # Храним последние 50

    @dp.message(CommandStart())
    async def h_start(m: Message):
        cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not cfg: return
        
        # Регистрация пользователя
        if "connectedUsers" not in cfg: cfg["connectedUsers"] = []
        if not any(u["id"] == m.from_user.id for u in cfg["connectedUsers"]):
            cfg["connectedUsers"].append({
                "id": m.from_user.id,
                "first_name": m.from_user.first_name,
                "username": m.from_user.username,
                "is_active": True,
                "is_banned": False,
                "warns": 0,
                "joined_at": int(time.time() * 1000)
            })
        
        log_event(cfg, "incoming", f"User {m.from_user.id} started bot")
        save_db()
        await m.answer(cfg.get("welcomeMessage", "Привет!"))

    @dp.message()
    async def h_all(m: Message):
        cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not cfg: return
        
        admin_id = cfg.get("adminChatId")
        
        # ОБРАБОТКА ОТВЕТА АДМИНА
        if admin_id and str(m.chat.id) == str(admin_id) and m.reply_to_message:
            rep_text = m.reply_to_message.text or m.reply_to_message.caption or ""
            match = re.search(r"ID: (\d+)", rep_text)
            if match:
                target_id = int(match.group(1))
                try:
                    await bot.copy_message(target_id, m.chat.id, m.message_id)
                    await m.reply("✅ Сообщение доставлено")
                    log_event(cfg, "outgoing", f"Admin replied to {target_id}")
                    save_db()
                    return
                except Exception as e:
                    await m.reply(f"❌ Ошибка отправки: {e}")
                    return

        # ОБРАБОТКА СООБЩЕНИЯ ОТ ЮЗЕРА
        if admin_id and str(m.chat.id) != str(admin_id):
            # 1. Проверка триггеров
            if m.text:
                for t in cfg.get("triggers", []):
                    if t["keyword"].lower() in m.text.lower():
                        await m.answer(t["response"])
                        log_event(cfg, "system", f"Trigger fired: {t['keyword']}")
                        return
                
                for btn in cfg.get("buttons", []):
                    if btn["text"].lower() == m.text.lower():
                        await m.answer(btn["response"])
                        log_event(cfg, "system", f"Button click: {btn['text']}")
                        return

            # 2. Пересылка админу (Livegram)
            header = f"📩 <b>Сообщение от {m.from_user.full_name}</b>\nID: <code>{m.from_user.id}</code>"
            try:
                await bot.send_message(admin_id, header)
                await bot.copy_message(admin_id, m.chat.id, m.message_id)
                log_event(cfg, "incoming", f"Forwarded msg from {m.from_user.id}")
                save_db()
            except Exception as e:
                logger.error(f"Forward error: {e}")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Bot {bot_id} Polling Error: {e}")
    finally:
        await session.close()
        active_bots.pop(bot_id, None)

# --- FastAPI Setup ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_db()
    logger.info("✅ Database loaded")
    yield
    for t in active_tasks.values(): t.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/ping")
async def ping(): return {"status": "online", "timestamp": time.time()}

# --- AUTH ROUTES ---

@app.post("/api/auth/request-verification")
async def auth_req_ver(req: Dict[str, str], bg: BackgroundTasks):
    email = req.get("email", "").lower().strip()
    if not email: raise HTTPException(400, "Email required")
    code = "".join([str(random.randint(0, 9)) for _ in range(6)])
    db_content["verification_codes"][email] = {"code": code, "expires": time.time() + 600}
    bg.add_task(EmailService.send_verification_code, email, code)
    return {"status": "ok"}

@app.post("/api/auth/verify-and-register")
async def auth_verify_reg(req: VerifyRegisterRequest):
    email = req.email.lower().strip()
    ver = db_content["verification_codes"].get(email)
    if not ver or ver["code"] != req.code: raise HTTPException(400, "Invalid code")
    
    user = {
        "id": str(uuid.uuid4()),
        "username": req.username,
        "email": email,
        "password": req.password,
        "balance": 0,
        "botsCreated": 0,
        "licenseExpiresAt": int((time.time() + 259200) * 1000) # 3 дня триала
    }
    db_content["users"].append(user)
    save_db()
    return user

@app.post("/api/auth/login")
async def auth_login(req: AuthRequest):
    email = req.email.lower().strip()
    u = next((u for u in db_content["users"] if u["email"] == email and u["password"] == req.password), None)
    if not u: raise HTTPException(401, "Invalid credentials")
    return u

@app.post("/api/auth/forgot-password")
async def auth_forgot(req: Dict[str, str], bg: BackgroundTasks):
    email = req.get("email", "").lower().strip()
    u = next((u for u in db_content["users"] if u["email"] == email), None)
    if not u: raise HTTPException(404, "User not found")
    code = "".join([str(random.randint(0, 9)) for _ in range(6)])
    db_content["verification_codes"][email] = {"code": code, "expires": time.time() + 600}
    bg.add_task(EmailService.send_password_reset, email, code)
    return {"status": "ok"}

@app.post("/api/auth/reset-password")
async def auth_reset(req: ResetPasswordRequest):
    email = req.email.lower().strip()
    ver = db_content["verification_codes"].get(email)
    if not ver or ver["code"] != req.code: raise HTTPException(400, "Invalid code")
    u = next((u for u in db_content["users"] if u["email"] == email), None)
    if u:
        u["password"] = req.newPassword
        save_db()
        return {"status": "ok"}
    raise HTTPException(404)

# --- BOT ROUTES ---

@app.get("/api/bots/{uid}")
async def get_user_bots(uid: str):
    bots = [b for b in db_content["bots"] if str(b["ownerId"]) == str(uid)]
    for b in bots:
        b["status"] = "RUNNING" if b["id"] in active_tasks and not active_tasks[b["id"]].done() else "IDLE"
    return bots

@app.post("/api/bots/save")
async def api_save_bot(bot_data: dict):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == bot_data["id"]), -1)
    if idx >= 0: db_content["bots"][idx] = bot_data
    else: db_content["bots"].append(bot_data)
    save_db()
    return {"status": "ok"}

@app.delete("/api/bots/delete/{bid}")
async def api_delete_bot(bid: str):
    if bid in active_tasks:
        active_tasks[bid].cancel()
        del active_tasks[bid]
    db_content["bots"] = [b for b in db_content["bots"] if b["id"] != bid]
    save_db()
    return {"status": "ok"}

@app.post("/api/bots/start/{bid}")
async def api_start_bot(bid: str):
    cfg = next((b for b in db_content["bots"] if b["id"] == bid), None)
    if not cfg: raise HTTPException(404)
    if bid in active_tasks and not active_tasks[bid].done(): return {"status": "ok"}
    active_tasks[bid] = asyncio.create_task(bot_worker(bid, cfg["token"]))
    return {"status": "ok"}

@app.post("/api/bots/stop/{bid}")
async def api_stop_bot(bid: str):
    t = active_tasks.pop(bid, None)
    if t: t.cancel()
    return {"status": "ok"}

@app.post("/api/broadcast")
async def api_broadcast(req: BroadcastRequest):
    success, failed = 0, 0
    for bid in req.botIds:
        bot = active_bots.get(bid)
        if not bot: continue
        cfg = next((b for b in db_content["bots"] if b["id"] == bid), None)
        if not cfg: continue
        for u in cfg.get("connectedUsers", []):
            try:
                await bot.send_message(u["id"], req.message)
                success += 1
                await asyncio.sleep(0.05)
            except: failed += 1
    return {"success": success, "failed": failed}

@app.post("/api/license/activate")
async def api_activate(req: Dict[str, str]):
    bid = req.get("botId")
    key = req.get("key", "")
    # Простая валидация ключа (можно усложнить)
    if not key.startswith("BOT-"): raise HTTPException(400, "Invalid key")
    
    bot = next((b for b in db_content["bots"] if b["id"] == bid), None)
    if bot:
        new_expiry = int((time.time() + 2592000) * 1000) # +30 дней
        bot["licenseExpiresAt"] = new_expiry
        save_db()
        return {"status": "ok", "newExpiry": new_expiry}
    raise HTTPException(404)

@app.post("/api/admin/generate-key")
async def api_gen_key(req: KeyGenRequest, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET: raise HTTPException(403)
    key = f"BOT-{req.months}-{secrets.token_hex(4).upper()}"
    return {"key": key}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
