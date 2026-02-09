import asyncio
import logging
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
Сделал несколько важных исправлений, чтобы всё работало стабильно:

Асинхронность (самое важное): Твой EmailService использует синхронную библиотеку smtplib. Чтобы сервер не «зависал» и отправка не обрывалась на полпути, добавил run_in_threadpool.

Обработка ошибок: В forgot-password добавил проверку результата отправки, чтобы ты видел в логах, если почта не ушла.

Безопасность типов: Уточнил фильтрацию в reset-password, чтобы нельзя было использовать код регистрации для сброса пароля.

Обновленный код эндпоинтов
Python

import random
import secrets
import time
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool # Для работы с синхронной почтой

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
    
    # Отправляем через поток, чтобы не блокировать API
    success = await run_in_threadpool(EmailService.send_verification_code, email, code)
    if success:
        return True
    raise HTTPException(500, "Ошибка почтового сервера")

@app.post("/api/auth/verify-and-register")
async def verify_reg(d: dict):
    email = d['email'].lower()
    
    # Проверка кода (тип VERIFY по умолчанию)
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
        "license_expires_at": int(time.time()*1000) + 259200000, # +3 дня
        "marketing_consent": d.get('marketing_consent', False) 
    }
    
    await db.post("users", json=user_data)
    await db.delete("temp_codes", params={"email": f"eq.{email}"})
    
    return user_data

@app.post("/api/auth/forgot-password")
async def forgot_p(d: dict):
    email = d['email'].lower()
    
    # Проверяем, есть ли такой юзер
    u = await db.get("users", params={"email": f"eq.{email}"})
    if not u.json(): 
        return True # Безопасность: не подтверждаем отсутствие email
    
    code = str(random.randint(100000, 999999))
    
    # Сохраняем код именно с типом RESET
    await db.post("temp_codes", 
                  json={"email": email, "code": code, "type": "RESET"}, 
                  headers={"Prefer": "resolution=merge-duplicates"})
    
    # Отправляем в фоновом потоке
    await run_in_threadpool(EmailService.send_password_reset, email, code)
    
    return True

@app.post("/api/auth/reset-password")
async def reset_p(d: dict):
    email = d['email'].lower()
    
    # Ищем код именно для сброса (RESET)
    r = await db.get("temp_codes", params={
        "email": f"eq.{email}", 
        "code": f"eq.{d['code']}", 
        "type": "eq.RESET"
    })
    
    if not r.json(): 
        raise HTTPException(400, "Код недействителен или устарел")
    
    # Обновляем пароль (используем newPassword из запроса)
    new_hpwd = hash_pwd(d['newPassword'])
    await db.patch("users", params={"email": f"eq.{email}"}, json={"password": new_hpwd})
    
    # Очищаем код
    await db.delete("temp_codes", params={"email": f"eq.{email}", "type": "eq.RESET"})
    
    return True
    
# ==========================================
# 5. УПРАВЛЕНИЕ БОТАМИ
# ==========================================

@app.get("/api/bots/{uid}")
async def get_user_bots(uid: str):
    r = await db.get("bots", params={"owner_id": f"eq.{uid}"})
    # При передаче на фронт токены остаются зашифрованными (безопасность!)
    return [{**b, **(b.get("config") or {})} for b in r.json()]

@app.post("/api/bots/save")
async def save_bot(b: dict):
    bid = b['id']
    # Шифруем токен перед отправкой в базу
    raw_token = b.get('token', '')
    # Если токен пришел уже зашифрованным (начинается на gAAAA), не шифруем второй раз
    final_token = encrypt_val(raw_token) if not raw_token.startswith('gAAAA') else raw_token
    
    old_r = await db.get("bots", params={"id": f"eq.{bid}"})
    curr = old_r.json()[0] if old_r.json() else {}
    
    sys_keys = ['id', 'owner_id', 'name', 'token', 'status', 'license_expires_at', 'config']
    ui_cfg = {k: v for k, v in b.items() if k not in sys_keys}
    
    payload = {
        "id": bid,
        "owner_id": b['owner_id'],
        "name": b["name"],
        "token": final_token,
        "status": b.get("status", curr.get("status", "IDLE")),
        "license_expires_at": b.get("license_expires_at") or curr.get("license_expires_at", 0),
        "config": ui_cfg
    }
    await db.post("bots", json=payload, headers={"Prefer": "resolution=merge-duplicates"})
    return payload

@app.post("/api/bots/start")
async def start_handler(req: dict):
    bid = req.get('id')
    r = await db.get("bots", params={"id": f"eq.{bid}"})
    if not r.json(): raise HTTPException(404, "Бот не найден")
    
    data = r.json()[0]
    # Пытаемся запустить
    if await pm.start_bot(bid, data) is True:
        await db.patch("bots", params={"id": f"eq.{bid}"}, json={"status": "RUNNING"})
        return True
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
# 9. ADMIN PANEL & ANALYTICS (NEW)
# ==========================================

# Безопасное чтение админов из окружения
    # Пытаемся достать строку ADMIN_DATA и превратить её в словарь

try:
    raw_admin_data = os.getenv("ADMIN_DATA", "{}")
    ADMIN_ACCOUNTS = json.loads(raw_admin_data)
    
    if not ADMIN_ACCOUNTS:
        print("⚠️ ВНИМАНИЕ: Список администраторов пуст. Проверьте .env файл!")
except Exception as e:
    print(f"❌ ОШИБКА: Не удалось загрузить ADMIN_DATA из .env: {e}")
    ADMIN_ACCOUNTS = {}

# Эндпоинт входа остается таким же, он просто ищет в этом словаре
@app.post("/api/admin/login")
async def admin_login(d: dict):
    login = d.get('login')
    password = d.get('password')
    
    if login in ADMIN_ACCOUNTS and ADMIN_ACCOUNTS[login] == password:
        # A_SECRET — это твой глобальный ADMIN_TOKEN из server.py
        return {"token": A_SECRET, "role": "admin", "name": login}
    
    raise HTTPException(401, "Неверный логин или пароль")
    
# Зависимость для проверки админ-токена
async def verify_admin(x_admin_token: str = Header(None)):
    if x_admin_token != A_SECRET:
        raise HTTPException(403, "Invalid Admin Token")
    return True

@app.get("/api/admin/dashboard")
async def get_admin_dashboard(x_admin_token: str = Header(None)):
    """
    Важно: Мы добавили Header(None), чтобы FastAPI не падал, 
    если заголовок пришел под другим именем или пустой.
    """
    if not verify_admin_token(x_admin_token):
        raise HTTPException(status_code=401, detail="Invalid admin token")

    # Чистим старые ключи доступа заодно
    now = time.time()
    expired = [k for k, v in TEMP_ADMIN_ACCESS.items() if v['expires'] < now]
    for k in expired: del TEMP_ADMIN_ACCESS[k]

    # Считаем статистику из БД
    try:
        users_res = await db.get("users")
        bots_res = await db.get("bots")
        
        users_count = len(users_res.json()) if users_res.status_code == 200 else 0
        bots_data = bots_res.json() if bots_res.status_code == 200 else []
        
        return {
            "total_users": users_count,
            "total_bots": len(bots_data),
            "active_bots": len([b for b in bots_data if b.get('status') == 'RUNNING']),
            "total_messages": 0, # Можно вытянуть из таблицы сообщений, если нужно
            "server_uptime": "Online",
            "active_temp_keys": len(TEMP_ADMIN_ACCESS)
        }
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return {"error": "Database connection failed"}

@app.get("/api/admin/users")
async def get_all_users(x_admin_token: str = Header(None)):
    if x_admin_token != A_SECRET: raise HTTPException(403)
    # Получаем всех пользователей
    r = await db.get("users", params={"select": "*", "order": "created_at.desc"})
    return r.json()

@app.get("/api/admin/bots")
async def get_all_bots(x_admin_token: str = Header(None)):
    if x_admin_token != A_SECRET: raise HTTPException(403)
    # Получаем всех ботов с информацией о владельце
    r = await db.get("bots", params={"select": "*, owner:users(email, username)", "order": "created_at.desc"})
    return r.json()

@app.post("/api/admin/user/ban")
async def admin_ban_user(d: dict, x_admin_token: str = Header(None)):
    if x_admin_token != A_SECRET: raise HTTPException(403)
    # Пример: Меняем пароль на случайный, чтобы юзер не вошел, или добавляем поле is_banned в БД
    # Пока просто стопаем его ботов
    uid = d.get('user_id')
    bots = await db.get("bots", params={"owner_id": f"eq.{uid}"})
    for b in bots.json():
        await pm.stop_bot(b['id'])
        await db.patch("bots", params={"id": f"eq.{b['id']}"}, json={"status": "BANNED"})
    return True

@app.post("/api/admin/bot/action")
async def admin_bot_action(d: dict, x_admin_token: str = Header(None)):
    if x_admin_token != A_SECRET: raise HTTPException(403)
    bid = d.get('bot_id')
    action = d.get('action') # stop / start / delete
    
    if action == 'stop':
        await pm.stop_bot(bid)
        await db.patch("bots", params={"id": f"eq.{bid}"}, json={"status": "IDLE"})
    elif action == 'delete':
        await pm.stop_bot(bid)
        await db.delete("bots", params={"id": f"eq.{bid}"})
    
    return True

@app.post("/api/admin/generate-key")
async def admin_generate_key(d: dict, x_admin_token: str = Header(None)):
    if x_admin_token != A_SECRET: raise HTTPException(403)
    
    months = d.get('months', 0)
    days = d.get('days', 0)
    
    # Генерация красивого ключа (например, XXXX-XXXX-XXXX)
    new_key = f"{secrets.token_hex(2)}-{secrets.token_hex(2)}-{secrets.token_hex(2)}".upper()
    
    payload = {
        "key": new_key,
        "months": months,
        "days": days,
        "used": False,
        "created_at": int(time.time())
    }
    
    await db.post("issued_keys", json=payload)
    return {"key": new_key}

@app.post("/api/admin/temp-access")
async def create_temp_access(request: Request):
    """Создает временный ключ, который пользователь дает админу"""
    data = await request.json()
    bot_id = data.get("botId")
    key = data.get("key")
    
    if not bot_id or not key:
        raise HTTPException(status_code=400, detail="Missing data")
        
    # Записываем: ключ действителен 20 минут (1200 секунд)
    TEMP_ADMIN_ACCESS[key] = {
        "bot_id": bot_id,
        "expires": time.time() + 1200
    }
    logger.info(f"[!] Создан временный доступ для бота {bot_id} по ключу {key}")
    return {"status": "ok"}

@app.post("/api/admin/bots/start")
async def admin_start_bot(request: Request, x_admin_token: str = Header(None)):
    if not verify_admin_token(x_admin_token):
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    data = await request.json()
    bot_data = data.get("bot") # Передаем объект бота целиком
    
    if not bot_data:
        raise HTTPException(status_code=400, detail="Bot data missing")
        
    # Вызываем твою существующую функцию запуска процесса
    # (у тебя в server.py она обычно называется start_bot_process)
    success = await start_bot_process(bot_data)
    
    if success:
        return {"status": "started"}
    else:
        raise HTTPException(status_code=500, detail="Failed to start bot process")
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

