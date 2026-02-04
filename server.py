
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
from fastapi import FastAPI, HTTPException, Request, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# --- Инициализация окружения ---
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")

load_env()

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("BotEngineServer")

SB_URL = os.getenv("SUPABASE_URL")
SB_KEY = os.getenv("SUPABASE_KEY")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")

if not SB_URL or not SB_KEY:
    logger.error("❌ SUPABASE_URL или SUPABASE_KEY не найдены!")

# Импорт сервиса почты (email_service.py)
try:
    from email_service import EmailService
except ImportError:
    class EmailService:
        @staticmethod
        def send_verification_code(e, c): logger.info(f"📧 [MOCK] Email {e} code {c}"); return True
        @staticmethod
        def send_password_reset(e, c): logger.info(f"📧 [MOCK] Reset {e} code {c}"); return True

class BotProcessManager:
    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}

    def start_bot(self, bot_id: str, code: str):
        self.stop_bot(bot_id)
        os.makedirs("active_bots", exist_ok=True)
        filename = f"active_bots/bot_{bot_id}.py"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(code)
        try:
            # Запускаем из корня, чтобы ядро bot_core.py было доступно
            process = subprocess.Popen([sys.executable, filename], env=os.environ.copy(), cwd=os.getcwd())
            self.processes[bot_id] = process
            logger.info(f"🚀 Бот {bot_id} запущен (PID: {process.pid})")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка запуска {bot_id}: {e}")
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
pending_verifications = {}

# Supabase Client
db = httpx.AsyncClient(
    base_url=f"{SB_URL}/rest/v1/",
    headers={"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}", "Content-Type": "application/json"},
    timeout=20
)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- AUTH ---

@app.post("/api/auth/request-verification")
async def req_verify(data: dict):
    email = data.get("email", "").lower().strip()
    code = str(random.randint(100000, 999999))
    pending_verifications[email] = {"code": code, "expires": time.time() + 600}
    EmailService.send_verification_code(email, code)
    return {"status": "ok"}

@app.post("/api/auth/verify-and-register")
async def verify_reg(data: dict):
    email = data.get("email", "").lower().strip()
    if email not in pending_verifications or pending_verifications[email]["code"] != data.get("code"):
        raise HTTPException(400, "Неверный код подтверждения")
    
    user_id = f"u_{int(time.time())}"
    payload = {
        "id": user_id, "username": data.get("username", "User"), 
        "email": email, "password": data.get("password"),
        "license_expires_at": int((time.time() + 259200) * 1000)
    }
    res = await db.post("users", json=payload, headers={"Prefer": "return=representation"})
    if res.status_code >= 400: raise HTTPException(500, f"Ошибка БД: {res.text}")
    return res.json()[0]

@app.post("/api/auth/login")
async def login(data: dict):
    res = await db.get("users", params={"email": f"eq.{data['email']}", "password": f"eq.{data['password']}"})
    if res.status_code != 200 or not res.json(): raise HTTPException(401, "Неверный логин или пароль")
    u = res.json()[0]
    u["licenseExpiresAt"] = u.get("license_expires_at", 0)
    return u

@app.post("/api/auth/forgot-password")
async def forgot_pass(data: dict):
    email = data.get("email", "").lower().strip()
    code = str(random.randint(100000, 999999))
    pending_verifications[email] = {"reset_code": code, "expires": time.time() + 600}
    EmailService.send_password_reset(email, code)
    return {"status": "ok"}

@app.post("/api/auth/reset-password")
async def reset_pass(data: dict):
    email = data.get("email", "").lower().strip()
    if email not in pending_verifications or pending_verifications[email].get("reset_code") != data.get("code"):
        raise HTTPException(400, "Неверный код сброса")
    await db.patch("users", params={"email": f"eq.{email}"}, json={"password": data.get("newPassword")})
    return {"status": "ok"}

# --- BOT CRUD ---

@app.get("/api/bots/{user_id}")
async def get_user_bots(user_id: str):
    res = await db.get("bots", params={"owner_id": f"eq.{user_id}"})
    if res.status_code != 200: return []
    return [{**b, **b.get("config", {})} for b in res.json()]

@app.post("/api/bots/save")
async def save_bot(bot: dict):
    payload = {
        "id": bot["id"], "owner_id": bot["ownerId"], "name": bot["name"], "token": bot["token"],
        "status": bot.get("status", "IDLE"), "license_expires_at": int(bot.get("licenseExpiresAt", 0)),
        "config": {k: bot.get(k) for k in ["description", "adminChatId", "welcomeMessage", "triggers", "buttons", "settings", "connectedUsers"]}
    }
    await db.post("bots", json=payload, headers={"Prefer": "resolution=merge-duplicates"})
    return {"status": "ok"}

@app.delete("/api/bots/delete/{user_id}/{bot_id}")
async def del_bot(user_id: str, bot_id: str):
    pm.stop_bot(bot_id)
    await db.delete("bots", params={"id": f"eq.{bot_id}", "owner_id": f"eq.{user_id}"})
    return {"status": "ok"}

# --- RUNTIME ---

@app.post("/api/bots/start")
async def start_bot_ep(req: dict):
    if pm.start_bot(req['id'], req['code']):
        await db.patch("bots", params={"id": f"eq.{req['id']}"}, json={"status": "RUNNING"})
        return {"status": "ok"}
    raise HTTPException(500, "Ошибка запуска")

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot_ep(bot_id: str):
    pm.stop_bot(bot_id)
    await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"status": "IDLE"})
    return {"status": "ok"}

@app.get("/api/bots/messages/{bot_id}")
async def get_messages(bot_id: str):
    res = await db.get("bot_messages", params={"bot_id": f"eq.{bot_id}", "order": "created_at.desc", "limit": 50})
    if res.status_code != 200: return []
    return [{"user": {"id": m["user_id"], "name": m["first_name"]}, "text": m["message_text"], "timestamp": m["created_at"], "is_admin": m["is_from_admin"]} for m in res.json()]

# --- BROADCAST ---

@app.post("/api/bots/broadcast")
async def broadcast(req: dict):
    bot_ids = req.get('botIds', [])
    text = req.get('message', '')
    results = {"success": 0, "failed": 0}
    
    for bid in bot_ids:
        res = await db.get("bots", params={"id": f"eq.{bid}"})
        if res.status_code != 200 or not res.json(): continue
        bot_data = res.json()[0]
        token = bot_data['token']
        users = bot_data.get('config', {}).get('connectedUsers', [])
        
        async with httpx.AsyncClient() as client:
            for u in users:
                if u.get('is_banned') or not u.get('is_active'): continue
                try:
                    r = await client.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": u['id'], "text": text, "parse_mode": "HTML"})
                    if r.status_code == 200: results["success"] += 1
                    else: results["failed"] += 1
                except: results["failed"] += 1
    return results

# --- LICENSE ---

@app.post("/api/admin/generate-key")
async def gen_key(req: dict, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET: raise HTTPException(401)
    months = req.get("months", 1)
    new_key = f"BOT-{months}-{''.join(random.choices('ABCDEF0123456789', k=8))}"
    await db.post("issued_keys", json={"key": new_key, "months": months, "used": False})
    return {"key": new_key}

@app.post("/api/license/activate")
async def activate_license(req: dict):
    bot_id, key_str = req.get("botId"), req.get("key")
    res = await db.get("issued_keys", params={"key": f"eq.{key_str}", "used": "is.false"})
    if not res.json(): raise HTTPException(400, "Ключ недействителен")
    
    key_data = res.json()[0]
    bot_res = await db.get("bots", params={"id": f"eq.{bot_id}"})
    bot_data = bot_res.json()[0]
    
    current_expiry = bot_data.get("license_expires_at", int(time.time() * 1000))
    new_expiry = max(current_expiry, int(time.time() * 1000)) + (key_data["months"] * 30 * 24 * 3600 * 1000)
    
    await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"license_expires_at": new_expiry})
    await db.patch("issued_keys", params={"key": f"eq.{key_str}"}, json={"used": True})
    return {"status": "ok", "newExpiry": new_expiry}

@app.get("/api/ping")
async def ping(): return {"status": "online"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
