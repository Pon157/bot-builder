
import os
import asyncio
import logging
import sys
import requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, CallbackQuery, Message

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)
logger = logging.getLogger("LicenseBot")

def load_config():
    """Принудительное чтение файла .env"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(script_dir, '.env')
    if not os.path.exists(p):
        p = '/root/bot-builder/bot-builder/.env'
    
    config = {}
    if os.path.exists(p):
        try:
            with open(p, 'r', encoding='utf-8-sig') as f:
                for line in f:
                    line = line.strip()
                    if line and '=' in line and not line.startswith('#'):
                        k, v = line.split('=', 1)
                        val = v.strip().strip('"').strip("'")
                        if "root/" in val and k == "ADMIN_BOT_TOKEN":
                            val = val.split("root/")[0].strip()
                        config[k.strip()] = val
        except Exception as e:
            logger.error(f"Error reading .env: {e}")
    
    # Резерв из окружения
    if 'ADMIN_BOT_TOKEN' not in config:
        config['ADMIN_BOT_TOKEN'] = os.getenv('ADMIN_BOT_TOKEN')
    
    return config

CONF = load_config()
TOKEN = CONF.get('ADMIN_BOT_TOKEN')
ADMIN_SECRET = CONF.get('ADMIN_SECRET', 'MRAKOTIK')
SERVER_URL = CONF.get('SERVER_URL', 'http://localhost:8000')

if not TOKEN or not isinstance(TOKEN, str) or len(TOKEN) < 10:
    logger.critical(f"❌ ТОКЕН НЕВАЛИДЕН ИЛИ ОТСУТСТВУЕТ! Найдено: {TOKEN}")
    print("\n--- ДИАГНОСТИКА ---")
    print(f"Текущая папка: {os.getcwd()}")
    print(f"Файлы в папке: {os.listdir('.')}")
    print("-------------------\n")
    sys.exit(1)

logger.info(f"✅ Токен загружен: {TOKEN[:10]}...")

bot = Bot(token=TOKEN)
dp = Dispatcher()

async def call_api(months: int):
    try:
        r = requests.post(f"{SERVER_URL}/api/admin/generate-key", 
                         json={"months": months}, 
                         headers={"x-admin-token": ADMIN_SECRET}, timeout=10)
        return r.json().get("key") if r.status_code == 200 else f"Error {r.status_code}"
    except Exception as e: return f"Connection error: {e}"

@dp.message(Command("start"))
async def cmd_start(m: Message):
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔑 1 Месяц", callback_data="buy_1"))
    kb.row(InlineKeyboardButton(text="🔑 3 Месяца", callback_data="buy_3"))
    kb.row(InlineKeyboardButton(text="💎 1 Год", callback_data="buy_12"))
    await m.answer("👋 Панель генерации ключей:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("buy_"))
async def handle_cb(cb: CallbackQuery):
    months = int(cb.data.split("_")[1])
    await cb.message.edit_text("⏳ Генерирую...")
    key = await call_api(months)
    await cb.message.edit_text(f"✅ Ключ на {months} мес:\n\n<code>{key}</code>", parse_mode="HTML")

async def main():
    logger.info("Бот лицензий запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
