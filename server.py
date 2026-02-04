
import asyncio
import logging
import os
import subprocess
import sys
import time
import json
import random
import httpx
import secrets
from typing import Dict, List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- Конфигурация ---
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

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotEngineServer")

SB_URL = os.getenv("SUPABASE_URL")
SB_KEY = os.getenv("SUPABASE_KEY")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")

# --- Генератор кода (теперь внутри сервера для надежности) ---
def generate_bot_script(config: dict) -> str:
    config_json = json.dumps(config, ensure_ascii=False, indent=2)
    return f"""#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, json, subprocess, sys

# Инъекция переменных окружения
os.environ['SUPABASE_URL'] = {repr(SB_URL)}
os.environ['SUPABASE_KEY'] = {repr(SB_KEY)}

CONFIG = {config_json}

def main():
    bot_id = CONFIG.get('id', 'unknown')
    config_path = os.path.join(os.getcwd(), f"config_{{bot_id}}.json")
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(CONFIG, f, ensure_ascii=False, indent=2)
        
        # Запуск ядра bot_core.py в той же папке
        process = subprocess.run(
            [sys.executable, "bot_core.py", config_path],
            env=os.environ.copy(),
            check=False
        )
    except Exception as e:
        print(f"Error: {{e}}")
    finally:
        if os.path.exists(config_path): os.remove(config_path)

if __name__ == "__main__":
    main()
"""

class BotProcessManager:
    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}

    def start_bot(self, bot_id: str, config: dict):
        self.stop_bot(bot_id)
        os.makedirs("active_bots", exist_ok=True)
        filename = f"active_bots/bot_{bot_id}.py"
        
        code = generate_bot_script(config)
        with open(filename, "w", encoding="utf-8") as f:
            f.write(code)
        
        try:
            env = os.environ.copy()
            # Убеждаемся что PYTHONPATH включает текущую директорию для импорта bot_core
            env["PYTHONPATH"] = os.getcwd()
            
            log_file = open(f"active_bots/bot_{bot_id}.log", "a", encoding="utf-8")
            process = subprocess.Popen(
                [sys.executable, filename],
                env=env, cwd=os.getcwd(),
                stdout=log_file, stderr=log_file
            )
            self.processes[bot_id] = process
            logger.info(f"🚀 Бот {bot_id} запущен (PID: {process.pid})")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка запуска {bot_id}: {e}")
            return False

    def stop_bot(self, bot_id: str):
        if bot_id in self.processes:
            p = self.processes[bot_id]
            logger.info(f"🛑 Останавливаю бота {bot_id}...")
            p.terminate()
            try: p.wait(timeout=5)
            except: p.kill()
            del self.processes[bot_id]
            return True
        return False

pm = BotProcessManager()

# --- FastAPI Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: запуск мониторинга и восстановление ботов
    asyncio.create_task(health_monitor())
    await restore_active_bots()
    yield
    # Shutdown: корректное завершение всех процессов
    for bid in list(pm.processes.keys()):
        pm.stop_bot(bid)

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

db = httpx.AsyncClient(
    base_url=f"{SB_URL.rstrip('/')}/rest/v1/",
    headers={"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}", "Content-Type": "application/json"},
    timeout=30
)

async def health_monitor():
    """Фоновая проверка падения процессов"""
    while True:
        await asyncio.sleep(60)
        for bid, proc in list(pm.processes.items()):
            if proc.poll() is not None:
                logger.warning(f"⚠️ Бот {bid} упал (Exit Code: {proc.returncode}). Статус: ERROR")
                del pm.processes[bid]
                await db.patch("bots", params={"id": f"eq.{bid}"}, json={"status": "ERROR"})

async def restore_active_bots():
    """Восстановление ботов, которые были в статусе RUNNING"""
    logger.info("🛠 Начинаю восстановление активных инстансов из БД...")
    try:
        res = await db.get("bots", params={"status": "eq.RUNNING"})
        if res.status_code == 200:
            for b in res.json():
                # Проверяем лицензию
                if int(b.get("license_expires_at", 0)) > int(time.time() * 1000):
                    config = {**b, **(b.get("config") or {})}
                    pm.start_bot(b["id"], config)
            logger.info(f"✅ Восстановлено ботов: {len(pm.processes)}")
    except Exception as e:
        logger.error(f"❌ Ошибка восстановления: {e}")

# --- API Эндпоинты ---

@app.post("/api/auth/login")
async def login(data: dict):
    email = data.get("email", "").lower().strip()
    password = data.get("password", "")
    res = await db.get("users", params={"email": f"eq.{email}", "password": f"eq.{password}"})
    if res.status_code != 200 or not res.json(): raise HTTPException(401, "Неверный логин или пароль")
    return res.json()[0]

@app.get("/api/bots/{user_id}")
async def get_user_bots(user_id: str):
    res = await db.get("bots", params={"owner_id": f"eq.{user_id}"})
    if res.status_code != 200: return []
    # Синхронизируем статус с реально запущенными процессами
    bots = res.json()
    for b in bots:
        if b['id'] in pm.processes: b['status'] = "RUNNING"
        elif b['status'] == "RUNNING": b['status'] = "IDLE" # Если в БД RUNNING но процесса нет
    return [{**b, **(b.get("config") or {})} for b in bots]

@app.post("/api/bots/save")
async def save_bot(bot: dict):
    # Поля, которые идут в JSONB конфиг
    config_fields = ["description", "adminChatId", "welcomeMessage", "triggers", "buttons", "settings", "connectedUsers", "subscribers", "stats"]
    config = {k: bot.get(k) for k in config_fields if k in bot}
    
    payload = {
        "id": bot["id"], "owner_id": bot["ownerId"], "name": bot["name"], "token": bot["token"],
        "status": bot.get("status", "IDLE"), 
        "license_expires_at": int(bot.get("licenseExpiresAt", 0)),
        "config": config
    }
    res = await db.post("bots", json=payload, headers={"Prefer": "resolution=merge-duplicates"})
    if res.status_code >= 400: raise HTTPException(500, f"Ошибка БД: {res.text}")
    return {"status": "ok"}

@app.post("/api/bots/start")
async def start_bot_endpoint(req: dict):
    bot_id = req.get('id')
    # Получаем актуальный конфиг из БД
    res = await db.get("bots", params={"id": f"eq.{bot_id}"})
    if res.status_code != 200 or not res.json(): raise HTTPException(404, "Бот не найден")
    
    bot_data = res.json()[0]
    config = {**bot_data, **(bot_data.get("config") or {})}
    
    if pm.start_bot(bot_id, config):
        await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"status": "RUNNING"})
        return {"status": "ok"}
    raise HTTPException(500, "Ошибка при запуске процесса")

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot_endpoint(bot_id: str):
    pm.stop_bot(bot_id)
    await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"status": "IDLE"})
    return {"status": "ok"}

@app.post("/api/bots/broadcast")
async def broadcast_endpoint(req: dict):
    bot_ids = req.get('botIds', [])
    message_text = req.get('message', '')
    if not message_text: return {"success": 0, "failed": 0}

    async def send_to_bot(bid):
        res = await db.get("bots", params={"id": f"eq.{bid}"})
        if res.status_code != 200 or not res.json(): return 0, 0
        bot = res.json()[0]
        token = bot['token']
        # Берем список подписчиков
        subscribers = (bot.get('config') or {}).get('subscribers', [])
        
        success, failed = 0, 0
        async with httpx.AsyncClient() as client:
            # ТГ позволяет 30 сообщений в секунду
            for i in range(0, len(subscribers), 30):
                chunk = subscribers[i:i+30]
                tasks = []
                for uid in chunk:
                    url = f"https://api.telegram.org/bot{token}/sendMessage"
                    tasks.append(client.post(url, json={"chat_id": uid, "text": message_text, "parse_mode": "HTML"}))
                
                responses = await asyncio.gather(*tasks, return_exceptions=True)
                for r in responses:
                    if isinstance(r, httpx.Response) and r.status_code == 200: success += 1
                    else: failed += 1
                await asyncio.sleep(1)
        return success, failed

    bot_tasks = [send_to_bot(bid) for bid in bot_ids]
    results = await asyncio.gather(*bot_tasks)
    
    total_s, total_f = sum(r[0] for r in results), sum(r[1] for r in results)
    return {"success": total_s, "failed": total_f}

@app.post("/api/admin/generate-key")
async def generate_key_endpoint(req: dict, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET: raise HTTPException(403, "Forbidden")
    months = req.get("months", 1)
    key = f"BOT-{months}-{secrets.token_hex(4).upper()}"
    await db.post("issued_keys", json={"key": key, "months": months, "used": False})
    return {"key": key}

@app.get("/api/bots/messages/{bot_id}")
async def get_messages(bot_id: str):
    res = await db.get("bot_messages", params={"bot_id": f"eq.{bot_id}", "order": "created_at.desc", "limit": "50"})
    if res.status_code != 200: return []
    # Форматируем для фронтенда
    messages = []
    for m in res.json():
        messages.append({
            "user": {"id": m["user_id"], "name": m["first_name"]},
            "text": m["message_text"],
            "timestamp": m["created_at"],
            "is_admin": m["is_from_admin"]
        })
    return messages

@app.get("/api/ping")
async def ping():
    return {"status": "online", "active_bots": len(pm.processes)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
