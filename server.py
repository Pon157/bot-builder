
import asyncio
import logging
import json
import os
import time
import re
import uuid
import secrets
from contextlib import asynccontextmanager
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, Message, ContentType
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
import uvicorn

# Настройки безопасности
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "SUPER_SECRET_TOKEN_123")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BotEngine")

DB_FILE = "database.json"
db_content = {"users": [], "bots": [], "issued_keys": []}
active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}

class LoginRequest(BaseModel):
    email: str
    password: str

class KeyActivationRequest(BaseModel):
    userId: str
    key: str

class KeyGenRequest(BaseModel):
    months: int

class BroadcastRequest(BaseModel):
    botIds: List[str]
    message: str

class UserBase(BaseModel):
    id: str
    username: str
    email: str
    password: str
    licenseExpiresAt: int
    trialUsed: bool
    balance: float
    botsCreated: int

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db_content, f, ensure_ascii=False, indent=2)
    except Exception as e: logger.error(f"Save DB Error: {e}")

def load_db():
    global db_content
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                db_content["users"] = loaded.get("users", [])
                db_content["bots"] = loaded.get("bots", [])
                db_content["issued_keys"] = loaded.get("issued_keys", [])
        except Exception as e: 
            db_content = {"users": [], "bots": [], "issued_keys": []}

def check_license(user_id: str) -> bool:
    user = next((u for u in db_content["users"] if u["id"] == user_id), None)
    if not user: return False
    return user["licenseExpiresAt"] > (time.time() * 1000)

def add_log(bot_id: str, log_type: str, text: str, code: str = None):
    for b in db_content["bots"]:
        if b["id"] == bot_id:
            if "logs" not in b: b["logs"] = []
            b["logs"].insert(0, {
                "id": str(uuid.uuid4()),
                "timestamp": int(time.time() * 1000),
                "type": log_type,
                "text": text,
                "code": code
            })
            b["logs"] = b["logs"][:50]
            save_db()

async def bot_worker(bot_cfg: dict):
    bot_id = bot_cfg["id"]
    owner_id = bot_cfg["ownerId"]
    
    if not check_license(owner_id):
        add_log(bot_id, "error", "Лицензия истекла. Бот не может быть запущен.", "LICENSE_EXPIRED")
        return

    try:
        token = bot_cfg["token"].strip()
        bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        dp = Dispatcher()
        active_bots[bot_id] = bot
        
        @dp.message(CommandStart())
        async def _start(m: Message):
            if not check_license(owner_id):
                await m.answer("⚠️ Работа бота приостановлена владельцем (истекла лицензия).")
                return
            await m.answer(bot_cfg.get("welcomeMessage", "Привет!"))

        @dp.message()
        async def _handle_all(m: Message):
            if not check_license(owner_id): return
            user_id = m.from_user.id
            admin_id = bot_cfg.get("adminChatId")
            if admin_id and str(user_id) == str(admin_id) and m.reply_to_message:
                reply_text = m.reply_to_message.text or m.reply_to_message.caption or ""
                match = re.search(r"ID: (\d+)", reply_text)
                if match:
                    target_user_id = int(match.group(1))
                    try: await bot.send_message(target_user_id, m.text or "Медиа"); return await m.reply("✅ Отправлено")
                    except: pass
            if admin_id and str(user_id) != str(admin_id):
                await bot.send_message(admin_id, f"📩 <b>Сообщение от {m.from_user.full_name}</b>\nID: {user_id}\n\n{m.text or '[Медиа]'}")

        add_log(bot_id, "system", "Инстанс запущен.")
        await dp.start_polling(bot)
    except Exception as e:
        add_log(bot_id, "error", f"Ошибка: {str(e)}")
    finally:
        if bot_id in active_bots: del active_bots[bot_id]

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_db()
    for b in db_content["bots"]:
        if b.get("status") == "RUNNING" and check_license(b["ownerId"]):
            active_tasks[b["id"]] = asyncio.create_task(bot_worker(b))
        elif b.get("status") == "RUNNING":
            b["status"] = "IDLE"
    save_db()
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/ping")
async def ping(): return {"status": "online"}

@app.post("/api/admin/generate-key")
async def admin_gen_key(req: KeyGenRequest, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET: raise HTTPException(403, "Invalid Admin Token")
    new_key = f"BOT-{req.months}-{secrets.token_hex(4).upper()}"
    db_content["issued_keys"].append({"key": new_key, "months": req.months, "used": False})
    save_db()
    return {"key": new_key}

@app.post("/api/license/activate")
async def activate_key(req: KeyActivationRequest):
    user = next((u for u in db_content["users"] if u["id"] == req.userId), None)
    if not user: raise HTTPException(404, "User not found")
    key_entry = next((k for k in db_content["issued_keys"] if k["key"] == req.key and not k["used"]), None)
    if not key_entry: raise HTTPException(400, "Неверный или использованный ключ")
    months = key_entry["months"]
    now = int(time.time() * 1000)
    current_expiry = user.get("licenseExpiresAt", now)
    new_expiry = max(current_expiry, now) + (months * 30 * 24 * 3600 * 1000)
    user["licenseExpiresAt"] = new_expiry
    key_entry["used"] = True
    key_entry["used_by"] = user["email"]
    save_db()
    return {"status": "ok", "newExpiry": new_expiry}

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    user = next((u for u in db_content["users"] if u["email"] == req.email and u["password"] == req.password), None)
    if not user: raise HTTPException(401)
    return user

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str): return [b for b in db_content["bots"] if b["ownerId"] == user_id]

@app.post("/api/bots/start/{bot_id}")
async def start_bot(bot_id: str):
    bot_cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not bot_cfg: raise HTTPException(404)
    if not check_license(bot_cfg["ownerId"]): raise HTTPException(403)
    if bot_id in active_tasks: return {"status": "ok"}
    active_tasks[bot_id] = asyncio.create_task(bot_worker(bot_cfg))
    bot_cfg["status"] = "RUNNING"
    save_db()
    return {"status": "ok"}

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    if bot_id in active_tasks: active_tasks[bot_id].cancel(); del active_tasks[bot_id]
    for b in db_content["bots"]:
        if b["id"] == bot_id: b["status"] = "IDLE"
    save_db()
    return {"status": "ok"}

@app.post("/api/bots/save")
async def save_bot_api(bot_data: dict):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == bot_data["id"]), -1)
    if idx >= 0: db_content["bots"][idx] = bot_data
    else: db_content["bots"].append(bot_data)
    save_db()
    return {"status": "ok"}

@app.delete("/api/bots/delete/{bot_id}")
async def delete_bot(bot_id: str):
    await stop_bot(bot_id)
    db_content["bots"] = [b for b in db_content["bots"] if b["id"] != bot_id]
    save_db()
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
