
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
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ContentType
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter
import uvicorn

# --- Загрузка переменных окружения из .env ---
def load_env_file():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip().strip('"').strip("'")

load_env_file()

try:
    from email_service import EmailService
except ImportError:
    class EmailService:
        @staticmethod
        def send_verification_code(*args): return False
        @staticmethod
        def send_password_reset(*args): return False
        @staticmethod
        def send_license_alert(*args): return False

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

ADMIN_SECRET = os.getenv("ADMIN_SECRET")
if not ADMIN_SECRET:
    ADMIN_SECRET = secrets.token_hex(16)
    logger.warning(f"⚠️ ADMIN_SECRET не найден! Сгенерирован: {ADMIN_SECRET}")

# --- Модели данных ---
class LoginRequest(BaseModel):
    email: str
    password: str

class VerificationRequest(BaseModel):
    email: str

class VerifyAndRegisterRequest(BaseModel):
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

# --- База Данных ---
db_content = {"users": [], "bots": [], "issued_keys": [], "system_logs": []}
verification_store: Dict[str, dict] = {} 

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db_content, f, ensure_ascii=False, indent=2)
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
        except Exception as e:
            logger.error(f"❌ Load DB Error: {e}")

def update_bot_stats(bot_id: str, direction: str):
    bot = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not bot: return
    if "stats" not in bot or not bot["stats"]:
        bot["stats"] = {"totalMessages": 0, "incomingToday": 0, "outgoingToday": 0, "bannedCount": 0, "history": [], "activeUsers24h": 0}
    bot["stats"]["totalMessages"] += 1
    bot["stats"]["incomingToday" if direction == "incoming" else "outgoingToday"] += 1
    save_db()

def is_bot_license_active(bot_config: dict) -> bool:
    return int(bot_config.get("licenseExpiresAt", 0)) > int(time.time() * 1000)

async def license_checker_loop():
    logger.info("⏳ Запущен фоновый мониторинг лицензий")
    while True:
        try:
            now = int(time.time() * 1000)
            day_ms = 24 * 3600 * 1000
            for bot in db_content["bots"]:
                expires = int(bot.get("licenseExpiresAt", 0))
                diff = expires - now
                owner = next((u for u in db_content["users"] if str(u["id"]) == str(bot["ownerId"])), None)
                if not owner or not owner.get("email"): continue
                if 3 * day_ms >= diff > 2.5 * day_ms:
                    EmailService.send_license_alert(owner["email"], bot["name"], 3)
                elif day_ms >= diff > 0.5 * day_ms:
                    EmailService.send_license_alert(owner["email"], bot["name"], 1)
            await asyncio.sleep(12 * 3600)
        except Exception as e:
            logger.error(f"Error in license checker: {e}")
            await asyncio.sleep(60)

# --- Бот Воркер ---
active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}

def format_msg(template: str, m: Message, btn_text: str = "") -> str:
    if not template: return f"📩 Сообщение от {m.from_user.id}"
    res = template.replace("{{id}}", str(m.from_user.id))
    res = res.replace("{{name}}", m.from_user.full_name or "User")
    res = res.replace("{{username}}", f"@{m.from_user.username}" if m.from_user.username else "none")
    res = res.replace("{{button}}", btn_text)
    return res

async def bot_worker_task(bot_id: str, token: str):
    session = AiohttpSession()
    bot = Bot(token=token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    active_bots[bot_id] = bot
    dp = Dispatcher()
    router = Router()

    @router.message(CommandStart())
    async def cmd_start(m: Message):
        config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not config or not is_bot_license_active(config): return
        if "connectedUsers" not in config: config["connectedUsers"] = []
        user = next((u for u in config["connectedUsers"] if u["id"] == m.from_user.id), None)
        if not user:
            user = {"id": m.from_user.id, "first_name": m.from_user.first_name, "username": m.from_user.username, "joined_at": int(time.time()), "is_banned": False, "warns": 0, "thread_id": None}
            config["connectedUsers"].append(user)
            config["usersCount"] = len(config["connectedUsers"])
        if "subscribers" not in config: config["subscribers"] = []
        if m.from_user.id not in config["subscribers"]: config["subscribers"].append(m.from_user.id)
        save_db()
        if user.get("is_banned"): return
        rows = []
        for btn in config.get("buttons", []):
            if btn.get("text"): rows.append([KeyboardButton(text=btn["text"])])
        kb = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True) if rows else None
        msg = format_msg(config.get("welcomeMessage", "Привет!"), m)
        await m.answer(msg, reply_markup=kb)

    @router.message(Command("warn", "unwarn", "ban", "unban"))
    async def admin_moderation(m: Message):
        config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not config or str(m.chat.id) != str(config.get("adminChatId")): return
        target_user = None
        if m.message_thread_id:
            target_user = next((u for u in config.get("connectedUsers", []) if u.get("thread_id") == m.message_thread_id), None)
        if not target_user and m.reply_to_message:
            match = re.search(r"ID: (\d+)", m.reply_to_message.text or m.reply_to_message.caption or "")
            if match:
                uid = int(match.group(1))
                target_user = next((u for u in config.get("connectedUsers", []) if u["id"] == uid), None)
        if not target_user: return await m.reply("❌ Пользователь не найден.")
        cmd = m.text.split()[0].replace("/", "").lower()
        threshold = config.get("settings", {}).get("autoBanThreshold", 0)
        if cmd == "warn":
            target_user["warns"] = target_user.get("warns", 0) + 1
            txt = f"⚠️ <b>Вам выдано предупреждение!</b>\nВсего: {target_user['warns']}"
            if threshold > 0: txt += f" / {threshold}"
            try: await bot.send_message(target_user["id"], txt)
            except: pass
            if threshold > 0 and target_user["warns"] >= threshold:
                target_user["is_banned"] = True
                try: await bot.send_message(target_user["id"], "🚫 <b>Вы забанены по порогу варнов.</b>")
                except: pass
            await m.answer(f"✅ Варн выдан ({target_user['warns']})")
        elif cmd == "ban":
            target_user["is_banned"] = True
            try: await bot.send_message(target_user["id"], "🚫 <b>Вы были заблокированы администратором.</b>")
            except: pass
            await m.answer("🔨 Забанен.")
        elif cmd == "unban":
            target_user["is_banned"] = False
            target_user["warns"] = 0
            try: await bot.send_message(target_user["id"], "✅ <b>Вы были разблокированы!</b>")
            except: pass
            await m.answer("😇 Разбанен.")
        save_db()

    @router.message()
    async def main_handler(m: Message):
        config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not config or not is_bot_license_active(config): return
        admin_id = config.get("adminChatId")
        if admin_id and str(m.chat.id) == str(admin_id):
            target_id = None
            if m.message_thread_id:
                u = next((u for u in config.get("connectedUsers", []) if u.get("thread_id") == m.message_thread_id), None)
                if u: target_id = u["id"]
            if not target_id and m.reply_to_message:
                match = re.search(r"ID: (\d+)", m.reply_to_message.text or m.reply_to_message.caption or "")
                if match: target_id = int(match.group(1))
            if target_id:
                try:
                    await bot.copy_message(target_id, m.chat.id, m.message_id)
                    update_bot_stats(bot_id, "outgoing")
                except: pass
            return
        user = next((u for u in config.get("connectedUsers", []) if u["id"] == m.from_user.id), None)
        if not user or user.get("is_banned"): return
        if m.text:
            low = m.text.lower()
            for btn in config.get("buttons", []):
                if btn.get("text") and btn["text"].lower() == low:
                    if btn.get("type") == "request" and admin_id:
                        if config.get("settings", {}).get("useTopics") and not user.get("thread_id"):
                            try:
                                t = await bot.create_forum_topic(admin_id, f"{m.from_user.first_name} [{m.from_user.id}]")
                                user["thread_id"] = t.message_thread_id
                                save_db()
                            except: pass
                        txt = format_msg(btn.get("adminTemplate", ""), m, btn["text"])
                        await bot.send_message(admin_id, txt, message_thread_id=user.get("thread_id"))
                    await m.answer(btn.get("response", "Принято"))
                    update_bot_stats(bot_id, "outgoing")
                    return
        if admin_id:
            tid = user.get("thread_id")
            try:
                if not tid:
                    await bot.send_message(admin_id, f"📩 Сообщение от ID: <code>{m.from_user.id}</code>\nИмя: {m.from_user.full_name}")
                await bot.copy_message(admin_id, m.chat.id, m.message_id, message_thread_id=tid)
                update_bot_stats(bot_id, "incoming")
            except:
                await bot.copy_message(admin_id, m.chat.id, m.message_id)

    dp.include_router(router)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await session.close()

# --- FastAPI App ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_db()
    for b in db_content["bots"]:
        if b.get("status") == "RUNNING" and is_bot_license_active(b):
            active_tasks[b["id"]] = asyncio.create_task(bot_worker_task(b["id"], b["token"]))
    asyncio.create_task(license_checker_loop())
    yield
    for t in active_tasks.values(): t.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/ping")
async def ping(): return {"status": "online"}

@app.post("/api/auth/request-verification")
async def request_verification(req: VerificationRequest):
    logger.info(f"📥 Запрос верификации для регистрации: {req.email}")
    code = "".join(secrets.choice("0123456789") for _ in range(6))
    verification_store[req.email] = {"code": code, "expires": int(time.time()) + 600, "type": "reg"}
    
    success = EmailService.send_verification_code(req.email, code)
    if success:
        logger.info(f"✅ Код регистрации отправлен на {req.email}")
        return {"status": "ok"}
    
    logger.error(f"❌ Не удалось отправить код регистрации на {req.email}")
    raise HTTPException(500, "Ошибка при отправке Email")

@app.post("/api/auth/verify-and-register")
async def verify_and_register(req: VerifyAndRegisterRequest):
    store = verification_store.get(req.email)
    if not store or store["code"] != req.code or store["expires"] < time.time() or store["type"] != "reg":
        raise HTTPException(400, "Неверный код или срок действия истек")
    if any(u["email"] == req.email for u in db_content["users"]):
        raise HTTPException(400, "Email уже зарегистрирован")
    new_user = {
        "id": "u_" + secrets.token_hex(4),
        "username": req.username,
        "email": req.email,
        "password": req.password,
        "licenseExpiresAt": int(time.time() * 1000) + (3 * 24 * 3600 * 1000),
        "balance": 0, "botsCreated": 0
    }
    db_content["users"].append(new_user)
    save_db()
    if req.email in verification_store: del verification_store[req.email]
    return new_user

@app.post("/api/auth/forgot-password")
async def forgot_password(req: VerificationRequest):
    logger.info(f"📥 Запрос восстановления пароля: {req.email}")
    user = next((u for u in db_content["users"] if u["email"] == req.email), None)
    if not user: 
        logger.warning(f"⚠️ Попытка сброса пароля для несуществующего Email: {req.email}")
        raise HTTPException(404, "Email не найден")
    
    code = "".join(secrets.choice("0123456789") for _ in range(6))
    verification_store[req.email] = {"code": code, "expires": int(time.time()) + 600, "type": "reset"}
    
    success = EmailService.send_password_reset(req.email, code)
    if success:
        return {"status": "ok"}
    raise HTTPException(500, "Ошибка при отправке Email")

@app.post("/api/auth/reset-password")
async def reset_password(req: ResetPasswordRequest):
    store = verification_store.get(req.email)
    if not store or store["code"] != req.code or store["expires"] < time.time() or store["type"] != "reset":
        raise HTTPException(400, "Неверный код")
    user = next((u for u in db_content["users"] if u["email"] == req.email), None)
    if not user: raise HTTPException(404)
    user["password"] = req.newPassword
    save_db()
    if req.email in verification_store: del verification_store[req.email]
    return {"status": "ok"}

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    u = next((u for u in db_content["users"] if u["email"] == req.email and u["password"] == req.password), None)
    if not u: raise HTTPException(401)
    return u

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    res = [b for b in db_content["bots"] if str(b["ownerId"]) == str(user_id)]
    for b in res: b["status"] = "RUNNING" if b["id"] in active_tasks and not active_tasks[b["id"]].done() else "IDLE"
    return res

@app.post("/api/bots/save")
async def save_bot(bot_data: dict):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == bot_data["id"]), -1)
    if idx >= 0: db_content["bots"][idx] = bot_data
    else: db_content["bots"].append(bot_data)
    save_db(); return {"status": "ok"}

@app.delete("/api/bots/delete/{bot_id}")
async def delete_bot(bot_id: str):
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel(); del active_tasks[bot_id]
    db_content["bots"] = [b for b in db_content["bots"] if b["id"] != bot_id]
    save_db(); return {"status": "ok"}

@app.post("/api/bots/start/{bot_id}")
async def start_bot(bot_id: str):
    cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not cfg or not is_bot_license_active(cfg): raise HTTPException(403, "License error")
    if bot_id not in active_tasks:
        active_tasks[bot_id] = asyncio.create_task(bot_worker_task(bot_id, cfg["token"]))
    return {"status": "ok"}

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel(); del active_tasks[bot_id]
    if bot_id in active_bots: del active_bots[bot_id]
    return {"status": "ok"}

@app.post("/api/broadcast")
async def broadcast(req: BroadcastRequest):
    results = {"success": 0, "failed": 0}
    for bot_id in req.botIds:
        bot_instance = active_bots.get(bot_id)
        config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not bot_instance or not config: continue
        for user_id in config.get("subscribers", []):
            try:
                await bot_instance.send_message(user_id, req.message)
                results["success"] += 1
            except: results["failed"] += 1
    return results

@app.post("/api/license/activate")
async def activate(req: ActivateRequest):
    bot_cfg = next((b for b in db_content["bots"] if b["id"] == req.botId), None)
    key_obj = next((k for k in db_content["issued_keys"] if k["key"] == req.key and not k["used"]), None)
    if not bot_cfg or not key_obj: raise HTTPException(400)
    now = int(time.time() * 1000)
    exp = max(bot_cfg.get("licenseExpiresAt", now), now)
    bot_cfg["licenseExpiresAt"] = exp + (key_obj["months"] * 30 * 24 * 3600 * 1000)
    key_obj["used"] = True; save_db(); return {"status": "ok", "newExpiry": bot_cfg["licenseExpiresAt"]}

@app.post("/api/admin/generate-key")
async def gen_key(req: KeyGenRequest, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET: raise HTTPException(403)
    k = f"BOT-{req.months}-{secrets.token_hex(3).upper()}"
    db_content["issued_keys"].append({"key": k, "months": req.months, "used": False, "created_at": int(time.time())})
    save_db(); return {"key": k}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
