
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
        await asyncio.sleep(20)
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
                expires = b.get("license_expires_at") or 0
                if int(expires) > int(time.time() * 1000):
                    await pm.start_bot(b["id"], {**b, **(b.get("config") or {})} )
    except: pass

@app.post("/api/bots/save")
async def save_bot(bot: dict):
    bot_id = bot.get("id")
    res = await db.get("bots", params={"id": f"eq.{bot_id}"})
    db_bot = res.json()[0] if res.status_code == 200 and res.json() else {}
    db_config = db_bot.get("config") or {}

    # МЕРЖ ПОЛЬЗОВАТЕЛЕЙ: Приоритет данным из панели по варнам/банам
    incoming_users = bot.get("connectedUsers") or []
    db_users = db_config.get("connectedUsers") or []
    
    # Создаем карту существующих юзеров из БД
    users_map = {u['id']: u for u in db_users}
    
    # Обновляем их данными из входящего запроса (модерация)
    for iu in incoming_users:
        uid = iu['id']
        if uid in users_map:
            # Обновляем только поля модерации
            users_map[uid].update({
                "is_banned": iu.get("is_banned", users_map[uid].get("is_banned", False)),
                "warns": iu.get("warns", users_map[uid].get("warns", 0)),
                "is_active": iu.get("is_active", users_map[uid].get("is_active", True))
            })
        else:
            users_map[uid] = iu
            
    final_users = list(users_map.values())

    # Статистика
    incoming_stats = bot.get("stats") or {}
    db_stats = db_config.get("stats") or {}
    if db_stats.get("totalMessages", 0) > incoming_stats.get("totalMessages", 0):
        final_stats = db_stats
    else:
        final_stats = incoming_stats

    config_keys = ["description", "adminChatId", "welcomeMessage", "triggers", "buttons", "settings", "subscribers"]
    config = {k: bot.get(k) for k in config_keys if k in bot}
    config["stats"] = final_stats
    config["connectedUsers"] = final_users
    
    payload = {
        "id": bot_id, "owner_id": bot.get("owner_id"), "name": bot["name"], "token": bot["token"],
        "status": bot.get("status", "IDLE"), 
        "license_expires_at": int(bot.get("license_expires_at") or 0),
        "config": config
    }
    await db.post("bots", json=payload, headers={"Prefer": "resolution=merge-duplicates"})
    return {"status": "ok"}

@app.post("/api/auth/login")
async def login(data: dict):
    res = await db.get("users", params={"email": f"eq.{data['email'].lower()}", "password": f"eq.{data['password']}"})
    if res.status_code != 200 or not res.json(): raise HTTPException(401)
    return res.json()[0]

@app.post("/api/auth/verify-and-register")
async def register(data: dict):
    user_id = f"u_{secrets.token_hex(4)}"
    payload = {
        "id": user_id, "username": data['username'], "email": data['email'].lower(), 
        "password": data['password'], "balance": 0, "license_expires_at": int(time.time()*1000) + 259200000
    }
    await db.post("users", json=payload)
    return payload

@app.get("/api/bots/messages/{bot_id}")
async def get_messages(bot_id: str):
    res = await db.get("bot_messages", params={"bot_id": f"eq.{bot_id}", "order": "created_at.desc", "limit": "100"})
    return [{"user": {"id": m["user_id"], "name": m["first_name"]}, "text": m["message_text"], "timestamp": m["created_at"], "is_admin": m["is_from_admin"]} for m in res.json()] if res.status_code == 200 else []

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

@app.get("/api/bots/{user_id}")
async def get_user_bots(user_id: str):
    res = await db.get("bots", params={"owner_id": f"eq.{user_id}"})
    bots = res.json() if res.status_code == 200 else []
    for b in bots: b['status'] = "RUNNING" if b['id'] in pm.processes else "IDLE"
    return [{**b, **(b.get("config") or {})} for b in bots]

@app.get("/api/bots/logs/{bot_id}")
async def logs(bot_id: str): return {"logs": pm.get_logs(bot_id)}

@app.post("/api/bots/broadcast")
async def broadcast(data: dict, background_tasks: BackgroundTasks):
    bot_ids = data.get("botIds", [])
    message = data.get("message", "")
    if not bot_ids or not message: return {"success": 0, "failed": 0}
    
    success, failed = 0, 0
    async with httpx.AsyncClient() as client:
        for bid in bot_ids:
            res = await db.get("bots", params={"id": f"eq.{bid}"})
            if res.status_code == 200 and res.json():
                bot_data = res.json()[0]
                token = bot_data.get("token")
                config = bot_data.get("config") or {}
                users = config.get("connectedUsers") or []
                subscribers = [u['id'] for u in users if u.get('is_active') and not u.get('is_banned')]
                
                for uid in subscribers:
                    try:
                        url = f"https://api.telegram.org/bot{token}/sendMessage"
                        r = await client.post(url, json={"chat_id": uid, "text": message, "parse_mode": "HTML"}, timeout=5)
                        if r.status_code == 200: success += 1
                        else: failed += 1
                    except: failed += 1
    return {"success": success, "failed": failed}

@app.get("/api/ping")
async def ping(): return {"status": "online"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
