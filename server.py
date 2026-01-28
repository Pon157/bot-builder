
import asyncio
import logging
import json
import os
import time
import re
import uuid
import secrets
import sys
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ContentType
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter
import uvicorn

# --- Инициализация окружения и Логирование ---
# Попытка определить рабочую директорию для корректной работы путей
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("server.log", encoding='utf-8')
    ]
)
logger = logging.getLogger("BotEngineCore")

# --- Настройки и Константы ---
DB_FILE = "database.json"
# Секретный токен для генерации ключей через API (можно менять в .env)
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")

# --- Модели данных для API ---
class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    id: str
    username: str
    email: str
    password: str
    licenseExpiresAt: int
    trialUsed: bool
    balance: float
    botsCreated: int

class BroadcastRequest(BaseModel):
    botIds: List[str]
    message: str

class KeyGenRequest(BaseModel):
    months: int

# --- Ядро Базы Данных (JSON Storage) ---
db_content = {
    "users": [],
    "bots": [],
    "issued_keys": [],
    "system_logs": []
}

def save_db():
    """Атомарное сохранение базы данных во избежание повреждения файлов."""
    temp_file = f"{DB_FILE}.tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(db_content, f, ensure_ascii=False, indent=2)
        os.replace(temp_file, DB_FILE)
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения БД: {e}")

def load_db():
    """Загрузка базы данных при старте сервера."""
    global db_content
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                # Безопасное обновление ключей
                for key in db_content.keys():
                    if key in loaded:
                        db_content[key] = loaded[key]
            logger.info(f"✅ БД загружена: {len(db_content['users'])} юзеров, {len(db_content['bots'])} ботов")
        except Exception as e:
            logger.error(f"❌ Ошибка чтения БД: {e}. Создана новая структура.")
            save_db()
    else:
        save_db()

# --- Вспомогательные функции бизнес-логики ---

def add_bot_log(bot_id: str, log_type: str, text: str, code: str = None):
    """Добавление записи в консоль конкретного бота."""
    bot = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not bot: return
    log_entry = {
        "id": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "type": log_type,
        "text": text,
        "code": code
    }
    if "logs" not in bot: bot["logs"] = []
    bot["logs"].insert(0, log_entry)
    bot["logs"] = bot["logs"][:150] # Храним последние 150 логов
    save_db()

def update_bot_stats(bot_id: str, direction: str):
    """Обновление счетчиков статистики сообщений."""
    bot = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not bot: return
    
    if "stats" not in bot or not bot["stats"]:
        bot["stats"] = {
            "totalMessages": 0, "incomingToday": 0, "outgoingToday": 0,
            "bannedCount": 0, "history": [], "activeUsers24h": 0
        }
    
    bot["stats"]["totalMessages"] += 1
    if direction == "incoming":
        bot["stats"]["incomingToday"] += 1
    else:
        bot["stats"]["outgoingToday"] += 1
    
    # Обновление истории для графика (раз в день)
    today_str = datetime.now().strftime("%d.%m")
    history = bot["stats"].setdefault("history", [])
    today_point = next((p for p in history if p["date"] == today_str), None)
    
    if not today_point:
        today_point = {"date": today_str, "incoming": 0, "outgoing": 0}
        history.append(today_point)
        if len(history) > 7: history.pop(0) # Только за неделю
        
    today_point[direction] += 1
    save_db()

def is_license_active(owner_id: str) -> bool:
    """Проверка срока действия лицензии пользователя."""
    user = next((u for u in db_content["users"] if str(u["id"]) == str(owner_id)), None)
    if not user: return False
    return int(user.get("licenseExpiresAt", 0)) > int(time.time() * 1000)

# --- Состояние запущенных инстансов ---
active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}

# --- ГПТ/Шаблонизатор ---
def format_admin_notification(template: str, m: Message, btn_text: str = "") -> str:
    """Заменяет теги в тексте уведомления для админа."""
    if not template: return f"🆘 Новое обращение!\nОт: {m.from_user.full_name}\nID: {m.from_user.id}"
    res = template.replace("{{id}}", str(m.from_user.id))
    res = res.replace("{{name}}", m.from_user.full_name or "Unknown")
    res = res.replace("{{username}}", f"@{m.from_user.username}" if m.from_user.username else "нет")
    res = res.replace("{{button}}", btn_text)
    return res

# --- Логика Бота (Worker) ---
async def bot_worker_task(bot_id: str, token: str):
    """Изолированная задача для работы одного Telegram бота."""
    logger.info(f"🤖 Запуск воркера для бота {bot_id}")
    session = AiohttpSession()
    bot = Bot(token=token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    active_bots[bot_id] = bot
    dp = Dispatcher()
    router = Router()

    @router.message(CommandStart())
    async def cmd_start(m: Message):
        config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not config or not is_license_active(config["ownerId"]): return

        # Регистрация пользователя в локальной БД бота
        if "connectedUsers" not in config: config["connectedUsers"] = []
        user = next((u for u in config["connectedUsers"] if u["id"] == m.from_user.id), None)
        
        if not user:
            user = {
                "id": m.from_user.id, "first_name": m.from_user.first_name,
                "username": m.from_user.username, "joined_at": int(time.time()),
                "is_banned": False, "is_active": True, "warns": 0, "thread_id": None
            }
            config["connectedUsers"].append(user)
            config["usersCount"] = len(config["connectedUsers"])
            add_bot_log(bot_id, "info", f"👤 Новый пользователь: {m.from_user.full_name} ({m.from_user.id})")
        
        # Подписка на рассылки (ID чата)
        if "subscribers" not in config: config["subscribers"] = []
        if m.from_user.id not in config["subscribers"]:
            config["subscribers"].append(m.from_user.id)
        
        save_db()
        if user.get("is_banned"): return

        kb_buttons = []
        for btn in config.get("buttons", []):
            if btn.get("text"): kb_buttons.append([KeyboardButton(text=btn["text"])])
        
        kb = ReplyKeyboardMarkup(keyboard=kb_buttons, resize_keyboard=True) if kb_buttons else None
        await m.answer(config.get("welcomeMessage", "Привет!"), reply_markup=kb)

    @router.message(Command("id"))
    async def cmd_id(m: Message):
        await m.answer(f"Твой ID: <code>{m.from_user.id}</code>\nID этого чата: <code>{m.chat.id}</code>")

    @router.message()
    async def global_handler(m: Message):
        config = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
        if not config or not is_license_active(config["ownerId"]): return
        admin_id = config.get("adminChatId")
        if not admin_id: return

        # --- ЛОГИКА АДМИНА ---
        if str(m.chat.id) == str(admin_id):
            target_id = None
            # 1. Ответ через топик (Forum)
            if m.message_thread_id:
                user = next((u for u in config.get("connectedUsers", []) if u.get("thread_id") == m.message_thread_id), None)
                if user: target_id = user["id"]
            
            # 2. Ответ через Reply (Livegram style)
            if not target_id and m.reply_to_message:
                match = re.search(r"ID: (\d+)", m.reply_to_message.text or m.reply_to_message.caption or "")
                if match: target_id = int(match.group(1))
            
            if target_id:
                try:
                    await bot.copy_message(chat_id=target_id, from_chat_id=m.chat.id, message_id=m.message_id)
                    update_bot_stats(bot_id, "outgoing")
                except TelegramForbiddenError:
                    await m.reply("❌ Пользователь заблокировал бота.")
                except Exception as e:
                    await m.reply(f"❌ Ошибка отправки: {e}")
            return

        # --- ЛОГИКА ПОЛЬЗОВАТЕЛЯ ---
        user = next((u for u in config.get("connectedUsers", []) if u["id"] == m.from_user.id), None)
        if not user or user.get("is_banned"): return

        # Проверка кнопок и триггеров
        if m.text:
            text_low = m.text.lower()
            # Кнопки
            for btn in config.get("buttons", []):
                if btn.get("text") and btn["text"].lower() == text_low:
                    if btn.get("type") == "request":
                        template = btn.get("adminTemplate", "🆘 Обращение!\nID: {{id}}")
                        info = format_admin_notification(template, m, btn["text"])
                        
                        thread_id = None
                        if config.get("settings", {}).get("topicPerRequest"):
                            try:
                                topic = await bot.create_forum_topic(admin_id, f"Ticket: {m.from_user.first_name}")
                                thread_id = topic.message_thread_id
                            except: pass
                        elif config.get("settings", {}).get("useTopics") and user.get("thread_id"):
                            thread_id = user["thread_id"]
                            
                        await bot.send_message(admin_id, info, message_thread_id=thread_id)
                    
                    await m.answer(btn.get("response", "Принято!"))
                    update_bot_stats(bot_id, "outgoing")
                    return

            # Текстовые триггеры
            for trig in config.get("triggers", []):
                if trig.get("keyword") and trig["keyword"].lower() in text_low:
                    await m.answer(trig.get("response", "Понял вас!"))
                    update_bot_stats(bot_id, "outgoing")
                    return

        # Пересылка сообщения админу (Feedback)
        settings = config.get("settings", {})
        use_topics = settings.get("useTopics", False)
        thread_id = None

        if use_topics:
            if not user.get("thread_id"):
                try:
                    topic_name = f"{m.from_user.first_name} [{m.from_user.id}]"
                    new_topic = await bot.create_forum_topic(admin_id, topic_name)
                    user["thread_id"] = new_topic.message_thread_id
                    save_db()
                    header = f"👤 <b>Новый чат</b>\nИмя: {m.from_user.full_name}\nID: <code>{m.from_user.id}</code>"
                    await bot.send_message(admin_id, header, message_thread_id=user["thread_id"])
                except Exception as e:
                    logger.warning(f"Failed to create topic for bot {bot_id}: {e}")
            thread_id = user.get("thread_id")

        try:
            if not use_topics:
                # В обычном чате добавляем подпись, чтобы админ знал, кому отвечать
                await bot.send_message(admin_id, f"📩 <b>Сообщение от ID: {m.from_user.id}</b>\nИмя: {m.from_user.full_name}")
            
            await bot.copy_message(admin_id, m.chat.id, m.message_id, message_thread_id=thread_id)
            update_bot_stats(bot_id, "incoming")
        except Exception as e:
            add_bot_log(bot_id, "error", f"Ошибка пересылки админу: {e}")

    # Запуск
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        add_bot_log(bot_id, "system", "🚀 Бот успешно запущен в облаке")
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logger.error(f"Worker {bot_id} fatal error: {e}")
        add_bot_log(bot_id, "error", f"Критический сбой: {e}")
    finally:
        await session.close()
        logger.info(f"Worker {bot_id} stopped.")

# --- Жизненный цикл FastAPI ---
@asynccontextmanager
async def server_lifespan(app: FastAPI):
    load_db()
    # Автостарт ботов, которые были запущены до перезагрузки
    for bot_cfg in db_content["bots"]:
        if bot_cfg.get("status") == "RUNNING":
            if is_license_active(bot_cfg["ownerId"]):
                active_tasks[bot_cfg["id"]] = asyncio.create_task(bot_worker_task(bot_cfg["id"], bot_cfg["token"]))
            else:
                bot_cfg["status"] = "IDLE"
                logger.warning(f"Бот {bot_cfg['id']} не запущен: лицензия истекла.")
    save_db()
    yield
    # Завершение всех ботов при выключении сервера
    for bid, task in active_tasks.items():
        task.cancel()
    logger.info("Сервер остановлен, задачи очищены.")

# --- FastAPI Приложение ---
app = FastAPI(lifespan=server_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.get("/api/ping")
async def api_ping():
    return {"status": "online", "time": int(time.time())}

@app.post("/api/auth/register")
async def api_register(req: RegisterRequest):
    if any(u["email"] == req.email for u in db_content["users"]):
        raise HTTPException(400, "User already exists")
    db_content["users"].append(req.dict())
    save_db()
    return req

@app.post("/api/auth/login")
async def api_login(req: LoginRequest):
    user = next((u for u in db_content["users"] if u["email"] == req.email and u["password"] == req.password), None)
    if not user:
        raise HTTPException(401, "Invalid email or password")
    return user

@app.get("/api/bots/{user_id}")
async def api_get_user_bots(user_id: str):
    user_bots = [b for b in db_content["bots"] if str(b["ownerId"]) == str(user_id)]
    # Синхронизация статусов с активными задачами
    for b in user_bots:
        b["status"] = "RUNNING" if b["id"] in active_tasks and not active_tasks[b["id"]].done() else "IDLE"
    return user_bots

@app.post("/api/bots/save")
async def api_save_bot(bot_data: dict):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == bot_data["id"]), -1)
    if idx >= 0:
        # Сохраняем важные поля, которые не приходят с фронта в полном объеме
        old = db_content["bots"][idx]
        bot_data["logs"] = old.get("logs", [])
        bot_data["connectedUsers"] = old.get("connectedUsers", [])
        bot_data["subscribers"] = old.get("subscribers", [])
        bot_data["stats"] = old.get("stats", {})
        db_content["bots"][idx] = bot_data
    else:
        db_content["bots"].append(bot_data)
    save_db()
    return {"status": "ok"}

@app.delete("/api/bots/delete/{bot_id}")
async def api_delete_bot(bot_id: str):
    idx = next((i for i, b in enumerate(db_content["bots"]) if b["id"] == bot_id), -1)
    if idx >= 0:
        if bot_id in active_tasks:
            active_tasks[bot_id].cancel()
            del active_tasks[bot_id]
        db_content["bots"].pop(idx)
        save_db()
        return {"status": "ok"}
    raise HTTPException(404, "Bot not found")

@app.post("/api/bots/start/{bot_id}")
async def api_start_bot(bot_id: str):
    bot_cfg = next((b for b in db_content["bots"] if b["id"] == bot_id), None)
    if not bot_cfg: raise HTTPException(404, "Bot config not found")
    
    if not is_license_active(bot_cfg["ownerId"]):
        raise HTTPException(403, "License expired. Please renew in profile.")

    if bot_id in active_tasks and not active_tasks[bot_id].done():
        return {"status": "already_running"}
    
    active_tasks[bot_id] = asyncio.create_task(bot_worker_task(bot_id, bot_cfg["token"]))
    bot_cfg["status"] = "RUNNING"
    save_db()
    return {"status": "started"}

@app.post("/api/bots/stop/{bot_id}")
async def api_stop_bot(bot_id: str):
    if bot_id in active_tasks:
        active_tasks[bot_id].cancel()
        del active_tasks[bot_id]
    
    if bot_id in active_bots:
        del active_bots[bot_id]

    for b in db_content["bots"]:
        if b["id"] == bot_id: b["status"] = "IDLE"
    
    save_db()
    return {"status": "stopped"}

@app.post("/api/broadcast")
async def api_broadcast(req: BroadcastRequest):
    results = {"success": 0, "failed": 0}
    for bid in req.botIds:
        bot = active_bots.get(bid)
        cfg = next((b for b in db_content["bots"] if b["id"] == bid), None)
        if bot and cfg:
            for uid in cfg.get("subscribers", []):
                try:
                    await bot.send_message(uid, req.message)
                    results["success"] += 1
                    update_bot_stats(bid, "outgoing")
                except Exception:
                    results["failed"] += 1
                await asyncio.sleep(0.05) # Защита от флуда
    return results

@app.post("/api/license/activate")
async def api_activate_license(req: dict):
    user_id = req.get("userId")
    key_str = req.get("key")
    
    user = next((u for u in db_content["users"] if str(u["id"]) == str(user_id)), None)
    key_obj = next((k for k in db_content["issued_keys"] if k["key"] == key_str and not k["used"]), None)
    
    if not user or not key_obj:
        raise HTTPException(400, "Invalid user or inactive key")
    
    months = key_obj["months"]
    now = int(time.time() * 1000)
    current_expiry = max(user.get("licenseExpiresAt", now), now)
    
    new_expiry = current_expiry + (months * 30 * 24 * 3600 * 1000)
    user["licenseExpiresAt"] = new_expiry
    key_obj["used"] = True
    key_obj["used_by"] = user_id
    key_obj["used_at"] = int(time.time())
    
    save_db()
    return {"status": "ok", "newExpiry": new_expiry}

@app.post("/api/admin/generate-key")
async def api_admin_gen_key(req: KeyGenRequest, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET:
        raise HTTPException(403, "Forbidden")
    
    new_key = f"BOT-{req.months}-{secrets.token_hex(3).upper()}"
    db_content["issued_keys"].append({
        "key": new_key,
        "months": req.months,
        "used": False,
        "created_at": int(time.time())
    })
    save_db()
    return {"key": new_key}

# --- Запуск Сервера ---
if __name__ == "__main__":
    load_db()
    logger.info("🚀 BotEngine Pro Server starting on port 8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
