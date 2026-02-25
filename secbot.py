"""
╔══════════════════════════════════════════════════════════════════════╗
║           ADVANCED TELEGRAM BOT - GUARD SYSTEM v2.0                 ║
║     Расширенная модерация, анти-спам, безопасность, логирование     ║
╚══════════════════════════════════════════════════════════════════════╝

УСТАНОВКА:
    pip install python-telegram-bot==20.7 aiosqlite python-dotenv

НАСТРОЙКА:
    Создайте файл .env:
        BOT_TOKEN=ваш_токен
        OWNER_ID=ваш_telegram_id

ЗАПУСК:
    python bot.py
"""

import asyncio
import logging
import re
import time
import json
import hashlib
import random
import string
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import Optional, Dict, List, Tuple
from enum import Enum

import aiosqlite
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

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
DB_PATH = "guard_bot.db"

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
#  ENUMS И КОНСТАНТЫ
# ══════════════════════════════════════════════════════

class Role(str, Enum):
    OWNER = "owner"
    TRUSTED = "trusted"
    MODERATOR = "moderator"

class PunishmentType(str, Enum):
    WARN = "warn"
    MUTE = "mute"
    KICK = "kick"
    BAN = "ban"
    SHADOWBAN = "shadowban"

class ChatCategory(str, Enum):
    CHANNEL = "channel"
    GROUP = "group"
    SUPERGROUP = "supergroup"

# Лимиты анти-флуда
FLOOD_MESSAGES = 5        # сообщений
FLOOD_INTERVAL = 5        # за секунд
FLOOD_MUTE_DURATION = 300 # мут 5 минут

# Авто-бан после N предупреждений
WARNS_LIMIT = 3

# Капча: время на ответ
CAPTCHA_TIMEOUT = 90      # секунд

# Максимум одинаковых сообщений подряд (анти-копипаст)
DUPLICATE_LIMIT = 3

# Доверенный домен whitelist для ссылок
LINK_WHITELIST = ["t.me", "telegram.org", "telegram.me"]

# Паттерны SPAM
SPAM_PATTERNS = [
    r"(?i)(заработ|earn|crypto|крипто|invest|инвест).{0,30}(click|жми|подпис|profit|профит)",
    r"(?i)(быстр|quick).{0,20}(деньг|money|заработ|earn)",
    r"(?i)casino|казино|ставк|букмекер|1xbet|mostbet|melbet",
    r"(?i)(подписчик|follower|subscriber).{0,20}(купить|buy|продам|sell)",
    r"(?i)(накрут|boost|прокач).{0,20}(подписчик|follower|like|лайк)",
    r"@[A-Za-z0-9_]{5,32}\s*(заработ|подпис|casino|crypto)",
    r"(?i)adult|18\+|только.{0,5}взросл|sex|секс",
    r"(?i)(пиши|write|dm|пм|pm).{0,15}(продам|купл|offer|предлаг)",
]

SPAM_COMPILED = [re.compile(p) for p in SPAM_PATTERNS]

# Анти-рейд: если за SHORT время вошло много новых юзеров — триггер
RAID_JOIN_COUNT = 10
RAID_JOIN_WINDOW = 30  # секунд
RAID_LOCKDOWN_DURATION = 300  # секунд


# ══════════════════════════════════════════════════════
#  IN-MEMORY ТРЕКЕРЫ
# ══════════════════════════════════════════════════════

# flood: {chat_id: {user_id: deque([timestamp, ...])}}
flood_tracker: Dict[int, Dict[int, deque]] = defaultdict(lambda: defaultdict(deque))

# Дубли: {chat_id: {user_id: (last_text, count)}}
duplicate_tracker: Dict[int, Dict[int, Tuple[str, int]]] = defaultdict(dict)

# Капча: {(chat_id, user_id): {"answer": int, "msg_id": int, "time": float}}
captcha_pending: Dict[Tuple[int, int], dict] = {}

# Рейд: {chat_id: deque([timestamp, ...])}
raid_tracker: Dict[int, deque] = defaultdict(deque)

# Lockdown: {chat_id: timestamp_until}
lockdown_active: Dict[int, float] = {}

# Shadowban (не отвечаем, тихо удаляем): {chat_id: {user_id}}
shadowbanned: Dict[int, set] = defaultdict(set)

# Temporary mutes in memory: {chat_id: {user_id: until_timestamp}}
mute_tracker: Dict[int, Dict[int, float]] = defaultdict(dict)


# ══════════════════════════════════════════════════════
#  БАЗА ДАННЫХ
# ══════════════════════════════════════════════════════

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        -- Авторизованные чаты/каналы
        CREATE TABLE IF NOT EXISTS authorized_chats (
            chat_id INTEGER PRIMARY KEY,
            chat_title TEXT,
            chat_type TEXT,
            added_by INTEGER,
            added_at TEXT,
            project_owner_id INTEGER,  -- кому слать логи
            settings TEXT DEFAULT '{}'  -- JSON настройки чата
        );

        -- Персонал (trusted/moderators)
        CREATE TABLE IF NOT EXISTS staff (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            role TEXT,
            added_by INTEGER,
            added_at TEXT
        );

        -- Предупреждения
        CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            reason TEXT,
            issued_by INTEGER,
            issued_at TEXT
        );

        -- Баны (постоянные)
        CREATE TABLE IF NOT EXISTS bans (
            chat_id INTEGER,
            user_id INTEGER,
            reason TEXT,
            banned_by INTEGER,
            banned_at TEXT,
            PRIMARY KEY (chat_id, user_id)
        );

        -- Муты
        CREATE TABLE IF NOT EXISTS mutes (
            chat_id INTEGER,
            user_id INTEGER,
            until TEXT,
            reason TEXT,
            muted_by INTEGER,
            PRIMARY KEY (chat_id, user_id)
        );

        -- Логи действий
        CREATE TABLE IF NOT EXISTS action_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            action_type TEXT,
            target_user_id INTEGER,
            target_username TEXT,
            performed_by INTEGER,
            reason TEXT,
            details TEXT,
            created_at TEXT
        );

        -- Фильтры слов для чата
        CREATE TABLE IF NOT EXISTS word_filters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            word TEXT,
            action TEXT DEFAULT 'delete',  -- delete | warn | mute | ban
            added_by INTEGER
        );

        -- Белый список ссылок
        CREATE TABLE IF NOT EXISTS link_whitelist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            domain TEXT,
            added_by INTEGER
        );

        -- Статистика спама
        CREATE TABLE IF NOT EXISTS spam_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            spam_type TEXT,
            detected_at TEXT,
            message_text TEXT
        );
        """)
        await db.commit()


async def is_authorized_chat(chat_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM authorized_chats WHERE chat_id=?", (chat_id,)
        ) as cur:
            return await cur.fetchone() is not None


async def authorize_chat(chat_id: int, title: str, chat_type: str, added_by: int, project_owner_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO authorized_chats
               (chat_id, chat_title, chat_type, added_by, added_at, project_owner_id)
               VALUES (?,?,?,?,?,?)""",
            (chat_id, title, chat_type, added_by, _now(), project_owner_id)
        )
        await db.commit()


async def deauthorize_chat(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM authorized_chats WHERE chat_id=?", (chat_id,))
        await db.commit()


async def get_chat_settings(chat_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT settings FROM authorized_chats WHERE chat_id=?", (chat_id,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                try:
                    return json.loads(row[0] or "{}")
                except Exception:
                    return {}
    return {}


async def set_chat_setting(chat_id: int, key: str, value):
    settings = await get_chat_settings(chat_id)
    settings[key] = value
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE authorized_chats SET settings=? WHERE chat_id=?",
            (json.dumps(settings), chat_id)
        )
        await db.commit()


async def get_chat_project_owner(chat_id: int) -> Optional[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT project_owner_id FROM authorized_chats WHERE chat_id=?", (chat_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def is_staff(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM staff WHERE user_id=?", (user_id,)
        ) as cur:
            return await cur.fetchone() is not None


async def get_staff_role(user_id: int) -> Optional[str]:
    if user_id == OWNER_ID:
        return Role.OWNER
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT role FROM staff WHERE user_id=?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
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
        async with db.execute(
            "SELECT user_id,username,role,added_by,added_at FROM staff ORDER BY role"
        ) as cur:
            return await cur.fetchall()


async def add_warning(chat_id: int, user_id: int, reason: str, issued_by: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO warnings (chat_id,user_id,reason,issued_by,issued_at) VALUES (?,?,?,?,?)",
            (chat_id, user_id, reason, issued_by, _now())
        )
        await db.commit()
        async with db.execute(
            "SELECT COUNT(*) FROM warnings WHERE chat_id=? AND user_id=?",
            (chat_id, user_id)
        ) as cur:
            row = await cur.fetchone()
            return row[0]


async def get_warnings(chat_id: int, user_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT reason,issued_at FROM warnings WHERE chat_id=? AND user_id=? ORDER BY issued_at",
            (chat_id, user_id)
        ) as cur:
            return await cur.fetchall()


async def clear_warnings(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM warnings WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        )
        await db.commit()


async def add_ban(chat_id: int, user_id: int, reason: str, banned_by: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO bans (chat_id,user_id,reason,banned_by,banned_at) VALUES (?,?,?,?,?)",
            (chat_id, user_id, reason, banned_by, _now())
        )
        await db.commit()


async def remove_ban(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM bans WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        )
        await db.commit()


async def is_banned(chat_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM bans WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        ) as cur:
            return await cur.fetchone() is not None


async def log_action(chat_id: int, action_type: str, target_id: int,
                     target_name: str, by_id: int, reason: str = "", details: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO action_logs
               (chat_id,action_type,target_user_id,target_username,performed_by,reason,details,created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (chat_id, action_type, target_id, target_name, by_id, reason, details, _now())
        )
        await db.commit()


async def get_word_filters(chat_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id,word,action FROM word_filters WHERE chat_id=?", (chat_id,)
        ) as cur:
            return await cur.fetchall()


async def add_word_filter(chat_id: int, word: str, action: str, added_by: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO word_filters (chat_id,word,action,added_by) VALUES (?,?,?,?)",
            (chat_id, word.lower(), action, added_by)
        )
        await db.commit()


async def remove_word_filter(chat_id: int, filter_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM word_filters WHERE id=? AND chat_id=?", (filter_id, chat_id)
        )
        await db.commit()


async def get_chat_link_whitelist(chat_id: int) -> List[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT domain FROM link_whitelist WHERE chat_id=?", (chat_id,)
        ) as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]


async def add_link_whitelist(chat_id: int, domain: str, added_by: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO link_whitelist (chat_id,domain,added_by) VALUES (?,?,?)",
            (chat_id, domain.lower(), added_by)
        )
        await db.commit()


async def log_spam(chat_id: int, user_id: int, spam_type: str, text: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO spam_stats (chat_id,user_id,spam_type,detected_at,message_text) VALUES (?,?,?,?,?)",
            (chat_id, user_id, spam_type, _now(), text[:500])
        )
        await db.commit()


# ══════════════════════════════════════════════════════
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ══════════════════════════════════════════════════════

def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _ts() -> float:
    return time.time()


def user_mention(user: User) -> str:
    name = user.full_name or f"User{user.id}"
    return f'<a href="tg://user?id={user.id}">{name}</a>'


def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}с"
    elif seconds < 3600:
        return f"{seconds // 60}м"
    elif seconds < 86400:
        return f"{seconds // 3600}ч"
    else:
        return f"{seconds // 86400}д"


def generate_captcha() -> Tuple[str, int]:
    a = random.randint(1, 20)
    b = random.randint(1, 20)
    op = random.choice(["+", "-", "×"])
    if op == "+":
        answer = a + b
    elif op == "-":
        answer = a - b
    else:
        answer = a * b
    question = f"{a} {op} {b} = ?"
    return question, answer


def generate_invite_code(length=12) -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def extract_user_from_reply(update: Update) -> Optional[User]:
    if update.message and update.message.reply_to_message:
        return update.message.reply_to_message.from_user
    return None


def parse_time_arg(arg: str) -> int:
    """Парсит '10m', '2h', '3d' -> секунды"""
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if not arg:
        return 0
    if arg[-1] in units:
        try:
            return int(arg[:-1]) * units[arg[-1]]
        except ValueError:
            pass
    try:
        return int(arg) * 60  # по умолчанию минуты
    except ValueError:
        return 0


async def safe_delete(msg: Message):
    try:
        await msg.delete()
    except (TelegramError, BadRequest):
        pass


async def safe_ban(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, until: int = 0):
    try:
        until_dt = datetime.utcfromtimestamp(until) if until else None
        await context.bot.ban_chat_member(chat_id, user_id, until_date=until_dt)
        return True
    except (TelegramError, BadRequest) as e:
        logger.warning(f"Ban failed {user_id} in {chat_id}: {e}")
        return False


async def safe_mute(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, until: int = 0):
    try:
        perms = ChatPermissions(
            can_send_messages=False,
            can_send_polls=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False
        )
        until_dt = datetime.utcfromtimestamp(until) if until else None
        await context.bot.restrict_chat_member(chat_id, user_id, perms, until_date=until_dt)
        return True
    except (TelegramError, BadRequest) as e:
        logger.warning(f"Mute failed {user_id} in {chat_id}: {e}")
        return False


async def safe_unmute(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int):
    try:
        perms = ChatPermissions(
            can_send_messages=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_change_info=False,
            can_invite_users=True,
            can_pin_messages=False
        )
        await context.bot.restrict_chat_member(chat_id, user_id, perms)
        return True
    except (TelegramError, BadRequest):
        return False


async def notify_owner(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str):
    """Отправляет уведомление владельцу проекта"""
    owner_id = await get_chat_project_owner(chat_id)
    if owner_id:
        try:
            await context.bot.send_message(owner_id, text, parse_mode=ParseMode.HTML)
        except (TelegramError, Forbidden):
            pass


# ══════════════════════════════════════════════════════
#  ДЕКОРАТОРЫ-ПРОВЕРКИ
# ══════════════════════════════════════════════════════

def owner_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user or user.id != OWNER_ID:
            await update.message.reply_text("🚫 Только для владельца бота.")
            return
        return await func(update, context)
    wrapper.__name__ = func.__name__
    return wrapper


def staff_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user or not await is_staff(user.id):
            await update.message.reply_text("🚫 Нет доступа.")
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


async def check_is_admin(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]
    except TelegramError:
        return False


# ══════════════════════════════════════════════════════
#  ОБНАРУЖЕНИЕ СПАМА
# ══════════════════════════════════════════════════════

def check_spam_patterns(text: str) -> Optional[str]:
    for i, pattern in enumerate(SPAM_COMPILED):
        if pattern.search(text):
            return f"pattern_{i}"
    return None


def check_flood(chat_id: int, user_id: int) -> bool:
    """True если флуд обнаружен"""
    now = _ts()
    dq = flood_tracker[chat_id][user_id]
    dq.append(now)
    # Удаляем старые
    while dq and dq[0] < now - FLOOD_INTERVAL:
        dq.popleft()
    return len(dq) >= FLOOD_MESSAGES


def check_duplicate(chat_id: int, user_id: int, text: str) -> bool:
    """True если сообщение дублируется слишком часто"""
    key = (chat_id, user_id)
    prev = duplicate_tracker[chat_id].get(user_id)
    if prev:
        last_text, count = prev
        if last_text == text:
            count += 1
            duplicate_tracker[chat_id][user_id] = (text, count)
            return count >= DUPLICATE_LIMIT
    duplicate_tracker[chat_id][user_id] = (text, 1)
    return False


def check_links(text: str, chat_whitelist: List[str]) -> bool:
    """True если найдены запрещённые ссылки"""
    url_pattern = re.compile(
        r'(https?://|t\.me/|telegram\.me/|@[A-Za-z0-9_]{5,})'
        r'([A-Za-z0-9\-._~:/?#\[\]@!$&\'()*+,;=%]*)',
        re.IGNORECASE
    )
    all_allowed = LINK_WHITELIST + chat_whitelist
    for match in url_pattern.finditer(text):
        url = match.group(0).lower()
        allowed = any(domain in url for domain in all_allowed)
        if not allowed:
            return True
    return False


def check_raid(chat_id: int) -> bool:
    """True если детектирован рейд"""
    now = _ts()
    dq = raid_tracker[chat_id]
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

    # Мутим до прохождения капчи
    await safe_mute(context, chat_id, user.id)

    text = (
        f"👋 Добро пожаловать, {user_mention(user)}!\n\n"
        f"🔐 Для входа в чат решите задачу:\n"
        f"<b>{question}</b>\n\n"
        f"⏳ У вас {CAPTCHA_TIMEOUT} секунд."
    )

    buttons = []
    # Правильный ответ + 3 ложных
    variants = {answer}
    while len(variants) < 4:
        variants.add(answer + random.randint(-10, 10))
    variants = list(variants)
    random.shuffle(variants)

    row = [
        InlineKeyboardButton(str(v), callback_data=f"captcha:{user.id}:{v}:{answer}")
        for v in variants
    ]
    markup = InlineKeyboardMarkup([row])

    msg = await context.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_markup=markup)
    captcha_pending[key] = {"answer": answer, "msg_id": msg.message_id, "time": _ts()}

    # Авто-кик если не ответил
    context.job_queue.run_once(
        _captcha_timeout, CAPTCHA_TIMEOUT,
        data={"chat_id": chat_id, "user_id": user.id, "msg_id": msg.message_id},
        name=f"captcha_{chat_id}_{user.id}"
    )


async def _captcha_timeout(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    chat_id, user_id, msg_id = data["chat_id"], data["user_id"], data["msg_id"]
    key = (chat_id, user_id)
    if key in captcha_pending:
        del captcha_pending[key]
        await safe_ban(context, chat_id, user_id, until=int(_ts() + 600))
        try:
            await context.bot.delete_message(chat_id, msg_id)
        except Exception:
            pass
        await log_action(chat_id, "captcha_fail_kick", user_id, "unknown", context.bot.id, "Не прошёл капчу")


# ══════════════════════════════════════════════════════
#  ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ (МОДЕРАЦИЯ)
# ══════════════════════════════════════════════════════

@authorized_chat_only
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.edited_message
    if not msg:
        return

    chat = update.effective_chat
    user = update.effective_user

    if not user or not chat:
        return

    chat_id = chat.id
    user_id = user.id

    # Боты пропускаем (кроме проверки на спам-боты - можно расширить)
    if user.is_bot:
        return

    # Игнорируем стафф
    if await is_staff(user_id):
        return

    # Shadowban — тихо удаляем
    if user_id in shadowbanned.get(chat_id, set()):
        await safe_delete(msg)
        return

    settings = await get_chat_settings(chat_id)
    text = msg.text or msg.caption or ""

    # ── 1. Флуд ──
    if settings.get("antiflood", True) and check_flood(chat_id, user_id):
        await safe_delete(msg)
        until = int(_ts() + FLOOD_MUTE_DURATION)
        await safe_mute(context, chat_id, user_id, until)
        mute_tracker[chat_id][user_id] = until
        warn_count = await add_warning(chat_id, user_id, "Флуд", context.bot.id)
        await log_action(chat_id, "mute_flood", user_id, user.full_name, context.bot.id, "Флуд")
        await log_spam(chat_id, user_id, "flood", text[:100])

        notif = await context.bot.send_message(
            chat_id,
            f"🌊 {user_mention(user)} замучен на {format_duration(FLOOD_MUTE_DURATION)} за флуд. "
            f"[⚠️ {warn_count}/{WARNS_LIMIT}]",
            parse_mode=ParseMode.HTML
        )
        await notify_owner(context, chat_id,
            f"🌊 <b>Флуд</b> в чате <code>{chat_id}</code>\n"
            f"Пользователь: {user_mention(user)} (<code>{user_id}</code>)\n"
            f"Мут: {format_duration(FLOOD_MUTE_DURATION)}"
        )
        context.job_queue.run_once(
            lambda ctx: safe_delete(notif), 15, name=f"del_notif_{notif.message_id}"
        )

        if warn_count >= WARNS_LIMIT:
            await _auto_ban(context, chat_id, user, "Превышен лимит предупреждений (флуд)")
        return

    # ── 2. Дубликаты ──
    if settings.get("antiduplicate", True) and text and check_duplicate(chat_id, user_id, text):
        await safe_delete(msg)
        warn_count = await add_warning(chat_id, user_id, "Копипаст/дубли", context.bot.id)
        await log_action(chat_id, "warn_duplicate", user_id, user.full_name, context.bot.id)
        notif = await context.bot.send_message(
            chat_id,
            f"♻️ {user_mention(user)}, не повторяй одно сообщение. [⚠️ {warn_count}/{WARNS_LIMIT}]",
            parse_mode=ParseMode.HTML
        )
        context.job_queue.run_once(lambda ctx: safe_delete(notif), 10)
        if warn_count >= WARNS_LIMIT:
            await _auto_ban(context, chat_id, user, "Превышен лимит предупреждений (дубли)")
        return

    # ── 3. Спам-паттерны ──
    if settings.get("antispam", True) and text:
        spam_type = check_spam_patterns(text)
        if spam_type:
            await safe_delete(msg)
            warn_count = await add_warning(chat_id, user_id, "Спам", context.bot.id)
            await log_action(chat_id, "warn_spam", user_id, user.full_name, context.bot.id, spam_type)
            await log_spam(chat_id, user_id, spam_type, text)
            notif = await context.bot.send_message(
                chat_id,
                f"🚫 {user_mention(user)}, спам удалён. [⚠️ {warn_count}/{WARNS_LIMIT}]",
                parse_mode=ParseMode.HTML
            )
            await notify_owner(context, chat_id,
                f"🚫 <b>Спам</b> в чате <code>{chat_id}</code>\n"
                f"Пользователь: {user_mention(user)}\n"
                f"Тип: <code>{spam_type}</code>\n"
                f"Текст: <code>{text[:200]}</code>"
            )
            context.job_queue.run_once(lambda ctx: safe_delete(notif), 12)
            if warn_count >= WARNS_LIMIT:
                await _auto_ban(context, chat_id, user, "Превышен лимит предупреждений (спам)")
            return

    # ── 4. Ссылки ──
    if settings.get("antilinks", False) and text:
        chat_wl = await get_chat_link_whitelist(chat_id)
        if check_links(text, chat_wl):
            # Проверяем, не стафф ли чата в Telegram
            if not await check_is_admin(context, chat_id, user_id):
                await safe_delete(msg)
                warn_count = await add_warning(chat_id, user_id, "Запрещённая ссылка", context.bot.id)
                await log_action(chat_id, "warn_link", user_id, user.full_name, context.bot.id)
                notif = await context.bot.send_message(
                    chat_id,
                    f"🔗 {user_mention(user)}, ссылки запрещены. [⚠️ {warn_count}/{WARNS_LIMIT}]",
                    parse_mode=ParseMode.HTML
                )
                context.job_queue.run_once(lambda ctx: safe_delete(notif), 10)
                if warn_count >= WARNS_LIMIT:
                    await _auto_ban(context, chat_id, user, "Запрещённые ссылки")
                return

    # ── 5. Фильтры слов ──
    if text:
        word_filters = await get_word_filters(chat_id)
        text_lower = text.lower()
        for f_id, word, action in word_filters:
            if word in text_lower:
                await safe_delete(msg)
                await log_action(chat_id, f"filter_{action}", user_id, user.full_name, context.bot.id, f"Слово: {word}")
                if action == "warn":
                    warn_count = await add_warning(chat_id, user_id, f"Запрещённое слово: {word}", context.bot.id)
                    notif = await context.bot.send_message(
                        chat_id,
                        f"⚠️ {user_mention(user)}, запрещённое слово. [⚠️ {warn_count}/{WARNS_LIMIT}]",
                        parse_mode=ParseMode.HTML
                    )
                    context.job_queue.run_once(lambda ctx: safe_delete(notif), 10)
                    if warn_count >= WARNS_LIMIT:
                        await _auto_ban(context, chat_id, user, "Превышен лимит предупреждений")
                elif action == "mute":
                    until = int(_ts() + 3600)
                    await safe_mute(context, chat_id, user_id, until)
                    notif = await context.bot.send_message(
                        chat_id,
                        f"🔇 {user_mention(user)} замучен на 1ч за нарушение фильтра.",
                        parse_mode=ParseMode.HTML
                    )
                    context.job_queue.run_once(lambda ctx: safe_delete(notif), 15)
                elif action == "ban":
                    await safe_ban(context, chat_id, user_id)
                    await add_ban(chat_id, user_id, f"Фильтр: {word}", context.bot.id)
                    await context.bot.send_message(
                        chat_id,
                        f"🔨 {user_mention(user)} заблокирован за нарушение фильтра.",
                        parse_mode=ParseMode.HTML
                    )
                return

    # ── 6. Анти-форвард (опционально) ──
    if settings.get("antiforward", False) and msg.forward_date:
        if not await check_is_admin(context, chat_id, user_id):
            await safe_delete(msg)
            notif = await context.bot.send_message(
                chat_id,
                f"📩 {user_mention(user)}, пересылка сообщений запрещена.",
                parse_mode=ParseMode.HTML
            )
            context.job_queue.run_once(lambda ctx: safe_delete(notif), 10)
            return


async def _auto_ban(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user: User, reason: str):
    await safe_ban(context, chat_id, user.id)
    await add_ban(chat_id, user.id, reason, context.bot.id)
    await clear_warnings(chat_id, user.id)
    await log_action(chat_id, "autoban", user.id, user.full_name, context.bot.id, reason)
    await context.bot.send_message(
        chat_id,
        f"🔨 {user_mention(user)} автоматически <b>заблокирован</b>: {reason}",
        parse_mode=ParseMode.HTML
    )
    await notify_owner(context, chat_id,
        f"🔨 <b>Авто-бан</b> в чате <code>{chat_id}</code>\n"
        f"Пользователь: {user_mention(user)} (<code>{user.id}</code>)\n"
        f"Причина: {reason}"
    )


# ══════════════════════════════════════════════════════
#  ОБРАБОТЧИК НОВЫХ УЧАСТНИКОВ
# ══════════════════════════════════════════════════════

@authorized_chat_only
async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.new_chat_members:
        return

    chat_id = msg.chat.id
    settings = await get_chat_settings(chat_id)

    for user in msg.new_chat_members:
        if user.is_bot:
            continue

        # Проверка рейда
        if settings.get("antiraid", True) and check_raid(chat_id):
            if chat_id not in lockdown_active or lockdown_active[chat_id] < _ts():
                lockdown_active[chat_id] = _ts() + RAID_LOCKDOWN_DURATION
                await log_action(chat_id, "raid_lockdown", 0, "SYSTEM", context.bot.id, "Рейд обнаружен")
                await context.bot.send_message(
                    chat_id,
                    f"🚨 <b>РЕЙД ОБНАРУЖЕН!</b>\n"
                    f"Чат заблокирован на {format_duration(RAID_LOCKDOWN_DURATION)}. "
                    f"Все вступающие будут кикнуты.",
                    parse_mode=ParseMode.HTML
                )
                await notify_owner(context, chat_id,
                    f"🚨 <b>РЕЙД!</b> Чат <code>{chat_id}</code>\n"
                    f"Lockdown на {format_duration(RAID_LOCKDOWN_DURATION)}"
                )

        # Если активен lockdown — баним входящих
        if chat_id in lockdown_active and lockdown_active[chat_id] > _ts():
            await safe_ban(context, chat_id, user.id, until=int(lockdown_active[chat_id]))
            await safe_delete(msg)
            continue

        # Капча
        if settings.get("captcha", True):
            await safe_delete(msg)
            await send_captcha(context, chat_id, user)
            await log_action(chat_id, "captcha_sent", user.id, user.full_name, context.bot.id)
        else:
            # Просто приветствие
            welcome = settings.get("welcome_text", "")
            if welcome:
                notif = await context.bot.send_message(
                    chat_id,
                    welcome.replace("{user}", user_mention(user)),
                    parse_mode=ParseMode.HTML
                )
                context.job_queue.run_once(lambda ctx: safe_delete(notif), 30)


# ══════════════════════════════════════════════════════
#  CALLBACK - КАПЧА
# ══════════════════════════════════════════════════════

async def captcha_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split(":")
    if len(data) != 4:
        return

    _, target_id, chosen, correct = data
    target_id = int(target_id)
    chosen = int(chosen)
    correct = int(correct)
    chat_id = query.message.chat.id

    # Только тот пользователь может нажать
    if query.from_user.id != target_id:
        await query.answer("Это не ваша капча!", show_alert=True)
        return

    key = (chat_id, target_id)
    if key not in captcha_pending:
        await query.answer("Капча устарела.", show_alert=True)
        return

    # Отменяем таймаут
    jobs = context.job_queue.get_jobs_by_name(f"captcha_{chat_id}_{target_id}")
    for job in jobs:
        job.schedule_removal()

    del captcha_pending[key]
    await query.message.delete()

    if chosen == correct:
        await safe_unmute(context, chat_id, target_id)
        await log_action(chat_id, "captcha_pass", target_id, query.from_user.full_name, context.bot.id)
        notif = await context.bot.send_message(
            chat_id,
            f"✅ {user_mention(query.from_user)} прошёл проверку!",
            parse_mode=ParseMode.HTML
        )
        context.job_queue.run_once(lambda ctx: safe_delete(notif), 10)
    else:
        await safe_ban(context, chat_id, target_id, until=int(_ts() + 600))
        await log_action(chat_id, "captcha_fail", target_id, query.from_user.full_name, context.bot.id)
        notif = await context.bot.send_message(
            chat_id,
            f"❌ {user_mention(query.from_user)} не прошёл проверку и кикнут на 10 минут.",
            parse_mode=ParseMode.HTML
        )
        context.job_queue.run_once(lambda ctx: safe_delete(notif), 10)


# ══════════════════════════════════════════════════════
#  КОМАНДЫ ВЛАДЕЛЬЦА БОТА (СИСТЕМНЫЕ)
# ══════════════════════════════════════════════════════

@owner_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ <b>Guard Bot активен</b>\n\n"
        "Вы — владелец системы. Доступные команды:\n\n"
        "<b>Персонал:</b>\n"
        "/addstaff [id] [role] — добавить стафф (trusted/moderator)\n"
        "/removestaff [id] — удалить из стаффа\n"
        "/liststaff — список персонала\n\n"
        "<b>Авторизация чатов:</b>\n"
        "/authchat — авторизовать текущий чат\n"
        "/deauthchat — деавторизовать чат\n\n"
        "<b>В авторизованных чатах:</b>\n"
        "Все команды модерации /ban /mute /kick /warn и т.д.\n\n"
        "/help — полная справка",
        parse_mode=ParseMode.HTML
    )


@owner_only
async def cmd_addstaff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Использование: /addstaff [user_id] [trusted|moderator]")
        return

    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("Неверный ID.")
        return

    role = args[1].lower()
    if role not in [Role.TRUSTED, Role.MODERATOR]:
        await update.message.reply_text("Роль: trusted или moderator")
        return

    username = args[2] if len(args) > 2 else f"user_{target_id}"
    await add_staff(target_id, username, role, OWNER_ID)
    await update.message.reply_text(f"✅ <code>{target_id}</code> добавлен как <b>{role}</b>.", parse_mode=ParseMode.HTML)
    await log_action(0, "add_staff", target_id, username, OWNER_ID, role)


@owner_only
async def cmd_removestaff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /removestaff [user_id]")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Неверный ID.")
        return
    await remove_staff(target_id)
    await update.message.reply_text(f"✅ <code>{target_id}</code> удалён из стаффа.", parse_mode=ParseMode.HTML)


@owner_only
async def cmd_liststaff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    staff = await list_staff()
    if not staff:
        await update.message.reply_text("Стафф пуст.")
        return
    lines = [f"👑 <b>Владелец:</b> <code>{OWNER_ID}</code>", ""]
    for uid, uname, role, added_by, added_at in staff:
        emoji = "🔑" if role == Role.TRUSTED else "🛡"
        lines.append(f"{emoji} <code>{uid}</code> @{uname} — {role}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@staff_only
async def cmd_authchat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Авторизовать чат для работы бота"""
    chat = update.effective_chat
    user = update.effective_user

    # Только владелец или trusted могут авторизовывать
    role = await get_staff_role(user.id)
    if role not in [Role.OWNER, Role.TRUSTED] and user.id != OWNER_ID:
        await update.message.reply_text("🚫 Только trusted/owner может авторизовывать чаты.")
        return

    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
        await update.message.reply_text("Команда только для групп и каналов.")
        return

    # project_owner — тот кто выдаёт команду
    await authorize_chat(chat.id, chat.title or "", chat.type, user.id, user.id)
    await update.message.reply_text(
        f"✅ Чат <b>{chat.title}</b> авторизован!\n"
        f"Логи будут отправляться вам в личку.\n\n"
        f"Настройки по умолчанию:\n"
        f"• Анти-флуд: ✅\n• Анти-спам: ✅\n• Капча: ✅\n• Анти-рейд: ✅\n\n"
        f"Используйте /settings для настройки.",
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
#  КОМАНДЫ МОДЕРАЦИИ
# ══════════════════════════════════════════════════════

@authorized_chat_only
@staff_only
async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    target = extract_user_from_reply(update)
    if not target:
        if context.args:
            try:
                tid = int(context.args[0])
                target_name = context.args[0]
                reason = " ".join(context.args[1:]) or "Без причины"
                await safe_ban(context, chat.id, tid)
                await add_ban(chat.id, tid, reason, user.id)
                await log_action(chat.id, "ban", tid, target_name, user.id, reason)
                await update.message.reply_text(
                    f"🔨 Пользователь <code>{tid}</code> заблокирован.\nПричина: {reason}",
                    parse_mode=ParseMode.HTML
                )
                return
            except (ValueError, IndexError):
                pass
        await update.message.reply_text("Ответьте на сообщение пользователя или укажите ID.")
        return

    reason = " ".join(context.args) if context.args else "Без причины"
    if target.id == OWNER_ID or await is_staff(target.id):
        await update.message.reply_text("🚫 Нельзя банить персонал.")
        return

    success = await safe_ban(context, chat.id, target.id)
    if success:
        await add_ban(chat.id, target.id, reason, user.id)
        await log_action(chat.id, "ban", target.id, target.full_name, user.id, reason)
        await update.message.reply_text(
            f"🔨 {user_mention(target)} <b>заблокирован</b>.\nПричина: {reason}",
            parse_mode=ParseMode.HTML
        )
        await notify_owner(context, chat.id,
            f"🔨 <b>Бан</b> в чате <code>{chat.id}</code>\n"
            f"Модератор: {user_mention(user)}\n"
            f"Нарушитель: {user_mention(target)}\n"
            f"Причина: {reason}"
        )
    else:
        await update.message.reply_text("❌ Не удалось заблокировать.")


@authorized_chat_only
@staff_only
async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("Использование: /unban [user_id]")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Неверный ID.")
        return

    await context.bot.unban_chat_member(chat.id, target_id)
    await remove_ban(chat.id, target_id)
    await log_action(chat.id, "unban", target_id, str(target_id), user.id)
    await update.message.reply_text(f"✅ Пользователь <code>{target_id}</code> разблокирован.", parse_mode=ParseMode.HTML)


@authorized_chat_only
@staff_only
async def cmd_kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    target = extract_user_from_reply(update)
    if not target:
        await update.message.reply_text("Ответьте на сообщение пользователя.")
        return

    reason = " ".join(context.args) if context.args else "Без причины"
    if target.id == OWNER_ID or await is_staff(target.id):
        await update.message.reply_text("🚫 Нельзя кикать персонал.")
        return

    try:
        await context.bot.ban_chat_member(chat.id, target.id)
        await context.bot.unban_chat_member(chat.id, target.id)
        await log_action(chat.id, "kick", target.id, target.full_name, user.id, reason)
        await update.message.reply_text(
            f"👢 {user_mention(target)} <b>кикнут</b>.\nПричина: {reason}",
            parse_mode=ParseMode.HTML
        )
    except TelegramError as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


@authorized_chat_only
@staff_only
async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    target = extract_user_from_reply(update)
    if not target:
        await update.message.reply_text("Ответьте на сообщение пользователя.")
        return

    if target.id == OWNER_ID or await is_staff(target.id):
        await update.message.reply_text("🚫 Нельзя мутить персонал.")
        return

    duration = 3600  # дефолт 1ч
    reason = "Без причины"
    if context.args:
        dur = parse_time_arg(context.args[0])
        if dur > 0:
            duration = dur
            reason = " ".join(context.args[1:]) or "Без причины"
        else:
            reason = " ".join(context.args)

    until = int(_ts() + duration)
    await safe_mute(context, chat.id, target.id, until)
    mute_tracker[chat.id][target.id] = until

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO mutes (chat_id,user_id,until,reason,muted_by) VALUES (?,?,?,?,?)",
            (chat.id, target.id, datetime.utcfromtimestamp(until).strftime("%Y-%m-%d %H:%M:%S"), reason, user.id)
        )
        await db.commit()

    await log_action(chat.id, "mute", target.id, target.full_name, user.id, reason)
    await update.message.reply_text(
        f"🔇 {user_mention(target)} замучен на <b>{format_duration(duration)}</b>.\nПричина: {reason}",
        parse_mode=ParseMode.HTML
    )
    await notify_owner(context, chat.id,
        f"🔇 <b>Мут</b> в чате <code>{chat.id}</code>\n"
        f"Модератор: {user_mention(user)}\n"
        f"Пользователь: {user_mention(target)}\n"
        f"Длительность: {format_duration(duration)}\n"
        f"Причина: {reason}"
    )


@authorized_chat_only
@staff_only
async def cmd_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    target = extract_user_from_reply(update)
    if not target:
        await update.message.reply_text("Ответьте на сообщение.")
        return

    await safe_unmute(context, chat.id, target.id)
    if target.id in mute_tracker.get(chat.id, {}):
        del mute_tracker[chat.id][target.id]
    await log_action(chat.id, "unmute", target.id, target.full_name, user.id)
    await update.message.reply_text(f"🔊 {user_mention(target)} размучен.", parse_mode=ParseMode.HTML)


@authorized_chat_only
@staff_only
async def cmd_warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    target = extract_user_from_reply(update)
    if not target:
        await update.message.reply_text("Ответьте на сообщение пользователя.")
        return

    if target.id == OWNER_ID or await is_staff(target.id):
        await update.message.reply_text("🚫 Нельзя предупреждать персонал.")
        return

    reason = " ".join(context.args) if context.args else "Без причины"
    warn_count = await add_warning(chat.id, target.id, reason, user.id)
    await log_action(chat.id, "warn", target.id, target.full_name, user.id, reason)

    if warn_count >= WARNS_LIMIT:
        await _auto_ban(context, chat.id, target, f"Превышен лимит предупреждений ({warn_count})")
    else:
        await update.message.reply_text(
            f"⚠️ {user_mention(target)} получил предупреждение [{warn_count}/{WARNS_LIMIT}]\n"
            f"Причина: {reason}",
            parse_mode=ParseMode.HTML
        )
        await notify_owner(context, chat.id,
            f"⚠️ <b>Варн</b> в чате <code>{chat.id}</code>\n"
            f"Модератор: {user_mention(user)}\n"
            f"Нарушитель: {user_mention(target)}\n"
            f"[{warn_count}/{WARNS_LIMIT}] Причина: {reason}"
        )


@authorized_chat_only
@staff_only
async def cmd_unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    target = extract_user_from_reply(update)
    if not target:
        await update.message.reply_text("Ответьте на сообщение.")
        return
    await clear_warnings(chat.id, target.id)
    await update.message.reply_text(f"✅ Предупреждения {user_mention(target)} сброшены.", parse_mode=ParseMode.HTML)


@authorized_chat_only
@staff_only
async def cmd_shadowban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    target = extract_user_from_reply(update)
    if not target:
        await update.message.reply_text("Ответьте на сообщение.")
        return
    shadowbanned[chat.id].add(target.id)
    await log_action(chat.id, "shadowban", target.id, target.full_name, user.id)
    await update.message.reply_text(
        f"👻 Shadowban применён к <code>{target.id}</code>. Их сообщения будут тихо удаляться.",
        parse_mode=ParseMode.HTML
    )


@authorized_chat_only
@staff_only
async def cmd_unshadowban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    target = extract_user_from_reply(update)
    if not target:
        await update.message.reply_text("Ответьте на сообщение.")
        return
    shadowbanned[chat.id].discard(target.id)
    await update.message.reply_text(f"✅ Shadowban снят с <code>{target.id}</code>.", parse_mode=ParseMode.HTML)


@authorized_chat_only
@staff_only
async def cmd_purge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаляет N последних сообщений в чате"""
    if not context.args:
        await update.message.reply_text("Использование: /purge [кол-во] (макс 100)")
        return
    try:
        count = min(int(context.args[0]), 100)
    except ValueError:
        await update.message.reply_text("Неверное число.")
        return

    chat = update.effective_chat
    user = update.effective_user
    deleted = 0

    # Telegram API не даёт удалять старые сообщения, работаем через reply
    if update.message.reply_to_message:
        msg_id = update.message.reply_to_message.message_id
        for mid in range(msg_id, msg_id + count):
            try:
                await context.bot.delete_message(chat.id, mid)
                deleted += 1
            except Exception:
                pass
    else:
        msg_id = update.message.message_id
        for mid in range(msg_id - count, msg_id + 1):
            if mid > 0:
                try:
                    await context.bot.delete_message(chat.id, mid)
                    deleted += 1
                except Exception:
                    pass

    await log_action(chat.id, "purge", 0, "SYSTEM", user.id, f"Удалено ~{deleted} сообщений")
    notif = await context.bot.send_message(chat.id, f"🗑️ Удалено ~{deleted} сообщений.")
    context.job_queue.run_once(lambda ctx: safe_delete(notif), 5)


@authorized_chat_only
@staff_only
async def cmd_slowmode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Включить медленный режим"""
    chat = update.effective_chat
    if not context.args:
        await update.message.reply_text("Использование: /slowmode [секунды] (0 = выкл)")
        return
    try:
        delay = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Неверное число.")
        return
    try:
        await context.bot.set_chat_slow_mode_delay(chat.id, delay)
        await update.message.reply_text(
            f"🐢 Slowmode: {'выключен' if delay == 0 else f'{delay}с'}"
        )
    except TelegramError as e:
        await update.message.reply_text(f"❌ {e}")


@authorized_chat_only
@staff_only
async def cmd_lockdown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ручной lockdown чата"""
    chat = update.effective_chat
    user = update.effective_user
    duration = 600
    if context.args:
        duration = parse_time_arg(context.args[0]) or duration

    lockdown_active[chat.id] = _ts() + duration
    await log_action(chat.id, "manual_lockdown", 0, "SYSTEM", user.id, f"{format_duration(duration)}")

    # Закрываем чат
    try:
        await context.bot.set_chat_permissions(chat.id, ChatPermissions(
            can_send_messages=False,
            can_send_polls=False,
            can_send_other_messages=False
        ))
    except Exception:
        pass

    await update.message.reply_text(
        f"🔒 <b>LOCKDOWN</b> активирован на {format_duration(duration)}!",
        parse_mode=ParseMode.HTML
    )
    await notify_owner(context, chat.id,
        f"🔒 <b>Lockdown</b> в чате <code>{chat.id}</code>\nМодератор: {user_mention(user)}\n"
        f"Длительность: {format_duration(duration)}"
    )

    # Автоснятие
    async def unlock(ctx):
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

    context.job_queue.run_once(unlock, duration, name=f"unlock_{chat.id}")


@authorized_chat_only
@staff_only
async def cmd_unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    lockdown_active.pop(chat.id, None)
    # Снять джобы
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

@authorized_chat_only
@staff_only
async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    settings = await get_chat_settings(chat.id)

    def yesno(key, default=True):
        return "✅" if settings.get(key, default) else "❌"

    text = (
        f"⚙️ <b>Настройки чата {chat.title}</b>\n\n"
        f"{yesno('antiflood')} Анти-флуд\n"
        f"{yesno('antispam')} Анти-спам\n"
        f"{yesno('antiduplicate')} Анти-дубли\n"
        f"{yesno('antilinks', False)} Анти-ссылки\n"
        f"{yesno('antiforward', False)} Анти-форвард\n"
        f"{yesno('captcha')} Капча на вход\n"
        f"{yesno('antiraid')} Анти-рейд\n\n"
        f"Изменить: /set [параметр] [on|off]\n"
        f"Пример: <code>/set antilinks on</code>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


@authorized_chat_only
@staff_only
async def cmd_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /set [параметр] [on|off]")
        return

    key = context.args[0].lower()
    val = context.args[1].lower()
    valid_keys = ["antiflood", "antispam", "antiduplicate", "antilinks", "antiforward", "captcha", "antiraid"]

    if key not in valid_keys:
        await update.message.reply_text(f"Неверный параметр. Доступные: {', '.join(valid_keys)}")
        return

    if val not in ["on", "off", "1", "0", "true", "false"]:
        await update.message.reply_text("Значение: on или off")
        return

    value = val in ["on", "1", "true"]
    await set_chat_setting(chat.id, key, value)
    await update.message.reply_text(f"✅ {key} = {'on' if value else 'off'}")


@authorized_chat_only
@staff_only
async def cmd_setwelcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not context.args:
        await update.message.reply_text(
            "Использование: /setwelcome [текст]\nИспользуйте {user} для упоминания."
        )
        return
    text = " ".join(context.args)
    await set_chat_setting(chat.id, "welcome_text", text)
    await update.message.reply_text(f"✅ Приветствие установлено:\n{text}")


@authorized_chat_only
@staff_only
async def cmd_addfilter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /addfilter [слово] [delete|warn|mute|ban]")
        return
    word = context.args[0].lower()
    action = context.args[1].lower()
    if action not in ["delete", "warn", "mute", "ban"]:
        await update.message.reply_text("Действие: delete, warn, mute или ban")
        return
    await add_word_filter(chat.id, word, action, user.id)
    await update.message.reply_text(f"✅ Фильтр добавлен: <code>{word}</code> → {action}", parse_mode=ParseMode.HTML)


@authorized_chat_only
@staff_only
async def cmd_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    filters_list = await get_word_filters(chat.id)
    if not filters_list:
        await update.message.reply_text("Фильтры слов не настроены.")
        return
    lines = ["📝 <b>Фильтры слов:</b>"]
    for f_id, word, action in filters_list:
        lines.append(f"#{f_id} | <code>{word}</code> → {action}")
    lines.append("\nУдалить: /delfilter [id]")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@authorized_chat_only
@staff_only
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


@authorized_chat_only
@staff_only
async def cmd_addwl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить домен в whitelist ссылок"""
    chat = update.effective_chat
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("Использование: /addwl [домен]")
        return
    domain = context.args[0].lower().replace("https://", "").replace("http://", "").split("/")[0]
    await add_link_whitelist(chat.id, domain, user.id)
    await update.message.reply_text(f"✅ Домен <code>{domain}</code> добавлен в whitelist.", parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════
#  ИНФОРМАЦИЯ И ЛОГИ
# ══════════════════════════════════════════════════════

@authorized_chat_only
@staff_only
async def cmd_userinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    target = extract_user_from_reply(update)
    if not target:
        await update.message.reply_text("Ответьте на сообщение пользователя.")
        return

    warns = await get_warnings(chat.id, target.id)
    is_banned_f = await is_banned(chat.id, target.id)
    is_shadow = target.id in shadowbanned.get(chat.id, set())
    mute_until = mute_tracker.get(chat.id, {}).get(target.id, 0)
    is_muted = mute_until > _ts()

    text = (
        f"👤 <b>Информация о пользователе</b>\n\n"
        f"ID: <code>{target.id}</code>\n"
        f"Имя: {user_mention(target)}\n"
        f"Username: @{target.username or '—'}\n\n"
        f"⚠️ Предупреждений: {len(warns)}/{WARNS_LIMIT}\n"
        f"🔇 Мут: {'до ' + datetime.utcfromtimestamp(mute_until).strftime('%H:%M %d.%m') if is_muted else 'нет'}\n"
        f"🔨 Бан: {'да' if is_banned_f else 'нет'}\n"
        f"👻 Shadowban: {'да' if is_shadow else 'нет'}\n"
    )
    if warns:
        text += "\n<b>История предупреждений:</b>\n"
        for reason, issued_at in warns:
            text += f"• {issued_at}: {reason}\n"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


@authorized_chat_only
@staff_only
async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    limit = 10
    if context.args:
        try:
            limit = min(int(context.args[0]), 50)
        except ValueError:
            pass

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT action_type, target_username, performed_by, reason, created_at
               FROM action_logs WHERE chat_id=?
               ORDER BY created_at DESC LIMIT ?""",
            (chat.id, limit)
        ) as cur:
            rows = await cur.fetchall()

    if not rows:
        await update.message.reply_text("Логи пусты.")
        return

    lines = [f"📋 <b>Последние {len(rows)} действий:</b>"]
    for action, target, by, reason, at in rows:
        lines.append(f"• [{at}] <b>{action}</b> → {target} | {reason or '—'}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@authorized_chat_only
@staff_only
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM action_logs WHERE chat_id=?", (chat.id,)
        ) as cur:
            total_actions = (await cur.fetchone())[0]

        async with db.execute(
            "SELECT COUNT(*) FROM spam_stats WHERE chat_id=?", (chat.id,)
        ) as cur:
            total_spam = (await cur.fetchone())[0]

        async with db.execute(
            "SELECT COUNT(*) FROM warnings WHERE chat_id=?", (chat.id,)
        ) as cur:
            total_warns = (await cur.fetchone())[0]

        async with db.execute(
            "SELECT COUNT(*) FROM bans WHERE chat_id=?", (chat.id,)
        ) as cur:
            total_bans = (await cur.fetchone())[0]

        async with db.execute(
            """SELECT spam_type, COUNT(*) as cnt FROM spam_stats
               WHERE chat_id=? GROUP BY spam_type ORDER BY cnt DESC LIMIT 5""",
            (chat.id,)
        ) as cur:
            spam_types = await cur.fetchall()

    text = (
        f"📊 <b>Статистика чата {chat.title}</b>\n\n"
        f"Всего действий: {total_actions}\n"
        f"Спам-инцидентов: {total_spam}\n"
        f"Предупреждений: {total_warns}\n"
        f"Банов: {total_bans}\n"
    )
    if spam_types:
        text += "\n<b>Топ спам-типов:</b>\n"
        for st, cnt in spam_types:
            text += f"• {st}: {cnt}\n"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════
#  СПРАВКА
# ══════════════════════════════════════════════════════

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    role = await get_staff_role(user.id)

    if not role and user.id != OWNER_ID:
        await update.message.reply_text(
            "🛡️ <b>Guard Bot</b>\n\n"
            "Бот для защиты чатов и каналов от спама, рейдов и нарушителей.",
            parse_mode=ParseMode.HTML
        )
        return

    text = (
        "🛡️ <b>Guard Bot — Справка</b>\n\n"
        "<b>🔨 Модерация:</b>\n"
        "/ban — бан (ответ или /ban [id])\n"
        "/unban [id] — разбан\n"
        "/kick — кик\n"
        "/mute [время] — мут (10m, 2h, 3d)\n"
        "/unmute — снять мут\n"
        "/warn [причина] — предупреждение\n"
        "/unwarn — сброс предупреждений\n"
        "/shadowban — теневой бан\n"
        "/purge [n] — удалить n сообщений\n\n"
        "<b>🔒 Защита:</b>\n"
        "/lockdown [время] — lockdown чата\n"
        "/unlock — снять lockdown\n"
        "/slowmode [сек] — медленный режим\n\n"
        "<b>⚙️ Настройки:</b>\n"
        "/settings — показать настройки\n"
        "/set [параметр] [on|off] — изменить\n"
        "/setwelcome [текст] — приветствие\n"
        "/addfilter [слово] [действие] — фильтр\n"
        "/filters — список фильтров\n"
        "/delfilter [id] — удалить фильтр\n"
        "/addwl [домен] — whitelist ссылок\n\n"
        "<b>📊 Информация:</b>\n"
        "/userinfo — инфо о пользователе\n"
        "/logs [n] — последние логи\n"
        "/stats — статистика\n\n"
        "<b>⚡ Параметры /set:</b>\n"
        "antiflood | antispam | antiduplicate\n"
        "antilinks | antiforward | captcha | antiraid"
    )

    if user.id == OWNER_ID:
        text += (
            "\n\n<b>👑 Системные (только owner):</b>\n"
            "/addstaff [id] [role] — добавить стафф\n"
            "/removestaff [id] — удалить\n"
            "/liststaff — список\n"
            "/authchat — авторизовать чат\n"
            "/deauthchat — деавторизовать\n"
        )

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════
#  ОБРАБОТЧИК ВЫХОДА БОТА ИЗ ЧАТА (безопасность)
# ══════════════════════════════════════════════════════

async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Реагирует на изменение статуса бота в чате"""
    result = update.my_chat_member
    if not result:
        return

    chat = result.chat
    new_status = result.new_chat_member.status

    if new_status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR]:
        # Бот добавлен в чат — проверяем авторизацию
        if not await is_authorized_chat(chat.id):
            logger.warning(f"Бот добавлен в неавторизованный чат {chat.id} ({chat.title}). Выхожу.")
            try:
                await context.bot.send_message(
                    chat.id,
                    "⛔ Этот бот не авторизован для данного чата. Обратитесь к администратору системы."
                )
                await asyncio.sleep(2)
                await context.bot.leave_chat(chat.id)
            except Exception:
                pass
            # Уведомить владельца
            try:
                await context.bot.send_message(
                    OWNER_ID,
                    f"⚠️ Попытка добавить бота в неавторизованный чат!\n"
                    f"Чат: <b>{chat.title}</b> (<code>{chat.id}</code>)\n"
                    f"Тип: {chat.type}\n"
                    f"Добавил: <code>{result.from_user.id}</code> @{result.from_user.username}",
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass


# ══════════════════════════════════════════════════════
#  ОБРАБОТЧИК ОШИБОК
# ══════════════════════════════════════════════════════

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}", exc_info=True)
    if isinstance(context.error, Forbidden):
        logger.warning("Бот заблокирован или не имеет прав.")
    elif isinstance(context.error, BadRequest):
        logger.warning(f"Bad request: {context.error}")


# ══════════════════════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════════════════════

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не задан! Укажите в .env файле.")
        return
    if not OWNER_ID:
        logger.error("OWNER_ID не задан! Укажите в .env файле.")
        return

    async def post_init(app: Application):
        await init_db()
        logger.info(f"Guard Bot запущен. Owner ID: {OWNER_ID}")
        try:
            await app.bot.send_message(
                OWNER_ID,
                "🟢 <b>Guard Bot запущен</b>\n\n"
                "Система защиты активирована.\n"
                "Используйте /help для списка команд.",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # ── Системные команды ──
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("addstaff", cmd_addstaff))
    app.add_handler(CommandHandler("removestaff", cmd_removestaff))
    app.add_handler(CommandHandler("liststaff", cmd_liststaff))

    # ── Авторизация чатов ──
    app.add_handler(CommandHandler("authchat", cmd_authchat))
    app.add_handler(CommandHandler("deauthchat", cmd_deauthchat))

    # ── Модерация ──
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))
    app.add_handler(CommandHandler("kick", cmd_kick))
    app.add_handler(CommandHandler("mute", cmd_mute))
    app.add_handler(CommandHandler("unmute", cmd_unmute))
    app.add_handler(CommandHandler("warn", cmd_warn))
    app.add_handler(CommandHandler("unwarn", cmd_unwarn))
    app.add_handler(CommandHandler("shadowban", cmd_shadowban))
    app.add_handler(CommandHandler("unshadowban", cmd_unshadowban))
    app.add_handler(CommandHandler("purge", cmd_purge))

    # ── Защита чата ──
    app.add_handler(CommandHandler("lockdown", cmd_lockdown))
    app.add_handler(CommandHandler("unlock", cmd_unlock))
    app.add_handler(CommandHandler("slowmode", cmd_slowmode))

    # ── Настройки ──
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("set", cmd_set))
    app.add_handler(CommandHandler("setwelcome", cmd_setwelcome))
    app.add_handler(CommandHandler("addfilter", cmd_addfilter))
    app.add_handler(CommandHandler("filters", cmd_filters))
    app.add_handler(CommandHandler("delfilter", cmd_delfilter))
    app.add_handler(CommandHandler("addwl", cmd_addwl))

    # ── Информация ──
    app.add_handler(CommandHandler("userinfo", cmd_userinfo))
    app.add_handler(CommandHandler("logs", cmd_logs))
    app.add_handler(CommandHandler("stats", cmd_stats))

    # ── Сообщения (модерация) ──
    app.add_handler(MessageHandler(
        filters.TEXT | filters.CAPTION | filters.FORWARDED,
        handle_message
    ))

    # ── Новые участники ──
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_member))

    # ── Капча (callback) ──
    app.add_handler(CallbackQueryHandler(captcha_callback, pattern=r"^captcha:"))

    # ── Статус бота в чате ──
    app.add_handler(ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    # ── Ошибки ──
    app.add_error_handler(error_handler)

    logger.info("Запуск polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
