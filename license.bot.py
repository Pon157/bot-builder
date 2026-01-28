
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
    """Универсальный загрузчик .env"""
    paths = ['.env', '../.env', './.env']
    for p in paths:
        if os.path.exists(p):
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if '=' in line and not line.startswith('#'):
                        k, v = line.split('=', 1)
                        os.environ[k.strip()] = v.strip('"').strip("'").strip()
            return True
    return False

load_env()

# Конфигурация
TOKEN = os.getenv("ADMIN_BOT_TOKEN")
# Важно: ADMIN_SECRET должен совпадать с тем, что в server.py
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "SUPER_SECRET_TOKEN_123")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8000")

if not TOKEN:
    logger.critical("❌ ОШИБКА: ADMIN_BOT_TOKEN не найден! Проверьте файл .env")
    sys.exit(1)

bot = Bot(token=TOKEN.strip())
dp = Dispatcher()

def is_authorized(message: types.Message):
    """Проверяет, разрешено ли пользователю или чату управлять лицензиями"""
    if not ADMIN_CHAT_ID:
        return True # Если не указано, разрешено всем (не рекомендуется)
    
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
        return None
    except Exception as e:
        logger.error(f"Ошибка API: {e}")
        return None

def get_admin_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔑 1 месяц", callback_data="gen_1"))
    builder.row(InlineKeyboardButton(text="🔑 3 месяца", callback_data="gen_3"))
    builder.row(InlineKeyboardButton(text="💎 12 месяцев", callback_data="gen_12"))
    return builder.as_markup()

@dp.message(Command("start"))
async def start(message: types.Message):
    if not is_authorized(message):
        return await message.answer("❌ Доступ ограничен. Ваш ID: `" + str(message.from_user.id) + "`", parse_mode="Markdown")
        
    await message.answer(
        "💎 **Генератор лицензионных ключей**\nВыберите тариф для создания ключа:",
        reply_markup=get_admin_kb(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("gen_"))
async def handle_gen_key(callback: CallbackQuery):
    if not is_authorized(callback.message):
        return await callback.answer("Нет доступа", show_alert=True)

    months = int(callback.data.split("_")[1])
    await callback.answer("Генерирую...")
    
    key = await generate_key_via_api(months)
    
    if key:
        await callback.message.answer(
            f"✅ **Ключ создан (на {months} мес.)**\n\n`{key}`\n\n_Скопируйте и отправьте пользователю._",
            parse_mode="Markdown"
        )
    else:
        await callback.message.answer("❌ **Ошибка API!** Проверьте, что `server.py` запущен.")

async def main():
    logger.info(f"Бот запущен. ADMIN_CHAT_ID: {ADMIN_CHAT_ID}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
