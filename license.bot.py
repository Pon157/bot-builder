import os
import asyncio
import logging
import secrets
import sys

# Настройка логирования для вывода в PM2
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("LicenseBot")

def load_env_at_all_costs():
    """Ищет .env везде: в текущей папке, в папке скрипта и по абсолютному пути."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cwd = os.getcwd()
    
    search_locations = [
        os.path.join(cwd, '.env'),
        os.path.join(script_dir, '.env'),
        '/root/bot-builder/bot-builder/.env'
    ]
    
    logger.info(f"🔍 Поиск .env. Текущая папка: {cwd}")
    
    for path in search_locations:
        if os.path.exists(path):
            logger.info(f"✅ Найден .env: {path}")
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'): continue
                        if '=' in line:
                            k, v = line.split('=', 1)
                            val = v.strip().strip('"').strip("'")
                            os.environ[k.strip()] = val
                return True
            except Exception as e:
                logger.error(f"❌ Ошибка чтения {path}: {e}")
    return False

# Загружаем окружение
load_env_at_all_costs()

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

# Получаем данные
TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
WEB_APP_URL = os.getenv("WEB_APP_URL", "http://localhost:3000")

# Проверка токена
if not TOKEN:
    logger.error("!!! КРИТИЧЕСКАЯ ОШИБКА: ADMIN_BOT_TOKEN НЕ НАЙДЕН !!!")
    logger.error("Убедитесь, что файл .env существует и содержит ADMIN_BOT_TOKEN=...")
    # Не падаем сразу, чтобы PM2 не перезапускал бесконечно, а пишем в лог
    sys.exit(1)

logger.info(f"🚀 Инициализация бота с токеном: {TOKEN[:8]}***")

try:
    bot = Bot(token=TOKEN.strip())
    dp = Dispatcher()
except Exception as e:
    logger.error(f"❌ Ошибка Aiogram: {e}")
    sys.exit(1)

# --- Логика бота ---

def generate_key(months: int):
    return f"BOT-{months}-{secrets.token_hex(4).upper()}"

def get_main_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⭐️ 1 Месяц", url=f"{WEB_APP_URL}"))
    builder.row(InlineKeyboardButton(text="⭐️ 2 Месяца", url=f"{WEB_APP_URL}"))
    builder.row(InlineKeyboardButton(text="✅ Я оплатил", callback_data="check_payment"))
    return builder.as_markup()

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "💎 **BotEngine Pro — Лицензии**\n\nКупите доступ и введите ключ в профиле.",
        reply_markup=get_main_kb(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "check_payment")
async def check_payment(callback: types.CallbackQuery):
    if not ADMIN_CHAT_ID:
        return await callback.answer("Ошибка: ADMIN_CHAT_ID не настроен", show_alert=True)
    
    try:
        await bot.send_message(
            ADMIN_CHAT_ID, 
            f"🔔 Оплата! Юзер: @{callback.from_user.username}\nID: `{callback.from_user.id}`",
            parse_mode="Markdown"
        )
        await callback.answer("✅ Админ уведомлен!", show_alert=True)
    except Exception as e:
        logger.error(f"Admin Notify Error: {e}")
        await callback.answer("Ошибка связи с админом", show_alert=True)

async def main():
    logger.info("📡 Начинаю polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановлено")
