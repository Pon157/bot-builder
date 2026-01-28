
import os
import asyncio
import logging
import sys
import requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, CallbackQuery, Message

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("LicenseBot")

def get_clean_token():
    """Загрузка и жесткая очистка токена из всех возможных источников"""
    token = os.getenv("ADMIN_BOT_TOKEN")
    
    # Пытаемся прочитать из файла .env напрямую, если в окружении пусто или мусор
    env_path = '/root/bot-builder/bot-builder/.env'
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                if line.startswith('ADMIN_BOT_TOKEN='):
                    token = line.split('=')[1].strip().strip('"').strip("'")
                    break
    
    if token and "root/" in token:
        token = token.split("root/")[0].strip()
    
    return token

TOKEN = get_clean_token()
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")
SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8000")
# Список ID админов, кому разрешено генерировать ключи
ALLOWED_ADMINS = os.getenv("ADMIN_CHAT_ID", "").split(',')

if not TOKEN:
    logger.critical("❌ КРИТИЧЕСКАЯ ОШИБКА: ADMIN_BOT_TOKEN не найден!")
    sys.exit(1)

bot = Bot(token=TOKEN)
dp = Dispatcher()

def is_admin(user_id: int):
    if not ALLOWED_ADMINS or ALLOWED_ADMINS == ['']: return True # Если не задано, разрешено всем (для теста)
    return str(user_id) in [id.strip() for id in ALLOWED_ADMINS]

async def call_api_gen(months: int):
    try:
        url = f"{SERVER_URL}/api/admin/generate-key"
        headers = {"x-admin-token": ADMIN_SECRET}
        r = requests.post(url, json={"months": months}, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json().get("key")
        return f"Ошибка API: {r.status_code}"
    except Exception as e:
        return f"Ошибка подключения: {e}"

@dp.message(Command("start"))
async def cmd_start(m: Message):
    if not is_admin(m.from_user.id):
        return await m.answer("⛔ У вас нет прав для использования этого бота.")
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔑 1 Месяц", callback_data="buy_1"))
    builder.row(InlineKeyboardButton(text="🔑 3 Месяца", callback_data="buy_3"))
    builder.row(InlineKeyboardButton(text="💎 1 Год", callback_data="buy_12"))
    
    await m.answer(
        "👋 <b>Панель управления лицензиями BotEngine</b>\n\n"
        "Выберите срок действия для генерации нового ключа:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("buy_"))
async def handle_callback(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer("Доступ запрещен", show_alert=True)
    
    months = int(cb.data.split("_")[1])
    await cb.message.edit_text(f"⏳ Генерирую ключ на {months} мес...")
    
    key = await call_api_gen(months)
    
    if key and "BOT-" in key:
        await cb.message.edit_text(
            f"✅ <b>Ключ успешно создан!</b>\n\n"
            f"Срок: <code>{months} месяцев</code>\n"
            f"Ключ: <code>{key}</code>\n\n"
            f"<i>Отправьте этот ключ пользователю для активации в панели.</i>",
            parse_mode="HTML"
        )
    else:
        await cb.message.edit_text(f"❌ <b>Ошибка генерации:</b>\n{key}", parse_mode="HTML")

async def main():
    logger.info(f"Бот лицензий запущен (Token: {TOKEN[:10]}...)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
