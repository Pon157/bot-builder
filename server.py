
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
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter, TokenValidationError
import uvicorn

# Попытка импорта Supabase для синхронизации
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

# Импорт сервиса почты
from email_service import EmailService

# --- Инициализация окружения ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotEngineCore")

DB_FILE = "database.json"
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Инициализация Supabase
supabase: Optional['Client'] = None
if SUPABASE_AVAILABLE and SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("✅ Supabase client initialized")
    except Exception as e:
        logger.error(f"❌ Supabase init error: {e}")

# Временное хранилище кодов (email: {code, timestamp, data})
verification_codes: Dict[str, dict] = {}

# --- Модели данных ---
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

# --- БД (Local JSON + Sync Logic) ---
db_content = {"users": [], "bots": [], "issued_keys": [], "system_logs": []}

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db_content, f, ensure_ascii=False, indent=2)
        # Опциональная синхронизация с Supabase (async не получится легко здесь, поэтому просто логируем)
        if supabase:
            logger.info("📡 Database updated, ready for cloud sync")
    except Exception as e:
        logger.error(f"❌ Save DB Error: {e}")

def load_db():
    global db_content
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                for key in db_content.keys():
                    if key in loaded: db_content[key] = loaded[key]
            logger.info(f"📁 Loaded: {len(db_content['users'])} users, {len(db_content['bots'])} bots")
        except Exception as e:
            logger.error(f"❌ Load DB Error: {e}")

load_db()

# --- Вспомогательные функции ---
def is_bot_license_active(bot_config: dict) -> bool:
    exp = bot_config.get("licenseExpiresAt", 0)
    return int(exp) > int(time.time() * 1000)

def add_bot_log(bot_id: str, log_type: str, text: str):
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
        bot_cfg["logs"] = bot_cfg["logs"][:50] # Храним последние 50 записей

active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}

# --- Бот Воркер (Сердце движка) ---

async def bot_worker_task(bot_id: str, token: str):
    logger.info(f"🤖 Starting worker for bot {bot_id}")
    
    try:
        session = AiohttpSession()
        bot = Bot(token=token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        active_bots[bot_id] = bot
        dp = Dispatcher()
        router = Router()

        # Получаем актуальный конфиг бота
        def get_config():
            return next((b for b in db_content["bots"] if b["id"] == bot_id), None)

        @router.message(CommandStart())
        async def cmd_start(message: Message):
            cfg = get_config()
            welcome = cfg.get("welcomeMessage", "Привет!") if cfg else "Привет!"
            
            # Формируем клавиатуру
            kb_list = []
            if cfg and cfg.get("buttons"):
                for btn in cfg["buttons"]:
                    kb_list.append([KeyboardButton(text=btn["text"])])
            
            reply_markup = ReplyKeyboardMarkup(keyboard=kb_list, resize_keyboard=True) if kb_list else None
            
            try:
                await message.answer(welcome, reply_markup=reply_markup)
                add_bot_log(bot_id, "incoming", f"User {message.from_user.id} (/start)")
                
                # Сохраняем пользователя в список подписчиков
                if cfg:
                    if "subscribers" not in cfg: cfg["subscribers"] = []
                    if message.from_user.id not in cfg["subscribers"]:
                        cfg["subscribers"].append(message.from_user.id)
                        cfg["usersCount"] = len(cfg["subscribers"])
                        save_db()
            except Exception as e:
                logger.error(f"Error in start cmd: {e}")

        @router.message()
        async def main_handler(message: Message):
            cfg = get_config()
            if not cfg: return
            
            user_id = message.from_user.id
            admin_id = cfg.get("adminChatId")
            text = message.text or ""

            # 1. Если пишет админ (Ответ пользователю)
            if admin_id and str(user_id) == str(admin_id) and message.reply_to_message:
                reply_text = message.reply_to_message.text or ""
                # Ищем ID пользователя в тексте пересланного сообщения
                match = re.search(r"ID: (\d+)", reply_text)
                if match:
                    target_id = int(match.group(1))
                    try:
                        if message.content_type == ContentType.TEXT:
                            await bot.send_message(target_id, message.text)
                        else:
                            await message.copy_to(target_id)
                        await message.reply("✅ Отправлено")
                        add_bot_log(bot_id, "outgoing", f"Admin replied to {target_id}")
                        return
                    except Exception as e:
                        await message.reply(f"❌ Ошибка отправки: {e}")
                        return

            # 2. Проверка кнопок
            for btn in cfg.get("buttons", []):
                if btn["text"].lower() == text.lower():
                    response = btn.get("response", "...")
                    await message.answer(response)
                    add_bot_log(bot_id, "outgoing", f"Button trigger: {btn['text']}")
                    
                    # Если это "Обращение", уведомляем админа
                    if btn.get("type") == "request" and admin_id:
                        template = btn.get("adminTemplate", "📩 Новое обращение: {{button}}\nОт: {{name}} (ID: {{id}})")
                        admin_msg = template.replace("{{id}}", str(user_id))\
                                           .replace("{{name}}", message.from_user.full_name)\
                                           .replace("{{username}}", f"@{message.from_user.username or 'none'}")\
                                           .replace("{{button}}", btn["text"])
                        try: await bot.send_message(admin_id, admin_msg)
                        except: pass
                    return

            # 3. Проверка триггеров
            for trig in cfg.get("triggers", []):
                if trig["keyword"].lower() in text.lower():
                    await message.answer(trig["response"])
                    add_bot_log(bot_id, "outgoing", f"Trigger: {trig['keyword']}")
                    return

            # 4. Пересылка админу (Livegram Mode)
            if admin_id and str(user_id) != str(admin_id):
                info = f"📩 <b>Сообщение от пользователя</b>\n👤 {message.from_user.full_name}\n🆔 ID: <code>{user_id}</code>\n\n"
                try:
                    if message.content_type == ContentType.TEXT:
                        await bot.send_message(admin_id, f"{info}{message.text}")
                    else:
                        await bot.send_message(admin_id, info)
                        await message.copy_to(admin_id)
                except Exception as e:
                    logger.error(f"Forward to admin failed: {e}")

        dp.include_router(router)
        add_bot_log(bot_id, "system", "Бот инициализирован и запущен")
        
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, skip_updates=True)
        
    except TokenValidationError:
        logger.error(f"❌ Invalid token for bot {bot_id}")
        add_bot_log(bot_id, "error", "Ошибка: Неверный токен бота")
    except Exception as e:
        logger.error(f"❌ Worker {bot_id} fatal error: {e}")
        add_bot_log(bot_id, "error", f"Критический сбой: {str(e)}")
    finally:
        if bot_id in active_bots: del active_bots[bot_id]
        if bot_id in active_tasks: del active_tasks[bot_id]
        logger.info(f"🛑 Worker for bot {bot_id} stopped")

# --- API Endpoints ---

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"]
)

@app.get("/api/ping")
async def ping(): 
    return {"status": "online", "time": int(time.time()), "supabase": SUPABASE_AVAILABLE}

# --- AUTH ---

@app.post("/api/auth/request-verification")
async def request_verification(req: VerificationRequest):
    email = req.email.lower().strip()
    if any(u["email"] == email for u in db_content["users"]):
        raise HTTPException(status_code=400, detail="Пользователь с таким Email уже существует")
    
    code = "".join([str(secrets.randbelow(10)) for _ in range(6)])
    verification_codes[email] = {"code": code, "timestamp": time.time()}
    
    logger.info(f"🔑 Generated code {code} for {email}")
    
    success = EmailService.send_verification_code(email, code)
    if not success:
        # В режиме разработки, если почта не настроена, можно вернуть код в лог
        logger.warning(f"⚠️ Email NOT sent. Code is {code}")
        raise HTTPException(status_code=500, detail="Ошибка отправки письма. Проверьте настройки SMTP в .env")
    
    return {"status": "ok"}

@app.post("/api/auth/verify-and-register")
async def verify_and_register(req: RegisterWithCodeRequest):
    email = req.email.lower().strip()
    stored = verification_codes.get(email)
    
    if not stored or stored["code"] != req.code:
        raise HTTPException(status_code=400, detail="Неверный или просроченный код подтверждения")
    
    if time.time() - stored["timestamp"] > 600: # 10 мин
        raise HTTPException(status_code=400, detail="Срок действия кода истек")
    
    new_user = {
        "id": f"u_{secrets.token_hex(4)}",
        "username": req.username,
        "email": email,
        "password": req.password,
        "balance": 0.0,
        "botsCreated": 0,
        "licenseExpiresAt": int(time.time() * 1000) + (3 * 24 * 3600 * 1000), # 3 дня триала
        "trialUsed": True
    }
    
    db_content["users"].append(new_user)
    save_db()
    del verification_codes[email]
    return new_user

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    email = req.email.lower().strip()
    u = next((u for u in db_content["users"] if u["email"] == email and u["password"] == req.password), None)
    if not u:
        raise HTTPException(status_code=401, detail="Неверный Email или пароль")
    return u

@app.post("/api/auth/forgot-password")
async def forgot_password(req: VerificationRequest):
    email = req.email.lower().strip()
    user = next((u for u in db_content["users"] if u["email"] == email), None)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь с такой почтой не найден")
    
    code = "".join([str(secrets.randbelow(10)) for _ in range(6)])
    verification_codes[email] = {"code": code, "timestamp": time.time()}
    EmailService.send_password_reset(email, code)
    return {"status": "ok"}

@app.post("/api/auth/reset-password")
async def reset_password(req: ResetPasswordRequest):
    email = req.email.lower().strip()
    stored = verification_codes.get(email)
    if not stored or stored["code"] != req.code:
        raise HTTPException(status_code=400, detail="Неверный код")
        
    user = next((u for u in db_content["users"] if u["email"] == email), None)
    if user:
        user["password"] = req.newPassword
        save_db()
        del verification_codes[email]
        return {"status": "ok"}
    raise HTTPException(status_code=404)

# --- BOTS ---

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    user_bots = [b for b in db_content["bots"] if str(b["ownerId"]) == str(user_id)]
    # Обновляем статус на лету
    for b in user_bots:
        b["status"] = "RUNNING" if b["id"] in active_tasks and not active_tasks[b["id"]].done() else "IDLE"
    return user_bots

@app.post("/api/bots/save")
async def save_bot_api(bot_data: dict):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == bot_data["id"]), -1)
    if idx >= 0:
        # Обновляем существующего бота, сохраняя логи и статистику если они не присланы
        old_bot = db_content["bots"][idx]
        if "logs" not in bot_data: bot_data["logs"] = old_bot.get("logs", [])
        if "stats" not in bot_data: bot_data["stats"] = old_bot.get("stats", {})
        if "subscribers" not in bot_data: bot_data["subscribers"] = old_bot.get("subscribers", [])
        db_content["bots"][idx] = bot_data
    else:
        # Новый бот
        if "logs" not in bot_data: bot_data["logs"] = []
        if "subscribers" not in bot_data: bot_data["subscribers"] = []
        db_content["bots"].append(bot_data)
    
    save_db()
    return {"status": "ok"}

@app.delete("/api/bots/delete/{bot_id}")
async def delete_bot_api(bot_id: str):
    # Останавливаем если запущен
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel()
        del active_tasks[bot_id]
    
    db_content["bots"] = [b for b in db_content["bots"] if b["id"] != bot_id]
    save_db()
    return {"status": "ok"}

@app.post("/api/bots/start/{bot_id}")
async def start_bot_api(bot_id: str):
    cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not cfg: raise HTTPException(404, "Бот не найден")
    
    if not is_bot_license_active(cfg):
        raise HTTPException(status_code=403, detail="Лицензия данного бота истекла. Продлите её в профиле.")
    
    if bot_id in active_tasks and not active_tasks[bot_id].done():
        return {"status": "ok", "message": "Already running"}
    
    active_tasks[bot_id] = asyncio.create_task(bot_worker_task(bot_id, cfg["token"]))
    cfg["status"] = "RUNNING"
    save_db()
    return {"status": "ok"}

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot_api(bot_id: str):
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel()
        del active_tasks[bot_id]
    
    if bot_id in active_bots:
        del active_bots[bot_id]
        
    for b in db_content["bots"]:
        if b["id"] == bot_id: b["status"] = "IDLE"
        
    save_db()
    return {"status": "ok"}

@app.post("/api/broadcast")
async def broadcast_api(req: BroadcastRequest):
    results = {"success": 0, "failed": 0}
    for bot_id in req.botIds:
        bot_instance = active_bots.get(bot_id)
        if not bot_instance: continue
        
        cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not cfg: continue
        
        subs = cfg.get("subscribers", [])
        for sub_id in subs:
            try:
                await bot_instance.send_message(sub_id, req.message)
                results["success"] += 1
                await asyncio.sleep(0.05) # Защита от флуда
            except Exception as e:
                logger.error(f"Broadcast error for {sub_id}: {e}")
                results["failed"] += 1
                
    return results

@app.post("/api/license/activate")
async def activate_key_api(req: ActivateRequest):
    bot_cfg = next((b for b in db_content["bots"] if b["id"] == req.botId), None)
    key_obj = next((k for k in db_content["issued_keys"] if k["key"] == req.key and not k["used"]), None)
    
    if not bot_cfg: raise HTTPException(404, "Бот не найден")
    if not key_obj: raise HTTPException(400, "Неверный или уже использованный ключ")
    
    now = int(time.time() * 1000)
    current_exp = int(bot_cfg.get("licenseExpiresAt", now))
    base_time = max(current_exp, now)
    
    bot_cfg["licenseExpiresAt"] = base_time + (key_obj["months"] * 30 * 24 * 3600 * 1000)
    key_obj["used"] = True
    key_obj["used_by_bot"] = req.botId
    key_obj["used_at"] = now
    
    save_db()
    return {"status": "ok", "newExpiry": bot_cfg["licenseExpiresAt"]}

@app.post("/api/admin/generate-key")
async def generate_key_api(req: KeyGenRequest, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    new_key = f"BOT-{req.months}-{secrets.token_hex(3).upper()}"
    db_content["issued_keys"].append({
        "key": new_key,
        "months": req.months,
        "used": False,
        "created_at": int(time.time() * 1000)
    })
    save_db()
    return {"key": new_key}

# --- LIFESPAN ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_db()
    
    # Автозапуск ботов, которые должны работать
    for b in db_content["bots"]:
        if b.get("status") == "RUNNING" and is_bot_license_active(b):
            logger.info(f"♻️ Auto-restarting bot {b['name']}")
            active_tasks[b["id"]] = asyncio.create_task(bot_worker_task(b["id"], b["token"]))
            
    # Фоновая задача проверки лицензий
    async def license_monitor():
        while True:
            try:
                now = int(time.time() * 1000)
                for b in db_content["bots"]:
                    if b["id"] in active_tasks and not is_bot_license_active(b):
                        logger.warning(f"🚨 License expired for {b['name']}, stopping...")
                        await stop_bot_api(b["id"])
            except Exception as e:
                logger.error(f"Monitor error: {e}")
            await asyncio.sleep(300) # Проверка каждые 5 минут

    monitor_task = asyncio.create_task(license_monitor())
    
    yield
    
    # Завершение работы
    monitor_task.cancel()
    for t in active_tasks.values():
        t.cancel()
    logger.info("👋 Server shutdown complete")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
