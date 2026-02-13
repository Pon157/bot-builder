"""
poster_core.py — Бот для постинга в Telegram-каналы.

Конфиг (хранится в колонке config JSONB в таблице bots):
{
  "channelId": "@mychannel",       // канал для публикации
  "adminIds": [123456789],         // кто может публиковать
  "stats": { "totalPosts": 0, "history": [] }
}

Публикация полностью через бота:
  /start → главное меню → "Создать пост" → wizard
  - текст/фото/видео/документ/аудио/стикер
  - кнопки (инлайн ссылки)
  - отложенная публикация (через N минут или в конкретное время)
  - предпросмотр перед отправкой
  - подтверждение (Опубликовать / Редактировать / Отмена)
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
from typing import Optional

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
    InputMediaPhoto, InputMediaVideo, InputMediaDocument, InputMediaAudio
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
import html as pyhtml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("PosterCore")

TOKEN  = os.getenv("BOT_TOKEN")
BOT_ID = os.getenv("BOT_ID")
SB_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SB_KEY = os.getenv("SUPABASE_KEY") or ""

if not TOKEN:
    logger.critical("❌ BOT_TOKEN не задан!")
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
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{SB_URL}/rest/v1/bots?id=eq.{BOT_ID}", headers=_sb_headers())
        if r.status_code == 200 and r.json():
            raw = r.json()[0].get("config") or {}
            _config = raw if isinstance(raw, dict) else json.loads(raw)
    return _config

async def save_config():
    async with httpx.AsyncClient(timeout=10) as c:
        await c.patch(
            f"{SB_URL}/rest/v1/bots?id=eq.{BOT_ID}",
            headers=_sb_headers(),
            json={"config": _config, "stats": _config.get("stats", {})}
        )

def cfg() -> dict:
    return _config

def admin_ids() -> list:
    return [int(x) for x in cfg().get("adminIds", []) if str(x).strip().lstrip("-").isdigit()]

def channel_id() -> str:
    return cfg().get("channelId", "")

def is_admin(uid: int) -> bool:
    return uid in admin_ids()

def get_stats() -> dict:
    return cfg().setdefault("stats", {"totalPosts": 0, "history": []})

# ──────────────────────────────────────────────────────────────
# FSM
# ──────────────────────────────────────────────────────────────
class CreatePost(StatesGroup):
    content      = State()   # Шаг 1: контент
    buttons      = State()   # Шаг 2: инлайн кнопки (опционально)
    schedule     = State()   # Шаг 3: отложить?
    schedule_val = State()   # Шаг 4: когда именно (если отложено)
    preview      = State()   # Шаг 5: предпросмотр + подтверждение

# Хранилище отложенных задач
_scheduled: dict = {}  # key: job_id, value: asyncio.Task

# ──────────────────────────────────────────────────────────────
# УТИЛИТЫ
# ──────────────────────────────────────────────────────────────
def parse_buttons(text: str) -> Optional[InlineKeyboardMarkup]:
    """
    Формат ввода:
      Кнопка 1 | https://site.com
      Кнопка 2 | https://other.com
    Пустая строка = новая строка кнопок.
    """
    if not text or text.strip().lower() in ("нет", "no", "-", "skip"):
        return None
    rows = []
    current_row = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            if current_row:
                rows.append(current_row)
                current_row = []
            continue
        if "|" in line:
            parts = line.split("|", 1)
            btn_text = parts[0].strip()
            btn_url  = parts[1].strip()
            if btn_text and btn_url.startswith("http"):
                current_row.append(InlineKeyboardButton(text=btn_text, url=btn_url))
    if current_row:
        rows.append(current_row)
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None

async def send_post(content: dict, kb: Optional[InlineKeyboardMarkup] = None) -> Optional[int]:
    """Публикует пост в канал. Возвращает message_id."""
    ch = channel_id()
    if not ch:
        raise ValueError("Канал не настроен (channelId в конфиге)")
    
    ctype   = content.get("type")
    text    = content.get("text") or ""
    file_id = content.get("file_id")
    entities= content.get("entities")

    try:
        if ctype == "text":
            sent = await bot.send_message(ch, text, parse_mode="HTML", reply_markup=kb)
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
            sent = await bot.send_message(ch, text or "📌 Пост", parse_mode="HTML", reply_markup=kb)
        return sent.message_id
    except Exception as e:
        logger.error(f"send_post error: {e}")
        raise

async def preview_post(chat_id: int, content: dict, kb: Optional[InlineKeyboardMarkup] = None):
    """Отправляет предпросмотр поста пользователю."""
    ctype   = content.get("type")
    text    = content.get("text") or ""
    file_id = content.get("file_id")
    try:
        if ctype == "text":
            await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb)
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
            await bot.send_message(chat_id, text or "📌 Пост", parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        await bot.send_message(chat_id, f"⚠️ Не удалось показать превью: {e}")

def extract_content(m: Message) -> dict:
    """Извлекает контент сообщения в универсальный dict."""
    if m.photo:
        return {"type": "photo",     "file_id": m.photo[-1].file_id, "text": m.caption or ""}
    if m.video:
        return {"type": "video",     "file_id": m.video.file_id,     "text": m.caption or ""}
    if m.document:
        return {"type": "document",  "file_id": m.document.file_id,  "text": m.caption or ""}
    if m.audio:
        return {"type": "audio",     "file_id": m.audio.file_id,     "text": m.caption or ""}
    if m.animation:
        return {"type": "animation", "file_id": m.animation.file_id, "text": m.caption or ""}
    if m.voice:
        return {"type": "voice",     "file_id": m.voice.file_id,     "text": m.caption or ""}
    if m.sticker:
        return {"type": "sticker",   "file_id": m.sticker.file_id,   "text": ""}
    return {"type": "text", "file_id": None, "text": m.text or ""}

def main_kb(uid: int):
    rows = [
        [InlineKeyboardButton(text="✏️ Создать пост", callback_data="new_post")],
        [InlineKeyboardButton(text="📊 Статистика",   callback_data="show_stats")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ──────────────────────────────────────────────────────────────
# СТАРТ
# ──────────────────────────────────────────────────────────────
@dp.message(Command("start"))
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    if not is_admin(m.from_user.id):
        return await m.answer("⛔ Этот бот только для администраторов канала.")
    ch = channel_id() or "(не настроен)"
    await m.answer(
        f"📡 <b>Бот постинга</b>\n\nКанал: <code>{pyhtml.escape(ch)}</code>\n\nВыбери действие:",
        reply_markup=main_kb(m.from_user.id),
        parse_mode="HTML"
    )

@dp.message(Command("cancel"))
async def cmd_cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("❌ Отменено.", reply_markup=main_kb(m.from_user.id))

# ──────────────────────────────────────────────────────────────
# СТАТИСТИКА
# ──────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "show_stats")
async def show_stats(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer("⛔", show_alert=True)
    st = get_stats()
    history = st.get("history", [])
    text = (
        f"📊 <b>Статистика постинга</b>\n\n"
        f"📮 Всего постов: <b>{st.get('totalPosts', 0)}</b>\n"
        f"📅 Последние {min(len(history), 7)} дней:\n"
    )
    for day in history[-7:]:
        text += f"  • {day.get('date', '?')}: {day.get('posts', 0)} постов\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔙 Назад", callback_data="to_main")
    ]])
    try:
        await c.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await c.message.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "to_main")
async def to_main(c: CallbackQuery, state: FSMContext):
    await state.clear()
    ch = channel_id() or "(не настроен)"
    kb = main_kb(c.from_user.id)
    try:
        await c.message.edit_text(
            f"📡 <b>Бот постинга</b>\n\nКанал: <code>{pyhtml.escape(ch)}</code>",
            reply_markup=kb, parse_mode="HTML"
        )
    except Exception:
        await c.message.answer(
            f"📡 <b>Бот постинга</b>\n\nКанал: <code>{pyhtml.escape(ch)}</code>",
            reply_markup=kb, parse_mode="HTML"
        )

# ──────────────────────────────────────────────────────────────
# WIZARD СОЗДАНИЯ ПОСТА
# ──────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "new_post")
async def step1_start(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return await c.answer("⛔", show_alert=True)
    await state.set_state(CreatePost.content)
    await c.message.answer(
        "📝 <b>Шаг 1 — Контент поста</b>\n\n"
        "Отправь что хочешь опубликовать:\n"
        "• Текст (HTML теги поддерживаются)\n"
        "• Фото / Видео / GIF / Аудио / Документ / Стикер\n"
        "• Фото + текст (подпись)\n\n"
        "<i>/cancel — отмена</i>",
        parse_mode="HTML"
    )

@dp.message(CreatePost.content)
async def step2_buttons(m: Message, state: FSMContext):
    content = extract_content(m)
    await state.update_data(content=content)
    await state.set_state(CreatePost.buttons)
    await m.answer(
        "🔘 <b>Шаг 2 — Инлайн кнопки</b>\n\n"
        "Добавь кнопки в формате:\n"
        "<code>Название кнопки | https://ссылка.com</code>\n"
        "<code>Ещё кнопка | https://другая.com</code>\n\n"
        "Пустая строка = новый ряд.\n"
        "Напиши <b>нет</b> — без кнопок.\n\n"
        "<i>/cancel — отмена</i>",
        parse_mode="HTML"
    )

@dp.message(CreatePost.buttons)
async def step3_schedule(m: Message, state: FSMContext):
    kb = parse_buttons(m.text or "нет")
    await state.update_data(buttons_raw=m.text, parsed_kb=None if kb is None else True)
    # Сохраняем кнопки как JSON-сериализуемый формат
    if kb:
        btn_data = [[{"text": b.text, "url": b.url} for b in row] for row in kb.inline_keyboard]
    else:
        btn_data = []
    await state.update_data(btn_data=btn_data)

    await state.set_state(CreatePost.schedule)
    sched_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🚀 Сразу",          callback_data="sched_now"),
        InlineKeyboardButton(text="⏰ Отложить",        callback_data="sched_later"),
    ]])
    await m.answer("📅 <b>Шаг 3 — Когда публиковать?</b>", reply_markup=sched_kb, parse_mode="HTML")

@dp.callback_query(F.data == "sched_now")
async def step_preview(c: CallbackQuery, state: FSMContext):
    await state.update_data(schedule_type="now", schedule_value=None)
    await _show_preview(c, state)

@dp.callback_query(F.data == "sched_later")
async def step_schedule_input(c: CallbackQuery, state: FSMContext):
    await state.set_state(CreatePost.schedule_val)
    await c.message.edit_text(
        "⏰ <b>Когда опубликовать?</b>\n\n"
        "Формат: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n"
        "или просто <code>30</code> (через 30 минут)\n\n"
        "<i>/cancel — отмена</i>",
        parse_mode="HTML"
    )

@dp.message(CreatePost.schedule_val)
async def step_schedule_value(m: Message, state: FSMContext):
    val = m.text.strip()
    # Если число — через N минут
    if val.isdigit():
        dt = datetime.now() + timedelta(minutes=int(val))
        sched_str = dt.strftime("%d.%m.%Y %H:%M")
        await state.update_data(schedule_type="delay", schedule_value=sched_str)
    else:
        try:
            datetime.strptime(val, "%d.%m.%Y %H:%M")
            await state.update_data(schedule_type="fixed", schedule_value=val)
        except ValueError:
            return await m.answer("❌ Неверный формат. Пример: <code>25.02.2026 15:30</code> или <code>30</code>",
                                  parse_mode="HTML")
    await state.set_state(CreatePost.preview)
    data = await state.get_data()
    sched_time = data["schedule_value"]
    await m.answer(f"✅ Запланировано на <b>{sched_time}</b>", parse_mode="HTML")
    # Строим callback как будто нажали "предпросмотр"
    class FakeCallback:
        from_user = m.from_user
        message   = m
        async def answer(self, *a, **kw): pass
    await _show_preview(FakeCallback(), state)

async def _show_preview(c, state: FSMContext):
    await state.set_state(CreatePost.preview)
    data = await state.get_data()
    content  = data.get("content", {})
    btn_data = data.get("btn_data", [])
    sched    = data.get("schedule_value")

    # Реконструируем клавиатуру для превью
    kb = None
    if btn_data:
        rows = [[InlineKeyboardButton(text=b["text"], url=b["url"]) for b in row] for row in btn_data]
        kb = InlineKeyboardMarkup(inline_keyboard=rows)

    uid = c.from_user.id
    await bot.send_message(uid, "👁 <b>Предпросмотр поста:</b>", parse_mode="HTML")
    await preview_post(uid, content, kb)

    sched_info = f"\n⏰ Публикация: <b>{sched}</b>" if sched else "\n🚀 Публикация: <b>немедленно</b>"
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Опубликовать",  callback_data="pub_confirm"),
        InlineKeyboardButton(text="✏️ Изменить текст", callback_data="pub_edit"),
        InlineKeyboardButton(text="❌ Отмена",         callback_data="pub_cancel"),
    ]])
    await bot.send_message(uid,
        f"Как выглядит пост сверху.{sched_info}\n\nПубликуем?",
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
        "✏️ Отправь новый контент для поста (текст, фото, видео и т.д.).\nКнопки и расписание будут сброшены.\n\n<i>/cancel — отмена</i>",
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "pub_confirm")
async def pub_confirm(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return await c.answer("⛔", show_alert=True)
    data = await state.get_data()
    await state.clear()

    content     = data.get("content", {})
    btn_data    = data.get("btn_data", [])
    sched_type  = data.get("schedule_type", "now")
    sched_value = data.get("schedule_value")

    kb = None
    if btn_data:
        rows = [[InlineKeyboardButton(text=b["text"], url=b["url"]) for b in row] for row in btn_data]
        kb = InlineKeyboardMarkup(inline_keyboard=rows)

    if sched_type == "now":
        # Публикуем сразу
        try:
            msg_id = await send_post(content, kb)
            _track_post()
            await save_config()
            await c.message.edit_text(
                f"✅ <b>Пост опубликован!</b>\nID сообщения: <code>{msg_id}</code>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🔙 В меню", callback_data="to_main")
                ]]),
                parse_mode="HTML"
            )
        except Exception as e:
            await c.message.edit_text(f"❌ Ошибка публикации: {pyhtml.escape(str(e))}", parse_mode="HTML")
    else:
        # Отложенная публикация
        job_id = f"post_{int(time.time())}"
        try:
            pub_dt = datetime.strptime(sched_value, "%d.%m.%Y %H:%M")
        except Exception:
            return await c.message.edit_text("❌ Неверный формат даты")

        delay = (pub_dt - datetime.now()).total_seconds()
        if delay < 0:
            return await c.message.edit_text("❌ Время уже прошло. Попробуй снова.")

        async def delayed_publish():
            await asyncio.sleep(delay)
            try:
                await send_post(content, kb)
                _track_post()
                await save_config()
                await bot.send_message(c.from_user.id, f"✅ Отложенный пост опубликован ({sched_value})!")
            except Exception as e:
                await bot.send_message(c.from_user.id, f"❌ Ошибка отложенного поста: {e}")
            finally:
                _scheduled.pop(job_id, None)

        task = asyncio.create_task(delayed_publish())
        _scheduled[job_id] = task

        await c.message.edit_text(
            f"⏰ <b>Пост запланирован на {sched_value}</b>\n\n"
            f"ID задачи: <code>{job_id}</code>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 В меню", callback_data="to_main")
            ]]),
            parse_mode="HTML"
        )

def _track_post():
    """Фиксирует статистику по постам"""
    st    = get_stats()
    today = datetime.now().strftime("%d.%m")
    st["totalPosts"] = st.get("totalPosts", 0) + 1
    history = st.setdefault("history", [])
    day = next((d for d in history if d.get("date") == today), None)
    if day:
        day["posts"] = day.get("posts", 0) + 1
    else:
        history.append({"date": today, "posts": 1})
    st["history"] = history[-30:]

# ──────────────────────────────────────────────────────────────
# КОМАНДА /broadcast (отправка в канал напрямую через команду)
# ──────────────────────────────────────────────────────────────
@dp.message(Command("stats"))
async def cmd_stats(m: Message):
    if not is_admin(m.from_user.id):
        return await m.answer("⛔ Нет доступа.")
    st = get_stats()
    history = st.get("history", [])
    text = (
        f"📊 <b>Статистика постинга</b>\n\n"
        f"📮 Всего постов: <b>{st.get('totalPosts', 0)}</b>\n\n"
        f"<b>Последние дни:</b>\n"
    )
    for day in history[-14:]:
        text += f"  • {day['date']}: {day.get('posts', 0)} постов\n"
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
