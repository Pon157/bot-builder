
import asyncio
import logging
import json
import os
import time
import re
import secrets
import sys
import httpx
import uuid
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any, Union

from fastapi import FastAPI, HTTPException, Header, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ParseMode, ContentType
from aiogram.filters import CommandStart, Command, BaseFilter
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, CallbackQuery
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramUnauthorizedError

import uvicorn

# Попытка импорта сервиса почты
try:
    from email_service import EmailService
except ImportError:
    class EmailService:
        @staticmethod
        def send_verification_code(email, code): print(f"DEBUG CODE: {email} -> {code}"); return True
        @staticmethod
        def send_password_reset(email, code): print(f"DEBUG RESET: {email} -> {code}"); return True

# --- 1. CONFIG & LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(name)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotEngineCore")

def load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip().strip('"').strip("'")

load_env()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.critical("🛑 CRITICAL: Database credentials missing! Check .env file.")
    sys.exit(1)

# --- 2. GLOBAL STATE ---
active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}
verification_store: Dict[str, dict] = {} 

# --- 3. DATABASE (SUPABASE) ---
class SupabaseDB:
    def __init__(self, url: str, key: str):
        self.url = url
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

    async def query(self, table: str, method: str = "GET", params: dict = None, json_data: dict = None):
        async with httpx.AsyncClient() as client:
            url = f"{self.url}/rest/v1/{table}"
            try:
                resp = await client.request(method, url, params=params, json=json_data, headers=self.headers)
                if resp.status_code >= 400:
                    logger.error(f"Supabase Error [{method} {table}]: {resp.text}")
                    return []
                return resp.json() if resp.status_code != 204 else []
            except Exception as e:
                logger.error(f"Database connection failed: {e}")
                return []

db = SupabaseDB(SUPABASE_URL, SUPABASE_KEY)

# --- 4. CORE UTILS ---
def is_active_license(expiry_ms: int) -> bool:
    """Check if the license is valid based on timestamp."""
    return int(expiry_ms or 0) > int(time.time() * 1000)

def apply_template(text: str, m: Message, btn: str = "") -> str:
    """Replace {{tags}} in message templates."""
    if not text: return ""
    rep = {
        "{{id}}": str(m.from_user.id),
        "{{name}}": m.from_user.full_name or "Пользователь",
        "{{username}}": f"@{m.from_user.username}" if m.from_user.username else "нет",
        "{{button}}": btn
    }
    for k, v in rep.items():
        text = text.replace(k, v)
    return text

async def log_event(bot_id: str, ltype: str, text: str):
    """Add a system log entry for a specific bot."""
    res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "config"})
    if not res: return
    config = res[0].get('config', {})
    logs = config.get("logs", [])
    logs.insert(0, {
        "id": str(uuid.uuid4()),
        "timestamp": int(time.time()*1000),
        "type": ltype,
        "text": str(text)[:500]
    })
    config["logs"] = logs[:100]
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"config": config})

async def update_stats(bot_id: str, direction: str, config: dict):
    """Update bot statistics (Total, Daily, History)."""
    res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "stats"})
    if not res: return
    stats = res[0].get('stats', {})
    if not stats:
        stats = {"totalMessages": 0, "incomingToday": 0, "outgoingToday": 0, "history": []}
    
    stats["totalMessages"] = stats.get("totalMessages", 0) + 1
    if direction == "in": stats["incomingToday"] = stats.get("incomingToday", 0) + 1
    else: stats["outgoingToday"] = stats.get("outgoingToday", 0) + 1
    
    today = datetime.now().strftime("%d.%m")
    history = stats.get("history", [])
    if not history or history[-1]["date"] != today:
        history.append({
            "date": today, "incoming": 0, "outgoing": 0, 
            "totalUsers": len(config.get("connectedUsers", [])), "activeUsers": 1
        })
    
    if direction == "in": history[-1]["incoming"] += 1
    else: history[-1]["outgoing"] += 1
    
    history[-1]["totalUsers"] = len(config.get("connectedUsers", []))
    stats["history"] = history[-30:]
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"stats": stats})

# --- 5. BOT LOGIC (ENGINE) ---
async def start_bot_worker(bot_id: str, token: str):
    """Main worker function for a single bot instance."""
    logger.info(f"⚙️ Initializing bot instance: {bot_id}")
    session = AiohttpSession()
    bot = Bot(token=token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    active_bots[bot_id] = bot
    dp = Dispatcher()
    router = Router()

    @router.message(CommandStart())
    async def cmd_start_handler(m: Message):
        res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "config,license_expires_at"})
        if not res or not is_active_license(res[0]['license_expires_at']): return
        config = res[0]['config']
        
        # User management & registration
        users = config.get("connectedUsers", [])
        user = next((u for u in users if u['id'] == m.from_user.id), None)
        if not user:
            user = {
                "id": m.from_user.id, "first_name": m.from_user.first_name, 
                "username": m.from_user.username, "joined_at": int(time.time()), 
                "is_banned": False, "warns": 0, "is_active": True, "thread_id": None
            }
            users.append(user)
            config["connectedUsers"] = users
            await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"config": config})
            await log_event(bot_id, "info", f"New user started bot: {m.from_user.id}")

        # Build Keyboard
        btns = config.get("buttons", [])
        if btns:
            rows = [[KeyboardButton(text=b["text"])] for b in btns if b.get("text")]
            kb = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
        else:
            kb = ReplyKeyboardRemove()
        
        welcome_text = apply_template(config.get("welcomeMessage", "Привет!"), m)
        await m.answer(welcome_text, reply_markup=kb)
        await update_stats(bot_id, "out", config)

    @router.message()
    async def main_handler(m: Message):
        res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "config,license_expires_at"})
        if not res or not is_active_license(res[0]['license_expires_at']): return
        config = res[0]['config']
        admin_id = str(config.get("adminChatId", ""))
        settings = config.get("settings", {})

        # User identification
        users = config.get("connectedUsers", [])
        user = next((u for u in users if u['id'] == m.from_user.id), None)
        
        # Auto-registration if missed /start
        if not user:
            user = {"id": m.from_user.id, "first_name": m.from_user.first_name, "username": m.from_user.username, "joined_at": int(time.time()), "is_banned": False, "warns": 0, "is_active": True, "thread_id": None}
            users.append(user); config["connectedUsers"] = users
            await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"config": config})

        # 1. ADMIN LOGIC (LIVEGRAM REPLY)
        if admin_id and str(m.chat.id) == admin_id:
            target_id = None
            if m.reply_to_message:
                # Extract User ID from the info block sent earlier
                ref_text = m.reply_to_message.text or m.reply_to_message.caption or ""
                match = re.search(r"ID: (\d+)", ref_text)
                if match:
                    target_id = int(match.group(1))
                    # Link current topic to user if Topics enabled
                    if m.message_thread_id and settings.get("useTopics"):
                        target_user = next((u for u in users if u['id'] == target_id), None)
                        if target_user:
                            target_user['thread_id'] = m.message_thread_id
                            await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"config": config})
                
            if target_id:
                try:
                    # Support for all types of content (copy_message is best for media)
                    await bot.copy_message(target_id, m.chat.id, m.message_id)
                    await update_stats(bot_id, "out", config)
                    return
                except Exception as e:
                    await m.reply(f"❌ Error sending to user: {e}")
            return

        # Block banned users
        if user.get("is_banned"): return

        # 2. BUTTONS & TRIGGERS (USER SIDE)
        if m.text:
            text_norm = m.text.lower().strip()
            # Buttons (exact match)
            for btn in config.get("buttons", []):
                if btn.get("text") and btn["text"].lower().strip() == text_norm:
                    if btn.get("type") == "request" and admin_id:
                        tpl = btn.get("adminTemplate") or "📩 New Request: {{button}}\nFrom: {{name}} (ID: <code>{{id}}</code>)"
                        tid = user.get('thread_id') if settings.get("useTopics") else None
                        await bot.send_message(admin_id, apply_template(tpl, m, btn["text"]), message_thread_id=tid)
                    
                    if btn.get("response"):
                        await m.answer(apply_template(btn.get("response"), m))
                        await update_stats(bot_id, "out", config)
                    return
            
            # Triggers (keyword in message)
            for tr in config.get("triggers", []):
                if tr.get("keyword") and tr["keyword"].lower().strip() in text_norm:
                    await m.answer(apply_template(tr.get("response", ""), m))
                    await update_stats(bot_id, "out", config)
                    return

        # 3. FORWARDING (LIVEGRAM MODE)
        if admin_id:
            try:
                # Send User Info Card
                info = f"👤 <b>{m.from_user.full_name}</b>"
                if m.from_user.username: info += f" (@{m.from_user.username})"
                info += f"\n🆔 ID: <code>{m.from_user.id}</code>"
                
                tid = user.get('thread_id') if settings.get("useTopics") else None
                await bot.send_message(admin_id, info, message_thread_id=tid)
                # Copy the content (photo/text/voice/etc)
                await bot.copy_message(admin_id, m.chat.id, m.message_id, message_thread_id=tid)
                
                await update_stats(bot_id, "in", config)
                await log_event(bot_id, "incoming", f"Message from {m.from_user.id} forwarded")
            except Exception as e:
                logger.error(f"Failed to forward message from {m.from_user.id}: {e}")

    dp.include_router(router)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logger.error(f"Polling crashed for {bot_id}: {e}")
    finally:
        await session.close()

# --- 6. FASTAPI WEB SERVER ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Restore running bots on startup
    rows = await db.query("bots", params={"status": "eq.RUNNING", "select": "id,token,license_expires_at"})
    for b in rows:
        if is_active_license(b['license_expires_at']):
            active_tasks[b['id']] = asyncio.create_task(start_bot_worker(b['id'], b['token']))
    yield
    # Shutdown all tasks
    for t in active_tasks.values(): t.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/ping")
async def ping_route():
    return {"status": "online", "time": int(time.time()), "active_bots": len(active_tasks)}

@app.post("/api/auth/login")
async def login_route(req: dict):
    res = await db.query("users", params={"email": f"eq.{req['email']}", "password": f"eq.{req['password']}"})
    if not res: raise HTTPException(401, "Invalid email or password")
    return res[0]

@app.get("/api/bots/{user_id}")
async def get_user_bots_route(user_id: str):
    rows = await db.query("bots", params={"owner_id": f"eq.{user_id}"})
    for r in rows:
        r['status'] = "RUNNING" if r['id'] in active_tasks else "IDLE"
    return rows

@app.post("/api/bots/save")
async def save_bot_route(data: dict):
    bid = data['id']
    # Robust merge payload
    payload = {
        "id": bid,
        "owner_id": data['ownerId'],
        "name": data['name'],
        "token": data['token'],
        "license_expires_at": data.get('licenseExpiresAt', 0),
        "config": {
            "welcomeMessage": data.get('welcomeMessage', ""),
            "adminChatId": data.get('adminChatId', ""),
            "buttons": data.get('buttons', []),
            "triggers": data.get('triggers', []),
            "settings": data.get('settings', {}),
            "connectedUsers": data.get('connectedUsers', []),
            "logs": data.get('logs', [])
        }
    }
    await db.query("bots", method="POST", json_data=payload, params={"on_conflict": "id"})
    
    # Reload bot if already running to apply new buttons/settings
    if bid in active_tasks:
        active_tasks[bid].cancel()
        active_tasks[bid] = asyncio.create_task(start_bot_worker(bid, data['token']))
        
    return {"status": "ok"}

@app.post("/api/bots/start/{bot_id}")
async def start_bot_route(bot_id: str):
    res = await db.query("bots", params={"id": f"eq.{bot_id}"})
    if not res: raise HTTPException(404, "Bot record not found")
    bot_data = res[0]
    
    if not is_active_license(bot_data['license_expires_at']):
        raise HTTPException(403, "Subscription expired for this bot")
    
    # Check token validity
    try:
        async with Bot(token=bot_data['token']).context() as test_bot:
            await test_bot.get_me()
    except Exception as e:
        raise HTTPException(400, f"Telegram rejected token: {e}")

    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"status": "RUNNING"})
    if bot_id not in active_tasks:
        active_tasks[bot_id] = asyncio.create_task(start_bot_worker(bot_id, bot_data['token']))
    
    return {"status": "ok"}

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot_route(bot_id: str):
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"status": "IDLE"})
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel()
        del active_tasks[bot_id]
    if bot_id in active_bots:
        del active_bots[bot_id]
    return {"status": "ok"}

@app.post("/api/broadcast")
async def broadcast_route(req: dict):
    bot_ids = req.get("botIds", [])
    msg_text = req.get("message", "")
    if not msg_text: raise HTTPException(400, "Cannot send empty message")
    
    results = {"success": 0, "failed": 0}
    for bid in bot_ids:
        bot = active_bots.get(bid)
        if not bot: continue
        
        bot_res = await db.query("bots", params={"id": f"eq.{bid}", "select": "config"})
        if not bot_res: continue
        
        users = [u['id'] for u in bot_res[0]['config'].get('connectedUsers', []) if not u.get('is_banned')]
        for uid in users:
            try:
                await bot.send_message(uid, msg_text)
                results["success"] += 1
            except:
                results["failed"] += 1
            await asyncio.sleep(0.05) # Prevent flood
            
    return results

@app.post("/api/license/activate")
async def activate_license_route(req: dict):
    bot_id, key = req.get("botId"), req.get("key")
    if not key or not bot_id: raise HTTPException(400, "Bot ID and Key are required")
    
    match = re.match(r"BOT-1-(\d+)-(\w+)", key)
    if not match: raise HTTPException(400, "Invalid activation key format")
    
    months = int(match.group(1))
    res = await db.query("bots", params={"id": f"eq.{bot_id}"})
    if not res: raise HTTPException(404, "Bot not found")
    
    current_expiry = max(int(time.time() * 1000), res[0]['license_expires_at'])
    new_expiry = current_expiry + (months * 30 * 24 * 3600 * 1000)
    
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"license_expires_at": new_expiry})
    return {"status": "ok", "newExpiry": new_expiry}

@app.post("/api/admin/generate-key")
async def admin_generate_key_route(req: dict, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET: raise HTTPException(403, "Forbidden")
    months = req.get("months", 1)
    new_key = f"BOT-1-{months}-{secrets.token_hex(4).upper()}"
    return {"key": new_key}

@app.delete("/api/bots/delete/{bot_id}")
async def delete_bot_route(bot_id: str):
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel()
        del active_tasks[bot_id]
    await db.query("bots", method="DELETE", params={"id": f"eq.{bot_id}"})
    return {"status": "ok"}

if __name__ == "__main__":
    logger.info("⚡ Engine core is warming up...")
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
