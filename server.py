
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
from aiogram.types import Message
from aiogram.client.default import DefaultBotProperties
import uvicorn

# ПРИНУДИТЕЛЬНАЯ НАСТРОЙКА ОКРУЖЕНИЯ
BASE_DIR = "/root/bot-builder/bot-builder"
if os.path.exists(BASE_DIR):
    os.chdir(BASE_DIR)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', stream=sys.stdout)
logger = logging.getLogger("API-Server")

def load_env_bulletproof():
    paths = [os.path.join(BASE_DIR, '.env'), '.env', '../.env']
    for p in paths:
        if os.path.exists(p):
            logger.info(f"📂 Загрузка конфигурации из: {p}")
            try:
                with open(p, 'r', encoding='utf-8-sig') as f:
                    for line in f:
                        line = line.strip()
                        if line and '=' in line and not line.startswith('#'):
                            k, v = line.split('=', 1)
                            val = v.strip().strip('"').strip("'")
                            # Фикс склейки путей в консоли
                            if "root/" in val and k.strip() == "ADMIN_BOT_TOKEN":
                                val = val.split("root/")[0].strip()
                            os.environ[k.strip()] = val
                return True
            except Exception as e: logger.error(f"Ошибка чтении {p}: {e}")
    return False

load_env_bulletproof()

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")
DB_FILE = "database.json"
db_content = {"users": [], "bots": [], "issued_keys": []}
active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}

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

def check_license(user_id: str) -> bool:
    user = next((u for u in db_content.get("users", []) if str(u.get("id")) == str(user_id)), None)
    if not user: return False
    return float(user.get("licenseExpiresAt", 0)) > (time.time() * 1000)

async def bot_worker(bot_cfg: dict):
    bot_id = bot_cfg["id"]
    try:
        token = bot_cfg["token"].strip()
        bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        active_bots[bot_id] = bot
        dp = Dispatcher()
        
        @dp.message(CommandStart())
        async def _start(m: Message):
            if not check_license(bot_cfg["ownerId"]): return
            if "subscribers" not in bot_cfg: bot_cfg["subscribers"] = []
            if m.from_user.id not in bot_cfg["subscribers"]:
                bot_cfg["subscribers"].append(m.from_user.id)
                save_db()
            await m.answer(bot_cfg.get("welcomeMessage", "Привет!"))

        @dp.message()
        async def _handle(m: Message):
            admin_id = bot_cfg.get("adminChatId")
            if not admin_id or not check_license(bot_cfg["ownerId"]): return
            if str(m.from_user.id) == str(admin_id) and m.reply_to_message:
                match = re.search(r"ID: (\d+)", m.reply_to_message.text or "")
                if match:
                    try:
                        await bot.send_message(int(match.group(1)), m.text or "[Media]")
                        await m.reply("✅ Отправлено")
                    except: pass
                return
            if str(m.from_user.id) != str(admin_id):
                info = f"📩 <b>От {m.from_user.full_name}</b>\nID: {m.from_user.id}\n\n"
                try:
                    if m.text: await bot.send_message(admin_id, info + m.text)
                    else: await bot.send_message(admin_id, info + "[Медиа]"); await m.forward(admin_id)
                except: pass

        await dp.start_polling(bot)
    except Exception as e: logger.error(f"Бот {bot_id} упал: {e}")
    finally: active_bots.pop(bot_id, None)

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_db()
    for b in db_content["bots"]:
        if b.get("status") == "RUNNING" and check_license(b["ownerId"]):
            active_tasks[b["id"]] = asyncio.create_task(bot_worker(b))
    yield
    for t in active_tasks.values(): t.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class LoginRequest(BaseModel):
    email: str
    password: str

class BroadcastRequest(BaseModel):
    botIds: List[str]
    message: str

@app.get("/api/ping")
async def ping(): return {"status": "online"}

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    u = next((u for u in db_content["users"] if u["email"] == req.email and u["password"] == req.password), None)
    if not u: raise HTTPException(401)
    return u

@app.post("/api/auth/register")
async def register(user_data: dict):
    db_content["users"].append(user_data); save_db()
    return user_data

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    return [b for b in db_content["bots"] if str(b["ownerId"]) == str(user_id)]

@app.post("/api/bots/save")
async def save_bot_api(bot_data: dict):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == bot_data["id"]), -1)
    if idx >= 0: db_content["bots"][idx] = bot_data
    else: db_content["bots"].append(bot_data)
    save_db(); return {"status": "ok"}

@app.delete("/api/bots/delete/{bot_id}")
async def delete_bot(bot_id: str):
    if bot_id in active_tasks: active_tasks[bot_id].cancel()
    db_content["bots"] = [b for b in db_content["bots"] if b["id"] != bot_id]
    save_db(); return {"status": "ok"}

@app.post("/api/bots/start/{bot_id}")
async def start_bot(bot_id: str):
    bot_cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not bot_cfg or not check_license(bot_cfg["ownerId"]): raise HTTPException(403)
    if bot_id not in active_tasks or active_tasks[bot_id].done():
        active_tasks[bot_id] = asyncio.create_task(bot_worker(bot_cfg))
        bot_cfg["status"] = "RUNNING"; save_db()
    return {"status": "ok"}

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    if bot_id in active_tasks: active_tasks[bot_id].cancel()
    for b in db_content["bots"]:
        if b["id"] == bot_id: b["status"] = "IDLE"
    save_db(); return {"status": "ok"}

@app.post("/api/broadcast")
async def broadcast(req: BroadcastRequest):
    success, failed = 0, 0
    for bid in req.botIds:
        bot = active_bots.get(bid)
        bot_cfg = next((b for b in db_content["bots"] if b["id"] == bid), None)
        if bot and bot_cfg:
            for uid in bot_cfg.get("subscribers", []):
                try: await bot.send_message(uid, req.message); success += 1
                except: failed += 1
    return {"success": success, "failed": failed}

@app.post("/api/license/activate")
async def activate_key(req: dict):
    u = next((u for u in db_content["users"] if str(u["id"]) == str(req['userId'])), None)
    k = next((k for k in db_content["issued_keys"] if k["key"] == req['key'] and not k["used"]), None)
    if not u or not k: raise HTTPException(400)
    now = int(time.time() * 1000)
    u["licenseExpiresAt"] = max(u.get("licenseExpiresAt", now), now) + (k["months"] * 30 * 24 * 3600 * 1000)
    k["used"] = True; save_db()
    return {"status": "ok", "newExpiry": u["licenseExpiresAt"]}

@app.post("/api/admin/generate-key")
async def admin_gen_key(req: dict, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET: raise HTTPException(403)
    key = f"BOT-{req['months']}-{secrets.token_hex(3).upper()}"
    db_content["issued_keys"].append({"key": key, "months": req['months'], "used": False})
    save_db(); return {"key": key}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
