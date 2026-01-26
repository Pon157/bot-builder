
import asyncio
import logging
import json
import os
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
import uvicorn

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_FILE = "database.json"

app = FastAPI(title="BotEngine Pro API")

# Разрешаем CORS для фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Хранилище в памяти
bot_configs: List[dict] = []
active_tasks: Dict[str, asyncio.Task] = {}

class BotConfigModel(BaseModel):
    id: str
    ownerId: str
    name: str
    token: str
    status: str
    welcomeMessage: str
    triggers: List[dict]
    buttons: List[dict]
    adminChatId: Optional[str] = ""

def save_db():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(bot_configs, f, ensure_ascii=False, indent=2)

def load_db():
    global bot_configs
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            bot_configs = json.load(f)

async def bot_worker(config_id: str):
    config = next((b for b in bot_configs if b["id"] == config_id), None)
    if not config: return

    bot = Bot(token=config["token"], parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    router = Router()

    @router.message(CommandStart())
    async def cmd_start(message: types.Message):
        kb = []
        if config.get("buttons"):
            row = []
            for btn in config["buttons"]:
                row.append(types.KeyboardButton(text=btn['text']))
                if len(row) == 2:
                    kb.append(row); row = []
            if row: kb.append(row)
        
        reply_markup = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True) if kb else None
        await message.answer(config["welcomeMessage"], reply_markup=reply_markup)

    @router.message()
    async def handle_all(message: types.Message):
        text = (message.text or "").lower()
        for trig in config.get("triggers", []):
            if trig['keyword'].lower() in text:
                await message.answer(trig['response'])
                return
        for btn in config.get("buttons", []):
            if btn['text'].lower() == text:
                await message.answer(btn['response'])
                return

    dp.include_router(router)
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Error in bot {config_id}: {e}")
    finally:
        await bot.session.close()

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    return [b for b in bot_configs if b["ownerId"] == user_id]

@app.post("/api/bots/save")
async def save_bot(bot: BotConfigModel):
    global bot_configs
    idx = next((i for i, b in enumerate(bot_configs) if b["id"] == bot.id), -1)
    if idx >= 0:
        bot_configs[idx] = bot.dict()
    else:
        bot_configs.append(bot.dict())
    save_db()
    return {"status": "ok"}

@app.delete("/api/bots/{bot_id}")
async def delete_bot(bot_id: str):
    global bot_configs
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel()
        del active_tasks[bot_id]
    bot_configs = [b for b in bot_configs if b["id"] != bot_id]
    save_db()
    return {"status": "deleted"}

@app.post("/api/bots/start/{bot_id}")
async def start_bot(bot_id: str):
    if bot_id in active_tasks:
        return {"status": "already_running"}
    
    config = next((b for b in bot_configs if b["id"] == bot_id), None)
    if not config: raise HTTPException(status_code=404)

    task = asyncio.create_task(bot_worker(bot_id))
    active_tasks[bot_id] = task
    
    # Обновляем статус в базе
    for b in bot_configs:
        if b["id"] == bot_id: b["status"] = "RUNNING"
    save_db()
    
    return {"status": "started"}

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel()
        del active_tasks[bot_id]
    
    for b in bot_configs:
        if b["id"] == bot_id: b["status"] = "IDLE"
    save_db()
    
    return {"status": "stopped"}

@app.on_event("startup")
async def startup_event():
    load_db()
    # Автозапуск ботов, которые должны работать
    for b in bot_configs:
        if b.get("status") == "RUNNING":
            active_tasks[b["id"]] = asyncio.create_task(bot_worker(b["id"]))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
