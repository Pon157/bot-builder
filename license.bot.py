
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

# Загрузка окружения (упрощенная и надежная)
def load_env():
    # Пытаемся найти .env в текущей папке или выше
    paths = ['.env', '../.env', '/root/bot-builder/bot-builder/.env']
    for p in paths:
        if os.path.exists(p):
            with open(p) as f:
                for line in f:
                    if '=' in line and not line.startswith('#'):
                        k, v = line.strip().split('=', 1)
                        os.environ[k] = v.strip('"').strip("'")
            return True
    return False

load_env()

# Конфигурация
TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "SUPER_SECRET_TOKEN_123")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8000") # URL вашего FastAPI сервера

if not TOKEN:
    logger.critical("КРИТИЧЕСКАЯ ОШИБКА: ADMIN_BOT_TOKEN не найден в .env!")
    sys.exit(1)

bot = Bot(token=TOKEN.strip())
dp = Dispatcher()

# --- Вспомогательные функции ---

async def generate_key_via_api(months: int):
    """Делает запрос к основному серверу для создания ключа в базе данных."""
    try:
        url = f"{SERVER_URL}/api/admin/generate-key"
        headers = {"x-admin-token": ADMIN_SECRET}
        payload = {"months": months}
        
        # Используем выполнение в экзекуторе, чтобы не блокировать event loop aiogram
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: requests.post(url, json=payload, headers=headers, timeout=5)
        )
        
        if response.status_code == 200:
            return response.json().get("key")
        else:
            logger.error(f"Server API Error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"Request failed: {e}")
        return None

# --- Обработчики ---

def get_admin_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔑 Создать ключ: 1 мес", callback_data="gen_1"))
    builder.row(InlineKeyboardButton(text="🔑 Создать ключ: 3 мес", callback_data="gen_3"))
    builder.row(InlineKeyboardButton(text="💎 Создать ключ: 12 мес", callback_data="gen_12"))
    return builder.as_markup()

@dp.message(Command("start"))
async def start(message: types.Message):
    # Проверка на админа (если задан ADMIN_CHAT_ID)
    if ADMIN_CHAT_ID and str(message.from_user.id) != str(ADMIN_CHAT_ID):
        return await message.answer("❌ У вас нет доступа к генерации ключей.")
        
    await message.answer(
        "🛠 **Панель управления лицензиями**\n\nВыберите срок действия ключа для генерации:",
        reply_markup=get_admin_kb(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("gen_"))
async def handle_gen_key(callback: CallbackQuery):
    months = int(callback.data.split("_")[1])
    await callback.answer("⏳ Генерация ключа...")
    
    key = await generate_key_via_api(months)
    
    if key:
        await callback.message.answer(
            f"✅ **Ключ успешно создан!**\n\n`{key}`\n\nСрок: {months} мес.\n\n_Отправьте этот ключ пользователю для активации в профиле._",
            parse_mode="Markdown"
        )
    else:
        await callback.message.answer("❌ **Ошибка!** Не удалось связаться с сервером API. Проверьте, запущен ли основной сервер на порту 8000.")

async def main():
    logger.info("Бот для лицензий запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
