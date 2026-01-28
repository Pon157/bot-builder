
import os
import asyncio
import logging
import sys
import requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, CallbackQuery

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("LicenseBot")

def load_env():
    """Максимально надежная загрузка .env из разных путей для PM2"""
    # Список возможных путей к .env
    possible_paths = [
        os.path.join(os.getcwd(), '.env'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'),
        '/root/bot-builder/bot-builder/.env'
    ]
    
    found = False
    for p in possible_paths:
        if os.path.exists(p):
            logger.info(f"Загрузка настроек из: {p}")
            with open(p, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        os.environ[k.strip()] = v.strip('"').strip("'").strip()
            found = True
            break
    return found

# Сначала загружаем окружение
if not load_env():
    logger.error("⚠️ ВНИМАНИЕ: Файл .env не найден! Бот может не запуститься.")

# Теперь берем переменные
TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "SUPER_SECRET_TOKEN_123")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8000")

# --- Глобальные объекты (создаем только если есть токен) ---
bot = None
dp = Dispatcher()

# --- Вспомогательные функции ---

def is_authorized(message: types.Message):
    if not ADMIN_CHAT_ID: return True
    user_id = str(message.from_user.id)
    chat_id = str(message.chat.id)
    allowed_ids = [i.strip() for i in ADMIN_CHAT_ID.split(',')]
    return user_id in allowed_ids or chat_id in allowed_ids

async def generate_key_via_api(months: int):
    try:
        url = f"{SERVER_URL}/api/admin/generate-key"
        headers = {"x-admin-token": ADMIN_SECRET}
        payload = {"months": months}
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: requests.post(url, json=payload, headers=headers, timeout=5)
        )
        if response.status_code == 200:
            return response.json().get("key")
    except Exception as e:
        logger.error(f"API Error: {e}")
    return None

def get_admin_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔑 1 месяц", callback_data="gen_1"))
    builder.row(InlineKeyboardButton(text="🔑 3 месяца", callback_data="gen_3"))
    builder.row(InlineKeyboardButton(text="💎 12 месяцев", callback_data="gen_12"))
    return builder.as_markup()

# --- Обработчики ---

@dp.message(Command("start"))
async def start(message: types.Message):
    if not is_authorized(message):
        return await message.answer(f"❌ Доступ ограничен. ID: `{message.from_user.id}`", parse_mode="Markdown")
    await message.answer("💎 **Генератор ключей**\nВыберите тариф:", reply_markup=get_admin_kb(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("gen_"))
async def handle_gen_key(callback: CallbackQuery):
    if not is_authorized(callback.message): return
    months = int(callback.data.split("_")[1])
    await callback.answer("⏳...")
    key = await generate_key_via_api(months)
    if key:
        await callback.message.answer(f"✅ **Ключ создан:**\n`{key}`", parse_mode="Markdown")
    else:
        await callback.message.answer("❌ Ошибка сервера API. Проверьте server.py")

async def main():
    global bot
    if not TOKEN:
        logger.critical("❌ ТОКЕН НЕ НАЙДЕН! Проверьте ADMIN_BOT_TOKEN в .env")
        return

    logger.info("Инициализация бота...")
    bot = Bot(token=TOKEN.strip())
    logger.info("Бот для лицензий успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
