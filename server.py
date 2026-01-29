
import asyncio
import logging
import json
import os
import time
import re
import uuid
import secrets
import sys
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ContentType
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter
import uvicorn

# --- Инициализация окружения ---  
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotEngineCore")

DB_FILE = "database.json"
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")

# --- Модели данных ---
class LoginRequest(BaseModel):
    email: str
    password: str

class BroadcastRequest(BaseModel):
    botIds: List[str]
    message: str

class KeyGenRequest(BaseModel):
    months: int

class ActivateRequest(BaseModel):
    botId: str
    key: str

# --- БД ---
db_content = {"users": [], "bots": [], "issued_keys": [], "system_logs": []}

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db_content, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"❌ Save DB Error: {e}")

def load_db():
    global db_content
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                for key in db_content.keys():
                    if key in loaded: db_content[key] = loaded[key]
        except Exception as e:
            logger.error(f"❌ Load DB Error: {e}")

def add_bot_log(bot_id: str, log_type: str, text: str):
    bot = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not bot: return
    log_entry = {"id": str(uuid.uuid4()), "timestamp": int(time.time() * 1000), "type": log_type, "text": text}
    if "logs" not in bot: bot["logs"] = []
    bot["logs"].insert(0, log_entry)
    bot["logs"] = bot["logs"][:100]
    save_db()

def update_bot_stats(bot_id: str, direction: str):
    bot = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not bot: return
    if "stats" not in bot or not bot["stats"]:
        bot["stats"] = {"totalMessages": 0, "incomingToday": 0, "outgoingToday": 0, "bannedCount": 0, "history": [], "activeUsers24h": 0}
    bot["stats"]["totalMessages"] += 1
    bot["stats"]["incomingToday" if direction == "incoming" else "outgoingToday"] += 1
    save_db()

def is_bot_license_active(bot_config: dict) -> bool:
    return int(bot_config.get("licenseExpiresAt", 0)) > int(time.time() * 1000)

active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}

def format_msg(template: str, m: Message, btn_text: str = "") -> str:
    if not template: return f"📩 Сообщение от {m.from_user.id}"
    res = template.replace("{{id}}", str(m.from_user.id))
    res = res.replace("{{name}}", m.from_user.full_name or "User")
    res = res.replace("{{username}}", f"@{m.from_user.username}" if m.from_user.username else "none")
    res = res.replace("{{button}}", btn_text)
    return res

# --- Бот Воркер ---
async def bot_worker_task(bot_id: str, token: str):
    session = AiohttpSession()
    bot = Bot(token=token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    active_bots[bot_id] = bot
    dp = Dispatcher()
    router = Router()

    @router.message(CommandStart())
    async def cmd_start(m: Message):
        config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not config or not is_bot_license_active(config): return
        
        if "connectedUsers" not in config: config["connectedUsers"] = []
        user = next((u for u in config["connectedUsers"] if u["id"] == m.from_user.id), None)
        if not user:
            user = {"id": m.from_user.id, "first_name": m.from_user.first_name, "username": m.from_user.username, "joined_at": int(time.time()), "is_banned": False, "warns": 0, "thread_id": None}
            config["connectedUsers"].append(user)
            config["usersCount"] = len(config["connectedUsers"])
        
        if "subscribers" not in config: config["subscribers"] = []
        if m.from_user.id not in config["subscribers"]: config["subscribers"].append(m.from_user.id)
        save_db()

        if user.get("is_banned"): return
        
        rows = []
        for btn in config.get("buttons", []):
            if btn.get("text"): rows.append([KeyboardButton(text=btn["text"])])
        kb = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True) if rows else None
        
        msg = format_msg(config.get("welcomeMessage", "Привет!"), m)
        await m.answer(msg, reply_markup=kb)

    @router.message(Command("warn", "unwarn", "ban", "unban"))
    async def admin_moderation(m: Message):
        config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not config or str(m.chat.id) != str(config.get("adminChatId")): return

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
        threshold = config.get("settings", {}).get("autoBanThreshold", 0)

        if cmd == "warn":
            target_user["warns"] = target_user.get("warns", 0) + 1
            txt = f"⚠️ <b>Вам выдано предупреждение!</b>\nВсего: {target_user['warns']}"
            if threshold > 0: txt += f" / {threshold}"
            try: await bot.send_message(target_user["id"], txt)
            except: pass
            
            if threshold > 0 and target_user["warns"] >= threshold:
                target_user["is_banned"] = True
                try: await bot.send_message(target_user["id"], "🚫 <b>Вы были автоматически заблокированы (порог варнов).</b>")
                except: pass
                await m.answer(f"🔨 Юзер {target_user['id']} автоматически забанен.")
            else:
                await m.answer(f"✅ Варн выдан. Всего: {target_user['warns']}")

        elif cmd == "unwarn":
            target_user["warns"] = max(0, target_user.get("warns", 0) - 1)
            try: await bot.send_message(target_user["id"], f"ℹ️ <b>С вас снято предупреждение.</b>\nОсталось: {target_user['warns']}")
            except: pass
            await m.answer(f"✅ Варн снят. Осталось: {target_user['warns']}")

        elif cmd == "ban":
            target_user["is_banned"] = True
            try: await bot.send_message(target_user["id"], "🚫 <b>Вы были заблокированы администратором.</b>")
            except: pass
            await m.answer("✅ Юзер забанен.")

        elif cmd == "unban":
            target_user["is_banned"] = False
            # При разбане через ТГ тоже сбрасываем варны, чтобы не было моментального ребана
            if threshold > 0 and target_user.get("warns", 0) >= threshold:
                target_user["warns"] = threshold - 1
            try: await bot.send_message(target_user["id"], "✅ <b>Вы были разблокированы администратором!</b>")
            except: pass
            await m.answer("✅ Юзер разблокирован.")

        save_db()

    @router.message()
    async def main_handler(m: Message):
        config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not config or not is_bot_license_active(config): return
        admin_id = config.get("adminChatId")

        # АДМИН
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
                    update_bot_stats(bot_id, "outgoing")
                except: pass
            return

        # ЮЗЕР
        user = next((u for u in config.get("connectedUsers", []) if u["id"] == m.from_user.id), None)
        if not user or user.get("is_banned"): return

        # Кнопки
        if m.text:
            low = m.text.lower()
            for btn in config.get("buttons", []):
                if btn.get("text") and btn["text"].lower() == low:
                    if btn.get("type") == "request" and admin_id:
                        tid = None
                        if config.get("settings", {}).get("topicPerRequest") or config.get("settings", {}).get("useTopics"):
                            try:
                                t = await bot.create_forum_topic(admin_id, f"Ticket: {m.from_user.first_name} [{m.from_user.id}]")
                                tid = t.message_thread_id
                                user["thread_id"] = tid
                                save_db()
                                await bot.send_message(admin_id, f"👤 Новое обращение через кнопку: <b>{btn['text']}</b>\nID: <code>{m.from_user.id}</code>", message_thread_id=tid)
                            except Exception as e:
                                logger.error(f"Failed to create topic: {e}")
                        
                        txt = format_msg(btn.get("adminTemplate", ""), m, btn["text"])
                        await bot.send_message(admin_id, txt, message_thread_id=user.get("thread_id"))
                    
                    await m.answer(btn.get("response", "Принято"))
                    update_bot_stats(bot_id, "outgoing")
                    return

        # Feedback
        if admin_id:
            tid = user.get("thread_id")
            async def send_with_recovery(target_tid):
                try:
                    if not target_tid:
                        await bot.send_message(admin_id, f"📩 Сообщение от ID: {m.from_user.id}")
                    await bot.copy_message(admin_id, m.chat.id, m.message_id, message_thread_id=target_tid)
                    update_bot_stats(bot_id, "incoming")
                    return True
                except TelegramBadRequest as e:
                    if "message thread not found" in str(e).lower() or "thread_id" in str(e).lower():
                        return False
                    raise e

            success = await send_with_recovery(tid)
            if not success and (config.get("settings", {}).get("useTopics") or config.get("settings", {}).get("topicPerRequest")):
                try:
                    t = await bot.create_forum_topic(admin_id, f"{m.from_user.first_name} [{m.from_user.id}]")
                    user["thread_id"] = t.message_thread_id
                    save_db()
                    await bot.send_message(admin_id, f"👤 Диалог возобновлен\nID: <code>{m.from_user.id}</code>", message_thread_id=user["thread_id"])
                    await bot.copy_message(admin_id, m.chat.id, m.message_id, message_thread_id=user["thread_id"])
                    update_bot_stats(bot_id, "incoming")
                except Exception as e:
                    await bot.send_message(admin_id, f"📩 Сообщение от ID: {m.from_user.id}")
                    await bot.copy_message(admin_id, m.chat.id, m.message_id)

    dp.include_router(router)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await session.close()

# --- API ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_db()
    for b in db_content["bots"]:
        if b.get("status") == "RUNNING" and is_bot_license_active(b):
            active_tasks[b["id"]] = asyncio.create_task(bot_worker_task(b["id"], b["token"]))
    yield
    for t in active_tasks.values(): t.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/ping")
async def ping(): return {"status": "online"}

@app.post("/api/auth/register")
async def register(req: dict):
    if any(u["email"] == req["email"] for u in db_content["users"]): raise HTTPException(400)
    db_content["users"].append(req); save_db(); return req

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    u = next((u for u in db_content["users"] if u["email"] == req.email and u["password"] == req.password), None)
    if not u: raise HTTPException(401)
    return u

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    res = [b for b in db_content["bots"] if str(b["ownerId"]) == str(user_id)]
    for b in res: b["status"] = "RUNNING" if b["id"] in active_tasks and not active_tasks[b["id"]].done() else "IDLE"
    return res

@app.post("/api/bots/save")
async def save_bot(bot_data: dict):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == bot_data["id"]), -1)
    if idx >= 0:
        old = db_content["bots"][idx]
        threshold = bot_data.get("settings", {}).get("autoBanThreshold", 0)
        bot_instance = active_bots.get(bot_data["id"])
        
        if bot_instance:
            for new_u in bot_data.get("connectedUsers", []):
                old_u = next((u for u in old.get("connectedUsers", []) if u["id"] == new_u["id"]), None)
                if old_u:
                    # Изменились варны
                    if new_u.get("warns", 0) > old_u.get("warns", 0):
                        try:
                            txt = f"⚠️ <b>Вам выдано предупреждение!</b>\nВсего: {new_u['warns']}"
                            if threshold > 0: txt += f" / {threshold}"
                            asyncio.create_task(bot_instance.send_message(new_u["id"], txt))
                        except: pass
                    elif new_u.get("warns", 0) < old_u.get("warns", 0):
                        try: asyncio.create_task(bot_instance.send_message(new_u["id"], f"ℹ️ <b>С вас снято предупреждение.</b>\nОсталось: {new_u['warns']}"))
                        except: pass
                    
                    # Изменился статус бана
                    if new_u.get("is_banned") and not old_u.get("is_banned"):
                        try: asyncio.create_task(bot_instance.send_message(new_u["id"], "🚫 <b>Вы были заблокированы администратором.</b>"))
                        except: pass
                    elif not new_u.get("is_banned") and old_u.get("is_banned"):
                        try: asyncio.create_task(bot_instance.send_message(new_u["id"], "✅ <b>Вы были разблокированы администратором!</b>"))
                        except: pass

        db_content["bots"][idx] = bot_data
    else: db_content["bots"].append(bot_data)
    save_db(); return {"status": "ok"}

@app.delete("/api/bots/delete/{bot_id}")
async def delete_bot(bot_id: str):
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel(); del active_tasks[bot_id]
    db_content["bots"] = [b for b in db_content["bots"] if b["id"] != bot_id]
    save_db(); return {"status": "ok"}

@app.post("/api/bots/start/{bot_id}")
async def start_bot(bot_id: str):
    cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not cfg: raise HTTPException(404)
    if not is_bot_license_active(cfg): raise HTTPException(403)
    if bot_id in active_tasks and not active_tasks[bot_id].done(): return {"status": "ok"}
    active_tasks[bot_id] = asyncio.create_task(bot_worker_task(bot_id, cfg["token"]))
    cfg["status"] = "RUNNING"; save_db(); return {"status": "ok"}

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel(); del active_tasks[bot_id]
    if bot_id in active_bots: del active_bots[bot_id]
    for b in db_content["bots"]:
        if b["id"] == bot_id: b["status"] = "IDLE"
    save_db(); return {"status": "ok"}

@app.post("/api/broadcast")
async def broadcast(req: BroadcastRequest):
    results = {"success": 0, "failed": 0}
    for bot_id in req.botIds:
        bot_instance = active_bots.get(bot_id)
        config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        
        if not bot_instance or not config:
            continue
            
        # Рассылаем всем подписчикам (те, кто нажал /start)
        subscribers = config.get("subscribers", [])
        for user_id in subscribers:
            try:
                await bot_instance.send_message(user_id, req.message)
                results["success"] += 1
                update_bot_stats(bot_id, "outgoing")
            except Exception as e:
                logger.error(f"Broadcast failed for user {user_id} on bot {bot_id}: {e}")
                results["failed"] += 1
                
    return results

@app.post("/api/license/activate")
async def activate(req: ActivateRequest):
    bot_cfg = next((b for b in db_content["bots"] if b["id"] == req.botId), None)
    key_obj = next((k for k in db_content["issued_keys"] if k["key"] == req.key and not k["used"]), None)
    if not bot_cfg or not key_obj: raise HTTPException(400)
    now = int(time.time() * 1000)
    exp = max(bot_cfg.get("licenseExpiresAt", now), now)
    bot_cfg["licenseExpiresAt"] = exp + (key_obj["months"] * 30 * 24 * 3600 * 1000)
    key_obj["used"] = True; save_db(); return {"status": "ok", "newExpiry": bot_cfg["licenseExpiresAt"]}

@app.post("/api/admin/generate-key")
async def gen_key(req: KeyGenRequest, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET: raise HTTPException(403)
    k = f"BOT-{req.months}-{secrets.token_hex(3).upper()}"
    db_content["issued_keys"].append({"key": k, "months": req.months, "used": False, "created_at": int(time.time())})
    save_db(); return {"key": k}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
