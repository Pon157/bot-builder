import asyncio
import logging
import string
import os
import sys
import time
import json
import httpx
import secrets
import random
import hashlib
import uuid
from typing import Dict, List, Optional
from contextlib import asynccontextmanager
# ДОБАВИЛИ Request СЮДА:
from fastapi import FastAPI, HTTPException, Header, Request 
from fastapi.middleware.cors import CORSMiddleware
# ДОБАВИЛИ ЭТУ СТРОКУ:
from starlette.middleware.base import BaseHTTPMiddleware 
from cryptography.fernet import Fernet

# Импорт твоего сервиса почты (файл email_service.py должен быть рядом)
try:
    from email_service import EmailService
except ImportError:
    class EmailService:
        @staticmethod
        def send_verification_code(e, c): return True
        @staticmethod
        def send_password_reset(e, c): return True

# Импорты aiogram 3.x для массовой рассылки
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError

from starlette.concurrency import run_in_threadpool

from datetime import datetime  # <--- Добавь это в начало файла

from fastapi.staticfiles import StaticFiles
from fastapi import UploadFile, File
import shutil

from fastapi import UploadFile, File, Form

MAX_FILE_SIZE = 25 * 1024 * 1024

# ==========================================
# 1. ИНИЦИАЛИЗАЦИЯ И БЕЗОПАСНОСТЬ
# ==========================================
def init_env():
    if os.path.exists('.env'):
        with open('.env', 'r', encoding='utf-8-sig') as f:
            for l in f:
                l = l.strip()
                if l and not l.startswith('#') and '=' in l:
                    k, v = l.split('=', 1)
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")

init_env()

# Переменные окружения
S_URL = os.getenv("SUPABASE_URL", "").rstrip('/')
S_KEY = os.getenv("SUPABASE_KEY", "")
A_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")
# Читаем токен из .env (как ты просил запомнить)
E_KEY = os.getenv("ENCRYPTION_KEY")
A_SECRET = os.getenv("ADMIN_TOKEN")

if not E_KEY:
    # Генерируем временный, если забыл добавить в .env, но лучше прописать!
    E_KEY = Fernet.generate_key().decode()
    print(f"⚠️ ВНИМАНИЕ: ENCRYPTION_KEY не найден. Использую временный: {E_KEY}")

cipher = Fernet(E_KEY.encode())

# Токен выделенного бота для форм (пользователи добавляют его в чат)
FORM_BOT_TOKEN = os.getenv("FORM_BOT_TOKEN", "")

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("DialogEngineServer")

# --- Функции защиты данных ---
def hash_pwd(password: str) -> str:
    """Создает необратимый хеш пароля с солью."""
    salt = "dialog_engine_secure_2026_salt" 
    return hashlib.sha256((password + salt).encode()).hexdigest()

def encrypt_val(val: str) -> str:
    """Шифрует строку (например, токен бота)."""
    if not val: return ""
    return cipher.encrypt(val.encode()).decode()

def decrypt_val(val: str) -> str:
    """Расшифровывает строку. Если строка не зашифрована, вернет как есть."""
    if not val: return ""
    try:
        return cipher.decrypt(val.encode()).decode()
    except:
        return val 

# ==========================================
# 2. МЕНЕДЖЕР ПРОЦЕССОВ БОТОВ
# ==========================================
class BotManager:
    def __init__(self):
        self.procs: Dict[str, asyncio.subprocess.Process] = {}
        self.log_paths: Dict[str, str] = {}

    async def start_bot(self, bid: str, config: dict):
        """Запуск процесса бота с 'живым' пробросом логов в консоль и файл."""
        await self.stop_bot(bid)
        
        os.makedirs("active_bots", exist_ok=True)
        cfg_path = f"active_bots/cfg_{bid}.json"
        log_path = f"active_bots/bot_{bid}.log"
        
        # Расшифровываем токен (согласно твоим правилам хранения в .env)
        raw_token = decrypt_val(config.get('token', ''))
        config['token'] = raw_token
        
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        
        self.log_paths[bid] = log_path
        platform = config.get('platform', 'telegram').lower()
        _CORE = {'vk': 'vkbot_core.py', 'poster': 'poster_core.py', 'randomizer': 'randomizer_core.py'}
        bot_file = _CORE.get(platform, 'bot_core.py')
        
        try:
            # 1. Подготовка окружения
            env = os.environ.copy()
            # ПРИНУДИТЕЛЬНО отключаем буферизацию Python, чтобы логи писались мгновенно
            env["PYTHONUNBUFFERED"] = "1" 
            env.update({"SUPABASE_URL": S_URL, "SUPABASE_KEY": S_KEY, "BOT_ID": str(bid), "BOT_TOKEN": config.get("token", "")})
            
            # 2. Запуск через PIPE, чтобы сервер мог перехватывать поток
            p = await asyncio.create_subprocess_exec(
                sys.executable, bot_file, cfg_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            self.procs[bid] = p

            # 3. Фоновая задача для записи в файл И вывода в PM2 сервера
            async def log_reader(stream, file_path, prefix):
                with open(file_path, "a", encoding="utf-8") as f:
                    while True:
                        line = await stream.readline()
                        if not line: break
                        msg = line.decode('utf-8', errors='replace')
                        # Пишем в лог-файл для фронтенда
                        f.write(msg)
                        f.flush()
                        # Дублируем в консоль PM2 (увидишь через pm2 logs bot-api)
                        print(f"[{prefix}] {msg.strip()}", flush=True)

            asyncio.create_task(log_reader(p.stdout, log_path, f"STDOUT_{bid}"))
            asyncio.create_task(log_reader(p.stderr, log_path, f"STDERR_{bid}"))

            logger.info(f"🚀 Бот {bid} ({platform.upper()}) запущен (PID: {p.pid})")
            return True
        except Exception as e:
            logger.error(f"❌ Критическая ошибка запуска {bid}: {e}")
            return str(e)

    async def stop_bot(self, bot_id: str):
        """Остановка бота с очисткой ресурсов."""
        p = self.procs.get(bot_id)
        if p:
            try:
                p.terminate() 
                try:
                    await asyncio.wait_for(p.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    p.kill()
            except Exception as e:
                logger.error(f"Ошибка при остановке {bot_id}: {e}")
            
            self.procs.pop(bot_id, None)
            
        # Удаляем конфиг, чтобы не плодить мусор
        cfg_path = f"active_bots/cfg_{bot_id}.json"
        if os.path.exists(cfg_path):
            try: os.remove(cfg_path)
            except: pass

    def get_logs(self, bid: str):
        """Чтение последних строк лога бота."""
        path = self.log_paths.get(bid)
        if not path or not os.path.exists(path): return "Логи отсутствуют."
        try:
            with open(path, "r", encoding="utf-8") as f:
                return "".join(f.readlines()[-150:])
        except: return "Ошибка чтения логов."

pm = BotManager()

# ==========================================
# 3. НАСТРОЙКА API И LIFESPAN
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Логика при старте и выключении сервера."""
    logger.info("--- Сервер запускается ---")
    
    # Текущее время в мс для проверки лицензий при автостарте
    curr_ms = int(time.time() * 1000)
    
    async with httpx.AsyncClient(
        base_url=f"{S_URL}/rest/v1/", 
        headers={"apikey": S_KEY, "Authorization": f"Bearer {S_KEY}"}
    ) as client:
        try:
            # Автостарт только тех ботов, у которых статус RUNNING И лицензия НЕ истекла
            params = {
                "status": "eq.RUNNING",
                "license_expires_at": f"gt.{curr_ms}" # Больше текущего времени
            }
            r = await client.get("bots", params=params)
            
            if r.status_code == 200:
                active_bots = r.json()
                logger.info(f"Найдено {len(active_bots)} активных ботов для автозапуска")
                for b in active_bots:
                    inner_cfg = b.get("config") or {}
                    merged = {**inner_cfg, **b}
                    await pm.start_bot(b['id'], merged)
            else:
                logger.error(f"Ошибка получения списка ботов: {r.status_code}")
                
        except Exception as e:
            logger.error(f"Критическая ошибка автозапуска: {e}")
    
    yield  # В этой точке сервер начинает принимать запросы
    
    logger.info("--- Сервер останавливается ---")
    # Корректно завершаем процессы всех ботов
    for bid in list(pm.procs.keys()):
        await pm.stop_bot(bid)


# 1. Сначала инициализируем приложение
app = FastAPI(lifespan=lifespan)

# 2. Определяем класс защиты
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            f"connect-src 'self' {S_URL}; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline';"
        )
        return response

# 3. Добавляем Middleware (теперь переменная 'app' уже существует)
app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. Инициализируем глобальный клиент БД
db = httpx.AsyncClient(
    base_url=f"{S_URL}/rest/v1/", 
    headers={
        "apikey": S_KEY, 
        "Authorization": f"Bearer {S_KEY}", 
        "Content-Type": "application/json"
    }
)

# Загрузка файлов
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ==========================================
# 4. ЭНДПОИНТЫ АВТОРИЗАЦИИ
# ==========================================

@app.post("/api/auth/login")
async def login(d: dict):
    email = d['email'].lower()
    hpwd = hash_pwd(d['password'])
    r = await db.get("users", params={"email": f"eq.{email}", "password": f"eq.{hpwd}"})
    data = r.json()
    if not data: 
        raise HTTPException(401, "Неверный логин или пароль")
    return data[0]

@app.post("/api/auth/request-verification")
async def request_ver(d: dict):
    email = d['email'].lower()
    code = str(random.randint(100000, 999999))
    
    # Сохраняем код для регистрации
    await db.post("temp_codes", json={
        "email": email, "code": code, "type": "VERIFY"
    }, headers={"Prefer": "resolution=merge-duplicates"})
    
    # Используем run_in_threadpool, так как smtplib внутри EmailService — синхронный
    success = await run_in_threadpool(EmailService.send_verification_code, email, code)
    if success:
        return True
    raise HTTPException(500, "Ошибка почтового сервера")

@app.post("/api/auth/verify-and-register")
async def verify_reg(d: dict):
    email = d['email'].lower()
    
    # Проверка кода именно для регистрации
    r = await db.get("temp_codes", params={
        "email": f"eq.{email}", 
        "code": f"eq.{d['code']}",
        "type": "eq.VERIFY"
    })
    
    if not r.json():
        raise HTTPException(400, "Неверный код подтверждения")
    
    uid = f"u_{secrets.token_hex(4)}"
    
    user_data = {
        "id": uid,
        "username": d['username'],
        "email": email,
        "password": hash_pwd(d['password']), 
        "balance": 0,
        "license_expires_at": int(time.time()*1000) + 259200000, # +3 дня бонуса
        "marketing_consent": d.get('marketing_consent', False) 
    }
    
    await db.post("users", json=user_data)
    await db.delete("temp_codes", params={"email": f"eq.{email}"})
    
    return user_data

@app.post("/api/auth/forgot-password")
async def forgot_p(d: dict):
    email = d['email'].lower()
    
    # Получаем данные пользователя
    r = await db.get("users", params={"email": f"eq.{email}"})
    u_data = r.json()
    
    # ЛОГ ДЛЯ ДЕБАГА (удалишь потом)
    print(f"DEBUG: Поиск юзера {email}, результат: {u_data}")
    
    # Если список пустой, письмо не шлем
    if not u_data: 
        return True 
    
    code = str(random.randint(100000, 999999))
    
    # Сохраняем код в базу
    await db.post("temp_codes", 
                  json={"email": email, "code": code, "type": "RESET"}, 
                  headers={"Prefer": "resolution=merge-duplicates"})
    
    # ОТПРАВКА ПИСЬМА: Обязательно через run_in_threadpool
    # так как smtplib внутри EmailService блокирует поток
    await run_in_threadpool(EmailService.send_password_reset, email, code)
    
    return True

@app.post("/api/auth/reset-password")
async def reset_p(d: dict):
    email = d['email'].lower()
    
    # Ищем код с типом RESET
    r = await db.get("temp_codes", params={
        "email": f"eq.{email}", 
        "code": f"eq.{d['code']}", 
        "type": "eq.RESET"
    })
    
    if not r.json(): 
        raise HTTPException(400, "Код недействителен или устарел")
    
    # Обновляем пароль
    new_hpwd = hash_pwd(d['newPassword'])
    await db.patch("users", params={"email": f"eq.{email}"}, json={"password": new_hpwd})
    
    # Удаляем код
    await db.delete("temp_codes", params={"email": f"eq.{email}", "type": "eq.RESET"})
    
    return True

# ==========================================
# 5. УПРАВЛЕНИЕ БОТАМИ
# ==========================================

@app.get("/api/auth/user/{user_id}")
async def get_user_data(user_id: str):
    """Возвращает данные пользователя. Если не найден — создаем заглушку, чтобы фронт не падал."""
    try:
        res = await db.get("users", params={"id": f"eq.{user_id}"})
        data = res.json()
        if res.status_code == 200 and len(data) > 0:
            return data[0]
        
        # Если юзера нет в БД, отдаем минимальный объект, чтобы редактор открылся
        return {"id": user_id, "email": "user@example.com", "role": "user"}
    except Exception as e:
        logger.error(f"Error fetching user {user_id}: {e}")
        raise HTTPException(status_code=404, detail="User not found")

@app.get("/api/bots/stats/{bot_id}")
async def get_bot_stats_api(bot_id: str):
    """Возвращает актуальную статистику бота напрямую из БД.
    
    Мержит данные из двух источников:
    - Колонка `stats` (JSONB) — основная, бот пишет сюда в реальном времени
    - Поле `config.stats` (JSONB внутри config) — резервный источник для старых ботов
    
    История объединяется по дате: для каждой даты берётся максимальное значение
    (чтобы не обнулить накопленные данные при мерже).
    """
    try:
        res = await db.get("bots", params={"id": f"eq.{bot_id}"})
        
        if res.status_code != 200 or not res.json():
            return {"stats": {"history": [], "totalMessages": 0}}

        bot_data = res.json()[0]
        
        def safe_dict(val):
            if isinstance(val, dict): return val
            if isinstance(val, str):
                try: return json.loads(val)
                except: pass
            return {}

        db_stats  = safe_dict(bot_data.get("stats"))
        db_config = safe_dict(bot_data.get("config"))
        cfg_stats = safe_dict(db_config.get("stats"))

        # Объединяем числовые счётчики (берём максимум, чтобы не потерять данные)
        def max_val(key):
            return max(
                db_stats.get(key) or 0,
                cfg_stats.get(key) or 0
            )

        # Объединяем историю по датам
        history_map: dict = {}
        for src in [cfg_stats.get("history") or [], db_stats.get("history") or []]:
            for pt in src:
                date = pt.get("date", "??")
                if date not in history_map:
                    history_map[date] = {**pt}
                else:
                    # Берём максимальные значения для каждой даты
                    existing = history_map[date]
                    history_map[date] = {
                        "date": date,
                        "incoming":    max(existing.get("incoming", 0),    pt.get("incoming", 0)),
                        "outgoing":    max(existing.get("outgoing", 0),    pt.get("outgoing", 0)),
                        "totalUsers":  max(existing.get("totalUsers", 0),  pt.get("totalUsers", 0)),
                        "activeUsers": max(existing.get("activeUsers", 0), pt.get("activeUsers", 0)),
                    }

        # Сортируем по дате (формат DD.MM)
        def sort_key(item):
            try:
                d, m = item["date"].split(".")
                return (int(m), int(d))
            except:
                return (0, 0)

        merged_history = sorted(history_map.values(), key=sort_key)

        payload = {
            "history":       merged_history,
            "bannedCount":   max_val("bannedCount"),
            "incomingToday": max_val("incomingToday"),
            "outgoingToday": max_val("outgoingToday"),
            "totalMessages": max_val("totalMessages"),
            "activeUsers24h":max_val("activeUsers24h"),
            # Poster-specific fields
            "totalPosts":    max_val("totalPosts"),
        }

        # Для постера — восстанавливаем поле posts в истории (оно отдельно от incoming/outgoing)
        # Перебираем оба источника истории и добираем поле posts
        for src in [cfg_stats.get("history") or [], db_stats.get("history") or []]:
            for pt in src:
                date = pt.get("date", "??")
                if date in history_map and "posts" in pt:
                    existing = history_map[date]
                    existing["posts"] = max(existing.get("posts", 0), pt.get("posts", 0))

        logger.info(f"📊 Stats [{bot_id}]: {len(merged_history)} дней, {payload['totalMessages']} сообщений")
        return {"stats": payload}

    except Exception as e:
        logger.error(f"🚨 Stats API error: {e}", exc_info=True)
        return {"stats": {"history": [], "totalMessages": 0}}
        
@app.get("/api/bots/{user_id}")
async def get_user_bots(user_id: str):
    try:
        res = await db.get("bots", params={"owner_id": f"eq.{user_id}"})
        if res.status_code != 200:
            return []
        
        bots = res.json()
        
        for bot in bots:
            # 1. Безопасно достаем конфиг
            cfg = bot.get("config")
            if not cfg: 
                cfg = {}
            elif isinstance(cfg, str): 
                try:
                    cfg = json.loads(cfg)
                except:
                    cfg = {}
            
            # 2. РАСПАКОВКА ID (Сначала из колонок БД, потом из конфига)
            # Это самое важное: берем значение прямо из bot["admin_chat_id"], 
            # которое пришло из таблицы Supabase
            db_admin_id = bot.get("admin_chat_id")
            db_vk_id = bot.get("vk_group_id")
            
            # Если в колонках пусто, проверяем внутри конфига (на всякий случай)
            final_admin_id = db_admin_id if db_admin_id is not None else cfg.get("admin_chat_id") or cfg.get("adminChatId")
            final_vk_id = db_vk_id if db_vk_id is not None else cfg.get("vk_group_id") or cfg.get("vkGroupId")

            # 3. ПРИСВАИВАЕМ ВСЕ ВАРИАНТЫ ДЛЯ ФРОНТЕНДА
            bot["admin_chat_id"] = final_admin_id
            bot["adminChatId"] = final_admin_id
            bot["vk_group_id"] = final_vk_id
            bot["vkGroupId"] = final_vk_id

            # Остальные поля
            bot["welcomeMessage"] = cfg.get("welcomeMessage") or ""
            bot["buttons"]  = cfg.get("buttons")  if cfg.get("buttons")  is not None else []
            bot["triggers"] = cfg.get("triggers") if cfg.get("triggers") is not None else []

            # Поля для poster / randomizer / /broadcast
            bot["adminIds"]   = cfg.get("adminIds",   [])
            bot["channelId"]  = cfg.get("channelId",  "")
            bot["lotChannel"] = cfg.get("lotChannel", "")
            bot["botLink"]    = cfg.get("botLink",    "")
            # Poster: список каналов (мигрируем из channelId если channels нет)
            raw_channels = cfg.get("channels", [])
            if not raw_channels and cfg.get("channelId"):
                raw_channels = [cfg["channelId"]]
            bot["channels"] = raw_channels

            # Настройки
            bot["settings"] = cfg.get("settings") if isinstance(cfg.get("settings"), dict) else {
                "forwardToAdmin": True,
                "antiSpam": False,
                "showHeaderId": True,
                "useTopics": False
            }

            # Данные рандомайзера и постера — прямо в корень для фронтенда
            bot["lotteries"]    = cfg.get("lotteries", [])
            bot["users"]        = cfg.get("users",     [])
            bot["config"]       = cfg
            bot["ai"]           = cfg.get("ai", {})
            bot["welcomePhoto"] = cfg.get("welcomePhoto", "")
            bot["welcomeInline"]= cfg.get("welcomeInline", [])

            # --- КРИТИЧНО ДЛЯ АНАЛИТИКИ ---
            # Статистика может быть в колонке stats ИЛИ внутри config.stats.
            # Объединяем оба источника и кладём в bot.stats, чтобы фронтенд видел данные.
            db_stats = bot.get("stats")
            if isinstance(db_stats, str):
                try: db_stats = json.loads(db_stats)
                except: db_stats = {}
            if not isinstance(db_stats, dict): db_stats = {}
            
            cfg_stats = cfg.get("stats")
            if not isinstance(cfg_stats, dict): cfg_stats = {}
            
            # Мержим: приоритет у колонки stats (туда пишет бот), фолбек — cfg.stats
            merged_stats = {**cfg_stats, **db_stats} if db_stats else cfg_stats
            bot["stats"] = merged_stats
            
        return bots
    except Exception as e:
        logger.error(f"🚨 Error getting bots: {e}")
        return []

@app.post("/api/bots/save")
async def save_bot(b: dict):
    try:
        bid = b.get('id')
        if not bid: 
            raise HTTPException(400, "ID бота потерян")

        # 1. Получаем текущее состояние из БД
        old_r = await db.get("bots", params={"id": f"eq.{bid}"})
        if old_r.status_code != 200:
            logger.error(f"❌ Supabase error: {old_r.text}")
            raise HTTPException(old_r.status_code, "Ошибка связи с БД")

        bots = old_r.json()
        
        # --- ЛОГИКА СОЗДАНИЯ (UPSERT), если бота нет в базе ---
        if not bots:
            logger.warning(f"⚠️ Бот {bid} не найден — выполняем создание (upsert)")
            raw_tok = b.get("token", "")
            enc_tok = encrypt_val(raw_tok) if raw_tok and not str(raw_tok).startswith("gAAAA") else raw_tok
            
            _ai = [int(x) for x in (b.get("adminIds") or []) if str(x).strip().lstrip("-").isdigit()]
            upsert_payload = {
                "id": bid,
                "owner_id": b.get("owner_id", ""),
                "name": b.get("name", "Новый бот"),
                "token": enc_tok,
                "platform": b.get("platform", "telegram"),
                "status": "IDLE",
                "license_expires_at": int(time.time() * 1000) + (24 * 3600 * 1000),
                "created_at": int(time.time() * 1000),
                "config": {
                    "buttons": b.get("buttons", []),
                    "triggers": b.get("triggers", []),
                    "welcomeMessage": b.get("welcomeMessage", "Привет!"),
                    "settings": b.get("settings") or {"forwardToAdmin": True},
                    "connectedUsers": [],
                    "adminIds":   _ai,
                    "channelId":  b.get("channelId",  ""),
                    "lotChannel": b.get("lotChannel", ""),
                    "botLink":    b.get("botLink",    ""),
                    "lotteries":  [],
                    "users":      [],
                },
                "stats": {},
                "admin_chat_id": None,
                "vk_group_id": None
            }
            ins_res = await db.post("bots", json=upsert_payload)
            if ins_res.status_code not in [200, 201, 204]:
                 raise HTTPException(ins_res.status_code, f"Ошибка создания: {ins_res.text}")
            return {**upsert_payload, "id": bid}

        # --- ЛОГИКА ОБНОВЛЕНИЯ СУЩЕСТВУЮЩЕГО БОТА ---
        curr = bots[0]
        old_config = curr.get("config", {}) or {}
        inc_cfg = b.get("config", {}) if isinstance(b.get("config"), dict) else {}
        
        # Определяем платформу
        platform = b.get('platform') or curr.get('platform') or 'vk'

        def clean_int(val):
            if val is None or str(val).strip() in ["", "null", "None"]: 
                return None
            try: return int(float(str(val).strip()))
            except: return None

        # 3. УМНОЕ РАСПРЕДЕЛЕНИЕ ID ПО ПЛАТФОРМАМ
        # Для Telegram: adminChatId -> admin_chat_id колонка
        # Для VK: adminChatId (из фронтенда) -> vk_group_id колонка (это peer_id беседы/диалога)
        
        # Ищем ID из фронтенда для TG (adminChatId / admin_chat_id)
        tg_id_raw = (
            b.get("adminChatId") or b.get("admin_chat_id") or
            inc_cfg.get("adminChatId") or inc_cfg.get("admin_chat_id")
        )
        
        # Ищем VK peer_id (может прийти как vkGroupId или vk_group_id)
        vk_id_raw = (
            b.get("vkGroupId") or b.get("vk_group_id") or
            inc_cfg.get("vkGroupId") or inc_cfg.get("vk_group_id")
        )

        # Стартовые значения — берём из текущей записи в БД
        new_admin_id = curr.get("admin_chat_id")
        new_vk_id = curr.get("vk_group_id")

        if platform == 'vk':
            incoming_vk = vk_id_raw or tg_id_raw
            if incoming_vk is not None:
                new_vk_id = clean_int(incoming_vk)
            new_admin_id = None
        elif platform in ('poster', 'randomizer'):
            # Poster/randomizer не используют колонки admin_chat_id/vk_group_id
            new_admin_id = None
            new_vk_id    = None
        else:  # telegram
            if tg_id_raw is not None:
                new_admin_id = clean_int(tg_id_raw)
            new_vk_id = None

        # 4. СОБИРАЕМ КОНФИГ (JSONB)
        def get_val(key, default=None):
            val = b.get(key)
            if val is None: val = inc_cfg.get(key)
            if val is None: val = old_config.get(key)
            return val if val is not None else default

        # Специальная проверка для кнопок, чтобы они всегда были списком
        btns = get_val("buttons", [])
        if not isinstance(btns, list): btns = []

        # adminIds — список числовых ID администраторов для /broadcast
        raw_ai = (b.get("adminIds") or inc_cfg.get("adminIds") or old_config.get("adminIds") or [])
        if isinstance(raw_ai, str):
            raw_ai = [int(x.strip()) for x in raw_ai.split(",") if x.strip().lstrip("-").isdigit()]
        admin_ids_list = [int(x) for x in raw_ai if str(x).strip().lstrip("-").isdigit()] if raw_ai else []

        channel_id_val  = get_val("channelId",  old_config.get("channelId",  "")) or ""
        lot_channel_val = get_val("lotChannel", old_config.get("lotChannel", "")) or ""
        bot_link_val    = get_val("botLink",    old_config.get("botLink",    "")) or ""
        # Poster channels list
        raw_ch = b.get("channels") or inc_cfg.get("channels") or old_config.get("channels") or []
        if not raw_ch and channel_id_val:
            raw_ch = [channel_id_val]
        channels_val = [c for c in raw_ch if c and str(c).strip()]

        # AI конфиг
        raw_ai_cfg = b.get("ai") or inc_cfg.get("ai") or old_config.get("ai") or {}
        if not isinstance(raw_ai_cfg, dict): raw_ai_cfg = {}
        ai_config = {
            "enabled":         raw_ai_cfg.get("enabled", False),
            "mode":            raw_ai_cfg.get("mode", "off"),
            "buttonName":      raw_ai_cfg.get("buttonName", "ИИ-ассистент"),
            "systemPrompt":    raw_ai_cfg.get("systemPrompt", "Ты полезный ИИ-ассистент."),
            "maxTokensPerReply": int(raw_ai_cfg.get("maxTokensPerReply", 800)),
            "contextMessages": int(raw_ai_cfg.get("contextMessages", 6)),
            "model":           raw_ai_cfg.get("model", "qwen-turbo"),
        }

        ui_config = {
            "stats": old_config.get("stats", {}),
            "buttons": btns,
            "triggers": get_val("triggers", []),
            "welcomeMessage": get_val("welcomeMessage", "Привет!"),
            "welcomePhoto":   get_val("welcomePhoto", ""),
            "welcomeInline":  get_val("welcomeInline", []),
            "settings": {**old_config.get("settings", {}), **(b.get("settings") or inc_cfg.get("settings") or {})},
            "connectedUsers": old_config.get("connectedUsers", []),
            "admin_chat_id": new_admin_id,
            "adminChatId":   new_admin_id,
            "vk_group_id":   new_vk_id,
            "vkGroupId":     new_vk_id,
            "adminIds":   admin_ids_list,
            "channelId":  channel_id_val,
            "channels":   channels_val,
            "lotChannel": lot_channel_val,
            "botLink":    bot_link_val,
            "lotteries":  old_config.get("lotteries", []),
            "users":      old_config.get("users",     []),
            # AI-конфиг
            "ai": ai_config,
        }

        # 5. ТОКЕН (Берем новый или оставляем старый зашифрованный)
        raw_token = b.get('token')
        final_token = curr.get('token')
        if raw_token and not str(raw_token).startswith('gAAAA') and len(str(raw_token)) > 5:
            final_token = encrypt_val(raw_token)

        # 6. ФОРМИРУЕМ ПАКЕТ ДЛЯ PATCH (Колонки таблицы Supabase)
        db_payload = {
            "name": b.get("name") or curr.get("name"),
            "token": final_token,
            "platform": platform,
            "config": ui_config,
            "admin_chat_id": new_admin_id, 
            "vk_group_id": new_vk_id       
        }

        # 7. ОТПРАВКА В БАЗУ ДАННЫХ
        logger.info(f"💾 Saving bot {bid} ({platform}). DB Payload: TG={new_admin_id}, VK={new_vk_id}")
        res = await db.patch("bots", params={"id": f"eq.{bid}"}, json=db_payload)
        
        if res.status_code not in [200, 201, 204]:
            logger.error(f"❌ Patch error: {res.text}")
            raise HTTPException(res.status_code, f"Ошибка сохранения в БД: {res.text}")

        # 8. ВОЗВРАТ АКТУАЛЬНЫХ ДАННЫХ
        return {
            **curr,
            **db_payload,
            **ui_config,
            "adminChatId":  new_admin_id,
            "admin_chat_id": new_admin_id,
            "vkGroupId":    new_vk_id,
            "vk_group_id":  new_vk_id,
            "adminIds":     admin_ids_list,
            "channelId":    channel_id_val,
            "channels":     channels_val,
            "lotChannel":   lot_channel_val,
            "botLink":      bot_link_val,
            "stats": curr.get("stats") or old_config.get("stats") or {},
            "id": bid
        }

    except Exception as e:
        logger.error(f"🚨 Критическая ошибка сохранения: {e}", exc_info=True)
        raise HTTPException(500, str(e))
        
@app.post("/api/bots/start")
async def start_handler(req: dict):
    bid = req.get('id')
    
    # 1. Получаем данные бота и сразу данные владельца через join (если позволяет БД)
    # Или делаем два запроса для надежности
    r = await db.get("bots", params={"id": f"eq.{bid}"})
    if not r.json(): 
        raise HTTPException(404, "Бот не найден")
    
    bot_data = r.json()[0]
    owner_id = bot_data.get('owner_id')

    # 2. ПРОВЕРКА НА БАН: Проверяем статус пользователя в таблице users
    u_res = await db.get("users", params={"id": f"eq.{owner_id}"})
    if u_res.status_code == 200 and u_res.json():
        user_data = u_res.json()[0]
        if user_data.get("is_banned") is True:
            # Если пользователь забанен, принудительно ставим боту статус BANNED
            await db.patch("bots", params={"id": f"eq.{bid}"}, json={"status": "BANNED"})
            logger.warning(f"🚫 Отказ в запуске: Владелец бота {bid} заблокирован.")
            raise HTTPException(403, "Ваш аккаунт заблокирован. Запуск ботов невозможен.")

    # 3. Мержим config (JSONB) с корневыми полями — vkbot_core ждёт platform, admin_chat_id и т.д. на верхнем уровне
    inner_cfg = bot_data.get("config") or {}
    merged = {**inner_cfg, **bot_data}
    if await pm.start_bot(bid, merged) is True:
        await db.patch("bots", params={"id": f"eq.{bid}"}, json={"status": "RUNNING"})
        logger.info(f"🚀 Бот {bid} успешно запущен")
        return {"status": "success"}
    
    raise HTTPException(500, "Ошибка запуска процесса")

@app.post("/api/bots/stop/{bid}")
async def stop_handler(bid: str):
    await pm.stop_bot(bid)
    await db.patch("bots", params={"id": f"eq.{bid}"}, json={"status": "IDLE"})
    return True

@app.delete("/api/bots/delete/{uid}/{bid}")
async def delete_handler(uid: str, bid: str):
    await pm.stop_bot(bid)
    await db.delete("bots", params={"id": f"eq.{bid}", "owner_id": f"eq.{uid}"})
    return {"status": "deleted"}

@app.get("/api/bots/logs/{bid}")
async def get_bot_logs(bid: str):
    return {"logs": pm.get_logs(bid)}

# ==========================================
# 6. ЛИЦЕНЗИИ И АДМИН-ПАНЕЛЬ
# ==========================================

@app.post("/api/admin/generate-key")
async def gen_key(d: dict, x_admin_token: str = Header(None)):
    if x_admin_token != A_SECRET: raise HTTPException(401, "Admin only")

    key_type = d.get("key_type", "license")  # 'license' | 'ai_tokens'
    if key_type == "ai_tokens":
        tokens = int(d.get("tokens", 500000))
        key = f"AITOK-{secrets.token_hex(3).upper()}-{random.randint(100,999)}"
        payload = {"key": key, "months": 0, "days": 0, "used": False,
                   "key_type": "ai_tokens", "tokens": tokens}
    else:
        key = f"DE-{secrets.token_hex(3).upper()}-{random.randint(100,999)}"
        payload = {"key": key, "months": d.get('months', 1), "days": d.get('days', 0),
                   "used": False, "key_type": "license", "tokens": 0}

    await db.post("issued_keys", json=payload)
    return {"key": key, "key_type": key_type}

@app.post("/api/license/activate")
async def activate_lic(req: dict):
    key_code = req.get('key')
    bid = req.get('botId')
    
    # Ищем ключ
    rk = await db.get("issued_keys", params={"key": f"eq.{key_code}", "used": "eq.false"})
    if not rk.json(): return {"status": "error", "message": "Ключ недействителен или уже активирован"}
    
    k_data = rk.json()[0]
    # Считаем время
    added_ms = (k_data['months'] * 30 * 86400000) + (k_data['days'] * 86400000)
    
    # Обновляем срок бота
    rb = await db.get("bots", params={"id": f"eq.{bid}"})
    curr_time = int(time.time() * 1000)
    old_expiry = rb.json()[0].get("license_expires_at") or 0
    new_expiry = max(old_expiry, curr_time) + added_ms
    
    await db.patch("bots", params={"id": f"eq.{bid}"}, json={"license_expires_at": new_expiry})
    await db.patch("issued_keys", params={"key": f"eq.{key_code}"}, json={"used": True, "used_by_bot": bid})
    
    return {"status": "ok", "new_expiry": new_expiry}

# ==========================================
# AI ТОКЕНЫ
# ==========================================

@app.post("/api/admin/generate-ai-key")
async def gen_ai_key(d: dict, x_admin_token: str = Header(None)):
    """Генерация ключа на AI-токены. Пишем в ai_token_keys."""
    if x_admin_token != A_SECRET: 
        raise HTTPException(401, "Admin only")
    
    tokens = int(d.get("tokens", 500000))
    price_rub = int(d.get("price_rub", 30))
    key = f"AITOK-{secrets.token_hex(3).upper()}-{random.randint(100,999)}"
    
    # Собираем payload строго под таблицу ai_token_keys
    payload = {
        "key": key,
        "tokens": tokens,
        "price_rub": price_rub,
        "used": False,
        "used_by_bot": None,
        # Для TIMESTAMPTZ в Supabase лучше всего подходит ISO формат
        "created_at": datetime.now().isoformat() 
    }
    
    # ВНИМАНИЕ: меняем таблицу на ai_token_keys
    res = await db.post("ai_token_keys", json=payload)
    
    if res.status_code not in [200, 201]:
        logger.error(f"Ошибка БД (ai_token_keys): {res.text}")
        raise HTTPException(500, f"Ошибка сохранения: {res.text}")

    return {"key": key, "tokens": tokens}

@app.get("/api/admin/ai-keys")
async def get_ai_keys(x_admin_token: str = Header(None)):
    if x_admin_token != A_SECRET: raise HTTPException(401)
    
    # Запрашиваем данные из новой таблицы
    res = await db.get("ai_token_keys?select=*&order=created_at.desc")
    return res.json()
    
@app.post("/api/ai/activate-tokens")
async def activate_ai_tokens(req: dict):
    """Активация ключа на AI-токены для конкретного бота."""
    key_code = req.get("key", "").strip().upper()
    bid = req.get("botId", "").strip()
    
    if not key_code or not bid:
        return {"status": "error", "message": "Ключ и botId обязательны"}

    # 1. Ищем ключ в ПРАВИЛЬНОЙ таблице (ai_token_keys), которую ты создал миграцией
    rk = await db.get("ai_token_keys", params={
        "key": f"eq.{key_code}",
        "used": "eq.false"
    })
    
    keys_found = rk.json()
    if not keys_found:
        return {"status": "error", "message": "Ключ недействителен или уже использован"}

    k_data = keys_found[0]
    tokens = int(k_data.get("tokens", 0))
    
    if tokens <= 0:
        return {"status": "error", "message": "Ключ содержит 0 токенов"}

    # 2. Проверяем, существует ли бот
    rb = await db.get("bots", params={"id": f"eq.{bid}"})
    if not rb.json():
        return {"status": "error", "message": "Бот не найден"}

    # 3. Обновляем или создаем баланс в ai_token_balances
    bal_r = await db.get("ai_token_balances", params={"bot_id": f"eq.{bid}"})
    balances = bal_r.json()
    
    if balances:
        # Если запись уже есть — плюсуем к текущему
        cur = balances[0]
        new_total = cur.get("tokens_total", 0) + tokens
        new_balance = cur.get("tokens_balance", 0) + tokens
        
        await db.patch("ai_token_balances",
            params={"bot_id": f"eq.{bid}"},
            json={
                "tokens_total": new_total, 
                "tokens_balance": new_balance,
                "updated_at": datetime.now().isoformat()
            }
        )
    else:
        # Если записи нет — создаем новую
        await db.post("ai_token_balances", json={
            "bot_id": bid,
            "tokens_total": tokens,
            "tokens_used": 0,
            "tokens_balance": tokens,
            "updated_at": datetime.now().isoformat()
        })

    # 4. Помечаем ключ использованным в таблице ai_token_keys
    await db.patch("ai_token_keys",
        params={"key": f"eq.{key_code}"},
        json={
            "used": True, 
            "used_by_bot": bid
        }
    )

    return {
        "status": "ok", 
        "tokens_added": tokens, 
        "message": f"✅ Начислено {tokens:,} токенов"
    }

@app.get("/api/ai/balance/{bot_id}")
async def get_ai_balance(bot_id: str):
    """Текущий баланс AI-токенов для бота."""
    r = await db.get("ai_token_balances", params={"bot_id": f"eq.{bot_id}"})
    if r.json():
        d = r.json()[0]
        return {
            "bot_id": bot_id,
            "tokens_total":   d.get("tokens_total", 0),
            "tokens_used":    d.get("tokens_used", 0),
            "tokens_balance": d.get("tokens_balance", 0)
        }
    return {"bot_id": bot_id, "tokens_total": 0, "tokens_used": 0, "tokens_balance": 0}

@app.get("/api/ai/usage/{bot_id}")
async def get_ai_usage(bot_id: str):
    """Лог расхода AI-токенов бота (последние 100 записей)."""
    r = await db.get("ai_token_usage_log", params={
        "bot_id": f"eq.{bot_id}",
        "order": "created_at.desc",
        "limit": "100"
    })
    return r.json() if r.status_code == 200 else []

@app.post("/api/ai/preview")
async def ai_preview_chat(req: dict):
    """Preview-чат с ИИ ассистентом из панели управления.
    
    Не расходует токены бота — использует системный баланс для тестирования.
    """
    import os, httpx as _httpx
    bot_id     = req.get("botId", "")
    message    = req.get("message", "").strip()
    sys_prompt = req.get("systemPrompt", "Ты полезный ИИ-ассистент.")
    model      = req.get("model", "gpt-4o")
    max_tok    = int(req.get("maxTokens", 800))

    if not message:
        raise HTTPException(400, "message is required")

    # Проверяем баланс токенов бота
    bal_r = await db.get("ai_token_balances", params={"bot_id": f"eq.{bot_id}"})
    balance = 0
    if bal_r.json():
        balance = bal_r.json()[0].get("tokens_balance", 0)
    if balance <= 0:
        return {"reply": "⚠️ AI-токены закончились. Активируйте ключ в разделе ИИ-ассистент."}

    api_key  = os.getenv("TIMEWEB_API_KEY") or os.getenv("QWEN_API_KEY", "")
    agent_id = os.getenv("TIMEWEB_AGENT_ID", "14ce55f9-dce2-4f2d-ad98-ff2cffe19ca2")
    ai_url   = f"https://agent.timeweb.cloud/api/v1/cloud-ai/agents/{agent_id}/v1/chat/completions"

    if not api_key:
        return {"reply": "❌ AI-ключ не настроен в .env (TIMEWEB_API_KEY)"}

    try:
        async with _httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                ai_url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user",   "content": message},
                    ],
                    "max_tokens": max_tok,
                    "temperature": 0.7,
                }
            )
            if resp.status_code == 200:
                data = resp.json()
                reply = data["choices"][0]["message"]["content"]
                total_tokens = data.get("usage", {}).get("total_tokens", 0)

                # Списываем токены с баланса бота (preview тоже расходует)
                if total_tokens > 0 and bot_id:
                    try:
                        headers_db = {
                            "apikey": S_KEY, "Authorization": f"Bearer {S_KEY}",
                            "Content-Type": "application/json"
                        }
                        async with _httpx.AsyncClient(timeout=5) as db_client:
                            await db_client.post(
                                f"{S_URL}/rest/v1/rpc/deduct_ai_tokens",
                                headers=headers_db,
                                json={"p_bot_id": bot_id, "p_amount": total_tokens}
                            )
                    except Exception:
                        pass

                return {"reply": reply, "tokens_used": total_tokens}
            else:
                logger.error(f"AI Preview error {resp.status_code}: {resp.text[:200]}")
                return {"reply": f"❌ Ошибка AI API: {resp.status_code}"}
    except Exception as e:
        logger.error(f"AI preview exception: {e}")
        return {"reply": "❌ Ошибка соединения с ИИ-сервисом"}

@app.post("/api/admin/upload-photo")
async def upload_welcome_photo(request: Request, x_admin_token: str = Header(None)):
    """Загрузка фото для стартового сообщения. Сохраняет в ./uploads/welcome/."""
    import shutil, uuid
    from fastapi import UploadFile
    form = await request.form()
    file: UploadFile = form.get("file")
    if not file:
        raise HTTPException(400, "Файл не передан")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
    fname = f"{uuid.uuid4().hex}.{ext}"
    save_dir = "./uploads/welcome"
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, fname)
    with open(save_path, "wb") as f_out:
        shutil.copyfileobj(file.file, f_out)
    # Возвращаем публичный URL (предполагаем что /uploads/ смонтирован)
    public_url = f"/uploads/welcome/{fname}"
    return {"url": public_url, "filename": fname}

# ==========================================
# 7. МАССОВАЯ РАССЫЛКА
# ==========================================

@app.post("/api/bots/broadcast")
async def broadcast_msg(d: dict):
    """Массовая рассылка сообщений всем пользователям бота.
    
    Поддерживает Telegram и VK ботов.
    Для VK использует httpx + VK API messages.send напрямую.
    """
    bot_ids = d.get('botIds', [])
    text    = d.get('message', '')
    if not text:
        return {"error": "Пустое сообщение"}

    results = {"success": 0, "failed": 0, "details": []}

    for bid in bot_ids:
        r = await db.get("bots", params={"id": f"eq.{bid}"})
        if not r.json():
            continue

        b_data   = r.json()[0]
        platform = (b_data.get('platform') or 'telegram').lower()
        token    = decrypt_val(b_data['token'])
        cfg      = b_data.get('config') or {}
        if isinstance(cfg, str):
            try: cfg = json.loads(cfg)
            except: cfg = {}
        users = cfg.get('connectedUsers', [])

        if platform == 'vk':
            # ── VK рассылка через httpx ──
            vk_api = "https://api.vk.com/method/messages.send"
            async with httpx.AsyncClient(timeout=10.0) as client:
                for u in users:
                    user_id = u['id'] if isinstance(u, dict) else u
                    # Пропускаем забаненных и неактивных
                    if isinstance(u, dict) and (u.get('is_banned') or u.get('is_active') is False):
                        continue
                    try:
                        resp = await client.post(vk_api, data={
                            "user_id": user_id,
                            "message": text,
                            "random_id": int(time.time() * 1000) % 2147483647,
                            "access_token": token,
                            "v": "5.199"
                        })
                        rj = resp.json()
                        if "error" in rj:
                            err_code = rj["error"].get("error_code", 0)
                            if err_code in (7, 900, 901, 902):
                                # Пользователь заблокировал бота — помечаем неактивным
                                if isinstance(u, dict):
                                    u["is_active"] = False
                            logger.warning(f"VK broadcast {bid}->{user_id}: {rj['error']}")
                            results["failed"] += 1
                        else:
                            results["success"] += 1
                    except Exception as e:
                        logger.warning(f"VK broadcast error {bid}->{user_id}: {e}")
                        results["failed"] += 1
                    await asyncio.sleep(0.05)  # ~20 msg/sec, VK лимит 20/сек

        else:
            # ── Telegram рассылка через aiogram ──
            try:
                async with Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML)) as bot:
                    for u in users:
                        user_id = u['id'] if isinstance(u, dict) else u
                        if isinstance(u, dict) and (u.get('is_banned') or u.get('is_active') is False):
                            continue
                        try:
                            await bot.send_message(user_id, text)
                            results["success"] += 1
                        except TelegramForbiddenError:
                            if isinstance(u, dict):
                                u["is_active"] = False
                            results["failed"] += 1
                        except Exception as e:
                            logger.warning(f"TG broadcast {bid}->{user_id}: {e}")
                            results["failed"] += 1
                        await asyncio.sleep(0.05)
            except Exception as e:
                logger.error(f"TG broadcast bot init error {bid}: {e}")
                results["failed"] += len(users)

    return results

# ==========================================
# 9. ADMIN PANEL & ANALYTICS (FULL SYSTEM)
# ==========================================

# 1. Загрузка конфигурации из .env
# ADMIN_TOKEN — это секретный ключ (пароль доступа к API)
# ADMIN_DATA — это JSON-словарь с логинами и паролями для входа
A_SECRET = os.getenv("ADMIN_TOKEN")

try:
    raw_admin_data = os.getenv("ADMIN_DATA", "{}")
    ADMIN_ACCOUNTS = json.loads(raw_admin_data)
    if not ADMIN_ACCOUNTS:
        logger.warning("⚠️ ВНИМАНИЕ: ADMIN_DATA в .env пуст или не задан!")
except Exception as e:
    logger.error(f"❌ ОШИБКА: Не удалось прочитать ADMIN_DATA: {e}")
    ADMIN_ACCOUNTS = {}

# Временное хранилище для гостевого доступа техподдержки
TEMP_ADMIN_ACCESS = {}

# 2. Функция проверки токена (Бронебойная)
def verify_admin_token(token: str) -> bool:
    if not token:
        return False
    # Очищаем от пробелов на случай случайных переносов строк в .env
    clean_token = token.strip()
    expected = A_SECRET.strip() if A_SECRET else ""
    
    is_valid = (clean_token == expected)
    if not is_valid:
        logger.error(f"🚫 ОТКАЗ ДОСТУПА: Пришел '{clean_token[:5]}...', ожидался '{expected[:5]}...'")
    return is_valid

# --- [ РОУТЫ АВТОРИЗАЦИИ ] ---

@app.post("/api/admin/login")
async def admin_login(d: dict):
    """Вход в админку и выдача токена доступа"""
    login = d.get('login')
    password = d.get('password')
    
    if login in ADMIN_ACCOUNTS and ADMIN_ACCOUNTS[login] == password:
        logger.info(f"🔑 Админ успешно вошел: {login}")
        # Возвращаем A_SECRET — именно его фронтенд будет слать в x-admin-token
        return {"token": A_SECRET, "role": "admin", "name": login}
    
    logger.warning(f"❌ Неудачная попытка входа в админку: {login}")
    raise HTTPException(401, "Неверный логин или пароль")

# --- [ ДАШБОРД И СТАТИСТИКА ] ---

@app.get("/api/admin/dashboard")
async def get_admin_dashboard(x_admin_token: str = Header(None)):
    if not verify_admin_token(x_admin_token):
        raise HTTPException(401, "Invalid admin token")

    try:
        # 1. Считаем пользователей
        u_req = await db.get("users", params={"select": "count"})
        # Supabase возвращает count в заголовке Content-Range, если запросить с head/count, 
        # но через простой get JSON вернет весь список. 
        # Для оптимизации лучше использовать count=exact, но пока загрузим списки (если база небольшая)
        
        users = (await db.get("users")).json()
        bots = (await db.get("bots")).json()
        keys = (await db.get("issued_keys")).json()
        
        # Считаем сообщения за сегодня для статистики
        today_start = datetime.now().replace(hour=0, minute=0, second=0).isoformat()
        msgs_today_req = await db.get("bot_messages", params={"created_at": f"gte.{today_start}", "select": "count"})
        # Если API Supabase настроен верно, можно получить count. Если нет - берем длину.
        # Для надежности в рамках текущего кода (где db.get возвращает json):
        
        # ПРИМЕЧАНИЕ: При большой БД это нужно переделать на select=count
        
        active_bots_count = len([b for b in bots if b.get('status') == 'RUNNING'])
        
        return {
            "total_users": len(users),
            "total_bots": len(bots),
            "active_bots": active_bots_count,
            "total_keys": len(keys),
            "revenue": len([k for k in keys if k.get('used')]) * 10, # Пример: $10 за ключ
            "msg_traffic": "N/A" # Сложно посчитать без count(*) запроса
        }
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return {"total_users": 0, "total_bots": 0, "active_bots": 0}

# --- [ УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ ] ---

@app.get("/api/admin/users")
async def get_all_users(x_admin_token: str = Header(None)):
    if not verify_admin_token(x_admin_token): raise HTTPException(403)
    # Получаем юзеров, сортируем по дате регистрации
    r = await db.get("users", params={"select": "*", "order": "created_at.desc"})
    return r.json()

@app.post("/api/admin/user/ban")
async def admin_ban_user(d: dict, x_admin_token: str = Header(None)):
    if not verify_admin_token(x_admin_token): raise HTTPException(403)
    uid = d.get('user_id')
    is_banned = d.get('is_banned', True) # True = забанить, False = разбанить
    
    # Обновляем юзера
    await db.patch("users", params={"id": f"eq.{uid}"}, json={"is_banned": is_banned})
    
    if is_banned:
        # Стопаем всех ботов
        bots = await db.get("bots", params={"owner_id": f"eq.{uid}"})
        for b in bots.json():
            await pm.stop_bot(b['id'])
            await db.patch("bots", params={"id": f"eq.{b['id']}"}, json={"status": "BANNED"})
    
    return {"status": "success", "banned": is_banned}

# --- [ УПРАВЛЕНИЕ БОТАМИ ] ---

@app.get("/api/admin/bots")
async def get_all_bots(x_admin_token: str = Header(None)):
    if not verify_admin_token(x_admin_token): raise HTTPException(403)
    # Тянем ботов с инфой о владельце через join
    r = await db.get("bots", params={"select": "*, owner:users(email, username)", "order": "created_at.desc"})
    return r.json()

@app.post("/api/admin/bot/action")
async def admin_bot_action(d: dict, x_admin_token: str = Header(None)):
    if not verify_admin_token(x_admin_token): raise HTTPException(403)
    bid = d.get('bot_id')
    action = d.get('action') # 'start', 'stop', 'delete'
    
    if action == 'stop':
        await pm.stop_bot(bid)
        await db.patch("bots", params={"id": f"eq.{bid}"}, json={"status": "IDLE"})
    elif action == 'start':
        res = await db.get("bots", params={"id": f"eq.{bid}"})
        if res.status_code == 200 and res.json():
            await start_bot_process(res.json()[0])
    elif action == 'delete':
        await pm.stop_bot(bid)
        await db.delete("bots", params={"id": f"eq.{bid}"})
    
    return {"status": "ok", "action": action}

# --- [ ЛИЦЕНЗИОННЫЕ КЛЮЧИ ] ---

@app.get("/api/admin/keys")
async def get_all_keys(x_admin_token: str = Header(None)):
    if not verify_admin_token(x_admin_token): raise HTTPException(403)
    r = await db.get("issued_keys", params={"order": "created_at.desc"})
    return r.json()

@app.post("/api/admin/generate_key")
async def generate_key(data: dict, x_admin_token: str = Header(None)):
    # 1. Проверка токена (берём из .env через твою функцию)
    if not verify_admin_token(x_admin_token):
        raise HTTPException(403, "Forbidden")

    # 2. Извлекаем название бота (которое ты ввёл в prompt)
    # Используем .get("bot_id"), так как фронтенд шлет имя в этом поле
    bot_name_input = data.get("bot_id")
    
    if not bot_name_input:
        logger.error("❌ Ошибка: Название бота не получено от фронтенда")
        raise HTTPException(400, "Название бота обязательно (поле bot_id пустое)")

    # 3. Ищем ID бота в таблице public.bots по колонке 'name'
    # Используем ilike для поиска без учета регистра (чтобы 'Бот' и 'бот' работали одинаково)
    try:
        bot_res = await db.get("bots", params={"name": f"ilike.{bot_name_input.strip()}"})
        bots_found = bot_res.json()
        
        if not bots_found or len(bots_found) == 0:
            logger.warning(f"⚠️ Бот с именем '{bot_name_input}' не найден в таблице bots")
            raise HTTPException(404, f"Бот '{bot_name_input}' не найден")
            
        # Берем данные первого найденного бота
        target_bot_id = bots_found[0]['id']  # Это будет оригинальный ID бота (текст)
        real_name = bots_found[0]['name']
        
    except Exception as e:
        logger.error(f"❌ Ошибка при обращении к таблице bots: {str(e)}")
        raise HTTPException(500, "Ошибка базы данных при поиске бота")

    # 4. Генерируем ключ
    import secrets
    import string
    new_key = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    
    # 5. Сохраняем ключ в таблицу public.keys
    payload = {
        "key": new_key,
        "duration_months": int(data.get("months", 1)),
        "bot_id": target_bot_id,  # ЗАПИСЫВАЕМ ТЕХНИЧЕСКИЙ ID
        "is_used": False,
        "created_at": datetime.now().isoformat()
    }

    res = await db.post("keys", json=payload)
    
    if res.status_code in [200, 201]:
        logger.info(f"✅ Ключ {new_key} создан для {real_name} (ID: {target_bot_id})")
        return {
            "status": "success", 
            "key": new_key, 
            "bot_id": target_bot_id,
            "bot_name": real_name
        }
    
    logger.error(f"❌ Ошибка записи ключа: {res.text}")
    raise HTTPException(500, "Не удалось сохранить ключ в базу")
        
# --- [ ПОДДЕРЖКА И ПРЯМОЙ ДОСТУП ] ---

@app.post("/api/admin/temp-access")
async def create_temp_access(request: Request):
    """Для входа админа в редактор чужого бота"""
    data = await request.json()
    bot_id, key = data.get("botId"), data.get("key")
    if bot_id and key:
        TEMP_ADMIN_ACCESS[key] = {"bot_id": bot_id, "expires": time.time() + 1200}
        return {"status": "ok"}
    raise HTTPException(400)

@app.post("/api/admin/bots/start")
async def admin_start_bot_direct(request: Request, x_admin_token: str = Header(None)):
    if not verify_admin_token(x_admin_token): raise HTTPException(401)
    data = await request.json()
    bot_data = data.get("bot")
    success = await start_bot_process(bot_data)
    return {"status": "started" if success else "failed"}

@app.get("/api/admin/system-logs")
async def get_admin_logs(x_admin_token: str = Header(None)):
    if not verify_admin_token(x_admin_token): raise HTTPException(403)
    
    # Берем последние 20 сообщений из bot_messages как "Логи системы"
    # join не обязателен, но полезен
    r = await db.get("bot_messages", params={
        "select": "*, bots(name)",
        "order": "created_at.desc",
        "limit": 20
    })
    return r.json()

@app.get("/api/admin/bot/{bot_id}")
async def get_bot_for_admin(bot_id: str, x_admin_token: str = Header(None)):
    if not verify_admin_token(x_admin_token): raise HTTPException(403)
    
    r = await db.get("bots", params={"id": f"eq.{bot_id}"})
    if not r.json():
        raise HTTPException(404, "Bot not found")
        
    bot_data = r.json()[0]
    # Мержим конфиг
    full_bot = {**bot_data, **(bot_data.get("config") or {})}
    # Токен отдаем как есть (зашифрованным), Editor его не показывает, но использует для save
    return full_bot


        
@app.post("/api/admin/verify_access_key")
async def verify_access_key(data: dict):
    # УБРАЛИ проверку x_admin_token, так как ключ вводит НЕ админ
    
    input_key = data.get("key", "").strip()
    # Получаем то, что прислал фронтенд (может быть ID или имя)
    requested_bot = str(data.get("bot_id", "")).strip()

    if not requested_bot or not input_key:
        raise HTTPException(400, "Ключ и идентификатор бота обязательны")

    # 1. Ищем ключ. 
    # Мы ищем запись, где ключ совпадает И (bot_id совпадает с присланным)
    params = {
        "key": f"eq.{input_key}",
        "is_used": "eq.false"
    }
    
    res = await db.get("keys", params=params)
    keys_found = res.json()

    if res.status_code == 200 and len(keys_found) > 0:
        found_key = keys_found[0]
        # Проверяем, привязан ли ключ именно к этому боту (регистронезависимо)
        key_target = str(found_key.get("bot_id", "")).lower()
        
        if key_target == requested_bot.lower():
            key_id = found_key.get("id")

            # 2. ПОМЕЧАЕМ КАК ИСПОЛЬЗОВАННЫЙ
            update_res = await db.patch("keys", params={"id": f"eq.{key_id}"}, json={"is_used": True})
            
            if update_res.status_code in [200, 204]:
                logger.info(f"✅ Ключ {input_key} активирован для {requested_bot}")
                return {"ok": True}
        else:
            logger.warning(f"❌ Ключ {input_key} принадлежит {key_target}, а запрошен для {requested_bot}")

    raise HTTPException(401, "Ключ не подходит или уже использован")

#VK CREATION

@app.post("/api/bots/create")
async def create_bot_endpoint(d: dict):
    try:
        # ЛОГИРУЕМ ВХОДЯЩИЙ ЗАПРОС
        logger.info(f"🚀 Поступил запрос на создание бота: {d}")
        
        owner_id = d.get('owner_id')
        token = d.get('token')
        
        if not owner_id or not token:
            raise HTTPException(400, "Owner ID и Token обязательны")

        bot_id = f"bot_{secrets.token_hex(4)}"
        
        _plat = d.get('platform', 'telegram')
        _ai_raw = d.get('adminIds', [])
        if isinstance(_ai_raw, str):
            _ai_raw = [int(x.strip()) for x in _ai_raw.split(",") if x.strip().lstrip("-").isdigit()]
        _ai = [int(x) for x in _ai_raw if str(x).strip().lstrip("-").isdigit()]

        if _plat == 'poster':
            _ch  = d.get('channelId', '')
            _chs = d.get('channels', [_ch] if _ch else [])
            _cfg = {
                "channelId":      _ch,
                "channels":       _chs,
                "adminIds":       _ai,
                "botLink":        d.get('botLink', ''),
                "welcomeMessage": "",
                "stats":          {"totalPosts": 0, "history": []},
            }
        elif _plat == 'randomizer':
            _cfg = {
                "lotChannel":    d.get('lotChannel', ''),
                "adminIds":      _ai,
                "botLink":       d.get('botLink',    ''),
                "welcomeMessage": "👋 Привет! Я бот для розыгрышей.",
                "lotteries":     [],
                "users":         [],
                "stats":         {"totalUsers": 0, "blockedCount": 0, "totalLotteries": 0, "history": []},
            }
        else:
            _cfg = {
                "buttons":        [],
                "triggers":       [],
                "welcomeMessage": "Привет!",
                "settings":       {"forwardToAdmin": True},
                "connectedUsers": [],
                "adminIds":       _ai,
            }

        # Данные строго под твою структуру SQL
        payload = {
            "id": bot_id,
            "owner_id": owner_id,
            "name": d.get('name', 'Новый бот'),
            "token": encrypt_val(token),
            "platform": _plat,
            "status": "IDLE",
            "license_expires_at": int(time.time() * 1000) + (30 * 24 * 3600 * 1000),
            "created_at": int(time.time() * 1000),
            "config": _cfg,
            "stats": {},
            "admin_chat_id": None,
            "vk_group_id": None
        }

        res = await db.post("bots", json=payload)
        
        if res.status_code not in [200, 201, 204]:
            logger.error(f"❌ Ошибка Supabase: {res.text}")
            raise HTTPException(res.status_code, f"DB Error: {res.text}")

        logger.info(f"✅ Бот {bot_id} успешно создан ({_plat})")
        return {**payload, "token": token, "adminIds": _ai, "channelId": d.get("channelId",""), "lotChannel": d.get("lotChannel",""), "botLink": d.get("botLink","")}

    except Exception as e:
        logger.error(f"🚨 Ошибка создания: {e}")
        raise HTTPException(500, str(e))
    
# ==========================================
# 8. VK BIND (Привязка беседы)
# ==========================================

@app.post("/api/bots/vk-bind")
async def vk_bind_peer(d: dict):
    """Привязывает peer_id беседы к боту.
    
    Вызывается двумя способами:
    1. Автоматически из vkbot_core при добавлении в беседу.
    2. Вручную — пользователь вводит ID беседы в BotEditor.
    
    Формат запроса: { "bot_id": "bot_xxx", "peer_id": 2000000010, "owner_id": "u_xxx" }
    """
    try:
        bot_id  = d.get("bot_id")
        peer_id = d.get("peer_id")
        owner_id= d.get("owner_id")  # Для проверки владельца

        if not bot_id or not peer_id:
            raise HTTPException(400, "bot_id и peer_id обязательны")

        peer_id = int(peer_id)

        # Проверяем, что бот принадлежит этому пользователю
        res = await db.get("bots", params={"id": f"eq.{bot_id}"})
        if not res.json():
            raise HTTPException(404, "Бот не найден")
        
        bot_data = res.json()[0]
        if owner_id and bot_data.get("owner_id") != owner_id:
            raise HTTPException(403, "Нет доступа к этому боту")

        # Получаем текущий конфиг и обновляем peer_id
        cfg = bot_data.get("config") or {}
        if isinstance(cfg, str):
            try: cfg = json.loads(cfg)
            except: cfg = {}

        cfg["vk_group_id"]   = peer_id
        cfg["vkGroupId"]     = peer_id
        cfg["admin_chat_id"] = peer_id
        cfg["adminChatId"]   = peer_id

        # Записываем и в колонку vk_group_id, и внутрь config
        patch_res = await db.patch(
            "bots",
            params={"id": f"eq.{bot_id}"},
            json={
                "vk_group_id": peer_id,
                "admin_chat_id": None,
                "config": cfg
            }
        )

        if patch_res.status_code not in [200, 201, 204]:
            raise HTTPException(500, f"Ошибка БД: {patch_res.text}")

        logger.info(f"🔗 Бот {bot_id} привязан к VK peer_id={peer_id}")
        return {"status": "ok", "bot_id": bot_id, "peer_id": peer_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"vk-bind error: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/bots/vk-peer-info/{peer_id}")
async def vk_get_peer_info(peer_id: int):
    """Возвращает человекочитаемое описание VK peer_id.
    
    peer_id < 2000000000  → личная переписка (ID пользователя ВК)  
    peer_id > 2000000000  → беседа/конференция (ID = peer_id - 2000000000)
    """
    if peer_id > 2000000000:
        conv_id = peer_id - 2000000000
        return {
            "type": "conversation",
            "peer_id": peer_id,
            "conversation_id": conv_id,
            "description": f"Беседа #{conv_id} (ID сообщества/чата)"
        }
    else:
        return {
            "type": "user",
            "peer_id": peer_id,
            "description": f"Личный диалог с пользователем VK ID={peer_id}"
        }

# --- ДОБАВИТЬ В КОНЕЦ ФАЙЛА server.py ---

@app.post("/api/reviews/submit")
async def proxy_submit_review(request: Request):
    # Данные от React
    data = await request.json()
    
    # URL нашего Python-бота (который на порту 3001)
    bot_reviews_url = "http://localhost:3001/api/reviews"
    
    async with httpx.AsyncClient() as client:
        try:
            # Отправляем боту, добавляя секрет ADMIN_SECRET из .env
            response = await client.post(
                bot_reviews_url,
                json=data,
                headers={"x-admin-token": os.getenv("ADMIN_SECRET")}
            )
            return response.json()
        except Exception as e:
            logger.error(f"Ошибка проксирования отзыва: {e}")
            raise HTTPException(status_code=500, detail="Бот модерации недоступен")

@app.get("/api/reviews/list")
async def proxy_get_reviews():
    async with httpx.AsyncClient() as client:
        try:
            # Забираем одобренные отзывы у бота
            response = await client.get("http://localhost:3001/api/reviews/get")
            return response.json()
        except Exception as e:
            logger.error(f"Ошибка получения отзывов: {e}")
            return []

@app.post("/api/applications/submit")
async def submit_application(request: Request):
    """Принимает отклик с сайта /careers и сохраняет в Supabase."""
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    required = ["contact", "experience", "about"]
    for field in required:
        if not data.get(field, "").strip():
            raise HTTPException(status_code=422, detail=f"Field '{field}' is required")

    record = {
        "id":            str(uuid.uuid4()),
        "vacancy_id":    data.get("vacancy_id", "unknown"),
        "vacancy_title": data.get("vacancy_title", ""),
        "contact":       data.get("contact", "").strip(),
        "experience":    data.get("experience", "").strip(),
        "about":         data.get("about", "").strip(),
        "extra":         data.get("extra", "").strip(),
        "status":        "new",
        "created_at":    datetime.utcnow().isoformat() + "Z",
    }

    try:
        r = await db.post(
            "job_applications",
            json=record,
            headers={"Prefer": "return=minimal"}
        )
        if r.status_code not in (200, 201):
            logger.error(f"Supabase insert error: {r.status_code} {r.text}")
            raise HTTPException(status_code=500, detail="DB error")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Applications submit error: {e}")
        raise HTTPException(status_code=500, detail="Server error")

    logger.info(f"📨 Новый отклик: {record['vacancy_title']} от {record['contact']}")
    return {"ok": True, "id": record["id"]}


# ── Список откликов (только для админа) ─────────────────────────
@app.get("/api/applications/list")
async def list_applications(x_admin_token: str = Header(None)):
    """Возвращает все отклики, отсортированные от новых к старым."""
    if not verify_admin_token(x_admin_token):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        r = await db.get(
            "job_applications",
            params={"order": "created_at.desc", "limit": "200"}
        )
        if r.status_code == 200:
            return r.json()
        return []
    except Exception as e:
        logger.error(f"Applications list error: {e}")
        return []


# ── Обновление статуса отклика ───────────────────────────────────
@app.patch("/api/applications/{app_id}/status")
async def update_application_status(
    app_id: str,
    request: Request,
    x_admin_token: str = Header(None)
):
    """Меняет статус отклика: new → reviewed (или другой)."""
    if not verify_admin_token(x_admin_token):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        body = await request.json()
        status = body.get("status", "reviewed")
    except Exception:
        status = "reviewed"

    try:
        r = await db.patch(
            f"job_applications?id=eq.{app_id}",
            json={"status": status},
            headers={"Prefer": "return=minimal"}
        )
        if r.status_code in (200, 204):
            return {"ok": True}
        raise HTTPException(status_code=500, detail="DB error")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Applications status update error: {e}")
        raise HTTPException(status_code=500, detail="Server error")


# ── Удаление отклика ─────────────────────────────────────────────
@app.delete("/api/applications/{app_id}")
async def delete_application(app_id: str, x_admin_token: str = Header(None)):
    """Удаляет отклик по ID."""
    if not verify_admin_token(x_admin_token):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        r = await db.delete(f"job_applications?id=eq.{app_id}")
        if r.status_code in (200, 204):
            return {"ok": True}
        raise HTTPException(status_code=500, detail="DB error")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Applications delete error: {e}")
        raise HTTPException(status_code=500, detail="Server error")

# ── Сохранить / обновить мини-приложение ─────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
# 8. МИНИ-ПРИЛОЖЕНИЯ  
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/admin/generate-miniapp-key")
async def gen_miniapp_key(d: dict, x_admin_token: str = Header(None)):
    """Генерация ключа подписки на мини-апп. Формат MAPP-XXXXXX-NNN"""
    if x_admin_token != A_SECRET:
        raise HTTPException(401, "Admin only")
    months = int(d.get("months", 1))
    price_rub = int(d.get("price_rub", 90))
    key = f"MAPP-{secrets.token_hex(3).upper()}-{random.randint(100,999)}"
    payload = {
        "key": key,
        "months": months,
        "price_rub": price_rub,
        "used": False,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    res = await db.post("miniapp_keys", json=payload)
    if res.status_code not in [200, 201]:
        raise HTTPException(500, f"DB error: {res.text}")
    return {"key": key, "months": months, "price_rub": price_rub}

@app.get("/api/admin/miniapp-keys")
async def get_miniapp_keys(x_admin_token: str = Header(None)):
    if x_admin_token != A_SECRET:
        raise HTTPException(401)
    res = await db.get("miniapp_keys?select=*&order=created_at.desc")
    return res.json()

@app.post("/api/miniapps/activate")
async def activate_miniapp(req: dict):
    """Активация ключа мини-апп для конкретного бота."""
    key_code = req.get("key", "").strip().upper()
    bot_id   = req.get("botId", "").strip()
    
    if not key_code or not bot_id:
        return {"status": "error", "message": "Ключ и botId обязательны"}

    # 1. Проверяем ключ
    rk = await db.get("miniapp_keys", params={"key": f"eq.{key_code}", "used": "eq.false"})
    keys_found = rk.json()
    
    if not keys_found or not isinstance(keys_found, list):
        return {"status": "error", "message": "Ключ недействителен или уже использован"}
    
    k_data = keys_found[0]
    months = int(k_data.get("months", 1))
    added_ms = months * 30 * 86400 * 1000

    # 2. Проверяем существующую лицензию
    lic_r = await db.get("miniapp_licenses", params={"bot_id": f"eq.{bot_id}"})
    lics = lic_r.json()
    curr_time = int(time.time() * 1000)

    # Безопасная проверка: lics должен быть списком и не быть пустым
    if isinstance(lics, list) and len(lics) > 0:
        # Лицензия уже есть, продлеваем
        lic_item = lics[0]
        # Используем .get() и проверяем на None/0
        cur_expiry = lic_item.get("expires_at")
        if not cur_expiry:
            cur_expiry = 0
            
        new_expiry = max(cur_expiry, curr_time) + added_ms
        
        await db.patch("miniapp_licenses", 
                       params={"bot_id": f"eq.{bot_id}"},
                       json={"expires_at": new_expiry, "active": True})
    else:
        # Лицензии нет, создаем новую
        new_expiry = curr_time + added_ms
        await db.post("miniapp_licenses", json={
            "bot_id": bot_id, 
            "expires_at": new_expiry, 
            "active": True
        })

    # 3. Помечаем ключ как использованный
    await db.patch("miniapp_keys", params={"key": f"eq.{key_code}"},
                   json={"used": True, "used_by_bot": bot_id})

    logger.info(f"✅ MiniApp ключ активирован: {key_code} → бот {bot_id}, до {new_expiry}")
    return {"status": "ok", "expires_at": new_expiry, "months_added": months}

@app.get("/api/miniapps/license/{bot_id}")
async def get_miniapp_license(bot_id: str):
    """Проверяет активность лицензии мини-апп для бота."""
    try:
        r = await db.get("miniapp_licenses", params={"bot_id": f"eq.{bot_id}", "limit": "1"})
        lics = r.json()
        if not lics:
            return {"active": False, "expires_at": 0}
        lic = lics[0]
        expires_at = lic.get("expires_at", 0) or 0
        active = expires_at > int(time.time() * 1000)
        # Обновляем флаг active в БД если истекла
        if not active and lic.get("active"):
            await db.patch("miniapp_licenses", params={"bot_id": f"eq.{bot_id}"},
                           json={"active": False})
        return {"active": active, "expires_at": expires_at}
    except Exception as e:
        logger.error(f"miniapp license check error: {e}")
        return {"active": False, "expires_at": 0}

@app.get("/api/miniapps/list-by-bot/{bot_id}")
async def list_miniapps_by_bot(bot_id: str):
    """Получить все мини-приложения конкретного бота (для редактора)."""
    try:
        r = await db.get("mini_apps", params={
            "bot_id": f"eq.{bot_id}",
            "select": "*",
            "order": "updated_at.desc",
            "limit": "50",
        })
        if r.status_code == 200:
            apps = r.json()
            for a in apps:
                a["formWebhook"]   = a.pop("form_webhook", "") or ""
                a["sheetsUrl"]     = a.pop("sheets_url", "") or ""
                a["webhookType"]   = a.pop("webhook_type", "formbot") or "formbot"
                a["notifyChatId"]  = a.pop("notify_chat_id", "") or ""
            return apps
        return []
    except Exception as e:
        logger.error(f"list_miniapps_by_bot error: {e}")
        return []

@app.post("/api/miniapps/save")
async def save_miniapp(request: Request):
    """Сохраняет мини-приложение."""
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    app_id       = data.get("id") or str(uuid.uuid4())
    owner_id     = data.get("owner_id", "")
    bot_id       = data.get("bot_id", "")
    title        = data.get("title", "Без названия")[:120]
    theme        = data.get("theme", {})
    components   = data.get("components", [])
    webhook          = data.get("form_webhook") or data.get("formWebhook", "")
    sheets_url       = data.get("sheets_url") or data.get("sheetsUrl", "")
    webhook_type     = data.get("webhook_type") or data.get("webhookType", "formbot")
    notify_chat_id   = data.get("notify_chat_id") or data.get("notifyChatId", "")

    if not owner_id:
        raise HTTPException(status_code=422, detail="owner_id required")

    if len(components) > 100:
        raise HTTPException(status_code=422, detail="Too many components (max 100)")

    record = {
        "id":             app_id,
        "owner_id":       owner_id,
        "bot_id":         bot_id,
        "title":          title,
        "theme":          theme,
        "components":     components,
        "form_webhook":   webhook,
        "sheets_url":     sheets_url,
        "webhook_type":   webhook_type,
        "notify_chat_id": notify_chat_id,
        "updated_at":     datetime.utcnow().isoformat() + "Z",
    }

    try:
        # ВАЖНО: Добавляем ?on_conflict=id, иначе Supabase не поймет, что нужно обновлять
        r = await db.post(
            "mini_apps?on_conflict=id", 
            json=record,
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )
        
        # 204 No Content возвращается при return=minimal, это признак успеха
        if r.status_code not in (200, 201, 204):
            logger.error(f"Miniapp save error: {r.status_code} {r.text}")
            raise HTTPException(status_code=500, detail=f"DB error: {r.text}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Miniapp save exception: {e}")
        raise HTTPException(status_code=500, detail="Server error")

    logger.info(f"💾 Мини-приложение сохранено: {app_id} ({title}) owner={owner_id}")
    return {"ok": True, "id": app_id}


# ── Получить мини-приложение по ID (публичный) ─────────────────────

# ── Список мини-приложений пользователя ──────────────────────────
@app.get("/api/miniapps/list/{owner_id}")
async def list_miniapps(owner_id: str):
    """Получить все мини-приложения пользователя."""
    try:
        r = await db.get(
            "mini_apps",
            params={
                "owner_id": f"eq.{owner_id}",
                "select":   "id,title,updated_at",
                "order":    "updated_at.desc",
                "limit":    "50",
            }
        )
        if r.status_code == 200:
            return r.json()
        return []
    except Exception as e:
        logger.error(f"Miniapp list error: {e}")
        return []
@app.get("/api/miniapps/{app_id}")
async def get_miniapp(app_id: str):
    """Публичный endpoint для рендера мини-приложения."""
    try:
        r = await db.get(
            "mini_apps",
            params={"id": f"eq.{app_id}", "select": "*", "limit": "1"}
        )
        if r.status_code == 200:
            results = r.json()
            if results:
                app_data = results[0]
                # Нормализуем поля для рендерера
                app_data["formWebhook"]   = app_data.pop("form_webhook", "") or ""
                app_data["sheetsUrl"]     = app_data.pop("sheets_url", "") or ""
                app_data["webhookType"]   = app_data.pop("webhook_type", "formbot") or "formbot"
                app_data["notifyChatId"]  = app_data.pop("notify_chat_id", "") or ""
                # bot_id остаётся как есть — рендерер читает его напрямую
                return app_data
        
        raise HTTPException(status_code=404, detail="App not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Miniapp get error: {e}")
        raise HTTPException(status_code=500, detail="Server error")




@app.post("/api/miniapps/submit")
async def submit_miniapp_form(request: Request):
    """Принимает данные формы из мини-приложения.
    
    Поддерживаемые типы доставки:
    - formbot: через выделенного бота (FORM_BOT_TOKEN) в указанный chat_id
    - sheets:  POST на Google Apps Script URL
    - webhook: POST на внешний URL (n8n, Make, Zapier)
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    app_id          = body.get("app_id", "")
    form_data       = body.get("data", {})
    webhook_type    = body.get("webhook_type", "")
    notify_chat_id  = body.get("notify_chat_id", "")
    sheets_url      = body.get("sheets_url", "")
    form_webhook    = body.get("form_webhook", "")
    app_title       = body.get("app_title", "")

    if not app_id:
        raise HTTPException(status_code=422, detail="app_id required")

    try:
        # 1. Извлекаем данные формы из запроса
        form_data = data.get("form_data", {})
        app_id = data.get("app_id")

        # 2. Получаем актуальные настройки мини-приложения из БД
        # Нам нужно узнать notify_chat_id и webhook_type
        r = await db.get("mini_apps", params={"id": f"eq.{app_id}", "select": "*", "limit": "1"})
        
        if r.status_code == 200 and r.json():
            app_row = r.json()[0]
            webhook_type = app_row.get("webhook_type", "bot")
            notify_chat_id = app_row.get("notify_chat_id", "") # Тот самый ID из forms_bot
            
            logger.info(f"Processing form: app={app_id}, type={webhook_type}, chat={notify_chat_id}")

            # 3. ЛОГИКА ОТПРАВКИ В TELEGRAM (через выделенного бота)
            if webhook_type == "bot" and notify_chat_id:
                # Берем токен нашего бота из .env
                bot_token = os.getenv("FORM_BOT_TOKEN")
                
                if bot_token:
                    # Форматируем сообщение
                    lines = [
                        "<b>Новая форма!</b>",
                        f"Приложение: <code>{app_id}</code>",
                        "---"
                    ]
                    for k, v in form_data.items():
                        lines.append(f"<b>{k}</b>: {v}")
                    
                    msg_text = "\n".join(lines)

                    # Отправляем напрямую в Telegram API
                    async with httpx.AsyncClient(timeout=10) as client:
                        resp = await client.post(
                            f"https://api.telegram.org/bot{bot_token}/sendMessage",
                            json={
                                "chat_id": notify_chat_id,
                                "text": msg_text,
                                "parse_mode": "HTML"
                            }
                        )
                        if resp.status_code == 200:
                            logger.info(f"Message sent to chat {notify_chat_id}")
                        else:
                            logger.error(f"TG Error: {resp.text}")
                else:
                    logger.error("FORM_BOT_TOKEN not found in .env")

        # 2. Google Sheets через Apps Script
        elif webhook_type == "sheets" and sheets_url:
            payload = {k: v for k, v in form_data.items() if not k.startswith("_")}
            payload["_appId"] = app_id
            if app_title:
                payload["_formTitle"] = app_title
            async with httpx.AsyncClient(timeout=15) as client:
                await client.post(sheets_url, json=payload)

        # 3. Внешний вебхук (n8n, Make, Zapier, собственный сервер)
        elif webhook_type == "webhook" and form_webhook:
            payload = {k: v for k, v in form_data.items() if not k.startswith("_")}
            payload["_appId"] = app_id
            if app_title:
                payload["_formTitle"] = app_title
            async with httpx.AsyncClient(timeout=15) as client:
                await client.post(form_webhook, json=payload)

        else:
            logger.warning(
                f"Form submit: no delivery configured. "
                f"app={app_id} type={webhook_type!r} "
                f"chat={notify_chat_id!r} sheets={sheets_url!r}"
            )

        logger.info(f"Form submitted: app={app_id} type={webhook_type}")
        return {"ok": True}

    except Exception as e:
        logger.error(f"Form submit error app={app_id}: {e}")
        # Возвращаем ok чтобы пользователь видел экран успеха (сервер уже получил данные)
        return {"ok": True, "warning": str(e)}

# ── Удалить мини-приложение ───────────────────────────────────────
@app.delete("/api/miniapps/{app_id}")
async def delete_miniapp(app_id: str, request: Request):
    """Удалить мини-приложение. Проверяем owner_id из тела."""
    try:
        body = await request.json()
        owner_id = body.get("owner_id", "")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if not owner_id:
         raise HTTPException(status_code=422, detail="owner_id required for deletion")

    try:
        # Проверка владельца прямо в запросе к БД
        r = await db.delete(
            f"mini_apps?id=eq.{app_id}&owner_id=eq.{owner_id}"
        )
        if r.status_code in (200, 204):
            return {"ok": True}
        
        logger.warning(f"Delete failed: {r.status_code} {r.text}")
        raise HTTPException(status_code=403, detail="Forbidden or not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Miniapp delete error: {e}")
        raise HTTPException(status_code=500, detail="Server error")


@app.post("/api/forms/submit")
async def handle_form_submit(request: Request):
    try:
        data = await request.json()
        app_id = data.get("app_id")
        form_data = data.get("form_data", {})

        logger.info(f"Получена форма для приложения: {app_id}")

        # 1. Достаем настройки приложения из БД
        r = await db.get("mini_apps", params={"id": f"eq.{app_id}", "select": "*", "limit": "1"})
        if r.status_code != 200 or not r.json():
            return {"ok": False, "error": "Приложение не найдено"}

        app_row = r.json()[0]
        webhook_type = app_row.get("webhook_type")
        
        async with httpx.AsyncClient() as client:
            # --- ЛОГИКА ДЛЯ TELEGRAM БОТА ---
            if webhook_type in ["bot", "formbot"]:
                chat_id = app_row.get("notify_chat_id")
                bot_token = os.getenv("FORM_BOT_TOKEN") # Токен берем из .env
                
                if chat_id and bot_token:
                    text = f"<b>🔔 Новая заявка!</b>\nID: <code>{app_id}</code>\n"
                    text += "—" * 10 + "\n"
                    for key, value in form_data.items():
                        text += f"<b>{key}:</b> {value}\n"

                    await client.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                        timeout=10.0
                    )
                    logger.info(f"Уведомление отправлено в TG: {chat_id}")

            # --- ЛОГИКА ДЛЯ GOOGLE SHEETS (НОВИНКА) ---
            elif webhook_type == "sheets":
                sheets_url = app_row.get("sheets_url")
                if sheets_url:
                    logger.info(f"Отправка данных в Google Sheets: {sheets_url}")
                    # Отправляем данные формы напрямую в Google Apps Script
                    res = await client.post(sheets_url, json=form_data, timeout=15.0)
                    logger.info(f"Ответ от Google Sheets: {res.status_code}")
                else:
                    logger.warning(f"Тип 'sheets' указан, но sheets_url пуст для {app_id}")

        return {"ok": True}
        
    except Exception as e:
        logger.error(f"Ошибка при обработке формы: {e}")
        return {"ok": False, "error": str(e)}
# ==========================================
# 9. СИСТЕМНЫЕ
# ==========================================

@app.get("/api/ping")
async def ping_pong():
    return {"status": "online", "server_time": time.time()}

# Блок запуска



# ==========================================
# CHAT PLATFORM v2 — Полные эндпоинты
# ==========================================
# Заменяет предыдущий блок "10. CHAT PLATFORM"
# Добавить вместо/после него в server.py

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

GMAIL_EMAIL    = os.getenv("GMAIL_EMAIL", "")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD", "")
SMTP_SERVER    = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT      = int(os.getenv("SMTP_PORT", "587"))

def send_chat_verification_email(to_email: str, code: str, site_name: str) -> bool:
    """Отправка кода верификации для чат-сайта через Gmail."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Код подтверждения — {site_name}"
        msg["From"]    = GMAIL_EMAIL
        msg["To"]      = to_email

        html = f"""
        <div style="font-family:system-ui,sans-serif;max-width:400px;margin:0 auto;padding:32px;background:#09090b;border-radius:24px;">
          <h2 style="color:#fff;margin:0 0 8px">{site_name}</h2>
          <p style="color:#71717a;font-size:14px;margin:0 0 24px">Подтвердите email для регистрации</p>
          <div style="background:#18181b;border-radius:16px;padding:24px;text-align:center;">
            <p style="color:#71717a;font-size:12px;text-transform:uppercase;letter-spacing:2px;margin:0 0 12px">Ваш код</p>
            <p style="color:#fff;font-size:36px;font-weight:900;letter-spacing:8px;margin:0">{code}</p>
          </div>
          <p style="color:#52525b;font-size:12px;margin:24px 0 0">Код действителен 10 минут. Если вы не запрашивали — игнорируйте это письмо.</p>
        </div>
        """
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(GMAIL_EMAIL, GMAIL_PASSWORD)
            server.sendmail(GMAIL_EMAIL, to_email, msg.as_string())
        return True
    except Exception as e:
        logger.error(f"Chat email error: {e}")
        return False


def _cs_h():
    """Supabase headers helper."""
    return {
        "apikey": S_KEY,
        "Authorization": f"Bearer {S_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }


def _gen_id(prefix="cs"):
    return f"{prefix}_{secrets.token_hex(6)}"


def _slug(name: str) -> str:
    import re
    s = re.sub(r'[^a-z0-9\-]', '-', name.lower().strip())
    s = re.sub(r'-+', '-', s).strip('-')[:28] or "site"
    return f"{s}-{secrets.token_hex(3)}"


async def _sb_get(table: str, params: dict) -> list:
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{S_URL}/rest/v1/{table}", headers=_cs_h(), params=params)
        return r.json() if r.status_code == 200 else []


async def _sb_post(table: str, data: dict) -> dict | None:
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{S_URL}/rest/v1/{table}", headers=_cs_h(), json=data)
        d = r.json()
        return d[0] if isinstance(d, list) and d else None


async def _sb_patch(table: str, params: dict, data: dict) -> bool:
    async with httpx.AsyncClient() as c:
        r = await c.patch(f"{S_URL}/rest/v1/{table}", headers=_cs_h(), params=params, json=data)
        return r.status_code in (200, 204)


async def _sb_delete(table: str, params: dict) -> bool:
    async with httpx.AsyncClient() as c:
        r = await c.delete(f"{S_URL}/rest/v1/{table}", headers=_cs_h(), params=params)
        return r.status_code in (200, 204)


# ─── Создать сайт ──────────────────────────────────────────────────────────────

@app.post("/api/chat/sites")
async def chat_create_site(d: dict):
    owner_id = d.get("owner_id", "").strip()
    name = d.get("name", "").strip()
    if not owner_id or not name:
        raise HTTPException(400, "owner_id и name обязательны")

    site_id = _gen_id("cs")
    slug = _slug(name)
    owner_login_raw   = f"owner_{secrets.token_hex(4)}"
    owner_pass_raw    = secrets.token_urlsafe(14)

    row = {
        "id": site_id,
        "owner_id": owner_id,
        "name": name,
        "slug": slug,
        "config": d.get("config", {
            "primaryColor": "#6366f1",
            "bgColor": "#09090b",
            "fontFamily": "Manrope, sans-serif",
            "welcomeMessage": "Чем можем помочь?",
            "commands": [],
            "logoText": name,
            "requireEmailVerification": False,
            "showOnlineStatus": True,
        }),
        "owner_login": owner_login_raw,
        "owner_password": hash_pwd(owner_pass_raw),
        "created_at": int(time.time() * 1000),
        "is_active": True,
    }

    async with httpx.AsyncClient() as c:
        r = await c.post(f"{S_URL}/rest/v1/chat_sites", headers=_cs_h(), json=row)
        if r.status_code not in (200, 201):
            raise HTTPException(500, f"Ошибка БД: {r.text}")

    # Создаём первого дефолтного администратора
    admin_login_raw = d.get("admin_login") or f"admin"
    admin_pass_raw  = d.get("admin_password") or secrets.token_urlsafe(10)
    admin_name      = d.get("admin_name") or "Поддержка"
    admin_id        = _gen_id("csa")

    admin_row = {
        "id": admin_id,
        "site_id": site_id,
        "display_name": admin_name,
        "login": admin_login_raw,
        "password": hash_pwd(admin_pass_raw),
        "avatar_color": "#6366f1",
        "bio": "Готов помочь!",
        "is_active": True,
        "is_online": False,
        "last_seen": int(time.time() * 1000),
        "created_at": int(time.time() * 1000),
    }
    await _sb_post("chat_site_admins", admin_row)

    return {
        **row,
        "owner_password_plain": owner_pass_raw,
        "admin_login": admin_login_raw,
        "admin_password_plain": admin_pass_raw,
        "admin_name": admin_name,
        "admin_id": admin_id,
    }


@app.get("/api/chat/sites/owner/{owner_id}")
async def chat_list_sites(owner_id: str):
    return await _sb_get("chat_sites", {"owner_id": f"eq.{owner_id}", "order": "created_at.desc"})


@app.get("/api/chat/sites/{site_id}")
async def chat_get_site(site_id: str, owner_id: str):
    rows = await _sb_get("chat_sites", {"id": f"eq.{site_id}", "owner_id": f"eq.{owner_id}"})
    if not rows: raise HTTPException(404)
    return rows[0]


@app.get("/api/chat/site/{slug}/public")
async def chat_site_public(slug: str):
    rows = await _sb_get("chat_sites", {"slug": f"eq.{slug}", "is_active": "eq.true"})
    if not rows: raise HTTPException(404, "Сайт не найден")
    s = rows[0]
    return {"id": s["id"], "name": s["name"], "slug": s["slug"], "config": s.get("config", {})}


@app.patch("/api/chat/sites/{site_id}")
async def chat_update_site(site_id: str, d: dict):
    owner_id = d.get("owner_id")
    if not owner_id: raise HTTPException(400, "owner_id required")
    payload = {}
    if "name"   in d: payload["name"]   = d["name"]
    if "config" in d: payload["config"] = d["config"]
    ok = await _sb_patch("chat_sites", {"id": f"eq.{site_id}", "owner_id": f"eq.{owner_id}"}, payload)
    return {"ok": ok}


@app.delete("/api/chat/sites/{site_id}")
async def chat_delete_site(site_id: str, owner_id: str):
    for t in ["chat_site_messages", "chat_conversations", "chat_site_users", "chat_site_admins", "chat_broadcasts"]:
        await _sb_delete(t, {"site_id": f"eq.{site_id}"})
    ok = await _sb_delete("chat_sites", {"id": f"eq.{site_id}", "owner_id": f"eq.{owner_id}"})
    return {"ok": ok}


# ─── Управление администраторами ───────────────────────────────────────────────

@app.get("/api/chat/sites/{site_id}/admins")
async def chat_list_admins(site_id: str, owner_id: str):
    sites = await _sb_get("chat_sites", {"id": f"eq.{site_id}", "owner_id": f"eq.{owner_id}"})
    if not sites: raise HTTPException(403)
    admins = await _sb_get("chat_site_admins", {"site_id": f"eq.{site_id}", "order": "created_at.asc"})
    # Скрываем пароли
    return [{k: v for k, v in a.items() if k != "password"} for a in admins]


@app.get("/api/chat/site/{slug}/admins")
async def chat_admins_public(slug: str):
    """Публичный список активных администраторов для выбора пользователем."""
    sites = await _sb_get("chat_sites", {"slug": f"eq.{slug}", "is_active": "eq.true"})
    if not sites: raise HTTPException(404)
    admins = await _sb_get("chat_site_admins", {
        "site_id": f"eq.{sites[0]['id']}",
        "is_active": "eq.true",
        "order": "created_at.asc"
    })
    return [{"id": a["id"], "display_name": a["display_name"], "bio": a.get("bio", ""),
             "avatar_color": a.get("avatar_color", "#6366f1"),
             "is_online": a.get("is_online", False)} for a in admins]


@app.post("/api/chat/sites/{site_id}/admins")
async def chat_create_admin(site_id: str, d: dict):
    owner_id = d.get("owner_id")
    sites = await _sb_get("chat_sites", {"id": f"eq.{site_id}", "owner_id": f"eq.{owner_id}"})
    if not sites: raise HTTPException(403)

    login = d.get("login", "").strip()
    password = d.get("password", "").strip()
    if not login or not password: raise HTTPException(400, "login и password обязательны")

    admin_row = {
        "id": _gen_id("csa"),
        "site_id": site_id,
        "display_name": d.get("display_name", "Администратор"),
        "login": login,
        "password": hash_pwd(password),
        "avatar_color": d.get("avatar_color", "#6366f1"),
        "bio": d.get("bio", ""),
        "is_active": True,
        "is_online": False,
        "last_seen": int(time.time() * 1000),
        "created_at": int(time.time() * 1000),
    }
    result = await _sb_post("chat_site_admins", admin_row)
    if not result: raise HTTPException(500, "Ошибка создания")
    return {k: v for k, v in result.items() if k != "password"}


@app.patch("/api/chat/sites/{site_id}/admins/{admin_id}")
async def chat_update_admin(site_id: str, admin_id: str, d: dict):
    owner_id = d.get("owner_id")
    sites = await _sb_get("chat_sites", {"id": f"eq.{site_id}", "owner_id": f"eq.{owner_id}"})
    if not sites: raise HTTPException(403)

    payload = {}
    for field in ["display_name", "bio", "avatar_color", "is_active"]:
        if field in d: payload[field] = d[field]
    if "password" in d and d["password"]:
        payload["password"] = hash_pwd(d["password"])
    if "login" in d: payload["login"] = d["login"]

    ok = await _sb_patch("chat_site_admins", {"id": f"eq.{admin_id}", "site_id": f"eq.{site_id}"}, payload)
    return {"ok": ok}


@app.delete("/api/chat/sites/{site_id}/admins/{admin_id}")
async def chat_delete_admin(site_id: str, admin_id: str, owner_id: str):
    sites = await _sb_get("chat_sites", {"id": f"eq.{site_id}", "owner_id": f"eq.{owner_id}"})
    if not sites: raise HTTPException(403)
    ok = await _sb_delete("chat_site_admins", {"id": f"eq.{admin_id}", "site_id": f"eq.{site_id}"})
    return {"ok": ok}


@app.post("/api/chat/sites/{site_id}/admins/{admin_id}/online")
async def chat_admin_set_online(site_id: str, admin_id: str, d: dict):
    """Обновление статуса онлайн для администратора."""
    is_online = d.get("is_online", True)
    payload = {"is_online": is_online, "last_seen": int(time.time() * 1000)}
    ok = await _sb_patch("chat_site_admins", {"id": f"eq.{admin_id}", "site_id": f"eq.{site_id}"}, payload)
    return {"ok": ok}


# ─── Авторизация ───────────────────────────────────────────────────────────────

@app.post("/api/chat/site/{slug}/verify-email")
async def chat_request_email_verify(slug: str, d: dict):
    email = (d.get("email") or "").strip().lower()
    if not email or "@" not in email: raise HTTPException(400, "Некорректный email")

    sites = await _sb_get("chat_sites", {"slug": f"eq.{slug}"})
    if not sites: raise HTTPException(404)
    site = sites[0]

    code = str(random.randint(100000, 999999))
    await _sb_patch("chat_verify_codes",
        {"email": f"eq.{email}", "site_id": f"eq.{site['id']}"},
        {"code": code, "created_at": int(time.time() * 1000)})

    # Upsert
    async with httpx.AsyncClient() as c:
        await c.post(f"{S_URL}/rest/v1/chat_verify_codes",
            headers={**_cs_h(), "Prefer": "resolution=merge-duplicates"},
            json={"email": email, "site_id": site["id"], "code": code, "created_at": int(time.time() * 1000)})

    success = await run_in_threadpool(
        send_chat_verification_email, email, code, site.get("name", "Чат")
    )
    if not success:
        raise HTTPException(500, "Ошибка отправки письма")
    return {"ok": True}


@app.post("/api/chat/site/{slug}/register")
async def chat_register(slug: str, d: dict):
    username = (d.get("username") or "").strip()
    password = (d.get("password") or "").strip()
    email    = (d.get("email") or "").strip().lower()
    verify_code = (d.get("verify_code") or "").strip()

    if not username or not password: raise HTTPException(400, "username и password обязательны")
    if len(username) < 2: raise HTTPException(400, "Имя минимум 2 символа")

    sites = await _sb_get("chat_sites", {"slug": f"eq.{slug}"})
    if not sites: raise HTTPException(404)
    site = sites[0]
    config = site.get("config", {})

    # Проверяем email-верификацию если включена
    is_verified = False
    if config.get("requireEmailVerification") and email:
        if not verify_code: raise HTTPException(400, "Требуется код подтверждения email")
        codes = await _sb_get("chat_verify_codes", {"email": f"eq.{email}", "site_id": f"eq.{site['id']}"})
        if not codes or codes[0]["code"] != verify_code:
            raise HTTPException(400, "Неверный код подтверждения")
        # Удаляем использованный код
        await _sb_delete("chat_verify_codes", {"email": f"eq.{email}", "site_id": f"eq.{site['id']}"})
        is_verified = True
    elif email:
        is_verified = False  # email указан, но верификация не обязательна

    # Проверяем уникальность
    exist = await _sb_get("chat_site_users", {"site_id": f"eq.{site['id']}", "username": f"eq.{username}"})
    if exist: raise HTTPException(409, "Имя пользователя уже занято")

    now = int(time.time() * 1000)
    user_id = _gen_id("csu")
    user_row = {
        "id": user_id,
        "site_id": site["id"],
        "username": username,
        "email": email or None,
        "password": hash_pwd(password),
        "is_banned": False,
        "is_verified": is_verified,
        "created_at": now,
        "last_seen": now,
    }
    result = await _sb_post("chat_site_users", user_row)
    if not result: raise HTTPException(500, "Ошибка регистрации")

    return {
    "id": user_id, 
    "username": username, 
    "display_name": username,  # <-- Добавь эту строку
    "site_id": sites[0]["id"], 
    "role": "user", 
    "token": f"user:{user_id}"
    }


@app.post("/api/chat/site/{slug}/auth")
async def chat_auth(slug: str, d: dict):
    login    = (d.get("login") or "").strip()
    password = (d.get("password") or "").strip()
    if not login or not password: raise HTTPException(400, "Логин и пароль обязательны")

    sites = await _sb_get("chat_sites", {"slug": f"eq.{slug}"})
    if not sites: raise HTTPException(404, "Сайт не найден")
    site = sites[0]
    hpwd = hash_pwd(password)

    # 1. Проверка владельца
    if login == site["owner_login"] and hpwd == site["owner_password"]:
        return {
            "id": f"owner_{site['id']}",
            "username": "Владелец",
            "display_name": "Владелец",
            "site_id": site["id"],
            "role": "owner",
            "token": f"owner:{site['id']}:{secrets.token_hex(8)}",
        }

    # 2. Проверка администратора (chat_site_admins)
    admins = await _sb_get("chat_site_admins", {
        "site_id": f"eq.{site['id']}",
        "login": f"eq.{login}",
        "is_active": "eq.true"
    })
    if admins and admins[0]["password"] == hpwd:
        a = admins[0]
        # Обновляем онлайн статус
        await _sb_patch("chat_site_admins", {"id": f"eq.{a['id']}"}, {
            "is_online": True,
            "last_seen": int(time.time() * 1000)
        })
        return {
            "id": a["id"],
            "username": a["display_name"],
            "display_name": a["display_name"],
            "avatar_color": a.get("avatar_color", "#6366f1"),
            "site_id": site["id"],
            "role": "admin",
            "token": f"admin:{a['id']}:{secrets.token_hex(8)}",
        }

    # 3. Проверка пользователя
    users = await _sb_get("chat_site_users", {
        "site_id": f"eq.{site['id']}",
        "username": f"eq.{login}",
        "password": f"eq.{hpwd}"
    })
    if users:
        u = users[0]
        if u.get("is_banned"):
            raise HTTPException(403, f"Вы заблокированы. {u.get('ban_reason', '')}")
        await _sb_patch("chat_site_users", {"id": f"eq.{u['id']}"}, {"last_seen": int(time.time() * 1000)})
        return {
            "id": u["id"],
            "username": u["username"],
            "display_name": u["username"],
            "site_id": site["id"],
            "role": "user",
            "token": f"user:{u['id']}:{secrets.token_hex(8)}",
        }

    raise HTTPException(401, "Неверный логин или пароль")


# ─── Диалоги ───────────────────────────────────────────────────────────────────

@app.post("/api/chat/site/{slug}/conversation")
async def chat_start_conversation(slug: str, d: dict):
    """Начать или получить диалог пользователя с конкретным администратором."""
    user_id   = d.get("user_id")
    admin_id  = d.get("admin_id")
    user_name = d.get("user_name", "")
    if not user_id or not admin_id: raise HTTPException(400, "user_id и admin_id обязательны")

    sites = await _sb_get("chat_sites", {"slug": f"eq.{slug}"})
    if not sites: raise HTTPException(404)
    site_id = sites[0]["id"]

    # Ищем существующий диалог
    existing = await _sb_get("chat_conversations", {
        "site_id": f"eq.{site_id}",
        "user_id": f"eq.{user_id}",
        "admin_id": f"eq.{admin_id}"
    })
    if existing:
        return existing[0]

    # Получаем имя администратора
    admins = await _sb_get("chat_site_admins", {"id": f"eq.{admin_id}"})
    admin_name = admins[0]["display_name"] if admins else "Администратор"

    now = int(time.time() * 1000)
    conv = {
        "id": _gen_id("ccv"),
        "site_id": site_id,
        "user_id": user_id,
        "admin_id": admin_id,
        "user_name": user_name,
        "admin_name": admin_name,
        "created_at": now,
        "last_message_at": now,
        "last_message_preview": "",
        "unread_admin": 0,
        "unread_user": 0,
    }
    result = await _sb_post("chat_conversations", conv)
    return result or conv


@app.get("/api/chat/site/{slug}/conversation")
async def chat_get_conversations(slug: str, role: str, session_id: str):
    """
    Список диалогов:
    - user: его диалоги (можно несколько с разными admin)
    - admin/owner: все диалоги с этим admin_id (или все для owner)
    """
    sites = await _sb_get("chat_sites", {"slug": f"eq.{slug}"})
    if not sites: raise HTTPException(404)
    site_id = sites[0]["id"]

    if role == "user":
        convs = await _sb_get("chat_conversations", {
            "site_id": f"eq.{site_id}",
            "user_id": f"eq.{session_id}",
            "order": "last_message_at.desc"
        })
    elif role == "admin":
        convs = await _sb_get("chat_conversations", {
            "site_id": f"eq.{site_id}",
            "admin_id": f"eq.{session_id}",
            "order": "last_message_at.desc"
        })
    else:  # owner — видит всё
        convs = await _sb_get("chat_conversations", {
            "site_id": f"eq.{site_id}",
            "order": "last_message_at.desc"
        })
    return convs


# ─── Сообщения ─────────────────────────────────────────────────────────────────

@app.get("/api/chat/site/{slug}/conversation/{conv_id}/messages")
async def chat_get_messages(slug: str, conv_id: str, since: int = 0):
    params = {
        "conversation_id": f"eq.{conv_id}",
        "is_deleted": "eq.false",
        "order": "created_at.asc",
        "limit": "300",
    }
    if since > 0:
        params["created_at"] = f"gt.{since}"
    return await _sb_get("chat_site_messages", params)


@app.post("/api/chat/site/{slug}/conversation/{conv_id}/messages")
async def chat_send_message(slug: str, conv_id: str, d: dict):
    from_id   = d.get("from_id")
    from_name = d.get("from_name", "")
    from_role = d.get("from_role", "user")
    text      = (d.get("text") or "").strip()
    media_url  = d.get("media_url")
    media_type = d.get("media_type")
    sticker_emoji = d.get("sticker_emoji")

    if not from_id: raise HTTPException(400, "from_id required")
    if not text and not media_url and not sticker_emoji:
        raise HTTPException(400, "Пустое сообщение")

    # Проверяем что пользователь не забанен
    if from_role == "user":
        users = await _sb_get("chat_site_users", {"id": f"eq.{from_id}"})
        if users and users[0].get("is_banned"):
            raise HTTPException(403, "Вы заблокированы")

    now = int(time.time() * 1000)
    msg = {
        "id": _gen_id("csm"),
        "site_id": (await _sb_get("chat_conversations", {"id": f"eq.{conv_id}"}) or [{}])[0].get("site_id", ""),
        "conversation_id": conv_id,
        "from_id": from_id,
        "from_name": from_name,
        "from_role": from_role,
        "text": text or None,
        "media_url": media_url,
        "media_type": media_type,
        "sticker_emoji": sticker_emoji,
        "created_at": now,
        "is_read": False,
        "is_deleted": False,
    }
    result = await _sb_post("chat_site_messages", msg)

    # Обновляем диалог: last_message_at, unread счётчик, превью
    preview = sticker_emoji or (text[:60] if text else f"[{media_type}]")
    unread_field = "unread_admin" if from_role == "user" else "unread_user"

    convs = await _sb_get("chat_conversations", {"id": f"eq.{conv_id}"})
    if convs:
        conv = convs[0]
        new_unread = (conv.get(unread_field) or 0) + 1
        await _sb_patch("chat_conversations", {"id": f"eq.{conv_id}"}, {
            "last_message_at": now,
            "last_message_preview": preview,
            unread_field: new_unread,
        })

    return result or msg


@app.post("/api/chat/site/{slug}/conversation/{conv_id}/read")
async def chat_mark_read(slug: str, conv_id: str, d: dict):
    """Сбросить счётчик непрочитанных для стороны."""
    role = d.get("role", "admin")
    field = "unread_user" if role == "user" else "unread_admin"
    await _sb_patch("chat_conversations", {"id": f"eq.{conv_id}"}, {field: 0})
    return {"ok": True}


# ─── Рассылка ──────────────────────────────────────────────────────────────────

@app.post("/api/chat/site/{slug}/broadcast")
async def chat_broadcast(slug: str, d: dict):
    role      = d.get("role")
    from_id   = d.get("from_id", "")
    from_name = d.get("from_name", "Администрация")
    text      = (d.get("text") or "").strip()
    if role not in ("admin", "owner"): raise HTTPException(403)
    if not text: raise HTTPException(400)

    sites = await _sb_get("chat_sites", {"slug": f"eq.{slug}"})
    if not sites: raise HTTPException(404)
    site_id = sites[0]["id"]

    now = int(time.time() * 1000)
    broadcast = {
        "id": _gen_id("csb"),
        "site_id": site_id,
        "from_name": from_name,
        "from_role": role,
        "text": text,
        "created_at": now,
    }
    await _sb_post("chat_broadcasts", broadcast)
    return {"ok": True, **broadcast}


@app.get("/api/chat/site/{slug}/broadcasts")
async def chat_get_broadcasts(slug: str, since: int = 0):
    sites = await _sb_get("chat_sites", {"slug": f"eq.{slug}"})
    if not sites: raise HTTPException(404)
    params = {"site_id": f"eq.{sites[0]['id']}", "order": "created_at.asc"}
    if since > 0: params["created_at"] = f"gt.{since}"
    return await _sb_get("chat_broadcasts", params)


# ─── Пользователи (управление) ─────────────────────────────────────────────────

@app.get("/api/chat/site/{slug}/users")
async def chat_get_users(slug: str, role: str):
    if role not in ("admin", "owner"): raise HTTPException(403)
    sites = await _sb_get("chat_sites", {"slug": f"eq.{slug}"})
    if not sites: raise HTTPException(404)
    users = await _sb_get("chat_site_users", {
        "site_id": f"eq.{sites[0]['id']}",
        "order": "last_seen.desc"
    })
    return [{k: v for k, v in u.items() if k not in ("password",)} for u in users]


@app.post("/api/chat/site/{slug}/users/{user_id}/ban")
async def chat_ban_user(slug: str, user_id: str, d: dict):
    role = d.get("role")
    if role not in ("admin", "owner"): raise HTTPException(403)
    is_banned  = d.get("is_banned", True)
    ban_reason = d.get("ban_reason", "")
    ok = await _sb_patch("chat_site_users", {"id": f"eq.{user_id}"}, {
        "is_banned": is_banned,
        "ban_reason": ban_reason if is_banned else None
    })
    return {"ok": ok}


# ─── Загрузка медиафайлов (использует существующий /api/upload) ────────────────

@app.post("/api/chat/media/upload")
async def chat_upload_media(
    file: UploadFile = File(...), 
    is_voice: bool = Form(False) # Фронтенд пришлет true для голосовых
):
    # 1. Проверка размера
    file_size = 0
    content = await file.read()
    file_size = len(content)
    
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(413, "Файл слишком большой. Максимум 25 МБ.")

    # 2. Папки и пути
    subdir = "voice" if is_voice else "files"
    os.makedirs(f"uploads/chat/{subdir}", exist_ok=True)
    
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "bin"
    if is_voice: ext = "webm" # Голосовые обычно в этом формате
    
    safe_name = f"{int(time.time())}_{secrets.token_hex(4)}.{ext}"
    save_path = f"uploads/chat/{subdir}/{safe_name}"

    # 3. Сохранение
    with open(save_path, "wb") as f:
        f.write(content)

    # 4. Определение media_type для превью
    media_type = "file"
    if ext in ["jpg", "jpeg", "png", "gif", "webp"]: media_type = "image"
    elif ext in ["mp4", "mov", "webm"] and not is_voice: media_type = "video"
    elif is_voice: media_type = "audio"

    return {
        "url": f"/uploads/chat/{subdir}/{safe_name}",
        "media_type": media_type,
        "filename": file.filename,
        "is_voice": is_voice
    }


# ─── Аналитика ─────────────────────────────────────────────────────────────────

@app.get("/api/chat/site/{slug}/analytics")
async def chat_analytics(slug: str, role: str, days: int = 30):
    if role not in ("admin", "owner"): raise HTTPException(403)
    sites = await _sb_get("chat_sites", {"slug": f"eq.{slug}"})
    if not sites: raise HTTPException(404)
    site_id = sites[0]["id"]

    users    = await _sb_get("chat_site_users", {"site_id": f"eq.{site_id}"})
    admins   = await _sb_get("chat_site_admins", {"site_id": f"eq.{site_id}"})
    convs    = await _sb_get("chat_conversations", {"site_id": f"eq.{site_id}"})
    msgs     = await _sb_get("chat_site_messages", {"site_id": f"eq.{site_id}", "is_deleted": "eq.false"})

    now_ms    = int(time.time() * 1000)
    day_ms    = 86_400_000
    cutoff_ms = now_ms - days * day_ms

    def ts_to_day(ts: int) -> str:
        return datetime.fromtimestamp(ts / 1000).strftime("%d.%m")

    # Сообщения по дням
    msg_by_day: dict[str, dict] = {}
    for m in msgs:
        ts = m.get("created_at", 0)
        if ts < cutoff_ms: continue
        day = ts_to_day(ts)
        if day not in msg_by_day:
            msg_by_day[day] = {"day": day, "user": 0, "admin": 0, "total": 0}
        fr = m.get("from_role", "user")
        if fr == "user":
            msg_by_day[day]["user"] += 1
        else:
            msg_by_day[day]["admin"] += 1
        msg_by_day[day]["total"] += 1

    # Пользователи по дням (регистрации)
    reg_by_day: dict[str, int] = {}
    for u in users:
        ts = u.get("created_at", 0)
        if ts < cutoff_ms: continue
        day = ts_to_day(ts)
        reg_by_day[day] = reg_by_day.get(day, 0) + 1

    # Часы активности
    hours: dict[int, int] = {i: 0 for i in range(24)}
    for m in msgs:
        ts = m.get("created_at", 0)
        if ts < cutoff_ms: continue
        h = datetime.fromtimestamp(ts / 1000).hour
        hours[h] += 1

    # Статистика по администраторам
    admin_stats = []
    for a in admins:
        aid = a["id"]
        a_convs = [c for c in convs if c.get("admin_id") == aid]
        a_msgs  = [m for m in msgs if m.get("from_id") == aid]
        admin_stats.append({
            "id": aid,
            "name": a["display_name"],
            "avatar_color": a.get("avatar_color", "#6366f1"),
            "is_online": a.get("is_online", False),
            "conversations": len(a_convs),
            "messages_sent": len(a_msgs),
        })

    # Время ответа (упрощённо)
    response_times = []
    for conv in convs:
        conv_msgs = sorted([m for m in msgs if m.get("conversation_id") == conv["id"]], key=lambda x: x["created_at"])
        last_user_ts = None
        for m in conv_msgs:
            if m["from_role"] == "user":
                last_user_ts = m["created_at"]
            elif m["from_role"] in ("admin", "owner") and last_user_ts:
                rt = (m["created_at"] - last_user_ts) / 60000  # минуты
                if 0 < rt < 1440:  # до 24 часов
                    response_times.append(rt)
                last_user_ts = None

    avg_response = round(sum(response_times) / len(response_times), 1) if response_times else 0

    # Сортируем по дате
    def sort_key(day_str):
        try:
            d_num, m_num = day_str.split(".")
            return int(m_num) * 100 + int(d_num)
        except: return 0

    msg_chart = sorted(msg_by_day.values(), key=lambda x: sort_key(x["day"]))
    reg_chart = [{"day": k, "count": v} for k, v in sorted(reg_by_day.items(), key=lambda x: sort_key(x[0]))]
    hours_chart = [{"hour": h, "count": cnt} for h, cnt in hours.items()]

    day_ago = now_ms - day_ms
    return {
        "overview": {
            "total_users": len(users),
            "active_24h": sum(1 for u in users if (u.get("last_seen") or 0) > day_ago),
            "banned": sum(1 for u in users if u.get("is_banned")),
            "total_conversations": len(convs),
            "total_messages": len(msgs),
            "user_messages": sum(1 for m in msgs if m.get("from_role") == "user"),
            "admin_messages": sum(1 for m in msgs if m.get("from_role") in ("admin", "owner")),
            "avg_response_min": avg_response,
            "admins_count": len(admins),
        },
        "msg_chart": msg_chart,
        "reg_chart": reg_chart,
        "hours_chart": hours_chart,
        "admin_stats": admin_stats,
    }


# ─── СТАТИКА: убедиться что монтирование добавлено ──────────────────────────
# В секцию инициализации app добавить:
#   from fastapi.staticfiles import StaticFiles
#   os.makedirs("uploads/chat", exist_ok=True)
#   app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


# ─── ВАРНЫ ──────────────────────────────────────────────────────────────────

@app.post("/api/chat/site/{slug}/users/{user_id}/warn")
async def chat_warn_user(slug: str, user_id: str, d: dict):
    """Выдать варн пользователю. Если варнов >= maxWarnsBeforeBan — авто-бан."""
    role = d.get("role")
    if role not in ("admin", "owner"): raise HTTPException(403)
    admin_id   = d.get("admin_id", "")
    admin_name = d.get("admin_name", "Администратор")
    reason     = (d.get("reason") or "").strip()
    if not reason: raise HTTPException(400, "reason required")

    sites = await _sb_get("chat_sites", {"slug": f"eq.{slug}"})
    if not sites: raise HTTPException(404)
    site = sites[0]
    site_id = site["id"]
    config  = site.get("config") or {}
    max_warns = int(config.get("maxWarnsBeforeBan", 3))

    now = int(time.time() * 1000)
    warn = {
        "id": _gen_id("cwn"),
        "site_id": site_id,
        "user_id": user_id,
        "admin_id": admin_id,
        "admin_name": admin_name,
        "reason": reason,
        "created_at": now,
    }
    await _sb_post("chat_user_warns", warn)

    # Увеличиваем счётчик варнов
    users = await _sb_get("chat_site_users", {"id": f"eq.{user_id}"})
    if not users: raise HTTPException(404, "user not found")
    user = users[0]
    new_count = (user.get("warn_count") or 0) + 1
    
    auto_banned = False
    if new_count >= max_warns:
        await _sb_patch("chat_site_users", {"id": f"eq.{user_id}"}, {
            "warn_count": new_count,
            "is_banned": True,
            "ban_reason": f"Авто-бан: {new_count} варнов"
        })
        auto_banned = True
    else:
        await _sb_patch("chat_site_users", {"id": f"eq.{user_id}"}, {
            "warn_count": new_count
        })

    return {"ok": True, "warn": warn, "warn_count": new_count, "auto_banned": auto_banned}


@app.get("/api/chat/site/{slug}/users/{user_id}/warns")
async def chat_get_user_warns(slug: str, user_id: str, role: str = "admin"):
    if role not in ("admin", "owner"): raise HTTPException(403)
    sites = await _sb_get("chat_sites", {"slug": f"eq.{slug}"})
    if not sites: raise HTTPException(404)
    return await _sb_get("chat_user_warns", {
        "site_id": f"eq.{sites[0]['id']}",
        "user_id": f"eq.{user_id}",
        "order": "created_at.desc"
    })


@app.delete("/api/chat/site/{slug}/users/{user_id}/warns")
async def chat_clear_warns(slug: str, user_id: str, role: str = "owner"):
    """Сбросить все варны (только owner)."""
    if role != "owner": raise HTTPException(403)
    sites = await _sb_get("chat_sites", {"slug": f"eq.{slug}"})
    if not sites: raise HTTPException(404)
    site_id = sites[0]["id"]
    # Удаляем через Supabase REST
    async with httpx.AsyncClient(
        base_url=f"{S_URL}/rest/v1/",
        headers={"apikey": S_KEY, "Authorization": f"Bearer {S_KEY}", "Content-Type": "application/json"}
    ) as client:
        await client.delete("chat_user_warns", params={
            "site_id": f"eq.{site_id}", "user_id": f"eq.{user_id}"
        })
    await _sb_patch("chat_site_users", {"id": f"eq.{user_id}"}, {"warn_count": 0})
    return {"ok": True}


# ─── МЮТЫ ────────────────────────────────────────────────────────────────────

@app.post("/api/chat/site/{slug}/users/{user_id}/mute")
async def chat_mute_user(slug: str, user_id: str, d: dict):
    """
    Замутить/размутить пользователя.
    d: { role, muted_until_ms: 0|timestamp, reason? }
    muted_until_ms=0 — снять мут
    """
    role = d.get("role")
    if role not in ("admin", "owner"): raise HTTPException(403)
    sites = await _sb_get("chat_sites", {"slug": f"eq.{slug}"})
    if not sites: raise HTTPException(404)

    muted_until = d.get("muted_until_ms", 0)
    ok = await _sb_patch("chat_site_users", {"id": f"eq.{user_id}"}, {
        "muted_until": muted_until
    })
    return {"ok": ok, "muted_until": muted_until}


# ─── ГРУППОВОЙ ЧАТ ───────────────────────────────────────────────────────────

@app.get("/api/chat/site/{slug}/group")
async def chat_group_get(slug: str, since: str = None, limit: int = 100):
    """Получить сообщения группового чата."""
    sites = await _sb_get("chat_sites", {"slug": f"eq.{slug}"})
    if not sites: raise HTTPException(404)
    site_id = sites[0]["id"]
    
    params = {
        "site_id": f"eq.{site_id}",
        "is_deleted": "eq.false",
        "order": "created_at.desc", # Берем последние сообщения
        "limit": str(limit)
    }
    
    # Если передана дата, фильтруем сообщения "после этой даты"
    if since and since != "0":
        params["created_at"] = f"gt.{since}"

    messages = await _sb_get("chat_group_messages", params)
    
    # Переворачиваем обратно, чтобы фронтенд получил: [Старое -> Новое]
    return sorted(messages, key=lambda x: x['created_at'])


@app.post("/api/chat/site/{slug}/group")
async def chat_group_send(slug: str, d: dict):
    """Отправить сообщение в групповой чат."""
    from_id   = d.get("from_id")
    from_name = d.get("from_name")
    from_role = d.get("from_role", "user")
    text      = (d.get("text") or "").strip()
    media_url = d.get("media_url")
    media_type = d.get("media_type")
    sticker_emoji = d.get("sticker_emoji")

    if not from_id or not from_name: raise HTTPException(400, "from_id and from_name required")
    if not text and not media_url and not sticker_emoji: raise HTTPException(400, "empty message")

    sites = await _sb_get("chat_sites", {"slug": f"eq.{slug}"})
    if not sites: raise HTTPException(404)
    site_id = sites[0]["id"]

    # Проверяем мут пользователя
    if from_role == "user":
        users = await _sb_get("chat_site_users", {"id": f"eq.{from_id}"})
        if users:
            u = users[0]
            if u.get("is_banned"): raise HTTPException(403, "Вы заблокированы")
            muted_until = u.get("muted_until") or 0
            if muted_until > int(time.time() * 1000):
                dt = datetime.fromtimestamp(muted_until / 1000)
                raise HTTPException(403, f"Вы замучены до {dt.strftime('%H:%M %d.%m')}")

    now = int(time.time() * 1000)
    msg = {
        "id": _gen_id("cgm"),
        "site_id": site_id,
        "from_id": from_id,
        "from_name": from_name,
        "from_role": from_role,
        "text": text or None,
        "media_url": media_url,
        "media_type": media_type,
        "sticker_emoji": sticker_emoji,
        "is_pinned": False,
        "created_at": now,
        "is_deleted": False
    }
    await _sb_post("chat_group_messages", msg)

    # Авто-ответ на команды из конфига сайта
    config = sites[0].get("config") or {}
    auto_replies = config.get("autoReplies", [])
    if text and auto_replies:
        for ar in auto_replies:
            cmd = (ar.get("command") or "").strip()
            reply = (ar.get("reply") or "").strip()
            if cmd and reply and text.lower().startswith(cmd.lower()):
                bot_msg = {
                    "id": _gen_id("cgm"),
                    "site_id": site_id,
                    "from_id": "system",
                    "from_name": config.get("logoText") or "Бот",
                    "from_role": "system",
                    "text": reply,
                    "media_url": None,
                    "media_type": None,
                    "sticker_emoji": None,
                    "is_pinned": False,
                    "created_at": now + 100,
                    "is_deleted": False
                }
                await _sb_post("chat_group_messages", bot_msg)
                break

    return {"ok": True, **msg}


@app.delete("/api/chat/site/{slug}/group/{msg_id}")
async def chat_group_delete_msg(slug: str, msg_id: str, role: str = "admin"):
    """Удалить сообщение из группового чата (только admin/owner)."""
    if role not in ("admin", "owner"): raise HTTPException(403)
    ok = await _sb_patch("chat_group_messages", {"id": f"eq.{msg_id}"}, {"is_deleted": True})
    return {"ok": ok}


@app.post("/api/chat/site/{slug}/group/{msg_id}/pin")
async def chat_group_pin_msg(slug: str, msg_id: str, d: dict):
    """Закрепить / открепить сообщение."""
    role = d.get("role")
    if role not in ("admin", "owner"): raise HTTPException(403)
    pin = d.get("pin", True)
    pinned_by = d.get("pinned_by", "")
    ok = await _sb_patch("chat_group_messages", {"id": f"eq.{msg_id}"}, {
        "is_pinned": pin,
        "pinned_by": pinned_by if pin else None
    })
    return {"ok": ok}


@app.get("/api/chat/site/{slug}/group/pinned")
async def chat_group_pinned(slug: str):
    """Получить закреплённые сообщения."""
    sites = await _sb_get("chat_sites", {"slug": f"eq.{slug}"})
    if not sites: raise HTTPException(404)
    return await _sb_get("chat_group_messages", {
        "site_id": f"eq.{sites[0]['id']}",
        "is_pinned": "eq.true",
        "is_deleted": "eq.false",
        "order": "created_at.desc"
    })


# ─── АВТО-ОТВЕТЫ (в личных диалогах) ────────────────────────────────────────
# Авто-ответ уже интегрирован в /api/chat/site/{slug}/message
# (нужно добавить проверку в существующий эндпоинт отправки сообщения)
# В функции chat_send_message (найдите её в server.py) добавьте после сохранения msg:
#
# config = site.get("config") or {}
# auto_replies = config.get("autoReplies", [])
# if text and auto_replies and from_role == "user":
#     for ar in auto_replies:
#         cmd = (ar.get("command") or "").strip()
#         reply_text = (ar.get("reply") or "").strip()
#         if cmd and reply_text and text.lower().startswith(cmd.lower()):
#             bot_reply = { ...системное сообщение от бота... }
#             await _sb_post("chat_site_messages", bot_reply)
#             break


# ─── ЛИЦЕНЗИОННЫЕ КЛЮЧИ ───────────────────────────────────────────────────────

@app.post("/api/chat/keys/generate")
async def chat_key_generate(d: dict):
    """
    Генерация нового ключа доступа.
    Только для супер-администратора (проверяем admin_token).
    d: { admin_token, owner_id, duration_days?, price_rub?, note? }
    """
    if d.get("admin_token") != A_SECRET:
        raise HTTPException(403, "Unauthorized")
    
    owner_id = d.get("owner_id", "system")
    duration_days = int(d.get("duration_days", 30))
    price_rub = int(d.get("price_rub", 150))
    note = d.get("note", "")
    
    # Генерируем красивый ключ вида: CHAT-XXXX-XXXX-XXXX
    raw = secrets.token_hex(6).upper()
    key_code = f"CHAT-{raw[:4]}-{raw[4:8]}-{raw[8:12]}"
    
    now = int(time.time() * 1000)
    key_obj = {
        "id": _gen_id("cky"),
        "key_code": key_code,
        "site_id": None,
        "owner_id": owner_id,
        "duration_days": duration_days,
        "price_rub": price_rub,
        "activated_at": None,
        "expires_at": None,
        "created_at": now,
        "is_active": True,
        "note": note
    }
    await _sb_post("chat_site_keys", key_obj)
    return {"ok": True, "key_code": key_code, "duration_days": duration_days}


@app.post("/api/chat/sites/{site_id}/activate-key")
async def chat_activate_key(site_id: str, d: dict):
    """
    Активировать ключ для сайта.
    d: { owner_id, key_code }
    """
    owner_id = d.get("owner_id")
    key_code = (d.get("key_code") or "").strip().upper()
    if not key_code: raise HTTPException(400, "key_code required")

    # Проверяем сайт
    sites = await _sb_get("chat_sites", {"id": f"eq.{site_id}"})
    if not sites: raise HTTPException(404, "site not found")
    if sites[0].get("owner_id") != owner_id: raise HTTPException(403)

    # Проверяем ключ
    keys = await _sb_get("chat_site_keys", {"key_code": f"eq.{key_code}", "is_active": "eq.true"})
    if not keys: raise HTTPException(404, "Ключ не найден или уже использован")
    key = keys[0]
    if key.get("site_id"): raise HTTPException(409, "Ключ уже активирован")

    now = int(time.time() * 1000)
    duration_ms = key["duration_days"] * 86_400_000
    expires_at = now + duration_ms

    await _sb_patch("chat_site_keys", {"id": f"eq.{key['id']}"}, {
        "site_id": site_id,
        "activated_at": now,
        "expires_at": expires_at,
        "is_active": True
    })
    return {
        "ok": True,
        "expires_at": expires_at,
        "duration_days": key["duration_days"],
        "expires_formatted": datetime.fromtimestamp(expires_at / 1000).strftime("%d.%m.%Y")
    }


@app.get("/api/chat/sites/{site_id}/license")
async def chat_get_license(site_id: str, owner_id: str):
    """Получить информацию о лицензии сайта."""
    sites = await _sb_get("chat_sites", {"id": f"eq.{site_id}"})
    if not sites: raise HTTPException(404)
    if sites[0].get("owner_id") != owner_id: raise HTTPException(403)

    keys = await _sb_get("chat_site_keys", {
        "site_id": f"eq.{site_id}",
        "is_active": "eq.true",
        "order": "expires_at.desc"
    })
    if not keys:
        return {"active": False, "expires_at": None}
    
    key = keys[0]
    now = int(time.time() * 1000)
    expires_at = key.get("expires_at") or 0
    active = expires_at > now
    days_left = max(0, int((expires_at - now) / 86_400_000)) if active else 0
    
    return {
        "active": active,
        "expires_at": expires_at,
        "days_left": days_left,
        "expires_formatted": datetime.fromtimestamp(expires_at / 1000).strftime("%d.%m.%Y") if expires_at else None
    }


# ─── СТАТУС ОНЛАЙН АДМИНИСТРАТОРА ────────────────────────────────────────────

@app.post("/api/chat/sites/{site_id}/admins/{admin_id}/online")
async def chat_admin_set_online(site_id: str, admin_id: str, d: dict):
    """
    Установить статус онлайн/оффлайн для администратора.
    d: { is_online: bool, session_token? }
    """
    is_online = bool(d.get("is_online", False))
    now = int(time.time() * 1000)
    
    patch_data = {
        "is_online": is_online,
        "last_seen": now
    }
    ok = await _sb_patch("chat_site_admins", {"id": f"eq.{admin_id}", "site_id": f"eq.{site_id}"}, patch_data)
    return {"ok": ok, "is_online": is_online}


# ─── ЗАГРУЗКА ФАЙЛОВ (улучшенная версия) ─────────────────────────────────────

@app.post("/api/chat/media/upload")
async def chat_upload_media_v2(request: Request):
    """
    Загрузка медиафайлов на жёсткий диск сервера.
    Поддерживает: изображения, видео, аудио (голосовые), файлы.
    Возвращает публичный URL вида /uploads/chat/...
    """
    import aiofiles

    form = await request.form()
    file_field = form.get("file")
    if not file_field:
        raise HTTPException(400, "file required")

    original_name = getattr(file_field, "filename", f"upload_{int(time.time())}")
    content = await file_field.read()
    
    if not content:
        raise HTTPException(400, "empty file")
    
    # Ограничение размера: 50MB
    MAX_SIZE = 50 * 1024 * 1024
    if len(content) > MAX_SIZE:
        raise HTTPException(413, "Файл слишком большой (макс. 50MB)")

    ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else "bin"
    
    # Маппинг расширений в типы
    MEDIA_MAP = {
        "jpg": "image", "jpeg": "image", "png": "image", 
        "gif": "image", "webp": "image", "bmp": "image",
        "mp4": "video", "mov": "video", "webm": "video", "avi": "video", "mkv": "video",
        "mp3": "audio", "ogg": "audio", "wav": "audio", 
        "m4a": "audio", "opus": "audio", "aac": "audio",
        "pdf": "file", "doc": "file", "docx": "file",
        "xls": "file", "xlsx": "file", "txt": "file",
        "zip": "file", "rar": "file", "7z": "file",
    }
    media_type = MEDIA_MAP.get(ext, "file")
    
    # Для голосовых сообщений
    is_voice = form.get("is_voice") == "true"
    if is_voice:
        media_type = "audio"
        subdir = "voice"
    elif media_type == "image":
        subdir = "images"
    elif media_type == "video":
        subdir = "videos"
    elif media_type == "audio":
        subdir = "audio"
    else:
        subdir = "files"
    
    save_dir = f"uploads/chat/{subdir}"
    os.makedirs(save_dir, exist_ok=True)
    
    # Безопасное имя файла
    safe_name = f"{int(time.time())}_{secrets.token_hex(6)}.{ext}"
    save_path = f"{save_dir}/{safe_name}"
    
    async with aiofiles.open(save_path, "wb") as f:
        await f.write(content)
    
    public_url = f"/uploads/chat/{subdir}/{safe_name}"
    
    # Размер в читаемом виде
    size = len(content)
    if size < 1024:
        size_str = f"{size} B"
    elif size < 1024 * 1024:
        size_str = f"{size // 1024} KB"
    else:
        size_str = f"{size // (1024 * 1024)} MB"
    
    return {
        "url": public_url,
        "media_type": media_type,
        "filename": original_name,
        "size": size,
        "size_str": size_str,
        "is_voice": is_voice
    }


# ─── ПРОВЕРКА МУТА ПРИ ОТПРАВКЕ СООБЩЕНИЯ ────────────────────────────────────
# В существующем эндпоинте chat_send_message добавить в начало (после получения user):
#
# if from_role == "user":
#     muted_until = user.get("muted_until") or 0
#     now_ms = int(time.time() * 1000)
#     if muted_until > now_ms:
#         dt = datetime.fromtimestamp(muted_until / 1000)
#         raise HTTPException(403, f"Вы замучены до {dt.strftime('%H:%M %d.%m.%Y')}")


# ─── МОНТИРОВАНИЕ СТАТИЧЕСКИХ ФАЙЛОВ ─────────────────────────────────────────
# ВАЖНО: добавить эти строки ПОСЛЕ создания app = FastAPI(...):
#
# from fastapi.staticfiles import StaticFiles
# os.makedirs("uploads", exist_ok=True)
# app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
#
# Это позволяет отдавать файлы из /uploads/chat/... напрямую.



if __name__ == "__main__":
    import uvicorn
    # Запуск сервера на порту 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
