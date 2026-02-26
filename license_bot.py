"""
license_bot.py — Лицензионный бот Dialoge Engine
БЕЗ supabase SDK — только чистые HTTP-запросы (requests)
"""
import os
import asyncio
import logging
import sys
import requests
from typing import List, Union

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import (
    InlineKeyboardButton, CallbackQuery, Message,
    BotCommand, BotCommandScopeChat
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramRetryAfter

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


def load_env():
    path = os.path.join(BASE_DIR, '.env')
    conf = {}
    if not os.path.exists(path):
        logger.error(f"Файл .env не найден в {BASE_DIR}")
        return conf
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
    return conf


CONFIG     = load_env()
BOT_TOKEN  = CONFIG.get("ADMIN_BOT_TOKEN")
SB_URL     = CONFIG.get("SUPABASE_URL", "").rstrip('/')
SB_KEY     = CONFIG.get("SUPABASE_KEY", "")
ADM_CHAT   = int(CONFIG.get("ADMIN_CHAT_ID", "0"))
ADM_SECRET = CONFIG.get("ADMIN_SECRET", "MRAKOTIK")
SRV_URL    = CONFIG.get("SERVER_URL", "http://localhost:8000")
MY_OWNER_ID = 5883703466

if not all([BOT_TOKEN, SB_URL, SB_KEY]):
    logger.critical("Не хватает ADMIN_BOT_TOKEN / SUPABASE_URL / SUPABASE_KEY в .env")
    sys.exit(1)

# ==========================================
# 2. SUPABASE ЧЕРЕЗ ЧИСТЫЙ HTTP (без SDK!)
# ==========================================
_SB_HEADERS = {
    "apikey":        SB_KEY,
    "Authorization": f"Bearer {SB_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=representation",
}


def _sb_url(table: str) -> str:
    return f"{SB_URL}/rest/v1/{table}"


def sb_select(table: str, params: dict) -> list:
    try:
        r = requests.get(_sb_url(table), headers=_SB_HEADERS, params=params, timeout=10)
        return r.json() if r.status_code == 200 else []
    except Exception as e:
        logger.error(f"sb_select [{table}]: {e}")
        return []


def sb_upsert(table: str, data: dict) -> bool:
    try:
        h = {**_SB_HEADERS, "Prefer": "resolution=merge-duplicates,return=minimal"}
        r = requests.post(_sb_url(table), headers=h, json=data, timeout=10)
        return r.status_code in (200, 201, 204)
    except Exception as e:
        logger.error(f"sb_upsert [{table}]: {e}")
        return False


# ==========================================
# 3. БОТ + ДИСПЕТЧЕР
# ==========================================
bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())


# ==========================================
# 4. FSM STATES
# ==========================================
class PromoState(StatesGroup):
    waiting_for_code = State()

class AiActivateState(StatesGroup):
    waiting_input = State()

class MiniappActivateState(StatesGroup):
    waiting_input = State()

class ChatSiteActivateState(StatesGroup):
    waiting_input = State()


# ==========================================
# 5. КОНФИГИ
# ==========================================
BASE_PRICE_RUB = 91

CURRENCIES = {
    "RUB": {"symbol": "₽",   "rate": 1.0},
    "USD": {"symbol": "$",   "rate": 0.011},
    "EUR": {"symbol": "€",   "rate": 0.010},
    "BYN": {"symbol": "BYN", "rate": 0.035},
    "UAH": {"symbol": "₴",   "rate": 0.43},
    "KZT": {"symbol": "₸",   "rate": 5.20},
    "XTR": {"symbol": "⭐️",  "rate": 0.6},
}

PERIODS = {
    1:  {"label": "1 Месяц",  "mult": 1.0},
    3:  {"label": "3 Месяца", "mult": 2.5},
    12: {"label": "1 Год",    "mult": 8.0},
}

AI_TOKEN_PACKS = {
    500_000:   {"label": "500 000 токенов",   "price_rub": 40},
    1_500_000: {"label": "1 500 000 токенов", "price_rub": 90},
    5_000_000: {"label": "5 000 000 токенов", "price_rub": 240},
}

CHAT_SITE_PACKS = {
    30: {"label": "Чат-платформа 1 мес.", "price_rub": 150},
}

PARTNERS_CONFIG = {
    "NOVASTUDIO": {
        "name":           "NOVA CREATIVE STUDIO",
        "payment_url":    "https://t.me/Kotickr",
        "admin_chat_id":  -1003784801472,
        "menu_title":     "<b>Оплата через Telegram Stars</b> NOVA CREATIVE STUDIO!",
        "force_currency": "XTR",
    },
}

AD_TOPUP_PACKS = {
    "100":  {"label": "100 ₽  (~200 показов)",  "amount": 100},
    "300":  {"label": "300 ₽  (~600 показов)",  "amount": 300},
    "500":  {"label": "500 ₽  (~1000 показов)", "amount": 500},
    "1000": {"label": "1000 ₽ (~2000 показов)", "amount": 1000},
    "3000": {"label": "3000 ₽ (~6000 показов)", "amount": 3000},
}


# ==========================================
# 6. БД-ФУНКЦИИ
# ==========================================
async def db_get_user_info(user_id: int) -> dict:
    try:
        rows = sb_select("bot_users", {"id": f"eq.{user_id}", "select": "currency,promo_group"})
        if rows:
            return rows[0]
    except Exception as e:
        logger.error(f"db_get_user_info: {e}")
    return {"currency": "RUB", "promo_group": None}


def db_upsert_user(user_id: int, currency: str = None,
                   username: str = None, promo_group: str = None):
    try:
        existing = sb_select("bot_users", {"id": f"eq.{user_id}"})
        if existing:
            cur = existing[0]
            data = {
                "id":          str(user_id),
                "currency":    currency    or cur.get("currency", "RUB"),
                "username":    username    or cur.get("username"),
                "promo_group": promo_group or cur.get("promo_group"),
            }
        else:
            data = {
                "id":          str(user_id),
                "currency":    currency    or "RUB",
                "username":    username,
                "promo_group": promo_group,
            }
        sb_upsert("bot_users", data)
    except Exception as e:
        logger.error(f"db_upsert_user: {e}")


def db_get_all_users() -> List[int]:
    try:
        rows = sb_select("bot_users", {"select": "id"})
        return [int(r["id"]) for r in rows] if rows else []
    except Exception as e:
        logger.error(f"db_get_all_users: {e}")
        return []


# ==========================================
# 7. UI-УТИЛИТЫ
# ==========================================
def format_price(months: int, currency_code: str) -> str:
    curr  = CURRENCIES.get(currency_code, CURRENCIES["RUB"])
    price = int(round(BASE_PRICE_RUB * PERIODS[months]["mult"] * curr["rate"]))
    return f"{price} {curr['symbol']}"


async def send_main_menu(m):
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔑 Лицензия бота",  callback_data="menu_license"))
    kb.row(InlineKeyboardButton(text="🤖 AI-токены",       callback_data="menu_ai"))
    kb.row(InlineKeyboardButton(text="📱 Мини-приложения", callback_data="menu_miniapps"))
    kb.row(InlineKeyboardButton(text="💬 Чат-платформа",   callback_data="menu_chatsite"))
    kb.row(InlineKeyboardButton(text="📢 Реклама в ботах", callback_data="menu_ads"))
    text = "👋 <b>Добро пожаловать!</b>\n\nВыберите раздел:"
    fn = m.answer if isinstance(m, Message) else m.message.edit_text
    await fn(text, reply_markup=kb.as_markup(), parse_mode="HTML")


async def send_menu_interface(m, user_id: int, mode: str = "standard"):
    user_info        = await db_get_user_info(user_id)
    saved_promo      = user_info.get("promo_group")
    current_currency = user_info.get("currency", "RUB")
    menu_title       = "🚀 <b>Dialoge Engine: Магазин</b>\n\nВыберите тариф подписки:"
    is_partner       = False

    if mode == "partner" and saved_promo in PARTNERS_CONFIG:
        p                = PARTNERS_CONFIG[saved_promo]
        menu_title       = p.get("menu_title", menu_title)
        current_currency = p.get("force_currency", current_currency)
        is_partner       = True

    prefix = "prt" if is_partner else "std"
    kb     = InlineKeyboardBuilder()
    for mc, info in PERIODS.items():
        kb.row(InlineKeyboardButton(
            text=f"{info['label']} — {format_price(mc, current_currency)}",
            callback_data=f"buy_{prefix}_{mc}"
        ))

    if not is_partner:
        kb.row(InlineKeyboardButton(text=f"🌍 Валюта: {current_currency}", callback_data="ui_set_currency"))

    if is_partner:
        kb.row(InlineKeyboardButton(text="🏠 В основное меню", callback_data="switch_to_std"))
    elif saved_promo:
        p_name = PARTNERS_CONFIG.get(saved_promo, {}).get("name", "Партнерка")
        kb.row(InlineKeyboardButton(text=p_name, callback_data="switch_to_prt"))
    else:
        kb.row(InlineKeyboardButton(text="Ввести промокод", callback_data="ui_enter_promo"))

    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="back_main"))

    if isinstance(m, CallbackQuery):
        await m.message.edit_text(menu_title, reply_markup=kb.as_markup(), parse_mode="HTML")
    else:
        await m.answer(menu_title, reply_markup=kb.as_markup(), parse_mode="HTML")


# ==========================================
# 8. КОМАНДЫ
# ==========================================
@dp.message(Command("start"))
async def cmd_start(m: Message):
    if m.from_user.id == MY_OWNER_ID:
        await bot.set_my_commands(
            [BotCommand(command="start",     description="🏠 Меню"),
             BotCommand(command="broadcast", description="📢 Рассылка"),
             BotCommand(command="ads_admin", description="📢 Реклама-обзор"),
             BotCommand(command="ai_keys",   description="🤖 AI-ключи")],
            scope=BotCommandScopeChat(chat_id=MY_OWNER_ID)
        )
    user_info = await db_get_user_info(m.from_user.id)
    db_upsert_user(m.from_user.id, user_info["currency"], m.from_user.username)
    await send_main_menu(m)


@dp.message(Command("broadcast"))
async def cmd_broadcast_text(m: Message):
    if m.from_user.id != MY_OWNER_ID:
        return
    text = m.text.replace("/broadcast", "").strip()
    if not text:
        return await m.answer("Введите текст после команды!")
    users    = db_get_all_users()
    progress = await m.answer(f"⏳ Рассылка на {len(users)} пользователей...")
    done, fail = 0, 0
    for uid in users:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
            done += 1
            await asyncio.sleep(0.05)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await bot.send_message(uid, text, parse_mode="HTML")
                done += 1
            except Exception:
                fail += 1
        except Exception:
            fail += 1
    await progress.edit_text(f"📢 <b>Рассылка завершена!</b>\n✅ {done} | ❌ {fail}", parse_mode="HTML")


@dp.message(F.photo, lambda m: m.from_user.id == MY_OWNER_ID
            and m.caption and m.caption.startswith("/broadcast"))
async def cmd_broadcast_photo(m: Message):
    text     = m.caption.replace("/broadcast", "").strip()
    users    = db_get_all_users()
    progress = await m.answer(f"⏳ Рассылка медиа на {len(users)} чел...")
    done     = 0
    for uid in users:
        try:
            await bot.send_photo(uid, m.photo[-1].file_id, caption=text, parse_mode="HTML")
            done += 1
            await asyncio.sleep(0.05)
        except Exception:
            continue
    await progress.edit_text(f"✅ Фото разослано! Доставлено: {done}")


@dp.message(Command("ai_keys"))
async def cmd_ai_keys(m: Message):
    if m.from_user.id != MY_OWNER_ID:
        return
    parts  = m.text.split()
    tokens = int(parts[1]) if len(parts) > 1 else 500_000
    try:
        r   = requests.post(f"{SRV_URL}/api/admin/generate-ai-key",
                            json={"tokens": tokens},
                            headers={"x-admin-token": ADM_SECRET}, timeout=10)
        key = r.json().get("key")
        await m.answer(f"🤖 AI-ключ: <code>{key}</code>\nТокены: {tokens:,}", parse_mode="HTML")
    except Exception as e:
        await m.answer(f"❌ {e}")


@dp.message(Command("ads_admin"))
async def cmd_ads_admin(m: Message):
    if m.from_user.id != MY_OWNER_ID:
        return
    try:
        r     = requests.get(f"{SRV_URL}/api/admin/ads/campaigns",
                             headers={"x-admin-token": ADM_SECRET}, timeout=10)
        camps = r.json() if r.status_code == 200 else []
    except Exception as e:
        return await m.answer(f"❌ {e}")

    em    = {"active": "🟢", "paused": "⏸", "depleted": "🔴"}
    total = sum(c.get("impressions", 0) for c in camps)
    lines = [
        f"📢 <b>Рекламный блок</b>\nКампаний: {len(camps)} | Показов: {total:,}\n"
    ]
    for c in camps[:8]:
        lines.append(
            f"{em.get(c.get('status',''), '⚪')} {c.get('title','?')} | {c.get('advertiser_name','?')}\n"
            f"   Показов: {c.get('impressions',0)} | Баланс: {float(c.get('balance',0)):.2f} ₽"
        )
    await m.answer("\n".join(lines), parse_mode="HTML")


# ==========================================
# 9. НАВИГАЦИЯ
# ==========================================
@dp.callback_query(F.data == "back_main")
async def cb_back_main(cb: CallbackQuery):
    await send_main_menu(cb)

@dp.callback_query(F.data == "menu_license")
async def cb_menu_license(cb: CallbackQuery):
    await send_menu_interface(cb, cb.from_user.id)

@dp.callback_query(F.data == "switch_to_prt")
async def cb_sw_prt(cb: CallbackQuery):
    await send_menu_interface(cb, cb.from_user.id, mode="partner")

@dp.callback_query(F.data == "switch_to_std")
async def cb_sw_std(cb: CallbackQuery):
    await send_menu_interface(cb, cb.from_user.id, mode="standard")

@dp.callback_query(F.data == "ui_set_currency")
async def cb_set_currency(cb: CallbackQuery):
    kb = InlineKeyboardBuilder()
    for code, info in CURRENCIES.items():
        kb.row(InlineKeyboardButton(text=f"{info['symbol']} {code}", callback_data=f"cur_{code}"))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="back_main"))
    await cb.message.edit_text("🌍 <b>Выберите валюту:</b>", reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("cur_"))
async def cb_set_cur(cb: CallbackQuery):
    code = cb.data.replace("cur_", "")
    db_upsert_user(cb.from_user.id, currency=code)
    await cb.answer(f"Валюта: {code}")
    await send_menu_interface(cb, cb.from_user.id)

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
        await m.answer(f"✅ Код {code} активирован!")
        await send_menu_interface(m, m.from_user.id, mode="partner")
    else:
        await m.answer("Неверный код. Попробуйте снова или /start")


# ==========================================
# 10. ЛИЦЕНЗИЯ — ПОКУПКА
# ==========================================
@dp.callback_query(F.data.startswith("buy_"))
async def cb_buy_start(cb: CallbackQuery):
    _, mode_code, months_str = cb.data.split("_")
    months    = int(months_str)
    user_info = await db_get_user_info(cb.from_user.id)
    promo     = user_info.get("promo_group")
    faq_url   = "https://telegra.ph/Politika-vozvrata-i-licenzirovaniya-Refund-Policy-02-06"

    if mode_code == "prt" and promo in PARTNERS_CONFIG:
        cfg       = PARTNERS_CONFIG[promo]
        currency  = cfg.get("force_currency", "RUB")
        price_str = format_price(months, currency)
        pay_url   = cfg["payment_url"]
        info_text = (f"🌟 <b>Партнерский заказ: {cfg['name']}</b>\n"
                     f"Лицензия {months} мес. — <b>{price_str}</b>\n\n"
                     "1. Оплатите по ссылке.\n2. Нажмите «Я оплатил».")
        back_cb   = "switch_to_prt"
    else:
        currency  = user_info["currency"]
        price_str = format_price(months, currency)
        pay_url   = "https://www.donationalerts.com/r/dialoge_engine"
        info_text = (f"🛒 <b>Лицензия: {PERIODS[months]['label']}</b>\n"
                     f"Сумма: <b>{price_str}</b>\n\n"
                     "1. Переведите сумму.\n2. Прочитайте правила.\n3. Нажмите «Я оплатил».")
        back_cb   = "switch_to_std"

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💳 Оплатить", url=pay_url))
    kb.row(InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"verify_{mode_code}_{months}"))
    kb.row(InlineKeyboardButton(text="📄 Правила возврата", url=faq_url))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data=back_cb))
    await cb.message.edit_text(info_text, reply_markup=kb.as_markup(), parse_mode="HTML")


@dp.callback_query(F.data.startswith("verify_"))
async def cb_verify_pay(cb: CallbackQuery):
    _, mode_code, months_str = cb.data.split("_")
    months      = int(months_str)
    user_info   = await db_get_user_info(cb.from_user.id)
    promo       = user_info.get("promo_group")
    target_chat = ADM_CHAT

    if mode_code == "prt" and promo in PARTNERS_CONFIG:
        curr        = PARTNERS_CONFIG[promo].get("force_currency", "RUB")
        price_str   = format_price(months, curr)
        target_chat = PARTNERS_CONFIG[promo].get("admin_chat_id", ADM_CHAT)
    else:
        price_str = format_price(months, user_info["currency"])

    akb = InlineKeyboardBuilder()
    akb.row(
        InlineKeyboardButton(text="✅ Выдать",  callback_data=f"adm_ok_{cb.from_user.id}_{months}"),
        InlineKeyboardButton(text="❌ Отказ",   callback_data=f"adm_no_{cb.from_user.id}"),
    )
    try:
        await bot.send_message(
            target_chat,
            f"🔔 <b>Заявка лицензия</b>\n"
            f"Юзер: {cb.from_user.full_name} (<code>{cb.from_user.id}</code>)\n"
            f"Тариф: {PERIODS[months]['label']} | {price_str}",
            reply_markup=akb.as_markup(), parse_mode="HTML"
        )
        await cb.message.edit_text("⏳ Заявка отправлена. Ожидайте подтверждения.")
    except Exception:
        await cb.answer("Ошибка отправки", show_alert=True)


@dp.callback_query(F.data.startswith("adm_ok_"))
async def cb_admin_ok(cb: CallbackQuery):
    await cb.answer()
    try:
        parts  = cb.data.split("_")
        months = int(parts[-1])
        uid    = parts[-2]
        await cb.message.edit_text(f"⏳ Генерирую ключ для {uid}...")
        r = requests.post(
            f"{SRV_URL}/api/admin/generate-key",
            json={"months": months, "owner_id": uid},
            headers={"x-admin-token": ADM_SECRET}, timeout=15
        )
        if r.status_code != 200:
            return await cb.message.edit_text(f"❌ Ошибка: {r.status_code}\n{r.text[:200]}")
        key = r.json().get("key")
        await bot.send_message(
            int(uid),
            f"🎉 <b>Оплата подтверждена!</b>\n\n"
            f"Ключ: <code>{key}</code>\nСрок: <b>{months} мес.</b>\n\n"
            "Активация: Дашборд → Редактор бота → <b>Лицензия</b>.",
            parse_mode="HTML"
        )
        await cb.message.edit_text(f"✅ Ключ <code>{key}</code> выдан {uid}.", parse_mode="HTML")
    except Exception as e:
        try: await cb.message.edit_text(f"❌ {e}")
        except: pass


@dp.callback_query(F.data.startswith("adm_no_"))
async def cb_admin_no(cb: CallbackQuery):
    uid = cb.data.replace("adm_no_", "")
    await cb.answer()
    try:
        await bot.send_message(int(uid),
                               "❌ <b>Оплата не подтверждена.</b>\nОбратитесь в поддержку.",
                               parse_mode="HTML")
        await cb.message.edit_text(f"❌ Отказ {uid} отправлен.")
    except Exception as e:
        await cb.message.edit_text(f"Ошибка: {e}")


# ==========================================
# 11. AI-ТОКЕНЫ
# ==========================================
@dp.callback_query(F.data == "menu_ai")
async def cb_menu_ai(cb: CallbackQuery):
    kb = InlineKeyboardBuilder()
    for tokens, info in AI_TOKEN_PACKS.items():
        kb.row(InlineKeyboardButton(
            text=f"🤖 {info['label']} — {info['price_rub']} ₽",
            callback_data=f"buyai_{tokens}"
        ))
    kb.row(InlineKeyboardButton(text="🔑 Активировать ключ", callback_data="activate_ai_key"))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="back_main"))
    await cb.message.edit_text(
        "🤖 <b>AI-токены для ботов</b>\n\nВыберите пакет:",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("buyai_"))
async def cb_buy_ai(cb: CallbackQuery):
    tokens = int(cb.data.replace("buyai_", ""))
    info   = AI_TOKEN_PACKS.get(tokens)
    if not info: return await cb.answer("Пакет не найден", show_alert=True)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💳 Оплатить", url="https://www.donationalerts.com/r/dialoge_engine"))
    kb.row(InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"verifyai_{tokens}"))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="menu_ai"))
    await cb.message.edit_text(
        f"🤖 {info['label']} — <b>{info['price_rub']} ₽</b>",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("verifyai_"))
async def cb_verify_ai(cb: CallbackQuery):
    tokens = int(cb.data.replace("verifyai_", ""))
    info   = AI_TOKEN_PACKS.get(tokens, {})
    akb    = InlineKeyboardBuilder()
    akb.row(
        InlineKeyboardButton(text="✅ Выдать", callback_data=f"adm_ai_ok_{cb.from_user.id}_{tokens}"),
        InlineKeyboardButton(text="❌ Отказ",  callback_data=f"adm_no_{cb.from_user.id}"),
    )
    try:
        await bot.send_message(
            ADM_CHAT,
            f"🤖 AI-токены\n{cb.from_user.full_name} (<code>{cb.from_user.id}</code>)\n"
            f"{info.get('label','?')} | {info.get('price_rub','?')} ₽",
            reply_markup=akb.as_markup(), parse_mode="HTML"
        )
        await cb.message.edit_text("⏳ Заявка отправлена.")
    except Exception:
        await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data.startswith("adm_ai_ok_"))
async def cb_admin_ai_ok(cb: CallbackQuery):
    await cb.answer()
    try:
        parts  = cb.data.split("_")
        tokens = int(parts[-1])
        uid    = parts[-2]
        r      = requests.post(f"{SRV_URL}/api/admin/generate-ai-key",
                               json={"tokens": tokens},
                               headers={"x-admin-token": ADM_SECRET}, timeout=10)
        key    = r.json().get("key") if r.status_code == 200 else None
        if not key: return await cb.message.edit_text(f"❌ {r.text[:200]}")
        await bot.send_message(
            int(uid),
            f"🤖 <b>AI-токены зачислены!</b>\nКлюч: <code>{key}</code>\nТокены: {tokens:,}",
            parse_mode="HTML"
        )
        await cb.message.edit_text(f"✅ AI-ключ выдан {uid}.")
    except Exception as e:
        try: await cb.message.edit_text(f"❌ {e}")
        except: pass

@dp.callback_query(F.data == "activate_ai_key")
async def cb_activate_ai(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text(
        "🔑 Отправьте: <code>AIKEY-XXXX bot_id</code>",
        parse_mode="HTML"
    )
    await state.set_state(AiActivateState.waiting_input)

@dp.message(AiActivateState.waiting_input)
async def process_ai_activation(m: Message, state: FSMContext):
    parts = m.text.strip().split()
    if len(parts) < 2: return await m.answer("Нужно: ключ + ID бота через пробел")
    key_code, bot_id = parts[0].upper(), parts[1]
    await state.clear()
    try:
        r   = requests.post(f"{SRV_URL}/api/bots/activate-ai-key",
                            json={"key": key_code, "bot_id": bot_id, "owner_id": str(m.from_user.id)},
                            timeout=15)
        res = r.json()
        if res.get("ok"):
            await m.answer(f"✅ AI-ключ активирован для <code>{bot_id}</code>!", parse_mode="HTML")
        else:
            await m.answer(f"❌ {res.get('detail', 'Ошибка')}")
    except Exception as e:
        await m.answer(f"❌ {e}")


# ==========================================
# 12. МИНИ-ПРИЛОЖЕНИЯ
# ==========================================
@dp.callback_query(F.data == "menu_miniapps")
async def cb_menu_miniapps(cb: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💳 Купить ключ — 200 ₽", callback_data="buymini_1"))
    kb.row(InlineKeyboardButton(text="🔑 Активировать ключ",   callback_data="activate_miniapp"))
    kb.row(InlineKeyboardButton(text="◀️ Назад",               callback_data="back_main"))
    await cb.message.edit_text(
        "📱 <b>Мини-приложения</b>\n\nСоздайте интерактивные страницы внутри Telegram.",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("buymini_"))
async def cb_buy_mini(cb: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💳 Оплатить 200 ₽", url="https://www.donationalerts.com/r/dialoge_engine"))
    kb.row(InlineKeyboardButton(text="✅ Я оплатил", callback_data="verifymini_1"))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="menu_miniapps"))
    await cb.message.edit_text("📱 Мини-приложение — <b>200 ₽</b>", reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("verifymini_"))
async def cb_verify_mini(cb: CallbackQuery):
    akb = InlineKeyboardBuilder()
    akb.row(
        InlineKeyboardButton(text="✅ Выдать", callback_data=f"adm_mini_ok_{cb.from_user.id}"),
        InlineKeyboardButton(text="❌ Отказ",  callback_data=f"adm_no_{cb.from_user.id}"),
    )
    try:
        await bot.send_message(
            ADM_CHAT,
            f"📱 Мини-приложение\n{cb.from_user.full_name} (<code>{cb.from_user.id}</code>) | 200 ₽",
            reply_markup=akb.as_markup(), parse_mode="HTML"
        )
        await cb.message.edit_text("⏳ Заявка отправлена.")
    except Exception:
        await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data.startswith("adm_mini_ok_"))
async def cb_admin_mini_ok(cb: CallbackQuery):
    await cb.answer()
    uid = cb.data.replace("adm_mini_ok_", "")
    try:
        r   = requests.post(f"{SRV_URL}/api/admin/generate-miniapp-key",
                            json={}, headers={"x-admin-token": ADM_SECRET}, timeout=10)
        key = r.json().get("key") if r.status_code == 200 else None
        if not key: return await cb.message.edit_text(f"❌ {r.text[:200]}")
        await bot.send_message(
            int(uid),
            f"📱 <b>Мини-приложение!</b>\nКлюч: <code>{key}</code>\n\nАктивация в дашборде.",
            parse_mode="HTML"
        )
        await cb.message.edit_text(f"✅ Ключ мини-приложения выдан {uid}.")
    except Exception as e:
        try: await cb.message.edit_text(f"❌ {e}")
        except: pass

@dp.callback_query(F.data == "activate_miniapp")
async def cb_activate_mini(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("🔑 Отправьте ключ (MINI-XXXX-XXXX):")
    await state.set_state(MiniappActivateState.waiting_input)

@dp.message(MiniappActivateState.waiting_input)
async def process_mini_activation(m: Message, state: FSMContext):
    key_code = m.text.strip().upper()
    await state.clear()
    try:
        r   = requests.post(f"{SRV_URL}/api/miniapps/activate-key",
                            json={"key": key_code, "owner_id": str(m.from_user.id)}, timeout=15)
        res = r.json()
        if res.get("ok"):
            await m.answer("✅ Мини-приложение активировано!", parse_mode="HTML")
        else:
            await m.answer(f"❌ {res.get('detail', 'Ошибка')}")
    except Exception as e:
        await m.answer(f"❌ {e}")


# ==========================================
# 13. ЧАТ-ПЛАТФОРМА
# ==========================================
@dp.callback_query(F.data == "menu_chatsite")
async def cb_menu_chatsite(cb: CallbackQuery):
    kb = InlineKeyboardBuilder()
    for days, info in CHAT_SITE_PACKS.items():
        kb.row(InlineKeyboardButton(
            text=f"💬 {info['label']} — {info['price_rub']} ₽",
            callback_data=f"buychat_{days}"
        ))
    kb.row(InlineKeyboardButton(text="🔑 Активировать ключ", callback_data="activate_chat_key"))
    kb.row(InlineKeyboardButton(text="◀️ Назад",             callback_data="back_main"))
    await cb.message.edit_text("💬 <b>Чат-платформа</b>", reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("buychat_"))
async def cb_buy_chatsite(cb: CallbackQuery):
    days = int(cb.data.replace("buychat_", ""))
    info = CHAT_SITE_PACKS.get(days)
    if not info: return await cb.answer("Тариф не найден", show_alert=True)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💳 Оплатить", url="https://www.donationalerts.com/r/dialoge_engine"))
    kb.row(InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"verifychat_{days}"))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="menu_chatsite"))
    await cb.message.edit_text(
        f"💬 {info['label']} — <b>{info['price_rub']} ₽</b>",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("verifychat_"))
async def cb_verify_chatsite(cb: CallbackQuery):
    days = int(cb.data.replace("verifychat_", ""))
    info = CHAT_SITE_PACKS.get(days, {})
    akb  = InlineKeyboardBuilder()
    akb.row(
        InlineKeyboardButton(text="✅ Выдать", callback_data=f"adm_chat_ok_{cb.from_user.id}_{days}"),
        InlineKeyboardButton(text="❌ Отказ",  callback_data=f"adm_no_{cb.from_user.id}"),
    )
    try:
        await bot.send_message(
            ADM_CHAT,
            f"💬 Чат-платформа\n{cb.from_user.full_name} (<code>{cb.from_user.id}</code>)\n"
            f"{info.get('label','?')} | {info.get('price_rub','?')} ₽",
            reply_markup=akb.as_markup(), parse_mode="HTML"
        )
        await cb.message.edit_text("⏳ Заявка отправлена.")
    except Exception:
        await cb.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data.startswith("adm_chat_ok_"))
async def cb_admin_approve_chatsite(cb: CallbackQuery):
    await cb.answer()
    try:
        parts    = cb.data.split("_")
        days     = int(parts[-1])
        uid      = parts[-2]
        info     = CHAT_SITE_PACKS.get(days, {})
        r        = requests.post(
            f"{SRV_URL}/api/chat/keys/generate",
            json={"admin_token": ADM_SECRET, "owner_id": uid,
                  "duration_days": days, "price_rub": info.get("price_rub", 0)},
            timeout=15
        )
        if r.status_code != 200:
            return await cb.message.edit_text(f"❌ {r.status_code} {r.text[:200]}")
        key_code = r.json().get("key_code")
        if not key_code: return await cb.message.edit_text("❌ Сервер не вернул ключ.")
        await bot.send_message(
            int(uid),
            f"🎉 <b>Чат-платформа активирована!</b>\nКлюч: <code>{key_code}</code>\n\n"
            "Активация: Дашборд → Чат-платформы → <b>Лицензия</b>.",
            parse_mode="HTML"
        )
        await cb.message.edit_text(f"✅ Ключ <code>{key_code}</code> выдан {uid}.", parse_mode="HTML")
    except Exception as e:
        try: await cb.message.edit_text(f"❌ {e}")
        except: pass

@dp.callback_query(F.data == "activate_chat_key")
async def cb_activate_chat_key(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("🔑 Отправьте: <code>CHAT-XXXX site_id</code>", parse_mode="HTML")
    await state.set_state(ChatSiteActivateState.waiting_input)

@dp.message(ChatSiteActivateState.waiting_input)
async def process_chat_activation(m: Message, state: FSMContext):
    parts = m.text.strip().split()
    if len(parts) < 2: return await m.answer("Нужно: ключ + ID сайта через пробел")
    key_code, site_id = parts[0].upper(), parts[1]
    await state.clear()
    try:
        r   = requests.post(
            f"{SRV_URL}/api/chat/sites/{site_id}/activate-key",
            json={"owner_id": str(m.from_user.id), "key_code": key_code}, timeout=15
        )
        res = r.json()
        if res.get("ok"):
            await m.answer(f"✅ Активировано до: <b>{res.get('expires_formatted','?')}</b>", parse_mode="HTML")
        else:
            await m.answer(f"❌ {res.get('detail', 'Ошибка')}")
    except Exception as e:
        await m.answer(f"❌ {e}")


# ==========================================
# 14. РЕКЛАМА
# ==========================================
@dp.callback_query(F.data == "menu_ads")
async def cb_menu_ads(cb: CallbackQuery):
    kb = InlineKeyboardBuilder()
    for key, info in AD_TOPUP_PACKS.items():
        kb.row(InlineKeyboardButton(text=f"💳 {info['label']}", callback_data=f"adtopup_{key}"))
    kb.row(InlineKeyboardButton(text="📊 Мои кампании",   callback_data="ads_mycamps"))
    kb.row(InlineKeyboardButton(text="ℹ️ Как работает",   callback_data="ads_info"))
    kb.row(InlineKeyboardButton(text="◀️ Назад",           callback_data="back_main"))
    await cb.message.edit_text(
        "📢 <b>Реклама в бесплатных ботах</b>\n\nОт <b>0.50 ₽</b> за показ. Пополните баланс:",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )

@dp.callback_query(F.data == "ads_info")
async def cb_ads_info(cb: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="menu_ads"))
    await cb.message.edit_text(
        "ℹ️ Пополните баланс → создайте кампанию на <b>dialoge.engine/ads</b> → реклама показывается пользователям бесплатных ботов.\n\n"
        "Мин. бюджет: 100 ₽ | Ставка: от 0.50 ₽/показ",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("adtopup_"))
async def cb_adtopup_select(cb: CallbackQuery):
    pack_key = cb.data.replace("adtopup_", "")
    info     = AD_TOPUP_PACKS.get(pack_key)
    if not info: return await cb.answer("Неверный пакет", show_alert=True)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💳 DonationAlerts", url="https://www.donationalerts.com/r/dialoge_engine"))
    kb.row(InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"adtopup_confirm_{pack_key}"))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="menu_ads"))
    await cb.message.edit_text(
        f"📢 <b>{info['label']}</b>\n\n"
        f"В комментарии: <code>ADS {cb.from_user.id}</code>",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("adtopup_confirm_"))
async def cb_adtopup_confirm(cb: CallbackQuery):
    pack_key = cb.data.replace("adtopup_confirm_", "")
    info     = AD_TOPUP_PACKS.get(pack_key)
    if not info: return await cb.answer("Ошибка", show_alert=True)
    akb = InlineKeyboardBuilder()
    akb.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"adm_ads_ok_{cb.from_user.id}_{pack_key}"),
        InlineKeyboardButton(text="❌ Отказ",       callback_data=f"adm_ads_no_{cb.from_user.id}"),
    )
    try:
        await bot.send_message(
            ADM_CHAT,
            f"📢 Рекламный баланс\n{cb.from_user.full_name} (<code>{cb.from_user.id}</code>)\n{info['label']}",
            reply_markup=akb.as_markup(), parse_mode="HTML"
        )
        await cb.message.edit_text("⏳ Заявка отправлена. До 24 часов.")
    except Exception as e:
        await cb.answer(f"Ошибка: {e}", show_alert=True)

@dp.callback_query(F.data.startswith("adm_ads_ok_"))
async def cb_admin_approve_ads(cb: CallbackQuery):
    if cb.from_user.id != MY_OWNER_ID:
        return await cb.answer("Нет прав", show_alert=True)
    await cb.answer()
    try:
        parts    = cb.data.split("_")
        pack_key = parts[-1]
        tg_uid   = int(parts[-2])
        info     = AD_TOPUP_PACKS.get(pack_key)
        if not info: return await cb.message.edit_text("Пакет не найден.")
        r        = requests.post(
            f"{SRV_URL}/api/ads/topup",
            json={"admin_token": ADM_SECRET, "advertiser_tg_id": str(tg_uid), "amount": info["amount"]},
            timeout=15
        )
        if r.status_code == 200:
            nb = r.json().get("new_balance", "?")
            await bot.send_message(
                tg_uid,
                f"✅ Баланс пополнен на <b>{info['amount']} ₽</b>\nИтого: <b>{nb} ₽</b>\n\n"
                "Создайте кампанию: dialoge.engine/ads",
                parse_mode="HTML"
            )
            await cb.message.edit_text(f"✅ Пополнено {tg_uid}: {info['amount']} ₽. Итого: {nb} ₽")
        else:
            await cb.message.edit_text(f"❌ {r.status_code} {r.text[:200]}")
    except Exception as e:
        try: await cb.message.edit_text(f"❌ {e}")
        except: pass

@dp.callback_query(F.data.startswith("adm_ads_no_"))
async def cb_admin_reject_ads(cb: CallbackQuery):
    tg_uid = int(cb.data.replace("adm_ads_no_", ""))
    await cb.answer()
    try:
        await bot.send_message(tg_uid, "❌ Пополнение не подтверждено.", parse_mode="HTML")
        await cb.message.edit_text(f"❌ Отказ {tg_uid}")
    except Exception as e:
        await cb.message.edit_text(f"Ошибка: {e}")

@dp.callback_query(F.data == "ads_mycamps")
async def cb_ads_mycamps(cb: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="menu_ads"))
    try:
        r     = requests.get(f"{SRV_URL}/api/ads/campaigns",
                             params={"advertiser_tg_id": str(cb.from_user.id)}, timeout=10)
        camps = r.json() if r.status_code == 200 else []
    except Exception:
        camps = []
    if not camps:
        return await cb.message.edit_text(
            "📊 Нет кампаний. Создайте на <b>dialoge.engine/ads</b>",
            reply_markup=kb.as_markup(), parse_mode="HTML"
        )
    em    = {"active": "🟢", "paused": "⏸", "depleted": "🔴"}
    lines = ["📊 <b>Мои кампании:</b>\n"]
    for c in camps[:5]:
        lines.append(
            f"{em.get(c.get('status',''),'⚪')} <b>{c.get('title','?')}</b> | "
            f"{c.get('impressions',0)} показов | {float(c.get('balance',0)):.2f} ₽"
        )
    await cb.message.edit_text("\n".join(lines), reply_markup=kb.as_markup(), parse_mode="HTML")


# ==========================================
# 15. ЗАПУСК
# ==========================================
async def main():
    logger.info("✨ Лицензионный бот запущен (без supabase SDK, pure requests)")
    await bot.set_my_commands([
        BotCommand(command="start", description="🏠 Магазин"),
    ])
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
