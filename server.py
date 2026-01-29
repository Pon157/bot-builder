
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
from pydantic import BaseModel, validator

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ContentType
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter

import uvicorn

# --- Инициализация окружения ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotEngineCore")

DB_FILE = "database.json"
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")

# --- База Данных ---
db_content = {"users": [], "bots": [], "issued_keys": [], "system_logs": []}
verification_store: Dict[str, dict] = {} 

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db_content, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"❌ Save DB Error: {e}")

def load_db():
    global db_content
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                db_content.update(loaded)
        except Exception as e:
            logger.error(f"❌ Load DB Error: {e}")

# --- Бот Воркер ---
active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}

async def bot_worker_task(bot_id: str, token: str):
    session = AiohttpSession()
    bot = Bot(token=token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    active_bots[bot_id] = bot
    dp = Dispatcher()
    
    @dp.message(CommandStart())
    async def cmd_start(m: Message):
        await m.answer("Бот запущен через BotEngine Pro!")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
        logger.info(f"Bot {bot_id} started polling")
    except Exception as e:
        logger.error(f"Error starting bot {bot_id}: {e}")
    finally:
        await session.close()
        active_tasks.pop(bot_id, None)

# --- API Router ---
api = APIRouter()

@api.get("/ping")
async def ping(): return {"status": "online"}

@api.post("/auth/login")
async def login(req: dict):
    email = req.get("email", "").lower().strip()
    password = req.get("password", "")
    u = next((u for u in db_content["users"] if u["email"].lower() == email and u["password"] == password), None)
    if not u: raise HTTPException(401, "Invalid credentials")
    return u

@api.post("/auth/verify-request")
@api.post("/auth/request-verification")
async def request_verification(req: dict):
    # Заглушка: в реальности тут должна быть отправка письма
    logger.info(f"Verification requested for: {req.get('email')}")
    return {"status": "ok"}

@api.post("/auth/register")
async def register(req: dict):
    email = req.get("email", "").lower().strip()
    username = req.get("username", "User")
    password = req.get("password")
    
    # Проверка на дубликат
    if any(u["email"].lower() == email for u in db_content["users"]):
        raise HTTPException(400, "User already exists")
    
    new_user = {
        "id": str(uuid.uuid4()),
        "username": username,
        "email": email,
        "password": password,
        "balance": 0,
        "licenseExpiresAt": int(time.time() * 1000) + (3 * 24 * 3600 * 1000) # 3 days trial
    }
    db_content["users"].append(new_user)
    save_db()
    return new_user

@api.post("/auth/forgot-password")
async def forgot_password(req: dict):
    return {"status": "ok"}

@api.post("/auth/reset-password")
async def reset_password(req: dict):
    return {"status": "ok"}

@api.get("/bots/{user_id}")
async def get_bots(user_id: str):
    res = [b for b in db_content["bots"] if str(b["ownerId"]) == str(user_id)]
    for b in res: 
        b["status"] = "RUNNING" if b["id"] in active_tasks else "IDLE"
    return res

@api.post("/bots/save")
async def save_bot_api(bot_data: dict):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == bot_data["id"]), -1)
    if idx >= 0: db_content["bots"][idx] = bot_data
    else: db_content["bots"].append(bot_data)
    save_db()
    return {"status": "ok"}

@api.post("/bots/start/{bot_id}")
async def start_bot(bot_id: str):
    bot_data = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not bot_data: raise HTTPException(404, "Bot not found")
    
    if bot_id in active_tasks:
        return {"status": "already_running"}
    
    token = bot_data.get("token")
    if not token: raise HTTPException(400, "Token missing")
    
    task = asyncio.create_task(bot_worker_task(bot_id, token))
    active_tasks[bot_id] = task
    return {"status": "ok"}

@api.post("/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    task = active_tasks.pop(bot_id, None)
    if task:
        task.cancel()
        return {"status": "ok"}
    return {"status": "not_running"}

@api.delete("/bots/delete/{bot_id}")
async def delete_bot(bot_id: str):
    db_content["bots"] = [b for b in db_content["bots"] if b["id"] != bot_id]
    save_db()
    await stop_bot(bot_id)
    return {"status": "ok"}

@api.post("/broadcast")
async def broadcast(req: dict):
    bot_ids = req.get("botIds", [])
    message = req.get("message", "")
    # Реализация рассылки в воркере...
    return {"success": 0, "failed": len(bot_ids)}

@api.post("/license/activate")
async def activate_license(req: dict):
    return {"status": "error", "message": "Invalid key"}

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_db()
    yield
    for t in active_tasks.values(): t.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_methods=["*"], 
    allow_headers=["*"],
    allow_credentials=True
)

# Регистрируем роутер с префиксом /api и без него для гибкости проксирования
app.include_router(api, prefix="/api")
app.include_router(api)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
