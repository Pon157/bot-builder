
import asyncio
import logging
import json
import os
import time
import re
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, Message
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
import uvicorn

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BotEngine")

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
                logger.info(f"Database loaded: {len(db_content['users'])} users, {len(db_content['bots'])} bots")
        except Exception as e: 
            logger.error(f"Load DB Error: {e}")
            db_content = {"users": [], "bots": []}

def add_bot_log(bot_id: str, log_type: str, text: str):
    bot = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if bot:
        if "logs" not in bot: bot["logs"] = []
        log_entry = {
            "id": str(uuid.uuid4()),
            "timestamp": int(time.time() * 1000),
            "type": log_type,
            "text": text
        }
        bot["logs"].insert(0, log_entry)
        bot["logs"] = bot["logs"][:50] # Храним последние 50 логов

# --- Bot Runner Engine ---

async def bot_worker(bot_cfg: dict):
    bot_id = bot_cfg["id"]
    token = bot_cfg["token"]
    
    try:
        bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        dp = Dispatcher()
        active_bots[bot_id] = bot
        
        add_bot_log(bot_id, "info", f"Инициализация инстанса {bot_cfg['name']}...")

        # Клавиатура из настроек
        def get_main_kb():
            buttons = bot_cfg.get("buttons", [])
            if not buttons: return None
            builder = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text=btn["text"])] for btn in buttons],
                resize_keyboard=True
            )
            return builder

        @dp.message(CommandStart())
        async def cmd_start(message: Message):
            welcome = bot_cfg.get("welcomeMessage", "Привет!")
            await message.answer(welcome, reply_markup=get_main_kb())
            add_bot_log(bot_id, "incoming", f"User {message.from_user.id} triggered /start")

        @dp.message()
        async def handle_all_messages(message: Message):
            if not message.text: return
            text = message.text.lower()
            
            # 1. Проверка кнопок
            for btn in bot_cfg.get("buttons", []):
                if btn["text"].lower() == text:
                    await message.answer(btn["response"])
                    add_bot_log(bot_id, "outgoing", f"Ответ на кнопку: {btn['text']}")
                    return

            # 2. Проверка триггеров
            for trig in bot_cfg.get("triggers", []):
                if trig["keyword"].lower() in text:
                    await message.answer(trig["response"])
                    add_bot_log(bot_id, "outgoing", f"Сработал триггер: {trig['keyword']}")
                    return

            # 3. Пересылка админу (Feedback)
            admin_id = bot_cfg.get("adminChatId")
            if admin_id and str(message.from_user.id) != str(admin_id):
                try:
                    info = f"👤 <b>Сообщение от юзера</b>\nID: <code>{message.from_user.id}</code>\nName: {message.from_user.full_name}\n\n{message.text}"
                    await bot.send_message(admin_id, info)
                except: pass

        add_bot_log(bot_id, "info", "Бот успешно запущен и слушает сообщения.")
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.error(f"Bot {bot_id} Error: {e}")
        add_bot_log(bot_id, "error", f"Ошибка запуска: {str(e)}")
        # Обновляем статус в БД
        for b in db_content["bots"]:
            if b["id"] == bot_id: b["status"] = "ERROR"
        save_db()
    finally:
        if bot_id in active_bots: del active_bots[bot_id]

# --- License Guard ---

async def license_checker_loop():
    while True:
        try:
            now = int(time.time() * 1000)
            for bot_cfg in db_content["bots"]:
                owner = next((u for u in db_content["users"] if u["id"] == bot_cfg["ownerId"]), None)
                if owner and owner.get("licenseExpiresAt", 0) < now and bot_cfg["id"] in active_tasks:
                    logger.info(f"License expired for {bot_cfg['id']}")
                    active_tasks[bot_cfg["id"]].cancel()
                    del active_tasks[bot_cfg["id"]]
                    bot_cfg["status"] = "IDLE"
                    add_bot_log(bot_cfg["id"], "system", "Бот остановлен: срок лицензии истек.")
            save_db()
        except Exception as e: logger.error(f"Checker error: {e}")
        await asyncio.sleep(600)

# --- API Endpoints ---

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/ping")
async def ping(): return {"status": "online"}

@app.post("/api/auth/register")
async def register(user: UserBase):
    if any(u["email"] == user.email for u in db_content["users"]):
        raise HTTPException(status_code=400, detail="User already exists")
    user_dict = user.dict()
    db_content["users"].append(user_dict)
    save_db()
    return user_dict

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    user = next((u for u in db_content["users"] if u["email"] == req.email and u["password"] == req.password), None)
    if not user: raise HTTPException(status_code=401, detail="Invalid credentials")
    return user

@app.post("/api/license/activate")
async def activate_key(req: KeyActivationRequest):
    user = next((u for u in db_content["users"] if u["id"] == req.userId), None)
    if not user: raise HTTPException(404, "Пользователь не найден")
    match = re.match(r"BOT-(\d+)-(\w+)", req.key.upper())
    if not match: raise HTTPException(400, "Неверный формат ключа")
    months = int(match.group(1))
    now_ms = int(time.time() * 1000)
    current_expiry = max(user.get("licenseExpiresAt", 0), now_ms)
    new_expiry = current_expiry + (months * 30 * 24 * 60 * 60 * 1000)
    user["licenseExpiresAt"] = new_expiry
    save_db()
    return {"status": "ok", "newExpiry": new_expiry}

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    return [b for b in db_content["bots"] if b["ownerId"] == user_id]

@app.post("/api/bots/start/{bot_id}")
async def start_bot_endpoint(bot_id: str):
    bot_cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not bot_cfg: raise HTTPException(404)
    
    owner = next((u for u in db_content["users"] if u["id"] == bot_cfg["ownerId"]), None)
    if not owner or owner.get("licenseExpiresAt", 0) < int(time.time() * 1000):
        raise HTTPException(403, "Лицензия истекла.")
        
    if bot_id in active_tasks: return {"status": "ok"}
    
    # Запускаем фоновую задачу
    task = asyncio.create_task(bot_worker(bot_cfg))
    active_tasks[bot_id] = task
    bot_cfg["status"] = "RUNNING"
    save_db()
    return {"status": "ok"}

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot_endpoint(bot_id: str):
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
async def save_bot_endpoint(bot_data: dict):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == bot_data["id"]), -1)
    if idx >= 0: db_content["bots"][idx] = bot_data
    else: db_content["bots"].append(bot_data)
    save_db()
    return {"status": "ok"}

@app.delete("/api/bots/delete/{bot_id}")
async def delete_bot_endpoint(bot_id: str):
    await stop_bot_endpoint(bot_id)
    db_content["bots"] = [b for b in db_content["bots"] if b["id"] != bot_id]
    save_db()
    return {"status": "ok"}

@app.post("/api/broadcast")
async def broadcast_endpoint(req: BroadcastRequest):
    success, failed = 0, 0
    # Эта логика требует отдельной реализации рассылки по базе пользователей каждого бота
    return {"success": success, "failed": failed}

@app.on_event("startup")
async def startup_event():
    load_db()
    asyncio.create_task(license_checker_loop())

if __name__ == "__main__":
    from aiogram.client.default import DefaultBotProperties
    uvicorn.run(app, host="0.0.0.0", port=8000)
