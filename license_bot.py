import os
import asyncio
import logging
import sys
import requests
import json
from datetime import datetime
from typing import List, Optional, Union

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import (
    InlineKeyboardButton, CallbackQuery, Message, 
    BotCommand, BotCommandScopeChat
)
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from supabase import create_client, Client

# ==========================================
# 1. КОНФИГУРАЦИЯ И ЛОГИРОВАНИЕ
# ==========================================
# Установка рабочей директории для корректного поиска .env
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("LicenseBotEngine")

def load_env_secure():
    """
    Безопасная загрузка конфигурации.
    Специальная логика для извлечения токена (инструкция [2025-12-23]).
    """
    path = os.path.join(BASE_DIR, '.env')
    conf = {}
    if not os.path.exists(path):
        logger.error(f"🛑 Файл .env не найден в {BASE_DIR}")
        return conf
    
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                val = v.strip().strip('"').strip("'")
                # Извлечение чистого токена до 'root/'
                if k.strip() == "ADMIN_BOT_TOKEN" and "root/" in val:
                    val = val.split("root/")[0].strip()
                conf[k.strip()] = val
    except Exception as e:
        logger.error(f"❌ Ошибка парсинга .env: {e}")
    return conf

# Инициализация параметров
CONFIG = load_env_secure()
BOT_TOKEN = CONFIG.get("ADMIN_BOT_TOKEN")
SB_URL = CONFIG.get("SUPABASE_URL")
SB_KEY = CONFIG.get("SUPABASE_KEY")
ADM_CHAT = CONFIG.get("ADMIN_CHAT_ID")
ADM_SECRET = CONFIG.get("ADMIN_SECRET", "MRAKOTIK")
SRV_URL = CONFIG.get("SERVER_URL", "http://localhost:8000")

# Твой персональный ID (Super Admin)
MY_OWNER_ID = 5883703466

if not all([BOT_TOKEN, SB_URL, SB_KEY]):
    logger.critical("🛑 Ошибка: Проверьте .env (BOT_TOKEN, SUPABASE_URL или KEY)")
    sys.exit(1)

# Создание объектов бота и базы
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
supabase: Client = create_client(SB_URL, SB_KEY)

# ==========================================
# 2. ЭКОНОМИЧЕСКАЯ МОДЕЛЬ
# ==========================================
BASE_PRICE_RUB = 89.9

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
# 3. ФУНКЦИИ БАЗЫ ДАННЫХ (SUPABASE)
# ==========================================

async def db_get_currency(user_id: int) -> str:
    """Получает валюту пользователя. По умолчанию RUB."""
    try:
        res = supabase.table("bot_users").select("currency").eq("id", str(user_id)).execute()
        if res.data and 'currency' in res.data[0]:
            return res.data[0]['currency']
    except Exception as e:
        logger.error(f"DB Fetch Error (uid: {user_id}): {e}")
    return "RUB"

def db_upsert_user(user_id: int, currency: str, username: str = None):
    """
    Обновляет данные пользователя.
    Убрано поле updated_at, так как его нет в вашей схеме (ошибка PGRST204).
    """
    try:
        data = {
            "id": str(user_id),
            "currency": currency
        }
        if username:
            data["username"] = username
        supabase.table("bot_users").upsert(data).execute()
    except Exception as e:
        logger.error(f"❌ Ошибка синхронизации БД: {e}")

def db_get_all_users() -> List[int]:
    """Возвращает список ID всех пользователей для рассылки."""
    try:
        res = supabase.table("bot_users").select("id").execute()
        if res.data:
            return [int(row['id']) for row in res.data]
    except Exception as e:
        logger.error(f"DB Global Fetch Error: {e}")
    return []

# ==========================================
# 4. ВСПОМОГАТЕЛЬНАЯ ЛОГИКА UI
# ==========================================

def format_price(months: int, currency_code: str) -> str:
    """Рассчитывает стоимость в зависимости от курса."""
    curr = CURRENCIES.get(currency_code, CURRENCIES["RUB"])
    price = int(round(BASE_PRICE_RUB * PERIODS[months]["mult"] * curr["rate"]))
    return f"{price} {curr['symbol']}"

async def send_main_menu(m: Union[Message, CallbackQuery], user_id: int, is_edit: bool = False):
    """Отображает главное меню магазина."""
    user_currency = await db_get_currency(user_id)
    kb = InlineKeyboardBuilder()
    
    # Кнопки тарифов
    for m_count, info in PERIODS.items():
        price_text = format_price(m_count, user_currency)
        kb.row(InlineKeyboardButton(
            text=f"🔑 {info['label']} — {price_text}", 
            callback_data=f"buy_{m_count}"
        ))
    
    # Кнопка смены валюты
    kb.row(InlineKeyboardButton(text=f"🌍 Валюта: {user_currency}", callback_data="ui_set_currency"))
    
    text = (
        "🚀 <b>BotEngine Pro: Магазин лицензий</b>\n\n"
        "Выберите период подписки ниже. Лицензия активируется "
        "сразу после подтверждения оплаты администратором."
    )
    
    if is_edit and isinstance(m, CallbackQuery):
        await m.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    else:
        await m.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

# ==========================================
# 5. ОБРАБОТЧИКИ КОМАНД (HANDLERS)
# ==========================================

@dp.message(Command("start"))
async def cmd_start(m: Message):
    """Регистрация пользователя и вывод меню."""
    # Если это владелец - регистрируем скрытую команду рассылки
    if m.from_user.id == MY_OWNER_ID:
        admin_cmds = [
            BotCommand(command="start", description="🏠 Меню"),
            BotCommand(command="broadcast", description="📢 Рассылка")
        ]
        await bot.set_my_commands(admin_cmds, scope=BotCommandScopeChat(chat_id=m.from_user.id))
    
    # Сохраняем пользователя в БД
    curr = await db_get_currency(m.from_user.id)
    db_upsert_user(m.from_user.id, curr, m.from_user.username)
    
    await send_main_menu(m, m.from_user.id)

@dp.message(Command("broadcast"))
async def cmd_broadcast_text(m: Message):
    """Рассылка текстового сообщения."""
    if m.from_user.id != MY_OWNER_ID:
        return

    text = m.text.replace("/broadcast", "").strip()
    if not text:
        return await m.answer("⚠️ <b>Ошибка!</b> Введите текст: <code>/broadcast привет</code>", parse_mode="HTML")

    users = db_get_all_users()
    progress = await m.answer(f"⏳ Запуск рассылки на {len(users)} пользователей...")
    
    done, fail = 0, 0
    for uid in users:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
            done += 1
            await asyncio.sleep(0.05)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            await bot.send_message(uid, text, parse_mode="HTML")
            done += 1
        except Exception:
            fail += 1
            
    await progress.edit_text(f"📢 <b>Рассылка завершена!</b>\n\n✅ Успешно: {done}\n❌ Ошибок: {fail}", parse_mode="HTML")

@dp.message(F.photo, lambda m: m.from_user.id == MY_OWNER_ID and m.caption and m.caption.startswith("/broadcast"))
async def cmd_broadcast_photo(m: Message):
    """Рассылка фото с подписью (если команда в описании)."""
    text = m.caption.replace("/broadcast", "").strip()
    users = db_get_all_users()
    progress = await m.answer(f"⏳ Рассылка медиа на {len(users)} чел...")
    
    done = 0
    for uid in users:
        try:
            await bot.send_photo(uid, m.photo[-1].file_id, caption=text, parse_mode="HTML")
            done += 1
            await asyncio.sleep(0.05)
        except: continue
        
    await progress.edit_text(f"✅ Медиа-рассылка завершена! Доставлено: {done}")

# ==========================================
# 6. КОЛБЭКИ МАГАЗИНА
# ==========================================

@dp.callback_query(F.data == "ui_set_currency")
async def cb_select_curr(cb: CallbackQuery):
    kb = InlineKeyboardBuilder()
    for code in CURRENCIES.keys():
        kb.add(InlineKeyboardButton(text=code, callback_data=f"save_c_{code}"))
    kb.adjust(3)
    await cb.message.edit_text("🌍 <b>Выберите валюту цен:</b>", reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("save_c_"))
async def cb_save_curr(cb: CallbackQuery):
    code = cb.data.split("_")[2]
    db_upsert_user(cb.from_user.id, code, cb.from_user.username)
    await cb.answer(f"Валюта {code} сохранена!")
    await send_main_menu(cb, cb.from_user.id, is_edit=True)

@dp.callback_query(F.data.startswith("buy_"))
async def cb_buy_confirm(cb: CallbackQuery):
    months = int(cb.data.split("_")[1])
    curr = await db_get_currency(cb.from_user.id)
    price = format_price(months, curr)
    
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💳 Оплатить", url="https://www.donationalerts.com/r/dialoge_engine"))
    kb.row(InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"verify_pay_{months}"))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu"))
    
    text = (
        f"🛒 <b>Заказ лицензии: {PERIODS[months]['label']}</b>\n\n"
        f"Стоимость: <b>{price}</b>\n\n"
        "1. Переведите сумму по ссылке выше.\n"
        "2. Нажмите 'Я оплатил'.\n"
        "3. Дождитесь проверки администратором."
    )
    await cb.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "back_to_menu")
async def cb_back(cb: CallbackQuery):
    await send_main_menu(cb, cb.from_user.id, is_edit=True)

@dp.callback_query(F.data.startswith("verify_pay_"))
async def cb_admin_notify(cb: CallbackQuery):
    """Уведомление в админ-чат."""
    months = int(cb.data.split("_")[2])
    curr = await db_get_currency(cb.from_user.id)
    price = format_price(months, curr)
    
    akb = InlineKeyboardBuilder()
    akb.row(
        InlineKeyboardButton(text="✅ Выдать", callback_data=f"adm_ok_{cb.from_user.id}_{months}"),
        InlineKeyboardButton(text="❌ Отказ", callback_data=f"adm_no_{cb.from_user.id}")
    )
    
    # Отправляем в чат админов
    await bot.send_message(
        ADM_CHAT,
        f"💰 <b>Заявка на оплату!</b>\n\n"
        f"Юзер: {cb.from_user.full_name} (<code>{cb.from_user.id}</code>)\n"
        f"Тариф: {months} мес.\n"
        f"Сумма: {price}",
        reply_markup=akb.as_markup(),
        parse_mode="HTML"
    )
    await cb.message.edit_text("⏳ <b>Заявка отправлена админу.</b> Ожидайте уведомления.")

# ==========================================
# 7. АДМИН-ПАНЕЛЬ (API)
# ==========================================

@dp.callback_query(F.data.startswith("adm_ok_"))
async def cb_admin_approve(cb: CallbackQuery):
    """Генерация ключа через API."""
    _, _, uid, m_count = cb.data.split("_")
    await cb.message.edit_text(f"⚙️ Генерирую ключ для {uid}...")
    
    try:
        r = requests.post(
            f"{SRV_URL}/api/admin/generate-key",
            json={"months": int(m_count), "user_id": uid},
            headers={"x-admin-token": ADM_SECRET},
            timeout=15
        )
        if r.status_code == 200:
            key = r.json().get("key")
            await bot.send_message(
                uid, 
                f"🎉 <b>Оплата подтверждена!</b>\nВаш ключ: <code>{key}</code>", 
                parse_mode="HTML"
            )
            await cb.message.edit_text(f"✅ Ключ <code>{key}</code> выдан пользователю {uid}")
        else:
            await cb.message.edit_text(f"❌ Ошибка сервера: {r.status_code}")
    except Exception as e:
        logger.error(f"API Error: {e}")
        await cb.message.edit_text(f"❌ Ошибка связи с API: {e}")

@dp.callback_query(F.data.startswith("adm_no_"))
async def cb_admin_reject(cb: CallbackQuery):
    uid = cb.data.split("_")[2]
    try:
        await bot.send_message(uid, "❌ <b>Администратор отклонил ваш платеж.</b>")
    except: pass
    await cb.message.edit_text(f"🔴 Заявка {uid} отклонена.")

# ==========================================
# 8. ЗАПУСК
# ==========================================

async def main():
    logger.info("✨ Бот BotEngine запущен!")
    # Команды по умолчанию для всех
    await bot.set_my_commands([BotCommand(command="start", description="🏠 Магазин")])
    
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("👋 Бот остановлен.")
