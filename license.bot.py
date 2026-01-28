
import os
import asyncio
import logging
import sys
import requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, CallbackQuery, Message

BASE_DIR = "/root/bot-builder/bot-builder"
if os.path.exists(BASE_DIR):
    os.chdir(BASE_DIR)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', stream=sys.stdout)
logger = logging.getLogger("LicenseBot")

def load_config_direct():
    """Прямое чтение .env без посредников"""
    path = os.path.join(BASE_DIR, '.env')
    conf = {}
    if os.path.exists(path):
        logger.info(f"🔎 Чтение файла: {path}")
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                for line in f:
                    line = line.strip()
                    if line and '=' in line and not line.startswith('#'):
                        k, v = line.split('=', 1)
                        key = k.strip()
                        val = v.strip().strip('"').strip("'")
                        # Очистка токена от мусора
                        if key == "ADMIN_BOT_TOKEN":
                             if "root/" in val: val = val.split("root/")[0].strip()
                        conf[key] = val
        except Exception as e: logger.error(f"Ошибка .env: {e}")
    
    # Резерв из окружения
    if not conf.get("ADMIN_BOT_TOKEN"):
        conf["ADMIN_BOT_TOKEN"] = os.getenv("ADMIN_BOT_TOKEN")
        
    return conf

CONF = load_config_direct()
TOKEN = CONF.get("ADMIN_BOT_TOKEN")
ADMIN_SECRET = CONF.get("ADMIN_SECRET", "MRAKOTIK")
SERVER_URL = CONF.get("SERVER_URL", "http://localhost:8000")

if not TOKEN or not isinstance(TOKEN, str) or len(TOKEN) < 20:
    logger.critical(f"🛑 КРИТИЧЕСКАЯ ОШИБКА: Токен не найден или пустой! (ADMIN_BOT_TOKEN={repr(TOKEN)})")
    print("\n--- ДИАГНОСТИКА ---")
    print(f"Путь: {os.getcwd()}")
    print(f"Файлы: {os.listdir('.')}")
    if os.path.exists('.env'):
        with open('.env', 'r') as f: print(f"Содержимое .env:\n{f.read()}")
    sys.exit(1)

logger.info(f"✅ Токен загружен успешно (длина {len(TOKEN)})")

async def main():
    try:
        bot = Bot(token=TOKEN)
        dp = Dispatcher()
        
        @dp.message(Command("start"))
        async def cmd_start(m: Message):
            kb = InlineKeyboardBuilder()
            kb.row(InlineKeyboardButton(text="🔑 1 Месяц", callback_data="buy_1"))
            kb.row(InlineKeyboardButton(text="🔑 3 Месяца", callback_data="buy_3"))
            kb.row(InlineKeyboardButton(text="💎 1 Год", callback_data="buy_12"))
            await m.answer("👋 <b>Панель лицензий</b>\nВыберите тариф:", reply_markup=kb.as_markup(), parse_mode="HTML")

        @dp.callback_query(F.data.startswith("buy_"))
        async def handle_buy(cb: CallbackQuery):
            months = int(cb.data.split("_")[1])
            await cb.message.edit_text("⏳ Генерирую...")
            try:
                r = requests.post(f"{SERVER_URL}/api/admin/generate-key", 
                                 json={"months": months}, 
                                 headers={"x-admin-token": ADMIN_SECRET}, timeout=5)
                key = r.json().get("key", "Error")
                await cb.message.edit_text(f"✅ Ключ на {months} мес:\n\n<code>{key}</code>", parse_mode="HTML")
            except Exception as e:
                await cb.message.edit_text(f"❌ Ошибка API: {e}")

        logger.info("✨ Бот лицензий запущен!")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")

if __name__ == "__main__":
    asyncio.run(main())
