import os
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from supabase import create_client, Client
from aiohttp import web
import aiohttp_cors

# Загружаем секреты из .env (помни: токены и id берем только оттуда!)
load_dotenv()

SUB_URL = os.getenv("SUPABASE_URL")
SUB_KEY = os.getenv("SUPABASE_KEY")
BOT_TOKEN = os.getenv("REVIEW_BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_CHAT_ID")
API_KEY = os.getenv("API_SECRET")

# Инициализация клиентов
supabase: Client = create_client(SUB_URL, SUB_KEY)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- ЛОГИКА ТЕЛЕГРАМ БОТА ---

@dp.callback_query(F.data.startswith("rev_"))
async def handle_moderation(callback: types.CallbackQuery):
    if str(callback.from_user.id) != ADMIN_ID:
        await callback.answer("Доступ только для владельца DialogEngine!", show_alert=True)
        return

    action, review_id = callback.data.split(":")[0], callback.data.split(":")[1]
    new_status = "approved" if action == "rev_approve" else "rejected"

    try:
        supabase.table("reviews").update({"status": new_status}).eq("id", review_id).execute()
        
        status_label = "✅ ОПУБЛИКОВАНО" if new_status == "approved" else "❌ УДАЛЕНО"
        await callback.message.edit_text(
            f"{callback.message.text}\n\nСтатус: {status_label}",
            reply_markup=None
        )
        await callback.answer(f"Статус обновлен")
    except Exception as e:
        await callback.answer(f"Ошибка БД: {e}")

# --- API МЕТОДЫ (ДЛЯ САЙТА) ---

async def get_approved_reviews(request):
    """Метод для отображения отзывов на лендинге"""
    try:
        res = supabase.table("reviews").select("*").eq("status", "approved").order("created_at", desc=True).execute()
        return web.json_response(res.data)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def post_new_review(request):
    """Прием отзыва с фронтенда с проверкой API ключа"""
    auth_key = request.headers.get("x-api-key")
    if auth_key != API_KEY:
        return web.json_response({"error": "Unauthorized"}, status=403)

    data = await request.json()
    
    try:
        res = supabase.table("reviews").insert({
            "author_name": data.get("name"),
            "author_role": data.get("role"),
            "review_text": data.get("text"),
            "rating": data.get("rating"),
            "status": "pending"
        }).execute()

        review_id = res.data[0]["id"]

        # Кнопки для админа
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"rev_approve:{review_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"rev_reject:{review_id}")
        ]])

        msg = (f"⭐️ <b>Новый отзыв!</b>\n\n"
               f"👤 {data.get('name')} ({data.get('role')})\n"
               f"📊 Оценка: {data.get('rating')}/5\n"
               f"💬 {data.get('text')}")

        await bot.send_message(ADMIN_ID, msg, parse_mode="HTML", reply_markup=keyboard)
        return web.json_response({"status": "success"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

# --- ЗАПУСК ВСЕЙ СИСТЕМЫ ---

async def main():
    app = web.Application()
    
    # Настройка CORS, чтобы React (на другом порту/домене) мог слать запросы
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
    })

    resource_post = app.router.add_resource("/api/reviews")
    cors.add(resource_post.add_route("POST", post_new_review))
    
    resource_get = app.router.add_resource("/api/reviews/get")
    cors.add(resource_get.add_route("GET", get_approved_reviews))

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 3001)
    
    await site.start()
    print("🚀 API сервера DialogEngine запущен на порту 3001")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
