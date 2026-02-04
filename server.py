
import asyncio
import logging
import os
import subprocess
import sys
import time
from typing import Dict
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Настройка логов для PM2
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotEngine")

class BotProcessManager:
    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}

    def start_bot(self, bot_id: str, bot_token: str, code: str):
        self.stop_bot(bot_id)
        os.makedirs("active_bots", exist_ok=True)
        filename = f"active_bots/bot_{bot_id}.py"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(code)
        try:
            process = subprocess.Popen([sys.executable, filename])
            self.processes[bot_id] = process
            logger.info(f"🚀 Бот {bot_id} запущен (PID: {process.pid})")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка запуска бота {bot_id}: {e}")
            return False

    def stop_bot(self, bot_id: str):
        if bot_id in self.processes:
            p = self.processes[bot_id]
            p.terminate()
            del self.processes[bot_id]
            logger.info(f"🛑 Бот {bot_id} остановлен")
            return True
        return False

pm = BotProcessManager()

# redirect_slashes=True поможет FastAPI ловить пути и со слешем и без
app = FastAPI(title="BotEngine API", redirect_slashes=True)

@app.middleware("http")
async def log_every_single_request(request: Request, call_next):
    # Это появится в pm2 logs 29
    logger.info(f"📥 Входящий запрос: {request.method} {request.url.path}")
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info(f"📤 Ответ: {response.status_code} (время: {process_time:.4f}s)")
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- РОУТЫ ---

@app.get("/api/ping")
@app.get("/api/ping/")
async def ping():
    return {"status": "online", "server_time": time.time()}

@app.post("/api/auth/login")
@app.post("/api/auth/login/")
async def login(data: dict):
    logger.info(f"Попытка входа: {data.get('email')}")
    return {
        "id": "admin", 
        "username": "Admin", 
        "email": data.get("email"), 
        "balance": 100, 
        "botsCreated": 0, 
        "licenseExpiresAt": int(time.time()*1000) + 86400000
    }

@app.post("/api/auth/request-verification")
@app.post("/api/auth/request-verification/")
async def verify(data: dict):
    email = data.get("email", "unknown")
    logger.info(f"✅ ВЕРИФИКАЦИЯ ВЫЗВАНА для: {email}")
    return {"status": "ok", "message": "Verification simulated"}

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    return []

@app.post("/api/bots/save")
async def save_bot(bot: dict):
    logger.info(f"Сохранение бота: {bot.get('name')}")
    return {"status": "ok"}

@app.post("/api/bots/start")
async def start_bot_endpoint(req: dict):
    # Используем dict для гибкости
    if pm.start_bot(req['id'], req['token'], req['code']):
        return {"status": "ok"}
    raise HTTPException(status_code=500, detail="Start failed")

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot_endpoint(bot_id: str):
    pm.stop_bot(bot_id)
    return {"status": "ok"}

if __name__ == "__main__":
    logger.info("🔥 Сервер запускается на порту 8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
