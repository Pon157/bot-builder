
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

# --- 1. CONFIGURATION & LOGGING ---
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
    logger.critical("🛑 CRITICAL ERROR: Database credentials (SUPABASE) missing!")
    sys.exit(1)

# --- 2. GLOBAL STATE ---
active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}
verification_store: Dict[str, dict] = {} # {email: {code, expires}}

# --- 3. DATABASE WRAPPER (SUPABASE) ---
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

# --- 4. UTILS & HELPERS ---
async def log_event(bot_id: str, ltype: str, text: str):
    """Добавляет запись в лог бота в БД"""
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
    config["logs"] = logs[:100] # Держим последние 100 записей
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"config": config})

def apply_template(text: str, m: Message, btn: str = "") -> str:
    """Заменяет переменные в шаблонах сообщений"""
    if not text: return ""
    replacements = {
        "{{id}}": str(m.from_user.id),
        "{{name}}": m.from_user.full_name or "Unknown",
        "{{username}}": f"@{m.from_user.username}" if m.from_user.username else "none",
        "{{button}}": btn
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text

async def update_stats(bot_id: str, direction: str, config: dict):
    """Обновляет статистику бота в реальном времени"""
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
    stats["history"] = history[-30:] # Храним месяц
    
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"stats": stats})

def is_license_valid(expiry_ms: int) -> bool:
    return int(expiry_ms or 0) > int(time.time() * 1000)

# --- 5. CORE BOT WORKER (THE ENGINE) ---
async def run_bot_instance(bot_id: str, token: str):
    logger.info(f"⚙️ Starting Bot Instance: {bot_id}")
    session = AiohttpSession()
    bot = Bot(token=token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    active_bots[bot_id] = bot
    dp = Dispatcher()
    router = Router()

    # Фильтр для проверки администратора
    class IsAdmin(BaseFilter):
        async def __call__(self, m: Message) -> bool:
            res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "config"})
            if not res: return False
            admin_id = str(res[0]['config'].get('adminChatId', ''))
            return str(m.chat.id) == admin_id

    @router.message(CommandStart())
    async def handle_start(m: Message):
        res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "config,license_expires_at"})
        if not res or not is_license_valid(res[0]['license_expires_at']): return
        config = res[0]['config']
        
        # Регистрация или обновление пользователя
        users = config.get("connectedUsers", [])
        user_idx = next((i for i, u in enumerate(users) if u['id'] == m.from_user.id), -1)
        if user_idx == -1:
            users.append({
                "id": m.from_user.id, "first_name": m.from_user.first_name, 
                "username": m.from_user.username, "joined_at": int(time.time()), 
                "is_banned": False, "warns": 0, "is_active": True
            })
            config["connectedUsers"] = users
            await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"config": config})
            await log_event(bot_id, "info", f"User {m.from_user.id} registered")

        # Клавиатура
        btns = config.get("buttons", [])
        rows = [[KeyboardButton(text=b["text"])] for b in btns if b.get("text")]
        kb = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True) if rows else ReplyKeyboardRemove()
        
        welcome = apply_template(config.get("welcomeMessage", "Hello!"), m)
        await m.answer(welcome, reply_markup=kb)
        await update_stats(bot_id, "out", config)

    @router.message(Command("ban", "unban", "warn"), IsAdmin())
    async def handle_moderation(m: Message):
        if not m.reply_to_message: return await m.reply("Reply to user message to moderate.")
        
        content = m.reply_to_message.text or m.reply_to_message.caption or ""
        match = re.search(r"ID: (\d+)", content)
        if not match: return await m.reply("Could not find User ID in message history.")
        
        target_id = int(match.group(1))
        res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "config"})
        config = res[0]['config']
        users = config.get("connectedUsers", [])
        user = next((u for u in users if u['id'] == target_id), None)
        
        if not user: return await m.reply("User not found in database.")

        cmd = m.text.split()[0][1:]
        if cmd == "ban": user["is_banned"] = True
        elif cmd == "unban": user["is_banned"] = False
        elif cmd == "warn": user["warns"] = user.get("warns", 0) + 1

        await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"config": config})
        await m.reply(f"Done: {cmd} for {target_id}")

    @router.message()
    async def message_router(m: Message):
        res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "config,license_expires_at"})
        if not res or not is_license_valid(res[0]['license_expires_at']): return
        config = res[0]['config']
        admin_id = str(config.get("adminChatId", ""))

        # 1. АВТО-РЕГИСТРАЦИЯ (для новых пользователей без /start)
        users = config.get("connectedUsers", [])
        user = next((u for u in users if u['id'] == m.from_user.id), None)
        if not user:
            user = {"id": m.from_user.id, "first_name": m.from_user.first_name, "username": m.from_user.username, "joined_at": int(time.time()), "is_banned": False, "warns": 0, "is_active": True}
            users.append(user)
            config["connectedUsers"] = users
            await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"config": config})

        # 2. ЕСЛИ ПИШЕТ АДМИН (ОТВЕТ ЮЗЕРУ)
        if admin_id and str(m.chat.id) == admin_id:
            if m.reply_to_message:
                ref_text = m.reply_to_message.text or m.reply_to_message.caption or ""
                match = re.search(r"ID: (\d+)", ref_text)
                if match:
                    target_id = int(match.group(1))
                    try:
                        await bot.copy_message(target_id, m.chat.id, m.message_id)
                        await update_stats(bot_id, "out", config)
                        await log_event(bot_id, "outgoing", f"Admin replied to {target_id}")
                    except Exception as e:
                        await m.reply(f"Send error: {e}")
                else:
                    await m.reply("Reply to a message containing 'ID: ...' to send answer.")
            return

        # Если в бане — игнор
        if user.get("is_banned"): return

        # 3. КНОПКИ (ТОЧНОЕ СОВПАДЕНИЕ)
        if m.text:
            msg_text = m.text.lower().strip()
            for btn in config.get("buttons", []):
                if btn.get("text") and btn["text"].lower().strip() == msg_text:
                    # Обработка типа "Обращение"
                    if btn.get("type") == "request" and admin_id:
                        tpl = btn.get("adminTemplate") or "📩 New Request: {{button}}\nFrom: {{name}} (ID: <code>{{id}}</code>)"
                        await bot.send_message(admin_id, apply_template(tpl, m, btn["text"]))
                    
                    # Ответ пользователю
                    if btn.get("response"):
                        await m.answer(apply_template(btn.get("response"), m))
                        await update_stats(bot_id, "out", config)
                    return

            # 4. ТРИГГЕРЫ (ВХОЖДЕНИЕ)
            for tr in config.get("triggers", []):
                if tr.get("keyword") and tr["keyword"].lower() in msg_text:
                    await m.answer(apply_template(tr.get("response", ""), m))
                    await update_stats(bot_id, "out", config)
                    return

        # 5. ПЕРЕСЫЛКА АДМИНУ (LIVEGRAM MODE)
        if admin_id:
            try:
                info = f"👤 <b>{m.from_user.full_name}</b>"
                if m.from_user.username: info += f" (@{m.from_user.username})"
                info += f"\n🆔 ID: <code>{m.from_user.id}</code>"
                
                # Отправляем инфо-блок
                await bot.send_message(admin_id, info)
                # Копируем сообщение
                await bot.copy_message(admin_id, m.chat.id, m.message_id)
                
                await update_stats(bot_id, "in", config)
                await log_event(bot_id, "incoming", f"Message from {m.from_user.id} forwarded to admin")
            except Exception as e:
                logger.error(f"Forward error for {bot_id}: {e}")

    dp.include_router(router)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logger.error(f"Polling failure for {bot_id}: {e}")
    finally:
        await session.close()

# --- 6. FASTAPI APPLICATION SETUP ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Восстановление работы запущенных ботов
    rows = await db.query("bots", params={"status": "eq.RUNNING", "select": "id,token,license_expires_at"})
    for b in rows:
        if is_active_license(b['license_expires_at']):
            active_tasks[b['id']] = asyncio.create_task(run_bot_instance(b['id'], b['token']))
    yield
    # Остановка при выключении сервера
    for t in active_tasks.values(): t.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- API ENDPOINTS ---

@app.get("/api/ping")
async def ping(): 
    return {"status": "online", "time": int(time.time()), "active_bots": len(active_tasks)}

@app.post("/api/auth/login")
async def login_route(req: dict):
    res = await db.query("users", params={"email": f"eq.{req['email']}", "password": f"eq.{req['password']}"})
    if not res: raise HTTPException(401, "Invalid credentials")
    return res[0]

@app.get("/api/bots/{user_id}")
async def get_user_bots(user_id: str):
    rows = await db.query("bots", params={"owner_id": f"eq.{user_id}"})
    for r in rows:
        r['status'] = "RUNNING" if r['id'] in active_tasks else "IDLE"
    return rows

@app.post("/api/bots/save")
async def save_bot_route(data: dict):
    bid = data['id']
    # Валидация структуры конфига
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
    return {"status": "ok"}

@app.post("/api/bots/start/{bot_id}")
async def start_bot_route(bot_id: str):
    res = await db.query("bots", params={"id": f"eq.{bot_id}"})
    if not res: raise HTTPException(404, "Bot not found")
    bot_data = res[0]
    
    if not is_license_valid(bot_data['license_expires_at']):
        raise HTTPException(403, "License expired")
    
    # Пытаемся проверить токен перед запуском
    try:
        async with Bot(token=bot_data['token']).context() as test_bot:
            await test_bot.get_me()
    except Exception as e:
        raise HTTPException(400, f"Invalid token: {e}")

    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"status": "RUNNING"})
    if bot_id not in active_tasks:
        active_tasks[bot_id] = asyncio.create_task(run_bot_instance(bot_id, bot_data['token']))
    
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
    if not msg_text: raise HTTPException(400, "Message empty")
    
    results = {"success": 0, "failed": 0}
    for bid in bot_ids:
        bot = active_bots.get(bid)
        if not bot: continue
        
        res = await db.query("bots", params={"id": f"eq.{bid}", "select": "config"})
        if not res: continue
        
        users = [u['id'] for u in res[0]['config'].get('connectedUsers', []) if not u.get('is_banned')]
        for uid in users:
            try:
                await bot.send_message(uid, msg_text)
                results["success"] += 1
            except:
                results["failed"] += 1
            await asyncio.sleep(0.05) # Rate limiting
            
    return results

@app.post("/api/license/activate")
async def activate_license_route(req: dict):
    bot_id, key = req.get("botId"), req.get("key")
    if not key or not bot_id: raise HTTPException(400, "Missing data")
    
    # Формат ключа: BOT-1-{months}-{hex}
    match = re.match(r"BOT-1-(\d+)-(\w+)", key)
    if not match: raise HTTPException(400, "Invalid key format")
    
    months = int(match.group(1))
    res = await db.query("bots", params={"id": f"eq.{bot_id}"})
    if not res: raise HTTPException(404, "Bot not found")
    
    current_expiry = max(int(time.time() * 1000), res[0]['license_expires_at'])
    new_expiry = current_expiry + (months * 30 * 24 * 3600 * 1000)
    
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"license_expires_at": new_expiry})
    return {"status": "ok", "newExpiry": new_expiry}

@app.post("/api/admin/generate-key")
async def admin_gen_key(req: dict, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET: raise HTTPException(403, "Access denied")
    months = req.get("months", 1)
    # Генерация уникального ключа
    new_key = f"BOT-1-{months}-{secrets.token_hex(4).upper()}"
    return {"key": new_key}

@app.delete("/api/bots/delete/{bot_id}")
async def delete_bot_route(bot_id: str):
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel()
        del active_tasks[bot_id]
    await db.query("bots", method="DELETE", params={"id": f"eq.{bot_id}"})
    return {"status": "ok"}

# --- 7. START SERVER ---
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"✨ Starting Engine on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
