import os
import asyncio
import logging
import sys
import requests
import json
from datetime import datetime
from typing import List, Optional, Union

from aiogram import Bot, Dispatcher, types, F, html
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
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("LicenseBotEngine")

def load_env_secure():
    """Чтение .env с учетом инструкции по извлечению токена."""
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
                # Извлечение токена: берем часть до 'root/'
                if k.strip() == "ADMIN_BOT_TOKEN" and "root/" in val:
                    val = val.split("root/")[0].strip()
                conf[k.strip()] = val
    except Exception as e:
        logger.error(f"❌ Ошибка парсинга .env: {e}")
    return conf

CONFIG = load_env_secure()
BOT_TOKEN = CONFIG.get("ADMIN_BOT_TOKEN")
SB_URL = CONFIG.get("SUPABASE_URL")
SB_KEY = CONFIG.get("SUPABASE_KEY")
ADM_CHAT = CONFIG.get("ADMIN_CHAT_ID")
ADM_SECRET = CONFIG.get("ADMIN_SECRET")
SRV_URL = CONFIG.get("SERVER_URL")

# ID для полных прав и рассылки
MY_OWNER_ID = 5883703466

if not all([BOT_TOKEN, SB_URL, SB_KEY]):
    logger.critical("🛑 Критическая ошибка: проверьте переменные в .env")
    sys.exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
supabase: Client = create_client(SB_URL, SB_KEY)

# ==========================================
# 2. ЭКОНОМИЧЕСКАЯ МОДЕЛЬ
# ==========================================
BASE_PRICE_RUB = 91
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
# 3. ФУНКЦИИ БАЗЫ ДАННЫХ
# ==========================================

async def db_get_currency(user_id: int) -> str:
    try:
        res = supabase.table("bot_users").select("currency").eq("id", str(user_id)).execute()
        if res.data and 'currency' in res.data[0]:
            return res.data[0]['currency']
    except Exception as e:
        logger.error(f"DB Error (get_curr): {e}")
    return "RUB"

def db_upsert_user(user_id: int, currency: str, username: str = None):
    """Синхронизация пользователя без лишних полей (типа updated_at)."""
    try:
        data = {"id": str(user_id), "currency": currency}
        if username: data["username"] = username
        supabase.table("bot_users").upsert(data).execute()
    except Exception as e:
        logger.error(f"❌ Ошибка БД (upsert): {e}")

def db_get_all_users() -> List[int]:
    try:
        res = supabase.table("bot_users").select("id").execute()
        return [int(row['id']) for row in res.data] if res.data else []
    except Exception as e:
        logger.error(f"DB Error (get_all): {e}")
        return []

# ==========================================
# 4. ВСПОМОГАТЕЛЬНАЯ ЛОГИКА UI
# ==========================================

def format_price(months: int, currency_code: str) -> str:
    curr = CURRENCIES.get(currency_code, CURRENCIES["RUB"])
    price = int(round(BASE_PRICE_RUB * PERIODS[months]["mult"] * curr["rate"]))
    return f"{price} {curr['symbol']}"

async def send_main_menu(m: Union[Message, CallbackQuery], user_id: int, is_edit: bool = False):
    user_currency = await db_get_currency(user_id)
    kb = InlineKeyboardBuilder()
    for m_count, info in PERIODS.items():
        kb.row(InlineKeyboardButton(
            text=f"🔑 {info['label']} — {format_price(m_count, user_currency)}", 
            callback_data=f"buy_{m_count}"
        ))
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
    if m.from_user.id == MY_OWNER_ID:
        await bot.set_my_commands(
            [BotCommand(command="start", description="🏠 Меню"), 
             BotCommand(command="broadcast", description="📢 Рассылка")],
            scope=BotCommandScopeChat(chat_id=m.from_user.id)
        )
    curr = await db_get_currency(m.from_user.id)
    db_upsert_user(m.from_user.id, curr, m.from_user.username)
    await send_main_menu(m, m.from_user.id)

@dp.message(Command("broadcast"))
async def cmd_broadcast_text(m: Message):
    """Рассылка только текста (через /broadcast Текст)"""
    if m.from_user.id != MY_OWNER_ID: return
    text = m.text.replace("/broadcast", "").strip()
    if not text:
        return await m.answer("⚠️ <b>Введите текст после команды!</b>", parse_mode="HTML")
    
    users = db_get_all_users()
    progress = await m.answer(f"⏳ Рассылка текста на {len(users)} чел...")
    done, fail = 0, 0
    for uid in users:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
            done += 1
            await asyncio.sleep(0.05)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            await bot.send_message(uid, text, parse_mode="HTML"); done += 1
        except Exception: fail += 1
    await progress.edit_text(f"📢 <b>Рассылка завершена!</b>\n\n✅ Доставлено: {done}\n❌ Ошибок: {fail}", parse_mode="HTML")

@dp.message(F.photo, lambda m: m.from_user.id == MY_OWNER_ID and m.caption and m.caption.startswith("/broadcast"))
async def cmd_broadcast_photo(m: Message):
    """Рассылка фото с описанием (команда должна быть в подписи к фото)"""
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
    await progress.edit_text(f"✅ Фото разослано! Доставлено: {done}")

# ==========================================
# 6. КОЛБЭКИ И ОПЛАТА
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
    price = format_price(months, await db_get_currency(cb.from_user.id))
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💳 Оплатить", url="https://www.donationalerts.com/r/dialoge_engine"))
    kb.row(InlineKeyboardButton(text="Правила лицензирования и возврата", url="https://telegra.ph/Politika-vozvrata-i-licenzirovaniya-Refund-Policy-02-06"))
    kb.row(InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"verify_pay_{months}"))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu"))
    text = (
        f"🛒 <b>Заказ лицензии: {PERIODS[months]['label']}</b>\n\n"
        f"Стоимость: <b>{price}</b>\n\n"
        "1. Переведите сумму по ссылке выше.\n"
        "2. Нажмите 'Я оплатил'.\n"
        "3. Ожидайте подтверждения админом."
    )
    await cb.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "back_to_menu")
async def cb_back(cb: CallbackQuery):
    await send_main_menu(cb, cb.from_user.id, is_edit=True)

@dp.callback_query(F.data.startswith("verify_pay_"))
async def cb_admin_notify(cb: CallbackQuery):
    months = int(cb.data.split("_")[2])
    price = format_price(months, await db_get_currency(cb.from_user.id))
    akb = InlineKeyboardBuilder()
    akb.row(InlineKeyboardButton(text="✅ Выдать", callback_data=f"adm_ok_{cb.from_user.id}_{months}"),
            InlineKeyboardButton(text="❌ Отказ", callback_data=f"adm_no_{cb.from_user.id}"))
    
    await bot.send_message(
        ADM_CHAT, 
        f"💰 <b>Заявка!</b>\n\n"
        f"Юзер: {cb.from_user.full_name} (<code>{cb.from_user.id}</code>)\n"
        f"Тариф: {months} мес.\n"
        f"Сумма: {price}", 
        reply_markup=akb.as_markup(), 
        parse_mode="HTML"
    )
    await cb.message.edit_text("⏳ Заявка отправлена. Ожидайте ключ.")

@dp.callback_query(F.data.startswith("adm_ok_"))
async def cb_admin_approve(cb: CallbackQuery):
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
                f"🎉 <b>Оплата принята!</b>\nВаш ключ: <code>{key}</code>", 
                parse_mode="HTML"
            )
            await cb.message.edit_text(f"✅ Ключ <code>{key}</code> выдан {uid}", parse_mode="HTML")
        else: 
            await cb.message.edit_text(f"❌ Ошибка API: {r.status_code}")
    except Exception as e: 
        await cb.message.edit_text(f"❌ Ошибка связи: {e}")

@dp.callback_query(F.data.startswith("adm_no_"))
async def cb_admin_reject(cb: CallbackQuery):
    uid = cb.data.split("_")[2]
    try:
        await bot.send_message(uid, "❌ <b>Ваш платеж отклонен администратором.</b>", parse_mode="HTML")
    except: pass
    await cb.message.edit_text(f"🔴 Заявка {uid} отклонена.")

# ==========================================
# 7. ЗАПУСК
# ==========================================

async def main():
    logger.info("✨ Лицензионный бот успешно запущен!")
    # Общее меню команд для всех
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
