
import asyncio
import logging
from typing import Dict, List
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
import uvicorn

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="BotEngine Cloud API")

# Хранилище активных инстансов в памяти (в продакшене дополняется БД)
active_bots: Dict[str, Dict] = {}

class BotConfig(BaseModel):
    id: str
    token: str
    name: str
    welcome_message: str
    triggers: List[dict]
    buttons: List[dict]

class BroadcastRequest(BaseModel):
    bot_ids: List[str]
    message: string

async def bot_worker(config: BotConfig):
    """Функция-воркер для отдельного бота"""
    bot = Bot(token=config.token, parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    router = Router()

    @router.message(CommandStart())
    async def cmd_start(message: types.Message):
        # Формирование клавиатуры из настроек
        kb = []
        if config.buttons:
            row = []
            for btn in config.buttons:
                row.append(types.KeyboardButton(text=btn['text']))
                if len(row) == 2:
                    kb.append(row)
                    row = []
            if row: kb.append(row)
        
        reply_markup = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True) if kb else None
        await message.answer(config.welcome_message, reply_markup=reply_markup)

    @router.message()
    async def handle_all(message: types.Message):
        text = (message.text or "").lower()
        # Проверка триггеров
        for trig in config.triggers:
            if trig['keyword'].lower() in text:
                await message.answer(trig['response'])
                return
        # Проверка кнопок
        for btn in config.buttons:
            if btn['text'].lower() == text:
                await message.answer(btn['response'])
                return

    dp.include_router(router)
    try:
        logger.info(f"Starting bot: {config.name}")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Error in bot {config.name}: {e}")
    finally:
        await bot.session.close()

@app.post("/api/bots/start")
async def start_bot(config: BotConfig, background_tasks: BackgroundTasks):
    if config.id in active_bots:
        raise HTTPException(status_code=400, detail="Bot already running")
    
    # Запуск бота в фоновом процессе сервера
    loop = asyncio.get_event_loop()
    task = loop.create_task(bot_worker(config))
    active_bots[config.id] = {"task": task, "config": config}
    return {"status": "started", "bot_id": config.id}

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    if bot_id not in active_bots:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    active_bots[bot_id]["task"].cancel()
    del active_bots[bot_id]
    return {"status": "stopped"}

@app.get("/api/bots/status")
async def get_statuses():
    return {bid: "RUNNING" for bid in active_bots}

if __name__ == "__main__":
    # Запуск API сервера
    uvicorn.run(app, host="0.0.0.0", port=8000)
