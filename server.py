
import asyncio
import logging
import json
import os
import time
import re
import uuid
import secrets
import sys
from contextlib import asynccontextmanager
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
import uvicorn

# --- Инициализация окружения ---
BASE_DIR = "/root/bot-builder/bot-builder"
if os.path.exists(BASE_DIR):
    os.chdir(BASE_DIR)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("API-Server")

def load_env():
    path = os.path.join(BASE_DIR, '.env')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip()
                if line and '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    val = v.strip().strip('"').strip("'")
                    # Очистка токена от мусора путей (если прилетел при копировании)
                    if k.strip() == "ADMIN_BOT_TOKEN" and "root/" in val:
                        val = val.split("root/")[0].strip()
                    os.environ[k.strip()] = val

load_env()
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")
DB_FILE = "database.json"

# --- Состояние ---
db_content = {"users": [], "bots": [], "issued_keys": []}
active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}

# --- Работа с БД ---
def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db_content, f, ensure_ascii=False, indent=2)
    except Exception as e: logger.error(f"DB Save Error: {e}")

def load_db():
    global db_content
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                db_content["users"] = loaded.get("users", [])
                db_content["bots"] = loaded.get("bots", [])
                db_content["issued_keys"] = loaded.get("issued_keys", [])
        except: pass

def check_license(owner_id: str) -> bool:
    user = next((u for u in db_content["users"] if str(u["id"]) == str(owner_id)), None)
    if not user: return False
    return float(user.get("licenseExpiresAt", 0)) > (time.time() * 1000)

# --- Логика Бот-Воркера (Конструктор) ---
async def bot_worker(bot_cfg: dict):
    bot_id = bot_cfg["id"]
    try:
        token = bot_cfg["token"].strip()
        bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        active_bots[bot_id] = bot
        dp = Dispatcher()

        def get_keyboard():
            btns = bot_cfg.get("buttons", [])
            if not btns: return None
            # Собираем клавиатуру по 2 кнопки в ряд
            rows = []
            current_row = []
            for b in btns:
                if b.get("text"):
                    current_row.append(KeyboardButton(text=b["text"]))
                    if len(current_row) == 2:
                        rows.append(current_row)
                        current_row = []
            if current_row: rows.append(current_row)
            return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

        @dp.message(CommandStart())
        async def handle_start(m: Message):
            if not check_license(bot_cfg["ownerId"]): return
            
            # Регистрация подписчика для рассылок
            if "subscribers" not in bot_cfg: bot_cfg["subscribers"] = []
            if m.from_user.id not in bot_cfg["subscribers"]:
                bot_cfg["subscribers"].append(m.from_user.id)
            
            # Регистрация пользователя для CRM/Модерации
            if "connectedUsers" not in bot_cfg: bot_cfg["connectedUsers"] = []
            if not any(u["id"] == m.from_user.id for u in bot_cfg["connectedUsers"]):
                bot_cfg["connectedUsers"].append({
                    "id": m.from_user.id,
                    "first_name": m.from_user.first_name,
                    "username": m.from_user.username,
                    "is_banned": False,
                    "warns": 0,
                    "joined_at": int(time.time())
                })
            save_db()
            await m.answer(bot_cfg.get("welcomeMessage", "Привет!"), reply_markup=get_keyboard())

        @dp.message()
        async def handle_messages(m: Message):
            if not check_license(bot_cfg["ownerId"]): return
            
            # 0. Проверка на бан
            user_crm = next((u for u in bot_cfg.get("connectedUsers", []) if u["id"] == m.from_user.id), None)
            if user_crm and user_crm.get("is_banned"): return

            admin_id = bot_cfg.get("adminChatId")

            # 1. Если пишет админ и это реплай — отвечаем пользователю (Livegram mode)
            if admin_id and str(m.from_user.id) == str(admin_id) and m.reply_to_message:
                reply_text = m.reply_to_message.text or m.reply_to_message.caption or ""
                match = re.search(r"ID: (\d+)", reply_text)
                if match:
                    target_id = int(match.group(1))
                    try:
                        if m.text: await bot.send_message(target_id, m.text)
                        elif m.photo: await bot.send_photo(target_id, m.photo[-1].file_id, caption=m.caption)
                        elif m.voice: await bot.send_voice(target_id, m.voice.file_id)
                        await m.reply("✅ Отправлено")
                    except Exception as e: await m.reply(f"❌ Ошибка отправки: {e}")
                return

            # 2. Обработка кнопок и триггеров (прежде чем слать админу)
            if m.text:
                text_low = m.text.lower()
                # Кнопки (точное совпадение)
                for btn in bot_cfg.get("buttons", []):
                    if btn["text"].lower() == text_low:
                        return await m.answer(btn["response"], reply_markup=get_keyboard())
                # Триггеры (вхождение слова)
                for trig in bot_cfg.get("triggers", []):
                    if trig["keyword"].lower() in text_low:
                        return await m.answer(trig["response"], reply_markup=get_keyboard())

            # 3. Пересылка админу (Feedback)
            if admin_id and str(m.from_user.id) != str(admin_id):
                info = f"📩 <b>Сообщение от {m.from_user.full_name}</b>\nID: <code>{m.from_user.id}</code>\n\n"
                try:
                    if m.text:
                        await bot.send_message(admin_id, info + m.text)
                    else:
                        await bot.send_message(admin_id, info + f"[Вложение: {m.content_type}]")
                        await m.forward_message(admin_id, m.chat.id, m.message_id)
                except Exception as e: logger.error(f"Forward fail: {e}")

        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Бот {bot_id} упал: {e}")
    finally: active_bots.pop(bot_id, None)

# --- FastAPI App ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_db()
    # Автозапуск ботов, которые были запущены
    for b in db_content["bots"]:
        if b.get("status") == "RUNNING" and check_license(b["ownerId"]):
            active_tasks[b["id"]] = asyncio.create_task(bot_worker(b))
    yield
    for t in active_tasks.values(): t.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class BroadcastRequest(BaseModel):
    botIds: List[str]
    message: str

# -- Auth API --
@app.get("/api/ping")
async def ping(): return {"status": "online"}

@app.post("/api/auth/login")
async def login(req: dict):
    u = next((u for u in db_content["users"] if u["email"] == req["email"] and u["password"] == req["password"]), None)
    if not u: raise HTTPException(401)
    return u

@app.post("/api/auth/register")
async def register(user: dict):
    if any(u["email"] == user["email"] for u in db_content["users"]):
        raise HTTPException(400, "User already exists")
    db_content["users"].append(user)
    save_db()
    return user

# -- Bots API --
@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    return [b for b in db_content["bots"] if str(b["ownerId"]) == str(user_id)]

@app.post("/api/bots/save")
async def save_bot_api(bot_data: dict):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == bot_data["id"]), -1)
    if idx >= 0:
        # Сохраняем логи и пользователей, если они уже есть в старом конфиге
        bot_data["logs"] = db_content["bots"][idx].get("logs", [])
        bot_data["connectedUsers"] = db_content["bots"][idx].get("connectedUsers", [])
        bot_data["subscribers"] = db_content["bots"][idx].get("subscribers", [])
        db_content["bots"][idx] = bot_data
    else:
        db_content["bots"].append(bot_data)
    save_db()
    return {"status": "ok"}

@app.delete("/api/bots/delete/{bot_id}")
async def delete_bot(bot_id: str):
    if bot_id in active_tasks: active_tasks[bot_id].cancel()
    db_content["bots"] = [b for b in db_content["bots"] if b["id"] != bot_id]
    save_db()
    return {"status": "ok"}

@app.post("/api/bots/start/{bot_id}")
async def start_bot(bot_id: str):
    cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not cfg: raise HTTPException(404)
    if not check_license(cfg["ownerId"]): raise HTTPException(403, "License expired")
    if bot_id not in active_tasks or active_tasks[bot_id].done():
        active_tasks[bot_id] = asyncio.create_task(bot_worker(cfg))
        cfg["status"] = "RUNNING"
        save_db()
    return {"status": "ok"}

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel()
        del active_tasks[bot_id]
    for b in db_content["bots"]:
        if b["id"] == bot_id: b["status"] = "IDLE"
    save_db()
    return {"status": "ok"}

# -- License & Admin API --
@app.post("/api/broadcast")
async def broadcast(req: BroadcastRequest):
    success, failed = 0, 0
    for bid in req.botIds:
        bot = active_bots.get(bid)
        cfg = next((b for b in db_content["bots"] if b["id"] == bid), None)
        if bot and cfg:
            for uid in cfg.get("subscribers", []):
                try:
                    await bot.send_message(uid, req.message)
                    success += 1
                except: failed += 1
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
