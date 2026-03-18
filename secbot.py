"""
╔══════════════════════════════════════════════════════════════════════╗
║           ADVANCED TELEGRAM BOT - GUARD SYSTEM v2.1                 ║
║     Расширенная модерация, анти-спам, безопасность, логирование     ║
╚══════════════════════════════════════════════════════════════════════╝

УСТАНОВКА:
    pip install "python-telegram-bot[job-queue]==20.7" aiosqlite python-dotenv httpx

НАСТРОЙКА:
    Создайте файл .env:
        BOT_TOKEN=ваш_токен
        OWNER_ID=ваш_telegram_id

ЗАПУСК:
    python bot.py

КТО МОЖЕТ ИСПОЛЬЗОВАТЬ КОМАНДЫ МОДЕРАЦИИ:
    - Telegram-администратор чата (любой)
    - ИЛИ пользователь добавлен owner'ом через /addstaff
    Обычный участник команды выполнить не сможет.

ИСПРАВЛЕНИЯ v2.1:
    - /unshadowban теперь работает по ответу И по /unshadowban [id]
    - /shadowban тоже принимает ID: /shadowban [id]
    - /userinfo принимает ID: /userinfo [id]
    - Команды модерации проверяют Telegram-статус админа чата
    - Убраны все падения от отсутствия job_queue (APScheduler)
    - Исправлен deprecated utcfromtimestamp
    - Исправлен slowmode (прямой HTTP вызов)
    - Shadowban проверяется ДО проверки на стафф
    - Улучшен /purge (от reply до текущего сообщения)
    - /unmute теперь удаляет запись из БД
    - HTML-символы экранируются в именах пользователей
"""

import asyncio
import logging
import re
import time
import json
import random
import datetime as dt
from collections import defaultdict, deque
from typing import Optional, Dict, List, Tuple
from enum import Enum

import aiosqlite
import httpx
from dotenv import load_dotenv
import os

from telegram import (
    Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup,
    ChatMember, Message, User, Chat
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ChatMemberHandler, filters, ContextTypes
)
from telegram.constants import ChatType, ParseMode
from telegram.error import TelegramError, BadRequest, Forbidden

load_dotenv()

# ══════════════════════════════════════════════════════
#  КОНФИГУРАЦИЯ
# ══════════════════════════════════════════════════════

BOT_TOKEN = os.getenv("SECURITY_BOT_TOKEN", "")
OWNER_ID  = int(os.getenv("OWNER_ID", "0"))
DB_PATH   = "guard_bot.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("guard_bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("GuardBot")


# ══════════════════════════════════════════════════════
#  КОНСТАНТЫ
# ══════════════════════════════════════════════════════

class Role(str, Enum):
    OWNER     = "owner"
    TRUSTED   = "trusted"
    MODERATOR = "moderator"

FLOOD_MESSAGES      = 5    # сообщений за окно
FLOOD_INTERVAL      = 5    # секунд
FLOOD_MUTE_DURATION = 300  # мут 5 минут
WARNS_LIMIT         = 3    # авто-бан
CAPTCHA_TIMEOUT     = 90   # секунд
DUPLICATE_LIMIT     = 3    # одинаковых сообщений подряд

LINK_WHITELIST = ["t.me", "telegram.org", "telegram.me"]

SPAM_PATTERNS = [
    r"(?i)(заработ|earn|crypto|крипто|invest|инвест).{0,30}(click|жми|подпис|profit|профит)",
    r"(?i)(быстр|quick).{0,20}(деньг|money|заработ|earn)",
    r"(?i)casino|казино|ставк|букмекер|1xbet|mostbet|melbet",
    r"(?i)(подписчик|follower|subscriber).{0,20}(купить|buy|продам|sell)",
    r"(?i)(накрут|boost|прокач).{0,20}(подписчик|follower|like|лайк)",
    r"@[A-Za-z0-9_]{5,32}\s*(заработ|подпис|casino|crypto)",
    r"(?i)adult|18\+|только.{0,5}взросл",
    r"(?i)(пиши|write|dm|пм|pm).{0,15}(продам|купл|offer|предлаг)",
]
SPAM_COMPILED = [re.compile(p) for p in SPAM_PATTERNS]

RAID_JOIN_COUNT       = 10
RAID_JOIN_WINDOW      = 30   # секунд
RAID_LOCKDOWN_DURATION = 300  # секунд


# ══════════════════════════════════════════════════════
#  IN-MEMORY ТРЕКЕРЫ
# ══════════════════════════════════════════════════════

flood_tracker:     Dict[int, Dict[int, deque]]  = defaultdict(lambda: defaultdict(deque))
duplicate_tracker: Dict[int, Dict[int, Tuple]]  = defaultdict(dict)
captcha_pending:   Dict[Tuple[int, int], dict]  = {}
raid_tracker:      Dict[int, deque]              = defaultdict(deque)
lockdown_active:   Dict[int, float]              = {}
shadowbanned:      Dict[int, set]                = defaultdict(set)
mute_tracker:      Dict[int, Dict[int, float]]   = defaultdict(dict)


# ══════════════════════════════════════════════════════
#  БАЗА ДАННЫХ
# ══════════════════════════════════════════════════════

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS authorized_chats (
            chat_id          INTEGER PRIMARY KEY,
            chat_title       TEXT,
            chat_type        TEXT,
            added_by         INTEGER,
            added_at         TEXT,
            project_owner_id INTEGER,
            settings         TEXT DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS staff (
            user_id  INTEGER PRIMARY KEY,
            username TEXT,
            role     TEXT,
            added_by INTEGER,
            added_at TEXT
        );
        CREATE TABLE IF NOT EXISTS warnings (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id   INTEGER,
            user_id   INTEGER,
            reason    TEXT,
            issued_by INTEGER,
            issued_at TEXT
        );
        CREATE TABLE IF NOT EXISTS bans (
            chat_id   INTEGER,
            user_id   INTEGER,
            reason    TEXT,
            banned_by INTEGER,
            banned_at TEXT,
            PRIMARY KEY (chat_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS mutes (
            chat_id  INTEGER,
            user_id  INTEGER,
            until    TEXT,
            reason   TEXT,
            muted_by INTEGER,
            PRIMARY KEY (chat_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS action_logs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id         INTEGER,
            action_type     TEXT,
            target_user_id  INTEGER,
            target_username TEXT,
            performed_by    INTEGER,
            reason          TEXT,
            details         TEXT,
            created_at      TEXT
        );
        CREATE TABLE IF NOT EXISTS word_filters (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id  INTEGER,
            word     TEXT,
            action   TEXT DEFAULT 'delete',
            added_by INTEGER
        );
        CREATE TABLE IF NOT EXISTS link_whitelist (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id  INTEGER,
            domain   TEXT,
            added_by INTEGER
        );
        CREATE TABLE IF NOT EXISTS spam_stats (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id      INTEGER,
            user_id      INTEGER,
            spam_type    TEXT,
            detected_at  TEXT,
            message_text TEXT
        );
        """)
        await db.commit()


# ─── Чаты ────────────────────────────────────────────

async def is_authorized_chat(chat_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM authorized_chats WHERE chat_id=?", (chat_id,)) as c:
            return await c.fetchone() is not None

async def authorize_chat(chat_id: int, title: str, chat_type: str, added_by: int, project_owner_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO authorized_chats (chat_id,chat_title,chat_type,added_by,added_at,project_owner_id) VALUES (?,?,?,?,?,?)",
            (chat_id, title, chat_type, added_by, _now(), project_owner_id)
        )
        await db.commit()

async def deauthorize_chat(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM authorized_chats WHERE chat_id=?", (chat_id,))
        await db.commit()

async def get_chat_settings(chat_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT settings FROM authorized_chats WHERE chat_id=?", (chat_id,)) as c:
            row = await c.fetchone()
            if row:
                try: return json.loads(row[0] or "{}")
                except: return {}
    return {}

async def set_chat_setting(chat_id: int, key: str, value):
    s = await get_chat_settings(chat_id)
    s[key] = value
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE authorized_chats SET settings=? WHERE chat_id=?", (json.dumps(s), chat_id))
        await db.commit()

async def get_chat_project_owner(chat_id: int) -> Optional[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT project_owner_id FROM authorized_chats WHERE chat_id=?", (chat_id,)) as c:
            row = await c.fetchone()
            return row[0] if row else None


# ─── Стафф ───────────────────────────────────────────

async def is_staff(user_id: int) -> bool:
    if user_id == OWNER_ID: return True
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM staff WHERE user_id=?", (user_id,)) as c:
            return await c.fetchone() is not None

async def get_staff_role(user_id: int) -> Optional[str]:
    if user_id == OWNER_ID: return Role.OWNER
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT role FROM staff WHERE user_id=?", (user_id,)) as c:
            row = await c.fetchone()
            return row[0] if row else None

async def add_staff(user_id: int, username: str, role: str, added_by: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO staff (user_id,username,role,added_by,added_at) VALUES (?,?,?,?,?)",
            (user_id, username, role, added_by, _now())
        )
        await db.commit()

async def remove_staff(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM staff WHERE user_id=?", (user_id,))
        await db.commit()

async def list_staff() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id,username,role,added_by,added_at FROM staff ORDER BY role") as c:
            return await c.fetchall()


# ─── Предупреждения ───────────────────────────────────

async def add_warning(chat_id: int, user_id: int, reason: str, issued_by: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO warnings (chat_id,user_id,reason,issued_by,issued_at) VALUES (?,?,?,?,?)",
            (chat_id, user_id, reason, issued_by, _now())
        )
        await db.commit()
        async with db.execute("SELECT COUNT(*) FROM warnings WHERE chat_id=? AND user_id=?", (chat_id, user_id)) as c:
            return (await c.fetchone())[0]

async def get_warnings(chat_id: int, user_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT reason,issued_at FROM warnings WHERE chat_id=? AND user_id=? ORDER BY issued_at",
            (chat_id, user_id)
        ) as c:
            return await c.fetchall()

async def clear_warnings(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM warnings WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        await db.commit()


# ─── Баны ────────────────────────────────────────────

async def add_ban(chat_id: int, user_id: int, reason: str, banned_by: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO bans (chat_id,user_id,reason,banned_by,banned_at) VALUES (?,?,?,?,?)",
            (chat_id, user_id, reason, banned_by, _now())
        )
        await db.commit()

async def remove_ban(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM bans WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        await db.commit()

async def is_banned(chat_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM bans WHERE chat_id=? AND user_id=?", (chat_id, user_id)) as c:
            return await c.fetchone() is not None


# ─── Логи ────────────────────────────────────────────

async def log_action(chat_id: int, action_type: str, target_id: int,
                     target_name: str, by_id: int, reason: str = "", details: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO action_logs (chat_id,action_type,target_user_id,target_username,performed_by,reason,details,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (chat_id, action_type, target_id, target_name, by_id, reason, details, _now())
        )
        await db.commit()


# ─── Фильтры ─────────────────────────────────────────

async def get_word_filters(chat_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id,word,action FROM word_filters WHERE chat_id=?", (chat_id,)) as c:
            return await c.fetchall()

async def add_word_filter(chat_id: int, word: str, action: str, added_by: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO word_filters (chat_id,word,action,added_by) VALUES (?,?,?,?)", (chat_id, word.lower(), action, added_by))
        await db.commit()

async def remove_word_filter(chat_id: int, filter_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM word_filters WHERE id=? AND chat_id=?", (filter_id, chat_id))
        await db.commit()

async def get_chat_link_whitelist(chat_id: int) -> List[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT domain FROM link_whitelist WHERE chat_id=?", (chat_id,)) as c:
            return [r[0] for r in await c.fetchall()]

async def add_link_whitelist(chat_id: int, domain: str, added_by: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO link_whitelist (chat_id,domain,added_by) VALUES (?,?,?)", (chat_id, domain.lower(), added_by))
        await db.commit()

async def log_spam(chat_id: int, user_id: int, spam_type: str, text: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO spam_stats (chat_id,user_id,spam_type,detected_at,message_text) VALUES (?,?,?,?,?)",
            (chat_id, user_id, spam_type, _now(), text[:500])
        )
        await db.commit()


# ══════════════════════════════════════════════════════
#  УТИЛИТЫ
# ══════════════════════════════════════════════════════

def _now() -> str:
    return dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

def _ts() -> float:
    return time.time()

def _until_dt(ts: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc)

def _esc(text: str) -> str:
    """Экранирует HTML-символы."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def user_mention(user: User) -> str:
    name = _esc(user.full_name or f"User{user.id}")
    return f'<a href="tg://user?id={user.id}">{name}</a>'

def format_duration(seconds: int) -> str:
    if seconds < 60:      return f"{seconds}с"
    elif seconds < 3600:  return f"{seconds // 60}м"
    elif seconds < 86400: return f"{seconds // 3600}ч"
    else:                 return f"{seconds // 86400}д"

def generate_captcha() -> Tuple[str, int]:
    a, b = random.randint(1, 20), random.randint(1, 20)
    op   = random.choice(["+", "-", "×"])
    ans  = a + b if op == "+" else (a - b if op == "-" else a * b)
    return f"{a} {op} {b} = ?", ans

def extract_user_from_reply(update: Update) -> Optional[User]:
    if update.message and update.message.reply_to_message:
        return update.message.reply_to_message.from_user
    return None

def parse_time_arg(arg: str) -> int:
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if not arg: return 0
    if arg[-1] in units:
        try: return int(arg[:-1]) * units[arg[-1]]
        except ValueError: pass
    try: return int(arg) * 60
    except ValueError: return 0

async def safe_delete(msg: Message):
    try:
        await msg.delete()
    except (TelegramError, BadRequest):
        pass

async def safe_ban(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, until: int = 0) -> bool:
    try:
        until_dt = _until_dt(until) if until else None
        await context.bot.ban_chat_member(chat_id, user_id, until_date=until_dt)
        return True
    except (TelegramError, BadRequest) as e:
        logger.warning(f"Ban failed {user_id}@{chat_id}: {e}")
        return False

async def safe_mute(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, until: int = 0) -> bool:
    try:
        perms    = ChatPermissions(can_send_messages=False, can_send_polls=False,
                                   can_send_other_messages=False, can_add_web_page_previews=False)
        until_dt = _until_dt(until) if until else None
        await context.bot.restrict_chat_member(chat_id, user_id, perms, until_date=until_dt)
        return True
    except (TelegramError, BadRequest) as e:
        logger.warning(f"Mute failed {user_id}@{chat_id}: {e}")
        return False

async def safe_unmute(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
    try:
        perms = ChatPermissions(
            can_send_messages=True, can_send_polls=True,
            can_send_other_messages=True, can_add_web_page_previews=True,
            can_change_info=False, can_invite_users=True, can_pin_messages=False
        )
        await context.bot.restrict_chat_member(chat_id, user_id, perms)
        return True
    except (TelegramError, BadRequest):
        return False

async def notify_owner(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str):
    oid = await get_chat_project_owner(chat_id)
    if oid:
        try:
            await context.bot.send_message(oid, text, parse_mode=ParseMode.HTML)
        except (TelegramError, Forbidden):
            pass

def _jq(context: ContextTypes.DEFAULT_TYPE, callback, delay: int, **kwargs):
    """Запуск отложенной задачи, безопасный при отсутствии APScheduler."""
    if context.job_queue:
        context.job_queue.run_once(callback, delay, **kwargs)


# ══════════════════════════════════════════════════════
#  ПРОВЕРКА ПРАВ ДОСТУПА
# ══════════════════════════════════════════════════════

async def check_is_tg_admin(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
    """Является ли пользователь Telegram-администратором данного чата."""
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]
    except TelegramError:
        return False

async def can_moderate(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
    """
    True если пользователь может выполнять команды модерации.
    Условие: owner/staff бота  ИЛИ  Telegram-администратор чата.
    """
    if user_id == OWNER_ID:
        return True
    if await is_staff(user_id):
        return True
    if chat_id and await check_is_tg_admin(context, chat_id, user_id):
        return True
    return False


# ══════════════════════════════════════════════════════
#  ДЕКОРАТОРЫ
# ══════════════════════════════════════════════════════

def owner_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user or user.id != OWNER_ID:
            if update.message:
                await update.message.reply_text("🚫 Только для владельца бота.")
            return
        return await func(update, context)
    wrapper.__name__ = func.__name__
    return wrapper

def staff_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user or not await is_staff(user.id):
            if update.message:
                await update.message.reply_text("🚫 Нет доступа.")
            return
        return await func(update, context)
    wrapper.__name__ = func.__name__
    return wrapper

def mod_access(func):
    """Staff бота ИЛИ Telegram-админ чата."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat = update.effective_chat
        if not user or not chat:
            return
        if not await can_moderate(context, chat.id, user.id):
            if update.message:
                await update.message.reply_text(
                    "🚫 Команды модерации доступны администраторам чата "
                    "или персоналу бота."
                )
            return
        return await func(update, context)
    wrapper.__name__ = func.__name__
    return wrapper

def authorized_chat_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        if chat and chat.type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
            if not await is_authorized_chat(chat.id):
                try:
                    await context.bot.leave_chat(chat.id)
                except Exception:
                    pass
                return
        return await func(update, context)
    wrapper.__name__ = func.__name__
    return wrapper


# ══════════════════════════════════════════════════════
#  ОБНАРУЖЕНИЕ СПАМА / НАРУШЕНИЙ
# ══════════════════════════════════════════════════════

def check_spam_patterns(text: str) -> Optional[str]:
    for i, p in enumerate(SPAM_COMPILED):
        if p.search(text): return f"pattern_{i}"
    return None

def check_flood(chat_id: int, user_id: int) -> bool:
    now = _ts()
    dq  = flood_tracker[chat_id][user_id]
    dq.append(now)
    while dq and dq[0] < now - FLOOD_INTERVAL:
        dq.popleft()
    return len(dq) >= FLOOD_MESSAGES

def check_duplicate(chat_id: int, user_id: int, text: str) -> bool:
    prev = duplicate_tracker[chat_id].get(user_id)
    if prev:
        last, count = prev
        if last == text:
            count += 1
            duplicate_tracker[chat_id][user_id] = (text, count)
            return count >= DUPLICATE_LIMIT
    duplicate_tracker[chat_id][user_id] = (text, 1)
    return False

def check_links(text: str, chat_whitelist: List[str]) -> bool:
    url_re = re.compile(
        r'(https?://|t\.me/|telegram\.me/|@[A-Za-z0-9_]{5,})'
        r'([A-Za-z0-9\-._~:/?#\[\]@!$&\'()*+,;=%]*)',
        re.IGNORECASE
    )
    all_ok = LINK_WHITELIST + chat_whitelist
    for m in url_re.finditer(text):
        url = m.group(0).lower()
        if not any(d in url for d in all_ok):
            return True
    return False

def check_raid(chat_id: int) -> bool:
    now = _ts()
    dq  = raid_tracker[chat_id]
    dq.append(now)
    while dq and dq[0] < now - RAID_JOIN_WINDOW:
        dq.popleft()
    return len(dq) >= RAID_JOIN_COUNT


# ══════════════════════════════════════════════════════
#  КАПЧА
# ══════════════════════════════════════════════════════

async def send_captcha(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user: User):
    question, answer = generate_captcha()
    key = (chat_id, user.id)

    await safe_mute(context, chat_id, user.id)

    variants = {answer}
    while len(variants) < 4:
        variants.add(answer + random.randint(-10, 10))
    variants = list(variants)
    random.shuffle(variants)

    row    = [InlineKeyboardButton(str(v), callback_data=f"captcha:{user.id}:{v}:{answer}") for v in variants]
    markup = InlineKeyboardMarkup([row])
    text   = (
        f"👋 Добро пожаловать, {user_mention(user)}!\n\n"
        f"🔐 Для входа решите задачу:\n<b>{question}</b>\n\n"
        f"⏳ У вас {CAPTCHA_TIMEOUT} секунд."
    )
    msg = await context.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_markup=markup)
    captcha_pending[key] = {"answer": answer, "msg_id": msg.message_id, "time": _ts()}

    _jq(context, _captcha_timeout, CAPTCHA_TIMEOUT,
        data={"chat_id": chat_id, "user_id": user.id, "msg_id": msg.message_id},
        name=f"captcha_{chat_id}_{user.id}")

async def _captcha_timeout(context: ContextTypes.DEFAULT_TYPE):
    d       = context.job.data
    chat_id = d["chat_id"]; user_id = d["user_id"]; msg_id = d["msg_id"]
    key     = (chat_id, user_id)
    if key in captcha_pending:
        del captcha_pending[key]
        await safe_ban(context, chat_id, user_id, until=int(_ts() + 600))
        try:
            await context.bot.delete_message(chat_id, msg_id)
        except Exception:
            pass
        await log_action(chat_id, "captcha_timeout_kick", user_id, "unknown", context.bot.id, "Не прошёл капчу")


# ══════════════════════════════════════════════════════
#  ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ
# ══════════════════════════════════════════════════════


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.edited_message
    if not msg: return

    chat = update.effective_chat
    user = update.effective_user
    if not user or not chat: return

    chat_id = chat.id
    user_id = user.id

    if user.is_bot: return

    # ── Shadowban ПЕРВЫМ ──
    if user_id in shadowbanned.get(chat_id, set()):
        await safe_delete(msg)
        return

    # Стафф и Telegram-админы чата — без авто-модерации
    if await can_moderate(context, chat_id, user_id):
        return

    settings = await get_chat_settings(chat_id)
    text     = msg.text or msg.caption or ""

    # ── 1. Флуд ──
    if settings.get("antiflood", True) and check_flood(chat_id, user_id):
        await safe_delete(msg)
        until = int(_ts() + FLOOD_MUTE_DURATION)
        await safe_mute(context, chat_id, user_id, until)
        mute_tracker[chat_id][user_id] = until
        wc = await add_warning(chat_id, user_id, "Флуд", context.bot.id)
        await log_action(chat_id, "mute_flood", user_id, user.full_name, context.bot.id, "Флуд")
        await log_spam(chat_id, user_id, "flood", text[:100])
        notif = await context.bot.send_message(
            chat_id,
            f"🌊 {user_mention(user)} замучен на {format_duration(FLOOD_MUTE_DURATION)} за флуд. [⚠️ {wc}/{WARNS_LIMIT}]",
            parse_mode=ParseMode.HTML
        )
        await notify_owner(context, chat_id,
            f"🌊 <b>Флуд</b> в <code>{chat_id}</code>\n"
            f"Пользователь: {user_mention(user)} (<code>{user_id}</code>)\n"
            f"Мут: {format_duration(FLOOD_MUTE_DURATION)}"
        )
        _jq(context, lambda ctx: safe_delete(notif), 15)
        if wc >= WARNS_LIMIT:
            await _auto_ban(context, chat_id, user, "Лимит предупреждений (флуд)")
        return

    # ── 2. Дубликаты ──
    if settings.get("antiduplicate", True) and text and check_duplicate(chat_id, user_id, text):
        await safe_delete(msg)
        wc    = await add_warning(chat_id, user_id, "Копипаст/дубли", context.bot.id)
        notif = await context.bot.send_message(
            chat_id,
            f"♻️ {user_mention(user)}, не повторяй одно сообщение. [⚠️ {wc}/{WARNS_LIMIT}]",
            parse_mode=ParseMode.HTML
        )
        _jq(context, lambda ctx: safe_delete(notif), 10)
        if wc >= WARNS_LIMIT:
            await _auto_ban(context, chat_id, user, "Лимит предупреждений (дубли)")
        return

    # ── 3. Спам-паттерны ──
    if settings.get("antispam", True) and text:
        stype = check_spam_patterns(text)
        if stype:
            await safe_delete(msg)
            wc    = await add_warning(chat_id, user_id, "Спам", context.bot.id)
            await log_action(chat_id, "warn_spam", user_id, user.full_name, context.bot.id, stype)
            await log_spam(chat_id, user_id, stype, text)
            notif = await context.bot.send_message(
                chat_id,
                f"🚫 {user_mention(user)}, спам удалён. [⚠️ {wc}/{WARNS_LIMIT}]",
                parse_mode=ParseMode.HTML
            )
            await notify_owner(context, chat_id,
                f"🚫 <b>Спам</b> в <code>{chat_id}</code>\n"
                f"Пользователь: {user_mention(user)}\n"
                f"Тип: <code>{stype}</code>\n"
                f"Текст: <code>{_esc(text[:200])}</code>"
            )
            _jq(context, lambda ctx: safe_delete(notif), 12)
            if wc >= WARNS_LIMIT:
                await _auto_ban(context, chat_id, user, "Лимит предупреждений (спам)")
            return

    # ── 4. Ссылки ──
    if settings.get("antilinks", False) and text:
        chat_wl = await get_chat_link_whitelist(chat_id)
        if check_links(text, chat_wl):
            await safe_delete(msg)
            wc    = await add_warning(chat_id, user_id, "Запрещённая ссылка", context.bot.id)
            notif = await context.bot.send_message(
                chat_id,
                f"🔗 {user_mention(user)}, ссылки запрещены. [⚠️ {wc}/{WARNS_LIMIT}]",
                parse_mode=ParseMode.HTML
            )
            _jq(context, lambda ctx: safe_delete(notif), 10)
            if wc >= WARNS_LIMIT:
                await _auto_ban(context, chat_id, user, "Лимит предупреждений (ссылки)")
            return

    # ── 5. Фильтры слов ──
    if text:
        wfs        = await get_word_filters(chat_id)
        text_lower = text.lower()
        for f_id, word, action in wfs:
            if word in text_lower:
                await safe_delete(msg)
                await log_action(chat_id, f"filter_{action}", user_id, user.full_name, context.bot.id, f"Слово: {word}")
                if action == "warn":
                    wc    = await add_warning(chat_id, user_id, f"Запрещённое слово: {word}", context.bot.id)
                    notif = await context.bot.send_message(
                        chat_id,
                        f"⚠️ {user_mention(user)}, запрещённое слово. [⚠️ {wc}/{WARNS_LIMIT}]",
                        parse_mode=ParseMode.HTML
                    )
                    _jq(context, lambda ctx: safe_delete(notif), 10)
                    if wc >= WARNS_LIMIT:
                        await _auto_ban(context, chat_id, user, "Лимит предупреждений (фильтр)")
                elif action == "mute":
                    until = int(_ts() + 3600)
                    await safe_mute(context, chat_id, user_id, until)
                    notif = await context.bot.send_message(
                        chat_id,
                        f"🔇 {user_mention(user)} замучен на 1ч за нарушение фильтра.",
                        parse_mode=ParseMode.HTML
                    )
                    _jq(context, lambda ctx: safe_delete(notif), 15)
                elif action == "ban":
                    await safe_ban(context, chat_id, user_id)
                    await add_ban(chat_id, user_id, f"Фильтр: {word}", context.bot.id)
                    await context.bot.send_message(
                        chat_id,
                        f"🔨 {user_mention(user)} заблокирован за нарушение фильтра.",
                        parse_mode=ParseMode.HTML
                    )
                return

    # ── 6. Анти-форвард ──
    if settings.get("antiforward", False) and msg.forward_date:
        await safe_delete(msg)
        notif = await context.bot.send_message(
            chat_id,
            f"📩 {user_mention(user)}, пересылка сообщений запрещена.",
            parse_mode=ParseMode.HTML
        )
        _jq(context, lambda ctx: safe_delete(notif), 10)


async def _auto_ban(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user: User, reason: str):
    await safe_ban(context, chat_id, user.id)
    await add_ban(chat_id, user.id, reason, context.bot.id)
    await clear_warnings(chat_id, user.id)
    await log_action(chat_id, "autoban", user.id, user.full_name, context.bot.id, reason)
    await context.bot.send_message(
        chat_id,
        f"🔨 {user_mention(user)} автоматически <b>заблокирован</b>.\nПричина: {reason}",
        parse_mode=ParseMode.HTML
    )
    await notify_owner(context, chat_id,
        f"🔨 <b>Авто-бан</b> в <code>{chat_id}</code>\n"
        f"Пользователь: {user_mention(user)} (<code>{user.id}</code>)\nПричина: {reason}"
    )


# ══════════════════════════════════════════════════════
#  НОВЫЕ УЧАСТНИКИ
# ══════════════════════════════════════════════════════

async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.new_chat_members: return

    chat_id  = msg.chat.id
    settings = await get_chat_settings(chat_id)

    for user in msg.new_chat_members:
        if user.is_bot: continue

        if settings.get("antiraid", True) and check_raid(chat_id):
            if chat_id not in lockdown_active or lockdown_active[chat_id] < _ts():
                lockdown_active[chat_id] = _ts() + RAID_LOCKDOWN_DURATION
                await log_action(chat_id, "raid_lockdown", 0, "SYSTEM", context.bot.id, "Рейд")
                await context.bot.send_message(
                    chat_id,
                    f"🚨 <b>РЕЙД ОБНАРУЖЕН!</b>\nЧат заблокирован на {format_duration(RAID_LOCKDOWN_DURATION)}.",
                    parse_mode=ParseMode.HTML
                )
                await notify_owner(context, chat_id,
                    f"🚨 <b>РЕЙД!</b> Чат <code>{chat_id}</code>\n"
                    f"Lockdown на {format_duration(RAID_LOCKDOWN_DURATION)}"
                )

        if chat_id in lockdown_active and lockdown_active[chat_id] > _ts():
            await safe_ban(context, chat_id, user.id, until=int(lockdown_active[chat_id]))
            await safe_delete(msg)
            continue

        if settings.get("captcha", True):
            await safe_delete(msg)
            await send_captcha(context, chat_id, user)
            await log_action(chat_id, "captcha_sent", user.id, user.full_name, context.bot.id)
        else:
            welcome = settings.get("welcome_text", "")
            if welcome:
                notif = await context.bot.send_message(
                    chat_id,
                    welcome.replace("{user}", user_mention(user)),
                    parse_mode=ParseMode.HTML
                )
                _jq(context, lambda ctx: safe_delete(notif), 30)


# ══════════════════════════════════════════════════════
#  CALLBACK — КАПЧА
# ══════════════════════════════════════════════════════

async def captcha_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    if len(parts) != 4: return

    _, tid_s, chosen_s, correct_s = parts
    target_id = int(tid_s); chosen = int(chosen_s); correct = int(correct_s)
    chat_id   = query.message.chat.id

    if query.from_user.id != target_id:
        await query.answer("Это не ваша капча!", show_alert=True)
        return

    key = (chat_id, target_id)
    if key not in captcha_pending:
        await query.answer("Капча устарела.", show_alert=True)
        return

    if context.job_queue:
        for job in context.job_queue.get_jobs_by_name(f"captcha_{chat_id}_{target_id}"):
            job.schedule_removal()

    del captcha_pending[key]
    try:
        await query.message.delete()
    except Exception:
        pass

    if chosen == correct:
        await safe_unmute(context, chat_id, target_id)
        await log_action(chat_id, "captcha_pass", target_id, query.from_user.full_name, context.bot.id)
        notif = await context.bot.send_message(
            chat_id,
            f"✅ {user_mention(query.from_user)} прошёл проверку!",
            parse_mode=ParseMode.HTML
        )
        _jq(context, lambda ctx: safe_delete(notif), 10)
    else:
        await safe_ban(context, chat_id, target_id, until=int(_ts() + 600))
        await log_action(chat_id, "captcha_fail", target_id, query.from_user.full_name, context.bot.id)
        notif = await context.bot.send_message(
            chat_id,
            f"❌ {user_mention(query.from_user)} не прошёл проверку — кик на 10 минут.",
            parse_mode=ParseMode.HTML
        )
        _jq(context, lambda ctx: safe_delete(notif), 10)


# ══════════════════════════════════════════════════════
#  СИСТЕМНЫЕ КОМАНДЫ (owner / staff)
# ══════════════════════════════════════════════════════

@owner_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ <b>Guard Bot v2.1 активен</b>\n\nВы — владелец системы.\n/help — список команд.",
        parse_mode=ParseMode.HTML
    )

@owner_only
async def cmd_addstaff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "Использование: /addstaff [user_id] [trusted|moderator] [username]\n\n"
            "trusted   — может авторизовывать чаты + модерация\n"
            "moderator — только модерация"
        )
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Неверный ID.")
        return
    role = context.args[1].lower()
    if role not in [Role.TRUSTED, Role.MODERATOR]:
        await update.message.reply_text("Роль: trusted или moderator")
        return
    username = context.args[2] if len(context.args) > 2 else f"user_{target_id}"
    await add_staff(target_id, username, role, OWNER_ID)
    await update.message.reply_text(
        f"✅ <code>{target_id}</code> (@{username}) добавлен как <b>{role}</b>.",
        parse_mode=ParseMode.HTML
    )
    await log_action(0, "add_staff", target_id, username, OWNER_ID, role)

@owner_only
async def cmd_removestaff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /removestaff [user_id]")
        return
    try:
        tid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Неверный ID.")
        return
    await remove_staff(tid)
    await update.message.reply_text(f"✅ <code>{tid}</code> удалён из стаффа.", parse_mode=ParseMode.HTML)

@owner_only
async def cmd_liststaff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    staff = await list_staff()
    lines = [f"👑 <b>Владелец:</b> <code>{OWNER_ID}</code>", ""]
    if not staff:
        lines.append("Стафф пуст.")
    for uid, uname, role, _, _ in staff:
        emoji = "🔑" if role == Role.TRUSTED else "🛡"
        lines.append(f"{emoji} <code>{uid}</code> @{uname} — {role}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

@staff_only
async def cmd_authchat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    role = await get_staff_role(user.id)
    if role not in [Role.OWNER, Role.TRUSTED] and user.id != OWNER_ID:
        await update.message.reply_text("🚫 Только trusted/owner может авторизовывать чаты.")
        return
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
        await update.message.reply_text("Команда только для групп и каналов.")
        return
    await authorize_chat(chat.id, chat.title or "", chat.type, user.id, user.id)
    await update.message.reply_text(
        f"✅ Чат <b>{_esc(chat.title or '')}</b> авторизован!\n"
        f"Логи → вам в личку.\n\n"
        f"Настройки по умолчанию:\n"
        f"• Анти-флуд ✅  • Анти-спам ✅\n"
        f"• Капча ✅  • Анти-рейд ✅\n\n"
        f"Изменить: /settings",
        parse_mode=ParseMode.HTML
    )
    await log_action(chat.id, "chat_authorized", user.id, user.full_name, user.id)

@staff_only
async def cmd_deauthchat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not await is_authorized_chat(chat.id):
        await update.message.reply_text("Чат не авторизован.")
        return
    await deauthorize_chat(chat.id)
    await update.message.reply_text("Чат деавторизован. Бот покидает чат.")
    await context.bot.leave_chat(chat.id)


# ══════════════════════════════════════════════════════
#  КОМАНДЫ МОДЕРАЦИИ  (Telegram-админ чата ИЛИ staff бота)
# ══════════════════════════════════════════════════════


@mod_access
async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat; user = update.effective_user
    target = extract_user_from_reply(update)

    if not target:
        if context.args:
            try:
                tid    = int(context.args[0])
                reason = " ".join(context.args[1:]) or "Без причины"
                await safe_ban(context, chat.id, tid)
                await add_ban(chat.id, tid, reason, user.id)
                await log_action(chat.id, "ban", tid, str(tid), user.id, reason)
                await update.message.reply_text(
                    f"🔨 <code>{tid}</code> заблокирован.\nПричина: {reason}", parse_mode=ParseMode.HTML
                )
                return
            except (ValueError, IndexError):
                pass
        await update.message.reply_text("Ответьте на сообщение или: /ban [id] [причина]")
        return

    reason = " ".join(context.args) if context.args else "Без причины"
    if target.id == OWNER_ID or await is_staff(target.id):
        await update.message.reply_text("🚫 Нельзя банить персонал бота.")
        return
    if await safe_ban(context, chat.id, target.id):
        await add_ban(chat.id, target.id, reason, user.id)
        await log_action(chat.id, "ban", target.id, target.full_name, user.id, reason)
        await update.message.reply_text(
            f"🔨 {user_mention(target)} <b>заблокирован</b>.\nПричина: {reason}", parse_mode=ParseMode.HTML
        )
        await notify_owner(context, chat.id,
            f"🔨 <b>Бан</b> в <code>{chat.id}</code>\n"
            f"Мод: {user_mention(user)}\nЦель: {user_mention(target)}\nПричина: {reason}"
        )
    else:
        await update.message.reply_text("❌ Не удалось. Проверьте права бота.")


@mod_access
async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat; user = update.effective_user
    if not context.args:
        await update.message.reply_text("Использование: /unban [user_id]")
        return
    try:
        tid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Неверный ID.")
        return
    try:
        await context.bot.unban_chat_member(chat.id, tid)
    except TelegramError as e:
        await update.message.reply_text(f"❌ {e}")
        return
    await remove_ban(chat.id, tid)
    await log_action(chat.id, "unban", tid, str(tid), user.id)
    await update.message.reply_text(f"✅ <code>{tid}</code> разблокирован.", parse_mode=ParseMode.HTML)


@mod_access
async def cmd_kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat; user = update.effective_user
    target = extract_user_from_reply(update)
    if not target:
        await update.message.reply_text("Ответьте на сообщение пользователя.")
        return
    reason = " ".join(context.args) if context.args else "Без причины"
    if target.id == OWNER_ID or await is_staff(target.id):
        await update.message.reply_text("🚫 Нельзя кикать персонал бота.")
        return
    try:
        await context.bot.ban_chat_member(chat.id, target.id)
        await context.bot.unban_chat_member(chat.id, target.id)
        await log_action(chat.id, "kick", target.id, target.full_name, user.id, reason)
        await update.message.reply_text(
            f"👢 {user_mention(target)} <b>кикнут</b>.\nПричина: {reason}", parse_mode=ParseMode.HTML
        )
    except TelegramError as e:
        await update.message.reply_text(f"❌ {e}")


@mod_access
async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat; user = update.effective_user
    target = extract_user_from_reply(update)
    if not target:
        await update.message.reply_text("Ответьте на сообщение пользователя.")
        return
    if target.id == OWNER_ID or await is_staff(target.id):
        await update.message.reply_text("🚫 Нельзя мутить персонал бота.")
        return

    duration = 3600; reason = "Без причины"
    if context.args:
        dur = parse_time_arg(context.args[0])
        if dur > 0:
            duration = dur
            reason   = " ".join(context.args[1:]) or "Без причины"
        else:
            reason = " ".join(context.args)

    until = int(_ts() + duration)
    await safe_mute(context, chat.id, target.id, until)
    mute_tracker[chat.id][target.id] = until

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO mutes (chat_id,user_id,until,reason,muted_by) VALUES (?,?,?,?,?)",
            (chat.id, target.id, _until_dt(until).strftime("%Y-%m-%d %H:%M:%S"), reason, user.id)
        )
        await db.commit()

    await log_action(chat.id, "mute", target.id, target.full_name, user.id, reason)
    await update.message.reply_text(
        f"🔇 {user_mention(target)} замучен на <b>{format_duration(duration)}</b>.\nПричина: {reason}",
        parse_mode=ParseMode.HTML
    )
    await notify_owner(context, chat.id,
        f"🔇 <b>Мут</b> в <code>{chat.id}</code>\n"
        f"Мод: {user_mention(user)}\nЦель: {user_mention(target)}\n"
        f"Длительность: {format_duration(duration)}\nПричина: {reason}"
    )


@mod_access
async def cmd_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat; user = update.effective_user
    target = extract_user_from_reply(update)
    if not target:
        await update.message.reply_text("Ответьте на сообщение пользователя.")
        return
    await safe_unmute(context, chat.id, target.id)
    mute_tracker[chat.id].pop(target.id, None)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM mutes WHERE chat_id=? AND user_id=?", (chat.id, target.id))
        await db.commit()
    await log_action(chat.id, "unmute", target.id, target.full_name, user.id)
    await update.message.reply_text(f"🔊 {user_mention(target)} размучен.", parse_mode=ParseMode.HTML)


@mod_access
async def cmd_warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat; user = update.effective_user
    target = extract_user_from_reply(update)
    if not target:
        await update.message.reply_text("Ответьте на сообщение пользователя.")
        return
    if target.id == OWNER_ID or await is_staff(target.id):
        await update.message.reply_text("🚫 Нельзя предупреждать персонал бота.")
        return
    reason = " ".join(context.args) if context.args else "Без причины"
    wc     = await add_warning(chat.id, target.id, reason, user.id)
    await log_action(chat.id, "warn", target.id, target.full_name, user.id, reason)
    if wc >= WARNS_LIMIT:
        await _auto_ban(context, chat.id, target, f"Лимит предупреждений ({wc})")
    else:
        await update.message.reply_text(
            f"⚠️ {user_mention(target)} получил предупреждение [{wc}/{WARNS_LIMIT}]\nПричина: {reason}",
            parse_mode=ParseMode.HTML
        )
        await notify_owner(context, chat.id,
            f"⚠️ <b>Варн</b> в <code>{chat.id}</code>\n"
            f"Мод: {user_mention(user)}\nЦель: {user_mention(target)}\n"
            f"[{wc}/{WARNS_LIMIT}] Причина: {reason}"
        )


@mod_access
async def cmd_unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    target = extract_user_from_reply(update)
    if not target:
        await update.message.reply_text("Ответьте на сообщение пользователя.")
        return
    await clear_warnings(chat.id, target.id)
    await update.message.reply_text(f"✅ Предупреждения {user_mention(target)} сброшены.", parse_mode=ParseMode.HTML)


@mod_access
async def cmd_shadowban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Теневой бан — сообщения тихо удаляются. Ответ на сообщение или /shadowban [id]"""
    chat = update.effective_chat; user = update.effective_user
    target = extract_user_from_reply(update)

    if not target:
        if context.args:
            try:
                target_id   = int(context.args[0])
                target_name = str(target_id)
            except ValueError:
                await update.message.reply_text("Ответьте на сообщение или: /shadowban [id]")
                return
        else:
            await update.message.reply_text("Ответьте на сообщение или: /shadowban [id]")
            return
    else:
        target_id   = target.id
        target_name = target.full_name

    shadowbanned[chat.id].add(target_id)
    await log_action(chat.id, "shadowban", target_id, target_name, user.id)
    await update.message.reply_text(
        f"👻 Shadowban применён к <code>{target_id}</code>.\n"
        f"Сообщения будут тихо удаляться.\n"
        f"Снять: /unshadowban {target_id}",
        parse_mode=ParseMode.HTML
    )


@mod_access
async def cmd_unshadowban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Снять теневой бан. Ответ на сообщение или /unshadowban [id]"""
    chat = update.effective_chat; user = update.effective_user
    target = extract_user_from_reply(update)

    if not target:
        if context.args:
            try:
                target_id   = int(context.args[0])
                target_name = str(target_id)
            except ValueError:
                await update.message.reply_text("Ответьте на сообщение или: /unshadowban [id]")
                return
        else:
            await update.message.reply_text("Ответьте на сообщение или: /unshadowban [id]")
            return
    else:
        target_id   = target.id
        target_name = target.full_name

    if target_id in shadowbanned.get(chat.id, set()):
        shadowbanned[chat.id].discard(target_id)
        await log_action(chat.id, "unshadowban", target_id, target_name, user.id)
        await update.message.reply_text(
            f"✅ Shadowban снят с <code>{target_id}</code>.", parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(
            f"ℹ️ Пользователь <code>{target_id}</code> не в shadowban.", parse_mode=ParseMode.HTML
        )


@mod_access
async def cmd_purge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить N сообщений. Ответьте на первое сообщение."""
    if not context.args:
        await update.message.reply_text("Использование: /purge [кол-во]\nОтветьте на сообщение, с которого начать удаление.")
        return
    try:
        count = min(int(context.args[0]), 200)
    except ValueError:
        await update.message.reply_text("Укажите число.")
        return

    chat = update.effective_chat; user = update.effective_user
    deleted = 0

    if update.message.reply_to_message:
        start_id = update.message.reply_to_message.message_id
        end_id   = update.message.message_id
    else:
        end_id   = update.message.message_id
        start_id = max(1, end_id - count)

    for mid in range(start_id, end_id + 1):
        try:
            await context.bot.delete_message(chat.id, mid)
            deleted += 1
        except Exception:
            pass

    await log_action(chat.id, "purge", 0, "SYSTEM", user.id, f"~{deleted}")
    notif = await context.bot.send_message(chat.id, f"🗑️ Удалено ~{deleted} сообщений.")
    _jq(context, lambda ctx: safe_delete(notif), 5)


# ══════════════════════════════════════════════════════
#  ЗАЩИТА ЧАТА
# ══════════════════════════════════════════════════════


@mod_access
async def cmd_slowmode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not context.args:
        await update.message.reply_text(
            "Использование: /slowmode [секунды] (0 = выкл)\n"
            "Допустимые: 0, 10, 30, 60, 300, 600, 900, 3600, 21600, 86400"
        )
        return
    try:
        delay = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Укажите число секунд.")
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setChatSlowModeDelay",
                json={"chat_id": chat.id, "slow_mode_delay": delay}
            )
        data = resp.json()
        if data.get("ok"):
            await update.message.reply_text(f"🐢 Slowmode: {'выключен' if delay == 0 else f'{delay}с'}")
        else:
            await update.message.reply_text(f"❌ {data.get('description', 'Ошибка API')}")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")


@mod_access
async def cmd_lockdown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat; user = update.effective_user
    duration = 600
    if context.args:
        duration = parse_time_arg(context.args[0]) or duration

    lockdown_active[chat.id] = _ts() + duration
    await log_action(chat.id, "manual_lockdown", 0, "SYSTEM", user.id, format_duration(duration))

    try:
        await context.bot.set_chat_permissions(chat.id, ChatPermissions(
            can_send_messages=False, can_send_polls=False, can_send_other_messages=False
        ))
    except Exception:
        pass

    await update.message.reply_text(
        f"🔒 <b>LOCKDOWN</b> на {format_duration(duration)}!\nВсе входящие будут кикнуты.",
        parse_mode=ParseMode.HTML
    )
    await notify_owner(context, chat.id,
        f"🔒 <b>Lockdown</b> <code>{chat.id}</code>\n"
        f"Мод: {user_mention(user)}\nДлительность: {format_duration(duration)}"
    )

    async def _auto_unlock(ctx: ContextTypes.DEFAULT_TYPE):
        lockdown_active.pop(chat.id, None)
        try:
            await ctx.bot.set_chat_permissions(chat.id, ChatPermissions(
                can_send_messages=True, can_send_polls=True,
                can_send_other_messages=True, can_add_web_page_previews=True,
                can_invite_users=True
            ))
            await ctx.bot.send_message(chat.id, "🔓 Lockdown снят.")
        except Exception:
            pass

    _jq(context, _auto_unlock, duration, name=f"unlock_{chat.id}")


@mod_access
async def cmd_unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    lockdown_active.pop(chat.id, None)
    if context.job_queue:
        for job in context.job_queue.get_jobs_by_name(f"unlock_{chat.id}"):
            job.schedule_removal()
    try:
        await context.bot.set_chat_permissions(chat.id, ChatPermissions(
            can_send_messages=True, can_send_polls=True,
            can_send_other_messages=True, can_add_web_page_previews=True,
            can_invite_users=True
        ))
    except Exception:
        pass
    await update.message.reply_text("🔓 Lockdown снят.")


# ══════════════════════════════════════════════════════
#  НАСТРОЙКИ ЧАТА
# ══════════════════════════════════════════════════════


@mod_access
async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    s    = await get_chat_settings(chat.id)
    yn   = lambda k, d=True: "✅" if s.get(k, d) else "❌"
    text = (
        f"⚙️ <b>Настройки: {_esc(chat.title or '')}</b>\n\n"
        f"{yn('antiflood')}      Анти-флуд\n"
        f"{yn('antispam')}       Анти-спам\n"
        f"{yn('antiduplicate')}  Анти-дубли\n"
        f"{yn('antilinks',False)} Анти-ссылки\n"
        f"{yn('antiforward',False)} Анти-форвард\n"
        f"{yn('captcha')}       Капча на вход\n"
        f"{yn('antiraid')}      Анти-рейд\n\n"
        f"Изменить: <code>/set [параметр] on|off</code>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


@mod_access
async def cmd_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat   = update.effective_chat
    valid  = ["antiflood","antispam","antiduplicate","antilinks","antiforward","captcha","antiraid"]
    if len(context.args) < 2:
        await update.message.reply_text(f"Использование: /set [параметр] on|off\nПараметры: {', '.join(valid)}")
        return
    key = context.args[0].lower(); val = context.args[1].lower()
    if key not in valid:
        await update.message.reply_text(f"Неверный параметр.\nДоступные: {', '.join(valid)}")
        return
    if val not in ["on","off","1","0","true","false"]:
        await update.message.reply_text("Значение: on или off")
        return
    value = val in ["on","1","true"]
    await set_chat_setting(chat.id, key, value)
    await update.message.reply_text(f"✅ {key} = {'on ✅' if value else 'off ❌'}")


@mod_access
async def cmd_setwelcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not context.args:
        await update.message.reply_text("Использование: /setwelcome [текст]\nПеременные: {user}")
        return
    await set_chat_setting(chat.id, "welcome_text", " ".join(context.args))
    await update.message.reply_text(f"✅ Приветствие сохранено:\n{' '.join(context.args)}")


@mod_access
async def cmd_addfilter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat; user = update.effective_user
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /addfilter [слово] [delete|warn|mute|ban]")
        return
    word = context.args[0].lower(); action = context.args[1].lower()
    if action not in ["delete","warn","mute","ban"]:
        await update.message.reply_text("Действие: delete, warn, mute или ban")
        return
    await add_word_filter(chat.id, word, action, user.id)
    await update.message.reply_text(f"✅ Фильтр: <code>{_esc(word)}</code> → {action}", parse_mode=ParseMode.HTML)

@mod_access
async def cmd_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    fl   = await get_word_filters(chat.id)
    if not fl:
        await update.message.reply_text("Фильтры слов не настроены.")
        return
    lines = ["📝 <b>Фильтры слов:</b>"]
    for f_id, word, action in fl:
        lines.append(f"#{f_id} | <code>{_esc(word)}</code> → {action}")
    lines.append("\nУдалить: /delfilter [id]")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@mod_access
async def cmd_delfilter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not context.args:
        await update.message.reply_text("Использование: /delfilter [id]")
        return
    try:
        f_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Неверный ID.")
        return
    await remove_word_filter(chat.id, f_id)
    await update.message.reply_text(f"✅ Фильтр #{f_id} удалён.")


@mod_access
async def cmd_addwl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat; user = update.effective_user
    if not context.args:
        await update.message.reply_text("Использование: /addwl [домен]\nПример: /addwl youtube.com")
        return
    domain = context.args[0].lower().replace("https://","").replace("http://","").split("/")[0]
    await add_link_whitelist(chat.id, domain, user.id)
    await update.message.reply_text(f"✅ <code>{_esc(domain)}</code> добавлен в whitelist.", parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════
#  ИНФОРМАЦИЯ
# ══════════════════════════════════════════════════════


@mod_access
async def cmd_userinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    target = extract_user_from_reply(update)

    if not target:
        if context.args:
            try:
                tid = int(context.args[0])
            except ValueError:
                await update.message.reply_text("Ответьте на сообщение или: /userinfo [id]")
                return
        else:
            await update.message.reply_text("Ответьте на сообщение или: /userinfo [id]")
            return
        tid_name = f"<code>{tid}</code>"
        full_name = None
    else:
        tid = target.id; full_name = target.full_name; tid_name = user_mention(target)

    warns       = await get_warnings(chat.id, tid)
    is_banned_f = await is_banned(chat.id, tid)
    is_shadow   = tid in shadowbanned.get(chat.id, set())
    mute_until  = mute_tracker.get(chat.id, {}).get(tid, 0)
    is_muted    = mute_until > _ts()

    text = f"👤 <b>Пользователь</b>\n\nID: <code>{tid}</code>\n"
    if full_name:
        text += f"Имя: {user_mention(target)}\nUsername: @{target.username or '—'}\n"
    text += (
        f"\n⚠️ Предупреждений: {len(warns)}/{WARNS_LIMIT}\n"
        f"🔇 Мут: {'до ' + _until_dt(int(mute_until)).strftime('%H:%M %d.%m') if is_muted else 'нет'}\n"
        f"🔨 Бан: {'да' if is_banned_f else 'нет'}\n"
        f"👻 Shadowban: {'да (/unshadowban ' + str(tid) + ')' if is_shadow else 'нет'}\n"
    )
    if warns:
        text += "\n<b>Предупреждения:</b>\n"
        for reason, issued_at in warns:
            text += f"• {issued_at}: {_esc(reason)}\n"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


@mod_access
async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat  = update.effective_chat
    limit = 10
    if context.args:
        try: limit = min(int(context.args[0]), 50)
        except ValueError: pass

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT action_type, target_username, performed_by, reason, created_at "
            "FROM action_logs WHERE chat_id=? ORDER BY created_at DESC LIMIT ?",
            (chat.id, limit)
        ) as c:
            rows = await c.fetchall()

    if not rows:
        await update.message.reply_text("Логи пусты.")
        return
    lines = [f"📋 <b>Последние {len(rows)} действий:</b>"]
    for action, target, by, reason, at in rows:
        lines.append(f"• [{at}] <b>{action}</b> → {_esc(target or '—')} | {_esc(reason or '—')}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@mod_access
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM action_logs WHERE chat_id=?", (chat.id,)) as c:
            total_actions = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM spam_stats WHERE chat_id=?", (chat.id,)) as c:
            total_spam = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM warnings WHERE chat_id=?", (chat.id,)) as c:
            total_warns = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM bans WHERE chat_id=?", (chat.id,)) as c:
            total_bans = (await c.fetchone())[0]
        async with db.execute(
            "SELECT spam_type, COUNT(*) cnt FROM spam_stats WHERE chat_id=? GROUP BY spam_type ORDER BY cnt DESC LIMIT 5",
            (chat.id,)
        ) as c:
            spam_types = await c.fetchall()

    text = (
        f"📊 <b>Статистика: {_esc(chat.title or '')}</b>\n\n"
        f"Всего действий:   {total_actions}\n"
        f"Спам-инцидентов: {total_spam}\n"
        f"Предупреждений:  {total_warns}\n"
        f"Банов:           {total_bans}\n"
    )
    if spam_types:
        text += "\n<b>Топ типов спама:</b>\n"
        for st, cnt in spam_types:
            text += f"• {_esc(st)}: {cnt}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════
#  СПРАВКА
# ══════════════════════════════════════════════════════

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    is_mod = await can_moderate(context, chat.id if chat else 0, user.id)

    if not is_mod:
        await update.message.reply_text(
            "🛡️ <b>Guard Bot</b>\nБот для защиты чатов от спама и рейдов.",
            parse_mode=ParseMode.HTML
        )
        return

    text = (
        "🛡️ <b>Guard Bot v2.1</b>\n\n"
        "<b>🔨 Модерация:</b>\n"
        "/ban — бан (ответ или /ban [id] [причина])\n"
        "/unban [id] — разбан\n"
        "/kick — кик\n"
        "/mute [время] [причина] — мут (10m, 2h, 3d)\n"
        "/unmute — снять мут\n"
        "/warn [причина] — предупреждение\n"
        "/unwarn — сброс предупреждений\n"
        "/shadowban — теневой бан (ответ или /shadowban [id])\n"
        "/unshadowban — снять теневой бан (ответ или /unshadowban [id])\n"
        "/purge [n] — удалить n сообщений\n\n"
        "<b>🔒 Защита:</b>\n"
        "/lockdown [время] — lockdown чата\n"
        "/unlock — снять lockdown\n"
        "/slowmode [сек] — медленный режим\n\n"
        "<b>⚙️ Настройки:</b>\n"
        "/settings — показать настройки\n"
        "/set [параметр] [on|off]\n"
        "/setwelcome [текст] — приветствие ({user})\n"
        "/addfilter [слово] [delete|warn|mute|ban]\n"
        "/filters | /delfilter [id]\n"
        "/addwl [домен] — whitelist ссылок\n\n"
        "<b>📊 Информация:</b>\n"
        "/userinfo (ответ или /userinfo [id])\n"
        "/logs [n] | /stats\n\n"
        "<b>⚡ Параметры /set:</b>\n"
        "<code>antiflood antispam antiduplicate\n"
        "antilinks antiforward captcha antiraid</code>\n\n"
        "<b>ℹ️ Доступ к командам:</b>\n"
        "Telegram-администраторы чата + персонал бота"
    )
    if user.id == OWNER_ID:
        text += (
            "\n\n<b>👑 Системные (только owner бота):</b>\n"
            "/addstaff [id] [trusted|moderator] [username]\n"
            "/removestaff [id] | /liststaff\n"
            "/authchat | /deauthchat"
        )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════
#  КОНТРОЛЬ ДОБАВЛЕНИЯ БОТА
# ══════════════════════════════════════════════════════

async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if not result: return
    chat       = result.chat
    new_status = result.new_chat_member.status

    if new_status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR]:
        if not await is_authorized_chat(chat.id):
            logger.warning(f"Бот добавлен в неавторизованный чат {chat.id} ({chat.title})")
            try:
                await context.bot.send_message(
                    chat.id,
                    "⛔ Этот бот не авторизован для данного чата.\n"
                    "Обратитесь к администратору системы."
                )
                await asyncio.sleep(2)
                await context.bot.leave_chat(chat.id)
            except Exception:
                pass
            try:
                await context.bot.send_message(
                    OWNER_ID,
                    f"⚠️ <b>Попытка добавить бота в неавторизованный чат!</b>\n"
                    f"Чат: <b>{_esc(chat.title or '')}</b> (<code>{chat.id}</code>)\n"
                    f"Тип: {chat.type}\n"
                    f"Добавил: <code>{result.from_user.id}</code> @{result.from_user.username or '—'}",
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass


# ══════════════════════════════════════════════════════
#  ОШИБКИ
# ══════════════════════════════════════════════════════

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = context.error
    if isinstance(err, Forbidden):
        logger.warning(f"Forbidden: {err}")
    elif isinstance(err, BadRequest):
        logger.warning(f"BadRequest: {err}")
    else:
        logger.error(f"Ошибка: {err}", exc_info=True)


# ══════════════════════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════════════════════

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не задан в .env!")
        return
    if not OWNER_ID:
        logger.error("OWNER_ID не задан в .env!")
        return

    async def post_init(app: Application):
        await init_db()
        logger.info(f"Guard Bot v2.1 запущен. Owner: {OWNER_ID}")
        if app.job_queue is None:
            logger.warning(
                "JobQueue недоступен! Таймауты капчи и авто-снятие lockdown не будут работать.\n"
                "Установите: pip install 'python-telegram-bot[job-queue]'"
            )
        try:
            await app.bot.send_message(
                OWNER_ID,
                "🟢 <b>Guard Bot v2.1 запущен</b>\n\n"
                "Система защиты активирована.\n/help — команды.",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Системные
    app.add_handler(CommandHandler("start",       cmd_start))
    app.add_handler(CommandHandler("help",        cmd_help))
    app.add_handler(CommandHandler("addstaff",    cmd_addstaff))
    app.add_handler(CommandHandler("removestaff", cmd_removestaff))
    app.add_handler(CommandHandler("liststaff",   cmd_liststaff))
    app.add_handler(CommandHandler("authchat",    cmd_authchat))
    app.add_handler(CommandHandler("deauthchat",  cmd_deauthchat))
    # Модерация
    app.add_handler(CommandHandler("ban",         cmd_ban))
    app.add_handler(CommandHandler("unban",       cmd_unban))
    app.add_handler(CommandHandler("kick",        cmd_kick))
    app.add_handler(CommandHandler("mute",        cmd_mute))
    app.add_handler(CommandHandler("unmute",      cmd_unmute))
    app.add_handler(CommandHandler("warn",        cmd_warn))
    app.add_handler(CommandHandler("unwarn",      cmd_unwarn))
    app.add_handler(CommandHandler("shadowban",   cmd_shadowban))
    app.add_handler(CommandHandler("unshadowban", cmd_unshadowban))
    app.add_handler(CommandHandler("purge",       cmd_purge))
    # Защита
    app.add_handler(CommandHandler("lockdown",    cmd_lockdown))
    app.add_handler(CommandHandler("unlock",      cmd_unlock))
    app.add_handler(CommandHandler("slowmode",    cmd_slowmode))
    # Настройки
    app.add_handler(CommandHandler("settings",    cmd_settings))
    app.add_handler(CommandHandler("set",         cmd_set))
    app.add_handler(CommandHandler("setwelcome",  cmd_setwelcome))
    app.add_handler(CommandHandler("addfilter",   cmd_addfilter))
    app.add_handler(CommandHandler("filters",     cmd_filters))
    app.add_handler(CommandHandler("delfilter",   cmd_delfilter))
    app.add_handler(CommandHandler("addwl",       cmd_addwl))
    # Информация
    app.add_handler(CommandHandler("userinfo",    cmd_userinfo))
    app.add_handler(CommandHandler("logs",        cmd_logs))
    app.add_handler(CommandHandler("stats",       cmd_stats))
    # Сообщения
    app.add_handler(MessageHandler(
        filters.TEXT | filters.CAPTION | filters.FORWARDED,
        handle_message
    ))
    # Новые участники
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_member))
    # Капча
    app.add_handler(CallbackQueryHandler(captcha_callback, pattern=r"^captcha:"))
    # Статус бота
    app.add_handler(ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    # Ошибки
    app.add_error_handler(error_handler)

    logger.info("Запуск polling...")
    app.run_polling(drop_pending_updates=True)

from telegram.ext import TypeHandler

async def debug_all(update, context):
    print(f"--- ПРИШЕЛ АПДЕЙТ ---")
    if update.message:
        print(f"Текст: {update.message.text}")
        print(f"От кого: {update.effective_user.id}")
        print(f"Тип чата: {update.effective_chat.type}")
    else:
        print(f"Тип апдейта: {type(update)}")

# Добавь это ПЕРВЫМ среди всех handlers
app.add_handler(TypeHandler(Update, debug_all), group=-1)


if __name__ == "__main__":
    main()
