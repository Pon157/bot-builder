import os
import asyncio
import logging
import sys
import requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, CallbackQuery, Message
from supabase import create_client, Client

# --- АВТО-ОПРЕДЕЛЕНИЕ ПУТИ ---
# Берем папку, в которой лежит текущий файл (main.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("LicenseBot")

def load_config():
    # Теперь путь всегда будет правильным: /var/www/botengine/.env
    path = os.path.join(BASE_DIR, '.env')
    conf = {}
    
    if not os.path.exists(path):
        logger.error(f"❌ Файл .env не найден по пути: {path}")
        return conf

    with open(path, 'r', encoding='utf-8-sig') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            val = v.strip().strip('"').strip("'")
            
            # Твой фикс для токена
            if k.strip() == "ADMIN_BOT_TOKEN" and "root/" in val:
                val = val.split("root/")[0].strip()
            
            conf[k.strip()] = val
    return conf

CONFIG = load_config()

# Проверка загрузки
TOKEN = CONFIG.get("ADMIN_BOT_TOKEN")
SUPABASE_URL = CONFIG.get("SUPABASE_URL")
SUPABASE_KEY = CONFIG.get("SUPABASE_KEY")

if not TOKEN or not SUPABASE_URL or not SUPABASE_KEY:
    logger.critical(f"🛑 ОШИБКА: Ключи не загружены! Путь поиска: {BASE_DIR}")
    # Выведем, что реально удалось прочитать
    logger.info(f"Доступные ключи: {list(CONFIG.keys())}")
    sys.exit(1)

# Данные для API и админки
ADMIN_SECRET = CONFIG.get("ADMIN_SECRET", "MRAKOTIK")
ADMIN_CHAT_ID = CONFIG.get("ADMIN_CHAT_ID")
SERVER_URL = CONFIG.get("SERVER_URL", "http://localhost:8000")

# Инициализация Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- ФУНКЦИИ БД (Таблица 'users', колонки 'user_id' и 'currency') ---

def get_user_currency(user_id: int):
    try:
        res = supabase.table("users").select("currency").eq("user_id", user_id).execute()
        if res.data:
            return res.data[0]['currency']
        return None
    except Exception as e:
        logger.error(f"Supabase error (get): {e}")
        return None

def set_user_currency(user_id: int, currency: str):
    try:
        # Используем upsert: если юзер есть - обновит, если нет - создаст
        supabase.table("users").upsert({"user_id": user_id, "currency": currency}).execute()
    except Exception as e:
        logger.error(f"Supabase error (set): {e}")

# --- ЭКОНОМИКА ---
BASE_PRICE_RUB = 100 
CURRENCIES = {
    "RUB": {"symbol": "₽", "rate": 1.0},
    "USD": {"symbol": "$", "rate": 0.011},
    "EUR": {"symbol": "€", "rate": 0.010},
    "BYN": {"symbol": "BYN", "rate": 0.035},
    "UAH": {"symbol": "₴", "rate": 0.43},
    "KZT": {"symbol": "₸", "rate": 5.20}
}
PERIODS = {
    1: {"label": "1 Месяц", "mult": 1.0},
    3: {"label": "3 Месяца", "mult": 2.5},
    12: {"label": "1 Год", "mult": 8.0}
}

def get_price_string(months, currency_code):
    curr_data = CURRENCIES.get(currency_code, CURRENCIES["RUB"])
    raw_price = BASE_PRICE_RUB * PERIODS[months]["mult"] * curr_data["rate"]
    price_val = int(round(raw_price)) if raw_price >= 10 else round(raw_price, 2)
    return f"{price_val} {curr_data['symbol']}"

# ==========================================
# 2. ЛОГИКА БОТА
# ==========================================

async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()

    async def send_main_menu(message: Message, user_id, is_edit=False):
        currency = get_user_currency(user_id) or "RUB"
        kb = InlineKeyboardBuilder()
        for months, info in PERIODS.items():
            price_text = get_price_string(months, currency)
            kb.row(InlineKeyboardButton(text=f"🔑 {info['label']} — {price_text}", callback_data=f"buy_{months}"))
        kb.row(InlineKeyboardButton(text=f"⚙️ Валюта: {currency}", callback_data="change_curr"))
        
        text = "🚀 <b>BotEngine Pro: Магазин</b>\nВыберите срок подписки:"
        if is_edit: await message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        else: await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

    @dp.message(Command("start"))
    async def cmd_start(m: Message):
        user_curr = get_user_currency(m.from_user.id)
        if not user_curr:
            kb = InlineKeyboardBuilder()
            for code in CURRENCIES.keys(): kb.add(InlineKeyboardButton(text=code, callback_data=f"setcurr_{code}"))
            kb.adjust(3)
            await m.answer("🌍 <b>Выберите вашу валюту:</b>", reply_markup=kb.as_markup(), parse_mode="HTML")
        else:
            await send_main_menu(m, m.from_user.id)

    @dp.callback_query(F.data.startswith("setcurr_"))
    async def set_curr(cb: CallbackQuery):
        code = cb.data.split("_")[1]
        set_user_currency(cb.from_user.id, code)
        await cb.answer(f"Выбрано: {code}")
        await send_main_menu(cb.message, cb.from_user.id, is_edit=True)

    @dp.callback_query(F.data == "change_curr")
    async def change_curr(cb: CallbackQuery):
        kb = InlineKeyboardBuilder()
        for code in CURRENCIES.keys(): kb.add(InlineKeyboardButton(text=code, callback_data=f"setcurr_{code}"))
        kb.adjust(3)
        await cb.message.edit_text("🌍 <b>Выберите новую валюту:</b>", reply_markup=kb.as_markup(), parse_mode="HTML")

    @dp.callback_query(F.data.startswith("buy_"))
    async def buy_item(cb: CallbackQuery):
        months = int(cb.data.split("_")[1])
        currency = get_user_currency(cb.from_user.id) or "RUB"
        price = get_price_string(months, currency)
        
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="💳 Оплатить", url="https://www.donationalerts.com/r/dialoge_engine"))
        kb.row(InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"verify_{months}"))
        kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu"))
        
        await cb.message.edit_text(
            f"🛒 <b>Оформление: {PERIODS[months]['label']}</b>\nК оплате: <b>{price}</b>\n\n"
            f"Переведите сумму и нажмите кнопку подтверждения.",
            reply_markup=kb.as_markup(), parse_mode="HTML"
        )

    @dp.callback_query(F.data == "back_to_menu")
    async def back(cb: CallbackQuery):
        await send_main_menu(cb.message, cb.from_user.id, is_edit=True)

    @dp.callback_query(F.data.startswith("verify_"))
    async def verify(cb: CallbackQuery):
        if not ADMIN_CHAT_ID: return await cb.answer("Ошибка админ-чата", show_alert=True)
        months = int(cb.data.split("_")[1])
        currency = get_user_currency(cb.from_user.id) or "RUB"
        price = get_price_string(months, currency)
        
        admin_kb = InlineKeyboardBuilder()
        admin_kb.row(
            InlineKeyboardButton(text="✅ Ок", callback_data=f"adm_ok_{cb.from_user.id}_{months}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"adm_no_{cb.from_user.id}")
        )
        
        await bot.send_message(ADMIN_CHAT_ID, 
            f"💰 <b>Заявка!</b>\nЮзер: {cb.from_user.full_name} (<code>{cb.from_user.id}</code>)\n"
            f"Тариф: {months} мес. | Сумма: {price}", reply_markup=admin_kb.as_markup(), parse_mode="HTML")
        await cb.message.edit_text("⏳ <b>Заявка отправлена. Ожидайте подтверждения.</b>")

    # --- АДМИН-ОБРАБОТЧИКИ ---

    @dp.callback_query(F.data.startswith("adm_ok_"))
    async def approve(cb: CallbackQuery):
        if str(cb.message.chat.id) != str(ADMIN_CHAT_ID): return
        uid, months = int(cb.data.split("_")[2]), int(cb.data.split("_")[3])
        await cb.message.edit_text(f"⏳ Генерирую ключ для {uid}...")
        
        try:
            # Запрос к твоему API (сервер должен сам занести ключ в Supabase/свою БД)
            r = requests.post(f"{SERVER_URL}/api/admin/generate-key", 
                             json={"months": months, "user_id": uid}, 
                             headers={"x-admin-token": ADMIN_SECRET}, timeout=10)
            
            if r.status_code == 200:
                key = r.json().get("key")
                await bot.send_message(uid, f"🎉 Оплата принята!\nВаш ключ активации: <code>{key}</code>")
                await cb.message.edit_text(f"✅ Успешно. Ключ <code>{key}</code> отправлен.")
            else:
                await cb.message.edit_text(f"❌ Ошибка API сервера: {r.status_code}")
        except Exception as e:
            await cb.message.edit_text(f"❌ Ошибка связи с сервером: {e}")

    @dp.callback_query(F.data.startswith("adm_no_"))
    async def decline(cb: CallbackQuery):
        if str(cb.message.chat.id) != str(ADMIN_CHAT_ID): return
        uid = int(cb.data.split("_")[2])
        try:
            await bot.send_message(uid, "❌ Ваш платеж не подтвержден.")
            await cb.message.edit_text(f"🔴 Заявка пользователя {uid} отклонена.")
        except: pass

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
