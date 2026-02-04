
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

# Импорт сервиса почты (файл email_service.py должен быть в той же папке)
try:
    from email_service import EmailService
except ImportError:
    class EmailService:
        @staticmethod
        def send_verification_code(email, code):
            print(f"!!! ЭМУЛЯЦИЯ ПОЧТЫ: Код {code} для {email} !!!")
            return True

# Настройка логов
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotEngine")

# --- ХРАНИЛИЩЕ ДАННЫХ (Простая замена БД на JSON) ---
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

# Глобальные переменные данных
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
    
    logger.info(f"📧 Генерируем код {code} для {email}")
    success = EmailService.send_verification_code(email, code)
    
    if not success:
        # Если почта не настроена, код все равно будет работать (для тестов)
        logger.warning("⚠️ Не удалось отправить письмо. Проверьте настройки SMTP.")
        return {"status": "ok", "debug": "Mail skip"}
        
    return {"status": "ok"}

@app.post("/api/auth/verify-and-register")
async def verify_and_register(data: dict):
    email = data.get("email", "").lower()
    code = data.get("code")
    username = data.get("username", "User")
    password = data.get("password")

    if email not in pending_verifications or pending_verifications[email]["code"] != code:
        raise HTTPException(400, "Неверный код подтверждения")

    # Создаем пользователя
    user_id = f"u_{int(time.time())}"
    user_data = {
        "id": user_id,
        "username": username,
        "email": email,
        "password": password, # В реальном проекте хешируйте пароли!
        "balance": 0,
        "botsCreated": 0,
        "licenseExpiresAt": int((time.time() + 259200) * 1000) # 3 дня триала
    }
    
    users[email] = user_data
    save_data(USERS_FILE, users)
    del pending_verifications[email]
    
    logger.info(f"👤 Новый пользователь зарегистрирован: {email}")
    return user_data

@app.post("/api/auth/login")
async def login(data: dict):
    email = data.get("email", "").lower()
    password = data.get("password")
    
    user = users.get(email)
    if not user or user["password"] != password:
        raise HTTPException(401, "Неверный Email или пароль")
        
    return user

# --- BOTS ROUTES ---

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    user_bots = [b for b in bots_db.values() if b["ownerId"] == user_id]
    return user_bots

@app.post("/api/bots/save")
async def save_bot(bot: dict):
    bots_db[bot["id"]] = bot
    save_data(BOTS_FILE, bots_db)
    logger.info(f"💾 Бот сохранен: {bot['name']}")
    return {"status": "ok"}

@app.post("/api/bots/start")
async def start_bot_endpoint(req: dict):
    bot_id = req['id']
    if pm.start_bot(bot_id, req['token'], req['code']):
        if bot_id in bots_db:
            bots_db[bot_id]["status"] = "RUNNING"
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

# --- LICENSE SYSTEM ---

@app.post("/api/admin/generate-key")
async def gen_key(data: dict, x_admin_token: str = Header(None)):
    if x_admin_token != "MRAKOTIK": raise HTTPException(403)
    
    months = data.get("months", 1)
    new_key = f"BOT-{months}-" + "".join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=8))
    
    valid_keys[new_key] = {"months": months, "created_at": time.time()}
    save_data(KEYS_FILE, valid_keys)
    
    logger.info(f"🔑 Создан ключ на {months} мес: {new_key}")
    return {"key": new_key}

@app.post("/api/license/activate")
async def activate_license(req: dict):
    bot_id = req.get("botId")
    key = req.get("key", "").strip()
    
    if key not in valid_keys:
        raise HTTPException(400, "Ключ недействителен или уже использован")
    
    if bot_id not in bots_db:
        raise HTTPException(404, "Бот не найден")
        
    months = valid_keys[key]["months"]
    # Продлеваем лицензию
    current_expiry = bots_db[bot_id].get("licenseExpiresAt", int(time.time() * 1000))
    ms_to_add = months * 30 * 24 * 3600 * 1000
    new_expiry = current_expiry + ms_to_add
    
    bots_db[bot_id]["licenseExpiresAt"] = new_expiry
    save_data(BOTS_FILE, bots_db)
    
    # Удаляем использованный ключ
    del valid_keys[key]
    save_data(KEYS_FILE, valid_keys)
    
    logger.info(f"✅ Лицензия бота {bot_id} продлена на {months} мес.")
    return {"status": "ok", "newExpiry": new_expiry}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
