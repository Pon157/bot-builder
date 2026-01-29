
import asyncio
import logging
import json
import os
import time
import re
import uuid
import secrets
import sys
import httpx
import random
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ParseMode, ContentType
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

import uvicorn
from email_service import EmailService

# --- 1. CONFIG & DB ---
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

class SupabaseDB:
    def __init__(self, url: str, key: str):
        self.url = url
        self.headers = {
            "apikey": key, "Authorization": f"Bearer {key}",
            "Content-Type": "application/json", "Prefer": "return=representation"
        }

    async def query(self, table: str, method: str = "GET", params: dict = None, json_data: dict = None):
        async with httpx.AsyncClient() as client:
            url = f"{self.url}/rest/v1/{table}"
            try:
                resp = await client.request(method, url, params=params, json=json_data, headers=self.headers)
                if resp.status_code >= 400:
                    logger.error(f"Supabase Error: {resp.text}")
                return resp.json() if resp.status_code < 400 and resp.status_code != 204 else []
            except Exception as e:
                logger.error(f"DB Error: {e}")
                return []

db = SupabaseDB(SUPABASE_URL, SUPABASE_KEY)

# --- 2. GLOBALS ---
active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}
bot_configs: Dict[str, dict] = {}
pending_verifications: Dict[str, dict] = {} # {email: {code: str, type: str, data: dict}}

# --- 3. UTILS ---
def is_active_license(expiry: int) -> bool:
    return int(expiry or 0) > int(time.time() * 1000)

def format_msg(template: str, m: Message, btn_text: str = "") -> str:
    if not template: return ""
    res = template.replace("{{id}}", str(m.from_user.id))
    res = res.replace("{{name}}", m.from_user.full_name or "User")
    res = res.replace("{{username}}", f"@{m.from_user.username}" if m.from_user.username else "none")
    res = res.replace("{{button}}", btn_text)
    return res

async def update_stats_in_db(bot_id: str, direction: str):
    res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "stats,config"})
    if not res: return
    stats = res[0].get('stats', {}) or {"totalMessages": 0, "incomingToday": 0, "outgoingToday": 0, "history": []}
    config = res[0].get('config', {})
    
    stats["totalMessages"] = stats.get("totalMessages", 0) + 1
    if direction == "in": stats["incomingToday"] = stats.get("incomingToday", 0) + 1
    else: stats["outgoingToday"] = stats.get("outgoingToday", 0) + 1
    
    today = datetime.now().strftime("%d.%m")
    history = stats.get("history", [])
    if not history or history[-1]["date"] != today:
        history.append({"date": today, "incoming": 0, "outgoing": 0, "totalUsers": len(config.get("connectedUsers", []))})
    
    if direction == "in": history[-1]["incoming"] += 1
    else: history[-1]["outgoing"] += 1
    stats["history"] = history[-30:]
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"stats": stats})

# --- 4. BOT WORKER ---
async def bot_worker_task(bot_id: str, token: str):
    logger.info(f"🚀 Bot task starting: {bot_id}")
    res = await db.query("bots", params={"id": f"eq.{bot_id}"})
    if not res: return
    bot_configs[bot_id] = res[0]

    session = AiohttpSession()
    bot = Bot(token=token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    active_bots[bot_id] = bot
    dp = Dispatcher()
    router = Router()

    @router.message(CommandStart())
    async def cmd_start(m: Message):
        full_data = bot_configs.get(bot_id)
        if not full_data or not is_active_license(full_data['license_expires_at']): return
        config = full_data.get('config', {})
        
        users = config.get("connectedUsers", [])
        user = next((u for u in users if str(u['id']) == str(m.from_user.id)), None)
        if not user:
            user = {"id": m.from_user.id, "first_name": m.from_user.first_name, "username": m.from_user.username, "joined_at": int(time.time()), "is_banned": False, "warns": 0, "thread_id": None}
            users.append(user); config["connectedUsers"] = users
            await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"config": config})
            bot_configs[bot_id]['config'] = config

        if user.get("is_banned"): return
        rows = [[KeyboardButton(text=b["text"])] for b in config.get("buttons", []) if b.get("text")]
        kb = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True) if rows else ReplyKeyboardRemove()
        await m.answer(format_msg(config.get("welcomeMessage", "Welcome!"), m), reply_markup=kb)
        asyncio.create_task(update_stats_in_db(bot_id, "out"))

    @router.message(Command("warn", "unwarn", "ban", "unban"))
    async def admin_moderation(m: Message):
        full_data = bot_configs.get(bot_id)
        if not full_data: return
        config = full_data.get('config', {})
        if str(m.chat.id) != str(config.get("adminChatId")): return

        target_user = None
        if m.message_thread_id:
            target_user = next((u for u in config.get("connectedUsers", []) if str(u.get("thread_id")) == str(m.message_thread_id)), None)
        if not target_user and m.reply_to_message:
            match = re.search(r"ID: (\d+)", m.reply_to_message.text or m.reply_to_message.caption or "")
            if match:
                uid = int(match.group(1))
                target_user = next((u for u in config.get("connectedUsers", []) if u["id"] == uid), None)

        if not target_user: return await m.reply("❌ User not found.")

        cmd = m.text.split()[0].replace("/", "").lower()
        if cmd == "warn":
            target_user["warns"] = target_user.get("warns", 0) + 1
            await bot.send_message(target_user["id"], f"⚠️ Предупреждение ({target_user['warns']})")
        elif cmd == "ban":
            target_user["is_banned"] = True
            await bot.send_message(target_user["id"], "🚫 Вы заблокированы.")
        elif cmd == "unban":
            target_user["is_banned"] = False
            await bot.send_message(target_user["id"], "✅ Разблокированы.")

        await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"config": config})
        bot_configs[bot_id]['config'] = config
        await m.answer(f"✅ {cmd} applied.")

    @router.message()
    async def main_handler(m: Message):
        full_data = bot_configs.get(bot_id)
        if not full_data or not is_active_license(full_data['license_expires_at']): return
        config = full_data.get('config', {})
        admin_id = str(config.get("adminChatId", ""))

        # Admin reply logic
        if admin_id and str(m.chat.id) == admin_id:
            target_id = None
            if m.message_thread_id:
                u = next((u for u in config.get("connectedUsers", []) if str(u.get("thread_id")) == str(m.message_thread_id)), None)
                if u: target_id = u["id"]
            if not target_id and m.reply_to_message:
                match = re.search(r"ID: (\d+)", m.reply_to_message.text or m.reply_to_message.caption or "")
                if match: target_id = int(match.group(1))
            
            if target_id:
                try:
                    await bot.copy_message(target_id, m.chat.id, m.message_id)
                    asyncio.create_task(update_stats_in_db(bot_id, "out"))
                except Exception as e: await m.reply(f"❌ Error: {e}")
            return

        # User logic
        users = config.get("connectedUsers", [])
        user = next((u for u in users if str(u['id']) == str(m.from_user.id)), None)
        if not user:
            user = {"id": m.from_user.id, "first_name": m.from_user.first_name, "username": m.from_user.username, "joined_at": int(time.time()), "is_banned": False, "warns": 0, "thread_id": None}
            users.append(user); config["connectedUsers"] = users
            await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"config": config})
            bot_configs[bot_id]['config'] = config

        if user.get("is_banned"): return

        # Buttons/Triggers
        if m.text:
            low = m.text.lower().strip()
            for btn in config.get("buttons", []):
                if btn.get("text") and btn["text"].lower().strip() == low:
                    if btn.get("type") == "request" and admin_id:
                        tid = user.get("thread_id")
                        tpl = btn.get("adminTemplate") or "📩 Request: {{button}}\nFrom: {{name}} (ID: {{id}})"
                        await bot.send_message(admin_id, format_msg(tpl, m, btn["text"]), message_thread_id=tid)
                    if btn.get("response"):
                        await m.answer(format_msg(btn["response"], m))
                        asyncio.create_task(update_stats_in_db(bot_id, "out"))
                    return
            for tr in config.get("triggers", []):
                if tr.get("keyword") and tr["keyword"].lower().strip() in low:
                    await m.answer(format_msg(tr.get("response", ""), m))
                    asyncio.create_task(update_stats_in_db(bot_id, "out"))
                    return

        # Forwarding
        if admin_id:
            tid = user.get("thread_id")
            info = f"👤 <b>{m.from_user.full_name}</b> (ID: <code>{m.from_user.id}</code>)"
            await bot.send_message(admin_id, info, message_thread_id=tid)
            await bot.copy_message(admin_id, m.chat.id, m.message_id, message_thread_id=tid)
            asyncio.create_task(update_stats_in_db(bot_id, "in"))

    dp.include_router(router)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, skip_updates=True)
    finally: await session.close()

# --- 5. FASTAPI ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    rows = await db.query("bots", params={"status": "eq.RUNNING"})
    for b in rows:
        if is_active_license(b['license_expires_at']):
            active_tasks[b['id']] = asyncio.create_task(bot_worker_task(b['id'], b['token']))
    yield
    for t in active_tasks.values(): t.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/ping")
async def ping(): return {"status": "online"}

# --- AUTH ENDPOINTS ---
@app.post("/api/auth/login")
async def login_endpoint(req: dict):
    res = await db.query("users", params={"email": f"eq.{req['email']}", "password": f"eq.{req['password']}"})
    if not res: raise HTTPException(401, "Invalid credentials")
    return res[0]

@app.post("/api/auth/verify-request")
async def verify_request(req: dict):
    email = req.get("email", "").lower()
    code = str(random.randint(100000, 999999))
    if EmailService.send_verification_code(email, code):
        pending_verifications[email] = {"code": code, "type": "register"}
        return {"status": "ok"}
    raise HTTPException(500, "Failed to send email")

@app.post("/api/auth/register")
async def register_endpoint(req: dict):
    email = req.get("email", "").lower()
    pv = pending_verifications.get(email)
    if not pv or pv["code"] != req.get("code"):
        raise HTTPException(400, "Invalid code")
    
    payload = {
        "id": str(uuid.uuid4()),
        "email": email,
        "username": req.get("username", email.split("@")[0]),
        "password": req.get("password"),
        "balance": 0,
        "botsCreated": 0,
        "licenseExpiresAt": int(time.time()*1000) + (3 * 24 * 3600 * 1000)
    }
    await db.query("users", method="POST", json_data=payload)
    del pending_verifications[email]
    return payload

@app.post("/api/auth/forgot-password")
async def forgot_password(req: dict):
    email = req.get("email", "").lower()
    res = await db.query("users", params={"email": f"eq.{email}"})
    if not res: raise HTTPException(404, "User not found")
    code = str(random.randint(100000, 999999))
    if EmailService.send_password_reset(email, code):
        pending_verifications[email] = {"code": code, "type": "reset"}
        return {"status": "ok"}
    raise HTTPException(500, "Failed to send email")

@app.post("/api/auth/reset-password")
async def reset_password(req: dict):
    email = req.get("email", "").lower()
    pv = pending_verifications.get(email)
    if not pv or pv["code"] != req.get("code"):
        raise HTTPException(400, "Invalid code")
    await db.query("users", method="PATCH", params={"email": f"eq.{email}"}, json_data={"password": req.get("newPassword")})
    del pending_verifications[email]
    return {"status": "ok"}

# --- BOT ENDPOINTS ---
@app.post("/api/bots/save")
async def save_bot(data: dict):
    bid = data['id']
    payload = {
        "id": bid, "owner_id": data['ownerId'], "name": data['name'], "token": data['token'],
        "license_expires_at": data.get('licenseExpiresAt', 0),
        "config": {
            "welcomeMessage": data.get('welcomeMessage', ""),
            "adminChatId": str(data.get('adminChatId', "")),
            "buttons": data.get('buttons', []), "triggers": data.get('triggers', []),
            "settings": data.get('settings', {}), "connectedUsers": data.get('connectedUsers', [])
        }
    }
    await db.query("bots", method="POST", json_data=payload, params={"on_conflict": "id"})
    res = await db.query("bots", params={"id": f"eq.{bid}"})
    if res: bot_configs[bid] = res[0]
    return {"status": "ok"}

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    rows = await db.query("bots", params={"owner_id": f"eq.{user_id}"})
    for r in rows: r['status'] = "RUNNING" if r['id'] in active_tasks else "IDLE"
    return rows

@app.post("/api/bots/start/{bot_id}")
async def start_bot(bot_id: str):
    res = await db.query("bots", params={"id": f"eq.{bot_id}"})
    if not res: raise HTTPException(404)
    if not is_active_license(res[0]['license_expires_at']): raise HTTPException(403)
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"status": "RUNNING"})
    if bot_id in active_tasks: active_tasks[bot_id].cancel()
    active_tasks[bot_id] = asyncio.create_task(bot_worker_task(bot_id, res[0]['token']))
    return {"status": "ok"}

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"status": "IDLE"})
    if bot_id in active_tasks: active_tasks[bot_id].cancel(); del active_tasks[bot_id]
    return {"status": "ok"}

@app.post("/api/broadcast")
async def broadcast(req: dict):
    bot_ids, msg = req.get("botIds", []), req.get("message", "")
    res_data = {"success": 0, "failed": 0}
    for bid in bot_ids:
        bot = active_bots.get(bid)
        if not bot: continue
        conf = bot_configs.get(bid, {}).get('config', {})
        users = [u['id'] for u in conf.get('connectedUsers', []) if not u.get('is_banned')]
        for uid in users:
            try: await bot.send_message(uid, msg); res_data["success"] += 1
            except: res_data["failed"] += 1
            await asyncio.sleep(0.05)
    return res_data

@app.post("/api/license/activate")
async def activate_lic(req: dict):
    bot_id, key = req.get("botId"), req.get("key")
    m = re.match(r"BOT-(\d+)-(\w+)", key)
    if not m: raise HTTPException(400)
    months = int(m.group(1))
    res = await db.query("bots", params={"id": f"eq.{bot_id}"})
    expiry = max(int(time.time()*1000), res[0]['license_expires_at']) + (months * 30 * 24 * 3600 * 1000)
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"license_expires_at": expiry})
    if bot_id in bot_configs: bot_configs[bot_id]['license_expires_at'] = expiry
    return {"status": "ok", "newExpiry": expiry}

@app.post("/api/admin/generate-key")
async def gen_key(req: dict, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET: raise HTTPException(403)
    return {"key": f"BOT-{req.get('months', 1)}-{secrets.token_hex(3).upper()}"}

@app.delete("/api/bots/delete/{bot_id}")
async def delete_bot(bot_id: str):
    if bot_id in active_tasks: active_tasks[bot_id].cancel(); del active_tasks[bot_id]
    await db.query("bots", method="DELETE", params={"id": f"eq.{bot_id}"})
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
