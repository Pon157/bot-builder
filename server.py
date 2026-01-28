import asyncio
import logging
import json
import os
import time
import re
import uuid
import sys
from contextlib import asynccontextmanager
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, Message
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
import uvicorn

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BotEngine")

def load_env_manual():
    """Синхронизированная загрузка .env для API"""
    paths = [os.path.join(os.getcwd(), '.env'), os.path.join(os.path.dirname(__file__), '.env')]
    for p in paths:
        if os.path.exists(p):
            with open(p, 'r') as f:
                for line in f:
                    if '=' in line and not line.startswith('#'):
                        k, v = line.split('=', 1)
                        os.environ[k.strip()] = v.strip().strip('"').strip("'")
            logger.info(f"Config loaded from {p}")
            break

load_env_manual()

DB_FILE = "database.json"
db_content = {"users": [], "bots": []}
active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}

# --- Models ---
class BroadcastRequest(BaseModel):
    botIds: List[str]
    message: str

class LoginRequest(BaseModel):
    email: str
    password: str

class KeyActivationRequest(BaseModel):
    userId: str
    key: str

class UserBase(BaseModel):
    id: str
    username: str
    email: str
    password: str
    licenseExpiresAt: int
    trialUsed: bool
    balance: float
    botsCreated: int

# --- DB Core ---
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
        except Exception as e: 
            logger.error(f"Load DB Error: {e}")
            db_content = {"users": [], "bots": []}

def add_bot_log(bot_id: str, log_type: str, text: str):
    bot = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if bot:
        if "logs" not in bot: bot["logs"] = []
        log_entry = {"id": str(uuid.uuid4()), "timestamp": int(time.time() * 1000), "type": log_type, "text": text}
        bot["logs"].insert(0, log_entry)
        bot["logs"] = bot["logs"][:50]

# --- Bot Runner Engine ---
async def bot_worker(bot_cfg: dict):
    bot_id = bot_cfg["id"]
    token = bot_cfg["token"].strip()
    
    try:
        bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        dp = Dispatcher()
        active_bots[bot_id] = bot
        
        add_bot_log(bot_id, "info", f"Запуск {bot_cfg['name']}...")

        @dp.message(CommandStart())
        async def cmd_start(message: Message):
            welcome = bot_cfg.get("welcomeMessage", "Привет!")
            await message.answer(welcome)

        @dp.message()
        async def handle_msg(message: Message):
            if not message.text: return
            text = message.text.lower()
            # Проверка кнопок и триггеров
            for btn in bot_cfg.get("buttons", []):
                if btn.get("text", "").lower() == text:
                    await message.answer(btn.get("response", "..."))
                    return
            
            admin_id = bot_cfg.get("adminChatId")
            if admin_id and str(message.from_user.id) != str(admin_id):
                try: await bot.send_message(admin_id, f"📩 Сообщение от {message.from_user.id}:\n{message.text}")
                except: pass

        add_bot_log(bot_id, "info", "Бот в сети.")
        await dp.start_polling(bot)
    except Exception as e:
        add_bot_log(bot_id, "error", f"Ошибка: {e}")
    finally:
        if bot_id in active_bots: del active_bots[bot_id]

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_db()
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/ping")
async def ping(): return {"status": "online"}

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    user = next((u for u in db_content["users"] if u["email"] == req.email and u["password"] == req.password), None)
    if not user: raise HTTPException(401, "Invalid credentials")
    return user

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    return [b for b in db_content["bots"] if b["ownerId"] == user_id]

@app.post("/api/bots/start/{bot_id}")
async def start_bot(bot_id: str):
    bot_cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not bot_cfg: raise HTTPException(404)
    if bot_id in active_tasks: return {"status": "already_running"}
    active_tasks[bot_id] = asyncio.create_task(bot_worker(bot_cfg))
    bot_cfg["status"] = "RUNNING"
    save_db()
    return {"status": "ok"}

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel()
        del active_tasks[bot_id]
    if bot_id in active_bots:
        await active_bots[bot_id].session.close()
        del active_bots[bot_id]
    for b in db_content["bots"]:
        if b["id"] == bot_id: b["status"] = "IDLE"
    save_db()
    return {"status": "ok"}

@app.post("/api/bots/save")
async def save_bot(bot_data: dict):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == bot_data["id"]), -1)
    if idx >= 0: db_content["bots"][idx] = bot_data
    else: db_content["bots"].append(bot_data)
    save_db()
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
