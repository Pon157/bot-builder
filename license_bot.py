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

# Настройка логирования для вывода в stdout (важно для PM2/Docker)
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("LicenseBotEngine")

def load_env_secure():
    """
    Чтение .env файла. 
    Реализовано извлечение токена: берется часть до 'root/' согласно инструкции.
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
                
                # Специальная обработка токена
                if k.strip() == "ADMIN_BOT_TOKEN" and "root/" in val:
                    val = val.split("root/")[0].strip()
                conf[k.strip()] = val
    except Exception as e:
        logger.error(f"❌ Ошибка парсинга .env: {e}")
    return conf

# Загрузка настроек
CONFIG = load_env_secure()
BOT_TOKEN = CONFIG.get("ADMIN_BOT_TOKEN")
SB_URL = CONFIG.get("SUPABASE_URL")
SB_KEY = CONFIG.get("SUPABASE_KEY")
ADM_CHAT = CONFIG.get("ADMIN_CHAT_ID")
ADM_SECRET = CONFIG.get("ADMIN_SECRET", "MRAKOTIK")
SRV_URL = CONFIG.get("SERVER_URL", "http://localhost:8000")

# Владелец с полными правами
MY_OWNER_ID = 5883703466

if not all([BOT_TOKEN, SB_URL, SB_KEY]):
    logger.critical("🛑 Критическая ошибка: проверьте переменные (TOKEN, URL, KEY) в .env")
    sys.exit(1)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
supabase: Client = create_client(SB_URL, SB_KEY)

class PromoState(StatesGroup):
    waiting_for_code = State()

class AiActivateState(StatesGroup):
    waiting_bot_id = State()

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
    "KZT": {"symbol": "₸", "rate": 5.20},
    "XTR": {"symbol": "⭐️", "rate": 0.6}  # Telegram Stars
}

PERIODS = {
    1: {"label": "1 Месяц", "mult": 1.0},
    3: {"label": "3 Месяца", "mult": 2.5},
    12: {"label": "1 Год", "mult": 8.0}
}

# AI токены — пакеты (токены: цена в рублях)
AI_TOKEN_PACKS = {
    500_000:  {"label": "500 000 токенов",  "price_rub": 30},
    1_500_000:{"label": "1 500 000 токенов","price_rub": 80},
    5_000_000:{"label": "5 000 000 токенов","price_rub": 230},
}

# Настройки партнеров
PARTNERS_CONFIG = {
    "NOVASTUDIO": { 
        "name": "NOVA CREATIVE STUDIO",
        "payment_url": "https://t.me/Kotickr", 
        "admin_chat_id": -1003784801472, 
        "menu_title": "<b>Оплата через Telegram Stars</b> NOVA CREATIVE STUDIO!",
        "force_currency": "XTR"
    }
}

# ==========================================
# 3. ФУНКЦИИ БАЗЫ ДАННЫХ (SUPABASE)
# ==========================================

async def db_get_user_info(user_id: int):
    """Получение валюты и привязки к партнеру."""
    try:
        res = supabase.table("bot_users").select("currency, promo_group").eq("id", str(user_id)).execute()
        if res.data:
            return res.data[0]
    except Exception as e:
        logger.error(f"DB Error (get_info): {e}")
    return {"currency": "RUB", "promo_group": None}

def db_upsert_user(user_id: int, currency: str = None, username: str = None, promo_group: str = None):
    """Обновление или создание пользователя."""
    try:
        # Проверяем наличие
        existing = supabase.table("bot_users").select("*").eq("id", str(user_id)).execute()
        data = {"id": str(user_id)}
        
        if existing.data:
            current = existing.data[0]
            data["currency"] = currency or current.get("currency", "RUB")
            data["username"] = username or current.get("username")
            data["promo_group"] = promo_group or current.get("promo_group")
        else:
            data["currency"] = currency or "RUB"
            data["username"] = username
            data["promo_group"] = promo_group
            
        supabase.table("bot_users").upsert(data).execute()
    except Exception as e:
        logger.error(f"❌ Ошибка БД (upsert): {e}")

def db_get_all_users() -> List[int]:
    """Список всех ID для рассылки."""
    try:
        res = supabase.table("bot_users").select("id").execute()
        return [int(row['id']) for row in res.data] if res.data else []
    except Exception as e:
        logger.error(f"DB Error (get_all): {e}")
        return []

# ==========================================
# 4. ЛОГИКА ИНТЕРФЕЙСА (UI)
# ==========================================

def format_price(months: int, currency_code: str) -> str:
    """Расчет цены с учетом курса и множителя периода."""
    curr = CURRENCIES.get(currency_code, CURRENCIES["RUB"])
    price = int(round(BASE_PRICE_RUB * PERIODS[months]["mult"] * curr["rate"]))
    return f"{price} {curr['symbol']}"

async def send_menu_interface(m: Union[Message, CallbackQuery], user_id: int, mode: str = "standard"):
    """
    Универсальное меню: обычное или партнерское.
    """
    user_info = await db_get_user_info(user_id)
    saved_promo = user_info.get("promo_group")
    
    current_currency = user_info.get("currency", "RUB")
    menu_title = "🚀 <b>Dialoge Engine: Магазин</b>\n\nВыберите тариф подписки:"
    is_partner_active = False

    # Логика переключения на партнерское меню
    if mode == "partner" and saved_promo in PARTNERS_CONFIG:
        p_conf = PARTNERS_CONFIG[saved_promo]
        menu_title = p_conf.get("menu_title", menu_title)
        if "force_currency" in p_conf:
            current_currency = p_conf["force_currency"]
        is_partner_active = True
    
    kb = InlineKeyboardBuilder()
    prefix = "prt" if is_partner_active else "std"
    
    # Кнопки покупки
    for m_count, info in PERIODS.items():
        kb.row(InlineKeyboardButton(
            text=f"{info['label']} — {format_price(m_count, current_currency)}", 
            callback_data=f"buy_{prefix}_{m_count}"
        ))
    
    # Настройка валюты
    if not is_partner_active:
        kb.row(InlineKeyboardButton(text=f"🌍 Валюта: {current_currency}", callback_data="ui_set_currency"))
    
    # Кнопки навигации/промокодов
    if is_partner_active:
        kb.row(InlineKeyboardButton(text="🏠 В основное меню", callback_data="switch_to_std"))
    elif saved_promo:
        p_name = PARTNERS_CONFIG.get(saved_promo, {}).get("name", "Партнерка")
        kb.row(InlineKeyboardButton(text=f"{p_name}", callback_data="switch_to_prt"))
    else:
        kb.row(InlineKeyboardButton(text="Ввести промокод", callback_data="ui_enter_promo"))

    if isinstance(m, CallbackQuery):
        await m.message.edit_text(menu_title, reply_markup=kb.as_markup(), parse_mode="HTML")
    else:
        await m.answer(menu_title, reply_markup=kb.as_markup(), parse_mode="HTML")

# ==========================================
# 5. ОБРАБОТЧИКИ КОМАНД
# ==========================================

@dp.message(Command("start"))
async def cmd_start(m: Message):
    if m.from_user.id == MY_OWNER_ID:
        await bot.set_my_commands(
            [BotCommand(command="start", description="🏠 Меню"),
             BotCommand(command="broadcast", description="📢 Рассылка"),
             BotCommand(command="ai_keys", description="🤖 Выдать AI-ключ")],
            scope=BotCommandScopeChat(chat_id=m.from_user.id)
        )

    user_info = await db_get_user_info(m.from_user.id)
    db_upsert_user(m.from_user.id, user_info["currency"], m.from_user.username)
    await send_main_menu(m)

async def send_main_menu(m):
    """Главное меню с выбором раздела."""
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔑 Лицензия бота",    callback_data="menu_license"))
    kb.row(InlineKeyboardButton(text="🤖 AI-токены",         callback_data="menu_ai"))
    text = "👋 <b>Добро пожаловать!</b>\n\nВыберите раздел:"
    fn = m.answer if isinstance(m, Message) else m.message.edit_text
    await fn(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.message(Command("broadcast"))
async def cmd_broadcast_text(m: Message):
    """Рассылка только текста для владельца."""
    if m.from_user.id != MY_OWNER_ID: return
    text = m.text.replace("/broadcast", "").strip()
    if not text:
        return await m.answer("Введите текст после команды!")
    
    users = db_get_all_users()
    progress = await m.answer(f"Рассылка на {len(users)} пользователей...")
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
            
    await progress.edit_text(f"📢 <b>Рассылка завершена!</b>\n✅ {done} | ❌ {fail}", parse_mode="HTML")

@dp.message(F.photo, lambda m: m.from_user.id == MY_OWNER_ID and m.caption and m.caption.startswith("/broadcast"))
async def cmd_broadcast_photo(m: Message):
    """Рассылка фото с описанием."""
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

@dp.callback_query(F.data == "switch_to_prt")
async def cb_sw_prt(cb: CallbackQuery):
    await send_menu_interface(cb, cb.from_user.id, mode="partner")

@dp.callback_query(F.data == "switch_to_std")
async def cb_sw_std(cb: CallbackQuery):
    await send_menu_interface(cb, cb.from_user.id, mode="standard")

@dp.callback_query(F.data == "ui_enter_promo")
async def cb_enter_promo(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("<b>Введите промокод партнера:</b>", parse_mode="HTML")
    await state.set_state(PromoState.waiting_for_code)

@dp.message(PromoState.waiting_for_code)
async def process_promo_code(m: Message, state: FSMContext):
    code = m.text.strip().upper()
    if code in PARTNERS_CONFIG:
        db_upsert_user(m.from_user.id, promo_group=code)
        await state.clear()
        await m.answer(f"Код {code} активирован!")
        await send_menu_interface(m, m.from_user.id, mode="partner")
    else:
        await m.answer("Неверный код. Попробуйте снова или /start")

@dp.callback_query(F.data.startswith("buy_"))
async def cb_buy_start(cb: CallbackQuery):
    """Формирование счета на оплату."""
    _, mode_code, months_str = cb.data.split("_")
    months = int(months_str)
    user_info = await db_get_user_info(cb.from_user.id)
    promo = user_info.get("promo_group")
    
    faq_url = "https://telegra.ph/Politika-vozvrata-i-licenzirovaniya-Refund-Policy-02-06"
    
    if mode_code == "prt" and promo in PARTNERS_CONFIG:
        cfg = PARTNERS_CONFIG[promo]
        currency = cfg.get("force_currency", "RUB")
        price_str = format_price(months, currency)
        pay_url = cfg["payment_url"]
        info_text = (
            f"🌟 <b>Партнерский заказ: {cfg['name']}</b>\n"
            f"Товар: Лицензия {months} мес.\nСумма: <b>{price_str}</b>\n\n"
            "1. Оплатите по ссылке.\n2. Нажмите 'Я оплатил'."
        )
        back_cb = "switch_to_prt"
    else:
        currency = user_info["currency"]
        price_str = format_price(months, currency)
        pay_url = "https://www.donationalerts.com/r/dialoge_engine"
        info_text = (
            f"🛒 <b>Заказ лицензии: {PERIODS[months]['label']}</b>\n"
            f"Сумма: <b>{price_str}</b>\n\n"
            "1. Переведите сумму по ссылке.\n2. Обязательно прочитайте правила возврата и лицензирования.\n3. Подтвердите оплату."
        )
        back_cb = "switch_to_std"

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="Оплатить", url=pay_url))
    kb.row(InlineKeyboardButton(text="Я оплатил", callback_data=f"verify_{mode_code}_{months}"))
    kb.row(InlineKeyboardButton(text="Правила возврата", url=faq_url))
    kb.row(InlineKeyboardButton(text="Назад", callback_data=back_cb))
    
    await cb.message.edit_text(info_text, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("verify_"))
async def cb_verify_pay(cb: CallbackQuery):
    """Уведомление админа о новом платеже."""
    _, mode_code, months_str = cb.data.split("_")
    months = int(months_str)
    user_info = await db_get_user_info(cb.from_user.id)
    promo = user_info.get("promo_group")
    
    target_chat = ADM_CHAT
    log_title = "BotEngine"
    
    if mode_code == "prt" and promo in PARTNERS_CONFIG:
        curr = PARTNERS_CONFIG[promo].get("force_currency", "RUB")
        price_str = format_price(months, curr)
        target_chat = PARTNERS_CONFIG[promo].get("admin_chat_id", ADM_CHAT)
        log_title = f"Partner: {PARTNERS_CONFIG[promo]['name']}"
    else:
        price_str = format_price(months, user_info["currency"])

    akb = InlineKeyboardBuilder()
    akb.row(InlineKeyboardButton(text="✅ Выдать", callback_data=f"adm_ok_{cb.from_user.id}_{months}"),
            InlineKeyboardButton(text="❌ Отказ", callback_data=f"adm_no_{cb.from_user.id}"))
    
    msg_text = (
        f"💰 <b>Заявка ({log_title})</b>\n"
        f"Юзер: {cb.from_user.full_name} (<code>{cb.from_user.id}</code>)\n"
        f"Тариф: {months} мес. | Сумма: <b>{price_str}</b>"
    )

    try:
        await bot.send_message(target_chat, msg_text, reply_markup=akb.as_markup(), parse_mode="HTML")
        await cb.message.edit_text("⏳ Заявка отправлена. Ожидайте подтверждения.")
        
        if str(target_chat) != str(ADM_CHAT):
            await bot.send_message(ADM_CHAT, f"📝 [LOG] {log_title} -> {price_str} от {cb.from_user.id}")
    except Exception:
        await cb.answer("Ошибка отправки заявки.", show_alert=True)

# ==========================================
# 7. АДМИН-ПАНЕЛЬ (ВЫДАЧА КЛЮЧЕЙ)
# ==========================================

@dp.callback_query(F.data.startswith("adm_ok_"))
async def cb_admin_approve(cb: CallbackQuery):
    """Генерация ключа через внешний API."""
    _, _, uid, m_count = cb.data.split("_")
    await cb.message.edit_text(f"⚙️ Генерирую ключ для {uid}...")
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
    await bot.send_message(uid, "❌ Ваш платеж отклонен администратором.")
    await cb.message.edit_text(f"🔴 Заявка {uid} отклонена.")

# ==========================================
# 8. УПРАВЛЕНИЕ ВАЛЮТОЙ
# ==========================================

@dp.callback_query(F.data == "ui_set_currency")
async def cb_select_curr(cb: CallbackQuery):
    kb = InlineKeyboardBuilder()
    for code in CURRENCIES:
        if code != "XTR":  # Звезды только для партнеров
            kb.add(InlineKeyboardButton(text=code, callback_data=f"save_c_{code}"))
    kb.adjust(3)
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="switch_to_std"))
    await cb.message.edit_text("🌍 <b>Выберите валюту цен:</b>", reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("save_c_"))
async def cb_save_curr(cb: CallbackQuery):
    code = cb.data.split("_")[2]
    db_upsert_user(cb.from_user.id, currency=code)
    await cb.answer(f"Валюта {code} сохранена!")
    await send_menu_interface(cb, cb.from_user.id, mode="standard")

# ==========================================
# AI-ТОКЕНЫ МЕНЮ
# ==========================================

@dp.callback_query(F.data == "menu_license")
async def cb_menu_license(cb: CallbackQuery):
    await send_menu_interface(cb, cb.from_user.id, mode="standard")

@dp.callback_query(F.data == "menu_ai")
async def cb_menu_ai(cb: CallbackQuery):
    """Меню покупки AI-токенов."""
    kb = InlineKeyboardBuilder()
    for tokens, info in AI_TOKEN_PACKS.items():
        kb.row(InlineKeyboardButton(
            text=f"{info['label']} — {info['price_rub']} ₽",
            callback_data=f"buyai_{tokens}"
        ))
    kb.row(InlineKeyboardButton(text="🔑 Активировать ключ AI", callback_data="activate_ai_key"))
    kb.row(InlineKeyboardButton(text="🏠 Назад",               callback_data="back_main"))
    ai_menu_text = ("🤖 <b>AI-токены для бота</b>\n\n"
                    "Токены расходуются при ответах ИИ-ассистента.\n"
                    "Чем длиннее сообщения — тем больше расход.\n\n"
                    "Выберите пакет:")
    await cb.message.edit_text(ai_menu_text, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("buyai_"))
async def cb_buy_ai(cb: CallbackQuery):
    tokens = int(cb.data.replace("buyai_", ""))
    info = AI_TOKEN_PACKS.get(tokens)
    if not info:
        return await cb.answer("Пакет не найден", show_alert=True)

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💳 Оплатить",
        url="https://www.donationalerts.com/r/dialoge_engine"))
    kb.row(InlineKeyboardButton(text="✅ Я оплатил",
        callback_data=f"verifyai_{tokens}"))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="menu_ai"))

    buy_text = (f"🤖 <b>Заказ: {info['label']}</b>\n\n"
               f"Сумма: <b>{info['price_rub']} ₽</b>\n\n"
               "1. Переведите сумму по ссылке.\n"
               "2. В комментарии укажите ваш Telegram ID.\n"
               "3. Нажмите «Я оплатил».")
    await cb.message.edit_text(buy_text, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("verifyai_"))
async def cb_verify_ai(cb: CallbackQuery):
    tokens = int(cb.data.replace("verifyai_", ""))
    info = AI_TOKEN_PACKS.get(tokens, {})

    akb = InlineKeyboardBuilder()
    akb.row(
        InlineKeyboardButton(text="✅ Выдать AI-ключ",
            callback_data=f"adm_ai_ok_{cb.from_user.id}_{tokens}"),
        InlineKeyboardButton(text="❌ Отказ",
            callback_data=f"adm_no_{cb.from_user.id}")
    )
    try:
        notify_text = (f"🤖 <b>Заявка AI-токены</b>\n"
                       f"Юзер: {cb.from_user.full_name} (<code>{cb.from_user.id}</code>)\n"
                       f"Пакет: {info.get('label', '?')} | Сумма: {info.get('price_rub', '?')} ₽")
        await bot.send_message(ADM_CHAT, notify_text, reply_markup=akb.as_markup(), parse_mode="HTML")
        await cb.message.edit_text("⏳ Заявка отправлена. Ожидайте подтверждения.")
    except Exception as e:
        await cb.answer("Ошибка отправки", show_alert=True)

@dp.callback_query(F.data.startswith("adm_ai_ok_"))
async def cb_admin_approve_ai(cb: CallbackQuery):
    """Администратор выдаёт AI-ключ пользователю."""
    parts = cb.data.split("_")  # adm_ai_ok_USERID_TOKENS
    uid  = parts[3]
    tokens = int(parts[4])

    try:
        r = requests.post(f"{SRV_URL}/api/admin/generate-ai-key",
            json={"tokens": tokens, "price_rub": AI_TOKEN_PACKS.get(tokens, {}).get("price_rub", 0)},
            headers={"x-admin-token": ADM_SECRET}, timeout=15)
        if r.status_code == 200:
            key = r.json().get("key")
            msg = (f"🎉 <b>Оплата подтверждена!</b>\n\n"
                   f"Ваш AI-ключ: <code>{key}</code>\n\n"
                   "Активируйте его в боте через «🤖 AI-токены → Активировать ключ AI».")
            await bot.send_message(uid, msg, parse_mode="HTML")
            await cb.message.edit_text(
                f"✅ AI-ключ выдан: <code>{key}</code>",
                parse_mode="HTML"
            )
        else:
            await cb.message.edit_text(f"❌ Ошибка API: {r.status_code}")
    except Exception as e:
        await cb.message.edit_text(f"❌ Ошибка: {e}")

@dp.callback_query(F.data == "activate_ai_key")
async def cb_activate_ai_key(cb: CallbackQuery, state: FSMContext):
    """Запрашиваем ключ и bot_id."""
    text = (
        "🔑 <b>Активация AI-ключа</b>\n\n"
        "Отправьте сообщение в формате:\n"
        "<code>AITOK-XXXXXX-NNN bot_id</code>\n\n"
        "Ключ и ID бота через пробел.\n"
        "ID бота найдёте в настройках бота."
    )
    await cb.message.edit_text(text, parse_mode="HTML")
    await state.set_state(AiActivateState.waiting_bot_id)

@dp.message(AiActivateState.waiting_bot_id)
async def process_ai_activation(m: Message, state: FSMContext):
    parts = m.text.strip().split()
    if len(parts) < 2:
        await m.answer(
            "Укажите ключ и ID бота через пробел.\n"
            "Пример: <code>AITOK-ABC123-456 bot_a1b2c3d4</code>",
            parse_mode="HTML"
        )
        return
    key_code = parts[0].upper()
    bot_id   = parts[1].strip()
    await state.clear()
    try:
        r = requests.post(f"{SRV_URL}/api/ai/activate-tokens",
            json={"key": key_code, "botId": bot_id}, timeout=15)
        res = r.json()
        if res.get("status") == "ok":
            tokens = res.get("tokens_added", 0)
            await m.answer(
                f"✅ <b>Активировано!</b>\n\n"
                f"Бот <code>{bot_id}</code> получил <b>{tokens:,}</b> AI-токенов.",
                parse_mode="HTML"
            )
        else:
            await m.answer(f"❌ {res.get('message', 'Ошибка')}")
    except Exception as e:
        await m.answer(f"❌ Ошибка сервера: {e}")

@dp.callback_query(F.data == "back_main")
async def cb_back_main(cb: CallbackQuery):
    await send_main_menu(cb)

@dp.message(Command("ai_keys"))
async def cmd_ai_keys(m: Message):
    """Только для владельца: быстрая генерация AI-ключа."""
    if m.from_user.id != MY_OWNER_ID:
        return
    parts = m.text.split()
    tokens = int(parts[1]) if len(parts) > 1 else 500_000
    try:
        r = requests.post(f"{SRV_URL}/api/admin/generate-ai-key",
            json={"tokens": tokens},
            headers={"x-admin-token": ADM_SECRET}, timeout=10)
        key = r.json().get("key")
        await m.answer(f"🤖 AI-ключ: <code>{key}</code>\nТокены: {tokens:,}", parse_mode="HTML")
    except Exception as e:
        await m.answer(f"❌ {e}")

# ==========================================
# 9. ЗАПУСК БОТА
# ==========================================

async def main():
    logger.info("✨ Лицензионный бот успешно запущен (Multi-Mode Support)")
    # Общее меню команд
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
