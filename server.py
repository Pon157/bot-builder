
import asyncio
import logging
import json
import os
import time
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, Message
from aiogram.exceptions import TelegramForbiddenError, TelegramConflictError
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
import uvicorn

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BotEngine")

DB_FILE = "database.json"
db_content = {"users": [], "bots": []}
active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}

class BroadcastModel(BaseModel):
    botIds: List[str]
    message: str

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db_content, f, ensure_ascii=False, indent=2)
    except Exception as e: logger.error(f"Save DB Error: {e}")

def load_db():
    global db_content
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                db_content = json.load(f)
                # Ensure structure exists for all bots
                for bot in db_content.get("bots", []):
                    if "stats" not in bot:
                        bot["stats"] = {"totalMessages": 0, "incomingToday": 0, "outgoingToday": 0, "bannedCount": 0, "history": [], "activeUsers24h": 0}
                    if "logs" not in bot:
                        bot["logs"] = []
                    if "connectedUsers" not in bot:
                        bot["connectedUsers"] = []
        except Exception as e: logger.error(f"Load DB Error: {e}")

def add_bot_log(bot_id: str, log_type: str, text: str):
    bot = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not bot: return
    
    log_entry = {
        "id": str(time.time()),
        "timestamp": int(time.time() * 1000),
        "type": log_type,
        "text": text
    }
    bot["logs"].insert(0, log_entry)
    bot["logs"] = bot["logs"][:100] # Limit to 100 logs
    save_db()

def update_bot_stats(bot_id: str, stat_type: str, user_id: Optional[int] = None):
    bot = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not bot: return
    
    if "stats" not in bot:
        bot["stats"] = {"totalMessages": 0, "incomingToday": 0, "outgoingToday": 0, "bannedCount": 0, "history": [], "activeUsers24h": 0}
    
    bot["stats"]["totalMessages"] += 1
    today = datetime.now().strftime("%Y-%m-%d")
    
    if stat_type == "incoming": bot["stats"]["incomingToday"] += 1
    else: bot["stats"]["outgoingToday"] += 1
    
    # Update active users 24h
    now = time.time()
    one_day_ago = now - 86400
    
    # Update last_seen for the user if provided
    if user_id:
        user = next((u for u in bot["connectedUsers"] if u["id"] == user_id), None)
        if user:
            user["last_seen"] = now
            user["is_active"] = True # If they sent a message, they are active

    # Recalculate active users in 24h
    active_count = sum(1 for u in bot["connectedUsers"] if u.get("last_seen", 0) > one_day_ago)
    bot["stats"]["activeUsers24h"] = active_count
    bot["stats"]["bannedCount"] = sum(1 for u in bot["connectedUsers"] if u.get("is_banned", False))

    # Update history for charts
    history = bot["stats"].get("history", [])
    day_stat = next((h for h in history if h["date"] == today), None)
    if not day_stat:
        day_stat = {"date": today, "incoming": 0, "outgoing": 0}
        history.append(day_stat)
    
    day_stat[stat_type] += 1
    bot["stats"]["history"] = history[-7:] # Keep last 7 days
    save_db()

async def bot_worker(bot_id: str, token: str):
    session = AiohttpSession()
    bot = Bot(token=token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    active_bots[bot_id] = bot
    dp = Dispatcher()
    router = Router()

    @router.message(CommandStart())
    async def cmd_start(m: Message):
        config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not config: return
        
        user = next((u for u in config["connectedUsers"] if u["id"] == m.from_user.id), None)
        if not user:
            user = {
                "id": m.from_user.id, 
                "first_name": m.from_user.first_name, 
                "username": m.from_user.username, 
                "joined_at": int(time.time()), 
                "last_seen": int(time.time()),
                "is_banned": False, 
                "is_active": True
            }
            config["connectedUsers"].append(user)
            config["usersCount"] = len(config["connectedUsers"])
            add_bot_log(bot_id, "system", f"New user: {m.from_user.full_name} ({m.from_user.id})")
        else:
            user["last_seen"] = int(time.time())
            user["is_active"] = True
            
        save_db()
        if user["is_banned"]: return
        
        kb = None
        if config.get("buttons"):
            rows = [config["buttons"][i:i+2] for i in range(0, len(config["buttons"]), 2)]
            kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=b["text"]) for b in row] for row in rows], resize_keyboard=True)
        
        await m.answer(config.get("welcomeMessage", "Welcome!"), reply_markup=kb)

    @router.message(Command("ban"))
    async def cmd_ban(m: Message):
        config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if str(m.chat.id) != str(config.get("adminChatId")): return
        
        parts = m.text.split()
        if len(parts) < 2: return await m.reply("Usage: /ban {user_id}")
        
        try:
            uid = int(parts[1])
            user = next((u for u in config["connectedUsers"] if u["id"] == uid), None)
            if user:
                user["is_banned"] = True
                config["stats"]["bannedCount"] = sum(1 for u in config["connectedUsers"] if u["is_banned"])
                add_bot_log(bot_id, "info", f"User {uid} banned by admin.")
                save_db()
                await m.reply(f"User {uid} has been banned.")
            else:
                await m.reply("User not found in bot database.")
        except ValueError:
            await m.reply("Invalid User ID.")

    @router.message()
    async def handle_msg(m: Message):
        config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not config: return
        
        admin_id = config.get("adminChatId")
        is_admin = str(m.chat.id) == str(admin_id)

        # Reply from Admin to User
        if is_admin and m.reply_to_message:
            target_id_match = re.search(r"ID: (\d+)", m.reply_to_message.text or m.reply_to_message.caption or "")
            if target_id_match:
                target_id = int(target_id_match.group(1))
                try:
                    await bot.copy_message(chat_id=target_id, from_chat_id=m.chat.id, message_id=m.message_id)
                    update_bot_stats(bot_id, "outgoing")
                    add_bot_log(bot_id, "outgoing", f"Admin replied to {target_id}")
                except TelegramForbiddenError:
                    user = next((u for u in config["connectedUsers"] if u["id"] == target_id), None)
                    if user: user["is_active"] = False
                    add_bot_log(bot_id, "error", f"User {target_id} has blocked the bot.")
                    await m.reply("User blocked the bot.")
                except Exception as e:
                    await m.reply(f"Error: {e}")
            return

        # From User to Admin
        user = next((u for u in config["connectedUsers"] if u["id"] == m.from_user.id), None)
        if user:
            if user["is_banned"]: return
            user["last_seen"] = int(time.time())
            user["is_active"] = True

        if not is_admin and admin_id:
            # Custom Triggers / Buttons Logic
            msg_text = m.text.lower() if m.text else ""
            for btn in config.get("buttons", []):
                if btn["text"].lower() == msg_text:
                    update_bot_stats(bot_id, "incoming", m.from_user.id)
                    return await m.answer(btn["response"])
            
            for trig in config.get("triggers", []):
                if trig["keyword"].lower() in msg_text:
                    update_bot_stats(bot_id, "incoming", m.from_user.id)
                    return await m.answer(trig["response"])

            # Forward to Admin
            info = f"<b>Message from:</b> {m.from_user.full_name}\n<b>ID:</b> <code>{m.from_user.id}</code>\n"
            if m.from_user.username: info += f"<b>User:</b> @{m.from_user.username}\n"
            info += "—" * 10
            
            try:
                await bot.send_message(admin_id, info)
                await bot.copy_message(chat_id=admin_id, from_chat_id=m.chat.id, message_id=m.message_id)
                update_bot_stats(bot_id, "incoming", m.from_user.id)
                add_bot_log(bot_id, "incoming", f"Message from {m.from_user.id} forwarded.")
            except Exception as e: 
                logger.error(f"Forward error: {e}")
                add_bot_log(bot_id, "error", f"Failed to forward message from {m.from_user.id}: {e}")

    dp.include_router(router)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        me = await bot.get_me()
        add_bot_log(bot_id, "info", f"Bot @{me.username} started successfully.")
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e: 
        logger.error(f"Bot {bot_id} Error: {e}")
        add_bot_log(bot_id, "error", f"Bot crash: {e}")
    finally: await session.close()

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/ping")
async def ping(): return {"status": "online"}

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    load_db()
    return [b for b in db_content["bots"] if b["ownerId"] == user_id]

@app.post("/api/bots/save")
async def save_bot_endpoint(bot_data: dict):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == bot_data["id"]), -1)
    if idx >= 0:
        # Preserve critical runtime data
        bot_data["connectedUsers"] = db_content["bots"][idx].get("connectedUsers", [])
        bot_data["stats"] = db_content["bots"][idx].get("stats", bot_data.get("stats"))
        bot_data["logs"] = db_content["bots"][idx].get("logs", bot_data.get("logs"))
        db_content["bots"][idx] = bot_data
    else:
        db_content["bots"].append(bot_data)
    save_db()
    return {"status": "ok"}

@app.post("/api/bots/start/{bot_id}")
async def start_bot(bot_id: str):
    bot_cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not bot_cfg: raise HTTPException(404, "Bot not found")
    if bot_id in active_tasks: return {"status": "ok"}
    active_tasks[bot_id] = asyncio.create_task(bot_worker(bot_id, bot_cfg["token"]))
    bot_cfg["status"] = "RUNNING"
    save_db()
    return {"status": "ok"}

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel()
        del active_tasks[bot_id]
    if bot_id in active_bots:
        del active_bots[bot_id]
    for b in db_content["bots"]:
        if b["id"] == bot_id: b["status"] = "IDLE"
    save_db()
    return {"status": "ok"}

@app.post("/api/broadcast")
async def broadcast(data: BroadcastModel):
    total_sent = 0
    total_errors = 0
    for bid in data.botIds:
        bot = active_bots.get(bid)
        config = next((b for b in db_content["bots"] if b["id"] == bid), None)
        if not bot or not config: continue
        
        for user in config["connectedUsers"]:
            if user["is_banned"] or not user["is_active"]: continue
            try:
                await bot.send_message(user["id"], data.message)
                total_sent += 1
                await asyncio.sleep(0.05)
            except TelegramForbiddenError:
                user["is_active"] = False
                total_errors += 1
            except Exception: total_errors += 1
    save_db()
    return {"success": total_sent, "failed": total_errors}

if __name__ == "__main__":
    load_db()
    uvicorn.run(app, host="0.0.0.0", port=8000)
