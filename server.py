
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
    """Вспомогательная функция для рассылки."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=5)
            return True
    except:
        return False

@app.post("/api/bots/broadcast")
async def broadcast_message(data: dict):
    bot_ids = data.get("botIds", [])
    message = data.get("message", "")
    if not bot_ids or not message:
        return {"success": 0, "failed": 0}

    success_count = 0
    failed_count = 0

    for bid in bot_ids:
        res = await db.get("bots", params={"id": f"eq.{bid}"})
        if res.status_code == 200 and res.json():
            bot_data = res.json()[0]
            token = bot_data.get("token")
            # Получаем юзеров из конфига
            config = bot_data.get("config", {})
            users = config.get("connectedUsers", [])
            
            for user in users:
                if user.get("is_active") and not user.get("is_banned"):
                    res_msg = await send_telegram_msg(token, user["id"], message)
                    if res_msg: success_count += 1
                    else: failed_count += 1
    
    return {"success": success_count, "failed": failed_count}

@app.post("/api/license/activate")
async def activate_license(data: dict):
    bot_id = data.get("botId")
    key_str = data.get("key")
    
    res_key = await db.get("issued_keys", params={"key": f"eq.{key_str}", "used": "eq.false"})
    if res_key.status_code != 200 or not res_key.json():
        return {"status": "error", "message": "Ключ не найден или уже использован"}
    
    key_data = res_key.json()[0]
    months = key_data.get("months") or 0
    days = key_data.get("days") or 0
    # Считаем общее кол-во мс: (месяцы * 30 + дни) * 24 * 3600 * 1000
    total_ms = ( (months * 30) + days ) * 24 * 3600 * 1000
    
    res_bot = await db.get("bots", params={"id": f"eq.{bot_id}"})
    if res_bot.status_code != 200 or not res_bot.json():
        return {"status": "error", "message": "Бот не найден"}
    
    bot = res_bot.json()[0]
    # Начинаем отсчет от текущего времени или от даты истечения, если она еще в будущем
    current_expiry = int(bot.get("license_expires_at") or 0)
    start_point = max(current_expiry, int(time.time() * 1000))
    new_expiry = start_point + total_ms
    
    await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"license_expires_at": new_expiry})
    await db.patch("issued_keys", params={"key": f"eq.{key_str}"}, json={"used": True, "used_by_bot": bot_id})
    
    return {"status": "ok", "newExpiry": new_expiry}

@app.post("/api/bots/save")
async def save_bot(bot: dict):
    bot_id = bot.get("id")
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

@app.get("/api/user/{user_id}")
async def get_user_ep(user_id: str):
    res = await db.get("users", params={"id": f"eq.{user_id}"})
    if res.status_code == 200 and res.json():
        return res.json()[0]
    raise HTTPException(404)

@app.get("/api/bots/{user_id}")
async def get_user_bots(user_id: str):
    res = await db.get("bots", params={"owner_id": f"eq.{user_id}"})
    bots = res.json() if res.status_code == 200 else []
    return [{**b, **(b.get("config") or {})} for b in bots]

@app.get("/api/ping")
async def ping(): return {"status": "online"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
