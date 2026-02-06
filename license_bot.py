import os
import asyncio
import logging
import sys
import requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, CallbackQuery, Message

# ==========================================
# 1. КОНФИГУРАЦИЯ И НАСТРОЙКИ
# ==========================================

BASE_DIR = "/root/bot-builder/bot-builder"
if os.path.exists(BASE_DIR):
    os.chdir(BASE_DIR)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("LicenseBot")

def load_config():
    path = os.path.join(BASE_DIR, '.env')
    conf = {}
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8-sig') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    val = v.strip().strip('"').strip("'")
                    # Очистка токена если там есть путь
                    if k.strip() == "ADMIN_BOT_TOKEN" and "root/" in val:
                        val = val.split("root/")[0].strip()
                    conf[k.strip()] = val
    return conf

CONFIG = load_config()
TOKEN = CONFIG.get("ADMIN_BOT_TOKEN")
ADMIN_SECRET = CONFIG.get("ADMIN_SECRET", "MRAKOTIK")
ADMIN_CHAT_ID = CONFIG.get("ADMIN_CHAT_ID") 
SERVER_URL = "http://localhost:8000"

if not TOKEN:
    logger.critical("🛑 ADMIN_BOT_TOKEN не найден в .env!")
    sys.exit(1)

# --- ЭКОНОМИКА ---

# Базовая цена за 1 месяц в РУБЛЯХ (от нее считаются все остальные)
BASE_PRICE_RUB = 100 

# Курсы валют (1 RUB = X валюты)
CURRENCIES = {
    "RUB": {"symbol": "₽", "rate": 1.0},
    "USD": {"symbol": "$", "rate": 0.011},
    "EUR": {"symbol": "€", "rate": 0.010},
    "BYN": {"symbol": "BYN", "rate": 0.035},
    "UAH": {"symbol": "₴", "rate": 0.43},
    "KZT": {"symbol": "₸", "rate": 5.20}
}

# Периоды и множители цены (скидки)
PERIODS = {
    1: {"label": "1 Месяц", "mult": 1.0},      # Цена = Base * 1
    3: {"label": "3 Месяца", "mult": 2.5},     # Цена = Base * 2.5 (скидка 16%)
    2: {"label": "2 Месяца", "mult": 1.9},  
    12: {"label": "1 Год", "mult": 8.0}        # Цена = Base * 8.0 (скидка 33%)
}

# Временное хранилище выбора валюты (User ID -> Currency Code)
# При перезагрузке бота сбросится на RUB. Для постоянства нужна БД.
user_currency_pref = {}

def get_price_string(months, currency_code):
    """Считает цену и возвращает красивую строку"""
    curr_data = CURRENCIES.get(currency_code, CURRENCIES["RUB"])
    
    # Расчет: Базовая цена * Множитель периода * Курс валюты
    raw_price = BASE_PRICE_RUB * PERIODS[months]["mult"] * curr_data["rate"]
    
    # Красивое округление
    if raw_price < 10 and raw_price != 0:
        price_val = round(raw_price, 2) # Оставляем копейки/центы для малых сумм
        if price_val == int(price_val): price_val = int(price_val)
    else:
        price_val = int(round(raw_price)) # Округляем до целых для больших сумм
        
    return f"{price_val} {curr_data['symbol']}"

# ==========================================
# 2. ЛОГИКА БОТА
# ==========================================

async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()

    # --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

    async def send_currency_selector(message: Message, is_edit=False):
        """Отправляет клавиатуру выбора валюты"""
        kb = InlineKeyboardBuilder()
        for code in CURRENCIES.keys():
            kb.add(InlineKeyboardButton(text=code, callback_data=f"setcurr_{code}"))
        kb.adjust(3) # По 3 кнопки в ряд
        
        text = "🌍 <b>Выберите вашу валюту:</b>\nЦены будут автоматически пересчитаны под вас."
        
        if is_edit:
            await message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

    async def send_main_menu(message: Message, user_id, is_edit=False):
        """Отправляет главное меню с ценами в валюте пользователя"""
        currency = user_currency_pref.get(user_id, "RUB")
        
        kb = InlineKeyboardBuilder()
        # Генерируем кнопки товаров динамически
        for months, info in PERIODS.items():
            price_text = get_price_string(months, currency)
            kb.row(InlineKeyboardButton(
                text=f"🔑 {info['label']} — {price_text}", 
                callback_data=f"buy_{months}"
            ))
            
        kb.row(InlineKeyboardButton(text=f"⚙️ Сменить валюту ({currency})", callback_data="change_curr"))
        
        text = (
            f"🚀 <b>BotEngine Pro: Магазин лицензий</b>\n\n"
            f"Валюта: <b>{currency}</b>\n"
            f"Выберите период подписки для получения ключа.\n"
            f"После выбора вы получите ссылку на оплату."
        )
        
        if is_edit:
            await message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

    # --- ХЕНДЛЕРЫ ПОЛЬЗОВАТЕЛЯ ---

    @dp.message(Command("start"))
    async def cmd_start(m: Message):
        # Если валюта еще не выбрана — предлагаем выбрать
        if m.from_user.id not in user_currency_pref:
            await send_currency_selector(m, is_edit=False)
        else:
            await send_main_menu(m, m.from_user.id, is_edit=False)

    @dp.callback_query(F.data.startswith("setcurr_"))
    async def set_currency_handler(cb: CallbackQuery):
        """Обработка выбора валюты"""
        code = cb.data.split("_")[1]
        user_currency_pref[cb.from_user.id] = code
        await cb.answer(f"Валюта установлена: {code}")
        await send_main_menu(cb.message, cb.from_user.id, is_edit=True)

    @dp.callback_query(F.data == "change_curr")
    async def change_currency_btn(cb: CallbackQuery):
        """Кнопка смены валюты из главного меню"""
        await send_currency_selector(cb.message, is_edit=True)
        
    @dp.callback_query(F.data == "back_to_menu")
    async def back_to_menu_btn(cb: CallbackQuery):
        """Кнопка 'Назад'"""
        await send_main_menu(cb.message, cb.from_user.id, is_edit=True)

    @dp.callback_query(F.data.startswith("buy_"))
    async def buy_handler(cb: CallbackQuery):
        """Меню оплаты конкретного товара"""
        months = int(cb.data.split("_")[1])
        currency = user_currency_pref.get(cb.from_user.id, "RUB")
        price_text = get_price_string(months, currency)
        
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="💳 Оплатить (DonationAlerts)", url="https://www.donationalerts.com/r/dialoge_engine"))
        kb.row(InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"verify_{months}"))
        kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu"))
        
        await cb.message.edit_text(
            f"🛒 <b>Оформление подписки</b>\n\n"
            f"Тариф: <b>{PERIODS[months]['label']}</b>\n"
            f"К оплате: <b>{price_text}</b>\n\n"
            f"1. Перейдите по кнопке «Оплатить».\n"
            f"2. В комментарии к платежу укажите ваш ID/Username: <code>{cb.from_user.id}</code> (оБЯЗАТЕЛЬНО).\n"
            f"3. Вернитесь сюда и нажмите «Я оплатил».",
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )

    @dp.callback_query(F.data.startswith("verify_"))
    async def verify_payment_handler(cb: CallbackQuery):
        """Пользователь нажал 'Я оплатил'"""
        if not ADMIN_CHAT_ID:
            return await cb.answer("❌ Ошибка: чат админов не настроен!", show_alert=True)
            
        months = int(cb.data.split("_")[1])
        user = cb.from_user
        currency = user_currency_pref.get(user.id, "RUB")
        expected_price = get_price_string(months, currency)
        
        # Клавиатура для админа
        admin_kb = InlineKeyboardBuilder()
        admin_kb.row(
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"adm_approve_{user.id}_{months}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm_decline_{user.id}")
        )
        
        try:
            # Отправка заявки админу
            await bot.send_message(
                ADMIN_CHAT_ID,
                f"💰 <b>НОВАЯ ОПЛАТА</b>\n\n"
                f"👤 Пользователь: {user.full_name} (@{user.username})\n"
                f"🆔 ID: <code>{user.id}</code>\n"
                f"📅 Тариф: <b>{months} мес.</b>\n"
                f"💵 Сумма к проверке: <b>{expected_price}</b>\n\n"
                f"Проверьте поступление средств и примите решение:",
                reply_markup=admin_kb.as_markup(),
                parse_mode="HTML"
            )
            
            # Ответ пользователю
            await cb.message.edit_text(
                "⏳ <b>Заявка отправлена на проверку!</b>\n\n"
                "Администратор проверит ваш платеж в течение 5-30 минут.\n"
                "Как только оплата подтвердится, бот пришлет вам ключ активации прямо сюда.",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to send to admin: {e}")
            await cb.answer("❌ Ошибка отправки заявки. Попробуйте позже.", show_alert=True)

    # --- ХЕНДЛЕРЫ АДМИНИСТРАТОРА ---

    @dp.callback_query(F.data.startswith("adm_approve_"))
    async def admin_approve(cb: CallbackQuery):
        """Админ нажал Подтвердить"""
        # Проверка прав (чтобы никто не мог подделать запрос, хотя chat_id уже фильтр)
        if str(cb.message.chat.id) != str(ADMIN_CHAT_ID):
            return await cb.answer("⛔ Доступ запрещен", show_alert=True)
            
        parts = cb.data.split("_")
        target_user_id = int(parts[2])
        months = int(parts[3])
        
        await cb.message.edit_text(f"⏳ Генерирую ключ для ID {target_user_id} ({months} мес)...")
        
        try:
            # Запрос к вашему API
            response = requests.post(
                f"{SERVER_URL}/api/admin/generate-key",
                json={"months": months},
                headers={"x-admin-token": ADMIN_SECRET},
                timeout=15
            )
            
            if response.status_code == 200:
                key = response.json().get("key")
                
                # 1. Отправляем ключ пользователю
                try:
                    await bot.send_message(
                        target_user_id,
                        f"🎉 <b>Оплата подтверждена! Спасибо!</b>\n\n"
                        f"Ваш ключ активации ({months} мес.):\n"
                        f"<code>{key}</code>\n\n"
                        f"<i>Скопируйте ключ и введите его в панели управления.</i>",
                        parse_mode="HTML"
                    )
                    # 2. Обновляем сообщение у админа
                    await cb.message.edit_text(
                        f"✅ <b>Успешно!</b>\n"
                        f"Ключ: <code>{key}</code>\n"
                        f"Отправлен пользователю {target_user_id}.",
                        parse_mode="HTML"
                    )
                except Exception as ex:
                    await cb.message.edit_text(f"⚠️ Ключ создан (<code>{key}</code>), но ЛС юзера закрыто.\nОшибка: {ex}", parse_mode="HTML")
            else:
                await cb.message.edit_text(f"❌ Ошибка API сервера: Code {response.status_code}\n{response.text}")
                
        except Exception as e:
            logger.error(f"API Error: {e}")
            await cb.message.edit_text(f"❌ Критическая ошибка соединения с сервером:\n{e}")

    @dp.callback_query(F.data.startswith("adm_decline_"))
    async def admin_decline(cb: CallbackQuery):
        """Админ нажал Отклонить"""
        if str(cb.message.chat.id) != str(ADMIN_CHAT_ID):
            return await cb.answer("⛔ Доступ запрещен", show_alert=True)
            
        target_user_id = int(cb.data.split("_")[2])
        
        try:
            # Уведомляем пользователя
            await bot.send_message(
                target_user_id,
                "❌ <b>Ваш платеж не был подтвержден.</b>\n\n"
                "Администратор не нашел поступления средств. "
                "Если произошла ошибка, свяжитесь с поддержкой.",
                parse_mode="HTML"
            )
            await cb.message.edit_text(f"🔴 Заявка пользователя {target_user_id} отклонена.")
        except:
            await cb.message.edit_text(f"🔴 Заявка отклонена (сообщение юзеру не доставлено).")

    # --- ЗАПУСК ---
    logger.info("✨ License Bot (Multi-Currency) запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
