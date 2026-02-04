
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

    def get_logs(self, bot_id: str):
        log_path = self.log_paths.get(bot_id)
        if not log_path or not os.path.exists(log_path): return "Логов нет."
        with open(log_path, "r", encoding="utf-8") as f:
            return "".join(f.readlines()[-150:])

pm = BotProcessManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    for bid in list(pm.processes.keys()): await pm.stop_bot(bid)

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

db = httpx.AsyncClient(
    base_url=f"{SB_URL.rstrip('/')}/rest/v1/",
    headers={"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}", "Content-Type": "application/json"}
)

@app.get("/api/ping")
async def ping(): return {"status": "online"}

@app.get("/api/user/{user_id}")
async def get_user(user_id: str):
    res = await db.get("users", params={"id": f"eq.{user_id}"})
    if res.status_code == 200 and res.json():
        user = res.json()[0]
        if "password" in user: del user["password"]
        return user
    raise HTTPException(404)

@app.post("/api/auth/login")
async def login(data: dict):
    email = data['email'].lower()
    input_hash = hash_password(data['password'])
    res = await db.get("users", params={"email": f"eq.{email}", "password": f"eq.{input_hash}"})
    if res.status_code != 200 or not res.json(): raise HTTPException(401)
    user = res.json()[0]
    if "password" in user: del user["password"]
    return user

@app.get("/api/bots/{user_id}")
async def get_user_bots(user_id: str):
    res = await db.get("bots", params={"owner_id": f"eq.{user_id}"})
    return res.json() if res.status_code == 200 else []

@app.post("/api/bots/save")
async def save_bot(bot: dict):
    clean_bot = {k: v for k, v in bot.items() if k not in ['id', 'owner_id', 'name', 'token', 'status', 'license_expires_at']}
    payload = {
        "id": bot['id'], "owner_id": bot['owner_id'], "name": bot['name'],
        "token": bot['token'], "status": bot['status'], 
        "license_expires_at": bot['license_expires_at'], "config": clean_bot
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
        if await pm.start_bot(req['id'], res.json()[0]):
            await db.patch("bots", params={"id": f"eq.{req['id']}"}, json={"status": "RUNNING"})
            return {"status": "ok"}
    raise HTTPException(500)

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
    success, failed = 0, 0
    async with httpx.AsyncClient() as client:
        for bid in bot_ids:
            res = await db.get("bots", params={"id": f"eq.{bid}"})
            if res.status_code == 200 and res.json():
                bot = res.json()[0]
                token = bot.get("token")
                users = bot.get("config", {}).get("connectedUsers", [])
                for u in users:
                    try:
                        uid = u.get("id")
                        if not uid or u.get("is_banned"): continue
                        url = f"https://api.telegram.org/bot{token}/sendMessage"
                        r = await client.post(url, json={"chat_id": uid, "text": message, "parse_mode": "HTML"}, timeout=5)
                        if r.status_code == 200: success += 1
                        else: failed += 1
                    except: failed += 1
    return {"success": success, "failed": failed}

@app.post("/api/license/activate")
async def activate_license(data: dict):
    bot_id = data.get("botId")
    res = await db.get("bots", params={"id": f"eq.{bot_id}"})
    if res.status_code == 200 and res.json():
        new_expiry = int(time.time() * 1000) + (30 * 24 * 3600 * 1000)
        await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"license_expires_at": new_expiry})
        return {"status": "ok", "newExpiry": new_expiry}
    return {"status": "error"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
