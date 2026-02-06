
import os
import asyncio
import logging
import sys
import requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, CallbackQuery, Message

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("LicenseBot")

def load_config():
    # Проверяем текущую папку и папку скрипта
    search_paths = [
        os.getcwd(),
        os.path.dirname(os.path.abspath(__file__))
    ]
    
    conf = {}
    for p in search_paths:
        path = os.path.join(p, '.env')
        if os.path.exists(path):
            logger.info(f"🔍 Нашел .env в: {path}")
            with open(path, 'r', encoding='utf-8-sig') as f:
                for line in f:
                    line = line.strip()
                    if line and '=' in line and not line.startswith('#'):
                        k, v = line.split('=', 1)
                        val = v.strip().strip('"').strip("'")
                        conf[k.strip()] = val
            return conf
    return conf

CONFIG = load_config()
TOKEN = CONFIG.get("ADMIN_BOT_TOKEN")
ADMIN_SECRET = CONFIG.get("ADMIN_SECRET", "MRAKOTIK")
ADMIN_CHAT_ID = CONFIG.get("ADMIN_CHAT_ID") 
# Исправляем URL для запросов к серверу
SERVER_URL = "http://127.0.0.1:8000"

if not TOKEN or "123456" in TOKEN:
    logger.critical(f"🛑 ADMIN_BOT_TOKEN не найден! Путь запуска: {os.getcwd()}")
    sys.exit(1)

async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()

    @dp.message(Command("start"))
    async def cmd_start(m: Message):
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="🔑 1 Месяц (50 ⭐)", callback_data="buy_1"))
        kb.row(InlineKeyboardButton(text="🔑 3 Месяца (120 ⭐)", callback_data="buy_3"))
        kb.row(InlineKeyboardButton(text="💎 1 Год (400 ⭐)", callback_data="buy_12"))
        
        await m.answer(
            "🚀 <b>BotEngine Pro: Магазин лицензий</b>\n\n"
            "Выберите период подписки для получения ключа.\n"
            "После выбора вы получите ссылку на оплату.",
            reply_markup=kb.as_markup(), 
            parse_mode="HTML"
        )

    # ... (остальной код хендлеров остается прежним)

    logger.info("✨ Бот лицензий запущен и готов к работе")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
