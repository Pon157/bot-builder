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
import shutil
import uuid
from typing import Dict, List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware 
from cryptography.fernet import Fernet
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import FSInputFile

# ОПРЕДЕЛЯЕМ БАЗОВУЮ ДИРЕКТОРИЮ (Где лежит этот скрипт)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

# Создаем папку для загрузок, если нет
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# Импорт сервиса почты (заглушка, если нет файла)
try:
    from email_service import EmailService
except ImportError:
    class EmailService:
        @staticmethod
        def send_verification_code(e, c): return True
        @staticmethod
        def send_password_reset(e, c): return True

# ==========================================
# 1. ИНИЦИАЛИЗАЦИЯ И КОНФИГУРАЦИЯ
# ==========================================
def init_env():
    env_path = os.path.join(BASE_DIR, '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8-sig') as f:
            for l in f:
                l = l.strip()
                if l and not l.startswith('#') and '=' in l:
                    k, v = l.split('=', 1)
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")

init_env()

S_URL = os.getenv("SUPABASE_URL", "").rstrip('/')
S_KEY = os.getenv("SUPABASE_KEY", "")
A_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")
E_KEY = os.getenv("ENCRYPTION_KEY")

if not E_KEY:
    E_KEY = Fernet.generate_key().decode()
    print(f"⚠️ ВНИМАНИЕ: ENCRYPTION_KEY не найден. Использую временный: {E_KEY}")

cipher = Fernet(E_KEY.encode())

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(BASE_DIR, "server.log"), encoding='utf-8')
    ]
)
logger = logging.getLogger("DialogEngineServer")

# --- Утилиты безопасности ---
def hash_pwd(password: str) -> str:
    salt = "dialog_engine_secure_2026_salt" 
    return hashlib.sha256((password + salt).encode()).hexdigest()

def encrypt_val(val: str) -> str:
    if not val: return ""
    return cipher.encrypt(val.encode()).decode()

def decrypt_val(val: str) -> str:
    if not val: return ""
    try:
        return cipher.decrypt(val.encode()).decode()
    except:
        return val 

# ==========================================
# 2. МЕНЕДЖЕР ПРОЦЕССОВ (PM2-style internal)
# ==========================================
class BotManager:
    def __init__(self):
        self.procs: Dict[str, asyncio.subprocess.Process] = {}
        self.log_paths: Dict[str, str] = {}
        self.bots_dir = os.path.join(BASE_DIR, "active_bots")
        os.makedirs(self.bots_dir, exist_ok=True)

    async def start_bot(self, bid: str, config: dict):
        await self.stop_bot(bid)
        
        cfg_path = os.path.join(self.bots_dir, f"cfg_{bid}.json")
        log_path = os.path.join(self.bots_dir, f"bot_{bid}.log")
        
        # Расшифровываем токен для воркера
        raw_token = decrypt_val(config.get('token', ''))
        config['token'] = raw_token
        
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        
        self.log_paths[bid] = log_path
        
        try:
            # Передаем переменные окружения и запускаем bot_core.py из той же папки
            env = os.environ.copy()
            env.update({"SUPABASE_URL": S_URL, "SUPABASE_KEY": S_KEY})
            
            l_out = open(log_path, "a", encoding="utf-8")
            
            # Используем sys.executable для гарантии того же Python интерпретатора
            bot_script = os.path.join(BASE_DIR, "bot_core.py")
            
            p = await asyncio.create_subprocess_exec(
                sys.executable, bot_script, cfg_path,
                stdout=l_out, stderr=l_out, env=env,
                cwd=BASE_DIR # Важно: рабочая папка процесса
            )
            self.procs[bid] = p
            logger.info(f"🚀 Бот {bid} запущен (PID: {p.pid})")
            return True
        except Exception as e:
            logger.error(f"❌ Критическая ошибка запуска {bid}: {e}")
            return str(e)

    async def stop_bot(self, bid: str):
        p = self.procs.get(bid)
        if p:
            try:
                p.terminate()
                await asyncio.wait_for(p.wait(), timeout=3.0)
            except:
                try: p.kill()
                except: pass
            finally:
                if bid in self.procs: del self.procs[bid]
        return True

    def get_logs(self, bid: str):
        path = self.log_paths.get(bid)
        if not path or not os.path.exists(path): return "Логи отсутствуют."
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                return "".join(lines[-100:])
        except: return "Ошибка чтения логов."

pm = BotManager()

# ==========================================
# 3. FASTAPI И LIFESPAN
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("--- SERVER STARTING ---")
    # Автозапуск ботов при рестарте сервера
    async with httpx.AsyncClient(base_url=f"{S_URL}/rest/v1/", 
                                 headers={"apikey": S_KEY, "Authorization": f"Bearer {S_KEY}"}) as client:
        try:
            r = await client.get("bots", params={"status": "eq.RUNNING"})
            if r.status_code == 200:
                for b in r.json():
                    cfg = {**(b.get("config") or {}), **b}
                    await pm.start_bot(b['id'], cfg)
        except Exception as e:
            logger.error(f"Auto-start error: {e}")
    
    yield
    
    logger.info("--- SERVER STOPPING ---")
    for bid in list(pm.procs.keys()):
        await pm.stop_bot(bid)

app = FastAPI(lifespan=lifespan)

# Раздача статики (фотографий)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# === MIDDLEWARE ===
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Разрешаем загрузку картинок
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data: blob:;"
        return response

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Клиент БД
db = httpx.AsyncClient(
    base_url=f"{S_URL}/rest/v1/", 
    headers={"apikey": S_KEY, "Authorization": f"Bearer {S_KEY}", "Content-Type": "application/json"}
)

# ==========================================
# 4. ЗАГРУЗКА ФАЙЛОВ (ЖЕЛЕЗОБЕТОННАЯ)
# ==========================================
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        ext = file.filename.split('.')[-1] if '.' in file.filename else "jpg"
        filename = f"{uuid.uuid4()}.{ext}"
        # Абсолютный путь для сохранения
        file_path = os.path.join(UPLOAD_DIR, filename)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Возвращаем путь, понятный и вебу (/uploads/...), и боту
        return {"url": f"/uploads/{filename}"}
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(500, "Ошибка сохранения файла")

# ==========================================
# 5. АВТОРИЗАЦИЯ
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
    await db.post("temp_codes", json={"email": email, "code": code, "type": "VERIFY"})
    EmailService.send_verification_code(email, code)
    return True

@app.post("/api/auth/verify-and-register")
async def verify_reg(d: dict):
    email = d['email'].lower()
    r = await db.get("temp_codes", params={"email": f"eq.{email}", "code": f"eq.{d['code']}"})
    if not r.json(): raise HTTPException(400, "Неверный код")
    
    uid = f"u_{secrets.token_hex(4)}"
    user_data = {
        "id": uid, "username": d['username'], "email": email,
        "password": hash_pwd(d['password']), "balance": 0,
        "license_expires_at": int(time.time()*1000) + 259200000,
        "marketing_consent": d.get('marketing_consent', False) 
    }
    await db.post("users", json=user_data)
    await db.delete("temp_codes", params={"email": f"eq.{email}"})
    return user_data

# ==========================================
# 6. УПРАВЛЕНИЕ БОТАМИ
# ==========================================
@app.get("/api/bots/{uid}")
async def get_user_bots(uid: str):
    r = await db.get("bots", params={"owner_id": f"eq.{uid}"})
    return [{**b, **(b.get("config") or {})} for b in r.json()]

@app.post("/api/bots/save")
async def save_bot(b: dict):
    bid = b['id']
    raw_token = b.get('token', '')
    final_token = encrypt_val(raw_token) if not raw_token.startswith('gAAAA') else raw_token
    
    old_r = await db.get("bots", params={"id": f"eq.{bid}"})
    curr = old_r.json()[0] if old_r.json() else {}
    
    sys_keys = ['id', 'owner_id', 'name', 'token', 'status', 'license_expires_at', 'config']
    ui_cfg = {k: v for k, v in b.items() if k not in sys_keys}
    
    payload = {
        "id": bid, "owner_id": b['owner_id'], "name": b["name"],
        "token": final_token, "status": b.get("status", curr.get("status", "IDLE")),
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
    res = await pm.start_bot(bid, data)
    if res is True:
        await db.patch("bots", params={"id": f"eq.{bid}"}, json={"status": "RUNNING"})
        return True
    raise HTTPException(500, f"Ошибка запуска: {res}")

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

@app.get("/api/bots/messages/{bid}")
async def get_bot_messages(bid: str):
    r = await db.get("bot_messages", params={"bot_id": f"eq.{bid}", "order": "timestamp.desc", "limit": 50})
    return r.json()

# ==========================================
# 7. РАССЫЛКА С ФОТО (BROADCAST)
# ==========================================
@app.post("/api/bots/broadcast")
async def broadcast_msg(d: dict):
    bot_ids = d.get('botIds', [])
    text = d.get('message', '')
    photo_url = d.get('photo_url') 

    if not text: return {"error": "Пустое сообщение"}

    results = {"success": 0, "failed": 0}
    
    for bid in bot_ids:
        r = await db.get("bots", params={"id": f"eq.{bid}"})
        if not r.json(): continue
        
        b_data = r.json()[0]
        token = decrypt_val(b_data['token'])
        users = (b_data.get('config') or {}).get('connectedUsers', [])
        
        async with Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML)) as bot:
            for u in users:
                try:
                    user_id = u['id'] if isinstance(u, dict) else u
                    
                    sent = False
                    if photo_url:
                        # Конвертируем /uploads/x.jpg -> /var/www/.../uploads/x.jpg
                        local_path = os.path.join(BASE_DIR, photo_url.lstrip('/'))
                        if os.path.exists(local_path):
                            await bot.send_photo(user_id, photo=FSInputFile(local_path), caption=text)
                            sent = True
                    
                    if not sent:
                        await bot.send_message(user_id, text)
                        
                    results["success"] += 1
                except Exception as e:
                    logger.warning(f"Broadcast error for {u}: {e}")
                    results["failed"] += 1
                await asyncio.sleep(0.05)
                
    return results

@app.get("/api/ping")
async def ping_pong():
    return {"status": "online", "time": time.time()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
