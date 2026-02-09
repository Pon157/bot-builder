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
# 1. КОНФИГУРАЦИЯ И ГЛУБОКОЕ ЛОГИРОВАНИЕ
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
    """Железобетонное чтение .env с очисткой токенов"""
    path = os.path.join(BASE_DIR, '.env')
    conf = {}
    if not os.path.exists(path):
        logger.warning("⚠️ Файл .env отсутствует, используются дефолтные значения")
        return conf
    
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                val = v.strip().strip('"').strip("'")
                # Специальная логика извлечения токена
                if k.strip() == "ADMIN_BOT_TOKEN" and "root/" in val:
                    val = val.split("root/")[0].strip()
                conf[k.strip()] = val
    except Exception as e:
        logger.error(f"Критическая ошибка парсинга конфига: {e}")
    return conf

# Загрузка окружения
ENV = load_env_secure()
BOT_TOKEN = ENV.get("ADMIN_BOT_TOKEN")
SB_URL = ENV.get("SUPABASE_URL")
SB_KEY = ENV.get("SUPABASE_KEY")
ADM_CHAT = ENV.get("ADMIN_CHAT_ID")
ADM_SECRET = ENV.get("ADMIN_SECRET", "MRAKOTIK")
SRV_URL = ENV.get("SERVER_URL", "http://localhost:8000")

# Твой ID вшит в ядро кода
SUPER_ADMIN_ID = 5883703466

if not all([BOT_TOKEN, SB_URL, SB_KEY]):
    logger.critical("🛑 Ошибка: Проверьте .env (Токен или Supabase отсутствуют)")
    sys.exit(1)

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
    1: {"label": "1 Месяц", "mult": 0.9},
    3: {"label": "3 Месяца", "mult": 2.4},
    12: {"label": "1 Год", "mult": 7.9}
}

# ==========================================
# 3. ФУНКЦИИ БАЗЫ ДАННЫХ (SUPABASE)
# ==========================================

async def db_get_user_currency(user_id: int):
    """Получение валюты пользователя"""
    try:
        res = supabase.table("bot_users").select("currency").eq("id", str(user_id)).execute()
        if res.data and 'currency' in res.data[0]:
            return res.data[0]['currency']
    except Exception as e:
        logger.error(f"Ошибка DB: {e}")
    return "RUB"

def db_sync_user(user_id: int, currency: str, username: str = None):
    """Сохранение/обновление пользователя"""
    try:
        data = {"id": str(user_id), "currency": currency}
        if username:
            data["username"] = username
        supabase.table("bot_users").upsert(data).execute()
    except Exception as e:
        logger.error(f"Ошибка синхронизации: {e}")

def db_fetch_all_users():
    """Получение всех ID для рассылки"""
    try:
        res = supabase.table("bot_users").select("id").execute()
        return [int(u['id']) for u in res.data] if res.data else []
    except Exception:
        return []

# ==========================================
# 4. ЛОГИКА ОТОБРАЖЕНИЯ (UI)
# ==========================================

def calculate_current_price(months: int, code: str):
    """Расчет цены с учетом валюты"""
    c = CURRENCIES.get(code, CURRENCIES["RUB"])
    val = int(round(BASE_PRICE_RUB * PERIODS[months]["mult"] * c["rate"]))
    return f"{val} {c['symbol']}"

async def render_main_menu(m: Union[Message, CallbackQuery], user_id: int, edit: bool = False):
    """Отрисовка главного меню магазина"""
    curr = await db_get_user_currency(user_id)
    kb = InlineKeyboardBuilder()
    
    for m_count, info in PERIODS.items():
        price_tag = calculate_current_price(m_count, curr)
        kb.row(InlineKeyboardButton(text=f"🔑 {info['label']} — {price_tag}", callback_data=f"buy_{m_count}"))
    
    kb.row(InlineKeyboardButton(text=f"🌍 Валюта: {curr}", callback_data="ui_currency"))
    
    txt = "🚀 <b>BotEngine Pro: Лицензионный центр</b>\n\nВыберите нужный период подписки ниже:"
    if edit:
        await m.message.edit_text(txt, reply_markup=kb.as_markup(), parse_mode="HTML")
    else:
        await m.answer(txt, reply_markup=kb.as_markup(), parse_mode="HTML")

# ==========================================
# 5. ОБРАБОТЧИКИ СОБЫТИЙ (HANDLERS)
# ==========================================

@dp.message(Command("start"))
async def handler_start(m: Message):
    """Старт бота и скрытая настройка меню для админа"""
    # Если это ты - добавляем секретную кнопку рассылки в меню команд
    if m.from_user.id == SUPER_ADMIN_ID:
        admin_cmds = [
            BotCommand(command="start", description="🏠 Главная"),
            BotCommand(command="broadcast", description="📢 Скрытая рассылка")
        ]
        await bot.set_my_commands(admin_cmds, scope=BotCommandScopeChat(chat_id=m.from_user.id))
    
    db_sync_user(m.from_user.id, await db_get_user_currency(m.from_user.id), m.from_user.username)
    await render_main_menu(m, m.from_user.id)

@dp.message(Command("broadcast"))
async def handler_broadcast(m: Message):
    """Железобетонная рассылка с защитой от флуда"""
    if m.from_user.id != SUPER_ADMIN_ID:
        return # Полный игнор, если пишет не хозяин

    text = m.text.replace("/broadcast", "").strip()
    if not text:
        return await m.answer("⚠️ <b>Введите текст сообщения после команды!</b>", parse_mode="HTML")

    users = db_fetch_all_users()
    msg = await m.answer(f"⏳ <b>Запуск рассылки...</b>\nЦелей обнаружено: {len(users)}", parse_mode="HTML")
    
    done, fail = 0, 0
    for uid in users:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
            done += 1
            await asyncio.sleep(0.05) # Плавность отправки
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            await bot.send_message(uid, text, parse_mode="HTML")
            done += 1
        except (TelegramForbiddenError, Exception):
            fail += 1
    
    await msg.edit_text(f"✅ <b>Рассылка завершена!</b>\n\nДоставлено: {done}\nОшибок: {fail}", parse_mode="HTML")

@dp.callback_query(F.data == "ui_currency")
async def handler_change_curr(cb: CallbackQuery):
    kb = InlineKeyboardBuilder()
    for code in CURRENCIES.keys():
        kb.add(InlineKeyboardButton(text=code, callback_data=f"set_val_{code}"))
    kb.adjust(3)
    await cb.message.edit_text("🌍 <b>Выберите валюту для отображения цен:</b>", reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("set_val_"))
async def handler_save_curr(cb: CallbackQuery):
    code = cb.data.split("_")[2]
    db_sync_user(cb.from_user.id, code, cb.from_user.username)
    await cb.answer(f"Валюта {code} сохранена")
    await render_main_menu(cb, cb.from_user.id, edit=True)

@dp.callback_query(F.data.startswith("buy_"))
async def handler_buy_process(cb: CallbackQuery):
    """Оформление заказа"""
    months = int(cb.data.split("_")[1])
    curr = await db_get_user_currency(cb.from_user.id)
    price_str = calculate_current_price(months, curr)
    
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💳 Перейти к оплате", url="https://www.donationalerts.com/r/dialoge_engine"))
    kb.row(InlineKeyboardButton(text="Пользовательское соглашение", url="https://telegra.ph/Politika-vozvrata-i-licenzirovaniya-Refund-Policy-02-06"))
    kb.row(InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"verif_wait_{months}"))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="ui_back"))
    
    await cb.message.edit_text(
        f"🛒 <b>Оплата: {PERIODS[months]['label']}</b>\nСумма: <b>{price_str}</b>\n\n"
        f"1. Сделайте перевод по ссылке.\n2. Нажмите кнопку подтверждения.",
        reply_markup=kb.as_markup(), parse_mode="HTML", disable_web_page_preview=True
    )

@dp.callback_query(F.data == "ui_back")
async def handler_back(cb: CallbackQuery):
    await render_main_menu(cb, cb.from_user.id, edit=True)

@dp.callback_query(F.data.startswith("verif_wait_"))
async def handler_verify_request(cb: CallbackQuery):
    """Отправка заявки админу"""
    months = int(cb.data.split("_")[2])
    curr = await db_get_user_currency(cb.from_user.id)
    price = calculate_current_price(months, curr)
    
    akb = InlineKeyboardBuilder()
    akb.row(
        InlineKeyboardButton(text="✅ Выдать", callback_data=f"adm_ok_{cb.from_user.id}_{months}"),
        InlineKeyboardButton(text="❌ Отказ", callback_data=f"adm_no_{cb.from_user.id}")
    )
    
    await bot.send_message(
        ADM_CHAT,
        f"💰 <b>Заявка на ключ!</b>\nЮзер: {cb.from_user.full_name}\nID: <code>{cb.from_user.id}</code>\n"
        f"Тариф: {months} мес.\nСумма: {price}",
        reply_markup=akb.as_markup(), parse_mode="HTML"
    )
    await cb.message.edit_text("⏳ <b>Заявка отправлена. Ожидайте активации.</b>", parse_mode="HTML")

# ==========================================
# 6. АДМИН-ЛОГИКА (API ГЕНЕРАЦИЯ КЛЮЧЕЙ)
# ==========================================

@dp.callback_query(F.data.startswith("adm_ok_"))
async def handler_admin_approve(cb: CallbackQuery):
    """Подтверждение оплаты и генерация ключа"""
    _, _, uid, months = cb.data.split("_")
    await cb.message.edit_text(f"⚙️ Генерирую ключ для {uid}...")
    
    try:
        r = requests.post(
            f"{SRV_URL}/api/admin/generate-key",
            json={"months": int(months), "user_id": uid},
            headers={"x-admin-token": ADM_SECRET},
            timeout=15
        )
        if r.status_code == 200:
            key = r.json().get("key")
            await bot.send_message(uid, f"🎉 <b>Оплата принята!</b>\nВаш ключ: <code>{key}</code>", parse_mode="HTML")
            await cb.message.edit_text(f"✅ Ключ <code>{key}</code> отправлен пользователю {uid}")
        else:
            await cb.message.edit_text(f"❌ Ошибка сервера: {r.status_code}")
    except Exception as e:
        await cb.message.edit_text(f"❌ Ошибка связи: {e}")

@dp.callback_query(F.data.startswith("adm_no_"))
async def handler_admin_decline(cb: CallbackQuery):
    uid = cb.data.split("_")[2]
    try:
        await bot.send_message(uid, "❌ <b>Ваш платеж не подтвержден.</b>", parse_mode="HTML")
        await cb.message.edit_text(f"🔴 Заявка {uid} отклонена.")
    except:
        pass

# ==========================================
# 7. ТОЧКА ВХОДА
# ==========================================

async def main():
    logger.info("✨ бот запущен")
    # Глобальное меню (без рассылки для всех)
    await bot.set_my_commands([BotCommand(command="start", description="🏠 Магазин")])
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот выключен пользователем.")
