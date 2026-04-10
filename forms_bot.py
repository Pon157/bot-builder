"""
forms_bot.py — Выделенный бот для приёма форм из мини-приложений.
"""

import asyncio
import logging
import os
import sys
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ChatMemberUpdated, BotCommand, BotCommandScopeDefault
from aiogram.filters import Command, CommandStart
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.client.session.aiohttp import AiohttpSession

# Пробуем импортировать прокси
try:
    from aiohttp_socks import ProxyConnector
    SOCKS_AVAILABLE = True
except ImportError:
    SOCKS_AVAILABLE = False
    ProxyConnector = None

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
    raise RuntimeError("FORM_BOT_TOKEN не задан")

# Поддержка разных имен переменных для прокси
PROXY_URL = os.getenv("TG_PROXY_URL") or os.getenv("PROXY_URL") or ""
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("FormsBot")

# Таймауты
TIMEOUT = aiohttp.ClientTimeout(total=60, connect=30)


class CustomProxySession(AiohttpSession):
    """Кастомная сессия для прокси"""
    def __init__(self, connector):
        super().__init__(timeout=TIMEOUT)
        self._connector = connector

    async def create_session(self) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(
            connector=self._connector,
            json_serialize=self.json_dumps,
            timeout=TIMEOUT
        )


def create_bot_session():
    """Создает сессию с прокси или без"""
    if PROXY_URL:
        if not SOCKS_AVAILABLE:
            logger.error("aiohttp_socks не установлен! Прокси не будет работать")
            logger.error("Установите: pip install aiohttp_socks")
            return AiohttpSession(timeout=TIMEOUT)
        
        try:
            logger.info(f"Подключаемся через прокси: {PROXY_URL}")
            connector = ProxyConnector.from_url(PROXY_URL)
            logger.info("Прокси успешно настроен")
            return CustomProxySession(connector)
        except Exception as e:
            logger.error(f"Ошибка прокси: {e}")
            logger.warning("Работаем без прокси")
            return AiohttpSession(timeout=TIMEOUT)
    
    return AiohttpSession(timeout=TIMEOUT)


# Создаем бота
bot_session = create_bot_session()
bot = Bot(
    token=TOKEN,
    session=bot_session,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()


# ── Тексты (без изменений) ────────────────────────────────────────────────────

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
    text = TEXT_START.format(user_id=message.from_user.id)
    await message.answer(text)
    logger.info(f"Start from user {message.from_user.id}")


@dp.message(Command("chatid"))
async def handle_chatid(message: Message) -> None:
    text = TEXT_CHATID.format(chat_id=message.chat.id)
    await message.answer(text)


@dp.message(Command("help"))
async def handle_help(message: Message) -> None:
    await message.answer(TEXT_HELP)


@dp.my_chat_member()
async def handle_chat_member_update(event: ChatMemberUpdated) -> None:
    new_status = event.new_chat_member.status
    if new_status in ("member", "administrator"):
        try:
            text = TEXT_ADDED_TO_CHAT.format(chat_id=event.chat.id)
            await bot.send_message(event.chat.id, text)
            logger.info(f"Added to chat {event.chat.id}")
        except Exception as exc:
            logger.warning(f"Cannot send to chat {event.chat.id}: {exc}")
    elif new_status in ("kicked", "left"):
        logger.info(f"Removed from chat {event.chat.id}")


# ── Запуск ────────────────────────────────────────────────────────────────────

async def main():
    """Запуск бота"""
    logger.info("FormsBot starting...")
    
    # Устанавливаем команды
    commands = [
        BotCommand(command="start", description="Инструкция по подключению"),
        BotCommand(command="chatid", description="ID текущего чата"),
        BotCommand(command="help", description="Справка"),
    ]
    
    try:
        await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
        logger.info("Commands set")
    except Exception as e:
        logger.error(f"Failed to set commands: {e}")
    
    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "my_chat_member"],
        )
    finally:
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted")
    except Exception as e:
        logger.error(f"Fatal: {e}", exc_info=True)
        sys.exit(1)
