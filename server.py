
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

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotEngineCore")

# Импорт зависимостей
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
        logger.info("✅ Supabase client initialized and connected")
    except Exception as e:
        logger.error(f"❌ Supabase init error: {e}")

# Временное хранилище кодов (email: {code, timestamp})
verification_codes: Dict[str, dict] = {}
# Временное хранилище для сброса пароля
reset_codes: Dict[str, dict] = {}

db_content = {"users": [], "bots": [], "issued_keys": [], "system_logs": []}

# --- Логика БД (Supabase Sync) ---

async def sync_to_supabase(table: str, data: Any):
    """Синхронизация конкретного объекта или списка в Supabase"""
    if not supabase: return
    try:
        payload = data if isinstance(data, list) else [data]
        if not payload: return
        
        # Удаляем временные поля, которых нет в схеме БД
        clean_payload = []
        for item in payload:
            c = item.copy()
            # Удаляем пароль при синхронизации ботов (если он там вдруг есть)
            # и другие динамические поля
            clean_payload.append(c)

        result = supabase.table(table).upsert(clean_payload).execute()
        return result
    except Exception as e:
        logger.error(f"❌ Supabase Sync Error (table: {table}): {e}")

def save_db_local():
    """Сохранение локального бэкапа"""
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db_content, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"❌ Local Save Error: {e}")

async def load_db_full():
    """Полная загрузка данных из Supabase"""
    global db_content
    
    if supabase:
        try:
            logger.info("🔄 Fetching data from Supabase...")
            users_res = supabase.table("users").select("*").execute()
            bots_res = supabase.table("bots").select("*").execute()
            keys_res = supabase.table("issued_keys").select("*").execute()
            
            db_content["users"] = users_res.data or []
            db_content["bots"] = bots_res.data or []
            db_content["issued_keys"] = keys_res.data or []
            
            logger.info(f"💾 Synced: {len(db_content['users'])} users, {len(db_content['bots'])} bots")
            save_db_local()
            return
        except Exception as e:
            logger.error(f"❌ Supabase Fetch Error, falling back to local: {e}")

    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                for key in db_content.keys():
                    if key in loaded: db_content[key] = loaded[key]
        except Exception as e:
            logger.error(f"❌ Local Load Error: {e}")

# --- Модели API ---
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

class BroadcastRequest(BaseModel):
    botIds: List[str]
    message: str

class KeyGenRequest(BaseModel):
    months: int

class ActivateRequest(BaseModel):
    botId: str
    key: str

# --- Вспомогательные функции ---
def is_bot_license_active(bot_config: dict) -> bool:
    exp = bot_config.get("licenseExpiresAt", 0)
    return int(exp) > int(time.time() * 1000)

async def add_bot_log(bot_id: str, log_type: str, text: str):
    bot_cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if bot_cfg:
        if "logs" not in bot_cfg: bot_cfg["logs"] = []
        log_entry = {
            "id": str(uuid.uuid4()),
            "timestamp": int(time.time() * 1000),
            "type": log_type,
            "text": text
        }
        bot_cfg["logs"].insert(0, log_entry)
        bot_cfg["logs"] = bot_cfg["logs"][:30]
        save_db_local()
        await sync_to_supabase("bots", bot_cfg)

active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}

# --- Бот Воркер ---

async def bot_worker_task(bot_id: str, token: str):
    logger.info(f"🤖 Starting worker for bot {bot_id}")
    try:
        async with AiohttpSession() as session:
            bot = Bot(token=token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
            active_bots[bot_id] = bot
            dp = Dispatcher()
            router = Router()

            def get_config():
                return next((b for b in db_content["bots"] if b["id"] == bot_id), None)

            @router.message(CommandStart())
            async def cmd_start(message: Message):
                cfg = get_config()
                welcome = cfg.get("welcomeMessage", "Привет!") if cfg else "Привет!"
                kb_list = []
                if cfg and cfg.get("buttons"):
                    for btn in cfg["buttons"]:
                        kb_list.append([KeyboardButton(text=btn["text"])])
                
                reply_markup = ReplyKeyboardMarkup(keyboard=kb_list, resize_keyboard=True) if kb_list else None
                await message.answer(welcome, reply_markup=reply_markup)
                await add_bot_log(bot_id, "incoming", f"User {message.from_user.id} (/start)")
                
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
                
                user_id = message.from_user.id
                admin_id = cfg.get("adminChatId")
                text = message.text or ""

                if admin_id and str(user_id) == str(admin_id) and message.reply_to_message:
                    reply_text = message.reply_to_message.text or message.reply_to_message.caption or ""
                    match = re.search(r"ID: (\d+)", reply_text)
                    if match:
                        target_id = int(match.group(1))
                        try:
                            if message.content_type == ContentType.TEXT:
                                await bot.send_message(target_id, message.text)
                            else:
                                await message.copy_to(target_id)
                            await message.reply("✅ Отправлено")
                            await add_bot_log(bot_id, "outgoing", f"Admin replied to {target_id}")
                            return
                        except Exception as e:
                            await message.reply(f"❌ Ошибка: {e}")
                            return

                for btn in cfg.get("buttons", []):
                    if btn["text"].lower() == text.lower():
                        await message.answer(btn.get("response", "..."))
                        await add_bot_log(bot_id, "outgoing", f"Button: {btn['text']}")
                        if btn.get("type") == "request" and admin_id:
                            template = btn.get("adminTemplate", "📩 Обращение: {{button}}\nОт: {{name}} (ID: {{id}})")
                            admin_msg = template.replace("{{id}}", str(user_id))\
                                               .replace("{{name}}", message.from_user.full_name)\
                                               .replace("{{username}}", f"@{message.from_user.username or 'none'}")\
                                               .replace("{{button}}", btn["text"])
                            try: await bot.send_message(admin_id, admin_msg)
                            except: pass
                        return

                for trig in cfg.get("triggers", []):
                    if trig["keyword"].lower() in text.lower():
                        await message.answer(trig["response"])
                        await add_bot_log(bot_id, "outgoing", f"Trigger: {trig['keyword']}")
                        return

                if admin_id and str(user_id) != str(admin_id):
                    info = f"📩 <b>Сообщение от пользователя</b>\n👤 {message.from_user.full_name}\n🆔 ID: <code>{user_id}</code>\n\n"
                    try:
                        if message.content_type == ContentType.TEXT:
                            await bot.send_message(admin_id, f"{info}{message.text}")
                        else:
                            await bot.send_message(admin_id, info)
                            await message.copy_to(admin_id)
                    except Exception as e:
                        logger.error(f"Forward failed: {e}")

            dp.include_router(router)
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logger.error(f"❌ Bot {bot_id} Error: {e}")
        await add_bot_log(bot_id, "error", str(e))
    finally:
        active_bots.pop(bot_id, None)
        active_tasks.pop(bot_id, None)

# --- API Endpoints ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    await load_db_full()
    for b in db_content["bots"]:
        if b.get("status") == "RUNNING" and is_bot_license_active(b):
            active_tasks[b["id"]] = asyncio.create_task(bot_worker_task(b["id"], b["token"]))
    
    async def monitor():
        while True:
            try:
                for b in db_content["bots"]:
                    if b["id"] in active_tasks and not is_bot_license_active(b):
                        active_tasks[b["id"]].cancel()
                        b["status"] = "IDLE"
                        await sync_to_supabase("bots", b)
            except: pass
            await asyncio.sleep(300)
    
    m_task = asyncio.create_task(monitor())
    yield
    m_task.cancel()
    for t in active_tasks.values(): t.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/api/ping")
async def ping(): return {"status": "online"}

@app.post("/api/auth/request-verification")
async def request_verification(req: VerificationRequest):
    email = req.email.lower().strip()
    
    if supabase:
        check = supabase.table("users").select("id").eq("email", email).execute()
        if check.data:
            raise HTTPException(400, "Пользователь с таким Email уже зарегистрирован")
    elif any(u["email"] == email for u in db_content["users"]):
        raise HTTPException(400, "Пользователь с таким Email уже зарегистрирован")

    code = "".join([str(secrets.randbelow(10)) for _ in range(6)])
    verification_codes[email] = {"code": code, "timestamp": time.time()}
    
    sent = EmailService.send_verification_code(email, code)
    if not sent:
        logger.warning(f"🔥 SMTP FAILURE. CODE FOR {email} IS: {code}")
        raise HTTPException(500, "Ошибка SMTP. Проверьте настройки почты в .env")
        
    return {"status": "ok"}

@app.post("/api/auth/verify-and-register")
async def verify_and_register(req: RegisterWithCodeRequest):
    email = req.email.lower().strip()
    stored = verification_codes.get(email)
    if not stored or stored["code"] != req.code or time.time() - stored["timestamp"] > 600:
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
    save_db_local()
    await sync_to_supabase("users", new_user)
    
    verification_codes.pop(email, None)
    return new_user

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    email = req.email.lower().strip()
    u = next((u for u in db_content["users"] if u["email"] == email and u["password"] == req.password), None)
    if not u: raise HTTPException(401, "Неверный Email или пароль")
    return u

@app.post("/api/auth/forgot-password")
async def forgot_password(req: VerificationRequest):
    email = req.email.lower().strip()
    u = next((u for u in db_content["users"] if u["email"] == email), None)
    if not u:
        raise HTTPException(404, "Пользователь с таким Email не найден")
    
    code = "".join([str(secrets.randbelow(10)) for _ in range(6)])
    reset_codes[email] = {"code": code, "timestamp": time.time()}
    
    sent = EmailService.send_password_reset(email, code)
    if not sent:
        logger.warning(f"🔥 SMTP FAILURE. RESET CODE FOR {email} IS: {code}")
        raise HTTPException(500, "Ошибка SMTP. Обратитесь в поддержку")
    
    return {"status": "ok"}

@app.post("/api/auth/reset-password")
async def reset_password(req: ResetPasswordRequest):
    email = req.email.lower().strip()
    stored = reset_codes.get(email)
    if not stored or stored["code"] != req.code or time.time() - stored["timestamp"] > 600:
        raise HTTPException(400, "Неверный или просроченный код подтверждения")
    
    user_idx = next((i for i, u in enumerate(db_content["users"]) if u["email"] == email), -1)
    if user_idx == -1:
        raise HTTPException(404, "Пользователь не найден")
    
    db_content["users"][user_idx]["password"] = req.newPassword
    save_db_local()
    await sync_to_supabase("users", db_content["users"][user_idx])
    
    reset_codes.pop(email, None)
    return {"status": "ok"}

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    user_bots = [b for b in db_content["bots"] if str(b["ownerId"]) == str(user_id)]
    for b in user_bots: b["status"] = "RUNNING" if b["id"] in active_tasks else "IDLE"
    return user_bots

@app.post("/api/bots/save")
async def save_bot_api(bot_data: dict):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == bot_data["id"]), -1)
    if idx >= 0:
        old = db_content["bots"][idx]
        for k in ["logs", "stats", "subscribers"]:
            if k not in bot_data: bot_data[k] = old.get(k, [])
        db_content["bots"][idx] = bot_data
    else:
        db_content["bots"].append(bot_data)
    
    save_db_local()
    await sync_to_supabase("bots", bot_data)
    return {"status": "ok"}

@app.post("/api/bots/start/{bot_id}")
async def start_bot_api(bot_id: str):
    cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
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
    
    for b in db_content["bots"]:
        if b["id"] == bot_id: 
            b["status"] = "IDLE"
            await sync_to_supabase("bots", b)
            
    save_db_local()
    return {"status": "ok"}

@app.post("/api/admin/generate-key")
async def generate_key_api(req: KeyGenRequest, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    new_key = {
        "key": f"BOT-{req.months}-{secrets.token_hex(3).upper()}",
        "months": req.months,
        "used": False,
        "created_at": int(time.time() * 1000)
    }
    db_content["issued_keys"].append(new_key)
    save_db_local()
    await sync_to_supabase("issued_keys", new_key)
    return {"key": new_key["key"]}

@app.post("/api/license/activate")
async def activate_key_api(req: ActivateRequest):
    bot_cfg = next((b for b in db_content["bots"] if b["id"] == req.botId), None)
    key_obj = next((k for k in db_content["issued_keys"] if k["key"] == req.key and not k.get("used")), None)
    
    if not bot_cfg: raise HTTPException(404, "Бот не найден")
    if not key_obj: raise HTTPException(400, "Ключ недействителен")
    
    now = int(time.time() * 1000)
    current_exp = int(bot_cfg.get("licenseExpiresAt", now))
    base_time = max(current_exp, now)
    
    bot_cfg["licenseExpiresAt"] = base_time + (key_obj["months"] * 30 * 24 * 3600 * 1000)
    key_obj["used"] = True
    key_obj["used_by_bot"] = req.botId
    key_obj["used_at"] = now
    
    save_db_local()
    await sync_to_supabase("bots", bot_cfg)
    await sync_to_supabase("issued_keys", key_obj)
    
    return {"status": "ok", "newExpiry": bot_cfg["licenseExpiresAt"]}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
