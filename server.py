
import asyncio
import logging
import json
import os
import signal
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from typing import Dict, Optional
from fastapi import FastAPI, HTTPException, APIRouter
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
        
        # Создаем директорию для ботов, если её нет
        os.makedirs("active_bots", exist_ok=True)
        filename = f"active_bots/bot_{bot_id}.py"
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(code)
        
        # Запускаем бота как отдельный процесс
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

# --- FastAPI Setup ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Backend is starting...")
    yield
    logger.info("Shutting down: stopping all bots...")
    process_manager.stop_all()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Модели ---
class BotStartRequest(BaseModel):
    id: str
    token: str
    code: str  # Фронтенд присылает сгенерированный код

# --- API Роутер ---
api_router = APIRouter(prefix="/api")

@api_router.get("/ping")
async def ping():
    return {"status": "online", "time": time.time()}

@api_router.post("/auth/login")
async def login(data: dict):
    # Упрощенная авторизация для дебага
    email = data.get("email")
    return {"id": "admin_user", "username": "Admin", "email": email, "balance": 100}

@api_router.get("/bots/{user_id}")
async def get_bots(user_id: str):
    # Здесь должна быть работа с БД, пока возвращаем пустой список
    return []

@api_router.post("/bots/save")
async def save_bot(bot: dict):
    return {"status": "ok"}

@api_router.post("/bots/start")
async def start_bot(req: BotStartRequest):
    # Код генерируется на фронтенде и присылается сюда
    success = process_manager.start_bot(req.id, req.token, req.code)
    if not success:
        raise HTTPException(status_code=500, detail="Could not start bot process")
    return {"status": "ok"}

@api_router.post("/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    process_manager.stop_bot(bot_id)
    return {"status": "ok"}

app.include_router(api_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
