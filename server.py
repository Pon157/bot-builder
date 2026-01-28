
import asyncio
import logging
import json
import os
import time
import re
import uuid
import secrets
import sys
import asyncpg
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest
import uvicorn

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

DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")

if not DATABASE_URL:
    print("❌ Ошибка: DATABASE_URL не найден в .env")
    sys.exit(1)

try:
    from email_service import EmailService
except ImportError:
    class EmailService:
        @staticmethod
        def send_verification_code(email, code): return True
        @staticmethod
        def send_password_reset(email, code): return True

# --- Логирование ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotEngineCore")

db_pool: Optional[asyncpg.Pool] = None
verification_store: Dict[str, dict] = {} 
active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}

async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                license_expires_at BIGINT NOT NULL,
                balance INT DEFAULT 0,
                created_at BIGINT
            );
            CREATE TABLE IF NOT EXISTS bots (
                id TEXT PRIMARY KEY,
                owner_id TEXT REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                token TEXT NOT NULL,
                status TEXT DEFAULT 'IDLE',
                config JSONB DEFAULT '{}',
                stats JSONB DEFAULT '{}',
                license_expires_at BIGINT NOT NULL,
                created_at BIGINT
            );
            CREATE TABLE IF NOT EXISTS issued_keys (
                key TEXT PRIMARY KEY,
                months INT NOT NULL,
                used BOOLEAN DEFAULT FALSE,
                created_at BIGINT
            );
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            CREATE INDEX IF NOT EXISTS idx_bots_owner ON bots(owner_id);
        ''')
    logger.info("✅ PostgreSQL tables initialized")

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

class ActivateRequest(BaseModel):
    botId: str
    key: str

class KeyGenRequest(BaseModel):
    months: int

def format_msg(template: str, m: Message, btn_text: str = "") -> str:
    if not template: return f"📩 Сообщение от {m.from_user.id}"
    res = template.replace("{{id}}", str(m.from_user.id))
    res = res.replace("{{name}}", m.from_user.full_name or "User")
    res = res.replace("{{username}}", f"@{m.from_user.username}" if m.from_user.username else "none")
    res = res.replace("{{button}}", btn_text)
    return res

async def update_bot_stats_db(bot_id: str, direction: str):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow('SELECT stats FROM bots WHERE id = $1', bot_id)
        stats = json.loads(row['stats']) if row and row['stats'] else {"totalMessages": 0, "incomingToday": 0, "outgoingToday": 0}
        stats["totalMessages"] += 1
        if direction == "incoming": stats["incomingToday"] += 1
        else: stats["outgoingToday"] += 1
        await conn.execute('UPDATE bots SET stats = $1 WHERE id = $2', json.dumps(stats), bot_id)

async def bot_worker_task(bot_id: str, token: str):
    session = AiohttpSession()
    bot = Bot(token=token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    active_bots[bot_id] = bot
    dp = Dispatcher()
    router = Router()

    @router.message(CommandStart())
    async def cmd_start(m: Message):
        async with db_pool.acquire() as conn:
            bot_row = await conn.fetchrow('SELECT config, license_expires_at FROM bots WHERE id = $1', bot_id)
            if not bot_row or bot_row['license_expires_at'] < int(time.time() * 1000): return
            config = json.loads(bot_row['config'])
            
            users = config.get("connectedUsers", [])
            if not any(u['id'] == m.from_user.id for u in users):
                users.append({"id": m.from_user.id, "first_name": m.from_user.first_name, "username": m.from_user.username, "joined_at": int(time.time()), "is_banned": False, "warns": 0, "thread_id": None})
                config["connectedUsers"] = users
                await conn.execute('UPDATE bots SET config = $1 WHERE id = $2', json.dumps(config), bot_id)
            
            rows = [[KeyboardButton(text=btn["text"])] for btn in config.get("buttons", []) if btn.get("text")]
            kb = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True) if rows else None
            await m.answer(format_msg(config.get("welcomeMessage", "Привет!"), m), reply_markup=kb)

    @router.message(Command("warn", "unwarn", "ban", "unban"))
    async def admin_cmds(m: Message):
        async with db_pool.acquire() as conn:
            bot_row = await conn.fetchrow('SELECT config FROM bots WHERE id = $1', bot_id)
            config = json.loads(bot_row['config'])
            if str(m.chat.id) != str(config.get("adminChatId")): return
            
            target_id = None
            if m.message_thread_id:
                u = next((u for u in config.get("connectedUsers", []) if u.get("thread_id") == m.message_thread_id), None)
                if u: target_id = u["id"]
            
            if not target_id and m.reply_to_message:
                match = re.search(r"ID: (\d+)", m.reply_to_message.text or m.reply_to_message.caption or "")
                if match: target_id = int(match.group(1))
            
            if not target_id: return await m.reply("❌ Пользователь не найден в контексте сообщения")
            
            users = config.get("connectedUsers", [])
            user = next((u for u in users if u['id'] == target_id), None)
            if not user: return
            
            cmd = m.text.split()[0].replace("/", "").lower()
            threshold = config.get("settings", {}).get("autoBanThreshold", 0)

            if cmd == "ban":
                user["is_banned"] = True
                try: await bot.send_message(target_id, "🚫 <b>Вы были заблокированы администратором.</b>")
                except: pass
            elif cmd == "unban":
                user["is_banned"] = False
                # Сброс варнов ниже порога при разбане
                if threshold > 0 and user.get("warns", 0) >= threshold:
                    user["warns"] = threshold - 1
                try: await bot.send_message(target_id, "✅ <b>Вы были разблокированы!</b>")
                except: pass
            elif cmd == "warn":
                user["warns"] = user.get("warns", 0) + 1
                try: await bot.send_message(target_id, f"⚠️ <b>Предупреждение!</b> Всего: {user['warns']}")
                except: pass
                if threshold > 0 and user["warns"] >= threshold:
                    user["is_banned"] = True
                    try: await bot.send_message(target_id, "🚫 <b>Автоматический бан (превышен порог предупреждений).</b>")
                    except: pass
            elif cmd == "unwarn":
                user["warns"] = max(0, user.get("warns", 0) - 1)
                try: await bot.send_message(target_id, f"ℹ️ <b>Предупреждение снято.</b> Осталось: {user['warns']}")
                except: pass
            
            await conn.execute('UPDATE bots SET config = $1 WHERE id = $2', json.dumps(config), bot_id)
            await m.answer(f"✅ Команда <b>/{cmd}</b> выполнена для юзера <code>{target_id}</code>")

    @router.message()
    async def main_handler(m: Message):
        async with db_pool.acquire() as conn:
            bot_row = await conn.fetchrow('SELECT config, license_expires_at FROM bots WHERE id = $1', bot_id)
            if not bot_row or bot_row['license_expires_at'] < int(time.time() * 1000): return
            config = json.loads(bot_row['config'])
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
                        await update_bot_stats_db(bot_id, "outgoing")
                    except: pass
                return

            user = next((u for u in config.get("connectedUsers", []) if u["id"] == m.from_user.id), None)
            if user and user.get("is_banned"): return

            if m.text:
                for btn in config.get("buttons", []):
                    if btn.get("text") and btn["text"].lower() == m.text.lower():
                        if btn.get("type") == "request" and admin_id:
                            tid = user.get("thread_id") if user else None
                            if config.get("settings", {}).get("useTopics") and not tid:
                                try:
                                    topic = await bot.create_forum_topic(admin_id, f"{m.from_user.first_name} [{m.from_user.id}]")
                                    tid = topic.message_thread_id
                                    user["thread_id"] = tid
                                    await conn.execute('UPDATE bots SET config = $1 WHERE id = $2', json.dumps(config), bot_id)
                                except: pass
                            
                            await bot.send_message(admin_id, format_msg(btn.get("adminTemplate", ""), m, btn["text"]), message_thread_id=tid)
                        
                        await m.answer(btn.get("response", "Принято"))
                        await update_bot_stats_db(bot_id, "outgoing")
                        return

            if admin_id and str(m.chat.id) != str(admin_id):
                tid = user.get("thread_id") if user else None
                info = f"📩 ID: <code>{m.from_user.id}</code>\n👤 {m.from_user.full_name}"
                try:
                    if not tid: await bot.send_message(admin_id, info)
                    await bot.copy_message(admin_id, m.chat.id, m.message_id, message_thread_id=tid)
                    await update_bot_stats_db(bot_id, "incoming")
                except TelegramBadRequest as e:
                    if "thread not found" in str(e):
                        await bot.send_message(admin_id, info)
                        await bot.copy_message(admin_id, m.chat.id, m.message_id)

    dp.include_router(router)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await session.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with db_pool.acquire() as conn:
        running = await conn.fetch("SELECT id, token FROM bots WHERE status = 'RUNNING'")
        for b in running:
            active_tasks[b['id']] = asyncio.create_task(bot_worker_task(b['id'], b['token']))
    yield
    for t in active_tasks.values(): t.cancel()
    await db_pool.close()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/ping")
async def ping(): return {"status": "online"}

@app.post("/api/auth/request-verification")
async def request_verification(req: VerificationRequest):
    async with db_pool.acquire() as conn:
        if await conn.fetchval('SELECT 1 FROM users WHERE email = $1', req.email):
            raise HTTPException(400, "Email уже занят")
    code = "".join(secrets.choice("0123456789") for _ in range(6))
    verification_store[req.email] = {"code": code, "expires": int(time.time()) + 600, "type": "reg"}
    if EmailService.send_verification_code(req.email, code): return {"status": "ok"}
    raise HTTPException(500, "Ошибка почты")

@app.post("/api/auth/verify-and-register")
async def verify_and_register(req: VerifyAndRegisterRequest):
    store = verification_store.get(req.email)
    if not store or store["code"] != req.code or store["type"] != "reg":
        raise HTTPException(400, "Неверный код")
    uid = "u_" + secrets.token_hex(4)
    expires = int(time.time() * 1000) + (3 * 24 * 3600 * 1000)
    async with db_pool.acquire() as conn:
        await conn.execute('INSERT INTO users (id, username, email, password, license_expires_at, created_at) VALUES ($1, $2, $3, $4, $5, $6)',
                           uid, req.username, req.email, req.password, expires, int(time.time()))
        user = await conn.fetchrow('SELECT * FROM users WHERE id = $1', uid)
    return dict(user)

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow('SELECT * FROM users WHERE email = $1 AND password = $2', req.email, req.password)
        if not user: raise HTTPException(401, "Неверные данные")
        return dict(user)

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch('SELECT * FROM bots WHERE owner_id = $1', user_id)
        res = []
        for r in rows:
            d = dict(r)
            config = json.loads(d.get('config', '{}'))
            stats = json.loads(d.get('stats', '{}'))
            status = "RUNNING" if d['id'] in active_tasks else "IDLE"
            bot_obj = {**config, **d, "status": status, "stats": stats}
            if "config" in bot_obj: del bot_obj["config"]
            res.append(bot_obj)
        return res

@app.post("/api/bots/save")
async def save_bot(data: dict):
    bid, oid, name, token = data['id'], data['ownerId'], data['name'], data['token']
    expires = data.get('licenseExpiresAt', 0)
    config_keys = ['welcomeMessage', 'adminChatId', 'buttons', 'triggers', 'settings', 'connectedUsers', 'logs']
    config = {k: data.get(k) for k in config_keys if k in data}
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO bots (id, owner_id, name, token, config, license_expires_at, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (id) DO UPDATE SET name=$3, token=$4, config=$5, license_expires_at=$6
        ''', bid, oid, name, token, json.dumps(config), expires, int(time.time()))
    return {"status": "ok"}

@app.delete("/api/bots/delete/{bot_id}")
async def delete_bot(bot_id: str):
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel(); del active_tasks[bot_id]
    async with db_pool.acquire() as conn:
        await conn.execute('DELETE FROM bots WHERE id = $1', bot_id)
    return {"status": "ok"}

@app.post("/api/bots/start/{bot_id}")
async def start_bot(bot_id: str):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow('SELECT token, license_expires_at FROM bots WHERE id = $1', bot_id)
        if not row or row['license_expires_at'] < int(time.time() * 1000):
            raise HTTPException(403, "Лицензия истекла")
        await conn.execute("UPDATE bots SET status = 'RUNNING' WHERE id = $1", bot_id)
        if bot_id not in active_tasks:
            active_tasks[bot_id] = asyncio.create_task(bot_worker_task(bot_id, row['token']))
    return {"status": "ok"}

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE bots SET status = 'IDLE' WHERE id = $1", bot_id)
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel(); del active_tasks[bot_id]
    return {"status": "ok"}

@app.post("/api/broadcast")
async def broadcast(req: BroadcastRequest):
    success, failed = 0, 0
    for bid in req.botIds:
        bot = active_bots.get(bid)
        if not bot: continue
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow('SELECT config FROM bots WHERE id = $1', bid)
            if not row: continue
            config = json.loads(row['config'])
            users = [u['id'] for u in config.get('connectedUsers', []) if not u.get('is_banned')]
            for uid in users:
                try:
                    await bot.send_message(uid, req.message)
                    success += 1
                except: failed += 1
    return {"success": success, "failed": failed}

@app.post("/api/license/activate")
async def activate_license(req: ActivateRequest):
    async with db_pool.acquire() as conn:
        key_row = await conn.fetchrow('SELECT * FROM issued_keys WHERE key = $1 AND used = FALSE', req.key)
        if not key_row: raise HTTPException(400, "Неверный ключ")
        bot = await conn.fetchrow('SELECT license_expires_at FROM bots WHERE id = $1', req.botId)
        new_exp = max(bot['license_expires_at'], int(time.time() * 1000)) + (key_row['months'] * 30 * 24 * 3600 * 1000)
        await conn.execute('UPDATE bots SET license_expires_at = $1 WHERE id = $2', new_exp, req.botId)
        await conn.execute('UPDATE issued_keys SET used = TRUE WHERE key = $1', req.key)
        return {"status": "ok", "newExpiry": new_exp}

@app.post("/api/admin/generate-key")
async def generate_key(req: KeyGenRequest, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET: raise HTTPException(403)
    key = f"BOT-{req.months}-{secrets.token_hex(3).upper()}"
    async with db_pool.acquire() as conn:
        await conn.execute('INSERT INTO issued_keys (key, months, created_at) VALUES ($1, $2, $3)', key, req.months, int(time.time()))
    return {"key": key}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
