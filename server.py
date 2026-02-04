
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

# Настройка логов
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("BotEngine")

# Менеджер процессов ботов
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
            # Запускаем в новом процессе
            process = subprocess.Popen([sys.executable, filename])
            self.processes[bot_id] = process
            logger.info(f"Bot {bot_id} started (PID: {process.pid})")
            return True
        except Exception as e:
            logger.error(f"Failed to start bot {bot_id}: {e}")
            return False

    def stop_bot(self, bot_id: str):
        if bot_id in self.processes:
            p = self.processes[bot_id]
            p.terminate()
            try:
                p.wait(timeout=5)
            except:
                p.kill()
            del self.processes[bot_id]
            logger.info(f"Bot {bot_id} stopped")
            return True
        return False

    def stop_all(self):
        for bid in list(self.processes.keys()): self.stop_bot(bid)

pm = BotProcessManager()

# Инициализация FastAPI с отключенными редиректами
app = FastAPI(title="BotEngine API", redirect_slashes=False)

# Middleware для отладки: выводит все запросы в консоль PM2
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Incoming request: {request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"Response status: {response.status_code}")
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Модели
class BotStartReq(BaseModel):
    id: str
    token: str
    code: str

# --- ЭНДПОИНТЫ ---

@app.get("/api/ping")
async def ping():
    return {"status": "online", "timestamp": time.time()}

@app.post("/api/auth/login")
async def login(data: dict):
    # Демо-вход
    return {
        "id": "admin", 
        "username": "Admin", 
        "email": data.get("email"), 
        "balance": 100, 
        "botsCreated": 0, 
        "licenseExpiresAt": int(time.time()*1000) + 86400000
    }

@app.post("/api/auth/request-verification")
async def verify(data: dict):
    email = data.get("email", "unknown")
    logger.info(f"!!! Verification hit !!! Email: {email}")
    return {"status": "ok", "message": "Code sent (simulated)"}

@app.get("/api/bots/{user_id}")
async def get_bots(user_id: str):
    return []

@app.post("/api/bots/save")
async def save_bot(bot: dict):
    return {"status": "ok"}

@app.post("/api/bots/start")
async def start_bot(req: BotStartReq):
    if pm.start_bot(req.id, req.token, req.code):
        return {"status": "ok"}
    raise HTTPException(status_code=500, detail="Failed to start bot process")

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot_endpoint(bot_id: str):
    pm.stop_bot(bot_id)
    return {"status": "ok"}

@app.delete("/api/bots/{user_id}/{bot_id}")
async def delete_bot(user_id: str, bot_id: str):
    pm.stop_bot(bot_id)
    return {"status": "ok"}

@app.post("/api/license/activate")
async def activate_lic(data: dict):
    return {"status": "ok", "newExpiry": int(time.time()*1000) + 2592000000}

# Эндпоинт для генерации ключей (вызывается из license_bot.py)
@app.post("/api/admin/generate-key")
async def gen_key(data: dict, x_admin_token: str = Header(None)):
    if x_admin_token != "MRAKOTIK":
        raise HTTPException(status_code=403)
    return {"key": f"KEY-{int(time.time())}"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
