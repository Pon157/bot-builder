
import asyncio
import logging
import os
import sys
import time
import json
import httpx
import secrets
import random
from datetime import datetime
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

# --- API ---

@app.get("/api/ping")
async def ping(): return {"status": "online"}

@app.post("/api/auth/login")
async def login(data: dict):
    res = await db.get("users", params={"email": f"eq.{data['email'].lower()}", "password": f"eq.{data['password']}"})
    if not res.json(): raise HTTPException(401, "Invalid credentials")
    return res.json()[0]

@app.post("/api/bots/save")
async def save_bot(bot: dict):
    bid = bot.get("id")
    res = await db.get("bots", params={"id": f"eq.{bid}"})
    db_bot = res.json()[0] if res.status_code == 200 and res.json() else {}
    db_config = db_bot.get("config", {})

    sys_keys = ['id', 'owner_id', 'name', 'token', 'status', 'license_expires_at', 'config']
    incoming_config = {k: v for k, v in bot.items() if k not in sys_keys}
    
    # Глубокое слияние: сохраняем самые свежие данные о юзерах и стате
    merged_config = {
        **incoming_config,
        "stats": db_config.get("stats", bot.get("stats", {})),
        "connectedUsers": db_config.get("connectedUsers", bot.get("connectedUsers", []))
    }
    
    payload = {
        "id": bid, "owner_id": bot.get("owner_id"), "name": bot["name"], "token": bot["token"], 
        "status": db_bot.get("status", "IDLE"), "license_expires_at": int(db_bot.get("license_expires_at", 0)),
        "config": merged_config
    }
    await db.post("bots", json=payload, headers={"Prefer": "resolution=merge-duplicates"})
    return {"status": "ok"}

@app.post("/api/bots/broadcast")
async def send_broadcast(data: dict):
    bot_ids = data.get("botIds", [])
    message = data.get("message", "")
    if not bot_ids or not message: return {"success": 0, "failed": 0}

    results = {"success": 0, "failed": 0}
    today = datetime.now().strftime("%d.%m")

    async with httpx.AsyncClient() as client:
        for bid in bot_ids:
            res = await db.get("bots", params={"id": f"eq.{bid}"})
            if not res.json(): continue
            bot = res.json()[0]
            token = bot["token"]
            config = bot.get("config", {})
            users = config.get("connectedUsers", [])
            stats = config.get("stats", {"totalMessages": 0, "outgoingToday": 0, "history": []})
            
            changes_made = False
            for u in users:
                # Отправляем только активным
                if u.get("is_active", True) and not u.get("is_banned", False):
                    try:
                        url = f"https://api.telegram.org/bot{token}/sendMessage"
                        r = await client.post(url, json={"chat_id": u["id"], "text": message, "parse_mode": "HTML"}, timeout=10)
                        
                        if r.status_code == 200:
                            results["success"] += 1
                            stats["totalMessages"] = stats.get("totalMessages", 0) + 1
                            stats["outgoingToday"] = stats.get("outgoingToday", 0) + 1
                            
                            # Обновляем историю для графиков
                            history = stats.get("history", [])
                            found_day = False
                            for day_pt in history:
                                if day_pt.get("date") == today:
                                    day_pt["outgoing"] = day_pt.get("outgoing", 0) + 1
                                    found_day = True
                                    break
                            if not found_day:
                                history.append({"date": today, "incoming": 0, "outgoing": 1, "totalUsers": len(users), "activeUsers": len([x for x in users if x.get('is_active', True)])})
                            stats["history"] = history[-14:]
                            changes_made = True
                        elif r.status_code == 403: # БОТ ЗАБЛОКИРОВАН ПОЛЬЗОВАТЕЛЕМ
                            u["is_active"] = False
                            results["failed"] += 1
                            changes_made = True
                        else:
                            results["failed"] += 1
                    except Exception as e:
                        logger.error(f"Broadcast error for user {u['id']}: {e}")
                        results["failed"] += 1
                    await asyncio.sleep(0.04) # Anti-flood
            
            if changes_made:
                config["connectedUsers"] = users
                config["stats"] = stats
                await db.patch("bots", params={"id": f"eq.{bid}"}, json={"config": config})
                
    return results

@app.post("/api/bots/moderate")
async def moderate_user(data: dict):
    bot_id = data.get("botId")
    user_id = data.get("userId")
    action = data.get("action")
    
    res = await db.get("bots", params={"id": f"eq.{bot_id}"})
    if not res.json(): raise HTTPException(404, "Bot not found")
    bot = res.json()[0]
    config = bot.get("config") or {}
    users = config.get("connectedUsers", [])
    
    target_user = next((u for u in users if u['id'] == user_id), None)
    if not target_user: raise HTTPException(404, "User not found")
    
    if action == "ban": target_user["is_banned"] = True
    elif action == "unban": target_user["is_banned"] = False
    elif action == "warn": target_user["warns"] = target_user.get("warns", 0) + 1
    elif action == "unwarn": target_user["warns"] = max(0, target_user.get("warns", 0) - 1)

    await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"config": config})
    return {"status": "ok", "user": target_user}

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

@app.get("/api/bots/logs/{bot_id}")
async def bot_logs_api(bot_id: str): return {"logs": pm.get_logs(bot_id)}

@app.get("/api/bots/messages/{bot_id}")
async def get_bot_msgs(bot_id: str):
    res = await db.get("bot_messages", params={"bot_id": f"eq.{bot_id}", "order": "created_at.desc", "limit": "50"})
    return [{"text": m["message_text"], "timestamp": m["created_at"], "is_admin": m["is_from_admin"], "user": {"name": m["first_name"]}} for m in res.json()][::-1]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
