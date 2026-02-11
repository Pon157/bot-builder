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
        """Запуск отдельного процесса для бота."""
        await self.stop_bot(bid)
        
        os.makedirs("active_bots", exist_ok=True)
        cfg_path = f"active_bots/cfg_{bid}.json"
        log_path = f"active_bots/bot_{bid}.log"
        
        # Расшифровываем токен для реальной работы
        raw_token = decrypt_val(config.get('token', ''))
        config['token'] = raw_token
        
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        
        self.log_paths[bid] = log_path
        
        try:
            env = os.environ.copy()
            env.update({"SUPABASE_URL": S_URL, "SUPABASE_KEY": S_KEY})
            l_out = open(log_path, "a", encoding="utf-8")
            
            p = await asyncio.create_subprocess_exec(
                sys.executable, "bot_core.py", cfg_path,
                stdout=l_out, stderr=l_out, env=env
            )
            self.procs[bid] = p
            logger.info(f"🚀 Бот {bid} запущен (PID: {p.pid})")
            return True
        except Exception as e:
            logger.error(f"❌ Критическая ошибка запуска {bid}: {e}")
            return str(e)

    async def stop_bot(self, bot_id: str):
        p = self.procs.get(bot_id)
        if p:
            try:
                # Пытаемся корректно завершить процесс
                p.terminate() 
                # Даем немного времени на выход, если не вышел — убиваем
                try:
                    await asyncio.wait_for(p.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    p.kill()
            except ProcessLookupError:
                # Если процесса уже нет в системе — просто игнорируем
                logger.warning(f"Процесс {bot_id} уже не существует.")
            except Exception as e:
                logger.error(f"Ошибка при остановке {bot_id}: {e}")
            
            # В любом случае удаляем из списка активных и чистим файл конфига
            self.procs.pop(bot_id, None)
            cfg_path = f"config_{bot_id}.json"
            if os.path.exists(cfg_path):
                os.remove(cfg_path)

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
                    cfg = {**(b.get("config") or {}), **b}
                    await pm.start_bot(b['id'], cfg)
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
# ==========================================
# 4. ЭНДПОИНТЫ АВТОРИЗАЦИИ
# ==========================================

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
    """
    Отдает статистику конкретного бота. 
    Структура должна быть {"stats": {...}}, иначе фронт упадет.
    """
    try:
        # Пока отдаем заглушку, чтобы оживить интерфейс
        # Позже здесь можно сделать реальный запрос к БД
        return {
            "stats": {
                "total_messages": 0,
                "active_users": 0,
                "new_users_today": 0,
                "commands_executed": 0
            }
        }
    except Exception as e:
        logger.error(f"Error in get_bot_stats: {e}")
        return {"stats": {"total_messages": 0, "active_users": 0}}

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
            
            # 2. РАСПАКОВКА (Важно: даем значения по умолчанию, чтобы не было null/undefined)
            # Добавляем и snake_case и camelCase на всякий случай для фронта
            bot["vk_group_id"] = cfg.get("vk_group_id") or ""
            bot["vkGroupId"] = cfg.get("vk_group_id") or ""
            
            bot["admin_chat_id"] = cfg.get("admin_chat_id") or ""
            bot["adminChatId"] = cfg.get("admin_chat_id") or ""
            
            bot["buttons"] = cfg.get("buttons") if cfg.get("buttons") is not None else []
            bot["triggers"] = cfg.get("triggers") if cfg.get("triggers") is not None else []
            
            # Настройки тоже должны быть всегда словарем
            bot["settings"] = cfg.get("settings") if isinstance(cfg.get("settings"), dict) else {
                "forwardToAdmin": True,
                "antiSpam": False,
                "showHeaderId": True
            }
            
        return bots
    except Exception as e:
        logger.error(f"🚨 Error getting bots: {e}")
        return []

@app.post("/api/bots/save")
async def save_bot(b: dict):
    try:
        bid = b.get('id')
        if not bid:
            raise HTTPException(400, "Missing bot ID")

        # 1. Загружаем текущие данные из базы
        old_r = await db.get("bots", params={"id": f"eq.{bid}"})
        curr = old_r.json()[0] if (old_r.status_code == 200 and old_r.json()) else {}
        old_config = curr.get("config", {})
        if not isinstance(old_config, dict):
            old_config = {}

        # 2. Извлекаем входящий конфиг (если фронт прислал данные внутри него)
        inc_cfg = b.get("config", {})
        if not isinstance(inc_cfg, dict):
            inc_cfg = {}

        # Функция-помощник: берет первое значение, которое не является None
        # Это позволяет сохранять пустые строки "", если ты их ввел в инпут
        def pick(*args):
            for a in args:
                if a is not None:
                    return a
            return None

        # 3. Собираем переменные с жестким приоритетом: 
        # Корень запроса > Объект config в запросе > Старая база
        vk_id = pick(b.get("vk_group_id"), inc_cfg.get("vk_group_id"), old_config.get("vk_group_id"))
        
        adm_id = pick(
            b.get("admin_chat_id"), 
            b.get("adminChatId"), 
            inc_cfg.get("admin_chat_id"), 
            inc_cfg.get("adminChatId"), 
            old_config.get("admin_chat_id")
        )

        welcome = pick(
            b.get("welcomeMessage"), 
            inc_cfg.get("welcomeMessage"), 
            old_config.get("welcomeMessage")
        )

        # 4. Формируем финальный объект config (JSONB)
        ui_config = {
            "buttons": pick(b.get("buttons"), inc_cfg.get("buttons"), old_config.get("buttons"), []),
            "triggers": pick(b.get("triggers"), inc_cfg.get("triggers"), old_config.get("triggers"), []),
            "welcomeMessage": welcome if welcome is not None else "Здравствуйте!",
            "vk_group_id": vk_id,
            "admin_chat_id": adm_id,
            "adminChatId": adm_id, # Дублируем для совместимости со старым кодом ботов
            "settings": {
                **old_config.get("settings", {}),
                **inc_cfg.get("settings", {}),
                **b.get("settings", {})
            }
        }

        # Логируем результат перед отправкой в базу
        logger.info(f"🔒 FINAL SAVE -> VK: {vk_id} | ADMIN: {adm_id} | WELCOME: {str(welcome)[:15] if welcome else 'None'}...")

        # Обработка токена (шифруем только если это не зашифрованная строка gAAAA...)
        raw_token = b.get('token')
        if raw_token:
            final_token = encrypt_val(raw_token) if not str(raw_token).startswith('gAAAA') else raw_token
        else:
            final_token = curr.get('token', '')

        # 5. Подготовка данных для Supabase
        db_payload = {
            "name": b.get("name") or curr.get("name"),
            "token": final_token,
            "platform": b.get('platform') or curr.get('platform'),
            "config": ui_config 
        }

        # Отправляем PATCH запрос
        res = await db.patch("bots", params={"id": f"eq.{bid}"}, json=db_payload)
        
        if res.status_code not in [200, 201, 204]:
            logger.error(f"❌ Supabase Error: {res.text}")
            raise HTTPException(res.status_code, f"DB Error: {res.text}")

        # Возвращаем объединенный объект, чтобы фронтенд сразу обновил интерфейс
        return {
            **curr,
            **db_payload,
            "vk_group_id": vk_id,
            "admin_chat_id": adm_id,
            "welcomeMessage": welcome
        }

    except Exception as e:
        logger.error(f"🚨 Save error: {e}", exc_info=True)
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

    # 3. Пытаемся запустить процесс
    # Передаем bot_data целиком, чтобы pm имел доступ к токену и конфигу
    if await pm.start_bot(bid, bot_data) is True:
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
    
    key = f"DE-{secrets.token_hex(3).upper()}-{random.randint(100, 999)}"
    payload = {
        "key": key,
        "months": d.get('months', 1),
        "days": d.get('days', 0),
        "used": False
    }
    await db.post("issued_keys", json=payload)
    return {"key": key}

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
# 7. МАССОВАЯ РАССЫЛКА
# ==========================================

@app.post("/api/bots/broadcast")
async def broadcast_msg(d: dict):
    bot_ids = d.get('botIds', [])
    text = d.get('message', '')
    if not text: return {"error": "Пустое сообщение"}

    results = {"success": 0, "failed": 0}
    
    for bid in bot_ids:
        r = await db.get("bots", params={"id": f"eq.{bid}"})
        if not r.json(): continue
        
        b_data = r.json()[0]
        # Расшифровка для работы Bot API
        token = decrypt_val(b_data['token'])
        users = (b_data.get('config') or {}).get('connectedUsers', [])
        
        async with Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML)) as bot:
            for u in users:
                try:
                    # u может быть словарем или просто ID
                    user_id = u['id'] if isinstance(u, dict) else u
                    await bot.send_message(user_id, text)
                    results["success"] += 1
                except Exception as e:
                    logger.warning(f"Ошибка рассылки юзеру {u}: {e}")
                    results["failed"] += 1
                await asyncio.sleep(0.05) # Защита от флуд-контроля
                
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
        owner_id = d.get('owner_id')
        name = d.get('name', 'New Bot')
        token = d.get('token', '')
        platform = d.get('platform', 'telegram')

        if not owner_id or not token:
            raise HTTPException(400, "Owner ID and Token are required")

        bot_id = f"b_{secrets.token_hex(4)}"
        encrypted_token = encrypt_val(token)

        # Формируем объект ПРАВИЛЬНО с самого начала
        new_bot_payload = {
            "id": bot_id,
            "owner_id": owner_id,
            "name": name,
            "token": encrypted_token,
            "platform": platform,
            "status": "IDLE",
            "created_at": int(time.time() * 1000),
            "license_expires_at": int(time.time() * 1000) + (24 * 3600 * 1000),
            "config": {
                "buttons": [],
                "triggers": [],
                # Инициализируем поля ВК/Админа, чтобы они существовали в JSONB
                "vk_group_id": None, 
                "admin_chat_id": None,
                "settings": {
                    "forwardToAdmin": True,
                    "antiSpam": False,
                    "showHeaderId": True
                }
            }
        }

        # Сохраняем в Supabase
        res = await db.post("bots", json=new_bot_payload)
        
        if res.status_code not in [200, 201, 204]:
            logger.error(f"DB Error on create: {res.text}")
            raise HTTPException(res.status_code, f"Database error: {res.text}")

        # ВАЖНО: Распаковываем поля для фронтенда перед возвратом
        # Чтобы фронтенд сразу записал их в стейт и инпуты не были undefined
        return {
            **new_bot_payload,
            "vk_group_id": None,
            "admin_chat_id": None,
            "buttons": [],
            "triggers": [],
            "settings": new_bot_payload["config"]["settings"]
        }

    except Exception as e:
        logger.error(f"🚨 Create Bot Error: {e}")
        raise HTTPException(500, str(e))
    
# ==========================================
# 8. СИСТЕМНЫЕ
# ==========================================

@app.get("/api/ping")
async def ping_pong():
    return {"status": "online", "server_time": time.time()}

if __name__ == "__main__":
    import uvicorn
    # Запуск сервера на порту 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
async def ping_pong():
    return {"status": "online", "server_time": time.time()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
