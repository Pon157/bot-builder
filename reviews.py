import os
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from supabase import create_client, Client
from aiohttp import web
import aiohttp_cors

load_dotenv()

# Все данные берем строго из .env
SUB_URL = os.getenv("SUPABASE_URL")
SUB_KEY = os.getenv("SUPABASE_KEY")
BOT_TOKEN = os.getenv("REVIEW_BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_CHAT_ID")
ADMIN_SECRET = os.getenv("ADMIN_SECRET") # Твой MRAKOTIK

supabase: Client = create_client(SUB_URL, SUB_KEY)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- ТЕЛЕГРАМ МОДЕРАЦИЯ ---
@dp.callback_query(F.data.startswith("rev_"))
async def handle_moderation(callback: types.CallbackQuery):
    if str(callback.from_user.id) != ADMIN_ID:
        return await callback.answer("Нет доступа!", show_alert=True)

    action, review_id = callback.data.split(":")[0], callback.data.split(":")[1]
    new_status = "approved" if action == "rev_approve" else "rejected"

    try:
        supabase.table("reviews").update({"status": new_status}).eq("id", review_id).execute()
        status_label = "✅ ОДОБРЕНО" if new_status == "approved" else "❌ УДАЛЕНО"
        await callback.message.edit_text(f"{callback.message.text}\n\nСтатус: {status_label}", reply_markup=None)
        await callback.answer("Готово")
    except Exception as e:
        await callback.answer(f"Ошибка БД: {e}")

# --- API МЕТОДЫ ---
async def get_approved_reviews(request):
    """Метод для лендинга (отдает только одобренное)"""
    res = supabase.table("reviews").select("*").eq("status", "approved").order("created_at", desc=True).execute()
    return web.json_response(res.data)

async def post_new_review(request):
    """Метод для приема отзыва от FastAPI бэкенда"""
    # Проверка секрета: бэкенд шлет x-admin-token
    if request.headers.get("x-admin-token") != ADMIN_SECRET:
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
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"rev_approve:{review_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"rev_reject:{review_id}")
        ]])
        
        msg = f"⭐️ <b>Новый отзыв!</b>\n\n👤 {data.get('name')}\n💬 {data.get('text')}"
        await bot.send_message(ADMIN_ID, msg, parse_mode="HTML", reply_markup=kb)
        return web.json_response({"status": "success"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def main():
    app = web.Application()
    cors = aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers="*", allow_headers="*")})
    
    # Регистрация роутов
    app.router.add_get('/api/reviews/get', get_approved_reviews)
    res_post = app.router.add_resource("/api/reviews")
    cors.add(res_post.add_route("POST", post_new_review))

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 3001).start()
    print("🚀 Бот-модератор запущен на порту 3001")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
