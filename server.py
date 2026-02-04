
import asyncio
import logging
import os
import sys
import time
import json
import httpx
import secrets
import random
from typing import Dict, List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from email_service import EmailService

# Настройка окружения
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")

load_env()
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("BotEngineServer")

SB_URL = os.getenv("SUPABASE_URL")
SB_KEY = os.getenv("SUPABASE_KEY")

class BotProcessManager:
    def __init__(self):
        self.processes: Dict[str, asyncio.subprocess.Process] = {}
        self.log_paths: Dict[str, str] = {}

    async def start_bot(self, bot_id: str, config: dict):
        await self.stop_bot(bot_id)
        active_dir = os.path.join(os.getcwd(), "active_bots")
        os.makedirs(active_dir, exist_ok=True)
        config_path = os.path.join(active_dir, f"config_{bot_id}.json")
        log_path = os.path.join(active_dir, f"bot_{bot_id}.log")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        self.log_paths[bot_id] = log_path
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = os.getcwd()
            log_file = open(log_path, "a", encoding="utf-8")
            process = await asyncio.create_subprocess_exec(
                sys.executable, "bot_core.py", config_path,
                stdout=log_file, stderr=log_file, env=env, cwd=os.getcwd()
            )
            self.processes[bot_id] = process
            return True
        except Exception as e:
            return str(e)

    async def stop_bot(self, bot_id: str):
        if bot_id in self.processes:
            p = self.processes[bot_id]
            p.terminate()
            try: await asyncio.wait_for(p.wait(), timeout=3.0)
            except: p.kill()
            del self.processes[bot_id]
            return True
        return False

    def get_logs(self, bot_id: str, lines: int = 150):
        log_path = self.log_paths.get(bot_id)
        if not log_path or not os.path.exists(log_path): return "Лог пуст."
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.readlines()
                return "".join(content[-lines:])
        except: return "Ошибка чтения."

pm = BotProcessManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    for bid in list(pm.processes.keys()): await pm.stop_bot(bid)

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
db = httpx.AsyncClient(
    base_url=f"{SB_URL.rstrip('/')}/rest/v1/",
    headers={"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}", "Content-Type": "application/json"},
    timeout=30
)

async def send_telegram_msg(token: str, chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=5)
            return r.status_code == 200
    except:
        return False

# --- AUTH ENDPOINTS ---

@app.post("/api/auth/request-verification")
async def request_verification(data: dict):
    email = data.get("email", "").lower()
    code = "".join([str(random.randint(0, 9)) for _ in range(6)])
    expires = int(time.time() * 1000) + (10 * 60 * 1000) # 10 минут
    
    # Сохраняем код в БД
    await db.post("temp_codes", json={"email": email, "code": code, "type": "REG", "expires_at": expires}, headers={"Prefer": "resolution=merge-duplicates"})
    
    # Отправляем письмо
    sent = EmailService.send_verification_code(email, code)
    if not sent:
        return {"status": "error", "message": "Ошибка отправки письма"}
    return {"status": "ok"}

@app.post("/api/auth/forgot-password")
async def forgot_password(data: dict):
    email = data.get("email", "").lower()
    # Проверяем есть ли юзер
    res = await db.get("users", params={"email": f"eq.{email}"})
    if not res.json(): return {"status": "error", "message": "Пользователь не найден"}
    
    code = "".join([str(random.randint(0, 9)) for _ in range(6)])
    expires = int(time.time() * 1000) + (10 * 60 * 1000)
    await db.post("temp_codes", json={"email": email, "code": code, "type": "RESET", "expires_at": expires}, headers={"Prefer": "resolution=merge-duplicates"})
    
    EmailService.send_password_reset(email, code)
    return {"status": "ok"}

@app.post("/api/auth/reset-password")
async def reset_password(data: dict):
    email = data.get("email", "").lower()
    code = data.get("code")
    new_password = data.get("newPassword")
    
    res = await db.get("temp_codes", params={"email": f"eq.{email}", "code": f"eq.{code}", "type": "eq.RESET"})
    if not res.json(): return {"status": "error", "message": "Неверный код"}
    
    await db.patch("users", params={"email": f"eq.{email}"}, json={"password": new_password})
    await db.delete("temp_codes", params={"email": f"eq.{email}"})
    return {"status": "ok"}

@app.post("/api/auth/login")
async def login(data: dict):
    res = await db.get("users", params={"email": f"eq.{data['email'].lower()}", "password": f"eq.{data['password']}"})
    if res.status_code != 200 or not res.json(): raise HTTPException(401)
    return res.json()[0]

@app.get("/api/auth/user/{user_id}")
async def get_user_ep(user_id: str):
    res = await db.get("users", params={"id": f"eq.{user_id}"})
    if res.status_code == 200 and res.json():
        return res.json()[0]
    raise HTTPException(404)

@app.post("/api/auth/verify-and-register")
async def verify_reg(data: dict):
    email = data.get("email", "").lower()
    code = data.get("code")
    
    res_code = await db.get("temp_codes", params={"email": f"eq.{email}", "code": f"eq.{code}"})
    if not res_code.json(): raise HTTPException(400, "Неверный код")
    
    user_id = f"u_{secrets.token_hex(4)}"
    payload = {
        "id": user_id, "username": data['username'], "email": email, 
        "password": data['password'], "balance": 0, 
        "license_expires_at": int(time.time()*1000) + (3 * 24 * 3600 * 1000)
    }
    await db.post("users", json=payload)
    await db.delete("temp_codes", params={"email": f"eq.{email}"})
    return payload

# --- BOTS ENDPOINTS ---

@app.get("/api/bots/{user_id}")
async def get_user_bots(user_id: str):
    res = await db.get("bots", params={"owner_id": f"eq.{user_id}"})
    bots = res.json() if res.status_code == 200 else []
    return [{**b, **(b.get("config") or {})} for b in bots]

@app.post("/api/bots/broadcast")
async def broadcast_message(data: dict):
    bot_ids = data.get("botIds", [])
    message = data.get("message", "")
    if not bot_ids or not message: return {"success": 0, "failed": 0}

    success = 0
    failed = 0
    for bid in bot_ids:
        res = await db.get("bots", params={"id": f"eq.{bid}"})
        if res.status_code == 200 and res.json():
            bot = res.json()[0]
            token = bot.get("token")
            users = bot.get("config", {}).get("connectedUsers", [])
            for u in users:
                if u.get("is_active") and not u.get("is_banned"):
                    if await send_telegram_msg(token, u["id"], message): success += 1
                    else: failed += 1
    return {"success": success, "failed": failed}

@app.post("/api/license/activate")
async def activate_license(data: dict):
    bot_id = data.get("botId")
    key_str = data.get("key")
    
    res_key = await db.get("issued_keys", params={"key": f"eq.{key_str}", "used": "eq.false"})
    if res_key.status_code != 200 or not res_key.json():
        return {"status": "error", "message": "Ключ не найден"}
    
    key_data = res_key.json()[0]
    total_ms = ( (key_data.get("months") or 0) * 30 + (key_data.get("days") or 0) ) * 24 * 3600 * 1000
    
    res_bot = await db.get("bots", params={"id": f"eq.{bot_id}"})
    if not res_bot.json(): return {"status": "error", "message": "Бот не найден"}
    
    bot = res_bot.json()[0]
    start = max(int(bot.get("license_expires_at") or 0), int(time.time() * 1000))
    new_expiry = start + total_ms
    
    await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"license_expires_at": new_expiry})
    await db.patch("issued_keys", params={"key": f"eq.{key_str}"}, json={"used": True, "used_by_bot": bot_id})
    return {"status": "ok", "newExpiry": new_expiry}

@app.post("/api/bots/save")
async def save_bot(bot: dict):
    bot_id = bot.get("id")
    expires = int(bot.get("license_expires_at") or 0)
    clean_config = {k: v for k, v in bot.items() if k not in ['id', 'owner_id', 'name', 'token', 'status', 'license_expires_at']}
    payload = {
        "id": bot_id, "owner_id": bot.get("owner_id"), "name": bot["name"], "token": bot["token"],
        "status": bot.get("status", "IDLE"), "license_expires_at": expires, "config": clean_config
    }
    await db.post("bots", json=payload, headers={"Prefer": "resolution=merge-duplicates"})
    return {"status": "ok"}

@app.post("/api/bots/start")
async def start_bot_ep(req: dict):
    res = await db.get("bots", params={"id": f"eq.{req['id']}"})
    if res.status_code == 200 and res.json():
        bot = res.json()[0]
        if await pm.start_bot(bot['id'], {**bot, **(bot.get("config") or {})}):
            await db.patch("bots", params={"id": f"eq.{bot['id']}"}, json={"status": "RUNNING"})
            return {"status": "ok"}
    raise HTTPException(500)

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot_ep(bot_id: str):
    await pm.stop_bot(bot_id)
    await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"status": "IDLE"})
    return {"status": "ok"}

@app.get("/api/bots/logs/{bot_id}")
async def logs(bot_id: str): return {"logs": pm.get_logs(bot_id)}

@app.get("/api/ping")
async def ping(): return {"status": "online"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
