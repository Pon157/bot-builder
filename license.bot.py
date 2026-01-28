import os
import asyncio
import logging
import secrets
import sys

# Настройка логирования ПЕРЕД загрузкой всего остального
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("LicenseBot")

# Попытка загрузки dotenv
try:
    from dotenv import load_dotenv
    # Проверяем .env в папке со скриптом
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(script_dir, '.env')
    
    if os.path.exists(env_path):
        load_dotenv(env_path)
        logger.info(f"✅ Конфигурация загружена из: {env_path}")
    else:
        logger.warning(f"⚠️ Файл .env не найден по пути: {env_path}")
except ImportError:
    logger.warning("⚠️ Библиотека python-dotenv не установлена. Используются системные переменные.")

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

# --- Конфигурация ---
TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
WEB_APP_URL = os.getenv("WEB_APP_URL", "http://localhost:3000") 

if not TOKEN or TOKEN.strip() == "":
    logger.error("❌ КРИТИЧЕСКАЯ ОШИБКА: ADMIN_BOT_TOKEN пустой или не найден!")
    logger.error("Проверьте, что в файле .env написано: ADMIN_BOT_TOKEN=ваш_токен")
    sys.exit(1)

# Инициализируем бота только если токен прошел проверку
try:
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
except Exception as e:
    logger.error(f"❌ Ошибка инициализации бота: {e}")
    sys.exit(1)

def generate_key(months: int):
    """Генерирует ключ формата BOT-1-ABC12345"""
    random_suffix = secrets.token_hex(4).upper()
    return f"BOT-{months}-{random_suffix}"

# --- Клавиатуры ---

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

# --- Обработчики ---

@dp.message(Command("start"))
async def start(message: types.Message):
    welcome_text = (
        "💎 **BotEngine Pro — Лицензионный центр**\n\n"
        "Для работы с конструктором необходима активная лицензия.\n"
        "Выберите тариф ниже и перейдите в профиль для оплаты/активации.\n\n"
        "💳 **Доступные способы:**\n"
        "• Telegram Stars (Звезды) ⭐️\n"
        "• Криптовалюта / Карты (через админа)\n\n"
        "🚀 *После покупки вы получите ключ, который нужно ввести на сайте.*"
    )
    await message.answer(welcome_text, reply_markup=get_main_kb(), parse_mode="Markdown")

@dp.callback_query(F.data == "check_payment")
async def process_check_payment(callback: types.CallbackQuery):
    user = callback.from_user
    if not ADMIN_CHAT_ID:
        logger.error("ADMIN_CHAT_ID не настроен в .env")
        return await callback.answer("❌ Ошибка: Админ не настроен", show_alert=True)
        
    alert_text = (
        f"🔔 **Заявка на проверку оплаты!**\n\n"
        f"Юзер: @{user.username or 'без_ника'}\n"
        f"ID: `{user.id}`\n"
        f"Имя: {user.full_name}\n\n"
        f"Если оплата поступила, нажмите кнопку ниже:"
    )
    
    try:
        await bot.send_message(ADMIN_CHAT_ID, alert_text, parse_mode="Markdown", reply_markup=get_admin_kb(user.id))
        await callback.answer("✅ Уведомление отправлено админам. Ключ придет сюда после проверки.", show_alert=True)
    except Exception as e:
        logger.error(f"Error sending to admin: {e}")
        await callback.answer(f"❌ Ошибка отправки админу", show_alert=True)

@dp.callback_query(F.data.startswith("confirm_"))
async def confirm_payment(callback: types.CallbackQuery):
    if str(callback.message.chat.id) != str(ADMIN_CHAT_ID):
        return await callback.answer("У вас нет прав.")

    parts = callback.data.split("_")
    target_user_id = int(parts[1])
    months = int(parts[2])
    new_key = generate_key(months)
    
    try:
        await bot.send_message(
            target_user_id,
            f"🎉 **Ваша лицензия готова!**\n\nКлюч: `{new_key}`\n\n"
            f"👉 Вставьте его на сайте в разделе Профиль.",
            parse_mode="Markdown"
        )
        await callback.message.edit_text(f"✅ Ключ `{new_key}` выдан пользователю `{target_user_id}`")
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)

@dp.callback_query(F.data.startswith("decline_"))
async def decline_payment(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    target_user_id = int(parts[1])
    try:
        await bot.send_message(target_user_id, "❌ Заявка на оплату отклонена.")
        await callback.message.edit_text(f"❌ Отклонено для `{target_user_id}`")
    except:
        await callback.message.edit_text(f"❌ Ошибка уведомления юзера.")

async def main():
    logger.info("🚀 Лицензионный бот запускается...")
    logger.info(f"⚙️ Config: AdminID={ADMIN_CHAT_ID}, WebApp={WEB_APP_URL}")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Критическая ошибка при поллинге: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
