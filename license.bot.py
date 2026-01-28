
import os
import asyncio
import logging
import secrets
import json
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, WebAppInfo

# --- Конфигурация ---
TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
# URL вашего сайта (замените на ваш реальный домен/IP)
WEB_APP_URL = os.getenv("WEB_APP_URL", "http://localhost:3000") 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

def generate_key(months: int):
    """Генерирует ключ формата BOT-1-ABC12345"""
    random_suffix = secrets.token_hex(4).upper()
    return f"BOT-{months}-{random_suffix}"

# --- Клавиатуры ---

def get_main_kb():
    builder = InlineKeyboardBuilder()
    
    # Кнопки с ценами, ведущие на профиль сайта
    # Можно использовать WebAppInfo для открытия сайта внутри Telegram
    builder.row(InlineKeyboardButton(
        text="⭐️ 50 | 1 Месяц доступа", 
        url=f"{WEB_APP_URL}"
    ))
    builder.row(InlineKeyboardButton(
        text="⭐️ 100 | 2 Месяца доступа", 
        url=f"{WEB_APP_URL}"
    ))
    builder.row(InlineKeyboardButton(
        text="💎 ОПТ | Связаться с админом", 
        url="https://t.me/Kotickr"
    ))
    
    # Кнопка подтверждения оплаты (ручная проверка)
    builder.row(InlineKeyboardButton(
        text="✅ Я оплатил (Проверка)", 
        callback_data="check_payment"
    ))
    
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
    
    # Пытаемся отправить красивую картинку, если есть (опционально)
    await message.answer(welcome_text, reply_markup=get_main_kb(), parse_mode="Markdown")

@dp.callback_query(F.data == "check_payment")
async def process_check_payment(callback: types.CallbackQuery):
    user = callback.from_user
    alert_text = (
        f"🔔 **Заявка на проверку оплаты!**\n\n"
        f"Юзер: @{user.username or 'без_ника'}\n"
        f"ID: `{user.id}`\n"
        f"Имя: {user.full_name}\n\n"
        f"Если оплата поступила, нажмите кнопку ниже для генерации ключа:"
    )
    
    try:
        await bot.send_message(
            ADMIN_CHAT_ID, 
            alert_text, 
            parse_mode="Markdown", 
            reply_markup=get_admin_kb(user.id)
        )
        await callback.answer("✅ Уведомление отправлено админам. Ключ придет сюда в течение 5-15 минут.", show_alert=True)
    except Exception as e:
        logging.error(f"Error sending to admin: {e}")
        await callback.answer("❌ Ошибка: ADMIN_CHAT_ID не настроен или бот не в чате.", show_alert=True)

@dp.callback_query(F.data.startswith("confirm_"))
async def confirm_payment(callback: types.CallbackQuery):
    # Проверка прав (только в админ чате)
    if str(callback.message.chat.id) != str(ADMIN_CHAT_ID):
        return await callback.answer("У вас нет прав администратора.")

    parts = callback.data.split("_")
    target_user_id = int(parts[1])
    months = int(parts[2])
    
    new_key = generate_key(months)
    
    try:
        await bot.send_message(
            target_user_id,
            f"🎉 **Ваша лицензия готова!**\n\n"
            f"Период: **{months} мес.**\n"
            f"Ключ: `{new_key}`\n\n"
            f"👉 Перейдите на сайт и вставьте его в поле активации в Профиле.",
            parse_mode="Markdown"
        )
        await callback.message.edit_text(f"✅ Ключ `{new_key}` (на {months} мес.) выдан пользователю `{target_user_id}`")
    except Exception as e:
        await callback.answer(f"Ошибка отправки: {e}", show_alert=True)

@dp.callback_query(F.data.startswith("decline_"))
async def decline_payment(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    target_user_id = int(parts[1])
    
    try:
        await bot.send_message(target_user_id, "❌ **Заявка на оплату отклонена.**\nЕсли вы уверены, что оплатили, свяжитесь с поддержкой: @Kotickr")
        await callback.message.edit_text(f"❌ Заявка пользователя `{target_user_id}` отклонена.")
    except:
        await callback.message.edit_text(f"❌ Не удалось оповестить `{target_user_id}`, заявка удалена.")

async def main():
    print("License Bot with Profile Links started...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
