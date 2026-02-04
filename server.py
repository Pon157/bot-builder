
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
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip().strip('"').strip("'")
        return True
    return False

load_env_to_os()

# Настройка логов
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotEngine")

SB_URL = os.getenv("SUPABASE_URL")
SB_KEY = os.getenv("SUPABASE_KEY")

if not SB_URL or not SB_KEY:
    logger.error("❌ SUPABASE_URL или SUPABASE_KEY не найдены в .env!")

# Импорт сервиса почты
try:
    from email_service import EmailService
except ImportError:
    class EmailService:
        @staticmethod
        def send_verification_code(email, code):
            logger.info(f"!!! ЭМУЛЯЦИЯ ПОЧТЫ: {email} -> {code} !!!")
            return True
        @staticmethod
        def send_password_reset(email, code):
            logger.info(f"!!! ЭМУЛЯЦИЯ СБРОСА: {email} -> {code} !!!")
            return True

# --- SUPABASE CLIENT ---
class SupabaseDB:
    def __init__(self):
        self.url = SB_URL.rstrip('/')
        self.headers = {
            "apikey": SB_KEY,
            "Authorization": f"Bearer {SB_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

    async def request(self, method: str, table: str, params: dict = None, json_data: dict = None, filters: str = ""):
        # Убираем лишние слеши
        url = f"{self.url}/rest/v1/{table}{filters}"
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.request(method, url, headers=self.headers, params=params, json=json_data)
                if resp.status_code >= 400:
                    logger.error(f"🔴 Supabase Error [{method} {table}]: {resp.status_code} - {resp.text}")
                    return None
                return resp.json()
            except Exception as e:
                logger.error(f"🔴 Network error connecting to Supabase: {str(e)}")
                return None

db = SupabaseDB()
pending_verifications = {}

# --- BOT PROCESS MANAGER ---
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
    email = data.get("email", "").lower().strip()
    if not email: raise HTTPException(400, "Email required")
    
    code = "".join([str(random.randint(0, 9)) for _ in range(6)])
    pending_verifications[email] = {"code": code, "expires": time.time() + 600}
    
    logger.info(f"📧 Регистрация: {email}, код {code}")
    EmailService.send_verification_code(email, code)
    return {"status": "ok"}

@app.post("/api/auth/verify-and-register")
async def verify_and_register(data: dict):
    email = data.get("email", "").lower().strip()
    code = data.get("code")
    username = data.get("username", "User")
    password = data.get("password")

    if email not in pending_verifications or pending_verifications[email]["code"] != code:
        raise HTTPException(400, "Неверный код подтверждения")

    # Генерируем уникальный ID
    user_id = f"u_{int(time.time())}_{random.randint(1000, 9999)}"
    
    # Пейлоад строго по твоей SQL схеме
    user_payload = {
        "id": user_id,
        "username": username,
        "email": email,
        "password": password,
        "balance": 0,
        "license_expires_at": int((time.time() + 259200) * 1000), # 3 дня триала
        "created_at": int(time.time() * 1000)
    }
    
    logger.info(f"📡 Отправка данных регистрации в Supabase для {email}...")
    res = await db.request("POST", "users", json_data=user_payload)
    
    if res is None:
        raise HTTPException(500, "Ошибка при записи в базу данных Supabase. Проверьте логи сервера.")
    
    del pending_verifications[email]
    
    # Для фронтенда переименовываем обратно
    user_payload["licenseExpiresAt"] = user_payload.pop("license_expires_at")
    return user_payload

@app.post("/api/auth/login")
async def login(data: dict):
    email = data.get("email", "").lower().strip()
    password = data.get("password")
    
    # Поиск пользователя
    res = await db.request("GET", "users", filters=f"?email=eq.{email}&password=eq.{password}")
    
    if not res or len(res) == 0:
        logger.warning(f"🕵️ Неудачная попытка входа: {email}")
        raise HTTPException(401, "Неверный Email или пароль")
    
    user = res[0]
    # Приводим к формату фронтенда
    user["licenseExpiresAt"] = user.pop("license_expires_at", 0)
    logger.info(f"✅ Успешный вход: {email}")
    return user

@app.post("/api/auth/forgot-password")
async def forgot_password(data: dict):
    email = data.get("email", "").lower().strip()
    # Проверяем наличие юзера
    res = await db.request("GET", "users", filters=f"?email=eq.{email}")
    if not res:
        raise HTTPException(404, "Пользователь не найден")
        
    code = "".join([str(random.randint(0, 9)) for _ in range(6)])
    pending_verifications[email] = {"code": code, "expires": time.time() + 600}
    
    EmailService.send_password_reset(email, code)
    return {"status": "ok"}

@app.post("/api/auth/reset-password")
async def reset_password(data: dict):
    email = data.get("email", "").lower().strip()
    code = data.get("code")
    new_password = data.get("newPassword")

    if email not in pending_verifications or pending_verifications[email]["code"] != code:
        raise HTTPException(400, "Неверный код")

    res = await db.request("PATCH", "users", filters=f"?email=eq.{email}", json_data={"password": new_password})
    if res is None:
        raise HTTPException(500, "Не удалось обновить пароль")
        
    del pending_verifications[email]
    return {"status": "ok"}

# --- BOTS ROUTES ---

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    res = await db.request("GET", "bots", filters=f"?owner_id=eq.{user_id}")
    if res is None: return []
    
    formatted_bots = []
    for b in res:
        # Разворачиваем JSONB поле 'config'
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
        formatted_bots.append(bot)
    return formatted_bots

@app.post("/api/bots/save")
async def save_bot(bot: dict):
    # Маппинг данных из фронтенда в SQL схему
    bot_id = bot.get("id")
    owner_id = bot.get("ownerId")
    name = bot.get("name")
    token = bot.get("token")
    status = bot.get("status", "IDLE")
    license_expires = int(bot.get("licenseExpiresAt", 0))
    created_at = int(bot.get("createdAt", time.time() * 1000))
    stats = bot.get("stats", {})

    # Поля, которые мы храним в JSONB колонке 'config'
    config_keys = ["description", "adminChatId", "welcomeMessage", "triggers", "buttons", "settings"]
    config = {k: bot.get(k) for k in config_keys if k in bot}

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
    
    # Используем UPSERT (Prefer: resolution=merge-duplicates)
    headers = {**db.headers, "Prefer": "resolution=merge-duplicates"}
    async with httpx.AsyncClient() as client:
        url = f"{db.url}/rest/v1/bots"
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            logger.error(f"❌ Ошибка сохранения бота: {resp.text}")
            raise HTTPException(500, "Ошибка сохранения в БД")
            
    return {"status": "ok"}

@app.post("/api/bots/start")
async def start_bot_endpoint(req: dict):
    if pm.start_bot(req['id'], req['token'], req['code']):
        await db.request("PATCH", "bots", filters=f"?id=eq.{req['id']}", json_data={"status": "RUNNING"})
        return {"status": "ok"}
    raise HTTPException(500, "Start failed")

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot_endpoint(bot_id: str):
    pm.stop_bot(bot_id)
    await db.request("PATCH", "bots", filters=f"?id=eq.{bot_id}", json_data={"status": "IDLE"})
    return {"status": "ok"}

@app.delete("/api/bots/delete/{user_id}/{bot_id}")
async def delete_bot_endpoint(user_id: str, bot_id: str):
    pm.stop_bot(bot_id)
    res = await db.request("DELETE", "bots", filters=f"?id=eq.{bot_id}&owner_id=eq.{user_id}")
    if res is None: raise HTTPException(500, "Delete failed")
    return {"status": "ok"}

# --- LICENSE SYSTEM ---

@app.post("/api/license/activate")
async def activate_license(req: dict):
    bot_id = req.get("botId")
    key_str = req.get("key", "").strip()
    
    # Ищем свободный ключ
    keys = await db.request("GET", "issued_keys", filters=f"?key=eq.{key_str}&used=eq.false")
    if not keys: raise HTTPException(400, "Ключ недействителен или уже использован")
    
    key_data = keys[0]
    
    # Ищем бота
    bots = await db.request("GET", "bots", filters=f"?id=eq.{bot_id}")
    if not bots: raise HTTPException(404, "Бот не найден")
    bot_data = bots[0]
    
    # Считаем новую дату (bigint)
    months = key_data["months"]
    now_ms = int(time.time() * 1000)
    current_expiry = max(now_ms, bot_data["license_expires_at"])
    new_expiry = current_expiry + (months * 30 * 24 * 3600 * 1000)
    
    # Обновляем
    await db.request("PATCH", "bots", filters=f"?id=eq.{bot_id}", json_data={"license_expires_at": new_expiry})
    await db.request("PATCH", "issued_keys", filters=f"?key=eq.{key_str}", json_data={"used": True})
    
    return {"status": "ok", "newExpiry": new_expiry}

@app.get("/api/ping")
async def ping(): return {"status": "online"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
