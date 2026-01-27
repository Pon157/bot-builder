
import asyncio
import logging
import json
import os
import time
from typing import Dict, List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.exceptions import TelegramUnauthorizedError, TelegramNetworkError, TelegramConflictError
from aiogram.client.session.aiohttp import AiohttpSession
import uvicorn

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BotEngine")

DB_FILE = "database.json"

# Хранилище в памяти
db_content = {"users": [], "bots": []}
active_tasks: Dict[str, asyncio.Task] = {}

class BroadcastModel(BaseModel):
    botIds: List[str]
    message: str

def save_db():
    """Синхронное сохранение БД (вызывается аккуратно)"""
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db_content, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving DB: {e}")

def load_db():
    global db_content
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                db_content = json.load(f)
        except Exception as e:
            logger.error(f"Error loading DB: {e}")
            db_content = {"users": [], "bots": []}

def add_log(bot_id: str, log_type: str, text: str):
    config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if config:
        if "logs" not in config: config["logs"] = []
        log_entry = {
            "id": str(time.time()),
            "timestamp": int(time.time() * 1000),
            "type": log_type,
            "text": text
        }
        config["logs"].insert(0, log_entry)
        config["logs"] = config["logs"][:50]
        # Не сохраняем файл на каждый лог, чтобы не нагружать диск. 
        # Сохранение произойдет при изменении статуса или конфига.

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
    """Изолированный воркер для одного бота"""
    session = AiohttpSession()
    bot = Bot(token=token, session=session, parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    router = Router()

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
        add_log(bot_id, "incoming", f"Текст: {m.text}")
        text = m.text.lower()
        for btn in config.get("buttons", []):
            if btn["text"].lower() == text:
                return await m.answer(btn["response"])
        for trig in config.get("triggers", []):
            if trig["keyword"].lower() in trig["keyword"].lower() in text:
                return await m.answer(trig["response"])

    dp.include_router(router)
    
    try:
        add_log(bot_id, "info", "Шаг 1: Очистка старых вебхуков...")
        await bot.delete_webhook(drop_pending_updates=True)
        
        add_log(bot_id, "info", "Шаг 2: Проверка авторизации...")
        me = await bot.get_me()
        add_log(bot_id, "info", f"Шаг 3: Бот @{me.username} готов к работе.")
        
        add_log(bot_id, "info", "Шаг 4: Запуск прослушивания (Polling)...")
        await dp.start_polling(bot, skip_updates=True)
        
    except asyncio.CancelledError:
        add_log(bot_id, "info", "Процесс бота был принудительно остановлен.")
    except TelegramUnauthorizedError:
        add_log(bot_id, "error", "Критическая ошибка: Токен недействителен!")
    except TelegramConflictError:
        add_log(bot_id, "error", "Ошибка: Обнаружен конфликт сессий. Пожалуйста, подождите 10 секунд.")
    except Exception as e:
        add_log(bot_id, "error", f"Ошибка воркера: {str(e)}")
        logger.exception(f"Worker for {bot_id} crashed")
    finally:
        add_log(bot_id, "info", "Сессия закрыта. Бот отключен.")
        await session.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    load_db()
    # Восстановление ботов, которые должны быть запущены
    for b in db_content["bots"]:
        if b.get("status") == "RUNNING":
            active_tasks[b["id"]] = asyncio.create_task(bot_worker(b["id"], b["token"]))
    yield
    # Shutdown
    for task in active_tasks.values():
        task.cancel()
    await asyncio.gather(*active_tasks.values(), return_exceptions=True)

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Endpoints

@app.get("/api/ping")
async def ping(): return {"status": "online"}

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
    was_running = False
    
    if idx >= 0:
        was_running = db_content["bots"][idx].get("status") == "RUNNING"
        # Сохраняем пользователей
        bot["connectedUsers"] = db_content["bots"][idx].get("connectedUsers", [])
        bot["usersCount"] = len(bot["connectedUsers"])
        db_content["bots"][idx] = bot
    else:
        db_content["bots"].append(bot)
    
    save_db()
    
    if was_running:
        add_log(bot["id"], "system", "Перезапуск по требованию (настройки изменены)")
        await stop_bot(bot["id"])
        await asyncio.sleep(1) # Важная пауза
        await start_bot(bot["id"])
        
    return {"status": "ok"}

@app.post("/api/bots/start/{bot_id}")
async def start_bot(bot_id: str):
    bot_cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not bot_cfg: raise HTTPException(status_code=404, detail="Bot not found")
    
    # Очистка старых задач
    if bot_id in active_tasks:
        if not active_tasks[bot_id].done():
            active_tasks[bot_id].cancel()
            try:
                await asyncio.wait_for(active_tasks[bot_id], timeout=2)
            except: pass
        del active_tasks[bot_id]

    active_tasks[bot_id] = asyncio.create_task(bot_worker(bot_id, bot_cfg["token"]))
    bot_cfg["status"] = "RUNNING"
    save_db()
    return {"status": "ok"}

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel()
        try:
            await asyncio.wait_for(active_tasks[bot_id], timeout=3)
        except: pass
        if bot_id in active_tasks: del active_tasks[bot_id]
            
    for b in db_content["bots"]:
        if b["id"] == bot_id: b["status"] = "IDLE"
    save_db()
    return {"status": "ok"}

@app.post("/api/broadcast")
async def broadcast(data: BroadcastModel):
    # Упрощенная рассылка через временную сессию
    results = {"success": 0, "failed": 0}
    for bot_id in data.botIds:
        config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not config: continue
        
        async with Bot(token=config["token"]).context() as bot:
            for user in config.get("connectedUsers", []):
                try:
                    await bot.send_message(user["id"], data.message)
                    results["success"] += 1
                except:
                    results["failed"] += 1
    return results

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
