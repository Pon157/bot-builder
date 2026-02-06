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

# ==========================================
# 1. КОНФИГУРАЦИЯ И ЛОГИРОВАНИЕ
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)
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
                # Извлечение токена по твоей инструкции [.env]
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
    logger.critical("🛑 Ошибка: Проверьте .env файл (TOKEN/SUPABASE)")
    sys.exit(1)

# Инициализация клиентов
bot = Bot(token=TOKEN)
dp = Dispatcher()
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 2. ЭКОНОМИКА И КОНСТАНТЫ
# ==========================================
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

# ==========================================
# 3. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (БД И ЦЕНЫ)
# ==========================================

def get_user_currency(user_id: int):
    try:
        res = supabase.table("bot_users").select("currency").eq("id", str(user_id)).execute()
        if res.data and 'currency' in res.data[0]:
            return res.data[0]['currency']
        return "RUB"
    except Exception as e:
        logger.error(f"Ошибка получения валюты: {e}")
        return "RUB"

def set_user_currency(user_id: int, code: str, username: str = None):
    try:
        data = {"id": str(user_id), "currency": code}
        if username:
            data["username"] = username
        supabase.table("bot_users").upsert(data).execute()
    except Exception as e:
        logger.error(f"Ошибка сохранения в bot_users: {e}")

def calculate_price(months: int, currency_code: str):
    curr = CURRENCIES.get(currency_code, CURRENCIES["RUB"])
    price = int(round(BASE_PRICE_RUB * PERIODS[months]["mult"] * curr["rate"]))
    return f"{price} {curr['symbol']}"

async def show_menu(message: Message, user_id: int, is_edit: bool = False):
    currency = get_user_currency(user_id)
    kb = InlineKeyboardBuilder()
    
    for months, info in PERIODS.items():
        price_text = calculate_price(months, currency)
        kb.row(InlineKeyboardButton(
            text=f"🔑 {info['label']} — {price_text}", 
            callback_data=f"buy_{months}"
        ))
        
    kb.row(InlineKeyboardButton(text=f"🌍 Валюта: {currency}", callback_data="change_currency"))
    
    text = "🚀 <b>BotEngine Pro: Магазин</b>\n\nВыберите период подписки. Цены пересчитаны автоматически."
    
    if is_edit:
        await message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

# ==========================================
# 4. ОБРАБОТЧИКИ (HANDLERS)
# ==========================================

@dp.message(Command("start"))
async def cmd_start(m: Message):
    set_user_currency(m.from_user.id, get_user_currency(m.from_user.id), m.from_user.username)
    await show_menu(m, m.from_user.id)

@dp.callback_query(F.data == "change_currency")
async def cmd_change_curr(cb: CallbackQuery):
    kb = InlineKeyboardBuilder()
    for code in CURRENCIES.keys():
        kb.add(InlineKeyboardButton(text=code, callback_data=f"set_{code}"))
    kb.adjust(3)
    await cb.message.edit_text("🌍 <b>Выберите вашу валюту:</b>", reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("set_"))
async def save_curr(cb: CallbackQuery):
    code = cb.data.split("_")[1]
    set_user_currency(cb.from_user.id, code, cb.from_user.username)
    await cb.answer(f"Установлено: {code}")
    await show_menu(cb.message, cb.from_user.id, is_edit=True)

@dp.callback_query(F.data.startswith("buy_"))
async def cmd_buy(cb: CallbackQuery):
    months = int(cb.data.split("_")[1])
    currency = get_user_currency(cb.from_user.id)
    price_str = calculate_price(months, currency)
    
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💳 Оплатить", url="https://www.donationalerts.com/r/dialoge_engine"))
    kb.row(InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"verif_p_{months}"))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu"))
    
    await cb.message.edit_text(
        f"🛒 <b>Оплата: {PERIODS[months]['label']}</b>\n"
        f"Сумма: <b>{price_str}</b>\n\n"
        f"1. Сделайте перевод по ссылке.\n"
        f"2. Нажмите кнопку подтверждения.",
        reply_markup=kb.as_markup(), 
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "back_to_menu")
async def cmd_back(cb: CallbackQuery):
    await show_menu(cb.message, cb.from_user.id, is_edit=True)

@dp.callback_query(F.data.startswith("verif_p_"))
async def cmd_verify(cb: CallbackQuery):
    if not ADMIN_CHAT_ID:
        return await cb.answer("Ошибка: Чат админа не настроен")
        
    months = int(cb.data.split("_")[2])
    currency = get_user_currency(cb.from_user.id)
    price_str = calculate_price(months, currency)
    
    akb = InlineKeyboardBuilder()
    akb.row(
        InlineKeyboardButton(text="✅ Ок", callback_data=f"adm_ok_{cb.from_user.id}_{months}"),
        InlineKeyboardButton(text="❌ Нет", callback_data=f"adm_no_{cb.from_user.id}")
    )
    
    await bot.send_message(
        ADMIN_CHAT_ID,
        f"💰 <b>Заявка на ключ!</b>\n\n"
        f"👤 Юзер: {cb.from_user.full_name}\n"
        f"🆔 ID: <code>{cb.from_user.id}</code>\n"
        f"💎 Тариф: {months} мес.\n"
        f"💵 Сумма: {price_str}",
        reply_markup=akb.as_markup(),
        parse_mode="HTML"
    )
    await cb.message.edit_text(
        "⏳ <b>Заявка на проверке</b>\n\n"
        "Как только администратор подтвердит ваш платёж, "
        "вы получите сообщение с ключом активации.",
        parse_mode="HTML"
    )

# ==========================================
# 5. АДМИН-ЛОГИКА (ВЫДАЧА КЛЮЧЕЙ)
# ==========================================

@dp.callback_query(F.data.startswith("adm_ok_"))
async def admin_approve(cb: CallbackQuery):
    _, _, uid, months = cb.data.split("_")
    await cb.message.edit_text(f"⏳ Генерирую ключ для {uid}...")
    
    try:
        r = requests.post(
            f"{SERVER_URL}/api/admin/generate-key",
            json={"months": int(months), "user_id": uid},
            headers={"x-admin-token": ADMIN_SECRET},
            timeout=10
        )
        if r.status_code == 200:
            key = r.json().get("key")
            # Юзеру
            await bot.send_message(
                uid, 
                f"🎉 <b>Оплата принята!</b>\n\n"
                f"Ваш ключ: <code>{key}</code>", 
                parse_mode="HTML"
            )
            # Админу
            await cb.message.edit_text(
                f"✅ Ключ <code>{key}</code>\n"
                f"Отправлен пользователю: <code>{uid}</code>", 
                parse_mode="HTML"
            )
        else:
            await cb.message.edit_text(f"❌ Ошибка сервера: {r.status_code}")
    except Exception as e:
        await cb.message.edit_text(f"❌ Ошибка связи: {e}")

@dp.callback_query(F.data.startswith("adm_no_"))
async def admin_decline(cb: CallbackQuery):
    uid = cb.data.split("_")[2]
    try:
        await bot.send_message(uid, "❌ <b>Ваш платеж не подтвержден.</b>", parse_mode="HTML")
        await cb.message.edit_text(f"🔴 Заявка {uid} отклонена.")
    except:
        pass

# ==========================================
# 6. ЗАПУСК
# ==========================================

async def main():
    logger.info("✨ Бот запускается...")
    # Удаляем вебхуки, если были
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
