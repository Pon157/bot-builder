import os
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# Загружаем переменные из .env
load_dotenv()
TOKEN = os.getenv("ADMIN_BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message()
async def redirect_to_site(message: types.Message):
    # Текст, который просил пользователь
    text = (
        "Оплата здесь больше не работает, "
        "перейдите на сайт: https://dialogengine.webtm.ru/"
    )
    
    # Отправляем ответ на любое сообщение
    await message.answer(text)

async def main():
    print("Бот запущен и готов перенаправлять пользователей.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен.")
