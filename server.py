
import asyncio
import logging
import json
import os
import time
import re
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, Message
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
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

def add_bot_log(bot_id: str, log_type: str, text: str, code: str = None):
    bot = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not bot: return
    log_entry = {"id": str(time.time()), "timestamp": int(time.time() * 1000), "type": log_type, "text": text, "code": code}
    bot["logs"].insert(0, log_entry)
    bot["logs"] = bot["logs"][:100]
    save_db()

def update_bot_stats(bot_id: str, stat_type: str):
    bot = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not bot: return
    if "stats" not in bot: bot["stats"] = {"totalMessages": 0, "incomingToday": 0, "outgoingToday": 0, "bannedCount": 0, "history": []}
    bot["stats"]["totalMessages"] += 1
    today = datetime.now().strftime("%Y-%m-%d")
    if stat_type == "incoming": bot["stats"]["incomingToday"] += 1
    else: bot["stats"]["outgoingToday"] += 1
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
            user = {"id": m.from_user.id, "first_name": m.from_user.first_name, "username": m.from_user.username, "joined_at": int(time.time()), "is_banned": False, "is_active": True, "warns": 0}
            config["connectedUsers"].append(user)
            config["usersCount"] = len(config["connectedUsers"])
            add_bot_log(bot_id, "system", f"New user: {m.from_user.full_name}")
            save_db()
        if user["is_banned"]: return
        await m.answer(config.get("welcomeMessage", "Welcome!"))

    @router.message(Command("ban", "unban", "warn", "unwarn"))
    async def admin_moderation(m: Message):
        config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if str(m.chat.id) != str(config.get("adminChatId")): return
        
        target_id = None
        if m.reply_to_message:
            match = re.search(r"ID: (\d+)", m.reply_to_message.text or m.reply_to_message.caption or "")
            if match: target_id = int(match.group(1))
        
        if not target_id:
            parts = m.text.split()
            if len(parts) > 1: target_id = int(parts[1])
            
        if not target_id: return await m.reply("Reply to user message or provide ID.")
        
        user = next((u for u in config["connectedUsers"] if u["id"] == target_id), None)
        if not user: return await m.reply("User not found.")
        
        cmd = m.text.split()[0].replace("/", "")
        if cmd == "ban": 
            user["is_banned"] = True
            await m.reply(f"User {target_id} banned.")
        elif cmd == "unban": 
            user["is_banned"] = False
            await m.reply(f"User {target_id} unbanned.")
        elif cmd == "warn": 
            user["warns"] = user.get("warns", 0) + 1
            await m.reply(f"User {target_id} warned ({user['warns']}).")
        elif cmd == "unwarn": 
            user["warns"] = max(0, user.get("warns", 0) - 1)
            await m.reply(f"User {target_id} unwarned ({user['warns']}).")
        
        save_db()

    @router.message()
    async def handle_msg(m: Message):
        config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not config: return
        admin_id = config.get("adminChatId")
        if not admin_id: return

        # Reply from Admin
        if str(m.chat.id) == str(admin_id) and m.reply_to_message:
            target_id_match = re.search(r"ID: (\d+)", m.reply_to_message.text or m.reply_to_message.caption or "")
            if target_id_match:
                target_id = int(target_id_match.group(1))
                try:
                    await bot.copy_message(chat_id=target_id, from_chat_id=m.chat.id, message_id=m.message_id)
                    update_bot_stats(bot_id, "outgoing")
                except TelegramForbiddenError:
                    add_bot_log(bot_id, "error", f"User {target_id} blocked the bot.")
                except Exception as e:
                    await m.reply(f"Error: {e}")
            return

        # From User to Admin
        user = next((u for u in config["connectedUsers"] if u["id"] == m.from_user.id), None)
        if not user: return # Should not happen due to cmd_start but just in case
        if user["is_banned"]: return

        use_topics = config.get("settings", {}).get("useTopics", False)
        
        if use_topics:
            if not user.get("thread_id"):
                try:
                    topic = await bot.create_forum_topic(admin_id, f"{m.from_user.first_name} ({m.from_user.id})")
                    user["thread_id"] = topic.message_thread_id
                    save_db()
                    
                    # First info message
                    info = f"👤 <b>New Client</b>\nID: <code>{m.from_user.id}</code>\n"
                    if config["settings"].get("showUsername") and m.from_user.username:
                        info += f"User: @{m.from_user.username}\n"
                    info += f"Name: {m.from_user.full_name}\n"
                    info += "—" * 10
                    await bot.send_message(admin_id, info, message_thread_id=user["thread_id"])
                except TelegramBadRequest as e:
                    if "forum is disabled" in str(e).lower():
                        add_bot_log(bot_id, "error", "Topic creation failed: Forum is disabled in admin chat.", "TOPIC_ERROR")
                        use_topics = False # Fallback to regular forwarding
                    else: raise e
            
            try:
                await bot.copy_message(admin_id, m.chat.id, m.message_id, message_thread_id=user.get("thread_id"))
                update_bot_stats(bot_id, "incoming")
            except Exception as e:
                add_bot_log(bot_id, "error", f"Forward error: {e}")
        else:
            # Regular forwarding without extra info to allow direct reply
            info = f"<b>Message from:</b> <code>{m.from_user.id}</code>\n—\n"
            try:
                await bot.send_message(admin_id, info)
                await bot.copy_message(admin_id, m.chat.id, m.message_id)
                update_bot_stats(bot_id, "incoming")
            except Exception as e:
                add_bot_log(bot_id, "error", f"Forward error: {e}")

    dp.include_router(router)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        add_bot_log(bot_id, "error", f"Bot stopped: {e}")
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
        # Keep runtime fields
        bot_data["connectedUsers"] = db_content["bots"][idx].get("connectedUsers", [])
        bot_data["logs"] = db_content["bots"][idx].get("logs", [])
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

if __name__ == "__main__":
    load_db()
    uvicorn.run(app, host="0.0.0.0", port=8000)
