
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
            # Убеждаемся, что зависимости установлены
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
            del self.processes[bot_id]
            logger.info(f"🛑 Бот {bot_id} остановлен")
            return True
        return False

pm = BotProcessManager()

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

    async def request(self, method: str, table: str, json_data: dict = None, filters: str = "", extra_headers: dict = None):
        url = f"{self.url}/rest/v1/{table}{filters}"
        headers = {**self.headers, **(extra_headers or {})}
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.request(method, url, headers=headers, json=json_data)
                logger.info(f"📡 Supabase {method} {table} | Status: {resp.status_code}")
                if resp.status_code >= 400:
                    logger.error(f"🔴 Supabase Error: {resp.text}")
                    return None
                return resp.json()
            except Exception as e:
                logger.error(f"🔴 Ошибка сети: {str(e)}")
                return None

db = SupabaseDB()
pending_verifications = {}

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- AUTH ROUTES ---

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
        "id": user_id,
        "username": username,
        "email": email,
        "password": password,
        "balance": 0,
        "license_expires_at": int((time.time() + 259200) * 1000),
        "created_at": int(time.time() * 1000)
    }
    
    res = await db.request("POST", "users", json_data=payload)
    if not res: raise HTTPException(500, "Ошибка БД")
    
    user_data = res[0]
    user_data["licenseExpiresAt"] = user_data.pop("license_expires_at")
    return user_data

@app.post("/api/auth/login")
async def login(data: dict):
    email = data.get("email", "").lower().strip()
    password = data.get("password")
    res = await db.request("GET", "users", filters=f"?email=eq.{email}&password=eq.{password}")
    if not res: raise HTTPException(401, "Неверные данные")
    user = res[0]
    user["licenseExpiresAt"] = user.pop("license_expires_at", 0)
    return user

# --- BOTS ROUTES ---

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    if user_id in ["new", "undefined"]: return []
    res = await db.request("GET", "bots", filters=f"?owner_id=eq.{user_id}")
    if not res: return []
    
    output = []
    for b in res:
        config = b.get("config", {})
        output.append({
            "id": b["id"], "ownerId": b["owner_id"], "name": b["name"],
            "token": b["token"], "status": b["status"],
            "licenseExpiresAt": b["license_expires_at"],
            "createdAt": b["created_at"], "stats": b.get("stats", {}),
            **config
        })
    return output

@app.post("/api/bots/save")
async def save_bot(bot: dict):
    config_keys = ["description", "adminChatId", "welcomeMessage", "triggers", "buttons", "settings"]
    config = {k: bot.get(k) for k in config_keys if k in bot}
    
    payload = {
        "id": bot["id"], "owner_id": bot["ownerId"], "name": bot["name"],
        "token": bot["token"], "status": bot.get("status", "IDLE"),
        "license_expires_at": int(bot.get("licenseExpiresAt", 0)),
        "created_at": int(bot.get("createdAt", 0)),
        "stats": bot.get("stats", {}), "config": config
    }
    
    headers = {"Prefer": "resolution=merge-duplicates, return=representation"}
    res = await db.request("POST", "bots", json_data=payload, extra_headers=headers)
    if not res: raise HTTPException(500, "Save failed")
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

# --- LICENSE / ADMIN ROUTES ---

@app.post("/api/license/activate")
async def activate_license(req: dict):
    bot_id = req.get("botId")
    key_str = req.get("key", "").strip()
    
    keys = await db.request("GET", "issued_keys", filters=f"?key=eq.{key_str}&used=eq.false")
    if not keys: raise HTTPException(400, "Ключ не найден или использован")
    
    key_data = keys[0]
    bots = await db.request("GET", "bots", filters=f"?id=eq.{bot_id}")
    if not bots: raise HTTPException(404, "Бот не найден")
    
    new_expiry = max(int(time.time()*1000), bots[0]["license_expires_at"]) + (key_data["months"] * 30 * 86400 * 1000)
    
    await db.request("PATCH", "bots", filters=f"?id=eq.{bot_id}", json_data={"license_expires_at": new_expiry})
    await db.request("PATCH", "issued_keys", filters=f"?key=eq.{key_str}", json_data={"used": True})
    
    return {"status": "ok", "newExpiry": new_expiry}

@app.post("/api/admin/generate-key")
async def admin_generate_key(req: dict, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET: raise HTTPException(403, "Forbidden")
    
    new_key = f"BE-{random.randint(100,999)}-{random.randint(1000,9999)}-{random.randint(1000,9999)}"
    payload = {
        "key": new_key,
        "months": req.get("months", 1),
        "used": False,
        "created_at": int(time.time() * 1000)
    }
    await db.request("POST", "issued_keys", json_data=payload)
    return {"key": new_key}

@app.get("/api/ping")
async def ping(): return {"status": "online"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
