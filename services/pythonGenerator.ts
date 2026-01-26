
import { BotConfig } from '../types';

export const generatePythonCode = (config: BotConfig): string => {
  const welcomeText = config.welcomeMessage.replace(/"/g, '\\"');
  const triggersJson = JSON.stringify(config.triggers || []);
  const buttonsJson = JSON.stringify(config.buttons || []);
  const antiSpamEnabled = config.antiSpam?.enabled || false;
  const rateLimit = config.antiSpam?.rateLimit || 10;
  
  return `#!/usr/bin/env python3
import asyncio
import logging
import sys
import json
import aiosqlite
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

# --- CONFIGURATION ---
TOKEN = "${config.token}"
ADMIN_ID = ${config.adminChatId || 0}
DB_PATH = "bot_database.db"
TRIGGERS = ${triggersJson}
BUTTONS = ${buttonsJson}
ANTISPAM_ENABLED = ${antiSpamEnabled}
RATE_LIMIT = ${rateLimit}

# Internal state for anti-spam
user_message_times = {}

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("BotEngine")

bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
router = Router()

# --- UTILS ---
def get_keyboard():
    if not BUTTONS:
        return None
    keyboard = []
    row = []
    for i, btn in enumerate(BUTTONS):
        row.append(KeyboardButton(text=btn['text']))
        if (i + 1) % 2 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

# --- DATABASE LAYER ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                joined_at DATETIME
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                text TEXT,
                is_incoming BOOLEAN,
                timestamp DATETIME
            )
        """)
        await db.commit()
        logger.info("Database initialized.")

async def register_user(user_id, username, full_name):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, full_name, joined_at) VALUES (?, ?, ?, ?)",
            (user_id, username, full_name, datetime.now())
        )
        await db.commit()

async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            return [row[0] for row in await cursor.fetchall()]

# --- MIDDLEWARE-LIKE ANTISPAM ---
def is_spamming(user_id):
    if not ANTISPAM_ENABLED: return False
    now = datetime.now()
    if user_id not in user_message_times:
        user_message_times[user_id] = []
    
    # Filter only messages within the last minute
    user_message_times[user_id] = [t for t in user_message_times[user_id] if t > now - timedelta(minutes=1)]
    
    if len(user_message_times[user_id]) >= RATE_LIMIT:
        return True
    
    user_message_times[user_id].append(now)
    return False

# --- HANDLERS ---
@router.message(CommandStart())
async def cmd_start(message: Message):
    await register_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    kb = get_keyboard()
    await message.answer("${welcomeText}", reply_markup=kb)
    if ADMIN_ID != 0 and message.from_user.id != ADMIN_ID:
        try:
            await bot.send_message(ADMIN_ID, f"👤 New user: {message.from_user.full_name} (@{message.from_user.username})")
        except: pass

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if ADMIN_ID != 0 and message.from_user.id != ADMIN_ID: return
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        return await message.answer("Usage: <code>/broadcast Your message</code>")
    
    users = await get_all_users()
    count = 0
    msg_status = await message.answer(f"🚀 Sending to {len(users)} users...")
    
    for uid in users:
        try:
            await bot.send_message(uid, text)
            count += 1
            await asyncio.sleep(0.05)
        except (TelegramForbiddenError, Exception): continue
    
    await msg_status.edit_text(f"✅ Broadcast finished. Sent to {count} users.")

@router.message()
async def main_handler(message: Message):
    if is_spamming(message.from_user.id):
        return logger.info(f"Ignored spam from {message.from_user.id}")

    await register_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    
    # Check Triggers
    msg_text = (message.text or "").lower()
    for trigger in TRIGGERS:
        if trigger['keyword'].lower() in msg_text:
            return await message.answer(trigger['response'])
            
    # Check Buttons
    for btn in BUTTONS:
        if btn['text'].lower() == msg_text:
            return await message.answer(btn['response'])

    # Support Relay (if enabled and not admin)
    if ADMIN_ID != 0 and message.from_user.id != ADMIN_ID:
        header = f"<b>Message from {message.from_user.full_name}</b> (ID: <code>{message.from_user.id}</code>)\\n\\n"
        await bot.send_message(ADMIN_ID, header + (message.text or "[Non-text message]"))

    # Admin Reply Logic
    if ADMIN_ID != 0 and message.from_user.id == ADMIN_ID and message.reply_to_message:
        try:
            target_text = message.reply_to_message.text or ""
            if "ID: " in target_text:
                target_id = int(target_text.split("ID: ")[1].split("\\n")[0].strip())
                await bot.send_message(target_id, message.text)
                await message.reply("✅ Sent.")
        except Exception as e:
            await message.reply(f"❌ Failed to reply: {e}")

# --- BOOTSTRAP ---
async function main():
    await init_db()
    dp.include_router(router)
    logger.info("Service Online")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Service Offline")
`;
};
