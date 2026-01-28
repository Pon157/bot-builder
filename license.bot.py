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

def bootstrap_env():
    """Надежный загрузчик переменных окружения"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Список мест, где мы ищем .env
    env_candidates = [
        os.path.join(script_dir, '.env'),
        os.path.join(os.getcwd(), '.env'),
        '/root/bot-builder/bot-builder/.env'
    ]
    
    env_found = False
    for path in env_candidates:
        if os.path.exists(path):
            logger.info(f"📂 Попытка загрузки .env из: {path}")
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#') or '=' not in line:
                            continue
                        k, v = line.split('=', 1)
                        # Очистка значения
                        clean_v = v.strip().strip('"').strip("'")
                        os.environ[k.strip()] = clean_v
                env_found = True
                logger.info(f"✅ Успешно загружено из {path}")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка чтения {path}: {e}")
    
    if not env_found:
        logger.warning("⚠️ Файл .env не найден ни в одном из стандартных путей!")

# Запускаем загрузку ПЕРЕД импортом aiogram
bootstrap_env()

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

# Читаем переменные
TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
WEB_APP_URL = os.getenv("WEB_APP_URL", "http://localhost:3000")

# Жёсткая проверка
if not TOKEN:
    logger.critical("!!! ADMIN_BOT_TOKEN НЕ НАЙДЕН В ОКРУЖЕНИИ !!!")
    logger.info(f"Текущие переменные: {list(os.environ.keys())}")
    print("\nОШИБКА: Токен пуст. Проверьте, что в .env написано ADMIN_BOT_TOKEN=...\n")
    sys.exit(1)

# Теперь создаем бота
try:
    bot = Bot(token=TOKEN.strip())
    dp = Dispatcher()
    logger.info("🤖 Бот успешно инициализирован.")
except Exception as e:
    logger.error(f"❌ Ошибка при создании Bot: {e}")
    sys.exit(1)

def generate_key(months: int):
    random_suffix = secrets.token_hex(4).upper()
    return f"BOT-{months}-{random_suffix}"

def get_main_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⭐️ Купить доступ (Web App)", url=f"{WEB_APP_URL}"))
    builder.row(InlineKeyboardButton(text="💎 ОПТ / Поддержка", url="https://t.me/Kotickr"))
    builder.row(InlineKeyboardButton(text="✅ Я оплатил", callback_data="check_payment"))
    return builder.as_markup()

def get_admin_kb(user_id: int):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ 1 мес", callback_data=f"confirm_{user_id}_1"),
        InlineKeyboardButton(text="✅ 2 мес", callback_data=f"confirm_{user_id}_2")
    )
    builder.row(InlineKeyboardButton(text="❌ Отклонить", callback_data=f"decline_{user_id}"))
    return builder.as_markup()

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "💎 **BotEngine Pro — Лицензионный центр**\n\n"
        "Для работы с конструктором необходима лицензия.",
        reply_markup=get_main_kb(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "check_payment")
async def process_check_payment(callback: types.CallbackQuery):
    if not ADMIN_CHAT_ID:
        return await callback.answer("Ошибка: ID админа не настроен", show_alert=True)
    
    try:
        await bot.send_message(
            ADMIN_CHAT_ID, 
            f"🔔 Оплата от @{callback.from_user.username or callback.from_user.id}",
            reply_markup=get_admin_kb(callback.from_user.id)
        )
        await callback.answer("✅ Запрос отправлен", show_alert=True)
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)

@dp.callback_query(F.data.startswith("confirm_"))
async def confirm_payment(callback: types.CallbackQuery):
    if str(callback.message.chat.id) != str(ADMIN_CHAT_ID): return
    
    _, uid, months = callback.data.split("_")
    key = generate_key(int(months))
    
    try:
        await bot.send_message(int(uid), f"🎉 Лицензия выдана!\n\nКлюч: `{key}`", parse_mode="Markdown")
        await callback.message.edit_text(f"✅ Выдан ключ {key} для {uid}")
    except Exception as e:
        await callback.answer(f"Ошибка: {e}")

async def main():
    logger.info("🚀 Запуск polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
