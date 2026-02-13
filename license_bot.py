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
# 1. КОНФИГУРАЦИЯ
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
    if not os.path.exists(path): return conf
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line: continue
                k, v = line.split('=', 1)
                val = v.strip().strip('"').strip("'")
                if k.strip() == "ADMIN_BOT_TOKEN" and "root/" in val:
                    val = val.split("root/")[0].strip()
                conf[k.strip()] = val
    except Exception: pass
    return conf

CONFIG = load_env_secure()
BOT_TOKEN = CONFIG.get("ADMIN_BOT_TOKEN")
SB_URL = CONFIG.get("SUPABASE_URL")
SB_KEY = CONFIG.get("SUPABASE_KEY")
ADM_CHAT = CONFIG.get("ADMIN_CHAT_ID")
ADM_SECRET = CONFIG.get("ADMIN_SECRET", "MRAKOTIK")
SRV_URL = CONFIG.get("SERVER_URL", "http://localhost:8000")
MY_OWNER_ID = 5883703466

# ==========================================
# 1.1 НАСТРОЙКИ ПАРТНЕРОВ И ЗВЕЗД
# ==========================================

# 1 Telegram Star ~ 1.6 - 2.0 RUB (курс плавающий, задаем фиксированный для бота)
STARS_RATE = 1.79 # Значит 1 рубль = 1 / 2.5 звезд (или наоборот, настроим ниже в CURRENCIES)

PARTNERS_CONFIG = {
    "NOVASTUDIO": { 
        "name": "NOVA CREATIVE STUDIO",
        "payment_url": "https://t.me/G_78_8_4_5_89254826783g", # Ссылка на оплату звездами (или инструкция)
        "admin_chat_id": -1003784801472, 
        "menu_title": "🌟 <b>Оплата через Telegram Stars</b> NOVA CREATIVE STUDIO!",
        "force_currency": "XTR" # Принудительно включаем звезды в этом меню
    }
}

if not all([BOT_TOKEN, SB_URL, SB_KEY]): sys.exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
supabase: Client = create_client(SB_URL, SB_KEY)

class PromoState(StatesGroup):
    waiting_for_code = State()

# ==========================================
# 2. ЭКОНОМИКА (ДОБАВИЛИ XTR)
# ==========================================
BASE_PRICE_RUB = 91

CURRENCIES = {
    "RUB": {"symbol": "₽", "rate": 1.0},
    "USD": {"symbol": "$", "rate": 0.011},
    "EUR": {"symbol": "€", "rate": 0.010},
    "BYN": {"symbol": "BYN", "rate": 0.035},
    "UAH": {"symbol": "₴", "rate": 0.43},
    "KZT": {"symbol": "₸", "rate": 5.20}
    "XTR": {"symbol": "⭐️", "rate": 1.79} 
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
    try:
        res = supabase.table("bot_users").select("currency, promo_group").eq("id", str(user_id)).execute()
        if res.data: return res.data[0]
    except Exception as e: logger.error(f"DB Error: {e}")
    return {"currency": "RUB", "promo_group": None}

def db_upsert_user(user_id: int, currency: str = None, username: str = None, promo_group: str = None):
    try:
        existing = supabase.table("bot_users").select("*").eq("id", str(user_id)).execute()
        data = {"id": str(user_id)}
        if existing.data:
            current = existing.data[0]
            data["currency"] = current.get("currency", "RUB")
            data["username"] = current.get("username", username)
            data["promo_group"] = current.get("promo_group", None)
        else:
            data["currency"] = "RUB"
            data["promo_group"] = None
            
        if currency: data["currency"] = currency
        if username: data["username"] = username
        if promo_group: data["promo_group"] = promo_group
        
        supabase.table("bot_users").upsert(data).execute()
    except Exception: pass

def db_get_all_users() -> List[int]:
    try:
        res = supabase.table("bot_users").select("id").execute()
        return [int(row['id']) for row in res.data] if res.data else []
    except Exception: return []

# ==========================================
# 4. ЛОГИКА МЕНЮ (ПЕРЕКЛЮЧЕНИЕ)
# ==========================================

def format_price(months: int, currency_code: str) -> str:
    curr = CURRENCIES.get(currency_code, CURRENCIES["RUB"])
    # Округляем до целого
    price = int(round(BASE_PRICE_RUB * PERIODS[months]["mult"] * curr["rate"]))
    return f"{price} {curr['symbol']}"

async def send_menu_interface(m: Union[Message, CallbackQuery], user_id: int, mode: str = "standard"):
    """
    mode: 'standard' (обычное) или 'partner' (партнерское)
    """
    user_info = await db_get_user_info(user_id)
    saved_promo = user_info.get("promo_group")
    
    # Настройки по умолчанию (Standard)
    current_currency = user_info.get("currency", "RUB")
    menu_title = "🚀 <b>BotEngine Pro: Магазин</b>\n\nВыберите тариф:"
    is_partner_active = False

    # Если запрошен режим ПАРТНЕРА и он есть у юзера
    if mode == "partner" and saved_promo and saved_promo in PARTNERS_CONFIG:
        p_conf = PARTNERS_CONFIG[saved_promo]
        menu_title = p_conf.get("menu_title", menu_title)
        # Если партнер форсирует валюту (например, Звезды)
        if "force_currency" in p_conf:
            current_currency = p_conf["force_currency"]
        is_partner_active = True
    
    kb = InlineKeyboardBuilder()
    
    # Генерация кнопок покупки. 
    # В callback добавляем префикс режима (std или prt), чтобы знать, как обрабатывать оплату
    prefix = "prt" if is_partner_active else "std"
    
    for m_count, info in PERIODS.items():
        kb.row(InlineKeyboardButton(
            text=f"🔑 {info['label']} — {format_price(m_count, current_currency)}", 
            callback_data=f"buy_{prefix}_{m_count}"
        ))
    
    # Управление валютой (только в стандартном режиме)
    if not is_partner_active:
        kb.row(InlineKeyboardButton(text=f"🌍 Валюта: {current_currency}", callback_data="ui_set_currency"))
    
    # === КНОПКИ ПЕРЕКЛЮЧЕНИЯ ===
    if is_partner_active:
        # Мы в партнерке -> Кнопка "Домой"
        kb.row(InlineKeyboardButton(text="🏠 В основное меню", callback_data="switch_to_std"))
    elif saved_promo:
        # Мы дома, но есть промокод -> Кнопка "В партнерку"
        # Получаем имя партнера для кнопки
        p_name = PARTNERS_CONFIG.get(saved_promo, {}).get("name", "Партнер")
        kb.row(InlineKeyboardButton(text=f"🌟 {p_name}", callback_data="switch_to_prt"))
    else:
        # Мы дома, промокода нет -> Кнопка ввода
        kb.row(InlineKeyboardButton(text="🎁 Ввести промокод", callback_data="ui_enter_promo"))

    if isinstance(m, CallbackQuery):
        # Чтобы не мигало, если текст тот же, можно проверить, но edit_text надежнее
        await m.message.edit_text(menu_title, reply_markup=kb.as_markup(), parse_mode="HTML")
    else:
        await m.answer(menu_title, reply_markup=kb.as_markup(), parse_mode="HTML")

# ==========================================
# 5. HANDLERS
# ==========================================

@dp.message(Command("start"))
async def cmd_start(m: Message):
    if m.from_user.id == MY_OWNER_ID:
        await bot.set_my_commands([BotCommand(command="start", description="🏠 Меню"), BotCommand(command="broadcast", description="📢 Рассылка")], scope=BotCommandScopeChat(chat_id=m.from_user.id))
    db_upsert_user(m.from_user.id, username=m.from_user.username)
    # По умолчанию открываем стандартное, юзер сам перейдет если захочет
    await send_menu_interface(m, m.from_user.id, mode="standard")

# --- ПЕРЕКЛЮЧЕНИЕ РЕЖИМОВ ---
@dp.callback_query(F.data == "switch_to_prt")
async def cb_sw_prt(cb: CallbackQuery):
    await send_menu_interface(cb, cb.from_user.id, mode="partner")

@dp.callback_query(F.data == "switch_to_std")
async def cb_sw_std(cb: CallbackQuery):
    await send_menu_interface(cb, cb.from_user.id, mode="standard")

# --- ПРОМОКОДЫ ---
@dp.callback_query(F.data == "ui_enter_promo")
async def cb_enter_promo(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("✍️ <b>Введите промокод:</b>")
    await state.set_state(PromoState.waiting_for_code)

@dp.message(PromoState.waiting_for_code)
async def process_promo_code(m: Message, state: FSMContext):
    code = m.text.strip().upper()
    if code in PARTNERS_CONFIG:
        db_upsert_user(m.from_user.id, promo_group=code)
        await state.clear()
        await m.answer(f"✅ Код <b>{code}</b> активирован!")
        # Сразу перекидываем в партнерское меню
        await send_menu_interface(m, m.from_user.id, mode="partner")
    else:
        await m.answer("❌ Неверный код. /start")

# --- ОПЛАТА (С РАЗДЕЛЕНИЕМ ЛОГИКИ) ---
@dp.callback_query(F.data.startswith("buy_"))
async def cb_buy_start(cb: CallbackQuery):
    # data format: buy_std_1 OR buy_prt_1
    _, mode_code, months_str = cb.data.split("_")
    months = int(months_str)
    
    user_info = await db_get_user_info(cb.from_user.id)
    promo = user_info.get("promo_group")
    
    # Определяем параметры сделки
    if mode_code == "prt" and promo in PARTNERS_CONFIG:
        # === ПАРТНЕРСКИЙ ФЛОУ ===
        cfg = PARTNERS_CONFIG[promo]
        currency = cfg.get("force_currency", "RUB")
        price_str = format_price(months, currency)
        pay_url = cfg.get("payment_url", "https://t.me/")
        
        info_text = (
            f"🌟 <b>Партнерский заказ: {PARTNERS_CONFIG[promo]['name']}</b>\n"
            f"Товар: Лицензия {months} мес.\n"
            f"К оплате: <b>{price_str}</b>\n\n"
            f"1. Отправьте звезды по ссылке/инструкции.\n"
            f"2. Нажмите кнопку подтверждения."
        )
        is_partner_sale = True
    else:
        # === ОБЫЧНЫЙ ФЛОУ ===
        currency = user_info.get("currency", "RUB")
        price_str = format_price(months, currency)
        pay_url = "https://www.donationalerts.com/r/dialoge_engine"
        
        info_text = (
            f"🛒 <b>Заказ лицензии (Standard)</b>\n"
            f"Период: {months} мес.\n"
            f"Сумма: <b>{price_str}</b>\n\n"
            f"1. Переведите сумму по ссылке.\n"
            f"2. Подтвердите оплату."
        )
        is_partner_sale = False

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💳 Оплатить", url=pay_url))
    # В кнопку проверки зашиваем режим (std/prt), чтобы знать, кому слать заявку
    kb.row(InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"verify_{mode_code}_{months}"))
    
    # Кнопка назад должна вести в правильное меню
    back_cb = "switch_to_prt" if is_partner_sale else "switch_to_std"
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=back_cb))
    
    await cb.message.edit_text(info_text, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("verify_"))
async def cb_verify_pay(cb: CallbackQuery):
    # data: verify_std_1 OR verify_prt_1
    _, mode_code, months_str = cb.data.split("_")
    months = int(months_str)
    
    user_info = await db_get_user_info(cb.from_user.id)
    promo = user_info.get("promo_group")
    
    target_chat = ADM_CHAT
    log_title = "BotEngine Standard"
    
    # Вычисляем цену снова для отображения админу
    if mode_code == "prt" and promo in PARTNERS_CONFIG:
        currency = PARTNERS_CONFIG[promo].get("force_currency", "RUB")
        price_str = format_price(months, currency)
        target_chat = PARTNERS_CONFIG[promo].get("admin_chat_id", ADM_CHAT)
        log_title = f"Partner: {PARTNERS_CONFIG[promo]['name']}"
    else:
        currency = user_info.get("currency", "RUB")
        price_str = format_price(months, currency)

    akb = InlineKeyboardBuilder()
    akb.row(InlineKeyboardButton(text="✅ Дать ключ", callback_data=f"adm_ok_{cb.from_user.id}_{months}"),
            InlineKeyboardButton(text="❌ Отказ", callback_data=f"adm_no_{cb.from_user.id}"))
    
    msg_text = (
        f"💰 <b>Заявка ({log_title})</b>\n"
        f"Юзер: {cb.from_user.full_name} (ID: <code>{cb.from_user.id}</code>)\n"
        f"Тариф: {months} мес.\n"
        f"Сумма: <b>{price_str}</b>"
    )

    try:
        await bot.send_message(target_chat, msg_text, reply_markup=akb.as_markup(), parse_mode="HTML")
        await cb.message.edit_text("⏳ Заявка отправлена администратору.")
        
        # Лог главному админу, если чаты разные
        if str(target_chat) != str(ADM_CHAT):
            await bot.send_message(ADM_CHAT, f"📝 [LOG] {log_title} -> {price_str} от {cb.from_user.id}")
            
    except Exception as e:
        await cb.answer("Ошибка отправки заявки.", show_alert=True)

# --- АДМИНСКИЕ КНОПКИ (Остались прежними, они универсальны) ---
@dp.callback_query(F.data.startswith("adm_ok_"))
async def cb_admin_approve(cb: CallbackQuery):
    _, _, uid, m_count = cb.data.split("_")
    await cb.message.edit_text(f"⚙️ Выдача ключа для {uid}...")
    try:
        r = requests.post(f"{SRV_URL}/api/admin/generate-key", 
                          json={"months": int(m_count), "user_id": uid}, 
                          headers={"x-admin-token": ADM_SECRET}, timeout=15)
        if r.status_code == 200:
            key = r.json().get("key")
            await bot.send_message(uid, f"🎉 <b>Оплата принята!</b>\nВаш ключ: <code>{key}</code>", parse_mode="HTML")
            await cb.message.edit_text(f"✅ Выдан ключ: <code>{key}</code>\nАдмин: {cb.from_user.full_name}", parse_mode="HTML")
        else:
            await cb.message.edit_text(f"❌ Ошибка API: {r.status_code}")
    except Exception as e:
        await cb.message.edit_text(f"❌ Ошибка связи: {e}")

@dp.callback_query(F.data.startswith("adm_no_"))
async def cb_admin_reject(cb: CallbackQuery):
    uid = cb.data.split("_")[2]
    await bot.send_message(uid, "❌ Платеж отклонен.")
    await cb.message.edit_text(f"🔴 Отказ заявки {uid}")

# --- СТАНДАРТНАЯ ВАЛЮТА ---
@dp.callback_query(F.data == "ui_set_currency")
async def cb_select_curr(cb: CallbackQuery):
    kb = InlineKeyboardBuilder()
    # Показываем все, КРОМЕ XTR (так как XTR только для партнеров)
    for code in CURRENCIES.keys():
        if code != "XTR":
            kb.add(InlineKeyboardButton(text=code, callback_data=f"save_c_{code}"))
    kb.adjust(3)
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="switch_to_std"))
    await cb.message.edit_text("🌍 Выберите валюту:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("save_c_"))
async def cb_save_curr(cb: CallbackQuery):
    code = cb.data.split("_")[2]
    db_upsert_user(cb.from_user.id, currency=code)
    await send_menu_interface(cb, cb.from_user.id, mode="standard")

# --- СИСТЕМНЫЕ ---
async def main():
    logger.info("✨ Бот запущен (Multi-Mode Support)")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try: asyncio.run(main())
    except: pass
