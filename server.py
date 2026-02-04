
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
from fastapi import FastAPI, HTTPException, Header, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

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
            logger.info(f"🚀 Бот {bot_id} запущен успешно.")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка при запуске {bot_id}: {e}")
            return str(e)

    async def stop_bot(self, bot_id: str):
        if bot_id in self.processes:
            p = self.processes[bot_id]
            logger.info(f"🛑 Останавливаю бота {bot_id}...")
            p.terminate()
            try: await asyncio.wait_for(p.wait(), timeout=5.0)
            except: p.kill()
            del self.processes[bot_id]
            return True
        return False

    def get_logs(self, bot_id: str, lines: int = 150):
        log_path = self.log_paths.get(bot_id)
        if not log_path or not os.path.exists(log_path): return "Файл логов еще не создан."
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.readlines()
                return "".join(content[-lines:])
        except Exception as e:
            return f"Ошибка чтения логов: {e}"

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
        await asyncio.sleep(30)
        for bid, proc in list(pm.processes.items()):
            if proc.returncode is not None:
                logger.warning(f"⚠️ Бот {bid} аварийно завершился.")
                del pm.processes[bid]
                try: await db.patch("bots", params={"id": f"eq.{bid}"}, json={"status": "ERROR"})
                except: pass

async def restore_active_bots():
    logger.info("🛠 Восстановление запущенных ботов...")
    try:
        res = await db.get("bots", params={"status": "eq.RUNNING"})
        if res.status_code == 200:
            for b in res.json():
                expires = b.get("license_expires_at") or 0
                if int(expires) > int(time.time() * 1000):
                    config = {**b, **(b.get("config") or {})}
                    await pm.start_bot(b["id"], config)
        logger.info(f"✅ Восстановлено {len(pm.processes)} ботов.")
    except Exception as e:
        logger.error(f"Ошибка восстановления: {e}")

@app.get("/api/ping")
async def ping(): return {"status": "online", "active": len(pm.processes)}

@app.post("/api/auth/login")
async def login(data: dict):
    email = data.get("email", "").lower().strip()
    res = await db.get("users", params={"email": f"eq.{email}", "password": f"eq.{data['password']}"})
    if res.status_code != 200 or not res.json(): raise HTTPException(401, "Неверные данные")
    return res.json()[0]

@app.get("/api/bots/{user_id}")
async def get_user_bots(user_id: str):
    res = await db.get("bots", params={"owner_id": f"eq.{user_id}"})
    if res.status_code != 200: return []
    bots = res.json()
    for b in bots:
        b['status'] = "RUNNING" if b['id'] in pm.processes else "IDLE"
    return [{**b, **(b.get("config") or {})} for b in bots]

@app.post("/api/bots/save")
async def save_bot(bot: dict):
    owner_id = bot.get("owner_id") or bot.get("ownerId")
    if not owner_id: raise HTTPException(400, "Missing owner identifier")

    stats = bot.get("stats", {})
    # Гарантируем инициализацию истории для графиков
    if not stats.get("history") or len(stats.get("history", [])) == 0:
        stats["history"] = [{
            "date": time.strftime("%d.%m"), 
            "incoming": 0, 
            "outgoing": 0, 
            "totalUsers": 0,
            "activeUsers": 0
        }]
    
    config_fields = ["description", "adminChatId", "welcomeMessage", "triggers", "buttons", "settings", "connectedUsers", "subscribers"]
    config = {k: bot.get(k) for k in config_fields if k in bot}
    config["stats"] = stats
    
    payload = {
        "id": bot["id"], "owner_id": owner_id, "name": bot["name"], "token": bot["token"],
        "status": bot.get("status", "IDLE"), 
        "license_expires_at": int(bot.get("license_expires_at") or bot.get("licenseExpiresAt") or 0),
        "config": config
    }
    await db.post("bots", json=payload, headers={"Prefer": "resolution=merge-duplicates"})
    return {"status": "ok"}

@app.post("/api/bots/start")
async def start_bot_ep(req: dict):
    bot_id = req.get('id')
    res = await db.get("bots", params={"id": f"eq.{bot_id}"})
    if res.status_code != 200 or not res.json(): raise HTTPException(404, "Бот не найден")
    
    bot_data = res.json()[0]
    config = {**bot_data, **(bot_data.get("config") or {})}
    
    if await pm.start_bot(bot_id, config):
        await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"status": "RUNNING"})
        return {"status": "ok"}
    raise HTTPException(500, "Ошибка запуска процесса")

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot_ep(bot_id: str):
    await pm.stop_bot(bot_id)
    await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"status": "IDLE"})
    return {"status": "ok"}

@app.get("/api/bots/logs/{bot_id}")
async def get_bot_logs(bot_id: str):
    return {"logs": pm.get_logs(bot_id)}

@app.get("/api/bots/messages/{bot_id}")
async def get_messages(bot_id: str):
    res = await db.get("bot_messages", params={"bot_id": f"eq.{bot_id}", "order": "created_at.desc", "limit": "50"})
    if res.status_code != 200: return []
    return [{"user": {"id": m["user_id"], "name": m["first_name"]}, "text": m["message_text"], "timestamp": m["created_at"], "is_admin": m["is_from_admin"]} for m in res.json()]

@app.post("/api/admin/generate-key")
async def generate_key(req: dict, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET: raise HTTPException(403)
    months = req.get("months", 1)
    key = f"BOT-{months}-{secrets.token_hex(4).upper()}"
    await db.post("issued_keys", json={"key": key, "months": months, "used": False})
    return {"key": key}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
