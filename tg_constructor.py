import os
import logging
import httpx
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command

import os
import aiohttp
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramBadRequest

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
            timeout=aiohttp.ClientTimeout(total=40, connect=15)
        )
# ---------------------------------------------------------

def _make_session():
    # Берем токен из .env файла
    _PROXY_URL = os.getenv("TG_PROXY_URL", "").strip()
    
    # Таймауты для стабильности
    _timeout = aiohttp.ClientTimeout(total=40, connect=15)

    # Если прокси нет — стандартная сессия
    if not _PROXY_URL:
        return AiohttpSession(timeout=_timeout)

    try:
        if not _SOCKS_OK:
            print("[NET] Ошибка: библиотека aiohttp_socks не установлена. Запуск без прокси.")
            return AiohttpSession(timeout=_timeout)

        # aiohttp_socks отлично работает и с SOCKS, и с HTTP.
        # Поэтому мы просто отдаем ему любой URL.
        clean_proxy = _PROXY_URL.replace("socks5h://", "socks5://")
        
        # Создаем коннектор
        connector = _ProxyConnector.from_url(clean_proxy, rdns=True)
        
        # ВОЗВРАЩАЕМ НАШ КЛАСС, а не стандартный AiohttpSession
        return CustomProxySession(connector=connector)
            
    except Exception as e:
        print(f"Ошибка конфигурации сессии: {e}")
    
    return AiohttpSession(timeout=_timeout)
    

# Загружаем переменные из .env согласно правилам безопасности
load_dotenv()

TOKEN = os.getenv("CONSTRUCTOR_BOT_TOKEN")
API_URL = os.getenv("SERVER_BASE_URL", "http://localhost:8000")

if not TOKEN:
    raise ValueError("Токен CONSTRUCTOR_BOT_TOKEN не найден в файле .env!")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()

# ==========================================
# FSM Состояния
# ==========================================
class BotCreateStates(StatesGroup):
    waiting_for_token = State()
    waiting_for_name = State()

class BotEditStates(StatesGroup):
    waiting_for_welcome = State()
    waiting_for_first_msg = State()
    waiting_for_admin_chat = State()
    waiting_for_trigger_keyword = State()
    waiting_for_trigger_reply = State()
    waiting_for_broadcast = State()

# ==========================================
# HTTP API Клиент к основному серверу
# ==========================================
async def api_request(method: str, endpoint: str, json_data: dict = None, params: dict = None):
    async with httpx.AsyncClient() as client:
        url = f"{API_URL}{endpoint}"
        try:
            if method == "GET":
                resp = await client.get(url, params=params, timeout=10)
            elif method == "POST":
                resp = await client.post(url, json=json_data, timeout=10)
            elif method == "PUT":
                resp = await client.put(url, json=json_data, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logging.error(f"API Error ({endpoint}): {e}")
            return None

# ==========================================
# Клавиатуры
# ==========================================
def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Создать бота", callback_data="create_bot")],
        [InlineKeyboardButton(text="Мои боты", callback_data="my_bots")]
    ])

def bot_manage_kb(bot_id: str, status: str):
    start_stop_btn = InlineKeyboardButton(text="⏹ Остановить", callback_data=f"stop_{bot_id}") if status == "RUNNING" else InlineKeyboardButton(text="▶️ Запустить", callback_data=f"start_{bot_id}")
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [start_stop_btn],
        [InlineKeyboardButton(text="Приветствие", callback_data=f"edit_welcome_{bot_id}"),
         InlineKeyboardButton(text="1-е сообщение", callback_data=f"edit_firstmsg_{bot_id}")],
        [InlineKeyboardButton(text="Добавить триггер", callback_data=f"add_trigger_{bot_id}"),
         InlineKeyboardButton(text="Админ-чат", callback_data=f"edit_admin_{bot_id}")],
        [InlineKeyboardButton(text="Сделать рассылку", callback_data=f"broadcast_{bot_id}")],
        [InlineKeyboardButton(text="Назад к списку", callback_data="my_bots")]
    ])

# ==========================================
# Обработчики
# ==========================================
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Привет! Я мини-конструктор ботов, созданный на базе Dialoge engine.\n\n"
        "Здесь ты можешь быстро создать бота, настроить его текста, триггеры и привязать админ-чат. "
        "Все твои боты работают на бесплатном тарифе со встроенной рекламной монетизацией.",
        reply_markup=main_menu_kb()
    )

# --- Создание бота ---
@router.callback_query(F.data == "create_bot")
async def process_create_bot(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Отправь мне токен нового бота (полученный в @BotFather):")
    await state.set_state(BotCreateStates.waiting_for_token)

@router.message(BotCreateStates.waiting_for_token)
async def process_token(message: Message, state: FSMContext):
    await state.update_data(token=message.text.strip())
    await message.answer("Отлично! Теперь отправь название для твоего бота:")
    await state.set_state(BotCreateStates.waiting_for_name)

@router.message(BotCreateStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = str(message.from_user.id)
    
    msg = await message.answer("Создаю бота в базе...")
    
    # Отправляем запрос на основной сервер (создаст free-бота с рекламой)
    payload = {"user_id": user_id, "name": message.text.strip(), "token": data['token']}
    res = await api_request("POST", "/api/free/bots/create", json_data=payload)
    
    if res and "id" in res:
        await msg.edit_text(f"Бот <b>{message.text}</b> успешно создан!", parse_mode="HTML", reply_markup=main_menu_kb())
    else:
        await msg.edit_text("Ошибка при создании бота. Проверь логи основного сервера.", reply_markup=main_menu_kb())
    await state.clear()

# --- Список ботов ---
@router.callback_query(F.data == "my_bots")
async def process_my_bots(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    logging.info(f"🔍 Ищем ботов для owner_id: {user_id}")
    
    # Запрашиваем список ботов
    bots = await api_request("GET", f"/api/free/bots/{user_id}")
    
    # Логируем ответ от сервера для отладки
    logging.info(f"📡 Ответ сервера: {bots}")

    # Проверяем, что пришел именно список и он не пуст
    if not bots or not isinstance(bots, list) or len(bots) == 0:
        try:
            await callback.message.edit_text(
                f"У тебя пока нет ботов. (Твой ID: {user_id})", 
                reply_markup=main_menu_kb()
            )
        except TelegramBadRequest:
            pass
        await callback.answer()
        return

    # Формируем кнопки
    buttons = []
    for b in bots:
        bot_name = b.get('name', 'Без названия')
        bot_status = b.get('status', 'IDLE')
        buttons.append([InlineKeyboardButton(
            text=f"{bot_name} [{bot_status}]", 
            callback_data=f"manage_{b['id']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="Главное меню", callback_data="main_menu")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    try:
        await callback.message.edit_text("Твои боты:", reply_markup=kb)
    except TelegramBadRequest:
        pass
    
    await callback.answer()
# --- Меню управления ботом ---
@router.callback_query(F.data.startswith("manage_"))
async def process_manage_bot(callback: CallbackQuery):
    # 1. СРАЗУ отвечаем Telegram, чтобы кнопка не зависла
    try:
        await callback.answer()
    except:
        pass

    bot_id = callback.data.split("_")[1]
    user_id = str(callback.from_user.id)

    # 2. Делаем запрос (теперь мы знаем, что он работает)
    # Если он долгий, Telegram уже не выбьет ошибку answerCallbackQuery
    bots = await api_request("GET", f"/api/free/bots/{user_id}")
    
    # Ищем конкретного бота в списке
    bot = next((b for b in bots if str(b['id']) == bot_id), None)

    if not bot:
        try:
            await callback.message.edit_text("Бот не найден или был удален.", reply_markup=main_menu_kb())
        except:
            await callback.answer("Бот не найден", show_alert=True)
        return

    # Отображаем меню управления ботом
    text = f"🤖 Управление ботом: <b>{bot.get('name')}</b>\nСтатус: {bot.get('status')}"
    
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=manage_bot_kb(bot_id))
    except Exception as e:
        logging.error(f"Ошибка отрисовки меню управления: {e}")

# --- Запуск / Остановка ---
@router.callback_query(F.data.startswith("start_"))
async def start_bot_handler(callback: CallbackQuery):
    bot_id = callback.data.split("_")[1]
    await callback.answer("Запускаю...")
    res = await api_request("POST", f"/api/free/bots/{bot_id}/start")
    if res and res.get("status") == "ok":
        await process_manage_bot(callback, FSMContext(storage=dp.storage, key=callback.message.chat.id))
    else:
        await callback.message.answer("Ошибка запуска.")

@router.callback_query(F.data.startswith("stop_"))
async def stop_bot_handler(callback: CallbackQuery):
    bot_id = callback.data.split("_")[1]
    await callback.answer("Останавливаю...")
    await api_request("POST", f"/api/free/bots/{bot_id}/stop")
    await process_manage_bot(callback, FSMContext(storage=dp.storage, key=callback.message.chat.id))

# --- Редактирование параметров (config) ---
async def fetch_and_update_config(user_id: str, bot_id: str, updates: dict):
    bots = await api_request("GET", f"/api/free/bots/{user_id}")
    bot_data = next((b for b in (bots or []) if b["id"] == bot_id), None)
    if not bot_data: return False
    
    current_cfg = bot_data.get("config", {})
    # Мержим обновления в текущий конфиг
    for k, v in updates.items():
        if k == "settings":
            current_cfg["settings"] = {**current_cfg.get("settings", {}), **v}
        elif k == "triggers_append":
            current_cfg.setdefault("triggers", []).append(v)
        else:
            current_cfg[k] = v

    payload = {"user_id": user_id, "config": current_cfg}
    res = await api_request("PUT", f"/api/free/bots/{bot_id}/config", json_data=payload)
    return bool(res)

@router.callback_query(F.data.startswith("edit_welcome_"))
async def edit_welcome(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BotEditStates.waiting_for_welcome)
    await callback.message.answer("Отправь новый текст приветственного сообщения:")

@router.message(BotEditStates.waiting_for_welcome)
async def save_welcome(message: Message, state: FSMContext):
    data = await state.get_data()
    bot_id = data.get("current_bot_id")
    if await fetch_and_update_config(str(message.from_user.id), bot_id, {"welcomeMessage": message.text}):
        await message.answer("✅Приветствие обновлено!")
    await state.clear()

@router.callback_query(F.data.startswith("edit_firstmsg_"))
async def edit_first_msg(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BotEditStates.waiting_for_first_msg)
    await callback.message.answer("Отправь заголовок/текст, который будет прикрепляться перед первым обращением юзера к админу:")

@router.message(BotEditStates.waiting_for_first_msg)
async def save_first_msg(message: Message, state: FSMContext):
    data = await state.get_data()
    if await fetch_and_update_config(str(message.from_user.id), data["current_bot_id"], {"settings": {"firstMessageHeader": message.text}}):
        await message.answer("Текст первого обращения обновлен!")
    await state.clear()

@router.callback_query(F.data.startswith("edit_admin_"))
async def edit_admin(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BotEditStates.waiting_for_admin_chat)
    await callback.message.answer("Отправь ID чата или перешли сообщение из группы, куда должны падать заявки:")

@router.message(BotEditStates.waiting_for_admin_chat)
async def save_admin(message: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = str(message.forward_from_chat.id) if message.forward_from_chat else message.text.strip()
    
    if await fetch_and_update_config(str(message.from_user.id), data["current_bot_id"], {"adminChatId": chat_id}):
        await message.answer(f"Админ-чат обновлен на: {chat_id}")
    await state.clear()

# --- Триггеры ---
@router.callback_query(F.data.startswith("add_trigger_"))
async def add_trigger_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BotEditStates.waiting_for_trigger_keyword)
    await callback.message.answer("Отправь ключевое слово (на что должен реагировать бот):")

@router.message(BotEditStates.waiting_for_trigger_keyword)
async def add_trigger_keyword(message: Message, state: FSMContext):
    await state.update_data(trigger_kw=message.text.strip())
    await state.set_state(BotEditStates.waiting_for_trigger_reply)
    await message.answer("Отлично. Теперь отправь текст, которым бот должен ответить на это слово:")

@router.message(BotEditStates.waiting_for_trigger_reply)
async def add_trigger_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    trigger = {"keyword": data["trigger_kw"], "reply": message.text.strip(), "matchType": "exact"}
    
    if await fetch_and_update_config(str(message.from_user.id), data["current_bot_id"], {"triggers_append": trigger}):
        await message.answer(f"Триггер «{data['trigger_kw']}» успешно добавлен!")
    await state.clear()

# --- Рассылка ---
@router.callback_query(F.data.startswith("broadcast_"))
async def broadcast_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BotEditStates.waiting_for_broadcast)
    await callback.message.answer("Отправь сообщение, которое нужно разослать всем пользователям этого бота:")

@router.message(BotEditStates.waiting_for_broadcast)
async def broadcast_send(message: Message, state: FSMContext):
    data = await state.get_data()
    bot_id = data.get("current_bot_id")
    
    msg = await message.answer("⏳ Рассылаю...")
    res = await api_request("POST", "/api/bots/broadcast", json_data={"botIds": [bot_id], "message": message.text})
    
    if res:
        await msg.edit_text(f"Рассылка завершена!\nУспешно: {res.get('success', 0)}\nОшибок: {res.get('failed', 0)}")
    else:
        await msg.edit_text("Ошибка при рассылке.")
    await state.clear()


async def main():
    dp.include_router(router)
    logging.info("Starting Constructor Bot...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
