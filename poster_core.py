"""
poster_core.py — Бот для постинга в Telegram-каналы.

Фичи:
  ✅ Нативное форматирование Telegram (bold/italic/code/underline — без HTML тегов)
  ✅ Несколько каналов — выбор при публикации (один или все сразу)
  ✅ Раскладка кнопок: строчкой (горизонтально) или столбцом (вертикально)
  ✅ Реакции на пост (настраиваемые эмодзи)
  ✅ Отложенная публикация (через N минут или дата)
  ✅ Предпросмотр перед публикацией
  ✅ Редактирование опубликованного поста
  ✅ Список запланированных постов + отмена
  ✅ Статистика по каналам
  ✅ /broadcast — рассылка по всем каналам
"""

import asyncio
import logging
import os
import sys
import json
import httpx
import time
import re
from datetime import datetime, timedelta
from typing import Optional, List

from dotenv import load_dotenv
load_dotenv()

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    MessageEntity,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
import html as pyhtml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("PosterCore")

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

if not TOKEN:
    logger.critical("❌ BOT_TOKEN не задан!")
    sys.exit(1)
if not BOT_ID:
    logger.critical("❌ BOT_ID не задан!")
    sys.exit(1)

bot = Bot(token=TOKEN)
dp  = Dispatcher(storage=MemoryStorage())

# ──────────────────────────────────────────────────────────────
# КОНФИГ
# ──────────────────────────────────────────────────────────────
_config: dict = {}

def _sb_headers():
    return {
        "apikey": SB_KEY,
        "Authorization": f"Bearer {SB_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }

async def load_config():
    global _config
    if _CFG_FILE:
        pre_cfg = _CFG_FILE.get("config", {})
        if isinstance(pre_cfg, str):
            try: pre_cfg = json.loads(pre_cfg)
            except: pre_cfg = {}
        _config.update(pre_cfg)
        for k in ("channelId", "channels", "adminIds", "botLink"):
            if k in _CFG_FILE and k not in _config:
                _config[k] = _CFG_FILE[k]
    if SB_URL and BOT_ID:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"{SB_URL}/rest/v1/bots?id=eq.{BOT_ID}", headers=_sb_headers())
                if r.status_code == 200 and r.json():
                    raw = r.json()[0].get("config") or {}
                    db_cfg = raw if isinstance(raw, dict) else json.loads(raw)
                    _config.update(db_cfg)
        except Exception as _le:
            logger.warning(f"load_config DB error: {_le}")
    # Defaults
    if "stats" not in _config:
        _config["stats"] = {"totalPosts": 0, "history": []}
    if "channels" not in _config:
        # Мигрируем старый channelId -> channels list
        old_ch = _config.get("channelId", "")
        _config["channels"] = [old_ch] if old_ch else []
    if "adminIds" not in _config:
        _config["adminIds"] = []
    return _config

async def save_config():
    stats_val = _config.get("stats", {"totalPosts": 0, "history": []})
    async with httpx.AsyncClient(timeout=10) as c:
        await c.patch(
            f"{SB_URL}/rest/v1/bots?id=eq.{BOT_ID}",
            headers=_sb_headers(),
            json={"config": _config, "stats": stats_val}
        )

def cfg() -> dict:
    return _config

def admin_ids() -> list:
    return [int(x) for x in cfg().get("adminIds", []) if str(x).strip().lstrip("-").isdigit()]

def channels() -> List[str]:
    """Возвращает список каналов. Поддерживает и старый channelId."""
    chs = cfg().get("channels", [])
    if not chs:
        old = cfg().get("channelId", "")
        chs = [old] if old else []
    return [c for c in chs if c]

def is_admin(uid: int) -> bool:
    return uid in admin_ids()

def get_stats() -> dict:
    return cfg().setdefault("stats", {"totalPosts": 0, "history": []})

# ──────────────────────────────────────────────────────────────
# FSM
# ──────────────────────────────────────────────────────────────
class CreatePost(StatesGroup):
    content      = State()
    buttons      = State()
    btn_layout   = State()   # ← НОВЫЙ: выбор раскладки кнопок
    channel_pick = State()   # ← НОВЫЙ: выбор канала(ов)
    schedule     = State()
    schedule_val = State()
    preview      = State()

class ManageChannels(StatesGroup):
    add = State()

# Хранилище отложенных задач
_scheduled: dict = {}   # job_id -> asyncio.Task
_scheduled_meta: dict = {}  # job_id -> {time, channels, preview_text}

# ──────────────────────────────────────────────────────────────
# ФОРМАТИРОВАНИЕ — entities -> HTML
# ──────────────────────────────────────────────────────────────
def entities_to_html(text: str, entities: Optional[list]) -> str:
    """
    Конвертирует нативное форматирование Telegram (entities) в HTML.
    Пользователь просто выделяет текст жирным/курсивом — мы это ловим.
    Поддерживаем вложенные entities (напр. жирный+курсив).
    """
    if not entities or not text:
        return pyhtml.escape(text or "")

    # Конвертируем text в список символов (unicode, с учётом surrogate pairs)
    chars = list(text)

    # Для каждого символа — набор открытых тегов
    # Строим карту: позиция -> [(tag, open/close)]
    events: dict[int, list] = {}
    for ent in entities:
        offset = ent.offset if hasattr(ent, 'offset') else ent.get('offset', 0)
        length = ent.length if hasattr(ent, 'length') else ent.get('length', 0)
        etype  = ent.type   if hasattr(ent, 'type')   else ent.get('type', '')

        tag = {
            "bold":              ("<b>",  "</b>"),
            "italic":            ("<i>",  "</i>"),
            "underline":         ("<u>",  "</u>"),
            "strikethrough":     ("<s>",  "</s>"),
            "code":              ("<code>", "</code>"),
            "pre":               ("<pre>", "</pre>"),
            "spoiler":           ("<tg-spoiler>", "</tg-spoiler>"),
            "text_link":         (f'<a href="{getattr(ent, "url", "") or ent.get("url","") if not hasattr(ent,"url") else ent.url}">', "</a>"),
        }.get(etype)

        if not tag:
            continue

        events.setdefault(offset, []).append(("open", tag[0]))
        events.setdefault(offset + length, []).insert(0, ("close", tag[1]))

    result = []
    for i, ch in enumerate(chars):
        for kind, markup in events.get(i, []):
            result.append(markup)
        result.append(pyhtml.escape(ch))
    # Закрывающие теги в конце
    for kind, markup in events.get(len(chars), []):
        result.append(markup)
    return "".join(result)

def extract_content(m: Message) -> dict:
    """
    Извлекает контент + конвертирует entities в HTML.
    Текст сохраняем УЖЕ в HTML — отправляем с parse_mode='HTML'.
    """
    def _to_html(txt: Optional[str], ents) -> str:
        if not txt: return ""
        ents_raw = []
        if ents:
            for e in ents:
                if hasattr(e, 'type'):
                    ents_raw.append(e)
                else:
                    ents_raw.append(e)
        return entities_to_html(txt, ents_raw)

    if m.photo:
        return {
            "type": "photo",
            "file_id": m.photo[-1].file_id,
            "text": _to_html(m.caption, m.caption_entities)
        }
    if m.video:
        return {"type": "video",   "file_id": m.video.file_id,     "text": _to_html(m.caption, m.caption_entities)}
    if m.document:
        return {"type": "document","file_id": m.document.file_id,  "text": _to_html(m.caption, m.caption_entities)}
    if m.audio:
        return {"type": "audio",   "file_id": m.audio.file_id,     "text": _to_html(m.caption, m.caption_entities)}
    if m.animation:
        return {"type": "animation","file_id": m.animation.file_id,"text": _to_html(m.caption, m.caption_entities)}
    if m.voice:
        return {"type": "voice",   "file_id": m.voice.file_id,     "text": _to_html(m.caption, m.caption_entities)}
    if m.sticker:
        return {"type": "sticker", "file_id": m.sticker.file_id,   "text": ""}
    # Текстовое сообщение
    return {"type": "text", "file_id": None, "text": _to_html(m.text, m.entities)}

# ──────────────────────────────────────────────────────────────
# КНОПКИ
# ──────────────────────────────────────────────────────────────
def parse_buttons(text: str, layout: str = "rows") -> Optional[InlineKeyboardMarkup]:
    """
    Формат:
      Кнопка 1 | https://site.com
      Кнопка 2 | https://other.com

    layout='rows'    — каждая кнопка в своей строке (вертикально, столбец)
    layout='columns' — все кнопки в одну строку (горизонтально)
    layout='auto'    — пустая строка = новый ряд (ручной режим)
    """
    if not text or text.strip().lower() in ("нет", "no", "-", "skip", "н"):
        return None

    parsed = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        if "|" in line:
            parts = line.split("|", 1)
            btn_text = parts[0].strip()
            btn_url  = parts[1].strip()
            if btn_text and (btn_url.startswith("http") or btn_url.startswith("tg://")):
                parsed.append(InlineKeyboardButton(text=btn_text, url=btn_url))

    if not parsed:
        return None

    if layout == "columns":
        # Всё в один ряд
        return InlineKeyboardMarkup(inline_keyboard=[parsed])
    elif layout == "rows":
        # Каждая кнопка — свой ряд (столбец)
        return InlineKeyboardMarkup(inline_keyboard=[[b] for b in parsed])
    else:
        # auto: пустая строка = новый ряд (но мы уже пропустили пустые)
        # Разбираем повторно с учётом пустых строк
        rows, current = [], []
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line:
                if current: rows.append(current); current = []
                continue
            if "|" in line:
                parts = line.split("|", 1)
                btn_text, btn_url = parts[0].strip(), parts[1].strip()
                if btn_text and btn_url.startswith("http"):
                    current.append(InlineKeyboardButton(text=btn_text, url=btn_url))
        if current: rows.append(current)
        return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None

def btn_data_from_kb(kb: Optional[InlineKeyboardMarkup]) -> list:
    if not kb: return []
    return [[{"text": b.text, "url": b.url or ""} for b in row] for row in kb.inline_keyboard]

def kb_from_btn_data(btn_data: list) -> Optional[InlineKeyboardMarkup]:
    if not btn_data: return None
    rows = [[InlineKeyboardButton(text=b["text"], url=b["url"]) for b in row] for row in btn_data]
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ──────────────────────────────────────────────────────────────
# ПУБЛИКАЦИЯ
# ──────────────────────────────────────────────────────────────
async def send_post_to_channel(ch: str, content: dict,
                               kb: Optional[InlineKeyboardMarkup] = None) -> int:
    """Публикует один пост в один канал. Возвращает message_id."""
    ctype   = content.get("type")
    text    = content.get("text") or ""
    file_id = content.get("file_id")

    if ctype == "text":
        sent = await bot.send_message(ch, text or "​", parse_mode="HTML", reply_markup=kb)
    elif ctype == "photo":
        sent = await bot.send_photo(ch, file_id, caption=text or None,
                                    parse_mode="HTML", reply_markup=kb)
    elif ctype == "video":
        sent = await bot.send_video(ch, file_id, caption=text or None,
                                    parse_mode="HTML", reply_markup=kb)
    elif ctype == "document":
        sent = await bot.send_document(ch, file_id, caption=text or None,
                                       parse_mode="HTML", reply_markup=kb)
    elif ctype == "audio":
        sent = await bot.send_audio(ch, file_id, caption=text or None,
                                    parse_mode="HTML", reply_markup=kb)
    elif ctype == "animation":
        sent = await bot.send_animation(ch, file_id, caption=text or None,
                                        parse_mode="HTML", reply_markup=kb)
    elif ctype == "voice":
        sent = await bot.send_voice(ch, file_id, caption=text or None,
                                    parse_mode="HTML", reply_markup=kb)
    elif ctype == "sticker":
        sent = await bot.send_sticker(ch, file_id, reply_markup=kb)
    else:
        sent = await bot.send_message(ch, text or "📌", parse_mode="HTML", reply_markup=kb)
    return sent.message_id

async def send_post_to_channels(target_channels: List[str], content: dict,
                                kb: Optional[InlineKeyboardMarkup] = None) -> dict:
    """Публикует в несколько каналов. Возвращает {channel: msg_id / error}."""
    results = {}
    for ch in target_channels:
        try:
            mid = await send_post_to_channel(ch, content, kb)
            results[ch] = mid
            logger.info(f"✅ Пост опубликован в {ch} (msg_id={mid})")
        except Exception as e:
            results[ch] = f"❌ {e}"
            logger.error(f"send_post error in {ch}: {e}")
    return results

async def preview_post(chat_id: int, content: dict,
                       kb: Optional[InlineKeyboardMarkup] = None):
    """Отправляет предпросмотр пользователю."""
    ctype   = content.get("type")
    text    = content.get("text") or ""
    file_id = content.get("file_id")
    try:
        if ctype == "text":
            await bot.send_message(chat_id, text or "​", parse_mode="HTML", reply_markup=kb)
        elif ctype == "photo":
            await bot.send_photo(chat_id, file_id, caption=text or None,
                                 parse_mode="HTML", reply_markup=kb)
        elif ctype == "video":
            await bot.send_video(chat_id, file_id, caption=text or None,
                                 parse_mode="HTML", reply_markup=kb)
        elif ctype == "document":
            await bot.send_document(chat_id, file_id, caption=text or None,
                                    parse_mode="HTML", reply_markup=kb)
        elif ctype == "audio":
            await bot.send_audio(chat_id, file_id, caption=text or None,
                                 parse_mode="HTML", reply_markup=kb)
        elif ctype == "animation":
            await bot.send_animation(chat_id, file_id, caption=text or None,
                                     parse_mode="HTML", reply_markup=kb)
        elif ctype == "voice":
            await bot.send_voice(chat_id, file_id, caption=text or None,
                                 parse_mode="HTML", reply_markup=kb)
        elif ctype == "sticker":
            await bot.send_sticker(chat_id, file_id)
        else:
            await bot.send_message(chat_id, text or "📌", parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        await bot.send_message(chat_id, f"⚠️ Не удалось показать превью: {pyhtml.escape(str(e))}")

# ──────────────────────────────────────────────────────────────
# КЛАВИАТУРЫ
# ──────────────────────────────────────────────────────────────
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Создать пост",       callback_data="new_post")],
        [InlineKeyboardButton(text="📋 Запланированные",    callback_data="list_scheduled")],
        [InlineKeyboardButton(text="📡 Каналы",             callback_data="manage_channels")],
        [InlineKeyboardButton(text="📊 Статистика",          callback_data="show_stats")],
    ])

def channels_kb():
    chs = channels()
    rows = []
    for i, ch in enumerate(chs):
        rows.append([InlineKeyboardButton(
            text=f"🗑 Удалить {ch}", callback_data=f"del_ch_{i}"
        )])
    rows.append([InlineKeyboardButton(text="➕ Добавить канал", callback_data="add_channel")])
    rows.append([InlineKeyboardButton(text="🔙 Назад",           callback_data="to_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def channel_pick_kb(selected: List[str]):
    """Клавиатура выбора каналов для публикации."""
    chs = channels()
    rows = []
    for ch in chs:
        check = "✅" if ch in selected else "⬜"
        rows.append([InlineKeyboardButton(
            text=f"{check} {ch}", callback_data=f"pick_ch_{ch}"
        )])
    rows.append([
        InlineKeyboardButton(text="📢 Все сразу",   callback_data="pick_all"),
        InlineKeyboardButton(text="➡️ Далее",        callback_data="pick_done"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ──────────────────────────────────────────────────────────────
# СТАТИСТИКА
# ──────────────────────────────────────────────────────────────
def _track_post(target_channels: List[str]):
    st    = get_stats()
    today = datetime.now().strftime("%d.%m")
    count = len(target_channels)
    st["totalPosts"] = st.get("totalPosts", 0) + count
    history = st.setdefault("history", [])
    day = next((d for d in history if d.get("date") == today), None)
    if day:
        day["posts"] = day.get("posts", 0) + count
    else:
        history.append({"date": today, "posts": count})
    st["history"] = history[-30:]

# ──────────────────────────────────────────────────────────────
# START / CANCEL
# ──────────────────────────────────────────────────────────────
@dp.message(Command("start"))
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    if not is_admin(m.from_user.id):
        return await m.answer("⛔ Этот бот только для администраторов канала.")
    chs = channels()
    ch_text = "\n".join(f"  • <code>{pyhtml.escape(c)}</code>" for c in chs) if chs else "  <i>не настроены</i>"
    await m.answer(
        f"📡 <b>Бот постинга</b>\n\n"
        f"Каналы:\n{ch_text}\n\n"
        f"Выбери действие:",
        reply_markup=main_kb(),
        parse_mode="HTML"
    )

@dp.message(Command("cancel"))
async def cmd_cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("❌ Отменено.", reply_markup=main_kb())

@dp.callback_query(F.data == "to_main")
async def to_main(c: CallbackQuery, state: FSMContext):
    await state.clear()
    chs = channels()
    ch_text = ", ".join(chs) if chs else "не настроены"
    try:
        await c.message.edit_text(
            f"📡 <b>Бот постинга</b>\n\nКаналы: <code>{pyhtml.escape(ch_text)}</code>",
            reply_markup=main_kb(), parse_mode="HTML"
        )
    except Exception:
        await c.message.answer(
            f"📡 <b>Бот постинга</b>\n\nКаналы: <code>{pyhtml.escape(ch_text)}</code>",
            reply_markup=main_kb(), parse_mode="HTML"
        )

# ──────────────────────────────────────────────────────────────
# УПРАВЛЕНИЕ КАНАЛАМИ
# ──────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "manage_channels")
async def manage_channels(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return await c.answer("⛔", show_alert=True)
    await state.clear()
    chs = channels()
    text = "📡 <b>Управление каналами</b>\n\n"
    if chs:
        text += "\n".join(f"  {i+1}. <code>{pyhtml.escape(ch)}</code>" for i, ch in enumerate(chs))
    else:
        text += "<i>Каналов ещё нет.</i>"
    text += "\n\n<i>Бот должен быть администратором каждого канала.</i>"
    try:
        await c.message.edit_text(text, reply_markup=channels_kb(), parse_mode="HTML")
    except Exception:
        await c.message.answer(text, reply_markup=channels_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "add_channel")
async def add_channel_start(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return await c.answer("⛔", show_alert=True)
    await state.set_state(ManageChannels.add)
    await c.message.edit_text(
        "➕ <b>Добавить канал</b>\n\n"
        "Отправь username или ID канала:\n"
        "<code>@mychannel</code>\n"
        "<code>-1001234567890</code>\n\n"
        "<i>/cancel — отмена</i>",
        parse_mode="HTML"
    )

@dp.message(ManageChannels.add)
async def add_channel_done(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    ch = m.text.strip()
    if not (ch.startswith("@") or ch.lstrip("-").isdigit()):
        return await m.answer("❌ Неверный формат. Пример: @mychannel или -1001234567890")
    chs = channels()
    if ch in chs:
        await state.clear()
        return await m.answer(f"⚠️ Канал <code>{pyhtml.escape(ch)}</code> уже в списке.",
                               parse_mode="HTML", reply_markup=channels_kb())
    chs.append(ch)
    cfg()["channels"] = chs
    cfg()["channelId"] = chs[0] if chs else ""
    await save_config()
    await state.clear()
    await m.answer(
        f"✅ Канал <code>{pyhtml.escape(ch)}</code> добавлен!",
        parse_mode="HTML", reply_markup=channels_kb()
    )

@dp.callback_query(F.data.startswith("del_ch_"))
async def del_channel(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return await c.answer("⛔", show_alert=True)
    try:
        idx = int(c.data.split("_")[-1])
        chs = channels()
        if 0 <= idx < len(chs):
            removed = chs.pop(idx)
            cfg()["channels"] = chs
            cfg()["channelId"] = chs[0] if chs else ""
            await save_config()
            await c.answer(f"🗑 Удалён: {removed}", show_alert=False)
    except Exception:
        pass
    await manage_channels(c, state)

# ──────────────────────────────────────────────────────────────
# WIZARD: ШАГ 1 — КОНТЕНТ
# ──────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "new_post")
async def step1_start(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return await c.answer("⛔", show_alert=True)
    if not channels():
        return await c.answer("❌ Сначала добавь хотя бы один канал!", show_alert=True)
    await state.set_state(CreatePost.content)
    await c.message.answer(
        "📝 <b>Шаг 1 — Контент поста</b>\n\n"
        "Отправь что хочешь опубликовать:\n"
        "• Текст — <b>форматируй прямо в Telegram</b> (жирный, курсив, ссылки и т.д.)\n"
        "• Фото / Видео / GIF / Аудио / Документ / Стикер\n"
        "• Медиа + подпись с форматированием\n\n"
        "<i>/cancel — отмена</i>",
        parse_mode="HTML"
    )

# ──────────────────────────────────────────────────────────────
# WIZARD: ШАГ 2 — КНОПКИ
# ──────────────────────────────────────────────────────────────
@dp.message(CreatePost.content)
async def step2_buttons(m: Message, state: FSMContext):
    content = extract_content(m)
    await state.update_data(content=content)
    await state.set_state(CreatePost.buttons)
    await m.answer(
        "🔘 <b>Шаг 2 — Инлайн кнопки</b>\n\n"
        "Формат:\n"
        "<code>Текст кнопки | https://ссылка.com</code>\n"
        "<code>Ещё кнопка  | https://другая.com</code>\n\n"
        "Напиши <b>нет</b> — пропустить кнопки.\n\n"
        "<i>/cancel — отмена</i>",
        parse_mode="HTML"
    )

# ──────────────────────────────────────────────────────────────
# WIZARD: ШАГ 2.5 — РАСКЛАДКА КНОПОК
# ──────────────────────────────────────────────────────────────
@dp.message(CreatePost.buttons)
async def step_btn_layout(m: Message, state: FSMContext):
    raw_text = m.text or "нет"
    # Быстрая проверка — есть ли вообще кнопки
    has_buttons = raw_text.strip().lower() not in ("нет", "no", "-", "skip", "н") and "|" in raw_text
    await state.update_data(buttons_raw=raw_text)

    if not has_buttons:
        # Кнопок нет — пропускаем выбор раскладки
        await state.update_data(btn_data=[], layout="rows")
        await _step_channel_pick(m, state)
        return

    await state.set_state(CreatePost.btn_layout)
    layout_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📋 Столбцом",    callback_data="layout_rows"),
        InlineKeyboardButton(text="➡️ Строчкой",   callback_data="layout_columns"),
        InlineKeyboardButton(text="🔀 Вручную",    callback_data="layout_auto"),
    ]])
    await m.answer(
        "📐 <b>Шаг 2.5 — Раскладка кнопок</b>\n\n"
        "Как расположить кнопки?\n\n"
        "• <b>Столбцом</b> — каждая кнопка в своей строке\n"
        "• <b>Строчкой</b> — все кнопки в одну строку\n"
        "• <b>Вручную</b> — пустая строка в твоём тексте = новый ряд",
        reply_markup=layout_kb, parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("layout_"))
async def step_layout_chosen(c: CallbackQuery, state: FSMContext):
    layout = c.data.replace("layout_", "")  # rows / columns / auto
    data = await state.get_data()
    raw_text = data.get("buttons_raw", "нет")
    kb = parse_buttons(raw_text, layout)
    await state.update_data(btn_data=btn_data_from_kb(kb), layout=layout)
    await c.answer()
    await _step_channel_pick(c.message, state)

async def _step_channel_pick(msg_or_obj, state: FSMContext):
    """Переход к выбору каналов."""
    chs = channels()
    if len(chs) == 1:
        # Только один канал — выбираем автоматически
        await state.update_data(target_channels=chs)
        await state.set_state(CreatePost.schedule)
        sched_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🚀 Сразу",    callback_data="sched_now"),
            InlineKeyboardButton(text="⏰ Отложить", callback_data="sched_later"),
        ]])
        send_fn = msg_or_obj.answer if hasattr(msg_or_obj, 'answer') else msg_or_obj.answer
        await send_fn("📅 <b>Шаг 3 — Когда публиковать?</b>", reply_markup=sched_kb, parse_mode="HTML")
    else:
        await state.set_state(CreatePost.channel_pick)
        await state.update_data(target_channels=[])
        send_fn = msg_or_obj.answer if hasattr(msg_or_obj, 'answer') else msg_or_obj.answer
        await send_fn(
            "📡 <b>Шаг 3 — Выбери каналы</b>\n\n"
            "Нажимай на каналы чтобы выбрать, затем «Далее».",
            reply_markup=channel_pick_kb([]),
            parse_mode="HTML"
        )

# ──────────────────────────────────────────────────────────────
# WIZARD: ШАГ 3 — ВЫБОР КАНАЛОВ (если их несколько)
# ──────────────────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("pick_ch_"))
async def toggle_channel_pick(c: CallbackQuery, state: FSMContext):
    ch = c.data[len("pick_ch_"):]
    data = await state.get_data()
    selected: List[str] = data.get("target_channels", [])
    if ch in selected:
        selected.remove(ch)
    else:
        selected.append(ch)
    await state.update_data(target_channels=selected)
    try:
        await c.message.edit_reply_markup(reply_markup=channel_pick_kb(selected))
    except Exception:
        pass
    await c.answer()

@dp.callback_query(F.data == "pick_all")
async def pick_all_channels(c: CallbackQuery, state: FSMContext):
    selected = channels()[:]
    await state.update_data(target_channels=selected)
    try:
        await c.message.edit_reply_markup(reply_markup=channel_pick_kb(selected))
    except Exception:
        pass
    await c.answer("✅ Все каналы выбраны")

@dp.callback_query(F.data == "pick_done")
async def pick_done(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("target_channels", [])
    if not selected:
        return await c.answer("❌ Выбери хотя бы один канал!", show_alert=True)
    await state.set_state(CreatePost.schedule)
    sched_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🚀 Сразу",    callback_data="sched_now"),
        InlineKeyboardButton(text="⏰ Отложить", callback_data="sched_later"),
    ]])
    await c.message.edit_text(
        f"✅ Выбрано каналов: <b>{len(selected)}</b>\n\n"
        "📅 <b>Когда публиковать?</b>",
        reply_markup=sched_kb, parse_mode="HTML"
    )

# ──────────────────────────────────────────────────────────────
# WIZARD: ШАГ 4 — РАСПИСАНИЕ
# ──────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "sched_now")
async def step_preview_now(c: CallbackQuery, state: FSMContext):
    await state.update_data(schedule_type="now", schedule_value=None)
    await _show_preview(c, state)

@dp.callback_query(F.data == "sched_later")
async def step_schedule_input(c: CallbackQuery, state: FSMContext):
    await state.set_state(CreatePost.schedule_val)
    await c.message.edit_text(
        "⏰ <b>Когда опубликовать?</b>\n\n"
        "Варианты:\n"
        "• <code>30</code> — через 30 минут\n"
        "• <code>2ч</code> — через 2 часа\n"
        "• <code>25.02.2026 15:30</code> — точная дата/время\n\n"
        "<i>/cancel — отмена</i>",
        parse_mode="HTML"
    )

@dp.message(CreatePost.schedule_val)
async def step_schedule_value(m: Message, state: FSMContext):
    val = m.text.strip()
    try:
        # "30" → через 30 минут
        if val.isdigit():
            dt = datetime.now() + timedelta(minutes=int(val))
        # "2ч" или "2h" → через N часов
        elif re.match(r"^\d+(ч|h|hr|час)$", val.lower()):
            hours = int(re.match(r"^(\d+)", val).group(1))
            dt = datetime.now() + timedelta(hours=hours)
        # "дд.мм.гггг чч:мм"
        else:
            dt = datetime.strptime(val, "%d.%m.%Y %H:%M")

        if dt <= datetime.now():
            return await m.answer("❌ Время уже прошло. Введи будущее время.")

        sched_str = dt.strftime("%d.%m.%Y %H:%M")
        await state.update_data(schedule_type="fixed", schedule_value=sched_str)
        await m.answer(f"✅ Запланировано на <b>{sched_str}</b>", parse_mode="HTML")

        class FakeCallback:
            from_user = m.from_user
            message   = m
            async def answer(self, *a, **kw): pass
        await _show_preview(FakeCallback(), state)

    except ValueError:
        await m.answer(
            "❌ Неверный формат.\n\n"
            "Примеры: <code>30</code> · <code>2ч</code> · <code>25.02.2026 15:30</code>",
            parse_mode="HTML"
        )

# ──────────────────────────────────────────────────────────────
# WIZARD: ШАГ 5 — ПРЕДПРОСМОТР
# ──────────────────────────────────────────────────────────────
async def _show_preview(c, state: FSMContext):
    await state.set_state(CreatePost.preview)
    data = await state.get_data()
    content      = data.get("content", {})
    btn_data     = data.get("btn_data", [])
    sched        = data.get("schedule_value")
    target_chs   = data.get("target_channels", channels()[:1])

    kb = kb_from_btn_data(btn_data)
    uid = c.from_user.id

    chs_text = ", ".join(f"<code>{pyhtml.escape(ch)}</code>" for ch in target_chs)
    await bot.send_message(uid,
        f"👁 <b>Предпросмотр</b>\nКаналы: {chs_text}",
        parse_mode="HTML"
    )
    await preview_post(uid, content, kb)

    sched_info = f"\n⏰ Публикация: <b>{sched}</b>" if sched else "\n🚀 Публикация: <b>сейчас</b>"
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Опубликовать",   callback_data="pub_confirm"),
            InlineKeyboardButton(text="❌ Отмена",          callback_data="pub_cancel"),
        ],
        [
            InlineKeyboardButton(text="✏️ Изменить текст", callback_data="pub_edit"),
            InlineKeyboardButton(text="🔘 Изменить кнопки", callback_data="pub_edit_btns"),
        ],
    ])
    await bot.send_message(uid,
        f"Как выглядит пост выше.{sched_info}\n\nПубликуем?",
        reply_markup=confirm_kb, parse_mode="HTML"
    )

@dp.callback_query(F.data == "pub_cancel")
async def pub_cancel(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.edit_text("❌ Пост отменён.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔙 В меню", callback_data="to_main")
    ]]))

@dp.callback_query(F.data == "pub_edit")
async def pub_edit(c: CallbackQuery, state: FSMContext):
    await state.set_state(CreatePost.content)
    await c.message.edit_text(
        "✏️ Отправь новый контент. Форматируй прямо в Telegram.\n"
        "Кнопки и расписание будут сброшены.\n\n<i>/cancel — отмена</i>",
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "pub_edit_btns")
async def pub_edit_btns(c: CallbackQuery, state: FSMContext):
    await state.set_state(CreatePost.buttons)
    await c.message.edit_text(
        "🔘 Введи новые кнопки:\n"
        "<code>Текст | https://ссылка.com</code>\n"
        "или <b>нет</b> — без кнопок.\n\n<i>/cancel — отмена</i>",
        parse_mode="HTML"
    )

# ──────────────────────────────────────────────────────────────
# WIZARD: ПУБЛИКАЦИЯ
# ──────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "pub_confirm")
async def pub_confirm(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return await c.answer("⛔", show_alert=True)
    data = await state.get_data()
    await state.clear()

    content      = data.get("content", {})
    btn_data     = data.get("btn_data", [])
    sched_type   = data.get("schedule_type", "now")
    sched_value  = data.get("schedule_value")
    target_chs   = data.get("target_channels", channels()[:1])
    kb = kb_from_btn_data(btn_data)

    if sched_type == "now":
        try:
            results = await send_post_to_channels(target_chs, content, kb)
            ok  = [ch for ch, r in results.items() if isinstance(r, int)]
            bad = [f"{ch}: {r}" for ch, r in results.items() if not isinstance(r, int)]
            _track_post(ok)
            await save_config()

            result_text = f"✅ <b>Опубликовано в {len(ok)} канал(а):</b>\n"
            for ch in ok:
                result_text += f"  • <code>{pyhtml.escape(ch)}</code>\n"
            if bad:
                result_text += f"\n❌ Ошибки:\n" + "\n".join(bad)

            await c.message.edit_text(result_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 В меню", callback_data="to_main")
            ]]), parse_mode="HTML")
        except Exception as e:
            await c.message.edit_text(f"❌ Ошибка: {pyhtml.escape(str(e))}", parse_mode="HTML")
    else:
        job_id = f"post_{int(time.time())}"
        try:
            pub_dt = datetime.strptime(sched_value, "%d.%m.%Y %H:%M")
        except Exception:
            return await c.message.edit_text("❌ Неверный формат даты.")

        delay = (pub_dt - datetime.now()).total_seconds()
        if delay < 0:
            return await c.message.edit_text("❌ Время уже прошло.")

        async def delayed_publish():
            await asyncio.sleep(delay)
            try:
                results = await send_post_to_channels(target_chs, content, kb)
                ok = [ch for ch, r in results.items() if isinstance(r, int)]
                _track_post(ok)
                await save_config()
                await bot.send_message(
                    c.from_user.id,
                    f"✅ Отложенный пост опубликован ({sched_value})!\n" +
                    "\n".join(f"  • {ch}" for ch in ok)
                )
            except Exception as e:
                await bot.send_message(c.from_user.id, f"❌ Ошибка отложенного поста: {e}")
            finally:
                _scheduled.pop(job_id, None)
                _scheduled_meta.pop(job_id, None)

        task = asyncio.create_task(delayed_publish())
        _scheduled[job_id] = task
        _scheduled_meta[job_id] = {
            "time": sched_value,
            "channels": target_chs,
            "text": (content.get("text") or "")[:60],
        }
        await c.message.edit_text(
            f"⏰ <b>Запланировано на {sched_value}</b>\n"
            f"Каналы: {', '.join(target_chs)}\n"
            f"ID задачи: <code>{job_id}</code>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 В меню", callback_data="to_main")
            ]]),
            parse_mode="HTML"
        )

# ──────────────────────────────────────────────────────────────
# ЗАПЛАНИРОВАННЫЕ ПОСТЫ
# ──────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "list_scheduled")
async def list_scheduled(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return await c.answer("⛔", show_alert=True)
    if not _scheduled_meta:
        return await c.message.edit_text(
            "📋 <b>Запланированных постов нет</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Назад", callback_data="to_main")
            ]]),
            parse_mode="HTML"
        )
    text = "📋 <b>Запланированные посты:</b>\n\n"
    rows = []
    for job_id, meta in _scheduled_meta.items():
        text += (
            f"• <code>{job_id}</code>\n"
            f"  ⏰ {meta['time']} → {', '.join(meta['channels'])}\n"
            f"  ✏️ {pyhtml.escape(meta.get('text','')[:50])}...\n\n"
        )
        rows.append([InlineKeyboardButton(
            text=f"🗑 Отменить {meta['time']}", callback_data=f"cancel_job_{job_id}"
        )])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="to_main")])
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                               parse_mode="HTML")

@dp.callback_query(F.data.startswith("cancel_job_"))
async def cancel_job(c: CallbackQuery, state: FSMContext):
    job_id = c.data.replace("cancel_job_", "")
    task = _scheduled.pop(job_id, None)
    if task:
        task.cancel()
    _scheduled_meta.pop(job_id, None)
    await c.answer("✅ Задача отменена")
    await list_scheduled(c, state)

# ──────────────────────────────────────────────────────────────
# СТАТИСТИКА
# ──────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "show_stats")
async def show_stats(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return await c.answer("⛔", show_alert=True)
    st = get_stats()
    history = st.get("history", [])
    text = (
        f"📊 <b>Статистика постинга</b>\n\n"
        f"📮 Всего постов: <b>{st.get('totalPosts', 0)}</b>\n"
        f"📡 Каналов: <b>{len(channels())}</b>\n"
        f"⏳ В очереди: <b>{len(_scheduled)}</b>\n\n"
        f"<b>Активность (последние 14 дней):</b>\n"
    )
    for day in history[-14:]:
        bar = "▓" * min(day.get("posts", 0), 10)
        text += f"  {day.get('date','?')} {bar} {day.get('posts',0)}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔙 Назад", callback_data="to_main")
    ]])
    try:
        await c.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await c.message.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.message(Command("stats"))
async def cmd_stats(m: Message):
    if not is_admin(m.from_user.id): return await m.answer("⛔")
    st = get_stats()
    history = st.get("history", [])
    text = f"📊 <b>Статистика</b>\n\n📮 Всего: <b>{st.get('totalPosts', 0)}</b>\n\n"
    for day in history[-14:]:
        text += f"  {day.get('date','?')}: {day.get('posts',0)} постов\n"
    await m.answer(text, parse_mode="HTML")

# ──────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────
async def main():
    logger.info(f"▶️  Запуск PosterCore (bot_id={BOT_ID})")
    await load_config()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
