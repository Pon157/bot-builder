
import asyncio
import logging
import json
import os
import time
import re
from datetime import datetime
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
        except Exception as e: logger.error(f"Load DB Error: {e}")

def update_bot_stats(bot_id: str, stat_type: str):
    bot = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not bot: return
    
    if "stats" not in bot:
        bot["stats"] = {"totalMessages": 0, "incomingToday": 0, "outgoingToday": 0, "bannedCount": 0, "history": []}
    
    bot["stats"]["totalMessages"] += 1
    today = datetime.now().strftime("%Y-%m-%d")
    
    if stat_type == "incoming": bot["stats"]["incomingToday"] += 1
    else: bot["stats"]["outgoingToday"] += 1
    
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
            user = {"id": m.from_user.id, "first_name": m.from_user.first_name, "username": m.from_user.username, "joined_at": int(time.time()), "is_banned": False, "is_active": True}
            config["connectedUsers"].append(user)
            config["usersCount"] = len(config["connectedUsers"])
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
        
        uid = int(parts[1])
        user = next((u for u in config["connectedUsers"] if u["id"] == uid), None)
        if user:
            user["is_banned"] = True
            config["stats"]["bannedCount"] = sum(1 for u in config["connectedUsers"] if u["is_banned"])
            save_db()
            await m.reply(f"User {uid} has been banned.")

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
                except TelegramForbiddenError:
                    await m.reply("User blocked the bot.")
                except Exception as e:
                    await m.reply(f"Error: {e}")
            return

        # From User to Admin
        user = next((u for u in config["connectedUsers"] if u["id"] == m.from_user.id), None)
        if user and user["is_banned"]: return

        if not is_admin and admin_id:
            info = f"<b>Message from:</b> {m.from_user.full_name}\n<b>ID:</b> <code>{m.from_user.id}</code>\n"
            if m.from_user.username: info += f"<b>User:</b> @{m.from_user.username}\n"
            info += "—" * 10
            
            try:
                await bot.send_message(admin_id, info)
                await bot.copy_message(chat_id=admin_id, from_chat_id=m.chat.id, message_id=m.message_id)
                update_bot_stats(bot_id, "incoming")
            except Exception as e: logger.error(f"Forward error: {e}")

    dp.include_router(router)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e: logger.error(f"Bot {bot_id} Error: {e}")
    finally: await session.close()

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/ping")
async def ping(): return {"status": "online"}

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    load_db()
    return [b for b in db_content["bots"] if b["ownerId"] == user_id]

@app.post("/api/bots/start/{bot_id}")
async def start_bot(bot_id: str):
    bot_cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
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
