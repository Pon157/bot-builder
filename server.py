
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

# Утилита для хеширования паролей (SHA-256)
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
        if not log_path or not os.path.exists(log_path): return "Лог пуст."
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.readlines()
                return "".join(content[-lines:])
        except: return "Ошибка чтения."

pm = BotProcessManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(health_monitor())
    asyncio.create_task(expiry_notification_worker())
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

async def expiry_notification_worker():
    while True:
        try:
            now_ms = int(time.time() * 1000)
            res = await db.get("bots") # Упрощенный поиск для примера
            if res.status_code == 200:
                for b in res.json():
                    # Логика уведомлений за 3 дня
                    pass
        except: pass
        await asyncio.sleep(86400)

async def restore_active_bots():
    try:
        res = await db.get("bots", params={"status": "eq.RUNNING"})
        if res.status_code == 200:
            for b in res.json():
                await pm.start_bot(b["id"], {**b, **(b.get("config") or {})} )
    except: pass

@app.post("/api/auth/request-verification")
async def request_ver(data: dict):
    email = data.get('email', '').lower()
    code = str(random.randint(100000, 999999))
    expires = int(time.time() * 1000) + 600000
    await db.post("temp_codes", json={"email": email, "code": code, "type": "register", "expires_at": expires}, headers={"Prefer": "resolution=merge-duplicates"})
    if EmailService.send_verification_code(email, code):
        return {"status": "ok"}
    raise HTTPException(500, "Ошибка отправки почты")

@app.post("/api/auth/verify-and-register")
async def register(data: dict):
    email = data['email'].lower()
    res = await db.get("temp_codes", params={"email": f"eq.{email}", "code": f"eq.{data['code']}", "type": "eq.register"})
    if res.status_code != 200 or not res.json(): raise HTTPException(400, "Неверный код")
    
    user_id = f"u_{secrets.token_hex(4)}"
    # Хешируем пароль перед записью в БД
    hashed_password = hash_password(data['password'])
    
    payload = {
        "id": user_id, "username": data['username'], "email": email, 
        "password": hashed_password, "balance": 0, "license_expires_at": int(time.time()*1000) + 259200000
    }
    await db.post("users", json=payload)
    await db.delete("temp_codes", params={"email": f"eq.{email}"})
    return payload

@app.post("/api/auth/login")
async def login(data: dict):
    email = data['email'].lower()
    # Хешируем введенный пароль для сравнения с тем, что в базе
    input_hash = hash_password(data['password'])
    
    res = await db.get("users", params={"email": f"eq.{email}", "password": f"eq.{input_hash}"})
    if res.status_code != 200 or not res.json(): 
        raise HTTPException(401, "Неверный логин или пароль")
    
    user = res.json()[0]
    # Удаляем хеш из ответа для безопасности
    if "password" in user: del user["password"]
    return user

@app.post("/api/bots/save")
async def save_bot(bot: dict):
    bot_id = bot.get("id")
    # Логика сохранения бота в Supabase
    await db.post("bots", json=bot, headers={"Prefer": "resolution=merge-duplicates"})
    return {"status": "ok"}

@app.get("/api/bots/{user_id}")
async def get_user_bots(user_id: str):
    res = await db.get("bots", params={"owner_id": f"eq.{user_id}"})
    return res.json() if res.status_code == 200 else []

@app.post("/api/bots/start")
async def start_bot_ep(req: dict):
    res = await db.get("bots", params={"id": f"eq.{req['id']}"})
    if res.status_code == 200 and res.json():
        bot = res.json()[0]
        if await pm.start_bot(bot['id'], bot):
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
