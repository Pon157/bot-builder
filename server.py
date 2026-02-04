
import asyncio
import logging
import json
import os
import signal
import subprocess
import sys
import time
import secrets
from contextlib import asynccontextmanager
from typing import Dict, Optional, List
from fastapi import FastAPI, HTTPException, APIRouter, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# --- Настройка логирования ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotEngine")

# --- Менеджер процессов ботов ---
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
            process = subprocess.Popen(
                [sys.executable, filename],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            self.processes[bot_id] = process
            logger.info(f"Bot {bot_id} started (PID: {process.pid})")
            return True
        except Exception as e:
            logger.error(f"Failed to start bot {bot_id}: {e}")
            return False

    def stop_bot(self, bot_id: str):
        if bot_id in self.processes:
            process = self.processes[bot_id]
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            del self.processes[bot_id]
            logger.info(f"Bot {bot_id} stopped")
            return True
        return False

    def stop_all(self):
        for bot_id in list(self.processes.keys()):
            self.stop_bot(bot_id)

process_manager = BotProcessManager()

# --- Модели данных ---
class BotStartRequest(BaseModel):
    id: str
    token: str
    code: str

class BroadcastRequest(BaseModel):
    botIds: List[str]
    message: str

class LicenseRequest(BaseModel):
    botId: str
    key: str

class KeyGenRequest(BaseModel):
    months: int

# --- FastAPI Setup ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Backend initialized")
    yield
    process_manager.stop_all()

# Важно: redirect_slashes=False помогает избежать 405 ошибок при проксировании
app = FastAPI(lifespan=lifespan, redirect_slashes=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix="/api")

@api_router.get("/ping")
async def ping():
    return {"status": "online", "time": time.time()}

@api_router.post("/auth/login")
async def login(data: dict):
    return {"id": "admin_user", "username": "Admin", "email": data.get("email"), "balance": 100, "botsCreated": 0, "licenseExpiresAt": int(time.time() * 1000) + 86400000}

@api_router.post("/auth/request-verification")
async def verify(data: dict):
    return {"status": "ok"}

@api_router.get("/bots/{user_id}")
async def get_bots(user_id: str):
    return []

@api_router.post("/bots/save")
async def save_bot(bot: dict):
    return {"status": "ok"}

@api_router.delete("/bots/{user_id}/{bot_id}")
async def delete_bot(user_id: str, bot_id: str):
    process_manager.stop_bot(bot_id)
    logger.info(f"Deleting bot {bot_id} for user {user_id}")
    return {"status": "ok"}

@api_router.post("/bots/start")
async def start_bot(req: BotStartRequest):
    success = process_manager.start_bot(req.id, req.token, req.code)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to start bot process")
    return {"status": "ok"}

@api_router.post("/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    process_manager.stop_bot(bot_id)
    return {"status": "ok"}

@api_router.post("/bots/broadcast")
async def broadcast(req: BroadcastRequest):
    logger.info(f"Broadcast to {len(req.botIds)} bots: {req.message[:20]}...")
    return {"success": len(req.botIds), "failed": 0}

@api_router.get("/bots/messages/{bot_id}")
async def get_messages(bot_id: str):
    # Демо-данные для чата
    return [
        {"user": {"id": "12345", "name": "Test User"}, "text": "Hello! I need help.", "timestamp": int(time.time() * 1000)}
    ]

@api_router.post("/license/activate")
async def activate_license(req: LicenseRequest):
    logger.info(f"Activating license for {req.botId} with key {req.key}")
    # Продлеваем на 30 дней от текущего момента
    new_expiry = int(time.time() * 1000) + (30 * 24 * 3600 * 1000)
    return {"status": "ok", "newExpiry": new_expiry}

# Эндпоинт для license_bot.py
@api_router.post("/admin/generate-key")
async def gen_key(req: KeyGenRequest, x_admin_token: str = Header(None)):
    admin_secret = os.getenv("ADMIN_SECRET", "MRAKOTIK")
    if x_admin_token != admin_secret:
        raise HTTPException(status_code=403, detail="Forbidden")
    new_key = f"BOT-{req.months}-{secrets.token_hex(4).upper()}"
    return {"key": new_key}

app.include_router(api_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
