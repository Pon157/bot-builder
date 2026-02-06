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
# 1. ОКРУЖЕНИЕ И ПУТИ
# ==========================================
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
                if not line or line.startswith('#') or '=' not in line: continue
                k, v = line.split('=', 1)
                val = v.strip().strip('"').strip("'")
                # Фикс токена (инструкция [2025-12-23])
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
    logger.critical("🛑 ОШИБКА: Не все ключи найдены в .env (TOKEN, URL или KEY)")
    sys.exit(1)

# Инициализация Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 2. ЭКОНОМИКА И ТАРИФЫ
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

# Те самые периоды (1, 3, 12 месяцев)
PERIODS = {
    1: {"label": "1 Месяц", "mult": 1.0},
    3: {"label": "3 Месяца", "mult": 2.5},
    12: {"label": "1 Год", "mult": 8.0}
}

# ==========================================
# 3. ФУНКЦИИ РАБОТЫ С БД (SUPABASE)
# ==========================================

# --- Функции для НОВОЙ таблицы bot_users ---

def get_user_currency(uid: int):
    try:
        # Ищем в новой таблице bot_users
        res = supabase.table("bot_users").select("currency").eq("id", str(uid)).execute()
        if res.data and 'currency' in res.data[0]:
            return res.data[0]['currency']
        return "RUB"
    except Exception as e:
        logger.error(f"Ошибка получения валюты: {e}")
        return "RUB"

def set_user_currency(uid: int, code: str, username: str = None):
    try:
        # Пишем в новую таблицу bot_users
        data = {"id": str(uid), "currency": code}
        if username: 
            data["username"] = username
        
        # upsert обновит валюту или создаст запись, если юзера еще нет
        supabase.table("bot_users").upsert(data).execute()
    except Exception as e:
        logger.error(f"Ошибка сохранения в bot_users: {e}")
def calculate_price(months: int, currency_code: str):
    """Считает цену и возвращает красивую строку"""
    curr = CURRENCIES.get(currency_code, CURRENCIES["RUB"])
    price = int(round(BASE_PRICE_RUB * PERIODS[months]["mult"] * curr["rate"]))
    return f"{price} {curr['symbol']}"

# ==========================================
# 4. ЛОГИКА ТЕЛЕГРАМ-БОТА
# ==========================================

async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()

    async def send_main_menu(message: Message, user_id: int, is_edit: bool = False):
        """Главное меню с выбором месяцев"""
        currency = get_user_currency(user_id)
        kb = InlineKeyboardBuilder()
        
        # Кнопки выбора месяцев (1, 3, 12)
        for months, info in PERIODS.items():
            price_text = calculate_price(months, currency)
            kb.row(InlineKeyboardButton(
                text=f"🔑 {info['label']} — {price_text}", 
                callback_data=f"buy_{months}"
            ))
            
        # Кнопка смены валюты
        kb.row(InlineKeyboardButton(text=f"🌍 Валюта: {currency}", callback_data="change_currency"))
        
        text = "🚀 <b>Dialoge Engine Beta: Магазин ключей</b>\n\nВыберите нужный период подписки ниже:"
        
        if is_edit:
            await message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.message(Command("start"))
async def cmd_start(m: Message):
    # Регистрируем/обновляем юзера в НОВОЙ таблице
    set_user_currency(m.from_user.id, get_user_currency(m.from_user.id), m.from_user.username)
    await show_menu(m, m.from_user.id)

@dp.callback_query(F.data == "change_currency")
async def cmd_change_curr(cb: CallbackQuery):
    """Меню выбора валюты"""
    kb = InlineKeyboardBuilder()
    for code in CURRENCIES.keys():
        # Важно: используем простой формат set_{code} для легкости парсинга
        kb.add(InlineKeyboardButton(text=code, callback_data=f"set_{code}"))
    kb.adjust(3)
    await cb.message.edit_text("🌍 <b>Выберите вашу валюту:</b>", reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("set_"))
async def save_curr(cb: CallbackQuery):
    # Теперь split("_")[1] четко достанет код валюты (RUB, USD и т.д.)
    code = cb.data.split("_")[1]
    set_user_currency(cb.from_user.id, code, cb.from_user.username)
    await cb.answer(f"Валюта: {code}")
    await show_menu(cb.message, cb.from_user.id, edit=True)

@dp.callback_query(F.data.startswith("buy_"))
async def cmd_buy(cb: CallbackQuery):
    """Экран оплаты конкретного тарифа"""
    # Парсим ID периода (1, 3 или 12)
    months = int(cb.data.split("_")[1])
    currency = get_user_currency(cb.from_user.id)
    price_str = calculate_price(months, currency)
        
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="💳 Перейти к оплате", url="https://www.donationalerts.com/r/dialoge_engine"))
        kb.row(InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"verify_pay_{months}"))
        kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu"))
        
        await cb.message.edit_text(
            f"🛒 <b>Оформление подписки</b>\n\n"
            f"Период: <b>{PERIODS[months]['label']}</b>\n"
            f"К оплате: <b>{price_str}</b>\n\n"
            f"После перевода нажмите кнопку «Я оплатил».",
            reply_markup=kb.as_markup(), parse_mode="HTML"
        )

    @dp.callback_query(F.data == "back_to_menu")
    async def cmd_back(cb: CallbackQuery):
        await send_main_menu(cb.message, cb.from_user.id, is_edit=True)

    @dp.callback_query(F.data.startswith("verify_pay_"))
    async def cmd_verify(cb: CallbackQuery):
        """Уведомление админа о платеже"""
        if not ADMIN_CHAT_ID:
            return await cb.answer("Ошибка: Чат админов не настроен!", show_alert=True)
            
        months = int(cb.data.split("_")[2])
        currency = get_user_currency(cb.from_user.id)
        price_str = calculate_price(months, currency)
        
        # Кнопки для админа
        akb = InlineKeyboardBuilder()
        akb.row(
            InlineKeyboardButton(text="✅ Выдать ключ", callback_data=f"adm_ok_{cb.from_user.id}_{months}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm_no_{cb.from_user.id}")
        )
        
        # Сообщение в админ-чат
        await bot.send_message(
            ADMIN_CHAT_ID,
            f"💰 <b>Поступила новая оплата!</b>\n\n"
            f"Пользователь: {cb.from_user.full_name} (@{cb.from_user.username})\n"
            f"ID: <code>{cb.from_user.id}</code>\n"
            f"Тариф: <b>{months} мес.</b>\n"
            f"Сумма: <b>{price_str}</b>",
            reply_markup=akb.as_markup(), parse_mode="HTML"
        )
 # Сообщение пользователю после нажатия "Я оплатил"
        await cb.message.edit_text(
            "⏳ <b>Заявка отправлена на проверку</b>\n\n"
            "Как только администратор подтвердит ваш платёж, "
            "вы получите сообщение с ключом активации.",
            parse_mode="HTML"
        )
    # ==========================================
    # 5. ОБРАБОТКА РЕШЕНИЙ АДМИНИСТРАТОРА
    # ==========================================

    @dp.callback_query(F.data.startswith("adm_ok_"))
    async def admin_approve(cb: CallbackQuery):
        """Админ нажал 'Ок' -> Запрос к серверу за ключом"""
        _, _, uid, months = cb.data.split("_")
        await cb.message.edit_text(f"⏳ Генерирую ключ для {uid}...")
        
        try:
            # Запрос к твоему бэкенду (который пишет в таблицу issued_keys)
            r = requests.post(
                f"{SERVER_URL}/api/admin/generate-key",
                json={"months": int(months), "user_id": uid},
                headers={"x-admin-token": ADMIN_SECRET},
                timeout=10
            )
            
            if r.status_code == 200:
                key = r.json().get("key")
                # Уведомляем юзера (Исправленное форматирование)
                await bot.send_message(
                    uid, 
                    f"🎉 <b>Оплата принята!</b>\n\n"
                    f"Ваш ключ: <code>{key}</code>", 
                    parse_mode="HTML"
                )
                # Обновляем сообщение админу (Исправленное форматирование)
                await cb.message.edit_text(
                    f"✅ Ключ <code>{key}</code>\n"
                    f"Отправлен пользователю: <code>{uid}</code>", 
                    parse_mode="HTML"
                )
            else:
                await cb.message.edit_text(f"❌ Ошибка API: {r.status_code}\nПроверьте работу сервера.")
        except Exception as e:
            await cb.message.edit_text(f"❌ Ошибка связи с сервером: {e}")

    @dp.callback_query(F.data.startswith("adm_no_"))
    async def admin_decline(cb: CallbackQuery):
        """Админ отклонил платеж"""
        uid = cb.data.split("_")[2]
        try:
            await bot.send_message(uid, "❌ <b>Ваш платеж не был подтвержден администратором.</b>\nЕсли это ошибка, свяжитесь с поддержкой.", parse_mode="HTML")
            await cb.message.edit_text(f"🔴 Заявка пользователя {uid} отклонена.")
        except:
            pass

    # Запуск
    logger.info("✨ Бот запущен в режиме Long Polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
