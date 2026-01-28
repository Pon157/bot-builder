import asyncio
import logging
import json
import os
import time
import re
import uuid
from contextlib import asynccontextmanager
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, Message
from aiogram.client.default import DefaultBotProperties
import uvicorn

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BotEngine")

def load_env_at_all_costs():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cwd = os.getcwd()
    search_locations = [os.path.join(cwd, '.env'), os.path.join(script_dir, '.env')]
    for path in search_locations:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'): continue
                    if '=' in line:
                        k, v = line.split('=', 1)
                        os.environ[k.strip()] = v.strip().strip('"').strip("'")
            return True
    return False

load_env_at_all_costs()

DB_FILE = "database.json"
db_content = {"users": [], "bots": []}
active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}

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
            db_content = {"users": [], "bots": []}

# --- Workers ---
async def bot_worker(bot_cfg: dict):
    bot_id = bot_cfg["id"]
    try:
        bot = Bot(token=bot_cfg["token"].strip(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        dp = Dispatcher()
        active_bots[bot_id] = bot
        
        @dp.message(CommandStart())
        async def _start(m: Message):
            await m.answer(bot_cfg.get("welcomeMessage", "Привет!"))

        @dp.message()
        async def _echo(m: Message):
            if not m.text: return
            for btn in bot_cfg.get("buttons", []):
                if btn.get("text", "").lower() == m.text.lower():
                    return await m.answer(btn.get("response", "...") )
            
            admin = bot_cfg.get("adminChatId")
            if admin:
                try: await bot.send_message(admin, f"📩 Сообщение от {m.from_user.id}:\n{m.text}")
                except: pass

        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Bot Worker {bot_id} Error: {e}")
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
    if not user: raise HTTPException(401)
    return user

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    return [b for b in db_content["bots"] if b["ownerId"] == user_id]

@app.post("/api/bots/start/{bot_id}")
async def start_bot(bot_id: str):
    bot_cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not bot_cfg: raise HTTPException(404)
    if bot_id in active_tasks: return {"status": "ok"}
    active_tasks[bot_id] = asyncio.create_task(bot_worker(bot_cfg))
    bot_cfg["status"] = "RUNNING"
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
