
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
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any, Union

from fastapi import FastAPI, HTTPException, Header, Request, Depends, BackgroundTasks, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode, ContentType
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError

import uvicorn

# --- ENV LOADING ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_env_vars():
    env_path = os.path.join(BASE_DIR, '.env')
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8-sig') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        os.environ[k.strip()] = v.strip().strip('"').strip("'")
        except Exception as e:
            print(f"Error loading .env: {e}")

load_env_vars()

try:
    from email_service import EmailService
except ImportError:
    class EmailService:
        @staticmethod
        def send_verification_code(e, c): return False

# --- CONFIG ---
DB_FILE = os.path.join(BASE_DIR, "database.json")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotEngine.Core")

# --- MODELS ---
class AuthRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    code: str

class BotSaveRequest(BaseModel):
    id: str
    ownerId: str
    name: str
    token: str
    adminChatId: Optional[str] = ""
    welcomeMessage: str = "Привет!"
    buttons: List[Any] = []
    triggers: List[Any] = []
    settings: Dict[str, Any] = {}

# --- DATABASE ---
db_content = {"users": [], "bots": [], "issued_keys": [], "verification_codes": {}}

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db_content, f, ensure_ascii=False, indent=2)
    except Exception as e: logger.error(f"Save DB Error: {e}")

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                db_content.update(json.load(f))
        except Exception as e: logger.error(f"Load DB Error: {e}")

# --- WORKER ---
active_tasks = {}
active_bots = {}

async def start_bot_worker(bot_id: str, token: str):
    logger.info(f"Starting bot worker: {bot_id}")
    session = AiohttpSession()
    bot = Bot(token=token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    active_bots[bot_id] = bot
    dp = Dispatcher()
    
    @dp.message(CommandStart())
    async def h_start(m: Message):
        cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not cfg: return
        await m.answer(cfg.get("welcomeMessage", "Привет!"))

    @dp.message()
    async def h_main(m: Message):
        cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not cfg or not cfg.get("adminChatId"): return
        # Simple Livegram logic
        if str(m.chat.id) != str(cfg["adminChatId"]):
            header = f"📩 Сообщение от {m.from_user.full_name} (ID: {m.from_user.id})"
            await bot.send_message(cfg["adminChatId"], header)
            await bot.copy_message(cfg["adminChatId"], m.chat.id, m.message_id)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await session.close()
        active_bots.pop(bot_id, None)

# --- API ---
app = FastAPI()

# Разрешаем CORS максимально широко для отладки
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Логгер для каждого запроса (поможет увидеть 405/404)
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    logger.info(f"Request: {request.method} {request.url.path} - Status: {response.status_code} - Time: {duration:.2f}s")
    return response

api = APIRouter(prefix="/api")

@api.get("/ping")
async def ping():
    return {"status": "ok", "active_bots": len(active_bots), "time": int(time.time())}

@api.post("/auth/request-verification")
async def req_ver(req: Dict[str, str], bg: BackgroundTasks):
    email = req.get("email", "").lower().strip()
    if not email: raise HTTPException(400, "Email required")
    code = "".join([str(random.randint(0, 9)) for _ in range(6)])
    db_content["verification_codes"][email] = {"code": code, "expires": time.time() + 600}
    bg.add_task(EmailService.send_verification_code, email, code)
    return {"status": "ok"}

@api.post("/auth/verify-and-register")
async def register(req: RegisterRequest):
    email = req.email.lower().strip()
    v = db_content["verification_codes"].get(email)
    if not v or v["code"] != req.code:
        raise HTTPException(400, "Неверный или просроченный код")
    
    if any(u["email"] == email for u in db_content["users"]):
        raise HTTPException(400, "Email уже занят")
        
    user = {
        "id": str(uuid.uuid4()), "username": req.username, "email": email, "password": req.password, 
        "balance": 0, "licenseExpiresAt": int((datetime.now() + timedelta(days=3)).timestamp()*1000)
    }
    db_content["users"].append(user)
    save_db()
    return user

@api.post("/auth/login")
async def login(req: AuthRequest):
    email = req.email.lower().strip()
    u = next((u for u in db_content["users"] if u["email"] == email and u["password"] == req.password), None)
    if not u: raise HTTPException(401, "Неверный Email или пароль")
    return u

@api.get("/bots/{uid}")
async def get_bots(uid: str):
    user_bots = [b for b in db_content["bots"] if str(b["ownerId"]) == str(uid)]
    for b in user_bots:
        b["status"] = "RUNNING" if b["id"] in active_tasks and not active_tasks[b["id"]].done() else "IDLE"
    return user_bots

@api.post("/bots/save")
async def save_bot_api(bdata: BotSaveRequest):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == bdata.id), -1)
    if idx >= 0: db_content["bots"][idx] = bdata.dict()
    else: db_content["bots"].append(bdata.dict())
    save_db()
    return {"status": "ok"}

@api.post("/bots/start/{bid}")
async def start_api(bid: str):
    c = next((b for b in db_content["bots"] if b["id"] == bid), None)
    if not c: raise HTTPException(404)
    if bid not in active_tasks or active_tasks[bid].done():
        active_tasks[bid] = asyncio.create_task(start_bot_worker(bid, c["token"]))
    return {"status": "ok"}

@api.post("/bots/stop/{bid}")
async def stop_api(bid: str):
    t = active_tasks.pop(bid, None)
    if t: t.cancel()
    return {"status": "ok"}

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_db()
    yield
    for t in active_tasks.values(): t.cancel()

app.include_router(api)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
