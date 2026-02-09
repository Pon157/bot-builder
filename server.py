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

    async def stop_bot(self, bid: str):
        """Безопасная остановка процесса."""
        p = self.procs.get(bid)
        if p:
            try:
                p.terminate()
                await asyncio.wait_for(p.wait(), timeout=3.0)
            except:
                if p: p.kill()
            finally:
                if bid in self.procs: del self.procs[bid]
        return True

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
    async with httpx.AsyncClient(base_url=f"{S_URL}/rest/v1/", 
                                 headers={"apikey": S_KEY, "Authorization": f"Bearer {S_KEY}"}) as client:
        try:
            # Автостарт ботов, которые были включены
            r = await client.get("bots", params={"status": "eq.RUNNING"})
            if r.status_code == 200:
                for b in r.json():
                    cfg = {**(b.get("config") or {}), **b}
                    await pm.start_bot(b['id'], cfg)
        except Exception as e:
            logger.error(f"Ошибка автозапуска: {e}")
    
    yield
    
    logger.info("--- Сервер останавливается ---")
    for bid in list(pm.procs.keys()):
        await pm.stop_bot(bid)

app = FastAPI(lifespan=lifespan)

# === НАЧАЛО БЛОКА ЗАЩИТЫ ===
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # HSTS - заставляет использовать HTTPS
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # Защита от кликджекинга
        response.headers["X-Frame-Options"] = "DENY"
        # Защита от подмены типов файлов
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Управление передачей реферера
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Настройка CSP (разрешаем работу твоего API и Supabase)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            f"connect-src 'self' {S_URL}; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline';"
        )
        return response

app.add_middleware(SecurityHeadersMiddleware)
# === КОНЕЦ БЛОКА ЗАЩИТЫ ===

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Глобальный клиент БД
db = httpx.AsyncClient(
    base_url=f"{S_URL}/rest/v1/", 
    headers={"apikey": S_KEY, "Authorization": f"Bearer {S_KEY}", "Content-Type": "application/json"}
)

# ==========================================
# 4. ЭНДПОИНТЫ АВТОРИЗАЦИИ
# ==========================================

@app.post("/api/auth/login")
async def login(d: dict):
    hpwd = hash_pwd(d['password'])
    r = await db.get("users", params={"email": f"eq.{d['email'].lower()}", "password": f"eq.{hpwd}"})
    data = r.json()
    if not data: raise HTTPException(401, "Неверный логин или пароль")
    return data[0]

@app.post("/api/auth/request-verification")
async def request_ver(d: dict):
    email = d['email'].lower()
    code = str(random.randint(100000, 999999))
    await db.post("temp_codes", json={
        "email": email, "code": code, "type": "VERIFY"
    }, headers={"Prefer": "resolution=merge-duplicates"})
    
    if EmailService.send_verification_code(email, code):
        return True
    raise HTTPException(500, "Ошибка почтового сервера")

@app.post("/api/auth/verify-and-register")
async def verify_reg(d: dict):
    email = d['email'].lower()
    
    # Проверка кода из базы
    r = await db.get("temp_codes", params={"email": f"eq.{email}", "code": f"eq.{d['code']}"})
    if not r.json():
        raise HTTPException(400, "Неверный код подтверждения")
    
    uid = f"u_{secrets.token_hex(4)}"
    
    # Формируем данные пользователя
    user_data = {
        "id": uid,
        "username": d['username'],
        "email": email,
        "password": hash_pwd(d['password']), 
        "balance": 0,
        "license_expires_at": int(time.time()*1000) + 259200000, # +3 дня бонуса
        # ДОБАВЛЯЕМ ЭТУ СТРОКУ:
        "marketing_consent": d.get('marketing_consent', False) 
    }
    
    # Отправляем в Supabase
    await db.post("users", json=user_data)
    
    # Очищаем код
    await db.delete("temp_codes", params={"email": f"eq.{email}"})
    
    return user_data

@app.post("/api/auth/forgot-password")
async def forgot_p(d: dict):
    email = d['email'].lower()
    u = await db.get("users", params={"email": f"eq.{email}"})
    if not u.json(): return True
    
    code = str(random.randint(100000, 999999))
    await db.post("temp_codes", json={"email": email, "code": code, "type": "RESET"}, headers={"Prefer": "resolution=merge-duplicates"})
    EmailService.send_password_reset(email, code)
    return True

@app.post("/api/auth/reset-password")
async def reset_p(d: dict):
    email = d['email'].lower()
    r = await db.get("temp_codes", params={"email": f"eq.{email}", "code": f"eq.{d['code']}", "type": "eq.RESET"})
    if not r.json(): raise HTTPException(400, "Код недействителен")
    
    new_hpwd = hash_pwd(d['newPassword'])
    await db.patch("users", params={"email": f"eq.{email}"}, json={"password": new_hpwd})
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
    
    # --- ДОБАВЛЕНА ПРОВЕРКА ЛИЦЕНЗИИ ---
    curr_time_ms = int(time.time() * 1000)
    expiry = data.get("license_expires_at", 0)
    
    if expiry < curr_time_ms:
        raise HTTPException(403, "Срок действия лицензии истек. Продлите лицензию для запуска.")
    # ----------------------------------

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

