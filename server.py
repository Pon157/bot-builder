
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
from fastapi import FastAPI, HTTPException, Request, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from email_service import EmailService

# Настройка окружения
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
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
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

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
        
        # Если конфиг упакован в поле config, распаковываем
        bot_data = config.get("config", config) if "config" in config else config
        
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(bot_data, f, ensure_ascii=False, indent=2)
        
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
            logger.info(f"🚀 {bot_id} запущен.")
            return True
        except Exception as e:
            logger.error(f"❌ {bot_id} ошибка: {e}")
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
        if not log_path or not os.path.exists(log_path): return "Логов пока нет. Бот запущен?"
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.readlines()
                return "".join(content[-lines:])
        except: return "Ошибка чтения логов."

pm = BotProcessManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(health_monitor())
    await restore_active_bots()
    yield
    for bid in list(pm.processes.keys()): await pm.stop_bot(bid)

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

db = httpx.AsyncClient(
    base_url=f"{SB_URL.rstrip('/')}/rest/v1/",
    headers={"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}", "Content-Type": "application/json"},
    timeout=30
)

async def health_monitor():
    while True:
        await asyncio.sleep(60)
        for bid, proc in list(pm.processes.items()):
            if proc.returncode is not None:
                del pm.processes[bid]
                try: await db.patch("bots", params={"id": f"eq.{bid}"}, json={"status": "ERROR"})
                except: pass

async def restore_active_bots():
    try:
        res = await db.get("bots", params={"status": "eq.RUNNING"})
        if res.status_code == 200:
            for b in res.json():
                await pm.start_bot(b["id"], b)
    except Exception as e:
        logger.error(f"Restore error: {e}")

@app.get("/api/ping")
async def ping(): return {"status": "online"}

@app.post("/api/auth/login")
async def login(data: dict):
    email = data['email'].lower()
    input_hash = hash_password(data['password'])
    res = await db.get("users", params={"email": f"eq.{email}", "password": f"eq.{input_hash}"})
    if res.status_code != 200 or not res.json(): 
        raise HTTPException(401, "Неверный логин или пароль")
    user = res.json()[0]
    if "password" in user: del user["password"]
    return user

@app.post("/api/auth/request-verification")
async def request_ver(data: dict):
    email = data.get('email', '').lower()
    code = str(random.randint(100000, 999999))
    expires = int(time.time() * 1000) + 600000
    await db.post("temp_codes", json={"email": email, "code": code, "type": "register", "expires_at": expires})
    if EmailService.send_verification_code(email, code):
        return {"status": "ok"}
    raise HTTPException(500, "Ошибка отправки почты")

@app.post("/api/auth/verify-and-register")
async def register(data: dict):
    email = data['email'].lower()
    res = await db.get("temp_codes", params={"email": f"eq.{email}", "code": f"eq.{data['code']}"})
    if res.status_code != 200 or not res.json(): raise HTTPException(400, "Неверный код")
    user_id = f"u_{secrets.token_hex(4)}"
    payload = {
        "id": user_id, "username": data['username'], "email": email, 
        "password": hash_password(data['password']), "balance": 0, 
        "license_expires_at": int(time.time()*1000) + 259200000
    }
    await db.post("users", json=payload)
    return payload

@app.get("/api/bots/{user_id}")
async def get_user_bots(user_id: str):
    res = await db.get("bots", params={"owner_id": f"eq.{user_id}"})
    return res.json() if res.status_code == 200 else []

@app.post("/api/bots/save")
async def save_bot(bot: dict):
    # Сохраняем все поля, упаковывая специфичные настройки в config JSONB для БД
    clean_bot = {k: v for k, v in bot.items() if k not in ['id', 'owner_id', 'name', 'token', 'status', 'license_expires_at']}
    payload = {
        "id": bot['id'],
        "owner_id": bot['owner_id'],
        "name": bot['name'],
        "token": bot['token'],
        "status": bot['status'],
        "license_expires_at": bot['license_expires_at'],
        "config": clean_bot
    }
    await db.post("bots", json=payload, headers={"Prefer": "resolution=merge-duplicates"})
    return {"status": "ok"}

@app.delete("/api/bots/delete/{user_id}/{bot_id}")
async def delete_bot(user_id: str, bot_id: str):
    await pm.stop_bot(bot_id)
    await db.delete("bots", params={"id": f"eq.{bot_id}", "owner_id": f"eq.{user_id}"})
    return {"status": "ok"}

@app.post("/api/bots/start")
async def start_bot_ep(req: dict):
    res = await db.get("bots", params={"id": f"eq.{req['id']}"})
    if res.status_code == 200 and res.json():
        bot = res.json()[0]
        if await pm.start_bot(bot['id'], bot):
            await db.patch("bots", params={"id": f"eq.{bot['id']}"}, json={"status": "RUNNING"})
            return {"status": "ok"}
    raise HTTPException(500, "Ошибка запуска")

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot_ep(bot_id: str):
    await pm.stop_bot(bot_id)
    await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"status": "IDLE"})
    return {"status": "ok"}

@app.get("/api/bots/logs/{bot_id}")
async def get_logs_ep(bot_id: str):
    return {"logs": pm.get_logs(bot_id)}

@app.post("/api/bots/broadcast")
async def broadcast(data: dict):
    bot_ids = data.get("botIds", [])
    message = data.get("message", "")
    if not bot_ids or not message:
        raise HTTPException(400, "Пустой список ботов или сообщение")
    
    success = 0
    failed = 0
    
    for bid in bot_ids:
        res = await db.get("bots", params={"id": f"eq.{bid}"})
        if res.status_code == 200 and res.json():
            bot_data = res.json()[0]
            token = bot_data.get("token")
            config = bot_data.get("config", {})
            users = config.get("connectedUsers", [])
            
            if not token or not users:
                continue

            # Рассылка по пользователям бота
            async with httpx.AsyncClient() as client:
                for u in users:
                    try:
                        uid = u.get("id")
                        if not uid or u.get("is_banned"): continue
                        url = f"https://api.telegram.org/bot{token}/sendMessage"
                        r = await client.post(url, json={"chat_id": uid, "text": message, "parse_mode": "HTML"})
                        if r.status_code == 200: success += 1
                        else: failed += 1
                    except: failed += 1
    
    return {"success": success, "failed": failed}

@app.post("/api/license/activate")
async def activate_license(data: dict):
    # Упрощенная логика активации для примера
    bot_id = data.get("botId")
    res = await db.get("bots", params={"id": f"eq.{bot_id}"})
    if res.status_code == 200 and res.json():
        new_expiry = int(time.time() * 1000) + (30 * 24 * 3600 * 1000)
        await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"license_expires_at": new_expiry})
        return {"status": "ok", "newExpiry": new_expiry}
    return {"status": "error", "message": "Бот не найден"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
