
import asyncio
import logging
import json
import os
import time
import re
import uuid
import secrets
import sys
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException, Header, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ContentType
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
import uvicorn

# --- Загрузка окружения ---
def manual_load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8-sig') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and value:
                        os.environ[key] = value
            return True
        except Exception as e:
            print(f"Error loading .env: {e}")
    return False

manual_load_env()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotEngineCore")

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

from email_service import EmailService

# --- Константы ---
DB_FILE = "database.json"
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Инициализация Supabase
supabase: Optional['Client'] = None
if SUPABASE_AVAILABLE and SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("✅ Supabase подключен (Источник правды)")
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Supabase: {e}")

# Временное хранилище
verification_codes: Dict[str, dict] = {}
reset_codes: Dict[str, dict] = {}
db_content = {"users": [], "bots": [], "issued_keys": []}

# --- Логика БД ---

async def sync_to_supabase(table: str, data: Any):
    if not supabase: return
    try:
        payload = data if isinstance(data, list) else [data]
        if not payload: return
        supabase.table(table).upsert(payload).execute()
    except Exception as e:
        logger.error(f"❌ Ошибка синхронизации в Supabase ({table}): {e}")

def save_db_local():
    """Сохраняем локальный кэш только для подстраховки воркеров"""
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db_content, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"❌ Local Save Error: {e}")

async def load_db_full():
    """Жесткая загрузка из Supabase при старте"""
    global db_content
    if supabase:
        try:
            logger.info("🔄 Полная синхронизация с облаком...")
            users = supabase.table("users").select("*").execute()
            bots = supabase.table("bots").select("*").execute()
            keys = supabase.table("issued_keys").select("*").execute()
            
            db_content["users"] = users.data or []
            db_content["bots"] = bots.data or []
            db_content["issued_keys"] = keys.data or []
            
            logger.info(f"💾 Синхронизировано: {len(db_content['users'])} пользователей, {len(db_content['bots'])} ботов")
            save_db_local()
        except Exception as e:
            logger.error(f"❌ Не удалось загрузить данные из облака: {e}")
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "r", encoding="utf-8") as f:
                    db_content.update(json.load(f))

# --- Модели ---
class LoginRequest(BaseModel):
    email: str
    password: str

class VerificationRequest(BaseModel):
    email: str

class RegisterWithCodeRequest(BaseModel):
    email: str
    code: str
    password: str
    username: str

class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    newPassword: str

class ActivateRequest(BaseModel):
    botId: str
    key: str

# --- Бот Воркер ---
active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}

def is_bot_license_active(bot_config: dict) -> bool:
    exp = bot_config.get("licenseExpiresAt", 0)
    return int(exp) > int(time.time() * 1000)

async def add_bot_log(bot_id: str, log_type: str, text: str):
    bot_cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if bot_cfg:
        if "logs" not in bot_cfg: bot_cfg["logs"] = []
        bot_cfg["logs"].insert(0, {"id": str(uuid.uuid4()), "timestamp": int(time.time() * 1000), "type": log_type, "text": text})
        bot_cfg["logs"] = bot_cfg["logs"][:20]
        await sync_to_supabase("bots", bot_cfg)

async def bot_worker_task(bot_id: str, token: str):
    logger.info(f"🤖 Запуск воркера: {bot_id}")
    try:
        async with AiohttpSession() as session:
            bot = Bot(token=token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
            active_bots[bot_id] = bot
            dp = Dispatcher()
            router = Router()

            def get_config(): return next((b for b in db_content["bots"] if b["id"] == bot_id), None)

            @router.message(CommandStart())
            async def cmd_start(message: Message):
                cfg = get_config()
                welcome = cfg.get("welcomeMessage", "Привет!") if cfg else "Привет!"
                kb_list = [[KeyboardButton(text=btn["text"])] for btn in cfg.get("buttons", [])] if cfg else []
                await message.answer(welcome, reply_markup=ReplyKeyboardMarkup(keyboard=kb_list, resize_keyboard=True) if kb_list else None)
                if cfg:
                    if "subscribers" not in cfg or cfg["subscribers"] is None: cfg["subscribers"] = []
                    if message.from_user.id not in cfg["subscribers"]:
                        cfg["subscribers"].append(message.from_user.id)
                        cfg["usersCount"] = len(cfg["subscribers"])
                        await sync_to_supabase("bots", cfg)

            @router.message()
            async def main_handler(message: Message):
                cfg = get_config()
                if not cfg: return
                user_id, admin_id, text = message.from_user.id, cfg.get("adminChatId"), message.text or ""

                if admin_id and str(user_id) == str(admin_id) and message.reply_to_message:
                    match = re.search(r"ID: (\d+)", message.reply_to_message.text or "")
                    if match:
                        try:
                            await bot.send_message(int(match.group(1)), message.text or "[Media]")
                            await message.reply("✅ Отправлено")
                            return
                        except Exception as e: await message.reply(f"❌: {e}"); return

                for btn in cfg.get("buttons", []):
                    if btn["text"].lower() == text.lower():
                        await message.answer(btn.get("response", "..."))
                        if btn.get("type") == "request" and admin_id:
                            msg = btn.get("adminTemplate", "{{name}} (ID: {{id}}): {{button}}")\
                                .replace("{{id}}", str(user_id)).replace("{{name}}", message.from_user.full_name)\
                                .replace("{{button}}", btn["text"])
                            try: await bot.send_message(admin_id, msg)
                            except: pass
                        return

                if admin_id and str(user_id) != str(admin_id):
                    info = f"📩 <b>От:</b> {message.from_user.full_name} (ID: <code>{user_id}</code>)\n\n"
                    try:
                        if message.content_type == ContentType.TEXT: await bot.send_message(admin_id, f"{info}{message.text}")
                        else: await bot.send_message(admin_id, info); await message.copy_to(admin_id)
                    except: pass

            dp.include_router(router)
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot, skip_updates=True)
    except Exception as e: logger.error(f"❌ Bot {bot_id} Error: {e}")
    finally: active_bots.pop(bot_id, None); active_tasks.pop(bot_id, None)

# --- API ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    await load_db_full()
    for b in db_content["bots"]:
        if b.get("status") == "RUNNING" and is_bot_license_active(b):
            active_tasks[b["id"]] = asyncio.create_task(bot_worker_task(b["id"], b["token"]))
    yield
    for t in active_tasks.values(): t.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/api/ping")
async def ping(): return {"status": "online"}

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    email = req.email.lower().strip()
    logger.info(f"🔑 Попытка входа: {email}")
    if supabase:
        res = supabase.table("users").select("*").eq("email", email).eq("password", req.password).execute()
        if not res.data:
            logger.warning(f"❌ Неудачный вход: {email}")
            raise HTTPException(401, "Неверный Email или пароль")
        return res.data[0]
    
    u = next((u for u in db_content["users"] if u["email"] == email and u["password"] == req.password), None)
    if not u: raise HTTPException(401, "Неверный Email или пароль")
    return u

@app.post("/api/auth/request-verification")
async def request_verification(req: VerificationRequest):
    email = req.email.lower().strip()
    logger.info(f"📧 Запрос кода: {email}")
    if supabase:
        res = supabase.table("users").select("id").eq("email", email).execute()
        if res.data: 
            logger.warning(f"❌ Попытка повторной регистрации: {email}")
            raise HTTPException(400, "Пользователь с таким Email уже существует")
    
    code = "".join([str(secrets.randbelow(10)) for _ in range(6)])
    verification_codes[email] = {"code": code, "timestamp": time.time()}
    if EmailService.send_verification_code(email, code): return {"status": "ok"}
    logger.error(f"❌ Ошибка SMTP для {email}")
    raise HTTPException(500, "Ошибка отправки почты. Попробуйте позже.")

@app.post("/api/auth/verify-and-register")
async def verify_and_register(req: RegisterWithCodeRequest):
    email = req.email.lower().strip()
    stored = verification_codes.get(email)
    if not stored or stored["code"] != req.code:
        raise HTTPException(400, "Неверный или просроченный код")
    
    new_user = {
        "id": f"u_{secrets.token_hex(4)}",
        "username": req.username,
        "email": email,
        "password": req.password,
        "balance": 0.0,
        "botsCreated": 0,
        "licenseExpiresAt": int(time.time() * 1000) + (3 * 24 * 3600 * 1000)
    }
    
    db_content["users"].append(new_user)
    await sync_to_supabase("users", new_user)
    verification_codes.pop(email, None)
    return new_user

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    if supabase:
        res = supabase.table("bots").select("*").eq("ownerId", user_id).execute()
        bots = res.data or []
        for b in bots: b["status"] = "RUNNING" if b["id"] in active_tasks else "IDLE"
        return bots
    return [b for b in db_content["bots"] if str(b["ownerId"]) == str(user_id)]

@app.post("/api/bots/save")
async def save_bot_api(bot_data: dict):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == bot_data["id"]), -1)
    if idx >= 0: db_content["bots"][idx] = bot_data
    else: db_content["bots"].append(bot_data)
    
    await sync_to_supabase("bots", bot_data)
    save_db_local()
    return {"status": "ok"}

@app.post("/api/bots/start/{bot_id}")
async def start_bot_api(bot_id: str):
    cfg = None
    if supabase:
        res = supabase.table("bots").select("*").eq("id", bot_id).execute()
        if res.data: cfg = res.data[0]
    
    if not cfg: cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not cfg: raise HTTPException(404, "Бот не найден")
    if not is_bot_license_active(cfg): raise HTTPException(403, "Лицензия истекла")
    
    if bot_id not in active_tasks:
        active_tasks[bot_id] = asyncio.create_task(bot_worker_task(bot_id, cfg["token"]))
        cfg["status"] = "RUNNING"
        await sync_to_supabase("bots", cfg)
    return {"status": "ok"}

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot_api_endpoint(bot_id: str):
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel()
        active_tasks.pop(bot_id, None)
    
    if supabase:
        supabase.table("bots").update({"status": "IDLE"}).eq("id", bot_id).execute()
    
    for b in db_content["bots"]:
        if b["id"] == bot_id: b["status"] = "IDLE"
    save_db_local()
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
