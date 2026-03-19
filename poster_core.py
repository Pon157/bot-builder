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
from db_adapter import DBAdapter, init_pg_pool
_db_adapter = DBAdapter(SB_URL, SB_KEY)

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
# ШАБЛОНЫ
# ──────────────────────────────────────────────────────────────
"""
Шаблон — это готовый текст поста с плейсхолдерами:
  {текст}  — сюда вставляется произвольный текст пользователя
  фото прикрепляется отдельно как медиа при публикации

Пример шаблона:
  🔥 АКЦИЯ ДНЯ

  {текст}

  👉 Успей до конца дня!
  📞 @manager

Структура в БД:
  {
    "id": int,
    "name": str,           # короткое название: «Акция», «Новость»
    "body": str,           # тело шаблона с плейсхолдером {текст}
    "buttons_raw": str,    # кнопки по умолчанию (можно оставить пустым)
    "btn_layout": str,     # rows / columns / auto
    "created_at": str,
  }
"""

def templates() -> list:
    return cfg().setdefault("templates", [])

def get_template(tid: int) -> Optional[dict]:
    return next((t for t in templates() if t["id"] == tid), None)

def next_template_id() -> int:
    ids = [t["id"] for t in templates()]
    return max(ids, default=0) + 1

def apply_template(tpl: dict, user_text: str, photo_id: Optional[str] = None) -> dict:
    """
    Подставляет {текст} в шаблон.
    Если передан photo_id — пост будет с фото (caption = заполненный шаблон).
    """
    body   = tpl.get("body", "")
    filled = body.replace("{текст}", user_text or "").strip()

    if photo_id:
        return {"type": "photo", "file_id": photo_id, "text": filled}
    return {"type": "text", "file_id": None, "text": filled}

def tpl_body_preview(body: str, max_len: int = 200) -> str:
    """Показывает тело шаблона с подсвеченным плейсхолдером."""
    preview = body[:max_len]
    if len(body) > max_len:
        preview += "..."
    escaped = pyhtml.escape(preview)
    escaped = escaped.replace("{текст}", "<b>{текст}</b>")
    return escaped

def templates_list_kb(show_none: bool = True):
    rows = []
    if show_none:
        rows.append([InlineKeyboardButton(text="🚫 Без шаблона", callback_data="tpl_none")])
    for t in templates():
        rows.append([InlineKeyboardButton(
            text=f"📄 {t['name']}", callback_data=f"tpl_pick_{t['id']}"
        )])
    rows.append([InlineKeyboardButton(text="➕ Создать шаблон", callback_data="tpl_create")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def templates_manage_kb():
    rows = []
    for t in templates():
        rows.append([InlineKeyboardButton(
            text=f"📄 {t['name']}", callback_data=f"tpl_view_{t['id']}"
        )])
    rows.append([InlineKeyboardButton(text="➕ Создать шаблон", callback_data="tpl_create")])
    rows.append([InlineKeyboardButton(text="🔙 Назад",           callback_data="to_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
class CreatePost(StatesGroup):
    template_pick = State()
    fill_text     = State()   # ввод {текст} для шаблона
    content      = State()
    buttons      = State()
    btn_layout   = State()
    channel_pick = State()
    schedule     = State()
    schedule_val = State()
    preview      = State()

class ManageChannels(StatesGroup):
    add = State()

class TemplateStates(StatesGroup):
    name        = State()   # название шаблона
    body        = State()   # тело с {текст}
    buttons_raw = State()   # кнопки по умолчанию
    btn_layout  = State()   # раскладка кнопок

class EditTemplateField(StatesGroup):
    value = State()

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
        [InlineKeyboardButton(text="📄 Шаблоны",            callback_data="manage_templates")],
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
# WIZARD: ШАГ 0 — ВЫБОР ШАБЛОНА
# ──────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "tpl_none")
async def tpl_none_chosen(c: CallbackQuery, state: FSMContext):
    await state.update_data(active_template=None, tpl_fill_text="", tpl_text_filled=False)
    await c.answer()
    await _go_to_content(c.message, state)

@dp.callback_query(F.data.startswith("tpl_pick_"), CreatePost.template_pick)
async def tpl_pick_chosen(c: CallbackQuery, state: FSMContext):
    try:
        tid = int(c.data.split("_")[2])
    except Exception:
        return await c.answer("Ошибка", show_alert=True)
    tpl = get_template(tid)
    if not tpl:
        return await c.answer("Шаблон не найден", show_alert=True)

    await state.update_data(active_template=tid, tpl_fill_text="", tpl_text_filled=False)
    await c.answer()

    body_has_text = "{текст}" in tpl.get("body", "")
    ph_str = "<b>{текст}</b>" if body_has_text else "<i>нет — шаблон фиксированный</i>"

    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Использовать", callback_data="tpl_confirm")],
        [InlineKeyboardButton(text="🔙 Выбрать другой", callback_data="tpl_back")],
    ])
    try:
        await c.message.edit_text(
            f"📄 <b>{pyhtml.escape(tpl['name'])}</b>\n\n"
            f"<b>Шаблон:</b>\n<code>{tpl_body_preview(tpl['body'])}</code>\n\n"
            f"Плейсхолдер: {ph_str}",
            reply_markup=confirm_kb, parse_mode="HTML"
        )
    except Exception:
        await c.message.answer(
            f"📄 <b>{pyhtml.escape(tpl['name'])}</b> выбран.",
            reply_markup=confirm_kb, parse_mode="HTML"
        )

@dp.callback_query(F.data == "tpl_confirm")
async def tpl_confirm(c: CallbackQuery, state: FSMContext):
    await c.answer()
    data = await state.get_data()
    tid  = data.get("active_template")
    tpl  = get_template(tid) if tid is not None else None
    if not tpl:
        await _go_to_content(c.message, state)
        return
    await _start_fill_template(c.message, state, tpl)

@dp.callback_query(F.data == "tpl_back")
async def tpl_back(c: CallbackQuery, state: FSMContext):
    await state.update_data(active_template=None, tpl_fill_text="", tpl_text_filled=False)
    await state.set_state(CreatePost.template_pick)
    try:
        await c.message.edit_text(
            "📄 <b>Выбери шаблон</b>",
            reply_markup=templates_list_kb(show_none=True), parse_mode="HTML"
        )
    except Exception:
        await c.message.answer(
            "📄 <b>Выбери шаблон</b>",
            reply_markup=templates_list_kb(show_none=True), parse_mode="HTML"
        )

async def _start_fill_template(msg, state: FSMContext, tpl: dict):
    """Если шаблон имеет {текст} — просим его ввести. Потом спрашиваем медиа."""
    body = tpl.get("body", "")
    if "{текст}" in body:
        await state.set_state(CreatePost.fill_text)
        await msg.answer(
            f"✏️ <b>Шаблон «{pyhtml.escape(tpl['name'])}»</b>\n\n"
            f"Введи текст для <b>{{текст}}</b>:\n\n"
            f"<i>Форматирование Telegram поддерживается</i>\n"
            f"<i>/cancel — отмена</i>",
            parse_mode="HTML"
        )
    else:
        # Нет {текст} — сразу к медиа
        await state.update_data(tpl_text_filled=True)
        await _ask_for_media(msg, state)

@dp.message(CreatePost.fill_text)
async def fill_template_text(m: Message, state: FSMContext):
    filled_text = entities_to_html(m.text or "", m.entities)
    await state.update_data(tpl_fill_text=filled_text, tpl_text_filled=True)
    await _ask_for_media(m, state)

async def _ask_for_media(msg, state: FSMContext):
    """Переходим к шагу content с пометкой что нужно применить шаблон."""
    await state.set_state(CreatePost.content)
    await msg.answer(
        "🖼 <b>Медиа (необязательно)</b>\n\n"
        "Прикрепи фото, видео, GIF или документ.\n\n"
        "Или отправь точку <code>.</code> — пост будет только текстовым.\n\n"
        "<i>/cancel — отмена</i>",
        parse_mode="HTML"
    )

async def _apply_template_and_go(msg, state: FSMContext, content: dict):
    """Подставляет {текст} в шаблон + прикрепляет медиа из content."""
    data      = await state.get_data()
    tid       = data.get("active_template")
    tpl       = get_template(tid) if tid is not None else None
    user_text = data.get("tpl_fill_text", "")

    if tpl:
        # Текст = шаблон с подставленным {текст}
        body   = tpl.get("body", "")
        filled_text = body.replace("{текст}", user_text).strip()

        # Если у пользователя есть медиа — используем его, текст = caption
        if content.get("type") not in (None, "text", "") and content.get("file_id"):
            filled_content = {
                "type":    content["type"],
                "file_id": content["file_id"],
                "text":    filled_text,
            }
        else:
            filled_content = {"type": "text", "file_id": None, "text": filled_text}
    else:
        filled_content = content

    await state.update_data(content=filled_content)

    # Подсказка про кнопки шаблона
    tpl_btns_hint = ""
    if tpl and tpl.get("buttons_raw"):
        tpl_btns_hint = (
            f"\n\n💡 <b>Кнопки из шаблона:</b>\n"
            f"<code>{pyhtml.escape(tpl['buttons_raw'])}</code>\n"
            f"Напиши <b>шаблон</b> — использовать их."
        )

    await state.set_state(CreatePost.buttons)
    await msg.answer(
        "🔘 <b>Инлайн кнопки</b>\n\n"
        "Формат: <code>Текст | https://ссылка.com</code>\n\n"
        "Напиши <b>нет</b> — без кнопок."
        + tpl_btns_hint +
        "\n\n<i>/cancel — отмена</i>",
        parse_mode="HTML"
    )

async def _go_to_content(msg, state: FSMContext):
    """Обычный путь без шаблона."""
    await state.set_state(CreatePost.content)
    await msg.answer(
        "📝 <b>Контент поста</b>\n\n"
        "Отправь что хочешь опубликовать:\n"
        "• Текст — <b>форматируй прямо в Telegram</b>\n"
        "• Фото / Видео / GIF / Аудио / Документ / Стикер\n"
        "• Медиа + подпись\n\n"
        "<i>/cancel — отмена</i>",
        parse_mode="HTML"
    )

# ──────────────────────────────────────────────────────────────
# WIZARD: ШАГ 1 — КОНТЕНТ (без шаблона)
# ──────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "new_post")
async def step1_start(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return await c.answer("⛔", show_alert=True)
    if not channels():
        return await c.answer("❌ Сначала добавь хотя бы один канал!", show_alert=True)

    await state.update_data(active_template=None, tpl_fill_text="", tpl_text_filled=False)

    if not templates():
        # Шаблонов нет — сразу к контенту
        await _go_to_content(c.message, state)
        return

    await state.set_state(CreatePost.template_pick)
    await c.message.answer(
        "📄 <b>Выбери шаблон</b>\n\n"
        "Или нажми «Без шаблона» — создать обычный пост.\n\n"
        "<i>/cancel — отмена</i>",
        reply_markup=templates_list_kb(show_none=True), parse_mode="HTML"
    )

# ──────────────────────────────────────────────────────────────
# WIZARD: ШАГ 2 — КОНТЕНТ
# ──────────────────────────────────────────────────────────────
@dp.message(CreatePost.content)
async def step2_buttons(m: Message, state: FSMContext):
    content = extract_content(m)
    data    = await state.get_data()

    # Шаблонный путь — применяем шаблон
    if data.get("tpl_text_filled"):
        # Точка/пустышка = только текст, без медиа
        if content.get("type") == "text" and (content.get("text") or "").strip() in (".", "-", ""):
            content = {"type": "text", "file_id": None, "text": ""}
        await _apply_template_and_go(m, state, content)
        return

    # Обычный путь
    await state.update_data(content=content)
    await state.set_state(CreatePost.buttons)
    await m.answer(
        "🔘 <b>Инлайн кнопки</b>\n\n"
        "Формат:\n"
        "<code>Текст кнопки | https://ссылка.com</code>\n\n"
        "Напиши <b>нет</b> — без кнопок.\n\n"
        "<i>/cancel — отмена</i>",
        parse_mode="HTML"
    )

# ──────────────────────────────────────────────────────────────
# WIZARD: ШАГ 2.5 — РАСКЛАДКА КНОПОК
# ──────────────────────────────────────────────────────────────
@dp.message(CreatePost.buttons)
async def step_btn_layout(m: Message, state: FSMContext):
    raw_text = m.text or "нет"
    data = await state.get_data()

    # "шаблон" — использовать кнопки из шаблона
    if raw_text.strip().lower() in ("шаблон", "template"):
        tid = data.get("active_template")
        if tid is not None:
            tpl = get_template(tid)
            if tpl and tpl.get("buttons_raw"):
                raw_text = tpl["buttons_raw"]

    has_buttons = raw_text.strip().lower() not in ("нет", "no", "-", "skip", "н") and "|" in raw_text
    await state.update_data(buttons_raw=raw_text)

    if not has_buttons:
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
        "📐 <b>Раскладка кнопок</b>\n\n"
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
# УПРАВЛЕНИЕ ШАБЛОНАМИ
# ──────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "manage_templates")
async def manage_templates(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return await c.answer("⛔", show_alert=True)
    await state.clear()
    tpls = templates()
    if tpls:
        text = f"📄 <b>Шаблоны постов</b> ({len(tpls)} шт.)\n\nВыбери шаблон или создай новый:"
    else:
        text = (
            "📄 <b>Шаблоны постов</b>\n\n"
            "<i>Шаблонов пока нет.</i>\n\n"
            "Создай шаблон — напиши оформление поста с плейсхолдером <b>{текст}</b>.\n\n"
            "Пример:\n<code>🔥 Акция!\n\n{текст}\n\n👉 @channel</code>\n\n"
            "Фото и видео прикрепляются отдельно при каждой публикации."
        )
    try:
        await c.message.edit_text(text, reply_markup=templates_manage_kb(), parse_mode="HTML")
    except Exception:
        await c.message.answer(text, reply_markup=templates_manage_kb(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("tpl_view_"))
async def tpl_view(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return await c.answer("⛔", show_alert=True)
    try:
        tid = int(c.data.split("_")[2])
    except Exception:
        return await c.answer("Ошибка")
    tpl = get_template(tid)
    if not tpl: return await c.answer("Шаблон не найден", show_alert=True)

    body_has_text = "{текст}" in tpl.get("body", "")
    ph_info = ["{текст} ✅"] if body_has_text else ["нет плейсхолдеров"]

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить шаблон",  callback_data=f"tpl_edit_body_{tid}"),
         InlineKeyboardButton(text="✏️ Переименовать",    callback_data=f"tpl_edit_name_{tid}")],
        [InlineKeyboardButton(text="🔘 Изменить кнопки",  callback_data=f"tpl_edit_buttons_{tid}")],
        [InlineKeyboardButton(text="🗑 Удалить",          callback_data=f"tpl_delete_{tid}"),
         InlineKeyboardButton(text="🔙 К списку",         callback_data="manage_templates")],
    ])
    try:
        await c.message.edit_text(
            f"📄 <b>{pyhtml.escape(tpl['name'])}</b>\n\n"
            f"<b>Тело шаблона:</b>\n<code>{tpl_body_preview(tpl['body'])}</code>\n\n"
            f"<b>Плейсхолдеры:</b> {', '.join(ph_info)}\n"
            f"<b>Кнопки:</b> {pyhtml.escape(tpl.get('buttons_raw','')) or '<i>нет</i>'}\n\n"
            f"📅 Создан: {tpl.get('created_at', '?')}",
            reply_markup=kb, parse_mode="HTML"
        )
    except Exception:
        await c.message.answer(
            f"📄 <b>{pyhtml.escape(tpl['name'])}</b>",
            reply_markup=kb, parse_mode="HTML"
        )

# ── Создание шаблона (2 шага: название → тело) ──
@dp.callback_query(F.data == "tpl_create")
async def tpl_create_start(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return await c.answer("⛔", show_alert=True)
    await state.set_state(TemplateStates.name)
    await c.message.answer(
        "📄 <b>Создание шаблона — Шаг 1/3</b>\n\n"
        "Введи <b>название</b> шаблона:\n"
        "<i>Например: «Новости», «Акция», «Анонс»</i>\n\n"
        "<i>/cancel — отмена</i>",
        parse_mode="HTML"
    )

@dp.message(TemplateStates.name)
async def tpl_step_name(m: Message, state: FSMContext):
    name = (m.text or "").strip()
    if not name or len(name) > 64:
        return await m.answer("❌ Название: от 1 до 64 символов.")
    await state.update_data(tpl_name=name)
    await state.set_state(TemplateStates.body)
    await m.answer(
        f"✅ Название: <b>{pyhtml.escape(name)}</b>\n\n"
        "📄 <b>Шаг 2/3 — Тело шаблона</b>\n\n"
        "Напиши текст поста как он будет выглядеть.\n"
        "Используй плейсхолдер <code>{текст}</code> — сюда будет вставляться нужный текст каждый раз.\n\n"
        "<b>Примеры:</b>\n"
        "<code>🔥 АКЦИЯ!\n\n{текст}\n\n👉 Подробности у @manager</code>\n\n"
        "<code>📢 Новость дня:\n\n{текст}\n\n— Редакция</code>\n\n"
        "Фото/видео прикрепляются отдельно при публикации.\n"
        "HTML-теги поддерживаются: <code>&lt;b&gt;жирный&lt;/b&gt;</code>\n\n"
        "<i>/cancel — отмена</i>",
        parse_mode="HTML"
    )

@dp.message(TemplateStates.body)
async def tpl_step_body(m: Message, state: FSMContext):
    body = (m.text or "").strip()
    if not body:
        return await m.answer("❌ Шаблон не может быть пустым.")
    await state.update_data(tpl_body=body)
    await state.set_state(TemplateStates.buttons_raw)

    has_text = "{текст}" in body
    ph_str   = "<b>{текст}</b>" if has_text else "<i>нет плейсхолдеров — шаблон публикуется как есть</i>"

    await m.answer(
        f"✅ Шаблон принят!\n"
        f"Плейсхолдеры: {ph_str}\n\n"
        "🔘 <b>Шаг 3/3 — Кнопки по умолчанию</b>\n\n"
        "Эти кнопки будут предложены при каждой публикации с этим шаблоном.\n\n"
        "Формат:\n"
        "<code>Сайт | https://site.com</code>\n\n"
        "Напиши <b>нет</b> — без кнопок.",
        parse_mode="HTML"
    )

@dp.message(TemplateStates.buttons_raw)
async def tpl_step_buttons(m: Message, state: FSMContext):
    raw = (m.text or "").strip()
    if raw.lower() in ("нет", "no", "-"):
        raw = ""
    has_btns = bool(raw and "|" in raw)
    await state.update_data(tpl_buttons=raw)

    if not has_btns:
        await _tpl_save(m, state, layout="rows")
        return

    await state.set_state(TemplateStates.btn_layout)
    layout_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📋 Столбцом",  callback_data="tpl_layout_rows"),
        InlineKeyboardButton(text="➡️ Строчкой", callback_data="tpl_layout_columns"),
    ]])
    await m.answer(
        "📐 <b>Раскладка кнопок шаблона</b>",
        reply_markup=layout_kb, parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("tpl_layout_"))
async def tpl_layout_chosen(c: CallbackQuery, state: FSMContext):
    layout = c.data.replace("tpl_layout_", "")
    await c.answer()
    await _tpl_save(c.message, state, layout=layout)

async def _tpl_save(msg, state: FSMContext, layout: str = "rows"):
    data = await state.get_data()
    await state.clear()
    tpl = {
        "id":          next_template_id(),
        "name":        data.get("tpl_name", "Шаблон"),
        "body":        data.get("tpl_body", ""),
        "buttons_raw": data.get("tpl_buttons", ""),
        "btn_layout":  layout,
        "created_at":  datetime.now().strftime("%d.%m.%Y %H:%M"),
    }
    templates().append(tpl)
    await save_config()

    has_text = "{текст}" in tpl["body"]
    ph_str   = "{текст}" if has_text else "нет"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 К шаблонам", callback_data="manage_templates")],
        [InlineKeyboardButton(text="🔙 В меню",     callback_data="to_main")],
    ])
    await msg.answer(
        f"✅ <b>Шаблон «{pyhtml.escape(tpl['name'])}» создан!</b>\n\n"
        f"Плейсхолдеры: {ph_str}\n"
        f"Кнопки: {'есть' if tpl['buttons_raw'] else 'нет'}",
        reply_markup=kb, parse_mode="HTML"
    )

# ── Редактирование полей шаблона ──
@dp.callback_query(F.data.startswith("tpl_edit_"))
async def tpl_edit_field(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return await c.answer("⛔", show_alert=True)
    parts = c.data.split("_")
    field = parts[2]   # body / name / buttons
    try:
        tid = int(parts[3])
    except Exception:
        return await c.answer("Ошибка")
    tpl = get_template(tid)
    if not tpl: return await c.answer("Шаблон не найден", show_alert=True)

    await state.set_state(EditTemplateField.value)
    await state.update_data(edit_tpl_id=tid, edit_tpl_field=field)

    prompts = {
        "body":    (
            "✏️ Введи новый текст шаблона.\n"
            "Используй <code>{текст}</code> как плейсхолдер:"
        ),
        "name":    "✏️ Введи новое название шаблона:",
        "buttons": "🔘 Введи новые кнопки (<code>Текст | URL</code>) или «нет»:",
    }
    await c.message.answer(prompts.get(field, "Введи новое значение:"), parse_mode="HTML")

@dp.message(EditTemplateField.value)
async def tpl_edit_apply(m: Message, state: FSMContext):
    data  = await state.get_data()
    tid   = data["edit_tpl_id"]
    field = data["edit_tpl_field"]
    await state.clear()

    tpl = get_template(tid)
    if not tpl:
        return await m.answer("❌ Шаблон не найден.")

    val = (m.text or "").strip()
    if field == "name":
        if not val or len(val) > 64:
            return await m.answer("❌ Название от 1 до 64 символов.")
        tpl["name"] = val
    elif field == "body":
        if not val:
            return await m.answer("❌ Шаблон не может быть пустым.")
        tpl["body"] = val
    elif field == "buttons":
        tpl["buttons_raw"] = "" if val.lower() in ("нет", "no", "-") else val

    await save_config()
    await m.answer(
        f"✅ Шаблон <b>{pyhtml.escape(tpl['name'])}</b> обновлён!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📄 Открыть", callback_data=f"tpl_view_{tid}"),
            InlineKeyboardButton(text="📄 К списку", callback_data="manage_templates"),
        ]]),
        parse_mode="HTML"
    )

# ── Удаление шаблона ──
@dp.callback_query(F.data.startswith("tpl_delete_confirm_"))
async def tpl_delete_confirm(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return await c.answer("⛔", show_alert=True)
    try:
        tid = int(c.data.split("_")[3])
    except Exception:
        return await c.answer("Ошибка")
    tpl = get_template(tid)
    name = tpl["name"] if tpl else "?"
    cfg()["templates"] = [t for t in templates() if t["id"] != tid]
    await save_config()
    await c.answer(f"🗑 Шаблон «{name}» удалён", show_alert=True)
    await manage_templates(c, state)

@dp.callback_query(F.data.startswith("tpl_delete_"))
async def tpl_delete(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return await c.answer("⛔", show_alert=True)
    # Не обрабатываем tpl_delete_confirm_ здесь (у него свой хендлер выше)
    if "confirm" in c.data: return
    try:
        tid = int(c.data.split("_")[2])
    except Exception:
        return await c.answer("Ошибка")
    tpl = get_template(tid)
    if not tpl: return await c.answer("Шаблон не найден", show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🗑 Да, удалить",  callback_data=f"tpl_delete_confirm_{tid}"),
        InlineKeyboardButton(text="❌ Отмена",        callback_data=f"tpl_view_{tid}"),
    ]])
    try:
        await c.message.edit_text(
            f"🗑 Удалить <b>{pyhtml.escape(tpl['name'])}</b>?\n\nЭто нельзя отменить.",
            reply_markup=kb, parse_mode="HTML"
        )
    except Exception:
        await c.message.answer(
            f"🗑 Удалить <b>{pyhtml.escape(tpl['name'])}</b>?",
            reply_markup=kb, parse_mode="HTML"
        )

# ──────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────
async def main():
    await init_pg_pool()
    logger.info(f"▶️  Запуск PosterCore (bot_id={BOT_ID})")
    await load_config()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
