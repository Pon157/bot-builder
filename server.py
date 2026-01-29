
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

# Импортируем сервис почты (если он есть в проекте)
try:
    from email_service import EmailService
except ImportError:
    class EmailService:
        @staticmethod
        def send_verification_code(email, code): print(f"CODE FOR {email}: {code}"); return True
        @staticmethod
        def send_password_reset(email, code): print(f"RESET FOR {email}: {code}"); return True

# --- 1. НАСТРОЙКИ И ЛОГИРОВАНИЕ ---
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
    logger.critical("🛑 ОШИБКА: SUPABASE_URL или SUPABASE_KEY не найдены в .env!")
    sys.exit(1)

# --- 2. ГЛОБАЛЬНЫЕ СОСТОЯНИЯ ---
active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}
verification_store: Dict[str, dict] = {} # {email: {code, expires, type}}

# --- 3. РАБОТА С БД (SUPABASE) ---
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
                    logger.error(f"DB Error [{method} {table}]: {resp.text}")
                    return []
                return resp.json() if resp.status_code != 204 else []
            except Exception as e:
                logger.error(f"Database connection error: {e}")
                return []

db = SupabaseDB(SUPABASE_URL, SUPABASE_KEY)

# --- 4. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
async def log_event(bot_id: str, ltype: str, text: str):
    res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "config"})
    if not res: return
    config = res[0].get('config', {})
    logs = config.get("logs", [])
    logs.insert(0, {
        "id": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "type": ltype,
        "text": str(text)[:500]
    })
    config["logs"] = logs[:100]
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"config": config})

def apply_template(text: str, m: Message, btn: str = "") -> str:
    if not text: return ""
    replacements = {
        "{{id}}": str(m.from_user.id),
        "{{name}}": m.from_user.full_name or "Пользователь",
        "{{username}}": f"@{m.from_user.username}" if m.from_user.username else "нет",
        "{{button}}": btn
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text

async def update_stats(bot_id: str, direction: str, config: dict):
    res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "stats"})
    if not res: return
    stats = res[0].get('stats', {})
    if not stats: stats = {"totalMessages": 0, "incomingToday": 0, "outgoingToday": 0, "history": []}
    
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

def is_active_license(expiry_ms: int) -> bool:
    """Проверяет, активна ли лицензия"""
    return int(expiry_ms or 0) > int(time.time() * 1000)

# --- 5. ДВИЖОК БОТА (CORE ENGINE) ---
async def run_bot_instance(bot_id: str, token: str):
    logger.info(f"⚙️ Запуск инстанса бота: {bot_id}")
    session = AiohttpSession()
    bot = Bot(token=token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    active_bots[bot_id] = bot
    dp = Dispatcher()
    router = Router()

    # Фильтр для админа
    class IsAdmin(BaseFilter):
        async def __call__(self, m: Message) -> bool:
            res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "config"})
            if not res: return False
            return str(m.chat.id) == str(res[0]['config'].get('adminChatId', ''))

    @router.message(CommandStart())
    async def handle_start(m: Message):
        res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "config,license_expires_at"})
        if not res or not is_active_license(res[0]['license_expires_at']): return
        config = res[0]['config']
        
        # Регистрация
        users = config.get("connectedUsers", [])
        if not any(u['id'] == m.from_user.id for u in users):
            users.append({"id": m.from_user.id, "first_name": m.from_user.first_name, "username": m.from_user.username, "joined_at": int(time.time()), "is_banned": False, "warns": 0, "is_active": True})
            config["connectedUsers"] = users
            await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"config": config})
            await log_event(bot_id, "info", f"User {m.from_user.id} registered")

        # Кнопки
        btns = config.get("buttons", [])
        rows = [[KeyboardButton(text=b["text"])] for b in btns if b.get("text")]
        kb = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True) if rows else ReplyKeyboardRemove()
        
        welcome = apply_template(config.get("welcomeMessage", "Привет!"), m)
        await m.answer(welcome, reply_markup=kb)
        await update_stats(bot_id, "out", config)

    @router.message(Command("ban", "unban", "warn"), IsAdmin())
    async def handle_moderation(m: Message):
        if not m.reply_to_message: return await m.reply("Ответьте на сообщение пользователя для модерации.")
        content = m.reply_to_message.text or m.reply_to_message.caption or ""
        match = re.search(r"ID: (\d+)", content)
        if not match: return await m.reply("ID пользователя не найден в истории сообщения.")
        
        target_id = int(match.group(1))
        res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "config"})
        config = res[0]['config']
        users = config.get("connectedUsers", [])
        user = next((u for u in users if u['id'] == target_id), None)
        if not user: return await m.reply("Пользователь не найден в базе.")

        cmd = m.text.split()[0][1:]
        if cmd == "ban": user["is_banned"] = True
        elif cmd == "unban": user["is_banned"] = False
        elif cmd == "warn": user["warns"] = user.get("warns", 0) + 1

        await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"config": config})
        await m.reply(f"Выполнено: {cmd} для {target_id}")

    @router.message()
    async def main_router(m: Message):
        res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "config,license_expires_at"})
        if not res or not is_active_license(res[0]['license_expires_at']): return
        config = res[0]['config']
        admin_id = str(config.get("adminChatId", ""))

        # 1. Авто-регистрация
        users = config.get("connectedUsers", [])
        user = next((u for u in users if u['id'] == m.from_user.id), None)
        if not user:
            user = {"id": m.from_user.id, "first_name": m.from_user.first_name, "username": m.from_user.username, "joined_at": int(time.time()), "is_banned": False, "warns": 0, "is_active": True}
            users.append(user)
            config["connectedUsers"] = users
            await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"config": config})

        # 2. Ответ админа
        if admin_id and str(m.chat.id) == admin_id:
            if m.reply_to_message:
                ref_text = m.reply_to_message.text or m.reply_to_message.caption or ""
                match = re.search(r"ID: (\d+)", ref_text)
                if match:
                    target_id = int(match.group(1))
                    try:
                        await bot.copy_message(target_id, m.chat.id, m.message_id)
                        await update_stats(bot_id, "out", config)
                    except Exception as e: await m.reply(f"Ошибка: {e}")
            return

        if user.get("is_banned"): return

        # 3. Кнопки и триггеры
        if m.text:
            msg_text = m.text.lower().strip()
            for btn in config.get("buttons", []):
                if btn.get("text") and btn["text"].lower().strip() == msg_text:
                    if btn.get("type") == "request" and admin_id:
                        tpl = btn.get("adminTemplate") or "📩 Заявка: {{button}}\nОт: {{name}} (ID: <code>{{id}}</code>)"
                        await bot.send_message(admin_id, apply_template(tpl, m, btn["text"]))
                    if btn.get("response"):
                        await m.answer(apply_template(btn.get("response"), m))
                        await update_stats(bot_id, "out", config)
                    return
            for tr in config.get("triggers", []):
                if tr.get("keyword") and tr["keyword"].lower() in msg_text:
                    await m.answer(apply_template(tr.get("response", ""), m))
                    await update_stats(bot_id, "out", config)
                    return

        # 4. Пересылка админу (Livegram)
        if admin_id:
            try:
                info = f"👤 <b>{m.from_user.full_name}</b>"
                if m.from_user.username: info += f" (@{m.from_user.username})"
                info += f"\n🆔 ID: <code>{m.from_user.id}</code>"
                await bot.send_message(admin_id, info)
                await bot.copy_message(admin_id, m.chat.id, m.message_id)
                await update_stats(bot_id, "in", config)
                await log_event(bot_id, "incoming", f"Message from {m.from_user.id}")
            except Exception as e: logger.error(f"Forward error: {e}")

    dp.include_router(router)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, skip_updates=True)
    finally: await session.close()

# --- 6. FASTAPI ROUTES ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Восстановление работы ботов
    rows = await db.query("bots", params={"status": "eq.RUNNING", "select": "id,token,license_expires_at"})
    for b in rows:
        if is_active_license(b['license_expires_at']):
            active_tasks[b['id']] = asyncio.create_task(run_bot_instance(b['id'], b['token']))
    yield
    for t in active_tasks.values(): t.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/ping")
async def ping(): return {"status": "online", "time": int(time.time()), "bots": len(active_tasks)}

@app.post("/api/auth/login")
async def login(req: dict):
    res = await db.query("users", params={"email": f"eq.{req['email']}", "password": f"eq.{req['password']}"})
    if not res: raise HTTPException(401, "Invalid data")
    return res[0]

@app.post("/api/auth/request-verification")
async def req_verify(req: dict):
    email = req.get("email")
    code = "".join(secrets.choice("0123456789") for _ in range(6))
    verification_store[email] = {"code": code, "expires": time.time() + 600}
    EmailService.send_verification_code(email, code)
    return {"status": "ok"}

@app.post("/api/auth/verify-and-register")
async def verify_reg(req: dict):
    email, code = req.get("email"), req.get("code")
    store = verification_store.get(email)
    if not store or store["code"] != code or store["expires"] < time.time(): raise HTTPException(400, "Bad code")
    payload = {
        "id": "u_" + secrets.token_hex(4), "username": req.get("username", "User"),
        "email": email, "password": req.get("password"), "balance": 0,
        "license_expires_at": int(time.time()*1000) + (3*24*3600*1000), "created_at": int(time.time())
    }
    res = await db.query("users", method="POST", json_data=payload)
    return res[0]

@app.get("/api/bots/{user_id}")
async def get_user_bots(user_id: str):
    rows = await db.query("bots", params={"owner_id": f"eq.{user_id}"})
    for r in rows: r['status'] = "RUNNING" if r['id'] in active_tasks else "IDLE"
    return rows

@app.post("/api/bots/save")
async def save_bot(data: dict):
    bid = data['id']
    payload = {
        "id": bid, "owner_id": data['ownerId'], "name": data['name'], "token": data['token'],
        "license_expires_at": data.get('licenseExpiresAt', 0),
        "config": {
            "welcomeMessage": data.get('welcomeMessage', ""), "adminChatId": data.get('adminChatId', ""),
            "buttons": data.get('buttons', []), "triggers": data.get('triggers', []),
            "settings": data.get('settings', {}), "connectedUsers": data.get('connectedUsers', []), "logs": data.get('logs', [])
        }
    }
    await db.query("bots", method="POST", json_data=payload, params={"on_conflict": "id"})
    return {"status": "ok"}

@app.post("/api/bots/start/{bot_id}")
async def start_bot(bot_id: str):
    res = await db.query("bots", params={"id": f"eq.{bot_id}"})
    if not res: raise HTTPException(404)
    if not is_active_license(res[0]['license_expires_at']): raise HTTPException(403, "Expired")
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"status": "RUNNING"})
    if bot_id not in active_tasks:
        active_tasks[bot_id] = asyncio.create_task(run_bot_instance(bot_id, res[0]['token']))
    return {"status": "ok"}

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"status": "IDLE"})
    if bot_id in active_tasks: active_tasks[bot_id].cancel(); del active_tasks[bot_id]
    if bot_id in active_bots: del active_bots[bot_id]
    return {"status": "ok"}

@app.post("/api/broadcast")
async def broadcast(req: dict):
    bot_ids, msg = req.get("botIds", []), req.get("message", "")
    res_data = {"success": 0, "failed": 0}
    for bid in bot_ids:
        bot = active_bots.get(bid)
        if not bot: continue
        conf_res = await db.query("bots", params={"id": f"eq.{bid}", "select": "config"})
        users = [u['id'] for u in conf_res[0]['config'].get('connectedUsers', []) if not u.get('is_banned')]
        for uid in users:
            try: await bot.send_message(uid, msg); res_data["success"] += 1
            except: res_data["failed"] += 1
    return res_data

@app.post("/api/license/activate")
async def activate_lic(req: dict):
    bot_id, key = req.get("botId"), req.get("key")
    match = re.match(r"BOT-1-(\d+)-(\w+)", key)
    if not match: raise HTTPException(400, "Bad key")
    months = int(match.group(1))
    res = await db.query("bots", params={"id": f"eq.{bot_id}"})
    new_expiry = max(int(time.time()*1000), res[0]['license_expires_at']) + (months * 30 * 24 * 3600 * 1000)
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"license_expires_at": new_expiry})
    return {"status": "ok", "newExpiry": new_expiry}

@app.post("/api/admin/generate-key")
async def gen_key(req: dict, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET: raise HTTPException(403)
    return {"key": f"BOT-1-{req.get('months', 1)}-{secrets.token_hex(4).upper()}"}

@app.delete("/api/bots/delete/{bot_id}")
async def delete_bot(bot_id: str):
    if bot_id in active_tasks: active_tasks[bot_id].cancel(); del active_tasks[bot_id]
    await db.query("bots", method="DELETE", params={"id": f"eq.{bot_id}"})
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
