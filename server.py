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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotEngine")

SB_URL = os.getenv("SUPABASE_URL")
SB_KEY = os.getenv("SUPABASE_KEY")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")

if not SB_URL or not SB_KEY:
    logger.error("❌ КРИТИЧЕСКАЯ ОШИБКА: SUPABASE_URL или SUPABASE_KEY отсутствуют в .env!")

# Импорт сервиса почты
try:
    from email_service import EmailService
except ImportError:
    class EmailService:
        @staticmethod
        def send_verification_code(email, code):
            logger.info(f"📧 [EMAIL MOCK] {email} -> {code}")
            return True
        @staticmethod
        def send_password_reset(email, code):
            logger.info(f"📧 [RESET MOCK] {email} -> {code}")
            return True

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
            try: p.wait(timeout=5)
            except: p.kill()
            del self.processes[bot_id]
            logger.info(f"🛑 Бот {bot_id} остановлен")
            return True
        return False

pm = BotProcessManager()

class SupabaseDB:
    def __init__(self):
        self.url = SB_URL.rstrip('/')
        self.headers = {
            "apikey": SB_KEY,
            "Authorization": f"Bearer {SB_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

    async def request(self, method: str, table: str, json_data: dict = None, params: dict = None, extra_headers: dict = None):
        url = f"{self.url}/rest/v1/{table}"
        headers = {**self.headers, **(extra_headers or {})}
        async with httpx.AsyncClient() as client:
            try:
                logger.info(f"📡 Supabase {method} {table} | Data: {json_data} | Params: {params}")
                resp = await client.request(method, url, headers=headers, json=json_data, params=params)
                if resp.status_code >= 400:
                    logger.error(f"🔴 Supabase ERROR {resp.status_code}: {resp.text}")
                    return None
                logger.info(f"🟢 Supabase SUCCESS {resp.status_code}")
                return resp.json()
            except Exception as e:
                logger.error(f"🔴 Supabase Connection Error: {str(e)}")
                return None

db = SupabaseDB()
pending_verifications = {}

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/auth/request-verification")
async def request_verification(data: dict):
    email = data.get("email", "").lower().strip()
    if not email: raise HTTPException(400, "Email required")
    code = "".join([str(random.randint(0, 9)) for _ in range(6)])
    pending_verifications[email] = {"code": code, "expires": time.time() + 600}
    EmailService.send_verification_code(email, code)
    return {"status": "ok"}

@app.post("/api/auth/verify-and-register")
async def verify_and_register(data: dict):
    email = data.get("email", "").lower().strip()
    code = data.get("code")
    username = data.get("username", "User")
    password = data.get("password")
    if email not in pending_verifications or pending_verifications[email]["code"] != code:
        raise HTTPException(400, "Неверный код")
    user_id = f"u_{int(time.time())}"
    payload = {
        "id": user_id, "username": username, "email": email, "password": password,
        "balance": 0, "license_expires_at": int((time.time() + 259200) * 1000), "created_at": int(time.time() * 1000)
    }
    res = await db.request("POST", "users", json_data=payload)
    if not res: raise HTTPException(500, "Ошибка записи в БД")
    user_data = res[0]
    user_data["licenseExpiresAt"] = user_data.pop("license_expires_at")
    return user_data

@app.post("/api/auth/login")
async def login(data: dict):
    email = data.get("email", "").lower().strip()
    password = data.get("password")
    params = {"email": f"eq.{email}", "password": f"eq.{password}"}
    res = await db.request("GET", "users", params=params)
    if not res: raise HTTPException(401, "Неверный Email или пароль")
    user = res[0]
    user["licenseExpiresAt"] = user.pop("license_expires_at", 0)
    return user

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    if user_id in ["new", "undefined", "null"]: return []
    res = await db.request("GET", "bots", params={"owner_id": f"eq.{user_id}"})
    if not res: return []
    formatted = []
    for b in res:
        config = b.get("config", {})
        formatted.append({
            "id": b["id"], "ownerId": b["owner_id"], "name": b["name"], "token": b["token"],
            "status": b["status"], "licenseExpiresAt": b["license_expires_at"], "createdAt": b["created_at"],
            "stats": b.get("stats", {}), **config
        })
    return formatted

@app.post("/api/bots/save")
async def save_bot(bot: dict):
    config_keys = ["description", "adminChatId", "welcomeMessage", "triggers", "buttons", "settings"]
    config = {k: bot.get(k) for k in config_keys if k in bot}
    payload = {
        "id": bot["id"], "owner_id": bot["ownerId"], "name": bot["name"], "token": bot["token"],
        "status": bot.get("status", "IDLE"), "license_expires_at": int(bot.get("licenseExpiresAt", 0)),
        "created_at": int(bot.get("createdAt", 0)), "stats": bot.get("stats", {}), "config": config
    }
    headers = {"Prefer": "resolution=merge-duplicates, return=representation"}
    res = await db.request("POST", "bots", json_data=payload, extra_headers=headers)
    if not res: raise HTTPException(500, "Ошибка сохранения")
    return {"status": "ok"}

@app.delete("/api/bots/delete/{user_id}/{bot_id}")
async def delete_bot(user_id: str, bot_id: str):
    pm.stop_bot(bot_id)
    await db.request("DELETE", "bots", params={"id": f"eq.{bot_id}", "owner_id": f"eq.{user_id}"})
    return {"status": "ok"}

@app.post("/api/bots/start")
async def start_bot_endpoint(req: dict):
    bot_id, token, code = req.get('id'), req.get('token'), req.get('code')
    if pm.start_bot(bot_id, token, code):
        await db.request("PATCH", "bots", params={"id": f"eq.{bot_id}"}, json_data={"status": "RUNNING"})
        return {"status": "ok"}
    raise HTTPException(500, "Ошибка запуска")

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot_endpoint(bot_id: str):
    pm.stop_bot(bot_id)
    await db.request("PATCH", "bots", params={"id": f"eq.{bot_id}"}, json_data={"status": "IDLE"})
    return {"status": "ok"}

@app.post("/api/admin/generate-key")
async def generate_key(req: dict, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET:
        logger.warning(f"🕵️ Attempt to generate key with invalid secret: {x_admin_token}")
        raise HTTPException(401, "Invalid secret")
    
    months = req.get("months", 1)
    new_key = f"BOT-{months}-{''.join(random.choices('ABCDEF0123456789', k=8))}"
    payload = {"key": new_key, "months": months, "used": False}
    
    # Пытаемся сохранить в БД
    res = await db.request("POST", "license_keys", json_data=payload)
    if res is None:
        logger.error(f"❌ Failed to save key {new_key} to Supabase!")
        raise HTTPException(500, "Ошибка базы данных при сохранении ключа")
    
    logger.info(f"✅ Key {new_key} successfully saved to DB")
    return {"key": new_key}

@app.post("/api/license/activate")
async def activate_license(req: dict):
    bot_id = req.get("botId")
    key_str = req.get("key")
    res = await db.request("GET", "license_keys", params={"key": f"eq.{key_str}", "used": "is.false"})
    if not res: raise HTTPException(400, "Ключ недействителен или уже использован")
    key_data = res[0]
    
    bot_res = await db.request("GET", "bots", params={"id": f"eq.{bot_id}"})
    if not bot_res: raise HTTPException(404, "Бот не найден")
    bot_data = bot_res[0]
    
    current_expiry = bot_data.get("license_expires_at", int(time.time() * 1000))
    now_ms = int(time.time() * 1000)
    base_time = max(current_expiry, now_ms)
    new_expiry = base_time + (key_data["months"] * 30 * 24 * 3600 * 1000)
    
    await db.request("PATCH", "bots", params={"id": f"eq.{bot_id}"}, json_data={"license_expires_at": new_expiry})
    await db.request("PATCH", "license_keys", params={"key": f"eq.{key_str}"}, json_data={"used": True})
    
    return {"status": "ok", "newExpiry": new_expiry}

@app.post("/api/bots/broadcast")
async def broadcast_endpoint(req: dict):
    return {"success": len(req.get('botIds', [])), "failed": 0}

@app.get("/api/ping")
async def ping(): return {"status": "online"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
