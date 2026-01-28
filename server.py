
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
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
import uvicorn

# --- Инициализация логирования ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(name)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotEngineCore")

# --- Загрузка переменных окружения ---
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

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.critical("🛑 Критическая ошибка: SUPABASE_URL или SUPABASE_KEY не найдены в .env!")
    sys.exit(1)

# --- Глобальные состояния ---
active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}
verification_store: Dict[str, dict] = {} 

# --- Работа с БД (Supabase) ---
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
            target_url = f"{self.url}/rest/v1/{table}"
            try:
                resp = await client.request(method, target_url, params=params, json=json_data, headers=self.headers)
                if resp.status_code >= 400:
                    logger.error(f"Supabase Error ({table} {method}): {resp.text}")
                return resp.json() if resp.status_code != 204 else []
            except Exception as e:
                logger.error(f"Network Error in DB query: {e}")
                return []

db = SupabaseDB(SUPABASE_URL, SUPABASE_KEY)

# --- Вспомогательные функции ---
async def add_bot_log(bot_id: str, log_type: str, text: str):
    res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "config"})
    if not res: return
    config = res[0].get('config', {})
    logs = config.get("logs", [])
    new_log = {
        "id": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "type": log_type,
        "text": str(text)[:500]
    }
    logs.insert(0, new_log)
    config["logs"] = logs[:50]
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"config": config})

def format_msg(template: str, m: Message, btn_text: str = "") -> str:
    if not template: return ""
    res = template.replace("{{id}}", str(m.from_user.id))
    res = res.replace("{{name}}", m.from_user.full_name or "Пользователь")
    res = res.replace("{{username}}", f"@{m.from_user.username}" if m.from_user.username else "нет")
    res = res.replace("{{button}}", btn_text)
    return res

async def update_bot_stats(bot_id: str, direction: str, config: dict):
    res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "stats"})
    if not res: return
    stats = res[0].get('stats', {})
    if not stats: stats = {"totalMessages": 0, "incomingToday": 0, "outgoingToday": 0, "history": []}
    
    stats["totalMessages"] = stats.get("totalMessages", 0) + 1
    if direction == "incoming": stats["incomingToday"] = stats.get("incomingToday", 0) + 1
    else: stats["outgoingToday"] = stats.get("outgoingToday", 0) + 1
    
    today = datetime.now().strftime("%d.%m")
    history = stats.get("history", [])
    if not history or history[-1]["date"] != today:
        history.append({
            "date": today, "incoming": 0, "outgoing": 0, 
            "totalUsers": len(config.get("connectedUsers", [])), "activeUsers": 0
        })
    
    if direction == "incoming": history[-1]["incoming"] += 1
    else: history[-1]["outgoing"] += 1
    history[-1]["totalUsers"] = len(config.get("connectedUsers", []))
    stats["history"] = history[-10:]
    
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"stats": stats})

def is_license_active(expiry: int) -> bool:
    return int(expiry or 0) > int(time.time() * 1000)

# --- BOT WORKER (AIOGRAM 3) ---
async def bot_worker_task(bot_id: str, token: str):
    logger.info(f"🤖 Запуск бота: {bot_id}")
    session = AiohttpSession()
    bot = Bot(token=token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    active_bots[bot_id] = bot
    dp = Dispatcher()
    router = Router()

    @router.message(CommandStart())
    async def cmd_start(m: Message):
        res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "config,license_expires_at"})
        if not res or not is_license_active(res[0]['license_expires_at']): return
        config = res[0]['config']
        
        # Регистрация
        users = config.get("connectedUsers", [])
        if not any(u['id'] == m.from_user.id for u in users):
            users.append({"id": m.from_user.id, "first_name": m.from_user.first_name, "username": m.from_user.username, "joined_at": int(time.time()), "is_banned": False, "warns": 0, "is_active": True})
            config["connectedUsers"] = users
            await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"config": config})
            await add_bot_log(bot_id, "info", f"Новый пользователь: {m.from_user.id}")

        btns = config.get("buttons", [])
        rows = [[KeyboardButton(text=b["text"])] for b in btns if b.get("text")]
        kb = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True) if rows else ReplyKeyboardRemove()
        
        welcome = config.get("welcomeMessage", "Привет!")
        await m.answer(format_msg(welcome, m), reply_markup=kb)
        await update_bot_stats(bot_id, "outgoing", config)

    @router.message(Command("ban", "unban", "warn"))
    async def cmd_moderation(m: Message):
        res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "config"})
        if not res: return
        config = res[0]['config']
        if str(m.chat.id) != str(config.get("adminChatId")): return

        target_id = None
        if m.reply_to_message:
            match = re.search(r"ID: (\d+)", m.reply_to_message.text or m.reply_to_message.caption or "")
            if match: target_id = int(match.group(1))

        if not target_id: return await m.reply("❌ Не удалось определить ID пользователя из реплая.")

        users = config.get("connectedUsers", [])
        user = next((u for u in users if u['id'] == target_id), None)
        if not user: return await m.reply("❌ Пользователь не найден в базе.")

        cmd = m.text.split()[0][1:]
        if cmd == "ban": user["is_banned"] = True
        elif cmd == "unban": user["is_banned"] = False
        elif cmd == "warn": user["warns"] = user.get("warns", 0) + 1

        await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"config": config})
        await m.reply(f"✅ Действие {cmd} выполнено для {target_id}")

    @router.message()
    async def main_handler(m: Message):
        res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "config,license_expires_at"})
        if not res or not is_license_active(res[0]['license_expires_at']): return
        config = res[0]['config']
        admin_id = str(config.get("adminChatId", ""))

        # 1. АВТО-РЕГИСТРАЦИЯ (Гарантирует работу Livegram)
        users = config.get("connectedUsers", [])
        user = next((u for u in users if u['id'] == m.from_user.id), None)
        if not user:
            user = {"id": m.from_user.id, "first_name": m.from_user.first_name, "username": m.from_user.username, "joined_at": int(time.time()), "is_banned": False, "warns": 0, "is_active": True}
            users.append(user)
            config["connectedUsers"] = users
            await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"config": config})

        # 2. ОТВЕТ АДМИНИСТРАТОРА
        if admin_id and str(m.chat.id) == admin_id:
            if m.reply_to_message:
                content = m.reply_to_message.text or m.reply_to_message.caption or ""
                match = re.search(r"ID: (\d+)", content)
                if match:
                    target_id = int(match.group(1))
                    try:
                        await bot.copy_message(target_id, m.chat.id, m.message_id)
                        await update_bot_stats(bot_id, "outgoing", config)
                        await add_bot_log(bot_id, "outgoing", f"Ответ админа юзеру {target_id}")
                    except Exception as e:
                        await m.reply(f"❌ Ошибка отправки: {e}")
            return

        if user.get("is_banned"): return

        # 3. КНОПКИ И ТРИГГЕРЫ
        if m.text:
            text_low = m.text.lower()
            # Кнопки
            for btn in config.get("buttons", []):
                if btn.get("text") and btn["text"].lower() == text_low:
                    if btn.get("type") == "request" and admin_id:
                        tpl = btn.get("adminTemplate") or "📩 <b>Обращение по кнопке:</b> {{button}}\nОт: {{name}} (ID: <code>{{id}}</code>)"
                        await bot.send_message(admin_id, format_msg(tpl, m, btn["text"]))
                    if btn.get("response"):
                        await m.answer(btn.get("response"))
                        await update_bot_stats(bot_id, "outgoing", config)
                    return
            # Триггеры
            for tr in config.get("triggers", []):
                if tr.get("keyword") and tr["keyword"].lower() in text_low:
                    await m.answer(tr.get("response", ""))
                    await update_bot_stats(bot_id, "outgoing", config)
                    return

        # 4. ПЕРЕСЫЛКА АДМИНУ (LIVEGRAM)
        if admin_id:
            try:
                header = f"👤 <b>{m.from_user.full_name}</b>"
                if m.from_user.username: header += f" (@{m.from_user.username})"
                header += f"\n🆔 ID: <code>{m.from_user.id}</code>"
                
                await bot.send_message(admin_id, header)
                await bot.copy_message(admin_id, m.chat.id, m.message_id)
                await update_bot_stats(bot_id, "incoming", config)
                await add_bot_log(bot_id, "incoming", f"Переслано админу от {m.from_user.id}")
            except Exception as e:
                logger.error(f"Forward error: {e}")

    dp.include_router(router)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await session.close()

# --- FASTAPI APP ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # При старте сервера запускаем ботов, которые были включены
    rows = await db.query("bots", params={"status": "eq.RUNNING", "select": "id,token,license_expires_at"})
    for b in rows:
        if is_license_active(b['license_expires_at']):
            active_tasks[b['id']] = asyncio.create_task(bot_worker_task(b['id'], b['token']))
    yield
    for t in active_tasks.values(): t.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- AUTH ROUTES ---
@app.post("/api/auth/login")
async def login(req: dict):
    res = await db.query("users", params={"email": f"eq.{req['email']}", "password": f"eq.{req['password']}"})
    if not res: raise HTTPException(401, "Неверные данные")
    return res[0]

@app.post("/api/auth/request-verification")
async def request_ver(req: dict):
    email = req.get("email")
    code = "".join(secrets.choice("0123456789") for _ in range(6))
    verification_store[email] = {"code": code, "expires": time.time() + 600}
    # Здесь должен быть вызов EmailService.send_verification_code(email, code)
    logger.info(f"📧 Код для {email}: {code}")
    return {"status": "ok"}

@app.post("/api/auth/verify-and-register")
async def verify_reg(req: dict):
    email, code = req.get("email"), req.get("code")
    store = verification_store.get(email)
    if not store or store["code"] != code or store["expires"] < time.time():
        raise HTTPException(400, "Неверный код")
    
    uid = "u_" + secrets.token_hex(4)
    payload = {
        "id": uid, "username": req.get("username", email.split("@")[0]),
        "email": email, "password": req.get("password"),
        "license_expires_at": int(time.time()*1000) + (3*24*3600*1000), # 3 дня триала
        "balance": 0, "created_at": int(time.time())
    }
    res = await db.query("users", method="POST", json_data=payload)
    return res[0]

# --- BOT MANAGEMENT ROUTES ---
@app.get("/api/bots/{user_id}")
async def get_user_bots(user_id: str):
    rows = await db.query("bots", params={"owner_id": f"eq.{user_id}"})
    for r in rows: r['status'] = "RUNNING" if r['id'] in active_tasks else "IDLE"
    return rows

@app.post("/api/bots/save")
async def save_bot_api(data: dict):
    bid = data['id']
    payload = {
        "id": bid, "owner_id": data['ownerId'], "name": data['name'], "token": data['token'],
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

@app.delete("/api/bots/delete/{bot_id}")
async def delete_bot_api(bot_id: str):
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel(); del active_tasks[bot_id]
    await db.query("bots", method="DELETE", params={"id": f"eq.{bot_id}"})
    return {"status": "ok"}

@app.post("/api/bots/start/{bot_id}")
async def start_bot_api(bot_id: str):
    res = await db.query("bots", params={"id": f"eq.{bot_id}"})
    if not res: raise HTTPException(404)
    if not is_license_active(res[0]['license_expires_at']): raise HTTPException(403, "Лицензия истекла")
    
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"status": "RUNNING"})
    if bot_id not in active_tasks:
        active_tasks[bot_id] = asyncio.create_task(bot_worker_task(bot_id, res[0]['token']))
    return {"status": "ok"}

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot_api(bot_id: str):
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"status": "IDLE"})
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel(); del active_tasks[bot_id]
    if bot_id in active_bots: del active_bots[bot_id]
    return {"status": "ok"}

# --- LICENSE & ADMIN ROUTES ---
@app.post("/api/license/activate")
async def activate_lic(req: dict):
    bot_id, key = req.get("botId"), req.get("key")
    # Простая логика ключей: BOT-1-(месяцы)-(рандом)
    match = re.match(r"BOT-1-(\d+)-(\w+)", key)
    if not match: raise HTTPException(400, "Неверный формат ключа")
    
    months = int(match.group(1))
    res = await db.query("bots", params={"id": f"eq.{bot_id}"})
    if not res: raise HTTPException(404)
    
    current_expiry = max(int(time.time()*1000), res[0]['license_expires_at'])
    new_expiry = current_expiry + (months * 30 * 24 * 3600 * 1000)
    
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"license_expires_at": new_expiry})
    return {"status": "ok", "newExpiry": new_expiry}

@app.post("/api/admin/generate-key")
async def gen_key(req: dict, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET: raise HTTPException(403)
    months = req.get("months", 1)
    key = f"BOT-1-{months}-{secrets.token_hex(4).upper()}"
    return {"key": key}

@app.post("/api/broadcast")
async def broadcast_api(req: dict):
    bot_ids, msg = req.get("botIds", []), req.get("message", "")
    success, failed = 0, 0
    for bid in bot_ids:
        bot = active_bots.get(bid)
        if not bot: continue
        res = await db.query("bots", params={"id": f"eq.{bid}", "select": "config"})
        if not res: continue
        users = [u['id'] for u in res[0]['config'].get('connectedUsers', []) if not u.get('is_banned')]
        for uid in users:
            try:
                await bot.send_message(uid, msg)
                success += 1
            except: failed += 1
    return {"success": success, "failed": failed}

@app.get("/api/ping")
async def ping(): return {"status": "online", "time": int(time.time())}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
