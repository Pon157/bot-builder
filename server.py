
import asyncio
import logging
import os
import sys
import time
import json
import httpx
import secrets
from typing import Dict, List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

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

@app.post("/api/bots/save")
async def save_bot(bot: dict):
    bot_id = bot.get("id")
    # Приводим license_expires_at к числу, чтобы избежать NaN в БД
    expires = bot.get("license_expires_at")
    try:
        expires = int(expires) if expires else 0
    except:
        expires = 0

    clean_config = {k: v for k, v in bot.items() if k not in ['id', 'owner_id', 'name', 'token', 'status', 'license_expires_at']}
    
    payload = {
        "id": bot_id, 
        "owner_id": bot.get("owner_id"), 
        "name": bot["name"], 
        "token": bot["token"],
        "status": bot.get("status", "IDLE"), 
        "license_expires_at": expires,
        "config": clean_config
    }
    await db.post("bots", json=payload, headers={"Prefer": "resolution=merge-duplicates"})
    return {"status": "ok"}

@app.post("/api/license/activate")
async def activate_license(data: dict):
    bot_id = data.get("botId")
    key_str = data.get("key")
    
    # 1. Проверяем ключ
    res_key = await db.get("issued_keys", params={"key": f"eq.{key_str}", "used": "eq.false"})
    if res_key.status_code != 200 or not res_key.json():
        return {"status": "error", "message": "Ключ не найден или уже использован"}
    
    key_data = res_key.json()[0]
    months = key_data.get("months") or 0
    days = key_data.get("days") or 0
    total_days = (months * 30) + days
    
    # 2. Получаем бота
    res_bot = await db.get("bots", params={"id": f"eq.{bot_id}"})
    if res_bot.status_code != 200 or not res_bot.json():
        return {"status": "error", "message": "Бот не найден"}
    
    bot = res_bot.json()[0]
    current_expiry = int(bot.get("license_expires_at") or time.time() * 1000)
    # Если лицензия уже истекла, начинаем отсчет от текущего момента
    start_time = max(current_expiry, int(time.time() * 1000))
    new_expiry = start_time + (total_days * 24 * 3600 * 1000)
    
    # 3. Обновляем бота и ключ
    await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"license_expires_at": new_expiry})
    await db.patch("issued_keys", params={"key": f"eq.{key_str}"}, json={"used": True, "used_by_bot": bot_id})
    
    return {"status": "ok", "newExpiry": new_expiry}

@app.post("/api/auth/login")
async def login(data: dict):
    res = await db.get("users", params={"email": f"eq.{data['email'].lower()}", "password": f"eq.{data['password']}"})
    if res.status_code != 200 or not res.json(): raise HTTPException(401)
    return res.json()[0]

@app.get("/api/user/{user_id}")
async def get_user(user_id: str):
    res = await db.get("users", params={"id": f"eq.{user_id}"})
    if res.status_code == 200 and res.json():
        return res.json()[0]
    raise HTTPException(404)

@app.post("/api/auth/verify-and-register")
async def register(data: dict):
    user_id = f"u_{secrets.token_hex(4)}"
    # При регистрации даем 3 дня триала
    payload = {
        "id": user_id, "username": data['username'], "email": data['email'].lower(), 
        "password": data['password'], "balance": 0, "license_expires_at": int(time.time()*1000) + (3 * 24 * 3600 * 1000)
    }
    await db.post("users", json=payload)
    return payload

@app.get("/api/bots/{user_id}")
async def get_user_bots(user_id: str):
    res = await db.get("bots", params={"owner_id": f"eq.{user_id}"})
    bots = res.json() if res.status_code == 200 else []
    return [{**b, **(b.get("config") or {})} for b in bots]

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
