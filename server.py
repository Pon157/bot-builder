
import asyncio
import logging
import json
import os
import time
import re
import uuid
import secrets
import sys
import random
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException, Header, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ContentType
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter
import uvicorn

# --- Логирование ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("BotEngine.Server")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "database.json")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")

try:
    from email_service import EmailService
except ImportError:
    class EmailService:
        @staticmethod
        def send_verification_code(e, c): logger.info(f"EMAIL CODE {e}: {c}"); return True
        @staticmethod
        def send_password_reset(e, c): logger.info(f"RESET CODE {e}: {c}"); return True

# --- БД ---
db_content = {"users": [], "bots": [], "issued_keys": [], "verification_codes": {}}

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db_content, f, ensure_ascii=False, indent=2)
    except Exception as e: logger.error(f"DB Save Error: {e}")

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                db_content.update(data)
        except Exception as e: logger.error(f"DB Load Error: {e}")

# --- Logic ---
active_tasks = {}
active_bots = {}

async def bot_worker(bot_id: str, token: str):
    logger.info(f"Starting bot {bot_id}")
    session = AiohttpSession()
    bot = Bot(token=token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    active_bots[bot_id] = bot
    dp = Dispatcher()
    
    @dp.message(CommandStart())
    async def h_start(m: Message):
        cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not cfg: return
        if "connectedUsers" not in cfg: cfg["connectedUsers"] = []
        if not any(u["id"] == m.from_user.id for u in cfg["connectedUsers"]):
            cfg["connectedUsers"].append({"id": m.from_user.id, "first_name": m.from_user.first_name, "username": m.from_user.username, "is_active": True, "is_banned": False, "warns": 0})
            save_db()
        await m.answer(cfg.get("welcomeMessage", "Привет!"))

    @dp.message()
    async def h_all(m: Message):
        cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not cfg: return
        admin_id = cfg.get("adminChatId")
        if admin_id and str(m.chat.id) == str(admin_id) and m.reply_to_message:
            match = re.search(r"ID: (\d+)", m.reply_to_message.text or "")
            if match:
                try:
                    await bot.copy_message(int(match.group(1)), m.chat.id, m.message_id)
                    await m.reply("✅ Отправлено")
                    return
                except: pass
        if admin_id and str(m.chat.id) != str(admin_id):
            await bot.send_message(admin_id, f"📩 Сообщение от {m.from_user.full_name}\nID: <code>{m.from_user.id}</code>")
            await bot.copy_message(admin_id, m.chat.id, m.message_id)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await session.close()

# --- API ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_db()
    logger.info("✅ DB Loaded")
    yield
    for t in active_tasks.values(): t.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/ping")
async def ping(): 
    return {"status": "online", "timestamp": time.time()}

# --- AUTH ---
class RegReq(BaseModel): email: str; code: str; password: str; username: str
@app.post("/api/auth/request-verification")
async def req_v(req: dict, bg: BackgroundTasks):
    e = req.get("email", "").lower().strip()
    c = str(random.randint(100000, 999999))
    db_content["verification_codes"][e] = {"code": c, "expires": time.time() + 600}
    bg.add_task(EmailService.send_verification_code, e, c)
    return {"status": "ok"}

@app.post("/api/auth/verify-and-register")
async def v_reg(req: RegReq):
    v = db_content["verification_codes"].get(req.email.lower())
    if not v or v["code"] != req.code: raise HTTPException(400, "Invalid code")
    u = {"id": str(uuid.uuid4()), "username": req.username, "email": req.email, "password": req.password, "licenseExpiresAt": int((time.time() + 259200)*1000)}
    db_content["users"].append(u)
    save_db()
    return u

@app.post("/api/auth/login")
async def login(req: dict):
    u = next((u for u in db_content["users"] if u["email"].lower() == req.get("email","").lower() and u["password"] == req.get("password")), None)
    if not u: raise HTTPException(401)
    return u

# --- BOTS ---
@app.get("/api/bots/{uid}")
async def get_b(uid: str):
    bots = [b for b in db_content["bots"] if str(b["ownerId"]) == str(uid)]
    for b in bots: b["status"] = "RUNNING" if b["id"] in active_tasks and not active_tasks[b["id"]].done() else "IDLE"
    return bots

@app.post("/api/bots/save")
async def save_b_api(data: dict):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == data["id"]), -1)
    if idx >= 0: db_content["bots"][idx] = data
    else: db_content["bots"].append(data)
    save_db()
    return {"status": "ok"}

@app.post("/api/bots/start/{bid}")
async def start_b(bid: str):
    cfg = next((b for b in db_content["bots"] if b["id"] == bid), None)
    if not cfg: raise HTTPException(404)
    if bid not in active_tasks or active_tasks[bid].done():
        active_tasks[bid] = asyncio.create_task(bot_worker(bid, cfg["token"]))
    return {"status": "ok"}

@app.post("/api/bots/stop/{bid}")
async def stop_b(bid: str):
    t = active_tasks.pop(bid, None)
    if t: t.cancel()
    return {"status": "ok"}

@app.post("/api/broadcast")
async def brdcst(req: dict):
    success = 0
    for bid in req.get("botIds", []):
        bot = active_bots.get(bid)
        if not bot: continue
        cfg = next((b for b in db_content["bots"] if b["id"] == bid), None)
        for u in cfg.get("connectedUsers", []):
            try: await bot.send_message(u["id"], req.get("message")); success += 1
            except: pass
    return {"success": success, "failed": 0}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
