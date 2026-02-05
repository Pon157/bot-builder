
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
from fastapi import FastAPI, HTTPException, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from email_service import EmailService

# Глубокая загрузка переменных окружения
def init_environment():
    env_file = '.env'
    if os.path.exists(env_file):
        with open(env_file, 'r', encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip().strip('"').strip("'")

init_environment()

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("BotEngineServer")

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip('/')
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")

class RuntimeProcessManager:
    def __init__(self):
        self.active_processes: Dict[str, asyncio.subprocess.Process] = {}
        self.bot_log_registry: Dict[str, str] = {}

    async def spawn_bot(self, bot_id: str, configuration: dict):
        """Создает и запускает изолированный процесс бота."""
        await self.kill_bot(bot_id)
        
        os.makedirs("active_bots", exist_ok=True)
        config_path = os.path.join("active_bots", f"config_{bot_id}.json")
        log_path = os.path.join("active_bots", f"bot_{bot_id}.log")
        
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(configuration, f, ensure_ascii=False, indent=4)
        
        self.bot_log_registry[bot_id] = log_path
        
        try:
            bot_env = os.environ.copy()
            bot_env.update({"SUPABASE_URL": SUPABASE_URL, "SUPABASE_KEY": SUPABASE_KEY})
            
            # Открываем файл логов в режиме добавления
            log_output = open(log_path, "a", encoding="utf-8")
            
            process = await asyncio.create_subprocess_exec(
                sys.executable, "bot_core.py", config_path,
                stdout=log_output, stderr=log_output, env=bot_env
            )
            self.active_processes[bot_id] = process
            return True
        except Exception as e:
            logger.error(f"Process spawn failed for {bot_id}: {e}")
            return str(e)

    async def kill_bot(self, bot_id: str):
        """Останавливает процесс бота."""
        if bot_id in self.active_processes:
            p = self.active_processes[bot_id]
            p.terminate()
            try:
                await asyncio.wait_for(p.wait(), timeout=3.0)
            except:
                p.kill()
            del self.active_processes[bot_id]
            return True
        return False

    def fetch_logs(self, bot_id: str, tail: int = 400):
        """Читает последние строки логов процесса."""
        path = self.bot_log_registry.get(bot_id)
        if not path or not os.path.exists(path):
            return "Логи не найдены. Бот еще не запускался."
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                return "".join(lines[-tail:])
        except Exception as e:
            return f"Ошибка чтения: {e}"

pm = RuntimeProcessManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Код при запуске сервера
    yield
    # Код при выключении: тушим всех ботов
    for bot_id in list(pm.active_processes.keys()):
        await pm.kill_bot(bot_id)

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_methods=["*"], 
    allow_headers=["*"]
)

# Прямой клиент к БД
db_client = httpx.AsyncClient(
    base_url=f"{SUPABASE_URL}/rest/v1/",
    headers={
        "apikey": SUPABASE_KEY, 
        "Authorization": f"Bearer {SUPABASE_KEY}", 
        "Content-Type": "application/json"
    }
)

# --- AUTH & ACCOUNT API ---
@app.post("/api/auth/login")
async def api_login(data: dict):
    r = await db_client.get("users", params={
        "email": f"eq.{data['email'].lower()}", 
        "password": f"eq.{data['password']}"
    })
    results = r.json()
    if not results: raise HTTPException(401, "Неверные учетные данные")
    return results[0]

@app.post("/api/auth/request-verification")
async def api_req_verif(data: dict):
    email = data['email'].lower()
    code = str(random.randint(100000, 999999))
    # Сохраняем код в БД с TTL
    await db_client.post("temp_codes", json={
        "email": email, "code": code, 
        "expires_at": int(time.time()*1000) + 600000
    }, headers={"Prefer": "resolution=merge-duplicates"})
    
    # Отправка через Email сервис
    EmailService.send_verification_code(email, code)
    return {"status": "ok"}

@app.post("/api/auth/verify-and-register")
async def api_verify_reg(data: dict):
    email = data['email'].lower()
    # Проверка кода
    r = await db_client.get("temp_codes", params={"email": f"eq.{email}", "code": f"eq.{data['code']}"})
    if not r.json(): raise HTTPException(400, "Неверный код верификации")
    
    new_user_id = f"u_{secrets.token_hex(4)}"
    user_payload = {
        "id": new_user_id, "username": data['username'], 
        "email": email, "password": data['password'], 
        "license_expires_at": int(time.time()*1000) + 259200000 # 3 дня триала
    }
    await db_client.post("users", json=user_payload)
    return user_payload

# --- BOTS MANAGEMENT API ---
@app.get("/api/bots/{user_id}")
async def api_get_bots(user_id: str):
    r = await db_client.get("bots", params={"owner_id": f"eq.{user_id}"})
    raw_bots = r.json() if r.status_code == 200 else []
    # Раскрываем конфиг для удобства фронтенда
    return [{**b, **(b.get("config") or {})} for b in raw_bots]

@app.post("/api/bots/save")
async def api_save_bot(bot: dict):
    bid = bot['id']
    sys_keys = ['id', 'owner_id', 'name', 'token', 'status', 'license_expires_at', 'config']
    # Все, что не системное — уходит в поле config
    config_part = {k: v for k, v in bot.items() if k not in sys_keys}
    
    payload = {
        "id": bid, "owner_id": bot['owner_id'], "name": bot["name"], 
        "token": bot["token"], "status": bot.get("status", "IDLE"), 
        "license_expires_at": int(bot.get("license_expires_at") or 0),
        "config": config_part
    }
    await db_client.post("bots", json=payload, headers={"Prefer": "resolution=merge-duplicates"})
    return {"status": "ok"}

@app.post("/api/bots/start")
async def api_start_bot(req: dict):
    bot_id = req.get('id')
    r = await db_client.get("bots", params={"id": f"eq.{bot_id}"})
    data_list = r.json()
    if not data_list: raise HTTPException(404, "Бот не найден")
    
    bot_data = data_list[0]
    # Формируем полный конфиг
    merged_cfg = {**bot_data, **(bot_data.get("config") or {})}
    
    success = await pm.spawn_bot(bot_id, merged_cfg)
    if success is True:
        await db_client.patch("bots", params={"id": f"eq.{bot_id}"}, json={"status": "RUNNING"})
        return {"status": "ok"}
    else:
        raise HTTPException(500, f"Ошибка запуска: {success}")

@app.post("/api/bots/stop/{bid}")
async def api_stop_bot(bid: str):
    await pm.kill_bot(bid)
    await db_client.patch("bots", params={"id": f"eq.{bid}"}, json={"status": "IDLE"})
    return {"status": "ok"}

@app.get("/api/bots/logs/{bid}")
async def api_get_logs(bid: str):
    return {"logs": pm.fetch_logs(bid)}

@app.get("/api/bots/messages/{bid}")
async def api_get_messages(bid: str):
    r = await db_client.get("bot_messages", params={
        "bot_id": f"eq.{bid}", 
        "order": "created_at.desc", 
        "limit": "60"
    })
    msgs = r.json()
    return [{"text": m["message_text"], "timestamp": m["created_at"], "is_admin": m["is_from_admin"], "user": {"name": m["first_name"]}} for m in msgs][::-1]

# --- BROADCAST API ---
@app.post("/api/bots/broadcast")
async def api_broadcast(data: dict, bg: BackgroundTasks):
    bg.add_task(execute_broadcast, data['botIds'], data['message'])
    return {"status": "queued"}

async def execute_broadcast(bot_ids: List[str], text: str):
    for bid in bot_ids:
        r = await db_client.get("bots", params={"id": f"eq.{bid}"})
        if not r.json(): continue
        bot = r.json()[0]
        users = (bot.get("config") or {}).get("connectedUsers", [])
        
        success, failed = 0, 0
        async with httpx.AsyncClient() as client:
            for u in users:
                if u.get("is_active", True) and not u.get("is_banned"):
                    try:
                        res = await client.post(
                            f"https://api.telegram.org/bot{bot['token']}/sendMessage", 
                            json={"chat_id": u["id"], "text": text, "parse_mode": "HTML"},
                            timeout=8
                        )
                        if res.status_code == 200: success += 1
                        else: failed += 1
                    except: failed += 1
                    
        # Обновляем статистику последнего вещания
        cfg = bot.get("config") or {}
        st = cfg.get("stats", {})
        st["last_broadcast"] = {"success": success, "failed": failed, "at": int(time.time())}
        await db_client.patch("bots", params={"id": f"eq.{bid}"}, json={"config": {**cfg, "stats": st}})

@app.get("/api/ping")
async def api_ping(): return {"status": "online", "time": int(time.time())}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
