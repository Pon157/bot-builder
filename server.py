
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
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
import uvicorn

# --- Модели данных (Pydantic) ---
class VerificationRequest(BaseModel):
    email: str

class VerifyRegisterRequest(BaseModel):
    email: str
    code: str
    username: str
    password: str

class BroadcastRequest(BaseModel):
    botIds: List[str]
    message: str

# --- Инициализация окружения ---
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
        def send_verification_code(email, code): return True
        @staticmethod
        def send_password_reset(email, code): return True

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Ошибка: В .env не указаны SUPABASE_URL или SUPABASE_KEY!")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotEngineCore")

active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}
verification_store: Dict[str, dict] = {} 

class SupabaseDB:
    def __init__(self, url: str, key: str):
        self.url = url
        self.key = key
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
                logger.error(f"HTTP Connection Error: {e}")
                return []

db = SupabaseDB(SUPABASE_URL, SUPABASE_KEY)

# --- Логирование в БД ---
async def add_bot_log(bot_id: str, log_type: str, text: str):
    res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "config"})
    if not res: return
    config = res[0].get('config', {})
    logs = config.get("logs", [])
    new_log = {
        "id": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "type": log_type,
        "text": text[:500]
    }
    logs.insert(0, new_log)
    config["logs"] = logs[:50] 
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"config": config})

def format_msg(template: str, m: Message, btn_text: str = "") -> str:
    if not template: return f"📩 Сообщение от {m.from_user.id}"
    res = template.replace("{{id}}", str(m.from_user.id))
    res = res.replace("{{name}}", m.from_user.full_name or "User")
    res = res.replace("{{username}}", f"@{m.from_user.username}" if m.from_user.username else "none")
    res = res.replace("{{button}}", btn_text)
    return res

async def update_bot_stats_db(bot_id: str, direction: str):
    res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "stats,config"})
    if not res: return
    stats = res[0].get('stats', {})
    config = res[0].get('config', {})
    
    if not stats: stats = {"totalMessages": 0, "incomingToday": 0, "outgoingToday": 0, "bannedCount": 0, "history": []}
    
    stats["totalMessages"] = stats.get("totalMessages", 0) + 1
    if direction == "incoming": stats["incomingToday"] = stats.get("incomingToday", 0) + 1
    else: stats["outgoingToday"] = stats.get("outgoingToday", 0) + 1
    
    today_str = datetime.now().strftime("%d.%m")
    history = stats.get("history", [])
    
    if not history or history[-1]["date"] != today_str:
        history.append({
            "date": today_str, 
            "incoming": 0, 
            "outgoing": 0,
            "totalUsers": len(config.get("connectedUsers", [])),
            "activeUsers": len([u for u in config.get("connectedUsers", []) if u.get("is_active") and not u.get("is_banned")])
        })
    
    if direction == "incoming": history[-1]["incoming"] += 1
    else: history[-1]["outgoing"] += 1
    
    history[-1]["totalUsers"] = len(config.get("connectedUsers", []))
    history[-1]["activeUsers"] = len([u for u in config.get("connectedUsers", []) if u.get("is_active") and not u.get("is_banned")])
    
    stats["history"] = history[-10:] 

    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"stats": stats})

def is_license_active(expires_at: int) -> bool:
    return int(expires_at or 0) > int(time.time() * 1000)

# --- Бот Воркер ---
async def bot_worker_task(bot_id: str, token: str):
    session = AiohttpSession()
    bot = Bot(token=token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    active_bots[bot_id] = bot
    dp = Dispatcher()
    router = Router()

    await add_bot_log(bot_id, "system", "Бот запущен.")

    @router.message(CommandStart())
    async def cmd_start(m: Message):
        res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "config,license_expires_at"})
        if not res or not is_license_active(res[0]['license_expires_at']): return
        config = res[0]['config']
        
        await add_bot_log(bot_id, "incoming", f"Команда /start от {m.from_user.id}")

        users = config.get("connectedUsers", [])
        user = next((u for u in users if u['id'] == m.from_user.id), None)
        if not user:
            user = {
                "id": m.from_user.id, "first_name": m.from_user.first_name, 
                "username": m.from_user.username, "joined_at": int(time.time()), 
                "is_banned": False, "warns": 0, "thread_id": None, "is_active": True
            }
            users.append(user)
            config["connectedUsers"] = users
            await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"config": config})
            await add_bot_log(bot_id, "info", f"Новый пользователь: {m.from_user.id}")
        
        btns = config.get("buttons", [])
        rows = [[KeyboardButton(text=b["text"])] for b in btns if b.get("text")]
        kb = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True) if rows else None
        
        welcome = config.get("welcomeMessage", "Привет!")
        await m.answer(format_msg(welcome, m), reply_markup=kb)
        await update_bot_stats_db(bot_id, "outgoing")

    @router.message(Command("warn", "unwarn", "ban", "unban"))
    async def admin_moderation(m: Message):
        res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "config"})
        if not res: return
        config = res[0]['config']
        if str(m.chat.id) != str(config.get("adminChatId")): return

        target_user = None
        if m.message_thread_id:
            target_user = next((u for u in config.get("connectedUsers", []) if u.get("thread_id") == m.message_thread_id), None)
        if not target_user and m.reply_to_message:
            match = re.search(r"ID: (\d+)", m.reply_to_message.text or m.reply_to_message.caption or "")
            if match:
                uid = int(match.group(1))
                target_user = next((u for u in config.get("connectedUsers", []) if u["id"] == uid), None)

        if not target_user:
            return await m.reply("❌ Пользователь не найден.")

        cmd = m.text.split()[0].replace("/", "").lower()
        await add_bot_log(bot_id, "system", f"Админ: {cmd} для {target_user['id']}")
        threshold = config.get("settings", {}).get("autoBanThreshold", 0)

        if cmd == "warn":
            target_user["warns"] = target_user.get("warns", 0) + 1
            txt = f"⚠️ <b>Предупреждение!</b> Всего: {target_user['warns']}"
            try: await bot.send_message(target_user["id"], txt)
            except: pass
            
            if threshold > 0 and target_user["warns"] >= threshold:
                target_user["is_banned"] = True
                try: await bot.send_message(target_user["id"], "🚫 <b>Авто-бан.</b>")
                except: pass
            await m.answer("✅ Варн выдан")

        elif cmd == "unwarn":
            target_user["warns"] = max(0, target_user.get("warns", 0) - 1)
            await m.answer("✅ Варн снят")

        elif cmd == "ban":
            target_user["is_banned"] = True
            try: await bot.send_message(target_user["id"], "🚫 <b>Вы заблокированы.</b>")
            except: pass
            await m.answer("✅ Пользователь забанен")

        elif cmd == "unban":
            target_user["is_banned"] = False
            await m.answer("✅ Разблокирован")

        await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"config": config})

    @router.message()
    async def main_handler(m: Message):
        res = await db.query("bots", params={"id": f"eq.{bot_id}", "select": "config,license_expires_at"})
        if not res or not is_license_active(res[0]['license_expires_at']): return
        config = res[0]['config']
        admin_id = config.get("adminChatId")

        # АДМИН ПИШЕТ
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
                    await update_bot_stats_db(bot_id, "outgoing")
                    await add_bot_log(bot_id, "outgoing", f"Ответ админа юзеру {target_id}")
                except Exception as e:
                    await add_bot_log(bot_id, "error", f"Ошибка отправки юзеру {target_id}: {e}")
            return

        # ПОЛЬЗОВАТЕЛЬ ПИШЕТ
        user = next((u for u in config.get("connectedUsers", []) if u["id"] == m.from_user.id), None)
        if not user or user.get("is_banned"): return

        await add_bot_log(bot_id, "incoming", f"Сообщение от {m.from_user.id}")

        if m.text:
            text_low = m.text.lower()
            # Обработка кнопок
            for btn in config.get("buttons", []):
                if btn.get("text") and btn["text"].lower() == text_low:
                    await add_bot_log(bot_id, "info", f"Нажата кнопка: {btn['text']}")
                    
                    if btn.get("type") == "request" and admin_id:
                        # Используем кастомный шаблон из настроек кнопки
                        template = btn.get("adminTemplate") or "📩 <b>Новое обращение!</b>\nКнопка: {{button}}\nОт: {{name}} (ID: {{id}})"
                        txt = format_msg(template, m, btn["text"])
                        try:
                            await bot.send_message(admin_id, txt, message_thread_id=user.get("thread_id"))
                        except: pass
                    
                    if btn.get("response"):
                        await m.answer(btn.get("response"))
                        await update_bot_stats_db(bot_id, "outgoing")
                    return
            
            # Обработка триггеров
            for trig in config.get("triggers", []):
                if trig.get("keyword") and trig["keyword"].lower() in text_low:
                    await add_bot_log(bot_id, "info", f"Сработал триггер: {trig['keyword']}")
                    await m.answer(trig.get("response", ""))
                    await update_bot_stats_db(bot_id, "outgoing")
                    return

        # Просто пересылка админу
        if admin_id:
            try:
                # Генерируем служебную плашку перед пересылкой, если это НЕ кнопка
                info_header = f"👤 {m.from_user.full_name} (ID: <code>{m.from_user.id}</code>)\n\n"
                await bot.send_message(admin_id, info_header, message_thread_id=user.get("thread_id"))
                await bot.copy_message(admin_id, m.chat.id, m.message_id, message_thread_id=user.get("thread_id"))
                await update_bot_stats_db(bot_id, "incoming")
            except: pass

    dp.include_router(router)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await session.close()

# --- FastAPI App ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    running = await db.query("bots", params={"status": "eq.RUNNING", "select": "id,token,license_expires_at"})
    for b in running:
        if is_license_active(b['license_expires_at']):
            active_tasks[b['id']] = asyncio.create_task(bot_worker_task(b['id'], b['token']))
    yield
    for t in active_tasks.values(): t.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/ping")
async def ping(): return {"status": "online"}

@app.post("/api/auth/request-verification")
async def req_ver(req: VerificationRequest):
    res = await db.query("users", params={"email": f"eq.{req.email}"})
    if res: raise HTTPException(400, "Email уже существует")
    code = "".join(secrets.choice("0123456789") for _ in range(6))
    verification_store[req.email] = {"code": code, "expires": int(time.time()) + 600}
    if EmailService.send_verification_code(req.email, code):
        return {"status": "ok"}
    raise HTTPException(500, "SMTP Error")

@app.post("/api/auth/verify-and-register")
async def ver_reg(req: VerifyRegisterRequest):
    store = verification_store.get(req.email)
    if not store or store["code"] != req.code or store["expires"] < time.time():
        raise HTTPException(400, "Код неверен")
    uid = "u_" + secrets.token_hex(4)
    expires = int(time.time() * 1000) + (3 * 24 * 3600 * 1000)
    user_payload = {"id": uid, "username": req.username, "email": req.email, "password": req.password, "license_expires_at": expires, "created_at": int(time.time()), "balance": 0}
    res = await db.query("users", method="POST", json_data=user_payload)
    return res[0]

@app.post("/api/auth/login")
async def login(req: dict):
    res = await db.query("users", params={"email": f"eq.{req['email']}", "password": f"eq.{req['password']}"})
    if not res: raise HTTPException(401, "Ошибка входа")
    return res[0]

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
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
async def del_bot(bot_id: str):
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel(); del active_tasks[bot_id]
    await db.query("bots", method="DELETE", params={"id": f"eq.{bot_id}"})
    return {"status": "ok"}

@app.post("/api/bots/start/{bot_id}")
async def start_bot(bot_id: str):
    res = await db.query("bots", params={"id": f"eq.{bot_id}"})
    if not res: raise HTTPException(404, "Not Found")
    bot_data = res[0]
    if not is_license_active(bot_data['license_expires_at']):
        raise HTTPException(403, "License Expired")
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"status": "RUNNING"})
    if bot_id not in active_tasks:
        active_tasks[bot_id] = asyncio.create_task(bot_worker_task(bot_id, bot_data['token']))
    return {"status": "ok"}

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    await db.query("bots", method="PATCH", params={"id": f"eq.{bot_id}"}, json_data={"status": "IDLE"})
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel(); del active_tasks[bot_id]
    if bot_id in active_bots:
        await add_bot_log(bot_id, "system", "Бот остановлен пользователем.")
        del active_bots[bot_id]
    return {"status": "ok"}

@app.post("/api/broadcast")
async def broadcast(req: BroadcastRequest):
    success, failed = 0, 0
    for bid in req.botIds:
        bot = active_bots.get(bid)
        if not bot: continue
        res = await db.query("bots", params={"id": f"eq.{bid}", "select": "config"})
        if not res: continue
        users = [u['id'] for u in res[0]['config'].get('connectedUsers', []) if not u.get('is_banned')]
        for uid in users:
            try:
                await bot.send_message(uid, req.message)
                success += 1
            except: failed += 1
    return {"success": success, "failed": failed}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
