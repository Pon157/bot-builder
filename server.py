
import asyncio
import logging
import os
import subprocess
import sys
import time
import json
import random
from typing import Dict, List
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# --- ЗАГРУЗКА ОКРУЖЕНИЯ ---
def load_env_to_os():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    # Убираем кавычки и пробелы
                    os.environ[key.strip()] = value.strip().strip('"').strip("'")
        return True
    return False

load_env_to_os()

# Импорт сервиса почты
try:
    from email_service import EmailService
except ImportError:
    class EmailService:
        @staticmethod
        def send_verification_code(email, code):
            print(f"!!! ЭМУЛЯЦИЯ ПОЧТЫ: Код {code} для {email} !!!")
            return True
        @staticmethod
        def send_password_reset(email, code):
            print(f"!!! ЭМУЛЯЦИЯ СБРОСА: Код {code} для {email} !!!")
            return True

# Настройка логов
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotEngine")

# --- ХРАНИЛИЩЕ ДАННЫХ ---
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
USERS_FILE = os.path.join(DATA_DIR, "users.json")
BOTS_FILE = os.path.join(DATA_DIR, "bots.json")
KEYS_FILE = os.path.join(DATA_DIR, "valid_keys.json")

def load_data(file, default):
    if os.path.exists(file):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return default
    return default

def save_data(file, data):
    with open(file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

users = load_data(USERS_FILE, {})
bots_db = load_data(BOTS_FILE, {})
valid_keys = load_data(KEYS_FILE, {})
pending_verifications = {} # {email: {"code": "123456", "expires": timestamp}}

class BotProcessManager:
    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}

    def start_bot(self, bot_id: str, bot_token: str, code: str):
        self.stop_bot(bot_id)
        os.makedirs("active_bots", exist_ok=True)
        filename = f"active_bots/bot_{bot_id}.py"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(code)
        try:
            process = subprocess.Popen([sys.executable, filename])
            self.processes[bot_id] = process
            logger.info(f"🚀 Бот {bot_id} запущен (PID: {process.pid})")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка запуска бота {bot_id}: {e}")
            return False

    def stop_bot(self, bot_id: str):
        if bot_id in self.processes:
            p = self.processes[bot_id]
            p.terminate()
            if bot_id in self.processes: del self.processes[bot_id]
            logger.info(f"🛑 Бот {bot_id} остановлен")
            return True
        return False

pm = BotProcessManager()
app = FastAPI(title="BotEngine API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"📥 {request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"📤 Status: {response.status_code}")
    return response

# --- AUTH ROUTES ---

@app.post("/api/auth/request-verification")
async def request_verification(data: dict):
    email = data.get("email", "").lower()
    if not email: raise HTTPException(400, "Email required")
    
    code = "".join([str(random.randint(0, 9)) for _ in range(6)])
    pending_verifications[email] = {"code": code, "expires": time.time() + 600}
    
    logger.info(f"📧 Регистрация: {email}, код {code}")
    EmailService.send_verification_code(email, code)
    return {"status": "ok"}

@app.post("/api/auth/verify-and-register")
async def verify_and_register(data: dict):
    email = data.get("email", "").lower()
    code = data.get("code")
    username = data.get("username", "User")
    password = data.get("password")

    if email not in pending_verifications or pending_verifications[email]["code"] != code:
        raise HTTPException(400, "Неверный код подтверждения")

    user_id = f"u_{int(time.time())}"
    user_data = {
        "id": user_id,
        "username": username,
        "email": email,
        "password": password,
        "balance": 0,
        "botsCreated": 0,
        "licenseExpiresAt": int((time.time() + 259200) * 1000)
    }
    
    users[email] = user_data
    save_data(USERS_FILE, users)
    del pending_verifications[email]
    
    logger.info(f"👤 Регистрация завершена: {email}")
    return user_data

@app.post("/api/auth/login")
async def login(data: dict):
    email = data.get("email", "").lower()
    password = data.get("password")
    user = users.get(email)
    if not user or user["password"] != password:
        raise HTTPException(401, "Неверный Email или пароль")
    return user

@app.post("/api/auth/forgot-password")
async def forgot_password(data: dict):
    email = data.get("email", "").lower()
    if email not in users:
        raise HTTPException(404, "Пользователь с таким Email не найден")
    
    code = "".join([str(random.randint(0, 9)) for _ in range(6)])
    pending_verifications[email] = {"code": code, "expires": time.time() + 600}
    
    logger.info(f"🔑 Сброс пароля: {email}, код {code}")
    EmailService.send_password_reset(email, code)
    return {"status": "ok"}

@app.post("/api/auth/reset-password")
async def reset_password(data: dict):
    email = data.get("email", "").lower()
    code = data.get("code")
    new_password = data.get("newPassword")

    if email not in pending_verifications or pending_verifications[email]["code"] != code:
        raise HTTPException(400, "Неверный или истекший код")

    if email in users:
        users[email]["password"] = new_password
        save_data(USERS_FILE, users)
        del pending_verifications[email]
        logger.info(f"✅ Пароль успешно изменен для {email}")
        return {"status": "ok"}
    
    raise HTTPException(404, "Пользователь не найден")

# --- BOTS & LICENSE (остальное без изменений) ---
@app.get("/api/ping")
async def ping(): return {"status": "online"}

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    return [b for b in bots_db.values() if b["ownerId"] == user_id]

@app.post("/api/bots/save")
async def save_bot_route(bot: dict):
    bots_db[bot["id"]] = bot
    save_data(BOTS_FILE, bots_db)
    return {"status": "ok"}

@app.post("/api/bots/start")
async def start_bot_endpoint(req: dict):
    if pm.start_bot(req['id'], req['token'], req['code']):
        if req['id'] in bots_db:
            bots_db[req['id']]["status"] = "RUNNING"
            save_data(BOTS_FILE, bots_db)
        return {"status": "ok"}
    raise HTTPException(500, "Start failed")

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot_endpoint(bot_id: str):
    pm.stop_bot(bot_id)
    if bot_id in bots_db:
        bots_db[bot_id]["status"] = "IDLE"
        save_data(BOTS_FILE, bots_db)
    return {"status": "ok"}

@app.post("/api/admin/generate-key")
async def gen_key(data: dict, x_admin_token: str = Header(None)):
    if x_admin_token != os.getenv("ADMIN_SECRET", "MRAKOTIK"): raise HTTPException(403)
    months = data.get("months", 1)
    new_key = f"BOT-{months}-" + "".join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=8))
    valid_keys[new_key] = {"months": months, "created_at": time.time()}
    save_data(KEYS_FILE, valid_keys)
    return {"key": new_key}

@app.post("/api/license/activate")
async def activate_license(req: dict):
    bot_id, key = req.get("botId"), req.get("key", "").strip()
    if key not in valid_keys or bot_id not in bots_db: raise HTTPException(400, "Invalid key or bot")
    months = valid_keys[key]["months"]
    bots_db[bot_id]["licenseExpiresAt"] = bots_db[bot_id].get("licenseExpiresAt", int(time.time()*1000)) + (months * 30 * 24 * 3600 * 1000)
    save_data(BOTS_FILE, bots_db)
    del valid_keys[key]
    save_data(KEYS_FILE, valid_keys)
    return {"status": "ok", "newExpiry": bots_db[bot_id]["licenseExpiresAt"]}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
