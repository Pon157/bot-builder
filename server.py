
import asyncio
import logging
import json
import os
import time
import re
import uuid
import secrets
from contextlib import asynccontextmanager
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, Message, ContentType
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter, TelegramBadRequest
import uvicorn

# Настройки безопасности
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BotEngine")

DB_FILE = "database.json"
db_content = {"users": [], "bots": [], "issued_keys": []}
active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}

class LoginRequest(BaseModel):
    email: str
    password: str

class KeyActivationRequest(BaseModel):
    userId: str
    key: str

class KeyGenRequest(BaseModel):
    months: int

class BroadcastRequest(BaseModel):
    botIds: List[str]
    message: str

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
                db_content["users"] = loaded.get("users", [])
                db_content["bots"] = loaded.get("bots", [])
                db_content["issued_keys"] = loaded.get("issued_keys", [])
        except Exception as e: 
            logger.error(f"Load DB Error: {e}")
            db_content = {"users": [], "bots": [], "issued_keys": []}

def check_license(user_id: str) -> bool:
    user = next((u for u in db_content.get("users", []) if str(u.get("id")) == str(user_id)), None)
    if not user: return False
    expires = user.get("licenseExpiresAt", 0)
    try:
        return float(expires) > (time.time() * 1000)
    except:
        return False

def add_log(bot_id: str, log_type: str, text: str, code: str = None):
    for b in db_content["bots"]:
        if b["id"] == bot_id:
            if "logs" not in b: b["logs"] = []
            b["logs"].insert(0, {
                "id": str(uuid.uuid4()),
                "timestamp": int(time.time() * 1000),
                "type": log_type,
                "text": text,
                "code": code
            })
            b["logs"] = b["logs"][:50]
            save_db()

async def bot_worker(bot_cfg: dict):
    bot_id = bot_cfg["id"]
    owner_id = bot_cfg["ownerId"]
    
    try:
        token = bot_cfg["token"].strip()
        # Чистим токен от возможного мусора путей
        if "root/" in token: token = token.split("root/")[0].strip()
        
        bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        dp = Dispatcher()
        active_bots[bot_id] = bot
        
        @dp.message(CommandStart())
        async def _start(m: Message):
            if not check_license(owner_id): return
            # Добавляем в подписчики если нет
            if "subscribers" not in bot_cfg: bot_cfg["subscribers"] = []
            if m.from_user.id not in bot_cfg["subscribers"]:
                bot_cfg["subscribers"].append(m.from_user.id)
                save_db()
            
            welcome = bot_cfg.get("welcomeMessage", "Привет!")
            await m.answer(welcome)
            add_log(bot_id, "incoming", f"User {m.from_user.id} started bot")

        @dp.message()
        async def _handle_all(m: Message):
            if not check_license(owner_id): return
            
            # Статистика
            if "stats" not in bot_cfg: bot_cfg["stats"] = {"totalMessages": 0}
            bot_cfg["stats"]["totalMessages"] = bot_cfg["stats"].get("totalMessages", 0) + 1
            
            admin_id = bot_cfg.get("adminChatId")
            
            # Если пишет админ и это ответ на сообщение
            if admin_id and str(m.from_user.id) == str(admin_id) and m.reply_to_message:
                reply_text = m.reply_to_message.text or m.reply_to_message.caption or ""
                match = re.search(r"ID: (\d+)", reply_text)
                if match:
                    target_user_id = int(match.group(1))
                    try:
                        await bot.send_message(target_user_id, m.text or "Медиа")
                        await m.reply("✅ Отправлено")
                        add_log(bot_id, "outgoing", f"Ответ пользователю {target_user_id}")
                    except Exception as e:
                        await m.reply(f"❌ Ошибка: {e}")
                return

            # Если пишет пользователь (не админ) - пересылаем админу
            if admin_id and str(m.from_user.id) != str(admin_id):
                try:
                    info = f"📩 <b>Сообщение от {m.from_user.full_name}</b>\nID: {m.from_user.id}\n\n"
                    if m.text:
                        await bot.send_message(admin_id, info + m.text)
                    else:
                        await bot.send_message(admin_id, info + "[Медиа]")
                        await m.forward(admin_id)
                    add_log(bot_id, "incoming", f"Сообщение от {m.from_user.id} переслано админу")
                except Exception as e:
                    logger.error(f"Forward error: {e}")

        add_log(bot_id, "system", "Бот успешно запущен")
        await dp.start_polling(bot)
    except Exception as e:
        add_log(bot_id, "error", f"Ошибка запуска: {str(e)}")
        logger.error(f"Bot {bot_id} crashed: {e}")
    finally:
        if bot_id in active_bots: del active_bots[bot_id]

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_db()
    logger.info("Сервер запускается, восстановление ботов...")
    for b in db_content.get("bots", []):
        if b.get("status") == "RUNNING":
            if check_license(b.get("ownerId")):
                active_tasks[b["id"]] = asyncio.create_task(bot_worker(b))
            else:
                b["status"] = "IDLE"
    save_db()
    yield
    for task in active_tasks.values(): task.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/ping")
async def ping(): return {"status": "online", "time": time.time()}

@app.post("/api/admin/generate-key")
async def admin_gen_key(req: KeyGenRequest, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET: raise HTTPException(403, "Invalid secret")
    new_key = f"BOT-{req.months}-{secrets.token_hex(3).upper()}"
    db_content["issued_keys"].append({"key": new_key, "months": req.months, "used": False, "createdAt": time.time()})
    save_db()
    return {"key": new_key}

@app.post("/api/license/activate")
async def activate_key(req: KeyActivationRequest):
    user = next((u for u in db_content["users"] if str(u.get("id")) == str(req.userId)), None)
    key_entry = next((k for k in db_content["issued_keys"] if k["key"] == req.key and not k["used"]), None)
    if not user: raise HTTPException(404, "User not found")
    if not key_entry: raise HTTPException(400, "Invalid or used key")
    
    now = int(time.time() * 1000)
    current_expiry = user.get("licenseExpiresAt", now)
    user["licenseExpiresAt"] = max(current_expiry, now) + (key_entry["months"] * 30 * 24 * 3600 * 1000)
    key_entry["used"] = True
    key_entry["usedBy"] = user["email"]
    save_db()
    return {"status": "ok", "newExpiry": user["licenseExpiresAt"]}

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    user = next((u for u in db_content["users"] if u["email"] == req.email and u["password"] == req.password), None)
    if not user: raise HTTPException(401, "Auth failed")
    return user

@app.post("/api/auth/register")
async def register(user_data: dict):
    if any(u["email"] == user_data["email"] for u in db_content["users"]):
        raise HTTPException(400, "Email exists")
    db_content["users"].append(user_data)
    save_db()
    return user_data

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    return [b for b in db_content["bots"] if str(b.get("ownerId")) == str(user_id)]

@app.post("/api/bots/save")
async def save_bot_api(bot_data: dict):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == bot_data["id"]), -1)
    if idx >= 0:
        # Сохраняем существующих подписчиков, чтобы не затереть
        subs = db_content["bots"][idx].get("subscribers", [])
        bot_data["subscribers"] = list(set(bot_data.get("subscribers", []) + subs))
        db_content["bots"][idx] = bot_data
    else:
        db_content["bots"].append(bot_data)
    save_db()
    return {"status": "ok"}

@app.post("/api/bots/start/{bot_id}")
async def start_bot(bot_id: str):
    bot_cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not bot_cfg: raise HTTPException(404)
    if not check_license(bot_cfg["ownerId"]): raise HTTPException(403, "License expired")
    
    if bot_id in active_tasks: 
        active_tasks[bot_id].cancel()
    
    active_tasks[bot_id] = asyncio.create_task(bot_worker(bot_cfg))
    bot_cfg["status"] = "RUNNING"
    save_db()
    return {"status": "ok"}

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel()
        del active_tasks[bot_id]
    for b in db_content["bots"]:
        if b["id"] == bot_id: b["status"] = "IDLE"
    save_db()
    return {"status": "ok"}

@app.post("/api/broadcast")
async def broadcast(req: BroadcastRequest):
    success = 0
    failed = 0
    for bot_id in req.botIds:
        bot_cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not bot_cfg or bot_id not in active_bots: continue
        
        bot = active_bots[bot_id]
        subs = bot_cfg.get("subscribers", [])
        for sub_id in subs:
            try:
                await bot.send_message(sub_id, req.message)
                success += 1
                await asyncio.sleep(0.05) # Защита от флуда
            except:
                failed += 1
    return {"success": success, "failed": failed}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
