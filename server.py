
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
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any

from fastapi import FastAPI, HTTPException, Header, Request, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties

import uvicorn
try:
    from email_service import EmailService
except ImportError:
    class EmailService:
        @staticmethod
        def send_verification_code(e, c): return True
        @staticmethod
        def send_password_reset(e, c): return True

# --- CONFIG ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BotEngine")

DB_FILE = "database.json"
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")

# --- DATABASE ---
db_content = {"users": [], "bots": [], "issued_keys": []}
verification_store = {}

def save_db():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db_content, f, ensure_ascii=False, indent=2)

def load_db():
    global db_content
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            db_content.update(json.load(f))

# --- BOT LOGIC ---
active_tasks = {}
active_bots = {}

async def bot_worker_task(bot_id: str, token: str):
    session = AiohttpSession()
    bot = Bot(token=token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    active_bots[bot_id] = bot
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def start(m: Message):
        bot_cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not bot_cfg: return
        
        # Регистрация юзера
        if "connectedUsers" not in bot_cfg: bot_cfg["connectedUsers"] = []
        if not any(u["id"] == m.from_user.id for u in bot_cfg["connectedUsers"]):
            bot_cfg["connectedUsers"].append({
                "id": m.from_user.id, "first_name": m.from_user.first_name, 
                "username": m.from_user.username, "joined_at": int(time.time()),
                "is_banned": False, "warns": 0, "is_active": True
            })
            save_db()

        welcome = bot_cfg.get("welcomeMessage", "Привет!")
        btns = bot_cfg.get("buttons", [])
        kb = None
        if btns:
            rows = [[KeyboardButton(text=b["text"])] for b in btns if b.get("text")]
            kb = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
        await m.answer(welcome, reply_markup=kb)

    @dp.message()
    async def handle(m: Message):
        bot_cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not bot_cfg: return
        admin_id = bot_cfg.get("adminChatId")

        # Ответ админа юзеру
        if admin_id and str(m.chat.id) == str(admin_id) and m.reply_to_message:
            match = re.search(r"ID: (\d+)", m.reply_to_message.text or m.reply_to_message.caption or "")
            if match:
                try:
                    await bot.copy_message(int(match.group(1)), m.chat.id, m.message_id)
                except: pass
            return

        # Кнопки
        if m.text:
            for btn in bot_cfg.get("buttons", []):
                if btn.get("text") and btn["text"].lower() == m.text.lower():
                    if btn.get("type") == "request" and admin_id:
                        info = f"📩 Обращение: {btn['text']}\n👤 {m.from_user.full_name}\n🆔 ID: {m.from_user.id}"
                        await bot.send_message(admin_id, info)
                    await m.answer(btn.get("response", "Принято"))
                    return

        # Пересылка админу (Livegram)
        if admin_id:
            info = f"👤 <b>{m.from_user.full_name}</b>\n🆔 ID: <code>{m.from_user.id}</code>"
            await bot.send_message(admin_id, info)
            await bot.copy_message(admin_id, m.chat.id, m.message_id)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await session.close()

# --- API ---
api = APIRouter()

@api.get("/ping")
async def ping(): return {"status": "online"}

@api.post("/auth/login")
async def login(req: dict):
    u = next((u for u in db_content["users"] if u["email"].lower() == req["email"].lower() and u["password"] == req["password"]), None)
    if not u: raise HTTPException(401, "Неверные данные")
    return u

@api.post("/auth/verify-request")
async def verify_req(req: dict):
    email = req["email"].lower()
    code = str(random.randint(100000, 999999))
    if EmailService.send_verification_code(email, code):
        verification_store[email] = {"code": code, "exp": time.time() + 600}
        return {"status": "ok"}
    raise HTTPException(500, "Ошибка почты")

@api.post("/auth/register")
async def register(req: dict):
    email = req["email"].lower()
    if email not in verification_store or verification_store[email]["code"] != req["code"]:
        raise HTTPException(400, "Неверный код")
    
    new_user = {
        "id": str(uuid.uuid4()), "username": req["username"], "email": email, "password": req["password"],
        "balance": 0, "botsCreated": 0, "licenseExpiresAt": int(time.time() * 1000) + 259200000
    }
    db_content["users"].append(new_user)
    save_db()
    return new_user

@api.get("/bots/{user_id}")
async def get_bots(user_id: str):
    bots = [b for b in db_content["bots"] if str(b["ownerId"]) == str(user_id)]
    for b in bots:
        b["status"] = "RUNNING" if b["id"] in active_tasks else "IDLE"
    return bots

@api.post("/bots/save")
async def save_bot_api(bot_data: dict):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == bot_data["id"]), -1)
    if idx >= 0: db_content["bots"][idx] = bot_data
    else: db_content["bots"].append(bot_data)
    save_db()
    return {"status": "ok"}

@api.post("/bots/start/{bot_id}")
async def start_bot_api(bot_id: str):
    cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not cfg: raise HTTPException(404)
    if bot_id in active_tasks: active_tasks[bot_id].cancel()
    active_tasks[bot_id] = asyncio.create_task(bot_worker_task(bot_id, cfg["token"]))
    return {"status": "ok"}

@api.post("/bots/stop/{bot_id}")
async def stop_bot_api(bot_id: str):
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel()
        del active_tasks[bot_id]
    return {"status": "ok"}

@api.delete("/bots/delete/{bot_id}")
async def del_bot_api(bot_id: str):
    if bot_id in active_tasks: active_tasks[bot_id].cancel()
    db_content["bots"] = [b for b in db_content["bots"] if b["id"] != bot_id]
    save_db()
    return {"status": "ok"}

@api.post("/admin/generate-key")
async def gen_key(req: dict, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET: raise HTTPException(403)
    key = f"BOT-{req['months']}-{secrets.token_hex(3).upper()}"
    db_content["issued_keys"].append({"key": key, "months": req["months"], "used": False})
    save_db()
    return {"key": key}

@api.post("/license/activate")
async def activate_lic(req: dict):
    bot = next((b for b in db_content["bots"] if b["id"] == req["botId"]), None)
    key_obj = next((k for k in db_content["issued_keys"] if k["key"] == req["key"] and not k["used"]), None)
    if not bot or not key_obj: raise HTTPException(400, "Неверный ключ")
    
    now = int(time.time() * 1000)
    current = max(bot.get("licenseExpiresAt", now), now)
    bot["licenseExpiresAt"] = current + (key_obj["months"] * 30 * 24 * 3600 * 1000)
    key_obj["used"] = True
    save_db()
    return {"status": "ok", "newExpiry": bot["licenseExpiresAt"]}

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_db()
    yield
    for t in active_tasks.values(): t.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Регистрируем роутер ДВАЖДЫ для исключения 404/405
app.include_router(api, prefix="/api")
app.include_router(api)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
