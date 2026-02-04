
import asyncio
import logging
import os
import subprocess
import sys
import time
import json
import random
import httpx
from typing import Dict, List, Optional
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
                    os.environ[key.strip()] = value.strip().strip('"').strip("'")
        return True
    return False

load_env_to_os()

# Данные Supabase
SB_URL = os.getenv("SUPABASE_URL")
SB_KEY = os.getenv("SUPABASE_KEY")

# Импорт сервиса почты
try:
    from email_service import EmailService
except ImportError:
    class EmailService:
        @staticmethod
        def send_verification_code(email, code):
            print(f"!!! EMAIL SIM: {email} -> {code} !!!")
            return True
        @staticmethod
        def send_password_reset(email, code):
            print(f"!!! RESET SIM: {email} -> {code} !!!")
            return True

# Настройка логов
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotEngine")

# --- SUPABASE CLIENT ---
class SupabaseDB:
    def __init__(self):
        self.url = SB_URL
        self.headers = {
            "apikey": SB_KEY,
            "Authorization": f"Bearer {SB_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

    async def request(self, method: str, table: str, params: dict = None, json_data: dict = None, filters: str = ""):
        url = f"{self.url}/rest/v1/{table}{filters}"
        async with httpx.AsyncClient() as client:
            resp = await client.request(method, url, headers=self.headers, params=params, json=json_data)
            if resp.status_code >= 400:
                logger.error(f"Supabase Error ({table}): {resp.text}")
                return None
            return resp.json()

db = SupabaseDB()
pending_verifications = {}

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
app = FastAPI(title="BotEngine Supabase API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- AUTH ROUTES ---

@app.post("/api/auth/request-verification")
async def request_verification(data: dict):
    email = data.get("email", "").lower()
    if not email: raise HTTPException(400, "Email required")
    code = "".join([str(random.randint(0, 9)) for _ in range(6)])
    pending_verifications[email] = {"code": code, "expires": time.time() + 600}
    logger.info(f"📧 Код для {email}: {code}")
    EmailService.send_verification_code(email, code)
    return {"status": "ok"}

@app.post("/api/auth/verify-and-register")
async def verify_and_register(data: dict):
    email = data.get("email", "").lower()
    code, username, password = data.get("code"), data.get("username"), data.get("password")

    if email not in pending_verifications or pending_verifications[email]["code"] != code:
        raise HTTPException(400, "Неверный код")

    user_id = f"u_{int(time.time())}"
    user_payload = {
        "id": user_id,
        "username": username,
        "email": email,
        "password": password,
        "balance": 0,
        "license_expires_at": int((time.time() + 259200) * 1000), # 3 дня
        "created_at": int(time.time() * 1000)
    }
    
    res = await db.request("POST", "users", json_data=user_payload)
    if res is None: raise HTTPException(500, "Ошибка создания пользователя в БД")
    
    del pending_verifications[email]
    # Приводим к формату фронтенда
    user_payload["licenseExpiresAt"] = user_payload.pop("license_expires_at")
    return user_payload

@app.post("/api/auth/login")
async def login(data: dict):
    email, password = data.get("email", "").lower(), data.get("password")
    res = await db.request("GET", "users", filters=f"?email=eq.{email}&password=eq.{password}")
    if not res: raise HTTPException(401, "Неверный логин или пароль")
    
    user = res[0]
    user["licenseExpiresAt"] = user.pop("license_expires_at")
    return user

# --- BOTS ROUTES ---

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    res = await db.request("GET", "bots", filters=f"?owner_id=eq.{user_id}")
    if res is None: return []
    
    # Конвертируем из БД-формата в формат фронтенда
    bots = []
    for b in res:
        config = b.get("config", {})
        bot = {
            "id": b["id"],
            "ownerId": b["owner_id"],
            "name": b["name"],
            "token": b["token"],
            "status": b["status"],
            "licenseExpiresAt": b["license_expires_at"],
            "createdAt": b["created_at"],
            "stats": b.get("stats", {}),
            **config
        }
        bots.append(bot)
    return bots

@app.post("/api/bots/save")
async def save_bot(bot: dict):
    # Извлекаем основные поля для колонок
    bot_id = bot.get("id")
    owner_id = bot.get("ownerId")
    name = bot.get("name")
    token = bot.get("token")
    status = bot.get("status", "IDLE")
    license_expires = bot.get("licenseExpiresAt")
    created_at = bot.get("createdAt", int(time.time() * 1000))
    stats = bot.get("stats", {})

    # Всё остальное упаковываем в config (JSONB)
    config_fields = ["description", "adminChatId", "welcomeMessage", "triggers", "buttons", "settings"]
    config = {k: bot.get(k) for k in config_fields if k in bot}

    payload = {
        "id": bot_id,
        "owner_id": owner_id,
        "name": name,
        "token": token,
        "status": status,
        "license_expires_at": license_expires,
        "created_at": created_at,
        "config": config,
        "stats": stats
    }
    
    # Используем UPSERT (POST с Prefer: resolution=merge-duplicates)
    headers = {**db.headers, "Prefer": "resolution=merge-duplicates"}
    async with httpx.AsyncClient() as client:
        url = f"{db.url}/rest/v1/bots"
        await client.post(url, headers=headers, json=payload)
    
    return {"status": "ok"}

@app.post("/api/bots/start")
async def start_bot_endpoint(req: dict):
    # Мы ожидаем 'code' (сгенерированный питон-код) от фронтенда
    if pm.start_bot(req['id'], req['token'], req['code']):
        await db.request("PATCH", "bots", filters=f"?id=eq.{req['id']}", json_data={"status": "RUNNING"})
        return {"status": "ok"}
    raise HTTPException(500, "Start failed")

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot_endpoint(bot_id: str):
    pm.stop_bot(bot_id)
    await db.request("PATCH", "bots", filters=f"?id=eq.{bot_id}", json_data={"status": "IDLE"})
    return {"status": "ok"}

# --- LICENSE SYSTEM (Supabase) ---

@app.post("/api/admin/generate-key")
async def gen_key(data: dict, x_admin_token: str = Header(None)):
    if x_admin_token != os.getenv("ADMIN_SECRET", "MRAKOTIK"): raise HTTPException(403)
    
    months = data.get("months", 1)
    new_key = f"BOT-{months}-" + "".join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=8))
    
    payload = {
        "key": new_key,
        "months": months,
        "used": False,
        "created_at": int(time.time() * 1000)
    }
    await db.request("POST", "issued_keys", json_data=payload)
    return {"key": new_key}

@app.post("/api/license/activate")
async def activate_license(req: dict):
    bot_id, key_str = req.get("botId"), req.get("key", "").strip()
    
    # 1. Ищем ключ
    keys = await db.request("GET", "issued_keys", filters=f"?key=eq.{key_str}&used=eq.false")
    if not keys: raise HTTPException(400, "Ключ недействителен или уже использован")
    key_data = keys[0]
    
    # 2. Ищем бота
    bots = await db.request("GET", "bots", filters=f"?id=eq.{bot_id}")
    if not bots: raise HTTPException(404, "Бот не найден")
    bot_data = bots[0]
    
    # 3. Продлеваем
    months = key_data["months"]
    current_expiry = bot_data["license_expires_at"]
    if current_expiry < int(time.time() * 1000):
        current_expiry = int(time.time() * 1000)
        
    new_expiry = current_expiry + (months * 30 * 24 * 3600 * 1000)
    
    # 4. Обновляем бота и помечаем ключ как использованный
    await db.request("PATCH", "bots", filters=f"?id=eq.{bot_id}", json_data={"license_expires_at": new_expiry})
    await db.request("PATCH", "issued_keys", filters=f"?key=eq.{key_str}", json_data={"used": True})
    
    return {"status": "ok", "newExpiry": new_expiry}

@app.get("/api/ping")
async def ping(): return {"status": "online"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
