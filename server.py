
import asyncio
import logging
import os
import subprocess
import sys
import time
import secrets
from typing import Dict, List
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Настройка логов
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("BotEngine")

# Менеджер процессов
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
            logger.info(f"Bot {bot_id} started (PID: {process.pid})")
            return True
        except Exception as e:
            logger.error(f"Failed to start bot {bot_id}: {e}")
            return False

    def stop_bot(self, bot_id: str):
        if bot_id in self.processes:
            p = self.processes[bot_id]
            p.terminate()
            del self.processes[bot_id]
            return True
        return False

    def stop_all(self):
        for bid in list(self.processes.keys()): self.stop_bot(bid)

pm = BotProcessManager()

# FastAPI
app = FastAPI(title="BotEngine API")

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

# --- Эндпоинты (Прямо в app для избежания проблем с роутером) ---

@app.get("/api/ping")
async def ping():
    return {"status": "online"}

@app.post("/api/auth/login")
async def login(data: dict):
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
    logger.info(f"Verification requested for: {data.get('email')}")
    return {"status": "ok"}

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
    raise HTTPException(status_code=500, detail="Start failed")

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    pm.stop_bot(bot_id)
    return {"status": "ok"}

@app.delete("/api/bots/{user_id}/{bot_id}")
async def delete_bot(user_id: str, bot_id: str):
    pm.stop_bot(bot_id)
    return {"status": "ok"}

@app.post("/api/license/activate")
async def activate(data: dict):
    return {"status": "ok", "newExpiry": int(time.time()*1000) + 2592000000}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
