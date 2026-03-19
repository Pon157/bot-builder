"""
randomizer_core.py — Бот-рандомайзер для экосистемы.

Конфиг (хранится в колонке config JSONB в таблице bots):
{
  "welcomeMessage": "Привет! ...",
  "lotChannel": "@mychannel",       // канал для публикации розыгрышей
  "adminIds": [123456789],          // список admin_id (числа)
  "lotteries": [...],               // активные и завершённые розыгрыши
  "users": [...],                   // список пользователей
  "stats": { "totalUsers": 0, "blockedCount": 0, "totalLotteries": 0, "history": [] }
}

Запуск: python randomizer_core.py  (переменные из .env: BOT_TOKEN, SUPABASE_URL, SUPABASE_KEY, BOT_ID)
"""

import asyncio
import logging
import os
import sys
import json
import random
import httpx
import re
import time
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramForbiddenError
import html as pyhtml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("RandomizerCore")

# ──────────────────────────────────────────────────────────────
# ENV
# ──────────────────────────────────────────────────────────────
# ── Читаем параметры: или из cfg_path (argv[1]) или из env ──
_CFG_PATH = sys.argv[1] if len(sys.argv) > 1 else None
_CFG_FILE: dict = {}
if _CFG_PATH and os.path.exists(_CFG_PATH):
    try:
        with open(_CFG_PATH, encoding="utf-8") as _f:
            _CFG_FILE = json.load(_f)
    except Exception as _e:
        logger.warning(f"Не удалось прочитать cfg-файл: {_e}")

def _env_or_cfg(key: str, default: str = "") -> str:
    return os.getenv(key) or str(_CFG_FILE.get(key, default))

TOKEN  = _env_or_cfg("BOT_TOKEN") or _CFG_FILE.get("token", "")
BOT_ID = _env_or_cfg("BOT_ID")    or _CFG_FILE.get("id", "")
SB_URL = (_env_or_cfg("SUPABASE_URL") or "").rstrip("/")
SB_KEY = _env_or_cfg("SUPABASE_KEY") or ""
from db_adapter import DBAdapter, init_pg_pool
_db_adapter = DBAdapter(SB_URL, SB_KEY)

if not TOKEN:
    logger.critical("❌ BOT_TOKEN не задан (ни env, ни cfg_file)!")
    sys.exit(1)
if not BOT_ID:
    logger.critical("❌ BOT_ID не задан!")
    sys.exit(1)

bot = Bot(token=TOKEN)
dp  = Dispatcher(storage=MemoryStorage())

# ──────────────────────────────────────────────────────────────
# КОНФИГ (кэш в памяти)
# ──────────────────────────────────────────────────────────────
_config: dict = {}
_config_lock = asyncio.Lock()

def _sb_headers():
    return {
        "apikey": SB_KEY,
        "Authorization": f"Bearer {SB_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }

async def load_config() -> dict:
    global _config
    # Предзаполняем из cfg_file
    if _CFG_FILE:
        pre_cfg = _CFG_FILE.get("config", {})
        if isinstance(pre_cfg, str):
            try: pre_cfg = json.loads(pre_cfg)
            except: pre_cfg = {}
        _config.update(pre_cfg)
        for k in ("lotChannel", "adminIds", "welcomeMessage", "botLink", "lotteries", "users"):
            if k in _CFG_FILE and k not in _config:
                _config[k] = _CFG_FILE[k]
    if BOT_ID:
        try:
            rows = await _db_adapter.get("bots", {"id": f"eq.{BOT_ID}"})
            if rows:
                raw = rows[0].get("config") or {}
                db_cfg = raw if isinstance(raw, dict) else json.loads(raw)
                _config.update(db_cfg)
        except Exception as _le:
            logger.warning(f"load_config DB error: {_le}")
    # Инициализируем обязательные поля
    if "stats" not in _config:
        _config["stats"] = {"totalUsers": 0, "blockedCount": 0, "totalLotteries": 0, "history": []}
    if "lotChannel" not in _config:
        _config["lotChannel"] = ""
    if "adminIds" not in _config:
        _config["adminIds"] = []
    if "lotteries" not in _config:
        _config["lotteries"] = []
    if "users" not in _config:
        _config["users"] = []
    if "welcomeMessage" not in _config:
        _config["welcomeMessage"] = "👋 Привет! Я бот для розыгрышей."
    return _config

async def save_config():
    """Сохраняет _config + stats в БД.
    stats пишем в обоих местах: config.stats и колонку stats.
    """
    stats_val = _config.get("stats", {
        "totalUsers": 0, "blockedCount": 0, "totalLotteries": 0, "history": []
    })
    await _db_adapter.patch("bots", {"id": f"eq.{BOT_ID}"}, {"config": _config, "stats": stats_val})

def cfg() -> dict:
    return _config

def admin_ids() -> list:
    return [int(x) for x in cfg().get("adminIds", []) if str(x).strip().lstrip("-").isdigit()]

def lot_channel() -> str:
    return cfg().get("lotChannel", "")

def users() -> list:
    return cfg().setdefault("users", [])

def lotteries() -> list:
    return cfg().setdefault("lotteries", [])

def get_stats() -> dict:
    return cfg().setdefault("stats", {
        "totalUsers": 0, "blockedCount": 0, "totalLotteries": 0, "history": []
    })

# ──────────────────────────────────────────────────────────────
# FSM
# ──────────────────────────────────────────────────────────────
class CreateLot(StatesGroup):
    post        = State()
    winners     = State()
    channels    = State()
    finish      = State()
    value       = State()

class EditLot(StatesGroup):
    choose_field = State()
    new_value    = State()

class BroadcastState(StatesGroup):
    content  = State()
    confirm  = State()

# ──────────────────────────────────────────────────────────────
# УТИЛИТЫ
# ──────────────────────────────────────────────────────────────
def is_admin(uid: int) -> bool:
    return uid in admin_ids()

def get_user(uid: int) -> Optional[dict]:
    return next((u for u in users() if u["id"] == uid), None)

def upsert_user(msg: Message, referred_by: int = None):
    uid  = msg.from_user.id
    name = msg.from_user.full_name
    uname= msg.from_user.username or ""
    u = get_user(uid)
    if not u:
        u = {"id": uid, "name": name, "username": uname,
             "joined_at": int(time.time()), "is_blocked": False,
             "participations": 0, "wins": 0, "referred_by": referred_by,
             "referrals": 0}
        users().append(u)
        st = get_stats()
        st["totalUsers"] = len(users())
        # Засчитываем реферала
        if referred_by:
            ref_user = get_user(referred_by)
            if ref_user:
                ref_user["referrals"] = ref_user.get("referrals", 0) + 1
        # Обновляем историю
        today = datetime.now().strftime("%d.%m")
        hist = st.setdefault("history", [])
        day = next((d for d in hist if d.get("date") == today), None)
        if not day:
            hist.append({"date": today, "totalUsers": len(users())})
        else:
            day["totalUsers"] = len(users())
        st["history"] = hist[-30:]
    else:
        u["name"]       = name
        u["username"]   = uname
        u["is_blocked"] = False
    return u

def get_lot(lot_id: int) -> Optional[dict]:
    return next((l for l in lotteries() if l["id"] == lot_id), None)

def next_lot_id() -> int:
    ids = [l["id"] for l in lotteries()]
    return max(ids, default=0) + 1

async def check_sub(uid: int, channels_str: str):
    if not channels_str or channels_str.lower().strip() in ("нет", "none", ""):
        return True, []
    bad = []
    for ch in [c.strip() for c in channels_str.split(",") if c.strip()]:
        try:
            m = await bot.get_chat_member(ch, uid)
            if m.status in ("left", "kicked") or (m.status == "restricted" and not getattr(m, "is_member", True)):
                bad.append(ch)
        except Exception:
            bad.append(ch)
    return len(bad) == 0, bad

async def update_lot_card(lot: dict):
    """Обновляет кнопку участия в канале (с цветной кнопкой Bot API 9.4)"""
    if not lot.get("message_id") or not lot_channel():
        return
    _bl = cfg().get("botLink", "").lstrip("@")
    if not _bl:
        me = await bot.get_me()
        _bl = me.username or ""
    count = len(lot.get("participants", []))

    # Используем raw Telegram API для цветных кнопок (Bot API 9.4)
    channel = lot_channel()
    lot_link = f"https://t.me/{_bl}?start=lot_{lot['id']}"
    reply_markup = {
        "inline_keyboard": [[
            {
                "text": f"✅ Участвовать! ({count})",
                "url": lot_link,
                "button_color": "success"   # зелёная кнопка (Bot API 9.4)
            }
        ]]
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{TOKEN}/editMessageReplyMarkup",
                json={
                    "chat_id": channel,
                    "message_id": lot["message_id"],
                    "reply_markup": reply_markup
                }
            )
    except Exception as e:
        logger.debug(f"update_lot_card: {e}")

async def finalize_lot(lot_id: int):
    lot = get_lot(lot_id)
    if not lot or lot["status"] != "active":
        return
    lot["status"] = "closed"
    # Обновляем счётчик завершённых лотерей в stats
    st = get_stats()
    st["totalLotteries"] = len([l for l in lotteries() if l["status"] == "closed"])
    participants = lot.get("participants", [])

    if not participants:
        try:
            await bot.send_message(lot_channel(), f"⚠️ Розыгрыш #{lot_id} завершён. Участников не набралось.",
                                   reply_to_message_id=lot.get("message_id"))
        except Exception:
            pass
        await save_config()
        return

    n_win = min(len(participants), lot.get("winners_count", 1))
    winners = random.sample(participants, n_win)
    lot["winners"] = winners
    lot["finished_at"] = datetime.now().strftime("%d.%m.%Y %H:%M")

    mentions = []
    for w in winners:
        safe = pyhtml.escape(w.get("name", "Участник"))
        if w.get("username"):
            mentions.append(f"@{w['username']}")
        else:
            mentions.append(f"<a href='tg://user?id={w['id']}'>{safe}</a>")
        u = get_user(w["id"])
        if u:
            u["wins"] = u.get("wins", 0) + 1
        try:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🎉 Отлично!", callback_data="winner_ack")
            ]])
            await bot.send_message(
                w["id"],
                f"🏆 <b>Вы победили в розыгрыше #{lot_id}!</b>\nСвяжитесь с администратором для получения приза.",
                parse_mode="HTML", reply_markup=kb
            )
        except TelegramForbiddenError:
            u2 = get_user(w["id"])
            if u2: u2["is_blocked"] = True
        except Exception:
            pass

    result_text = (
        f"🎊 <b>ИТОГИ РОЗЫГРЫША #{lot_id}</b>\n\n"
        f"🏆 Победители: {', '.join(mentions)}\n"
        f"📊 Всего участников: {len(participants)}\n\n"
        f"Победители получили уведомления в ЛС!"
    )
    try:
        await bot.send_message(lot_channel(), result_text, parse_mode="HTML",
                               reply_to_message_id=lot.get("message_id"))
    except Exception:
        pass

    # Уведомить всех участников кроме победителей
    winner_ids = {w["id"] for w in winners}
    for p in participants:
        if p["id"] not in winner_ids:
            try:
                await bot.send_message(
                    p["id"],
                    f"😔 Розыгрыш #{lot_id} завершён. На этот раз не повезло. Следите за новыми розыгрышами!",
                )
            except Exception:
                pass

    st = get_stats()
    st["totalLotteries"] = st.get("totalLotteries", 0) + 1
    await save_config()

# ──────────────────────────────────────────────────────────────
# СТАРТ
# ──────────────────────────────────────────────────────────────
@dp.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject, state: FSMContext):
    uid  = message.from_user.id
    args = command.args or ""

    # Разбираем реферальные параметры
    referred_by = None
    lot_id_from_link = None

    # Формат: lot_{id}_ref_{referrer_uid} или lot_{id} или ref_{referrer_uid}
    if args.startswith("lot_"):
        parts = args.split("_ref_")
        lot_part = parts[0]  # "lot_123"
        try:
            lot_id_from_link = int(lot_part.split("_")[1])
        except Exception:
            pass
        if len(parts) > 1:
            try:
                referred_by = int(parts[1])
                if referred_by == uid:
                    referred_by = None  # нельзя рефералить самого себя
            except Exception:
                pass
    elif args.startswith("ref_"):
        try:
            referred_by = int(args.split("_")[1])
            if referred_by == uid:
                referred_by = None
        except Exception:
            pass

    upsert_user(message, referred_by=referred_by)

    # Участие в розыгрыше через deep link
    if lot_id_from_link is not None:
        lot_id = lot_id_from_link
        lot = get_lot(lot_id)
        if not lot:
            return await message.answer("❌ Розыгрыш не найден.")
        if lot["status"] != "active":
            return await message.answer("❌ Розыгрыш уже завершён.")

        already = any(p["id"] == uid for p in lot.get("participants", []))
        if already:
            # Показываем реферальную ссылку участнику
            _bl_r = cfg().get("botLink", "").lstrip("@")
            if not _bl_r:
                _me_r = await bot.get_me()
                _bl_r = _me_r.username or ""
            ref_link = f"https://t.me/{_bl_r}?start=lot_{lot_id}_ref_{uid}"
            kb_ref = InlineKeyboardBuilder()
            kb_ref.button(text="🔗 Моя реферальная ссылка", url=ref_link)
            kb_ref.adjust(1)
            return await message.answer(
                f"⚠️ Вы уже участвуете в розыгрыше #{lot_id}. Ждите результатов!\n\n"
                f"📤 <b>Пригласите друзей</b> по вашей ссылке — они автоматически попадут в розыгрыш через вас!\n"
                f"<code>{ref_link}</code>",
                reply_markup=kb_ref.as_markup(),
                parse_mode="HTML"
            )

        is_sub, bad = await check_sub(uid, lot.get("channels", ""))
        if not is_sub:
            me = await bot.get_me()
            kb = InlineKeyboardBuilder()
            for ch in bad:
                ch_c = ch.replace("@", "").strip()
                kb.button(text=f"📢 Подписаться: {ch}", url=f"https://t.me/{ch_c}")
            # Сохраняем реферала в ссылке проверки
            ref_suffix = f"_ref_{referred_by}" if referred_by else ""
            kb.button(text="🔄 Проверить подписку", url=f"https://t.me/{me.username}?start=lot_{lot_id}{ref_suffix}")
            kb.adjust(1)
            return await message.answer(
                "⚠️ <b>Для участия нужно подписаться:</b>",
                reply_markup=kb.as_markup(), parse_mode="HTML"
            )

        lot.setdefault("participants", []).append({
            "id": uid,
            "name": message.from_user.full_name,
            "username": message.from_user.username or "",
            "joined_at": int(time.time()),
            "referred_by": referred_by
        })
        u = get_user(uid)
        if u: u["participations"] = u.get("participations", 0) + 1
        await update_lot_card(lot)

        # Уведомляем реферера
        if referred_by:
            ref_user = get_user(referred_by)
            if ref_user:
                ref_user["referrals"] = ref_user.get("referrals", 0) + 1
            try:
                await bot.send_message(
                    referred_by,
                    f"🎉 По вашей реферальной ссылке в розыгрыш #{lot_id} вступил "
                    f"<b>{pyhtml.escape(message.from_user.full_name)}</b>!",
                    parse_mode="HTML"
                )
            except Exception:
                pass

        # Проверяем лимит по участникам
        if lot["finish_type"] == "count" and len(lot["participants"]) >= int(lot["finish_value"]):
            await finalize_lot(lot_id)
        else:
            await save_config()

        # Формируем реферальную ссылку для нового участника
        _bl2 = cfg().get("botLink", "").lstrip("@")
        if not _bl2:
            _me2 = await bot.get_me()
            _bl2 = _me2.username or ""
        ref_link_new = f"https://t.me/{_bl2}?start=lot_{lot_id}_ref_{uid}"
        kb_success = InlineKeyboardBuilder()
        kb_success.button(text="🔗 Пригласить друзей", url=ref_link_new)
        kb_success.adjust(1)
        return await message.answer(
            f"✅ <b>Вы зарегистрированы в розыгрыше #{lot_id}!</b>\nУдачи! 🍀\n\n"
            f"📤 <b>Поделитесь ссылкой с друзьями:</b>\n<code>{ref_link_new}</code>",
            reply_markup=kb_success.as_markup(),
            parse_mode="HTML"
        )

    welcome = cfg().get("welcomeMessage") or "👋 Привет! Я бот для розыгрышей."
    kb_rows = [
        [InlineKeyboardButton(text="🎲 Активные розыгрыши", callback_data="active_lots"),
         InlineKeyboardButton(text="📊 Мой профиль",         callback_data="my_profile")],
    ]
    if is_admin(uid):
        kb_rows.append([InlineKeyboardButton(text="🛠 Панель администратора", callback_data="admin_main")])
    await message.answer(
        f"{welcome}\n\n<b>{pyhtml.escape(message.from_user.first_name)}</b>, выбери действие:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
        parse_mode="HTML"
    )
    await save_config()

@dp.callback_query(F.data == "winner_ack")
async def winner_ack(c: CallbackQuery):
    await c.answer("🏆 Поздравляем ещё раз!", show_alert=True)

# ──────────────────────────────────────────────────────────────
# МЕНЮ ПОЛЬЗОВАТЕЛЯ
# ──────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "active_lots")
async def show_active_lots(c: CallbackQuery):
    me = await bot.get_me()
    active = [l for l in lotteries() if l["status"] == "active"]
    kb = InlineKeyboardBuilder()
    if not active:
        await c.answer("Активных розыгрышей нет 😔", show_alert=True)
        return
    text = "🎲 <b>АКТИВНЫЕ РОЗЫГРЫШИ:</b>\n\n"
    for lot in active:
        text += (f"🔹 <b>Лот #{lot['id']}</b> | 🏆 {lot['winners_count']} победителей\n"
                 f"   👥 Участников: {len(lot.get('participants', []))}\n")
        if lot["finish_type"] == "time":
            text += f"   ⏳ Завершится: {lot['finish_value']}\n"
        else:
            text += f"   🎯 До финиша: {lot['finish_value']} участников\n"
        text += "---\n"
        kb.button(text=f"🎲 Участвовать #{lot['id']}",
                  url=f"https://t.me/{me.username}?start=lot_{lot['id']}")
    kb.button(text="🔙 Назад", callback_data="to_start")
    kb.adjust(1)
    try:
        await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    except Exception:
        await c.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "my_profile")
async def my_profile(c: CallbackQuery):
    uid = c.from_user.id
    u = get_user(uid) or {}
    _bl_p = cfg().get("botLink", "").lstrip("@")
    if not _bl_p:
        me_p = await bot.get_me()
        _bl_p = me_p.username or ""
    ref_link = f"https://t.me/{_bl_p}?start=ref_{uid}"
    kb = InlineKeyboardBuilder()
    kb.button(text="🔗 Моя реферальная ссылка", url=ref_link)
    kb.button(text="🔙 Назад", callback_data="to_start")
    kb.adjust(1)
    text = (
        f"📊 <b>Ваш профиль</b>\n\n"
        f"👤 {pyhtml.escape(c.from_user.full_name)}\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"🎲 Участий: <b>{u.get('participations', 0)}</b>\n"
        f"🏆 Побед: <b>{u.get('wins', 0)}</b>\n"
        f"👥 Рефералов: <b>{u.get('referrals', 0)}</b>\n"
        f"📅 Зарегистрирован: {datetime.fromtimestamp(u.get('joined_at', time.time())).strftime('%d.%m.%Y')}\n\n"
        f"🔗 <b>Ваша реферальная ссылка:</b>\n<code>{ref_link}</code>"
    )
    try:
        await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    except Exception:
        await c.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "to_start")
async def back_to_start(c: CallbackQuery, state: FSMContext):
    await state.clear()
    try: await c.message.delete()
    except: pass
    uid  = c.from_user.id
    welcome = cfg().get("welcomeMessage") or "👋 Привет!"
    kb_rows = [
        [InlineKeyboardButton(text="🎲 Активные розыгрыши", callback_data="active_lots"),
         InlineKeyboardButton(text="📊 Мой профиль",         callback_data="my_profile")],
    ]
    if is_admin(uid):
        kb_rows.append([InlineKeyboardButton(text="🛠 Панель администратора", callback_data="admin_main")])
    await c.message.answer(welcome, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))

# ──────────────────────────────────────────────────────────────
# ЦВЕТНЫЕ КНОПКИ (Bot API 9.4+)
# ──────────────────────────────────────────────────────────────
def colored_btn(text: str, callback_data: str = None, url: str = None, color: str = None) -> InlineKeyboardButton:
    """
    color: 'danger' (красный), 'success' (зелёный), 'primary' (синий), None (стандартный)
    """
    kwargs = {"text": text}
    if callback_data:
        kwargs["callback_data"] = callback_data
    if url:
        kwargs["url"] = url
    # Bot API 9.4: button_color через extra kwargs не поддерживается в aiogram напрямую,
    # используем кастомный workaround через raw payload
    if color:
        kwargs["button_color"] = color  # aiogram >=3.7 с Bot API 9.4 поддерживает
    return InlineKeyboardButton(**kwargs)

# ──────────────────────────────────────────────────────────────
# ADMIN PANEL
# ──────────────────────────────────────────────────────────────
def admin_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать розыгрыш", callback_data="adm_create"),
         InlineKeyboardButton(text="📋 Список лотов",     callback_data="adm_lots")],
        [InlineKeyboardButton(text="📢 Рассылка",         callback_data="adm_broadcast"),
         InlineKeyboardButton(text="👥 Пользователи",     callback_data="adm_users")],
        [InlineKeyboardButton(text="🔙 В меню",           callback_data="to_start")],
    ])

@dp.callback_query(F.data == "admin_main")
async def admin_panel(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        return await c.answer("⛔ Нет доступа", show_alert=True)
    st = get_stats()
    text = (
        f"🛠 <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n\n"
        f"👥 Всего пользователей: <b>{st.get('totalUsers', len(users()))}</b>\n"
        f"🚫 Заблокировали бота: <b>{sum(1 for u in users() if u.get('is_blocked'))}</b>\n"
        f"🎲 Всего розыгрышей: <b>{len(lotteries())}</b>\n"
        f"▶️ Активных: <b>{sum(1 for l in lotteries() if l['status'] == 'active')}</b>"
    )
    try:
        await c.message.edit_text(text, reply_markup=admin_main_kb(), parse_mode="HTML")
    except Exception:
        await c.message.answer(text, reply_markup=admin_main_kb(), parse_mode="HTML")

# ── Список лотов ──
@dp.callback_query(F.data == "adm_lots")
async def adm_lots_list(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer("⛔", show_alert=True)
    lots = sorted(lotteries(), key=lambda x: x["id"], reverse=True)[:15]
    kb = InlineKeyboardBuilder()
    for lot in lots:
        status_icon = "▶️" if lot["status"] == "active" else "✅"
        kb.button(text=f"{status_icon} Лот #{lot['id']} ({len(lot.get('participants', []))} уч.)",
                  callback_data=f"adm_lot_{lot['id']}")
    kb.button(text="🔙 Назад", callback_data="admin_main")
    kb.adjust(1)
    try:
        await c.message.edit_text("📋 <b>Розыгрыши:</b>", reply_markup=kb.as_markup(), parse_mode="HTML")
    except Exception:
        await c.message.answer("📋 <b>Розыгрыши:</b>", reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("adm_lot_"))
async def adm_lot_detail(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer("⛔", show_alert=True)
    lot_id = int(c.data.split("_")[2])
    lot = get_lot(lot_id)
    if not lot: return await c.answer("Лот не найден", show_alert=True)
    parts = lot.get("participants", [])
    wins  = lot.get("winners", [])

    # Реферальная статистика
    ref_count = sum(1 for p in parts if p.get("referred_by"))

    text = (
        f"🎲 <b>Лот #{lot_id}</b>\n"
        f"Статус: {'▶️ Активен' if lot['status'] == 'active' else '✅ Завершён'}\n"
        f"🏆 Победителей: {lot['winners_count']}\n"
        f"👥 Участников: {len(parts)}\n"
        f"🔗 Пришли по реферальной ссылке: {ref_count}\n"
        f"📢 Каналы: {lot.get('channels', 'нет')}\n"
        f"Финиш: {'⏰ по времени' if lot.get('finish_type') == 'time' else '👥 по участникам'} → {lot.get('finish_value', '?')}\n"
    )
    if wins:
        win_names = ", ".join([f"@{w.get('username') or w['id']}" for w in wins])
        text += f"🏆 Победители: {win_names}\n"

    kb = InlineKeyboardBuilder()
    if lot["status"] == "active":
        kb.button(text="✏️ Редактировать", callback_data=f"adm_edit_{lot_id}")
        kb.button(text="⏹ Завершить досрочно", callback_data=f"adm_stop_{lot_id}")
    kb.button(text="🔙 К списку", callback_data="adm_lots")
    kb.adjust(2, 1)
    try:
        await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    except Exception:
        await c.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("adm_stop_"))
async def adm_stop_lot(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer("⛔", show_alert=True)
    lot_id = int(c.data.split("_")[2])
    await c.answer("Завершаю розыгрыш...", show_alert=False)
    await finalize_lot(lot_id)
    await c.answer("✅ Розыгрыш завершён!", show_alert=True)
    await adm_lots_list(c)

# ──────────────────────────────────────────────────────────────
# РЕДАКТИРОВАНИЕ АКТИВНОГО ЛОТА
# ──────────────────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("adm_edit_"))
async def adm_edit_lot(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return await c.answer("⛔", show_alert=True)
    lot_id = int(c.data.split("_")[2])
    lot = get_lot(lot_id)
    if not lot or lot["status"] != "active":
        return await c.answer("Лот не найден или уже завершён", show_alert=True)
    await state.update_data(edit_lot_id=lot_id)
    await state.set_state(EditLot.choose_field)
    kb = InlineKeyboardBuilder()
    kb.button(text="🏆 Кол-во победителей",  callback_data="ef_winners")
    kb.button(text="📢 Каналы подписки",      callback_data="ef_channels")
    kb.button(text="⏰ Условие завершения",   callback_data="ef_finish")
    kb.button(text="❌ Отмена",               callback_data=f"adm_lot_{lot_id}")
    kb.adjust(2, 1, 1)
    await c.message.edit_text(
        f"✏️ <b>Редактирование лота #{lot_id}</b>\n\nЧто изменить?",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )

@dp.callback_query(F.data.in_({"ef_winners", "ef_channels", "ef_finish"}), EditLot.choose_field)
async def adm_edit_choose(c: CallbackQuery, state: FSMContext):
    field_map = {
        "ef_winners":  ("winners_count", "🏆 Введи новое количество победителей:"),
        "ef_channels": ("channels",      "📢 Введи каналы через запятую (или 'нет'):"),
        "ef_finish":   ("finish_value",  "⏰ Введи новое значение:\n• Для времени: дата в формате <code>DD.MM.YYYY HH:MM</code>\n• Для участников: число"),
    }
    field, prompt = field_map[c.data]
    await state.update_data(edit_field=field)
    await state.set_state(EditLot.new_value)
    await c.message.edit_text(prompt, parse_mode="HTML")

@dp.message(EditLot.new_value)
async def adm_edit_apply(m: Message, state: FSMContext):
    data = await state.get_data()
    lot_id = data["edit_lot_id"]
    field  = data["edit_field"]
    lot = get_lot(lot_id)
    if not lot:
        await state.clear()
        return await m.answer("❌ Лот не найден.")

    val = m.text.strip()
    if field == "winners_count":
        if not val.isdigit() or int(val) < 1:
            return await m.answer("❌ Введи число (минимум 1)!")
        lot["winners_count"] = int(val)
    elif field == "channels":
        lot["channels"] = "" if val.lower() in ("нет", "none", "-") else val
    elif field == "finish_value":
        if lot["finish_type"] == "count":
            if not val.isdigit():
                return await m.answer("❌ Введи число участников!")
            lot["finish_value"] = val
        else:
            try:
                datetime.strptime(val, "%d.%m.%Y %H:%M")
                lot["finish_value"] = val
            except ValueError:
                return await m.answer("❌ Неверный формат! Используй: <code>DD.MM.YYYY HH:MM</code>", parse_mode="HTML")

    await state.clear()
    await save_config()
    await m.answer(f"✅ Лот #{lot_id} обновлён!", parse_mode="HTML")

    # Обновляем карточку в канале
    await update_lot_card(lot)

# ── Пользователи ──
@dp.callback_query(F.data == "adm_users")
async def adm_users(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer("⛔", show_alert=True)
    all_u = users()
    blocked = [u for u in all_u if u.get("is_blocked")]
    top = sorted(all_u, key=lambda u: u.get("participations", 0), reverse=True)[:10]
    text = (
        f"👥 <b>ПОЛЬЗОВАТЕЛИ</b>\n\n"
        f"Всего: <b>{len(all_u)}</b> | Заблокировали: <b>{len(blocked)}</b>\n\n"
        f"<b>Топ по участиям:</b>\n"
    )
    for u in top:
        uname = f"@{u['username']}" if u.get("username") else f"ID:{u['id']}"
        text += f"• {pyhtml.escape(u.get('name','?'))} ({uname}) — {u.get('participations',0)} уч., {u.get('wins',0)} побед\n"
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="admin_main")
    try:
        await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    except Exception:
        await c.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

# ──────────────────────────────────────────────────────────────
# СОЗДАНИЕ РОЗЫГРЫША (Wizard)
# ──────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "adm_create")
async def create_step1(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return await c.answer("⛔", show_alert=True)
    await state.set_state(CreateLot.post)
    await c.message.answer(
        "📝 <b>Шаг 1/5 — Пост для канала</b>\n\n"
        "Отправь текст (поддерживается HTML), фото с подписью или стикер.\n"
        "Это будет опубликовано в канале розыгрышей.",
        parse_mode="HTML"
    )

@dp.message(CreateLot.post)
async def create_step2(m: Message, state: FSMContext):
    post = {
        "text":    m.caption or m.text or "",
        "photo_id": m.photo[-1].file_id if m.photo else None,
        "sticker_id": m.sticker.file_id if m.sticker else None,
    }
    await state.update_data(post=post)
    await state.set_state(CreateLot.winners)
    await m.answer("2️⃣ <b>Количество победителей?</b>\n\n🏆 Сколько человек получат приз? (введи число)", parse_mode="HTML")

@dp.message(CreateLot.winners)
async def create_step3(m: Message, state: FSMContext):
    if not m.text or not m.text.isdigit() or int(m.text) < 1:
        return await m.answer("❌ Введи число (минимум 1)!")
    await state.update_data(winners_count=int(m.text))
    await state.set_state(CreateLot.channels)
    await m.answer(
        "3️⃣ <b>Каналы для обязательной подписки</b>\n\n"
        "Введи через запятую (@channel1, @channel2) или напиши <b>нет</b>",
        parse_mode="HTML"
    )

@dp.message(CreateLot.channels)
async def create_step4(m: Message, state: FSMContext):
    channels = "" if m.text.lower().strip() in ("нет", "none", "-") else m.text.strip()
    await state.update_data(channels=channels)
    await state.set_state(CreateLot.finish)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⏰ По времени",       callback_data="ft_time"),
        InlineKeyboardButton(text="👥 По участникам",   callback_data="ft_count"),
    ]])
    await m.answer("4️⃣ <b>Условие завершения:</b>", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.in_({"ft_time", "ft_count"}))
async def create_step5(c: CallbackQuery, state: FSMContext):
    ft = "time" if c.data == "ft_time" else "count"
    await state.update_data(finish_type=ft)
    await state.set_state(CreateLot.value)
    if ft == "time":
        prompt = "⏰ 5️⃣ Через сколько <b>часов</b> завершить розыгрыш?\n\nНапример: <code>24</code> = через сутки"
    else:
        prompt = "👥 5️⃣ При каком количестве <b>участников</b> завершить розыгрыш?\n\nНапример: <code>100</code> = когда наберётся 100 участников"
    await c.message.edit_text(prompt, parse_mode="HTML")

@dp.message(CreateLot.value)
async def create_finish(m: Message, state: FSMContext):
    if not m.text or not m.text.isdigit():
        return await m.answer("❌ Введи число!")
    data = await state.get_data()
    await state.clear()

    ft    = data["finish_type"]
    val   = int(m.text)
    post  = data["post"]
    wc    = data["winners_count"]
    ch    = data.get("channels", "")

    if ft == "time":
        finish_value = (datetime.now() + timedelta(hours=val)).strftime("%d.%m.%Y %H:%M")
    else:
        finish_value = str(val)

    lot_id = next_lot_id()
    lot = {
        "id": lot_id,
        "text": post["text"],
        "photo_id": post["photo_id"],
        "sticker_id": post["sticker_id"],
        "channels": ch,
        "finish_type": ft,
        "finish_value": finish_value,
        "winners_count": wc,
        "status": "active",
        "participants": [],
        "winners": [],
        "message_id": None,
        "created_at": datetime.now().strftime("%d.%m.%Y %H:%M"),
    }
    lotteries().append(lot)

    _bl2 = cfg().get("botLink", "").lstrip("@")
    if not _bl2:
        _me2 = await bot.get_me()
        _bl2 = _me2.username or ""

    lot_link = f"https://t.me/{_bl2}?start=lot_{lot_id}"
    # Цветная кнопка (Bot API 9.4) через raw markup
    colored_kb = {
        "inline_keyboard": [[
            {"text": "✅ Участвовать! (0)", "url": lot_link, "button_color": "success"}
        ]]
    }
    # aiogram markup для fallback
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Участвовать! (0)", url=lot_link)

    try:
        if not lot_channel():
            raise ValueError("Не задан канал (lotChannel) в конфиге")
        if post["photo_id"]:
            sent = await bot.send_photo(
                lot_channel(), post["photo_id"],
                caption=post["text"] or None,
                reply_markup=kb.as_markup(),
                parse_mode="HTML"
            )
        elif post["sticker_id"]:
            await bot.send_sticker(lot_channel(), post["sticker_id"])
            sent = await bot.send_message(lot_channel(), "🎁 Новый розыгрыш! Нажми кнопку ниже.",
                                          reply_markup=kb.as_markup())
        else:
            sent = await bot.send_message(lot_channel(), post["text"],
                                          reply_markup=kb.as_markup(), parse_mode="HTML")
        lot["message_id"] = sent.message_id
        # Применяем цветную кнопку поверх отправленного сообщения
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{TOKEN}/editMessageReplyMarkup",
                json={
                    "chat_id": lot_channel(),
                    "message_id": sent.message_id,
                    "reply_markup": colored_kb
                }
            )
        await m.answer(f"✅ <b>Лот #{lot_id} опубликован в {lot_channel()}!</b>", parse_mode="HTML")
    except Exception as e:
        await m.answer(f"⚠️ Лот создан в базе, но не опубликован: {e}")

    await save_config()

# ──────────────────────────────────────────────────────────────
# РАССЫЛКА (только для admin из конфига)
# ──────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "adm_broadcast")
async def broadcast_start(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return await c.answer("⛔", show_alert=True)
    await state.set_state(BroadcastState.content)
    await c.message.answer(
        "📢 <b>Рассылка</b>\n\nОтправь сообщение для рассылки (текст, фото, видео — всё поддерживается).\n\n"
        "/cancel — отмена", parse_mode="HTML"
    )

@dp.message(Command("cancel"))
async def cancel_any(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("❌ Действие отменено.")

@dp.message(BroadcastState.content)
async def broadcast_preview(m: Message, state: FSMContext):
    await state.update_data(msg_id=m.message_id, chat_id=m.chat.id)
    await state.set_state(BroadcastState.confirm)
    all_u = [u for u in users() if not u.get("is_blocked")]
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"✅ Разослать ({len(all_u)} чел.)", callback_data="bc_confirm"),
        InlineKeyboardButton(text="❌ Отмена",                         callback_data="bc_cancel"),
    ]])
    await m.answer(f"👆 Вот как будет выглядеть сообщение.\nРазослать <b>{len(all_u)}</b> пользователям?",
                   reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "bc_cancel")
async def bc_cancel(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.edit_text("❌ Рассылка отменена.")

@dp.callback_query(F.data == "bc_confirm")
async def bc_confirm(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    all_u = [u for u in users() if not u.get("is_blocked")]
    await c.message.edit_text(f"🚀 Начинаю рассылку на {len(all_u)} пользователей...")
    ok = bad = 0
    for u in all_u:
        try:
            await bot.copy_message(chat_id=u["id"], from_chat_id=data["chat_id"], message_id=data["msg_id"])
            ok += 1
        except TelegramForbiddenError:
            u["is_blocked"] = True
            bad += 1
        except Exception:
            bad += 1
        await asyncio.sleep(0.05)
    # Обновляем blockedCount в stats
    st = get_stats()
    st["blockedCount"] = len([u for u in users() if u.get("is_blocked")])
    await save_config()
    await c.message.answer(f"🏁 Рассылка завершена.\n✅ Доставлено: {ok}\n❌ Ошибок/блок: {bad}")

# ──────────────────────────────────────────────────────────────
# КОМАНДА /broadcast (из ботэдитора через adminId)
# ──────────────────────────────────────────────────────────────
@dp.message(Command("broadcast"))
async def cmd_broadcast(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        return await m.answer("⛔ Нет доступа.")
    await state.set_state(BroadcastState.content)
    await m.answer(
        "📢 <b>Рассылка через команду</b>\n\nОтправь сообщение для рассылки.\n/cancel — отмена",
        parse_mode="HTML"
    )

# ──────────────────────────────────────────────────────────────
# МОНИТОРИНГ ВРЕМЕНИ
# ──────────────────────────────────────────────────────────────
async def time_monitor():
    logger.info("⏰ Монитор времени запущен")
    while True:
        try:
            now = datetime.now()
            for lot in lotteries():
                if lot["status"] != "active" or lot["finish_type"] != "time":
                    continue
                try:
                    finish_dt = datetime.strptime(lot["finish_value"], "%d.%m.%Y %H:%M")
                    if now >= finish_dt:
                        logger.info(f"⏰ Лот #{lot['id']} завершается по времени")
                        await finalize_lot(lot["id"])
                except ValueError:
                    pass
        except Exception as e:
            logger.error(f"Ошибка в time_monitor: {e}")
        await asyncio.sleep(60)

# ──────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────
async def main():
    await init_pg_pool()
    logger.info(f"▶️  Запуск RandomizerCore (bot_id={BOT_ID})")
    await load_config()
    asyncio.create_task(time_monitor())
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
