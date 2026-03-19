import os
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from db_adapter import DBAdapter, init_pg_pool
from aiohttp import web
import aiohttp_cors

load_dotenv()

# Все данные берем строго из .env
SUB_URL = os.getenv("SUPABASE_URL")
SUB_KEY = os.getenv("SUPABASE_KEY")
BOT_TOKEN = os.getenv("REVIEW_BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_CHAT_ID")
ADMIN_SECRET = os.getenv("ADMIN_SECRET") # Твой MRAKOTIK

_db = DBAdapter(SUB_URL, SUB_KEY)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- ТЕЛЕГРАМ МОДЕРАЦИЯ ---
# --- ТЕЛЕГРАМ МОДЕРАЦИЯ ---
@dp.callback_query(F.data.startswith("rev_"))
async def handle_moderation(callback: types.CallbackQuery):
    # 1. Проверяем права пользователя в этом чате
    try:
        member = await callback.bot.get_chat_member(
            chat_id=callback.message.chat.id, 
            user_id=callback.from_user.id
        )
        
        # Разрешаем только создателю и администраторам
        if member.status not in ["administrator", "creator"]:
            return await callback.answer("❌ Доступ только для администраторов чата!", show_alert=True)
            
    except Exception as e:
        print(f"Ошибка проверки прав: {e}")
        return await callback.answer("Ошибка проверки прав", show_alert=True)

    # 2. Если админ — продолжаем работу
    parts = callback.data.split(":")
    action = parts[0]
    review_id = parts[1]
    
    new_status = "approved" if action == "rev_approve" else "rejected"

    try:
        # Обновляем статус в Supabase
        await _db.patch("reviews", {"id": f"eq.{review_id}"}, {"status": new_status})
        
        status_label = "✅ ОДОБРЕНО" if new_status == "approved" else "❌ УДАЛЕНО"
        
        # Убираем кнопки и пишем кто модерировал
        await callback.message.edit_text(
            f"{callback.message.text}\n\nСтатус: {status_label}\nМодератор: {callback.from_user.first_name}", 
            reply_markup=None
        )
        await callback.answer("Готово")
    except Exception as e:
        print(f"Ошибка БД: {e}")
        await callback.answer(f"Ошибка БД: {e}")

# --- API МЕТОДЫ ---
async def get_approved_reviews(request):
    """Метод для лендинга (отдает только одобренное)"""
    res = await _db.get("reviews", {"status": "eq.approved", "order": "created_at.desc"})
    return web.json_response(res)

async def post_new_review(request):
    """Метод для приема отзыва"""
    # МЕНЯЕМ x-admin-token на X-Admin-Secret
    if request.headers.get("X-Admin-Secret") != ADMIN_SECRET:
        return web.json_response({"error": "Unauthorized"}, status=403)

    data = await request.json()
    try:
        res = await _db.post("reviews", {
            "author_name": data.get("name"),
            "author_role": data.get("role"),
            "review_text": data.get("text"),
            "rating": data.get("rating"),
            "status": "pending",
        })

        review_id = res["id"] if res else None
        if not review_id:
            return web.json_response({"error": "DB insert failed"}, status=500)
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
    await init_pg_pool()
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
