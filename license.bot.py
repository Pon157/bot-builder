
import os
import asyncio
import logging
import sys
import requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, CallbackQuery, Message

# ГАРАНТИРОВАННЫЙ ПЕРЕХОД В ПАПКУ
BASE_DIR = "/root/bot-builder/bot-builder"
if os.path.exists(BASE_DIR):
    os.chdir(BASE_DIR)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', stream=sys.stdout)
logger = logging.getLogger("LicenseBot")

def get_config():
    """Максимально надежный поиск ADMIN_BOT_TOKEN"""
    paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'),
        os.path.join(BASE_DIR, '.env'),
        '.env'
    ]
    conf = {}
    for p in paths:
        if os.path.exists(p):
            logger.info(f"🔎 Проверка .env по пути: {p}")
            try:
                with open(p, 'r', encoding='utf-8-sig') as f:
                    for line in f:
                        line = line.strip()
                        if line and '=' in line and not line.startswith('#'):
                            k, v = line.split('=', 1)
                            key = k.strip()
                            val = v.strip().strip('"').strip("'")
                            if "root/" in val and key == "ADMIN_BOT_TOKEN":
                                val = val.split("root/")[0].strip()
                            conf[key] = val
                if conf.get("ADMIN_BOT_TOKEN"):
                    logger.info("✅ Токен найден в файле")
                    break
            except Exception as e:
                logger.error(f"Ошибка чтения файла {p}: {e}")
    
    # Если в файлах не нашли, смотрим системное окружение
    if not conf.get("ADMIN_BOT_TOKEN"):
        env_token = os.getenv("ADMIN_BOT_TOKEN")
        if env_token:
            conf["ADMIN_BOT_TOKEN"] = env_token
            logger.info("✅ Токен взят из системного окружения")
            
    return conf

# ЗАГРУЗКА
CONFIG = get_config()
TOKEN = CONFIG.get("ADMIN_BOT_TOKEN")
ADMIN_SECRET = CONFIG.get("ADMIN_SECRET", "MRAKOTIK")
SERVER_URL = CONFIG.get("SERVER_URL", "http://localhost:8000")

# ВАЛИДАЦИЯ ПЕРЕД ЗАПУСКОМ
if not TOKEN or not isinstance(TOKEN, str) or len(TOKEN) < 20:
    logger.critical(f"🛑 ОШИБКА: ADMIN_BOT_TOKEN невалиден! Значение: {repr(TOKEN)}")
    print("\n--- ОТЛАДКА ---")
    print(f"Путь к скрипту: {os.path.abspath(__file__)}")
    print(f"Рабочая директория: {os.getcwd()}")
    print(f"Файлы в директории: {os.listdir('.')}")
    if os.path.exists('.env'):
        print("Файл .env существует.")
    print("----------------\n")
    sys.exit(1)

logger.info(f"🦾 Инициализация бота... (Token: {TOKEN[:5]}***{TOKEN[-5:]})")

try:
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
except Exception as e:
    logger.error(f"❌ Aiogram не принял токен: {e}")
    sys.exit(1)

async def call_api(months: int):
    try:
        r = requests.post(f"{SERVER_URL}/api/admin/generate-key", 
                         json={"months": months}, 
                         headers={"x-admin-token": ADMIN_SECRET}, timeout=10)
        if r.status_code == 200:
            return r.json().get("key")
        return f"Ошибка сервера: {r.status_code}"
    except Exception as e:
        return f"Ошибка связи: {e}"

@dp.message(Command("start"))
async def cmd_start(m: Message):
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔑 1 Месяц", callback_data="buy_1"))
    kb.row(InlineKeyboardButton(text="🔑 3 Месяца", callback_data="buy_3"))
    kb.row(InlineKeyboardButton(text="💎 1 Год", callback_data="buy_12"))
    await m.answer("👋 <b>Панель управления лицензиями</b>\nВыберите тариф для генерации ключа:", 
                   reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("buy_"))
async def handle_buy(cb: CallbackQuery):
    months = int(cb.data.split("_")[1])
    await cb.message.edit_text("⏳ Генерирую ключ...")
    key = await call_api(months)
    await cb.message.edit_text(f"✅ <b>Ключ на {months} мес. готов:</b>\n\n<code>{key}</code>", 
                               parse_mode="HTML")

async def main():
    logger.info("✨ Бот лицензий онлайн!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
