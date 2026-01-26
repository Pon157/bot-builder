
import asyncio
import logging
import json
import os
import uuid
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
import uvicorn

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("BotEngine")

DB_FILE = "database.json"

app = FastAPI(title="BotEngine Pro API")

# Исправленный CORS: нельзя использовать allow_credentials=True с ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware для логирования всех запросов (поможет понять, доходят ли данные)
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Incoming request: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Response status: {response.status_code}")
    return response

# Хранилище
db_content = {"users": [], "bots": []}
active_tasks: Dict[str, asyncio.Task] = {}

class UserModel(BaseModel):
    id: str
    username: str
    email: str
    password: str
    subscription: str = "FREE"
    balance: float = 0.0
    botsCreated: int = 0

class LoginModel(BaseModel):
    email: str
    password: str

class BotConfigModel(BaseModel):
    id: str
    ownerId: str
    name: str
    token: str
    status: str
    welcomeMessage: str
    triggers: List[dict]
    buttons: List[dict]
    adminChatId: Optional[str] = ""

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db_content, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Save DB Error: {e}")

def load_db():
    global db_content
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict) and "users" in loaded:
                    db_content = loaded
                    logger.info(f"DB loaded: {len(db_content['users'])} users, {len(db_content['bots'])} bots")
        except Exception as e:
            logger.error(f"Load DB Error: {e}")

async def bot_worker(config_id: str):
    config = next((b for b in db_content["bots"] if b["id"] == config_id), None)
    if not config: return

    logger.info(f"Starting worker for bot: {config['name']} ({config_id})")
    bot = Bot(token=config["token"], parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    router = Router()

    @router.message(CommandStart())
    async def cmd_start(message: types.Message):
        kb = []
        if config.get("buttons"):
            row = []
            for btn in config["buttons"]:
                row.append(types.KeyboardButton(text=btn['text']))
                if len(row) == 2: kb.append(row); row = []
            if row: kb.append(row)
        reply_markup = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True) if kb else None
        await message.answer(config["welcomeMessage"], reply_markup=reply_markup)

    @router.message()
    async def handle_all(message: types.Message):
        text = (message.text or "").lower()
        for trig in config.get("triggers", []):
            if trig['keyword'].lower() in text:
                await message.answer(trig['response'])
                return
        for btn in config.get("buttons", []):
            if btn['text'].lower() == text:
                await message.answer(btn['response'])
                return

    dp.include_router(router)
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Polling error in bot {config_id}: {e}")
    finally:
        await bot.session.close()

# --- API ---

@app.post("/api/auth/register")
async def register(user: UserModel):
    if any(u["email"] == user.email for u in db_content["users"]):
        raise HTTPException(status_code=400, detail="User already exists")
    db_content["users"].append(user.dict())
    save_db()
    return user

@app.post("/api/auth/login")
async def login(data: LoginModel):
    user = next((u for u in db_content["users"] if u["email"] == data.email and u["password"] == data.password), None)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return user

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    return [b for b in db_content["bots"] if b["ownerId"] == user_id]

@app.post("/api/bots/save")
async def save_bot(bot: BotConfigModel):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == bot.id), -1)
    if idx >= 0:
        db_content["bots"][idx] = bot.dict()
    else:
        db_content["bots"].append(bot.dict())
    save_db()
    return {"status": "ok"}

@app.delete("/api/bots/{bot_id}")
async def delete_bot(bot_id: str):
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel()
        del active_tasks[bot_id]
    db_content["bots"] = [b for b in db_content["bots"] if b["id"] != bot_id]
    save_db()
    return {"status": "deleted"}

@app.post("/api/bots/start/{bot_id}")
async def start_bot(bot_id: str):
    if bot_id in active_tasks: return {"status": "already_running"}
    config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not config: raise HTTPException(status_code=404)
    active_tasks[bot_id] = asyncio.create_task(bot_worker(bot_id))
    for b in db_content["bots"]:
        if b["id"] == bot_id: b["status"] = "RUNNING"
    save_db()
    return {"status": "started"}

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel()
        del active_tasks[bot_id]
    for b in db_content["bots"]:
        if b["id"] == bot_id: b["status"] = "IDLE"
    save_db()
    return {"status": "stopped"}

@app.on_event("startup")
async def startup_event():
    load_db()
    for b in db_content["bots"]:
        if b.get("status") == "RUNNING":
            active_tasks[b["id"]] = asyncio.create_task(bot_worker(b["id"]))

if __name__ == "__main__":
    logger.info("Starting BotEngine Server on 0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
