import os
import asyncio
import logging
import sys
import requests
import json
from datetime import datetime
from typing import List, Optional, Union

from aiogram import Bot, Dispatcher, types, F, html
from aiogram.filters import Command, StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import (
    InlineKeyboardButton, CallbackQuery, Message, 
    BotCommand, BotCommandScopeChat
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
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
ADM_CHAT = CONFIG.get("ADMIN_CHAT_ID") # Основной чат админа (для логов и обычных продаж)
ADM_SECRET = CONFIG.get("ADMIN_SECRET", "MRAKOTIK")
SRV_URL = CONFIG.get("SERVER_URL", "http://localhost:8000")

MY_OWNER_ID = 5883703466

# ==========================================
# 1.1 НАСТРОЙКИ ПАРТНЕРСКОЙ ПРОГРАММЫ
# ==========================================
# Здесь настраиваются промокоды и поведение для них
PARTNERS_CONFIG = {
    "PARTNER2026": { # Сам промокод (вводить в боте)
        "name": "Студия Alpha",
        "payment_url": "https://www.donationalerts.com/r/partner_alpha", # Ссылка на оплату партнера
        "admin_chat_id": -100123456789, # ID чата партнера (куда придет заявка "Проверить оплату")
        "menu_title": "🚀 <b>BotEngine: Partner Edition (Alpha)</b>\nСпециальные условия от партнера.",
        "discount_percent": 0 # Можно добавить логику скидок, пока просто для инфо
    },
    "SUPERDEV": {
        "name": "Super Dev Team",
        "payment_url": "https://yoomoney.ru/to/12345678",
        "admin_chat_id": ADM_CHAT, # Можно использовать тот же чат, но другую ссылку
        "menu_title": "💎 <b>BotEngine Premium</b>\nВы активировали код разработчика.",
        "discount_percent": 0
    }
}

if not all([BOT_TOKEN, SB_URL, SB_KEY]):
    logger.critical("🛑 Критическая ошибка: проверьте переменные в .env")
    sys.exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage()) # Добавили хранилище для FSM
supabase: Client = create_client(SB_URL, SB_KEY)

# ==========================================
# 2. ЭКОНОМИЧЕСКАЯ МОДЕЛЬ И СОСТОЯНИЯ
# ==========================================
class PromoState(StatesGroup):
    waiting_for_code = State()

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

async def db_get_user_info(user_id: int):
    """Возвращает валюту и промо-группу"""
    try:
        res = supabase.table("bot_users").select("currency, promo_group").eq("id", str(user_id)).execute()
        if res.data:
            return res.data[0]
    except Exception as e:
        logger.error(f"DB Error (get_info): {e}")
    return {"currency": "RUB", "promo_group": None}

def db_upsert_user(user_id: int, currency: str = None, username: str = None, promo_group: str = None):
    """Обновляет данные. Если параметр None, стараемся не затереть, но upsert требует полных данных для вставки."""
    try:
        # Сначала получаем текущие данные, чтобы не затереть существующее
        existing = supabase.table("bot_users").select("*").eq("id", str(user_id)).execute()
        
        data = {"id": str(user_id)}
        
        # Если юзер уже есть, берем старые значения как базу
        if existing.data:
            current = existing.data[0]
            data["currency"] = current.get("currency", "RUB")
            data["username"] = current.get("username", username)
            data["promo_group"] = current.get("promo_group", None)
        else:
            data["currency"] = "RUB"
            data["promo_group"] = None
            
        # Обновляем тем, что передали явно
        if currency: data["currency"] = currency
        if username: data["username"] = username
        if promo_group: data["promo_group"] = promo_group
        
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
    user_info = await db_get_user_info(user_id)
    user_currency = user_info.get("currency", "RUB")
    promo_code = user_info.get("promo_group")
    
    # Определяем настройки в зависимости от промокода
    is_partner_mode = False
    menu_title = "🚀 <b>BotEngine Pro: Магазин лицензий</b>\n\nВыберите период подписки ниже."
    
    if promo_code and promo_code in PARTNERS_CONFIG:
        is_partner_mode = True
        partner_data = PARTNERS_CONFIG[promo_code]
        menu_title = partner_data.get("menu_title", menu_title)

    kb = InlineKeyboardBuilder()
    
    # Кнопки товаров
    for m_count, info in PERIODS.items():
        kb.row(InlineKeyboardButton(
            text=f"🔑 {info['label']} — {format_price(m_count, user_currency)}", 
            callback_data=f"buy_{m_count}"
        ))
    
    # Кнопка валюты всегда есть
    kb.row(InlineKeyboardButton(text=f"🌍 Валюта: {user_currency}", callback_data="ui_set_currency"))
    
    # Если НЕ партнерский режим, показываем кнопку ввода промокода
    if not is_partner_mode:
        kb.row(InlineKeyboardButton(text="🎁 Ввести промокод партнера", callback_data="ui_enter_promo"))
    
    if is_edit and isinstance(m, CallbackQuery):
        await m.message.edit_text(menu_title, reply_markup=kb.as_markup(), parse_mode="HTML")
    else:
        await m.answer(menu_title, reply_markup=kb.as_markup(), parse_mode="HTML")

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
    # При старте просто обновляем юзернейм, не меняя валюту и промо
    db_upsert_user(m.from_user.id, username=m.from_user.username)
    await send_main_menu(m, m.from_user.id)

# --- ЛОГИКА ПРОМОКОДОВ ---
@dp.callback_query(F.data == "ui_enter_promo")
async def cb_enter_promo(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("✍️ <b>Введите партнерский код:</b>\n\n(Напишите его в чат)")
    await state.set_state(PromoState.waiting_for_code)

@dp.message(PromoState.waiting_for_code)
async def process_promo_code(m: Message, state: FSMContext):
    code = m.text.strip().upper() # Приводим к верхнему регистру
    
    if code in PARTNERS_CONFIG:
        # Сохраняем в БД привязку к промокоду
        db_upsert_user(m.from_user.id, promo_group=code)
        await state.clear()
        
        partner_name = PARTNERS_CONFIG[code]['name']
        await m.answer(f"✅ <b>Код принят!</b>\nВы перешли в меню партнера: {partner_name}")
        await send_main_menu(m, m.from_user.id)
    else:
        await m.answer("❌ Неверный код. Попробуйте снова или нажмите /start для отмены.")

# --- РАССЫЛКА ---
@dp.message(Command("broadcast"))
async def cmd_broadcast_text(m: Message):
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
    db_upsert_user(cb.from_user.id, currency=code) # Используем именованный аргумент
    await cb.answer(f"Валюта {code} сохранена!")
    await send_main_menu(cb, cb.from_user.id, is_edit=True)

@dp.callback_query(F.data.startswith("buy_"))
async def cb_buy_confirm(cb: CallbackQuery):
    months = int(cb.data.split("_")[1])
    user_info = await db_get_user_info(cb.from_user.id)
    currency = user_info.get("currency", "RUB")
    promo = user_info.get("promo_group")
    
    price = format_price(months, currency)
    
    # Определяем ссылки и параметры в зависимости от партнера
    payment_url = "https://www.donationalerts.com/r/dialoge_engine" # Default
    
    if promo and promo in PARTNERS_CONFIG:
        payment_url = PARTNERS_CONFIG[promo].get("payment_url", payment_url)
    
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💳 Оплатить", url=payment_url))
    kb.row(InlineKeyboardButton(text="Правила лицензирования", url="https://telegra.ph/Politika-vozvrata-i-licenzirovaniya-Refund-Policy-02-06"))
    kb.row(InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"verify_pay_{months}"))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu"))
    
    text = (
        f"🛒 <b>Заказ лицензии: {PERIODS[months]['label']}</b>\n\n"
        f"Стоимость: <b>{price}</b>\n\n"
        "1. Переведите сумму по ссылке выше.\n"
        "2. Нажмите 'Я оплатил'.\n"
        "3. Ожидайте подтверждения."
    )
    await cb.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "back_to_menu")
async def cb_back(cb: CallbackQuery):
    await send_main_menu(cb, cb.from_user.id, is_edit=True)

@dp.callback_query(F.data.startswith("verify_pay_"))
async def cb_admin_notify(cb: CallbackQuery):
    months = int(cb.data.split("_")[2])
    user_info = await db_get_user_info(cb.from_user.id)
    currency = user_info.get("currency", "RUB")
    promo = user_info.get("promo_group")
    
    price = format_price(months, currency)
    
    # Куда отправлять заявку?
    target_admin_chat = ADM_CHAT
    partner_name = "BotEngine (Standard)"
    
    if promo and promo in PARTNERS_CONFIG:
        target_admin_chat = PARTNERS_CONFIG[promo].get("admin_chat_id", ADM_CHAT)
        partner_name = PARTNERS_CONFIG[promo].get("name", "Unknown Partner")

    akb = InlineKeyboardBuilder()
    akb.row(InlineKeyboardButton(text="✅ Выдать", callback_data=f"adm_ok_{cb.from_user.id}_{months}"),
            InlineKeyboardButton(text="❌ Отказ", callback_data=f"adm_no_{cb.from_user.id}"))
    
    admin_text = (
        f"💰 <b>Заявка ({partner_name})!</b>\n\n"
        f"Юзер: {cb.from_user.full_name} (<code>{cb.from_user.id}</code>)\n"
        f"Тариф: {months} мес.\n"
        f"Сумма: {price}\n"
        f"Код: {promo if promo else 'Нет'}"
    )
    
    # 1. Отправка ответственному (Партнеру или Главному)
    try:
        await bot.send_message(
            target_admin_chat, 
            admin_text, 
            reply_markup=akb.as_markup(), 
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Не удалось отправить заявку в чат {target_admin_chat}: {e}")
        await cb.answer("Ошибка отправки заявки, свяжитесь с поддержкой.", show_alert=True)
        return

    # 2. Логирование Главному Админу (если заявка ушла партнеру, чтобы мы видели движ)
    # Преобразуем оба ID в строки для надежного сравнения
    if str(target_admin_chat) != str(ADM_CHAT):
        try:
            await bot.send_message(
                ADM_CHAT, 
                f"📝 <b>[LOG] Заявка у партнера {partner_name}</b>\n"
                f"Юзер: {cb.from_user.id}, Сумма: {price}",
                parse_mode="HTML"
            )
        except: pass

    await cb.message.edit_text("⏳ Заявка отправлена на проверку. Ожидайте ключ.")

@dp.callback_query(F.data.startswith("adm_ok_"))
async def cb_admin_approve(cb: CallbackQuery):
    # Эта функция срабатывает, когда админ (партнер или главный) нажимает "Выдать"
    _, _, uid, m_count = cb.data.split("_")
    
    # Проверка прав: нажимать могут только админы в чатах, куда бот добавлен.
    # Можно добавить проверку ID нажавшего, но пока оставим как есть.
    
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
            await cb.message.edit_text(f"✅ Ключ <code>{key}</code> выдан {uid}\nАдмин: {cb.from_user.full_name}", parse_mode="HTML")
            
            # Если выдал партнер, можно уведомлять главного админа о факте выдачи (опционально)
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
    await cb.message.edit_text(f"🔴 Заявка {uid} отклонена админом {cb.from_user.full_name}.")

# ==========================================
# 7. ЗАПУСК
# ==========================================

async def main():
    logger.info("✨ Лицензионный бот успешно запущен!")
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
