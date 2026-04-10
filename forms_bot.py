"""
forms_bot.py — Выделенный бот для приёма форм из мини-приложений.

Принцип работы:
  Пользователь добавляет этого бота в чат (группу, канал, личные сообщения).
  Бот сообщает ID чата.
  Этот ID вводится в настройки мини-приложения — поле «ID чата».
  Все заявки с форм приходят в этот чат.

Оптимизирован для высокой нагрузки:
  - aiogram 3.x с polling
  - Один переиспользуемый httpx.AsyncClient (connection pool)
  - Минимальная обработка в хендлерах, никаких блокирующих вызовов
  - Graceful shutdown

Переменные окружения (.env):
  FORM_BOT_TOKEN — токен бота (обязательно)
"""

import asyncio
import logging
import os
import signal
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ChatMemberUpdated, BotCommand, BotCommandScopeDefault
from aiogram.filters import Command, CommandStart
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter
from aiogram.client.session.aiohttp import AiohttpSession

try:
    from aiohttp_socks import ProxyConnector as _ProxyConnector
    _SOCKS_OK = True
except ImportError:
    _SOCKS_OK = False

import os
import aiohttp
from aiogram.client.session.aiohttp import AiohttpSession

# --- НАШ КАСТОМНЫЙ КЛАСС (ОБХОД ОШИБОК AIOGRAM 3.24) ---
class CustomProxySession(AiohttpSession):
    def __init__(self, connector: aiohttp.BaseConnector):
        # Вызываем конструктор aiogram БЕЗ аргументов (ошибок не будет)
        super().__init__()
        self._custom_connector = connector

    # Принудительно встраиваем коннектор прямо в ядро aiohttp
    async def create_session(self) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(
            connector=self._custom_connector,
            json_serialize=self.json_dumps,
            # FIX: увеличен до 90с — синхронизировать с _make_session timeout
            timeout=aiohttp.ClientTimeout(total=90, connect=20)
        )
# ---------------------------------------------------------


# ── Конфигурация ──────────────────────────────────────────────────────────────

def load_env() -> None:
    """Читает .env файл если он есть."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip("\"'"))


load_env()

TOKEN = os.getenv("FORM_BOT_TOKEN", "")
if not TOKEN:
    raise RuntimeError(
        "FORM_BOT_TOKEN не задан. Укажите его в .env или переменных окружения."
    )

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("FormsBot")


# ── Бот и диспетчер ───────────────────────────────────────────────────────────

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()


# ── Тексты ────────────────────────────────────────────────────────────────────

TEXT_START = (
    "<b>Бот для приёма форм</b>\n\n"
    "Через меня вы будете получать заявки из своих мини-приложений.\n\n"
    "<b>Как подключить:</b>\n"
    "1. Добавьте меня в нужный чат или группу.\n"
    "2. Я пришлю ID этого чата — скопируйте его.\n"
    "3. В редакторе мини-приложения выберите <b>«Через бот форм»</b>.\n"
    "4. Вставьте ID в поле <b>«ID чата»</b>.\n\n"
    "Ваш личный ID: <code>{user_id}</code>\n"
    "Используйте его если хотите получать заявки в личные сообщения."
)

TEXT_CHATID = (
    "<b>ID этого чата:</b> <code>{chat_id}</code>\n\n"
    "Скопируйте и вставьте в настройки мини-приложения — поле <b>«ID чата»</b>.\n"
    "После этого все заявки с формы будут приходить сюда."
)

TEXT_ADDED_TO_CHAT = (
    "<b>Бот для форм подключён.</b>\n\n"
    "<b>ID этого чата:</b> <code>{chat_id}</code>\n\n"
    "Скопируйте этот ID и вставьте в настройки нужного мини-приложения.\n"
    "Все заявки с форм будут приходить сюда."
)

TEXT_HELP = (
    "<b>Команды:</b>\n\n"
    "/start — приветствие и инструкция\n"
    "/chatid — показать ID текущего чата\n"
    "/help — эта справка\n\n"
    "<b>Как это работает:</b>\n"
    "Добавьте меня в чат. Я сообщу ID этого чата.\n"
    "Введите ID в настройки мини-приложения. Заявки будут приходить сюда."
)


# ── Хендлеры ──────────────────────────────────────────────────────────────────

@dp.message(CommandStart())
async def handle_start(message: Message) -> None:
    """Приветствие с инструкцией."""
    text = TEXT_START.format(user_id=message.from_user.id)
    await message.answer(text)
    logger.info(f"Start from user {message.from_user.id} (@{message.from_user.username})")


@dp.message(Command("chatid"))
async def handle_chatid(message: Message) -> None:
    """Показывает ID текущего чата. Работает в личке и в группах."""
    text = TEXT_CHATID.format(chat_id=message.chat.id)
    await message.answer(text)


@dp.message(Command("help"))
async def handle_help(message: Message) -> None:
    await message.answer(TEXT_HELP)


@dp.my_chat_member()
async def handle_chat_member_update(event: ChatMemberUpdated) -> None:
    """Срабатывает когда бота добавляют в чат или исключают."""
    new_status = event.new_chat_member.status

    if new_status in ("member", "administrator"):
        # Бота добавили — сообщаем ID чата
        try:
            text = TEXT_ADDED_TO_CHAT.format(chat_id=event.chat.id)
            await bot.send_message(event.chat.id, text)
            logger.info(
                f"Added to chat id={event.chat.id} "
                f"title={event.chat.title!r} "
                f"type={event.chat.type}"
            )
        except Exception as exc:
            logger.warning(f"Cannot send to chat {event.chat.id}: {exc}")

    elif new_status in ("kicked", "left"):
        logger.info(f"Removed from chat id={event.chat.id} title={event.chat.title!r}")


# ── Запуск ────────────────────────────────────────────────────────────────────

async def set_commands() -> None:
    """Регистрирует команды в меню Telegram."""
    commands = [
        BotCommand(command="start",  description="Инструкция по подключению"),
        BotCommand(command="chatid", description="ID текущего чата"),
        BotCommand(command="help",   description="Справка"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())


async def main() -> None:
    await set_commands()
    logger.info("FormsBot starting...")
    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "my_chat_member"],
            close_bot_session=True,
        )
    finally:
        await bot.session.close()
        logger.info("FormsBot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Interrupted.")
