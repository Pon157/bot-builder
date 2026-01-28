import os
import asyncio
import logging
import secrets
import sys

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("LicenseBot")

def load_env_robust():
    """Агрессивный поиск и парсинг .env файла"""
    possible_paths = [
        os.path.join(os.getcwd(), '.env'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'),
        '/root/bot-builder/bot-builder/.env' # Абсолютный путь как последний шанс
    ]
    
    found_path = None
    env_vars = {}

    for path in possible_paths:
        if os.path.exists(path):
            found_path = path
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'): continue
                        if '=' in line:
                            k, v = line.split('=', 1)
                            # Очистка от кавычек и пробелов
                            clean_v = v.strip().strip('"').strip("'")
                            env_vars[k.strip()] = clean_v
                break
            except Exception as e:
                logger.error(f"Ошибка при чтении {path}: {e}")

    if found_path:
        logger.info(f"✅ Файл .env найден по пути: {found_path}")
        for key, val in env_vars.items():
            os.environ[key] = val
            # Вывод для отладки (маскированный)
            masked_val = f"{val[:5]}...{val[-4:]}" if len(val) > 10 else "***"
            logger.info(f"🔹 Загружена переменная: {key} = {masked_val}")
    else:
        logger.error("❌ Файл .env НЕ НАЙДЕН ни в одной из папок!")
        logger.error(f"Проверенные пути: {possible_paths}")

load_env_robust()

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

# --- Конфигурация ---
TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
WEB_APP_URL = os.getenv("WEB_APP_URL", "http://localhost:3000") 

# Проверка перед инициализацией
if TOKEN is None or not TOKEN.strip():
    print("\n" + "!"*50)
    print("КРИТИЧЕСКАЯ ОШИБКА: ADMIN_BOT_TOKEN ПУСТОЙ!")
    print("Скрипт не может найти токен в .env файле.")
    print(f"Текущая рабочая директория: {os.getcwd()}")
    print("Убедитесь, что в .env есть: ADMIN_BOT_TOKEN=7123456:ABC...")
    print("!"*50 + "\n")
    sys.exit(1)

try:
    bot = Bot(token=TOKEN.strip())
    dp = Dispatcher()
    logger.info("🤖 Объект Bot успешно создан.")
except Exception as e:
    logger.error(f"❌ Aiogram не смог принять токен: {e}")
    sys.exit(1)

def generate_key(months: int):
    random_suffix = secrets.token_hex(4).upper()
    return f"BOT-{months}-{random_suffix}"

def get_main_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⭐️ 50 | 1 Месяц доступа", url=f"{WEB_APP_URL}"))
    builder.row(InlineKeyboardButton(text="⭐️ 100 | 2 Месяца доступа", url=f"{WEB_APP_URL}"))
    builder.row(InlineKeyboardButton(text="💎 ОПТ | Связаться с админом", url="https://t.me/Kotickr"))
    builder.row(InlineKeyboardButton(text="✅ Я оплатил (Проверка)", callback_data="check_payment"))
    return builder.as_markup()

def get_admin_kb(user_id: int):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Выдать 1 мес.", callback_data=f"confirm_{user_id}_1"),
        InlineKeyboardButton(text="✅ Выдать 2 мес.", callback_data=f"confirm_{user_id}_2")
    )
    builder.row(InlineKeyboardButton(text="❌ Отклонить", callback_data=f"decline_{user_id}"))
    return builder.as_markup()

@dp.message(Command("start"))
async def start(message: types.Message):
    welcome_text = (
        "💎 **BotEngine Pro — Лицензионный центр**\n\n"
        "Для работы с конструктором необходима активная лицензия.\n"
        "Выберите тариф ниже и перейдите в профиль для оплаты.\n\n"
        "🚀 *После покупки вы получите ключ, который нужно ввести на сайте.*"
    )
    await message.answer(welcome_text, reply_markup=get_main_kb(), parse_mode="Markdown")

@dp.callback_query(F.data == "check_payment")
async def process_check_payment(callback: types.CallbackQuery):
    if not ADMIN_CHAT_ID:
        return await callback.answer("❌ Ошибка: ADMIN_CHAT_ID не задан в .env", show_alert=True)
    
    user = callback.from_user
    alert_text = (
        f"🔔 **Заявка на проверку оплаты!**\n\n"
        f"Юзер: @{user.username or 'ID' + str(user.id)}\n"
        f"ID: `{user.id}`\n"
        f"Имя: {user.full_name}"
    )
    
    try:
        await bot.send_message(ADMIN_CHAT_ID, alert_text, parse_mode="Markdown", reply_markup=get_admin_kb(user.id))
        await callback.answer("✅ Уведомление отправлено. Ожидайте ключ.", show_alert=True)
    except Exception as e:
        logger.error(f"Error notifying admin: {e}")
        await callback.answer(f"Ошибка отправки админу", show_alert=True)

@dp.callback_query(F.data.startswith("confirm_"))
async def confirm_payment(callback: types.CallbackQuery):
    if str(callback.message.chat.id) != str(ADMIN_CHAT_ID):
        return await callback.answer("Доступ запрещен")

    parts = callback.data.split("_")
    target_user_id = int(parts[1])
    months = int(parts[2])
    new_key = generate_key(months)
    
    try:
        await bot.send_message(target_user_id, f"🎉 **Лицензия готова!**\n\nКлюч: `{new_key}`")
        await callback.message.edit_text(f"✅ Ключ `{new_key}` выдан юзеру `{target_user_id}`")
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)

async def main():
    logger.info("🚀 Бот лицензий запущен и начинает опрос серверов Telegram...")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при поллинге: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")
