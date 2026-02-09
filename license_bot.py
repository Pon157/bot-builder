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
    BotCommand, BotCommandScopeChat, ReplyKeyboardRemove
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
    """Чтение .env с извлечением токена по инструкции [.env]"""
    path = os.path.join(BASE_DIR, '.env')
    conf = {}
    if not os.path.exists(path):
        logger.warning("⚠️ Файл .env не найден")
        return conf
    
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                val = v.strip().strip('"').strip("'")
                # Специальная логика токена
                if k.strip() == "ADMIN_BOT_TOKEN" and "root/" in val:
                    val = val.split("root/")[0].strip()
                conf[k.strip()] = val
    except Exception as e:
        logger.error(f"Ошибка чтения конфига: {e}")
    return conf

# Загрузка
ENV = load_env_secure()
BOT_TOKEN = ENV.get("ADMIN_BOT_TOKEN")
SB_URL = ENV.get("SUPABASE_URL")
SB_KEY = ENV.get("SUPABASE_KEY")
ADM_CHAT = ENV.get("ADMIN_CHAT_ID")
ADM_SECRET = ENV.get("ADMIN_SECRET", "MRAKOTIK")
SRV_URL = ENV.get("SERVER_URL", "http://localhost:8000")

# Твой ID вшит в код «намертво»
SUPER_ADMIN_ID = 5883703466

if not all([BOT_TOKEN, SB_URL, SB_KEY]):
    logger.critical("🛑 Критическая ошибка: Проверьте параметры Supabase и Токен!")
    sys.exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
supabase: Client = create_client(SB_URL, SB_KEY)

# ==========================================
# 2. ЭКОНОМИКА
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
# 3. ФУНКЦИИ БАЗЫ ДАННЫХ
# ==========================================

async def db_get_currency(user_id: int):
    try:
        res = supabase.table("bot_users").select("currency").eq("id", str(user_id)).execute()
        return res.data[0]['currency'] if res.data else "RUB"
    except: return "RUB"

def db_upsert_user(user_id: int, currency: str, username: str = None):
    try:
        data = {"id": str(user_id), "currency": currency}
        if username: data["username"] = username
        supabase.table("bot_users").upsert(data).execute()
    except Exception as e: logger.error(f"DB Error: {e}")

def db_get_all_ids():
    try:
        res = supabase.table("bot_users").select("id").execute()
        return [int(u['id']) for u in res.data] if res.data else []
    except: return []

# ==========================================
# 4. ЛОГИКА МЕНЮ
# ==========================================

def get_price(m_count, c_code):
    c = CURRENCIES.get(c_code, CURRENCIES["RUB"])
    val = int(round(BASE_PRICE_RUB * PERIODS[m_count]["mult"] * c["rate"]))
    return f"{val} {c['symbol']}"

async def render_main_menu(m: Union[Message, CallbackQuery], user_id: int, edit: bool = False):
    curr = await db_get_currency(user_id)
    kb = InlineKeyboardBuilder()
    for months, info in PERIODS.items():
        kb.row(InlineKeyboardButton(text=f"🔑 {info['label']} — {get_price(months, curr)}", callback_data=f"buy_{months}"))
    kb.row(InlineKeyboardButton(text=f"🌍 Валюта: {curr}", callback_data="ui_curr"))
    
    txt = "🚀 <b>BotEngine Pro</b>\n\nВыберите период лицензии для вашего бота:"
    if edit: await m.message.edit_text(txt, reply_markup=kb.as_markup(), parse_mode="HTML")
    else: await m.answer(txt, reply_markup=kb.as_markup(), parse_mode="HTML")

# ==========================================
# 5. ОБРАБОТЧИКИ
# ==========================================

@dp.message(Command("start"))
async def cmd_start(m: Message):
    # Сокрытие команды /broadcast через установку меню только для тебя
    if m.from_user.id == SUPER_ADMIN_ID:
        admin_cmds = [BotCommand(command="start", description="🏠 Меню"), BotCommand(command="broadcast", description="📢 Рассылка")]
        await bot.set_my_commands(admin_cmds, scope=BotCommandScopeChat(chat_id=m.from_user.id))
    
    db_upsert_user(m.from_user.id, await db_get_currency(m.from_user.id), m.from_user.username)
    await render_main_menu(m, m.from_user.id)

@dp.message(Command("broadcast"))
async def cmd_broadcast(m: Message):
    # Жесткая проверка ID
    if m.from_user.id != SUPER_ADMIN_ID:
        return # Обычный юзер даже не получит ответа

    text = m.text.replace("/broadcast", "").strip()
    if not text:
        return await m.answer("⚠️ Введите текст сообщения!")

    users = db_get_all_ids()
    status = await m.answer(f"⏳ Начинаю рассылку на {len(users)} чел...")
    
    ok, err = 0, 0
    for uid in users:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
            ok += 1
            await asyncio.sleep(0.05)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            await bot.send_message(uid, text, parse_mode="HTML")
            ok += 1
        except: err += 1
    
    await status.edit_text(f"✅ Рассылка завершена!\nУспешно: {ok}\nОшибок: {err}")

@dp.callback_query(F.data == "ui_curr")
async def ui_curr(cb: CallbackQuery):
    kb = InlineKeyboardBuilder()
    for c in CURRENCIES.keys(): kb.add(InlineKeyboardButton(text=c, callback_data=f"set_c_{c}"))
    kb.adjust(3)
    await cb.message.edit_text("🌍 <b>Выберите валюту:</b>", reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("set_c_"))
async def set_curr(cb: CallbackQuery):
    c = cb.data.split("_")[2]
    db_upsert_user(cb.from_user.id, c, cb.from_user.username)
    await render_main_menu(cb, cb.from_user.id, edit=True)

@dp.callback_query(F.data.startswith("buy_"))
async def buy_choice(cb: CallbackQuery):
    m = int(cb.data.split("_")[1])
    p = get_price(m, await db_get_currency(cb.from_user.id))
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💳 Оплата", url="https://www.donationalerts.com/r/dialoge_engine"))
    kb.row(InlineKeyboardButton(text="✅ Проверить платеж", callback_data=f"check_{m}"))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back"))
    await cb.message.edit_text(f"🛒 <b>{PERIODS[m]['label']}</b>\nК оплате: <b>{p}</b>", reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "back")
async def back(cb: CallbackQuery):
    await render_main_menu(cb, cb.from_user.id, edit=True)

@dp.callback_query(F.data.startswith("check_"))
async def check(cb: CallbackQuery):
    m = int(cb.data.split("_")[1])
    p = get_price(m, await db_get_currency(cb.from_user.id))
    akb = InlineKeyboardBuilder()
    akb.row(InlineKeyboardButton(text="✅ Выдать", callback_data=f"a_ok_{cb.from_user.id}_{m}"),
            InlineKeyboardButton(text="❌ Отказ", callback_data=f"a_no_{cb.from_user.id}"))
    
    await bot.send_message(ADM_CHAT, f"💰 <b>Заявка!</b>\nЮзер: {cb.from_user.id}\nТариф: {m} мес\nСумма: {p}", reply_markup=akb.as_markup(), parse_mode="HTML")
    await cb.message.edit_text("⏳ <b>Заявка отправлена администратору.</b>")

# ==========================================
# 6. АДМИН ПАНЕЛЬ
# ==========================================

@dp.callback_query(F.data.startswith("a_ok_"))
async def a_ok(cb: CallbackQuery):
    _, _, uid, m = cb.data.split("_")
    await cb.message.edit_text("⚙️ Генерация...")
    try:
        r = requests.post(f"{SRV_URL}/api/admin/generate-key", 
                          json={"months": int(m), "user_id": uid}, 
                          headers={"x-admin-token": ADM_SECRET}, timeout=15)
        if r.status_code == 200:
            key = r.json().get("key")
            await bot.send_message(uid, f"🎉 <b>Лицензия выдана!</b>\nКлюч: <code>{key}</code>", parse_mode="HTML")
            await cb.message.edit_text(f"✅ Выдано пользователю {uid}")
        else: await cb.message.edit_text(f"❌ Ошибка API: {r.status_code}")
    except Exception as e: await cb.message.edit_text(f"❌ Ошибка: {e}")

@dp.callback_query(F.data.startswith("a_no_"))
async def a_no(cb: CallbackQuery):
    uid = cb.data.split("_")[2]
    try:
        await bot.send_message(uid, "❌ <b>Ваш платеж не подтвержден.</b>")
        await cb.message.edit_text(f"🔴 Отклонено {uid}")
    except: pass

# ==========================================
# 7. СТАРТ
# ==========================================

async def main():
    logger.info("🚀 Бот запущен")
    # Обычное меню для всех (без broadcast)
    user_cmds = [BotCommand(command="start", description="🏠 Магазин")]
    await bot.set_my_commands(user_cmds)
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try: asyncio.run(main())
    except: logger.info("Бот выключен")
