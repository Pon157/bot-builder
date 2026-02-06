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

# --- Инициализация путей ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("LicenseBot")

def load_config():
    path = os.path.join(BASE_DIR, '.env')
    conf = {}
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                val = v.strip().strip('"').strip("'")
                # Фикс токена из .env
                if k.strip() == "ADMIN_BOT_TOKEN" and "root/" in val:
                    val = val.split("root/")[0].strip()
                conf[k.strip()] = val
    return conf

CONFIG = load_config()
TOKEN = CONFIG.get("ADMIN_BOT_TOKEN")
SUPABASE_URL = CONFIG.get("SUPABASE_URL")
SUPABASE_KEY = CONFIG.get("SUPABASE_KEY")
ADMIN_CHAT_ID = CONFIG.get("ADMIN_CHAT_ID")
ADMIN_SECRET = CONFIG.get("ADMIN_SECRET", "MRAKOTIK")
SERVER_URL = CONFIG.get("SERVER_URL", "http://localhost:8000")

if not all([TOKEN, SUPABASE_URL, SUPABASE_KEY]):
    logger.critical("🛑 Ошибка: Проверьте TOKEN, SUPABASE_URL и SUPABASE_KEY в .env")
    sys.exit(1)

# Инициализация Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Настройки экономики ---
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

# --- Функции БД (Supabase) ---

def get_user_currency(user_id: int):
    try:
        res = supabase.table("users").select("currency").eq("id", str(user_id)).execute()
        if res.data and 'currency' in res.data[0]:
            return res.data[0]['currency']
        return "RUB" # По умолчанию
    except Exception as e:
        logger.error(f"Supabase GET error: {e}")
        return "RUB"

def set_user_currency(user_id: int, currency: str):
    try:
        # Используем upsert: обновляем валюту, сохраняя существующего юзера
        supabase.table("users").upsert({"id": str(user_id), "currency": currency}).execute()
    except Exception as e:
        logger.error(f"Supabase SET error: {e}")

def get_price_str(months, currency_code):
    c = CURRENCIES.get(currency_code, CURRENCIES["RUB"])
    price = int(round(BASE_PRICE_RUB * PERIODS[months]["mult"] * c["rate"]))
    return f"{price} {c['symbol']}"

# --- Логика Бота ---

async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()

    async def show_main_menu(m: Message, uid: int, is_edit=False):
        curr = get_user_currency(uid)
        kb = InlineKeyboardBuilder()
        for mo, data in PERIODS.items():
            kb.row(InlineKeyboardButton(text=f"🔑 {data['label']} — {get_price_str(mo, curr)}", callback_data=f"buy_{mo}"))
        kb.row(InlineKeyboardButton(text=f"⚙️ Валюта: {curr}", callback_data="change_curr"))
        
        text = "🚀 <b>BotEngine Pro: Магазин</b>\n\nВыберите период подписки. Цены пересчитаны автоматически."
        if is_edit: await m.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        else: await m.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

    @dp.message(Command("start"))
    async def cmd_start(m: Message):
        # Проверяем, есть ли юзер в базе
        curr = get_user_currency(m.from_user.id)
        # Если валюта не установлена (None), заставляем выбрать
        await show_main_menu(m, m.from_user.id)

    @dp.callback_query(F.data == "change_curr")
    async def select_currency(cb: CallbackQuery):
        kb = InlineKeyboardBuilder()
        for code in CURRENCIES.keys():
            kb.add(InlineKeyboardButton(text=code, callback_data=f"set_{code}"))
        kb.adjust(3)
        await cb.message.edit_text("🌍 <b>Выберите валюту:</b>", reply_markup=kb.as_markup(), parse_mode="HTML")

    @dp.callback_query(F.data.startswith("set_"))
    async def save_currency(cb: CallbackQuery):
        code = cb.data.split("_")[1]
        set_user_currency(cb.from_user.id, code)
        await cb.answer(f"Установлено: {code}")
        await show_main_menu(cb.message, cb.from_user.id, is_edit=True)

    @dp.callback_query(F.data.startswith("buy_"))
    async def prepare_buy(cb: CallbackQuery):
        mo = int(cb.data.split("_")[1])
        curr = get_user_currency(cb.from_user.id)
        price = get_price_str(mo, curr)
        
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="💳 Оплатить", url="https://www.donationalerts.com/r/dialoge_engine"))
        kb.row(InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"ver_{mo}"))
        kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back"))
        
        await cb.message.edit_text(
            f"🛒 <b>Оплата: {PERIODS[mo]['label']}</b>\n"
            f"Сумма: <b>{price}</b>\n\n"
            f"1. Сделайте перевод по ссылке.\n"
            f"2. Нажмите кнопку подтверждения.",
            reply_markup=kb.as_markup(), parse_mode="HTML"
        )

    @dp.callback_query(F.data == "back")
    async def back_to_start(cb: CallbackQuery):
        await show_main_menu(cb.message, cb.from_user.id, is_edit=True)

    @dp.callback_query(F.data.startswith("ver_"))
    async def send_to_admin(cb: CallbackQuery):
        if not ADMIN_CHAT_ID: return await cb.answer("Ошибка: ADMIN_CHAT_ID не задан", show_alert=True)
        mo = int(cb.data.split("_")[1])
        curr = get_user_currency(cb.from_user.id)
        
        adm_kb = InlineKeyboardBuilder()
        adm_kb.row(
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"ok_{cb.from_user.id}_{mo}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"no_{cb.from_user.id}")
        )
        
        await bot.send_message(
            ADMIN_CHAT_ID,
            f"🆕 <b>Заявка на ключ!</b>\n\n"
            f"Юзер: {cb.from_user.full_name} (@{cb.from_user.username})\n"
            f"ID: <code>{cb.from_user.id}</code>\n"
            f"Тариф: <b>{mo} мес.</b>\n"
            f"Валюта: <b>{curr}</b>",
            reply_markup=adm_kb.as_markup(), parse_mode="HTML"
        )
        await cb.message.edit_text("✅ <b>Заявка отправлена модераторам!</b>")

    # --- Обработка Админов ---

    @dp.callback_query(F.data.startswith("ok_"))
    async def admin_ok(cb: CallbackQuery):
        if str(cb.message.chat.id) != str(ADMIN_CHAT_ID): return
        _, uid, mo = cb.data.split("_")
        
        await cb.message.edit_text(f"⏳ Генерирую ключ для {uid}...")
        
        try:
            r = requests.post(
                f"{SERVER_URL}/api/admin/generate-key",
                json={"months": int(mo), "user_id": uid},
                headers={"x-admin-token": ADMIN_SECRET},
                timeout=10
            )
            if r.status_code == 200:
                key = r.json().get("key")
                await bot.send_message(uid, f"🎉 <b>Оплата принята!</b>\n\nВаш ключ: <code>{key}</code>")
                await cb.message.edit_text(f"✅ Ключ <code>{key}</code> отправлен пользователю {uid}")
            else:
                await cb.message.edit_text(f"❌ Ошибка сервера: {r.status_code}")
        except Exception as e:
            await cb.message.edit_text(f"❌ Ошибка связи: {e}")

    @dp.callback_query(F.data.startswith("no_"))
    async def admin_no(cb: CallbackQuery):
        if str(cb.message.chat.id) != str(ADMIN_CHAT_ID): return
        uid = cb.data.split("_")[1]
        try:
            await bot.send_message(uid, "❌ <b>Ваш платеж не подтвержден.</b>")
            await cb.message.edit_text(f"🔴 Заявка {uid} отклонена.")
        except: pass

    logger.info("✨ Бот запущен и готов к работе")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
