
import asyncio
import logging
import os
import sys
import time
import json
import httpx
from typing import Dict, List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

# Загрузка переменных окружения
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
    """Управляет процессами ботов в системе."""
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
            # Важно: пробрасываем PYTHONPATH, чтобы боты видели модули
            env["PYTHONPATH"] = os.getcwd()
            log_file = open(log_path, "a", encoding="utf-8")
            
            process = await asyncio.create_subprocess_exec(
                sys.executable, "bot_core.py", config_path,
                stdout=log_file, stderr=log_file, env=env, cwd=os.getcwd()
            )
            self.processes[bot_id] = process
            logger.info(f"🚀 Бот {bot_id} запущен (PID: {process.pid})")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка старта {bot_id}: {e}")
            return str(e)

    async def stop_bot(self, bot_id: str):
        if bot_id in self.processes:
            p = self.processes[bot_id]
            p.terminate()
            try: await asyncio.wait_for(p.wait(), timeout=3.0)
            except: p.kill()
            del self.processes[bot_id]
            logger.info(f"🛑 Бот {bot_id} остановлен.")
            return True
        return False

    def get_logs(self, bot_id: str, lines: int = 150):
        log_path = self.log_paths.get(bot_id)
        if not log_path or not os.path.exists(log_path): return "Лог пуст или еще не создан."
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.readlines()
                return "".join(content[-lines:])
        except: return "Ошибка при чтении файла логов."

pm = BotProcessManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Жизненный цикл приложения FastAPI."""
    asyncio.create_task(health_monitor())
    await restore_active_bots()
    yield
    # При выключении сервера гасим всех ботов
    for bid in list(pm.processes.keys()): await pm.stop_bot(bid)

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

db = httpx.AsyncClient(
    base_url=f"{SB_URL.rstrip('/')}/rest/v1/",
    headers={"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}", "Content-Type": "application/json"},
    timeout=30
)

async def health_monitor():
    """Проверяет, не упали ли боты."""
    while True:
        await asyncio.sleep(20)
        for bid, proc in list(pm.processes.items()):
            if proc.returncode is not None:
                logger.warning(f"⚠️ Бот {bid} завершился с кодом {proc.returncode}")
                del pm.processes[bid]
                try: await db.patch("bots", params={"id": f"eq.{bid}"}, json={"status": "ERROR"})
                except: pass

async def restore_active_bots():
    """Перезапускает ботов, которые должны работать."""
    try:
        res = await db.get("bots", params={"status": "eq.RUNNING"})
        if res.status_code == 200:
            for b in res.json():
                expires = b.get("license_expires_at") or 0
                if int(expires) > int(time.time() * 1000):
                    await pm.start_bot(b["id"], {**b, **(b.get("config") or {})} )
    except Exception as e: logger.error(f"Restore error: {e}")

# --- API Endpoints ---

@app.get("/api/ping")
async def ping(): return {"status": "online", "active_bots": len(pm.processes)}

@app.post("/api/bots/broadcast")
async def broadcast_mailing(req: dict):
    """Реализация массовой рассылки."""
    bot_ids = req.get('botIds', [])
    message = req.get('message', '')
    if not bot_ids or not message: return {"error": "Missing data"}
    
    success, failed = 0, 0
    async with httpx.AsyncClient() as client:
        for bid in bot_ids:
            res = await db.get("bots", params={"id": f"eq.{bid}"})
            if res.status_code != 200 or not res.json(): continue
            bot = res.json()[0]
            token = bot['token']
            subs = (bot.get('config') or {}).get('subscribers', [])
            
            for uid in subs:
                try:
                    r = await client.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": uid, "text": message, "parse_mode": "HTML"},
                        timeout=10
                    )
                    if r.status_code == 200: success += 1
                    else: failed += 1
                except: failed += 1
                await asyncio.sleep(0.05) # Защита от Flood Limit
    return {"success": success, "failed": failed}

@app.post("/api/bots/save")
async def save_bot_config(bot: dict):
    """Сохранение бота с защитой от перезатирания статистики."""
    bot_id = bot.get("id")
    # Проверяем наличие в базе для мержа
    res = await db.get("bots", params={"id": f"eq.{bot_id}"})
    db_config = {}
    if res.status_code == 200 and res.json():
        db_config = res.json()[0].get("config") or {}

    stats = bot.get("stats") or db_config.get("stats", {})
    if not stats.get("history"):
        stats["history"] = [{"date": time.strftime("%d.%m"), "incoming": 0, "outgoing": 0, "totalUsers": 0}]
    
    # Собираем конфиг из полей
    config_keys = ["description", "adminChatId", "welcomeMessage", "triggers", "buttons", "settings", "connectedUsers", "subscribers"]
    config = {k: bot.get(k) for k in config_keys if k in bot}
    config["stats"] = stats
    
    payload = {
        "id": bot_id, 
        "owner_id": bot.get("owner_id") or bot.get("ownerId"), 
        "name": bot["name"], 
        "token": bot["token"],
        "status": bot.get("status", "IDLE"), 
        "license_expires_at": int(bot.get("license_expires_at") or 0),
        "config": config
    }
    await db.post("bots", json=payload, headers={"Prefer": "resolution=merge-duplicates"})
    return {"status": "ok"}

@app.post("/api/bots/start")
async def start_bot_endpoint(req: dict):
    bot_id = req.get("id")
    res = await db.get("bots", params={"id": f"eq.{bot_id}"})
    if res.status_code != 200 or not res.json(): raise HTTPException(404, "Bot not found")
    bot = res.json()[0]
    if await pm.start_bot(bot['id'], {**bot, **(bot.get("config") or {})}):
        await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"status": "RUNNING"})
        return {"status": "ok"}
    raise HTTPException(500, "Start failed")

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot_endpoint(bot_id: str):
    await pm.stop_bot(bot_id)
    await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"status": "IDLE"})
    return {"status": "ok"}

@app.get("/api/bots/logs/{bot_id}")
async def get_logs_endpoint(bot_id: str):
    return {"logs": pm.get_logs(bot_id)}

@app.get("/api/bots/messages/{bot_id}")
async def get_messages_endpoint(bot_id: str):
    """Возвращает историю сообщений для вкладки 'Диалоги'."""
    res = await db.get("bot_messages", params={
        "bot_id": f"eq.{bot_id}", 
        "order": "created_at.desc", 
        "limit": "60"
    })
    if res.status_code != 200: return []
    return [
        {
            "user": {"id": m["user_id"], "name": m["first_name"]}, 
            "text": m["message_text"], 
            "timestamp": m["created_at"], 
            "is_admin": m["is_from_admin"]
        } for m in res.json()
    ]

@app.get("/api/bots/{user_id}")
async def get_user_bots_endpoint(user_id: str):
    """Список ботов конкретного пользователя."""
    res = await db.get("bots", params={"owner_id": f"eq.{user_id}"})
    if res.status_code != 200: return []
    bots = res.json()
    # Синхронизируем статус с реально запущенными процессами
    for b in bots: b['status'] = "RUNNING" if b['id'] in pm.processes else "IDLE"
    return [{**b, **(b.get("config") or {})} for b in bots]

@app.post("/api/auth/login")
async def login_endpoint(data: dict):
    res = await db.get("users", params={"email": f"eq.{data['email'].lower()}", "password": f"eq.{data['password']}"})
    if res.status_code != 200 or not res.json(): raise HTTPException(401, "Invalid credentials")
    return res.json()[0]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
