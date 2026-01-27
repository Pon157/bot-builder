
import asyncio
import logging
import json
import os
import time
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.exceptions import TelegramUnauthorizedError, TelegramNetworkError, TelegramConflictError
import uvicorn

# Настройка логирования для терминала
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BotEngine")

DB_FILE = "database.json"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Хранилище в памяти
db_content = {"users": [], "bots": []}
active_bots: Dict[str, Bot] = {}
active_tasks: Dict[str, asyncio.Task] = {}

class BroadcastModel(BaseModel):
    botIds: List[str]
    message: str

def save_db():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db_content, f, ensure_ascii=False, indent=2)

def load_db():
    global db_content
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                db_content = json.load(f)
        except Exception as e:
            logger.error(f"Error loading DB: {e}")
            db_content = {"users": [], "bots": []}

def add_log(bot_id: str, type: str, text: str):
    config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if config:
        if "logs" not in config: config["logs"] = []
        log_entry = {
            "id": str(time.time()),
            "timestamp": int(time.time() * 1000),
            "type": type,
            "text": text
        }
        config["logs"].insert(0, log_entry)
        config["logs"] = config["logs"][:50] # Храним только последние 50 записей
        save_db()

def get_keyboard(buttons):
    if not buttons: return None
    rows = []
    current_row = []
    for btn in buttons:
        current_row.append(KeyboardButton(text=btn['text']))
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []
    if current_row: rows.append(current_row)
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

async def bot_worker(bot_id: str, token: str):
    bot = Bot(token=token, parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    router = Router()
    active_bots[bot_id] = bot

    @router.message(CommandStart())
    async def cmd_start(m: types.Message):
        config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        welcome = config["welcomeMessage"] if config else "Hello!"
        kb = get_keyboard(config.get("buttons", [])) if config else None
        
        add_log(bot_id, "incoming", f"Команда /start от {m.from_user.full_name}")
        
        if config:
            user_entry = {"id": m.from_user.id, "first_name": m.from_user.first_name, "username": m.from_user.username}
            if "connectedUsers" not in config: config["connectedUsers"] = []
            if not any(u["id"] == m.from_user.id for u in config["connectedUsers"]):
                config["connectedUsers"].append(user_entry)
                config["usersCount"] = len(config["connectedUsers"])
                add_log(bot_id, "system", f"Новый пользователь: {m.from_user.full_name}")
                save_db()

        await m.answer(welcome, reply_markup=kb)

    @router.message()
    async def handle_all(m: types.Message):
        config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not config or not m.text: return
        
        add_log(bot_id, "incoming", f"Сообщение: {m.text} (от {m.from_user.full_name})")
        
        text = m.text.lower()
        # Проверка кнопок
        for btn in config.get("buttons", []):
            if btn["text"].lower() == text:
                add_log(bot_id, "outgoing", f"Ответ на кнопку: {btn['response']}")
                return await m.answer(btn["response"])
        
        # Проверка триггеров
        for trig in config.get("triggers", []):
            if trig["keyword"].lower() in text:
                add_log(bot_id, "outgoing", f"Ответ на триггер '{trig['keyword']}': {trig['response']}")
                return await m.answer(trig["response"])

    dp.include_router(router)
    
    try:
        add_log(bot_id, "info", "Запуск polling...")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except TelegramConflictError:
        add_log(bot_id, "error", "Конфликт: запущен другой экземпляр этого бота!")
        logger.error(f"Conflict error for bot {bot_id}")
    except Exception as e:
        add_log(bot_id, "error", f"Критический сбой: {str(e)}")
        logger.error(f"Bot {bot_id} crashed: {e}")
    finally:
        for b in db_content["bots"]:
            if b["id"] == bot_id: b["status"] = "IDLE"
        save_db()
        await bot.session.close()

# API Endpoints

@app.get("/api/ping")
async def ping(): return {"status": "online"}

@app.post("/api/auth/register")
async def register(user: dict):
    if any(u["email"] == user["email"] for u in db_content["users"]):
        raise HTTPException(status_code=400, detail="User exists")
    db_content["users"].append(user)
    save_db()
    return user

@app.post("/api/auth/login")
async def login(data: dict):
    user = next((u for u in db_content["users"] if u["email"] == data["email"] and u["password"] == data["password"]), None)
    if not user: raise HTTPException(status_code=401, detail="Invalid credentials")
    return user

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    return [b for b in db_content["bots"] if b["ownerId"] == user_id]

@app.post("/api/bots/save")
async def save_bot_endpoint(bot: dict):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == bot["id"]), -1)
    if idx >= 0:
        if not bot.get("connectedUsers"):
            bot["connectedUsers"] = db_content["bots"][idx].get("connectedUsers", [])
            bot["usersCount"] = len(bot["connectedUsers"])
        db_content["bots"][idx] = bot
    else:
        db_content["bots"].append(bot)
    save_db()
    
    if bot["id"] in active_tasks:
        add_log(bot["id"], "system", "Настройки изменены. Перезапуск...")
        await stop_bot(bot["id"])
        await start_bot(bot["id"])
    return {"status": "ok"}

@app.delete("/api/bots/delete/{user_id}/{bot_id}")
async def delete_bot(user_id: str, bot_id: str):
    await stop_bot(bot_id)
    db_content["bots"] = [b for b in db_content["bots"] if not (b["id"] == bot_id and b["ownerId"] == user_id)]
    save_db()
    return {"status": "ok"}

@app.post("/api/bots/start/{bot_id}")
async def start_bot(bot_id: str):
    bot_cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not bot_cfg: raise HTTPException(status_code=404, detail="Bot not found")
    
    if bot_id in active_tasks and not active_tasks[bot_id].done():
        return {"status": "ok", "message": "Already running"}

    # Проверка токена
    test_bot = Bot(token=bot_cfg["token"])
    try:
        me = await test_bot.get_me()
        add_log(bot_id, "info", f"Токен проверен: @{me.username}")
        await test_bot.session.close()
    except Exception as e:
        await test_bot.session.close()
        add_log(bot_id, "error", f"Ошибка проверки токена: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Ошибка токена: {str(e)}")

    active_tasks[bot_id] = asyncio.create_task(bot_worker(bot_id, bot_cfg["token"]))
    bot_cfg["status"] = "RUNNING"
    save_db()
    return {"status": "ok"}

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel()
        add_log(bot_id, "info", "Остановка бота пользователем...")
        try:
            await active_tasks[bot_id]
        except asyncio.CancelledError:
            pass
        del active_tasks[bot_id]
        
        if bot_id in active_bots:
            await active_bots[bot_id].session.close()
            del active_bots[bot_id]
            
        for b in db_content["bots"]:
            if b["id"] == bot_id: b["status"] = "IDLE"
        save_db()
    return {"status": "ok"}

@app.post("/api/broadcast")
async def broadcast(data: BroadcastModel):
    results = {"success": 0, "failed": 0}
    for bot_id in data.botIds:
        config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not config or bot_id not in active_bots: continue
        
        bot = active_bots[bot_id]
        add_log(bot_id, "system", f"Начало рассылки: {data.message[:20]}...")
        for user in config.get("connectedUsers", []):
            try:
                await bot.send_message(user["id"], data.message)
                results["success"] += 1
            except Exception as e:
                results["failed"] += 1
        add_log(bot_id, "system", f"Рассылка завершена. Успешно: {results['success']}")
    return results

@app.on_event("startup")
async def startup_event():
    load_db()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
