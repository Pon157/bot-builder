
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

SB_URL = os.getenv("SUPABASE_URL", "").rstrip('/')
SB_KEY = os.getenv("SUPABASE_KEY", "")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")

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
            env["SUPABASE_URL"] = SB_URL
            env["SUPABASE_KEY"] = SB_KEY
            
            # Очищаем лог перед запуском
            with open(log_path, "w") as f: f.write(f"--- Запуск инстанса {bot_id} ---\n")
            
            log_file = open(log_path, "a", encoding="utf-8")
            process = await asyncio.create_subprocess_exec(
                sys.executable, "bot_core.py", config_path,
                stdout=log_file, stderr=log_file, env=env, cwd=os.getcwd()
            )
            self.processes[bot_id] = process
            logger.info(f"Bot {bot_id} started. PID: {process.pid}")
            return True
        except Exception as e:
            logger.error(f"Error starting bot {bot_id}: {e}")
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

    def get_logs(self, bot_id: str, lines: int = 500):
        path = self.log_paths.get(bot_id)
        if not path or not os.path.exists(path): return "Лог пуст. Запустите бота."
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.readlines()
                return "".join(content[-lines:])
        except Exception as e:
            return f"Ошибка чтения логов: {e}"

pm = BotProcessManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    for bid in list(pm.processes.keys()): await pm.stop_bot(bid)

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

db = httpx.AsyncClient(
    base_url=f"{SB_URL}/rest/v1/",
    headers={"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}", "Content-Type": "application/json"},
    timeout=30
)

# --- ADMIN API ---
@app.post("/api/admin/generate-key")
async def generate_key(data: dict, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET: raise HTTPException(401, "Unauthorized")
    new_key = f"BE-{secrets.token_hex(3).upper()}-{secrets.token_hex(3).upper()}"
    payload = {"key": new_key, "months": data.get("months", 0), "days": data.get("days", 0), "used": False}
    await db.post("issued_keys", json=payload)
    return {"key": new_key}

# --- AUTH API ---
@app.post("/api/auth/login")
async def login(data: dict):
    res = await db.get("users", params={"email": f"eq.{data['email'].lower()}", "password": f"eq.{data['password']}"})
    if not res.json(): raise HTTPException(401, "Invalid credentials")
    return res.json()[0]

@app.post("/api/auth/request-verification")
async def req_verif(data: dict):
    email = data.get("email", "").lower()
    code = "".join([str(random.randint(0, 9)) for _ in range(6)])
    expires = int(time.time() * 1000) + (10 * 60 * 1000)
    await db.post("temp_codes", json={"email": email, "code": code, "type": "REG", "expires_at": expires}, headers={"Prefer": "resolution=merge-duplicates"})
    EmailService.send_verification_code(email, code)
    return {"status": "ok"}

@app.post("/api/auth/verify-and-register")
async def verify_reg(data: dict):
    email = data.get("email", "").lower()
    res_code = await db.get("temp_codes", params={"email": f"eq.{email}", "code": f"eq.{data['code']}"})
    if not res_code.json(): raise HTTPException(400, "Invalid code")
    user_id = f"u_{secrets.token_hex(4)}"
    payload = {"id": user_id, "username": data['username'], "email": email, "password": data['password'], "license_expires_at": int(time.time()*1000) + 259200000}
    await db.post("users", json=payload)
    await db.delete("temp_codes", params={"email": f"eq.{email}"})
    return payload

@app.get("/api/auth/user/{user_id}")
async def get_user_info(user_id: str):
    res = await db.get("users", params={"id": f"eq.{user_id}"})
    if res.json(): return res.json()[0]
    raise HTTPException(404)

# --- BOTS API ---
@app.get("/api/bots/{user_id}")
async def get_user_bots(user_id: str):
    res = await db.get("bots", params={"owner_id": f"eq.{user_id}"})
    bots = res.json() if res.status_code == 200 else []
    return [{**b, **(b.get("config") or {})} for b in bots]

@app.post("/api/bots/save")
async def save_bot(bot: dict):
    bid = bot.get("id")
    sys_keys = ['id', 'owner_id', 'name', 'token', 'status', 'license_expires_at']
    payload = {
        "id": bid, "owner_id": bot.get("owner_id"), "name": bot["name"], 
        "token": bot["token"], "status": bot.get("status", "IDLE"),
        "license_expires_at": int(bot.get("license_expires_at") or 0),
        "config": {k: v for k, v in bot.items() if k not in sys_keys}
    }
    await db.post("bots", json=payload, headers={"Prefer": "resolution=merge-duplicates"})
    return {"status": "ok"}

@app.delete("/api/bots/delete/{user_id}/{bot_id}")
async def delete_bot(user_id: str, bot_id: str):
    await pm.stop_bot(bot_id)
    await db.delete("bots", params={"id": f"eq.{bot_id}", "owner_id": f"eq.{user_id}"})
    return {"status": "ok"}

@app.post("/api/bots/start")
async def start_bot(req: dict):
    res = await db.get("bots", params={"id": f"eq.{req['id']}"})
    if res.json():
        bot = res.json()[0]
        if await pm.start_bot(bot['id'], {**bot, **(bot.get("config") or {})}):
            await db.patch("bots", params={"id": f"eq.{bot['id']}"}, json={"status": "RUNNING"})
            return {"status": "ok"}
    raise HTTPException(500, "Start failed")

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    await pm.stop_bot(bot_id)
    await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"status": "IDLE"})
    return {"status": "ok"}

@app.get("/api/bots/messages/{bot_id}")
async def get_bot_msgs(bot_id: str):
    res = await db.get("bot_messages", params={"bot_id": f"eq.{bot_id}", "order": "created_at.desc", "limit": "50"})
    return [{"text": m["message_text"], "timestamp": m["created_at"], "is_admin": m["is_from_admin"], "user": {"name": m["first_name"]}} for m in res.json()][::-1]

@app.get("/api/bots/logs/{bot_id}")
async def bot_logs_api(bot_id: str): return {"logs": pm.get_logs(bot_id)}

@app.post("/api/bots/broadcast")
async def broadcast(data: dict):
    bot_ids, message = data.get("botIds", []), data.get("message", "")
    success, failed = 0, 0
    for bid in bot_ids:
        res = await db.get("bots", params={"id": f"eq.{bid}"})
        if res.json():
            bot = res.json()[0]
            users = (bot.get("config") or {}).get("connectedUsers", [])
            for u in users:
                if not u.get("is_banned") and u.get("is_active"):
                    url = f"https://api.telegram.org/bot{bot['token']}/sendMessage"
                    try:
                        async with httpx.AsyncClient() as client:
                            r = await client.post(url, json={"chat_id": u["id"], "text": message, "parse_mode": "HTML"})
                            if r.status_code == 200: success += 1
                            else: failed += 1
                    except: failed += 1
    return {"success": success, "failed": failed}

@app.post("/api/license/activate")
async def activate_lic(data: dict):
    res_key = await db.get("issued_keys", params={"key": f"eq.{data['key']}", "used": "eq.false"})
    if not res_key.json(): return {"status": "error", "message": "Invalid key"}
    k = res_key.json()[0]
    add_ms = (k.get("months", 0) * 30 + k.get("days", 0)) * 24 * 3600 * 1000
    res_bot = await db.get("bots", params={"id": f"eq.{data['botId']}"})
    if res_bot.json():
        bot = res_bot.json()[0]
        new_exp = max(int(bot.get("license_expires_at") or 0), int(time.time()*1000)) + add_ms
        await db.patch("bots", params={"id": f"eq.{bot['id']}"}, json={"license_expires_at": new_exp})
        await db.patch("issued_keys", params={"key": f"eq.{data['key']}"}, json={"used": True, "used_by_bot": bot['id']})
        return {"status": "ok", "newExpiry": new_exp}
    return {"status": "error"}

@app.get("/api/ping")
async def ping(): return {"status": "online"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
