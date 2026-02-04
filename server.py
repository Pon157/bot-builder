
import asyncio
import logging
import os
import subprocess
import sys
import time
import json
import random
import httpx
import signal
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request, Header, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# --- Инициализация окружения ---
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

if not SB_URL or not SB_KEY:
    logger.error("❌ КРИТИЧЕСКАЯ ОШИБКА: SUPABASE_URL или SUPABASE_KEY не найдены!")

# --- Профессиональный менеджер процессов ---
class BotProcessManager:
    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}
        self.bot_configs: Dict[str, dict] = {}

    def start_bot(self, bot_id: str, code: str, config: dict = None):
        """Запуск инстанса бота с мониторингом"""
        self.stop_bot(bot_id)
        os.makedirs("active_bots", exist_ok=True)
        filename = f"active_bots/bot_{bot_id}.py"
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(code)
        
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = os.getcwd()
            
            # Логирование в файл для дебага
            log_file = open(f"active_bots/bot_{bot_id}.log", "a", encoding="utf-8")
            
            process = subprocess.Popen(
                [sys.executable, filename],
                env=env,
                cwd=os.getcwd(),
                stdout=log_file,
                stderr=log_file
            )
            
            self.processes[bot_id] = process
            if config: self.bot_configs[bot_id] = config
            
            logger.info(f"🚀 Бот {bot_id} успешно запущен (PID: {process.pid})")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка при запуске бота {bot_id}: {str(e)}")
            return False

    def stop_bot(self, bot_id: str):
        """Безопасная остановка процесса"""
        if bot_id in self.processes:
            p = self.processes[bot_id]
            logger.info(f"🛑 Останавливаю бота {bot_id}...")
            try:
                p.terminate()
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
            except Exception as e:
                logger.error(f"Ошибка при убийстве процесса {bot_id}: {e}")
            
            if bot_id in self.processes: del self.processes[bot_id]
            return True
        return False

    async def health_check_loop(self, db_client: httpx.AsyncClient):
        """Фоновая проверка: живы ли боты?"""
        while True:
            await asyncio.sleep(60) # Проверка раз в минуту
            dead_bots = []
            for bid, proc in self.processes.items():
                if proc.poll() is not None: # Если процесс завершился
                    logger.warning(f"⚠️ Обнаружено падение бота {bid}! Код выхода: {proc.returncode}")
                    dead_bots.append(bid)
            
            for bid in dead_bots:
                del self.processes[bid]
                try:
                    await db_client.patch("bots", params={"id": f"eq.{bid}"}, json={"status": "ERROR"})
                except: pass

pm = BotProcessManager()
app = FastAPI(title="BotEngine Pro API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Supabase Client
db = httpx.AsyncClient(
    base_url=f"{SB_URL.rstrip('/')}/rest/v1/",
    headers={
        "apikey": SB_KEY, 
        "Authorization": f"Bearer {SB_KEY}", 
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    },
    timeout=30
)

# --- Инициализация сервера ---
@app.on_event("startup")
async def startup_event():
    # 1. Запускаем цикл проверки здоровья
    asyncio.create_task(pm.health_check_loop(db))
    
    # 2. Авто-восстановление ботов
    logger.info("🛠 Начинаю восстановление активных инстансов...")
    try:
        res = await db.get("bots", params={"status": "eq.RUNNING"})
        if res.status_code == 200:
            running_bots = res.json()
            for bot_data in running_bots:
                # Генерируем код для запуска (через наш сервис генерации)
                # В реальности тут нужно дернуть генератор, но для примера мы просто
                # предполагаем, что файлы уже могут быть или мы их пересоздаем.
                # Для полноценного восстановления нам нужно хранить 'last_code' или генерировать его заново.
                from services.pythonGenerator import generatePythonCode
                config = {**bot_data, **(bot_data.get('config') or {})}
                code = generatePythonCode(config)
                pm.start_bot(bot_data['id'], code)
            logger.info(f"✅ Восстановлено ботов: {len(running_bots)}")
    except Exception as e:
        logger.error(f"❌ Ошибка при восстановлении: {e}")

# --- API Эндпоинты ---

@app.post("/api/auth/login")
async def login(data: dict):
    email = data.get("email", "").lower().strip()
    password = data.get("password", "")
    res = await db.get("users", params={"email": f"eq.{email}", "password": f"eq.{password}"})
    if res.status_code != 200 or not res.json():
        raise HTTPException(401, "Доступ запрещен: неверные данные")
    u = res.json()[0]
    return {
        "id": u["id"], "username": u["username"], "email": u["email"],
        "balance": u.get("balance", 0), "licenseExpiresAt": u.get("license_expires_at", 0)
    }

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    res = await db.get("bots", params={"owner_id": f"eq.{user_id}"})
    if res.status_code != 200: return []
    return [{**b, **(b.get("config") or {})} for b in res.json()]

@app.post("/api/bots/save")
async def save_bot(bot: dict):
    config_fields = ["description", "adminChatId", "welcomeMessage", "triggers", "buttons", "settings", "connectedUsers"]
    payload = {
        "id": bot["id"], "owner_id": bot["ownerId"], "name": bot["name"], "token": bot["token"],
        "status": bot.get("status", "IDLE"), 
        "license_expires_at": int(bot.get("licenseExpiresAt", 0)),
        "config": {k: bot.get(k) for k in config_fields if k in bot}
    }
    # Использование UPSERT через header Supabase
    res = await db.post("bots", json=payload, headers={"Prefer": "resolution=merge-duplicates"})
    if res.status_code >= 400: raise HTTPException(500, f"DB Error: {res.text}")
    return {"status": "ok"}

@app.post("/api/bots/start")
async def start_bot(req: dict):
    bot_id = req.get('id')
    code = req.get('code')
    if pm.start_bot(bot_id, code):
        await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"status": "RUNNING"})
        return {"status": "ok"}
    raise HTTPException(500, "Не удалось запустить процесс бота")

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    pm.stop_bot(bot_id)
    await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"status": "IDLE"})
    return {"status": "ok"}

@app.post("/api/bots/broadcast")
async def broadcast_message(req: dict):
    bot_ids = req.get('botIds', [])
    message_text = req.get('message', '')
    if not message_text: return {"success": 0, "failed": 0}

    async def send_to_bot(bid):
        res = await db.get("bots", params={"id": f"eq.{bid}"})
        if res.status_code != 200 or not res.json(): return 0, 0
        bot = res.json()[0]
        token = bot['token']
        users = (bot.get('config') or {}).get('connectedUsers', [])
        
        success, failed = 0, 0
        async with httpx.AsyncClient() as client:
            # Отправка пачками по 30 чел (лимиты ТГ)
            for i in range(0, len(users), 30):
                chunk = users[i:i+30]
                tasks = []
                for u in chunk:
                    if not u.get('is_banned') and u.get('is_active'):
                        url = f"https://api.telegram.org/bot{token}/sendMessage"
                        tasks.append(client.post(url, json={"chat_id": u['id'], "text": message_text, "parse_mode": "HTML"}))
                
                responses = await asyncio.gather(*tasks, return_exceptions=True)
                for r in responses:
                    if isinstance(r, httpx.Response) and r.status_code == 200: success += 1
                    else: failed += 1
                await asyncio.sleep(1) # Пауза между пачками
        return success, failed

    total_s, total_f = 0, 0
    # Выполняем рассылку для всех ботов параллельно
    bot_tasks = [send_to_bot(bid) for bid in bot_ids]
    results = await asyncio.gather(*bot_tasks)
    
    for s, f in results:
        total_s += s
        total_f += f
        
    return {"success": total_s, "failed": total_f}

@app.get("/api/ping")
async def ping():
    return {"status": "online", "active_processes": len(pm.processes)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
