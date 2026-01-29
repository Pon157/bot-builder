
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
from typing import Dict, List, Optional, Any, Union

from fastapi import FastAPI, HTTPException, Header, Request, Depends, APIRouter, status, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ParseMode, ContentType
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, ErrorEvent
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

import uvicorn
from email_service import EmailService

# --- CONFIG & LOGGING ---
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

# --- DATABASE LAYER ---
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
            headers = self.headers.copy()
            if method == "POST" and params and "on_conflict" in params:
                headers["Prefer"] = "resolution=merge-duplicates,return=representation"
            try:
                resp = await client.request(method, url, params=params, json=json_data, headers=headers)
                if resp.status_code >= 400:
                    logger.error(f"Supabase Error ({resp.status_code}) on {table}: {resp.text}")
                    return []
                return resp.json() if resp.status_code != 204 else []
            except Exception as e:
                logger.error(f"Database connection error: {e}")
                return []

db = SupabaseDB(SUPABASE_URL, SUPABASE_KEY)

# --- GLOBAL STATE ---
active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}
bot_configs: Dict[str, dict] = {}
pending_verifications: Dict[str, dict] = {} 
pending_resets: Dict[str, dict] = {}

# --- UTILS ---
def is_active_license(expiry: Any) -> bool:
    try:
        return int(expiry or 0) > int(time.time() * 1000)
    except:
        return False

def format_msg(template: str, m: Message, btn_text: str = "") -> str:
    if not template: return ""
    res = template.replace("{{id}}", str(m.from_user.id))
    res = res.replace("{{name}}", m.from_user.full_name or "User")
    res = res.replace("{{username}}", f"@{m.from_user.username}" if m.from_user.username else "none")
    res = res.replace("{{button}}", btn_text)
    return res

async def log_event(bot_id: str, type: str, text: str):
    res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "config"})
    if not res: return
    config = res[0].get('config', {})
    logs = config.get('logs', [])
    new_log = {"id": str(uuid.uuid4())[:8], "timestamp": int(time.time() * 1000), "type": type, "text": text}
    logs = [new_log] + logs[:49]
    config['logs'] = logs
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"config": config})
    if bot_id in bot_configs: bot_configs[bot_id]['config']['logs'] = logs

async def update_stats(bot_id: str, direction: str):
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
        history.append({"date": today, "incoming": 0, "outgoing": 0, "totalUsers": len(config.get("connectedUsers", [])), "activeUsers": 0})
    
    if direction == "in": history[-1]["incoming"] += 1
    else: history[-1]["outgoing"] += 1
    
    stats["history"] = history[-30:]
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"stats": stats})

# --- BOT ENGINE CORE ---
async def bot_worker_task(bot_id: str, token: str):
    logger.info(f"🚀 Initializing bot: {bot_id}")
    await log_event(bot_id, "system", "Запуск процесса...")
    
    res = await db.query("bots", params={"id": f"eq.{bot_id}"})
    if not res: return
    bot_configs[bot_id] = res[0]
    
    session = AiohttpSession()
    bot = Bot(token=token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    active_bots[bot_id] = bot
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def cmd_start(m: Message):
        full_data = bot_configs.get(bot_id)
        if not full_data or not is_active_license(full_data['license_expires_at']):
            return await m.answer("❌ Лицензия этого бота истекла.")
        
        config = full_data.get('config', {})
        users = config.get("connectedUsers", [])
        user = next((u for u in users if str(u['id']) == str(m.from_user.id)), None)
        
        if not user:
            user = {"id": m.from_user.id, "first_name": m.from_user.first_name, "username": m.from_user.username, "joined_at": int(time.time()), "is_banned": False, "warns": 0, "is_active": True}
            users.append(user)
            config["connectedUsers"] = users
            await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"config": config})
            bot_configs[bot_id]['config'] = config
            await log_event(bot_id, "info", f"Новый юзер: {m.from_user.full_name}")

        if user.get("is_banned"): return

        rows = [[KeyboardButton(text=b["text"])] for b in config.get("buttons", []) if b.get("text")]
        kb = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True) if rows else ReplyKeyboardRemove()
        
        welcome = config.get("welcomeMessage", "Добро пожаловать!")
        await m.answer(format_msg(welcome, m), reply_markup=kb)
        asyncio.create_task(update_stats(bot_id, "out"))

    @dp.message()
    async def main_handler(m: Message):
        full_data = bot_configs.get(bot_id)
        if not full_data or not is_active_license(full_data['license_expires_at']): return
        
        config = full_data.get('config', {})
        admin_id = str(config.get("adminChatId", ""))

        # 1. Ответ админа
        if admin_id and str(m.chat.id) == admin_id:
            target_id = None
            if m.reply_to_message:
                reply_text = m.reply_to_message.text or m.reply_to_message.caption or ""
                match = re.search(r"ID: (\d+)", reply_text)
                if match: target_id = int(match.group(1))
            
            if target_id:
                try:
                    await bot.copy_message(target_id, m.chat.id, m.message_id)
                    asyncio.create_task(update_stats(bot_id, "out"))
                    await log_event(bot_id, "outgoing", f"Ответ юзеру {target_id}")
                except Exception as e:
                    await m.reply(f"❌ Ошибка: {e}")
            return

        # 2. Кнопки и триггеры
        if m.text:
            low = m.text.lower().strip()
            # Buttons
            for btn in config.get("buttons", []):
                if btn.get("text") and btn["text"].lower().strip() == low:
                    if btn.get("type") == "request" and admin_id:
                        tpl = btn.get("adminTemplate") or "📩 Обращение: {{button}}\nОт: {{name}} (ID: {{id}})"
                        await bot.send_message(admin_id, format_msg(tpl, m, btn["text"]))
                    
                    if btn.get("response"):
                        await m.answer(format_msg(btn["response"], m))
                        asyncio.create_task(update_stats(bot_id, "out"))
                    return
            # Triggers
            for tr in config.get("triggers", []):
                if tr.get("keyword") and tr["keyword"].lower().strip() in low:
                    await m.answer(format_msg(tr.get("response", ""), m))
                    asyncio.create_task(update_stats(bot_id, "out"))
                    return

        # 3. Пересылка админу
        if admin_id:
            try:
                info = f"👤 <b>{m.from_user.full_name}</b>\n🆔 ID: <code>{m.from_user.id}</code>"
                await bot.send_message(admin_id, info)
                await bot.copy_message(admin_id, m.chat.id, m.message_id)
                asyncio.create_task(update_stats(bot_id, "in"))
                await log_event(bot_id, "incoming", f"Сообщение от {m.from_user.id}")
            except Exception as e:
                logger.error(f"Bot {bot_id} forward error: {e}")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await log_event(bot_id, "system", "Бот готов к работе.")
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        await log_event(bot_id, "error", f"Crash: {e}")
    finally:
        await session.close()

# --- API ENDPOINTS ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Восстановление активных ботов
    rows = await db.query("bots", params={"status": "eq.RUNNING"})
    for b in rows:
        if is_active_license(b.get('license_expires_at')):
            active_tasks[b['id']] = asyncio.create_task(bot_worker_task(b['id'], b['token']))
    yield
    for t in active_tasks.values(): t.cancel()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")

@api.get("/ping")
async def ping(): return {"status": "online", "time": int(time.time())}

# AUTH
@api.post("/auth/login")
async def login_api(req: dict):
    email, password = req.get('email', '').strip().lower(), req.get('password', '')
    res = await db.query("users", params={"email": f"eq.{email}", "password": f"eq.{password}"})
    if not res: raise HTTPException(401, "Неверные данные")
    return res[0]

@api.post("/auth/verify-request")
async def verify_req(req: dict):
    email = req.get("email", "").lower().strip()
    code = str(random.randint(100000, 999999))
    if EmailService.send_verification_code(email, code):
        pending_verifications[email] = {"code": code, "time": time.time()}
        return {"status": "ok"}
    raise HTTPException(500, "Email Error")

@api.post("/auth/register")
async def register_api(req: dict):
    email, code = req.get("email", "").lower().strip(), req.get("code")
    if email not in pending_verifications or pending_verifications[email]["code"] != code:
        raise HTTPException(400, "Код неверен")
    
    payload = {
        "id": str(uuid.uuid4()), "email": email, "username": req.get("username"),
        "password": req.get("password"), "balance": 0, "botsCreated": 0,
        "licenseExpiresAt": int(time.time()*1000) + (3 * 24 * 3600 * 1000)
    }
    await db.query("users", method="POST", json_data=payload)
    del pending_verifications[email]
    return payload

@api.post("/auth/forgot-password")
async def forgot_api(req: dict):
    email = req.get("email", "").lower().strip()
    res = await db.query("users", params={"email": f"eq.{email}"})
    if not res: raise HTTPException(404, "User not found")
    code = str(random.randint(100000, 999999))
    if EmailService.send_password_reset(email, code):
        pending_resets[email] = {"code": code, "time": time.time()}
        return {"status": "ok"}
    raise HTTPException(500, "SMTP Error")

@api.post("/auth/reset-password")
async def reset_api(req: dict):
    email, code, pwd = req.get("email", "").lower().strip(), req.get("code"), req.get("newPassword")
    if email not in pending_resets or pending_resets[email]["code"] != code:
        raise HTTPException(400, "Wrong code")
    await db.query("users", method="PATCH", params={"email": f"eq.{email}"}, json_data={"password": pwd})
    del pending_resets[email]
    return {"status": "ok"}

# BOTS
@api.get("/bots/{user_id}")
async def get_user_bots(user_id: str):
    rows = await db.query("bots", params={"owner_id": f"eq.{user_id}"})
    for r in rows: r['status'] = "RUNNING" if r['id'] in active_tasks else "IDLE"
    return rows

@api.post("/bots/save")
async def save_bot_api(data: dict):
    bid = data['id']
    payload = {
        "id": bid, "owner_id": data['ownerId'], "name": data['name'], "token": data['token'],
        "license_expires_at": int(data.get('licenseExpiresAt', 0)),
        "config": {
            "welcomeMessage": data.get('welcomeMessage', ""),
            "adminChatId": str(data.get('adminChatId', "")),
            "buttons": data.get('buttons', []), "triggers": data.get('triggers', []),
            "settings": data.get('settings', {}), "connectedUsers": data.get('connectedUsers', []),
            "logs": data.get('logs', [])
        }
    }
    await db.query("bots", method="POST", json_data=payload, params={"on_conflict": "id"})
    if bid in active_tasks:
        res = await db.query("bots", params={"id": f"eq.{bid}"})
        if res: bot_configs[bid] = res[0]
    return {"status": "ok"}

@api.post("/bots/start/{bot_id}")
async def start_bot_api(bot_id: str):
    res = await db.query("bots", params={"id": f"eq.{bot_id}"})
    if not res or not is_active_license(res[0].get('license_expires_at')):
        raise HTTPException(403, "No license")
    
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"status": "RUNNING"})
    if bot_id in active_tasks: active_tasks[bot_id].cancel()
    active_tasks[bot_id] = asyncio.create_task(bot_worker_task(bot_id, res[0]['token']))
    return {"status": "ok"}

@api.post("/bots/stop/{bot_id}")
async def stop_bot_api(bot_id: str):
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"status": "IDLE"})
    if bot_id in active_tasks: 
        active_tasks[bot_id].cancel()
        del active_tasks[bot_id]
    return {"status": "ok"}

@api.delete("/bots/delete/{bot_id}")
async def del_bot_api(bot_id: str):
    if bot_id in active_tasks: active_tasks[bot_id].cancel()
    await db.query("bots", method="DELETE", params={"id": f"eq.{bot_id}"})
    return {"status": "ok"}

@api.post("/broadcast")
async def broadcast_api(req: dict):
    bot_ids, msg = req.get("botIds", []), req.get("message", "")
    rep = {"success": 0, "failed": 0}
    for bid in bot_ids:
        bot = active_bots.get(bid)
        if not bot: continue
        conf = bot_configs.get(bid, {}).get('config', {})
        users = [u['id'] for u in conf.get('connectedUsers', []) if not u.get('is_banned')]
        for uid in users:
            try:
                await bot.send_message(uid, msg)
                rep["success"] += 1
            except: rep["failed"] += 1
            await asyncio.sleep(0.05)
    return rep

@api.post("/license/activate")
async def activate_lic_api(req: dict):
    bid, key = req.get("botId"), req.get("key", "")
    m = re.match(r"BOT-(\d+)-(\w+)", key)
    if not m: raise HTTPException(400, "Bad key")
    res = await db.query("bots", params={"id": f"eq.{bid}"})
    if not res: raise HTTPException(404)
    exp = max(int(time.time()*1000), int(res[0].get('license_expires_at', 0))) + (int(m.group(1)) * 30 * 24 * 3600 * 1000)
    await db.query("bots", method="PATCH", params={"id": f"eq.{bid}"}, json_data={"license_expires_at": exp})
    return {"status": "ok", "newExpiry": exp}

@api.post("/admin/generate-key")
async def gen_key_api(req: dict, x_token: str = Header(None, alias="x-admin-token")):
    if x_token != ADMIN_SECRET: raise HTTPException(403)
    key = f"BOT-{req.get('months', 1)}-{secrets.token_hex(4).upper()}"
    return {"key": key}

app.include_router(api)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
