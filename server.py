
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
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
import uvicorn

# --- Инициализация окружения ---
BASE_DIR = "/root/bot-builder/bot-builder"
if os.path.exists(BASE_DIR):
    os.chdir(BASE_DIR)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BotEngine")

def load_env():
    path = os.path.join(BASE_DIR, '.env')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip()
                if line and '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    val = v.strip().strip('"').strip("'")
                    os.environ[k.strip()] = val

load_env()
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")
DB_FILE = "database.json"

# --- Состояние ---
db_content = {"users": [], "bots": [], "issued_keys": []}
active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}

# --- DB Core ---
def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db_content, f, ensure_ascii=False, indent=2)
    except Exception as e: logger.error(f"Save DB Error: {e}")

def load_db():
    global db_content
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                db_content["users"] = loaded.get("users", [])
                db_content["bots"] = loaded.get("bots", [])
                db_content["issued_keys"] = loaded.get("issued_keys", [])
                logger.info(f"Database loaded: {len(db_content['users'])} users, {len(db_content['bots'])} bots")
        except Exception as e: 
            logger.error(f"Load DB Error: {e}")
            db_content = {"users": [], "bots": [], "issued_keys": []}

def add_bot_log(bot_id: str, log_type: str, text: str, code: str = None):
    bot = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not bot: return
    log_entry = {"id": str(time.time()), "timestamp": int(time.time() * 1000), "type": log_type, "text": text, "code": code}
    bot.setdefault("logs", []).insert(0, log_entry)
    bot["logs"] = bot["logs"][:100]
    save_db()

def update_bot_stats(bot_id: str, stat_type: str):
    bot = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not bot: return
    if "stats" not in bot or not bot["stats"]: 
        bot["stats"] = {"totalMessages": 0, "incomingToday": 0, "outgoingToday": 0, "bannedCount": 0, "history": []}
    bot["stats"]["totalMessages"] += 1
    if stat_type == "incoming": bot["stats"]["incomingToday"] += 1
    else: bot["stats"]["outgoingToday"] += 1
    save_db()

def check_license(owner_id: str) -> bool:
    user = next((u for u in db_content["users"] if str(u["id"]) == str(owner_id)), None)
    if not user: return False
    return float(user.get("licenseExpiresAt", 0)) > (time.time() * 1000)

# --- Bot Engine Logic ---
def get_keyboard(config: dict):
    buttons = config.get("buttons", [])
    if not buttons: return None
    kb_buttons = []
    row = []
    for btn in buttons:
        if btn.get("text"):
            row.append(KeyboardButton(text=btn["text"]))
            if len(row) == 2:
                kb_buttons.append(row); row = []
    if row: kb_buttons.append(row)
    return ReplyKeyboardMarkup(keyboard=kb_buttons, resize_keyboard=True)

async def bot_worker(bot_id: str, token: str):
    session = AiohttpSession()
    bot = Bot(token=token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    active_bots[bot_id] = bot
    dp = Dispatcher()
    router = Router()

    @router.message(CommandStart())
    async def cmd_start(m: Message):
        config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not config: return
        if not check_license(config["ownerId"]): return
        
        user = next((u for u in config.get("connectedUsers", []) if u["id"] == m.from_user.id), None)
        if not user:
            user = {"id": m.from_user.id, "first_name": m.from_user.first_name, "username": m.from_user.username, "joined_at": int(time.time()), "is_banned": False, "is_active": True, "warns": 0}
            config.setdefault("connectedUsers", []).append(user)
            config["usersCount"] = len(config["connectedUsers"])
            add_bot_log(bot_id, "system", f"New user: {m.from_user.full_name}")
            save_db()
        
        # Регистрация подписчика для рассылок
        if "subscribers" not in config: config["subscribers"] = []
        if m.from_user.id not in config["subscribers"]:
            config["subscribers"].append(m.from_user.id)
            save_db()

        if user["is_banned"]: return
        await m.answer(config.get("welcomeMessage", "Welcome!"), reply_markup=get_keyboard(config))

    @router.message(Command("ban", "unban", "warn", "unwarn"))
    async def admin_moderation(m: Message):
        config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if str(m.chat.id) != str(config.get("adminChatId")): return
        
        target_id = None
        if m.message_thread_id:
            user = next((u for u in config.get("connectedUsers", []) if u.get("thread_id") == m.message_thread_id), None)
            if user: target_id = user["id"]
        
        if not target_id and m.reply_to_message:
            match = re.search(r"ID: (\d+)", m.reply_to_message.text or m.reply_to_message.caption or "")
            if match: target_id = int(match.group(1))
            
        if not target_id:
            parts = m.text.split()
            if len(parts) > 1 and parts[1].isdigit(): target_id = int(parts[1])

        if not target_id: return await m.reply("Could not determine User ID.")
        
        user = next((u for u in config.get("connectedUsers", []) if u["id"] == target_id), None)
        if not user: return await m.reply("User not found in DB.")
        
        cmd = m.text.split()[0].lower()
        if "/ban" in cmd: user["is_banned"] = True
        elif "/unban" in cmd: user["is_banned"] = False
        elif "/warn" in cmd: user["warns"] = user.get("warns", 0) + 1
        elif "/unwarn" in cmd: user["warns"] = max(0, user.get("warns", 0) - 1)
        
        save_db()
        await m.reply(f"Action {cmd} applied to user {target_id}")

    @router.message()
    async def handle_msg(m: Message):
        config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not config or not check_license(config["ownerId"]): return
        admin_id = config.get("adminChatId")
        if not admin_id: return

        # 1. Логика Админа (Ответ пользователю)
        if str(m.chat.id) == str(admin_id):
            if m.text and m.text.startswith("/"): return
            target_id = None
            if m.message_thread_id:
                user = next((u for u in config.get("connectedUsers", []) if u.get("thread_id") == m.message_thread_id), None)
                if user: target_id = user["id"]
            if not target_id and m.reply_to_message:
                match = re.search(r"ID: (\d+)", m.reply_to_message.text or m.reply_to_message.caption or "")
                if match: target_id = int(match.group(1))
            if target_id:
                try:
                    await bot.copy_message(chat_id=target_id, from_chat_id=m.chat.id, message_id=m.message_id)
                    update_bot_stats(bot_id, "outgoing")
                except Exception as e: await m.reply(f"Error: {e}")
            return

        # 2. Логика Пользователя
        user = next((u for u in config.get("connectedUsers", []) if u["id"] == m.from_user.id), None)
        if not user or user["is_banned"]: return

        # Кнопки и Тиггеры
        if m.text:
            text_low = m.text.lower()
            
            # Проверка кнопок меню
            for btn in config.get("buttons", []):
                if btn.get("text") and btn["text"].lower() == text_low:
                    # Если кнопка - обращение, уведомляем админа
                    if btn.get("type") == "request":
                        try:
                            info = f"🆘 <b>Новое обращение!</b>\n👤 От: {m.from_user.full_name}\n🆔 ID: <code>{m.from_user.id}</code>\n📂 Тема: <i>{btn['text']}</i>"
                            await bot.send_message(admin_id, info)
                        except: pass
                    return await m.answer(btn.get("response", "...")), update_bot_stats(bot_id, "outgoing")
            
            # Проверка триггеров
            for trig in config.get("triggers", []):
                if trig.get("keyword") and trig["keyword"].lower() in text_low:
                    return await m.answer(trig.get("response", "...")), update_bot_stats(bot_id, "outgoing")

        # Пересылка админу (Feedback)
        use_topics = config.get("settings", {}).get("useTopics", False)
        target_thread = None
        if use_topics:
            if not user.get("thread_id"):
                try:
                    topic = await bot.create_forum_topic(admin_id, f"{m.from_user.first_name} [{m.from_user.id}]")
                    user["thread_id"] = topic.message_thread_id
                    save_db()
                    info = f"👤 <b>Новый диалог</b>\nID: <code>{m.from_user.id}</code>\n"
                    if config["settings"].get("showUsername") and m.from_user.username:
                        info += f"Username: @{m.from_user.username}\n"
                    await bot.send_message(admin_id, info, message_thread_id=user["thread_id"])
                except Exception: use_topics = False
            target_thread = user.get("thread_id")

        try:
            if not use_topics:
                await bot.send_message(admin_id, f"📩 <b>ID: {m.from_user.id}</b>\nName: {m.from_user.full_name}")
            await bot.copy_message(admin_id, m.chat.id, m.message_id, message_thread_id=target_thread)
            update_bot_stats(bot_id, "incoming")
        except Exception as e: add_bot_log(bot_id, "error", f"Forward fail: {e}")

    dp.include_router(router)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, skip_updates=True)
    finally: await session.close()

# --- API Endpoints ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_db()
    for b in db_content["bots"]:
        if b.get("status") == "RUNNING" and check_license(b["ownerId"]):
            active_tasks[b["id"]] = asyncio.create_task(bot_worker(b["id"], b["token"]))
    yield
    for t in active_tasks.values(): t.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class BroadcastRequest(BaseModel):
    botIds: List[str]
    message: str

@app.get("/api/ping")
async def ping(): return {"status": "online"}

@app.post("/api/auth/register")
async def register(user: dict):
    if any(u["email"] == user["email"] for u in db_content["users"]):
        raise HTTPException(status_code=400, detail="User already exists")
    db_content["users"].append(user)
    save_db()
    return user

@app.post("/api/auth/login")
async def login(req: dict):
    user = next((u for u in db_content["users"] if u["email"] == req["email"] and u["password"] == req["password"]), None)
    if not user: raise HTTPException(status_code=401, detail="Invalid credentials")
    return user

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    return [b for b in db_content["bots"] if str(b["ownerId"]) == str(user_id)]

@app.post("/api/bots/save")
async def save_bot_endpoint(bot_data: dict):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == bot_data["id"]), -1)
    if idx >= 0:
        bot_data.setdefault("logs", db_content["bots"][idx].get("logs", []))
        bot_data.setdefault("connectedUsers", db_content["bots"][idx].get("connectedUsers", []))
        bot_data.setdefault("subscribers", db_content["bots"][idx].get("subscribers", []))
        db_content["bots"][idx] = bot_data
    else: db_content["bots"].append(bot_data)
    save_db()
    return {"status": "ok"}

@app.delete("/api/bots/delete/{bot_id}")
async def delete_bot_global(bot_id: str):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == bot_id), -1)
    if idx >= 0:
        if bot_id in active_tasks:
            active_tasks[bot_id].cancel()
            del active_tasks[bot_id]
        if bot_id in active_bots: del active_bots[bot_id]
        db_content["bots"].pop(idx)
        save_db()
        return {"status": "ok"}
    raise HTTPException(status_code=404, detail="Bot not found")

@app.post("/api/bots/start/{bot_id}")
async def start_bot(bot_id: str):
    bot_cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not bot_cfg: raise HTTPException(404)
    if not check_license(bot_cfg["ownerId"]): raise HTTPException(403, "License expired")
    if bot_id in active_tasks and not active_tasks[bot_id].done(): return {"status": "ok"}
    active_tasks[bot_id] = asyncio.create_task(bot_worker(bot_id, bot_cfg["token"]))
    bot_cfg["status"] = "RUNNING"
    save_db()
    return {"status": "ok"}

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel()
        del active_tasks[bot_id]
    if bot_id in active_bots: del active_bots[bot_id]
    for b in db_content["bots"]:
        if b["id"] == bot_id: b["status"] = "IDLE"
    save_db()
    return {"status": "ok"}

@app.post("/api/broadcast")
async def broadcast(req: BroadcastRequest):
    success, failed = 0, 0
    for bot_id in req.botIds:
        bot_instance = active_bots.get(bot_id)
        config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if bot_instance and config:
            for uid in config.get("subscribers", []):
                try:
                    await bot_instance.send_message(uid, req.message)
                    success += 1
                    update_bot_stats(bot_id, "outgoing")
                except Exception: failed += 1
    return {"success": success, "failed": failed}

@app.post("/api/license/activate")
async def activate_key(req: dict):
    u = next((u for u in db_content["users"] if str(u["id"]) == str(req['userId'])), None)
    k = next((k for k in db_content["issued_keys"] if k["key"] == req['key'] and not k["used"]), None)
    if not u or not k: raise HTTPException(400, "Invalid key or user")
    
    now = int(time.time() * 1000)
    current_expiry = max(u.get("licenseExpiresAt", now), now)
    u["licenseExpiresAt"] = current_expiry + (k["months"] * 30 * 24 * 3600 * 1000)
    k["used"] = True
    save_db()
    return {"status": "ok", "newExpiry": u["licenseExpiresAt"]}

@app.post("/api/admin/generate-key")
async def admin_gen_key(req: dict, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET: raise HTTPException(403)
    key = f"BOT-{req['months']}-{secrets.token_hex(3).upper()}"
    db_content.setdefault("issued_keys", []).append({
        "key": key, 
        "months": req['months'], 
        "used": False,
        "created_at": int(time.time())
    })
    save_db()
    return {"key": key}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
