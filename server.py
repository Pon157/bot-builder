
import asyncio
import logging
import json
import os
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request
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

# Полная очистка CORS для предотвращения блокировок
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"REQ: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"RES: {response.status_code}")
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
        logger.error(f"DB Save Error: {e}")

def load_db():
    global db_content
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict) and "users" in loaded:
                    db_content = loaded
                    logger.info("Database loaded successfully")
        except Exception as e:
            logger.error(f"DB Load Error: {e}")

async def bot_worker(config_id: str):
    config = next((b for b in db_content["bots"] if b["id"] == config_id), None)
    if not config: return
    bot = Bot(token=config["token"], parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    router = Router()
    @router.message(CommandStart())
    async def cmd_start(m: types.Message):
        await m.answer(config["welcomeMessage"])
    dp.include_router(router)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

# --- ENDPOINTS ---

@app.get("/api/ping")
async def ping():
    return {"status": "online", "version": "1.0.1"}

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
    if idx >= 0: db_content["bots"][idx] = bot.dict()
    else: db_content["bots"].append(bot.dict())
    save_db()
    return {"status": "ok"}

@app.post("/api/bots/start/{bot_id}")
async def start_bot(bot_id: str):
    if bot_id not in active_tasks:
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
async def startup():
    load_db()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
