
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
        # Если бот уже запущен в этом инстансе менеджера - стопаем
        await self.stop_bot(bot_id)
        
        active_dir = os.path.join(os.getcwd(), "active_bots")
        os.makedirs(active_dir, exist_ok=True)
        config_path = os.path.join(active_dir, f"config_{bot_id}.json")
        log_path = os.path.join(active_dir, f"bot_{bot_id}.log")
        
        # Сохраняем актуальный конфиг в файл для запуска ядра
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        self.log_paths[bot_id] = log_path
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = os.getcwd()
            env["SUPABASE_URL"] = SB_URL
            env["SUPABASE_KEY"] = SB_KEY
            
            log_file = open(log_path, "a", encoding="utf-8")
            log_file.write(f"\n--- [{time.ctime()}] Запуск инстанса {bot_id} ---\n")
            
            process = await asyncio.create_subprocess_exec(
                sys.executable, "bot_core.py", config_path,
                stdout=log_file, stderr=log_file, env=env, cwd=os.getcwd()
            )
            self.processes[bot_id] = process
            logger.info(f"✅ Бот {bot_id} успешно запущен. PID: {process.pid}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка запуска бота {bot_id}: {e}")
            return str(e)

    async def stop_bot(self, bot_id: str):
        if bot_id in self.processes:
            p = self.processes[bot_id]
            logger.info(f"Stopping bot {bot_id}...")
            # Посылаем SIGTERM, чтобы бот успел сохранить статистику через save_final_state
            p.terminate()
            try: 
                await asyncio.wait_for(p.wait(), timeout=7.0)
            except: 
                logger.warning(f"Бот {bot_id} не завершился вовремя, убиваем...")
                p.kill()
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

async def auto_restart_active_bots():
    """Фоновая задача для автоматического запуска ботов при старте сервера."""
    logger.info("🔄 Инициализация автозапуска активных ботов из БД...")
    async with httpx.AsyncClient(
        base_url=f"{SB_URL}/rest/v1/",
        headers={"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}"},
        timeout=60
    ) as client:
        try:
            res = await client.get("bots", params={"status": "eq.RUNNING"})
            if res.status_code == 200:
                active_bots = res.json()
                logger.info(f"🔎 Найдено активных ботов в БД: {len(active_bots)}")
                for bot_data in active_bots:
                    config = {**bot_data, **(bot_data.get("config") or {})}
                    await pm.start_bot(bot_data['id'], config)
                    await asyncio.sleep(0.5) # Пауза чтобы не нагружать CPU
                logger.info("✨ Автозапуск завершен.")
            else:
                logger.error(f"Ошибка получения ботов для автозапуска: {res.status_code}")
        except Exception as e:
            logger.error(f"Критическая ошибка автозапуска: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # При старте API бэкенда восстанавливаем ботов
    asyncio.create_task(auto_restart_active_bots())
    yield
    # При выключении корректно стопаем всех ботов
    logger.info("🛑 Выключение сервера. Остановка ботов...")
    for bid in list(pm.processes.keys()): 
        await pm.stop_bot(bid)

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

db = httpx.AsyncClient(
    base_url=f"{SB_URL}/rest/v1/",
    headers={"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}", "Content-Type": "application/json"},
    timeout=30
)

# --- API ENDPOINTS ---

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
    code = str(data.get("code", "")).strip()
    res = await db.get("temp_codes", params={"email": f"eq.{email}", "type": "eq.REG"})
    codes = res.json()
    target = next((c for c in codes if str(c.get('code')).strip() == code), None)
    if not target: raise HTTPException(400, "Неверный код подтверждения")
    user_id = f"u_{secrets.token_hex(4)}"
    payload = {"id": user_id, "username": data['username'], "email": email, "password": data['password'], "license_expires_at": int(time.time()*1000) + 259200000}
    await db.post("users", json=payload)
    await db.delete("temp_codes", params={"email": f"eq.{email}"})
    return payload

@app.get("/api/bots/{user_id}")
async def get_user_bots(user_id: str):
    res = await db.get("bots", params={"owner_id": f"eq.{user_id}"})
    bots = res.json() if res.status_code == 200 else []
    return [{**b, **(b.get("config") or {})} for b in bots]

@app.post("/api/bots/save")
async def save_bot(bot: dict):
    bid = bot.get("id")
    sys_keys = ['id', 'owner_id', 'name', 'token', 'status', 'license_expires_at', 'config']
    config_payload = {k: v for k, v in bot.items() if k not in sys_keys}
    payload = {
        "id": bid, 
        "owner_id": bot.get("owner_id"), 
        "name": bot["name"], 
        "token": bot["token"], 
        "status": bot.get("status", "IDLE"),
        "license_expires_at": int(bot.get("license_expires_at") or 0),
        "config": config_payload
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
        bot_data = res.json()[0]
        config = {**bot_data, **(bot_data.get("config") or {})}
        if await pm.start_bot(bot_data['id'], config):
            await db.patch("bots", params={"id": f"eq.{bot_data['id']}"}, json={"status": "RUNNING"})
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
async def get_bot_messages(bot_id: str):
    res = await db.get("bot_messages", params={"bot_id": f"eq.{bot_id}", "order": "created_at.desc", "limit": "50"})
    return res.json() if res.status_code == 200 else []

@app.post("/api/bots/moderate")
async def moderate_bot_user(data: dict):
    # Заглушка модерации (в реальности бот_коре ловит изменения через полер)
    return {"status": "ok"}

@app.get("/api/ping")
async def ping(): return {"status": "online"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
