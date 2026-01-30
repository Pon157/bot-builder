
import asyncio
import logging
import json
import os
import hashlib
import secrets
import time
import sqlite3
import aiosqlite
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, APIRouter, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
import uvicorn
from email_service import EmailService

# --- Конфигурация ---
DB_PATH = "botengine.db"
SECRET_SALT = "bot_engine_pro_ultra_salt_2025"
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("BotEngine")

# --- Модели данных ---
class UserRegister(BaseModel):
    email: EmailStr
    username: str
    password: str
    code: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class VerificationRequest(BaseModel):
    email: EmailStr

class BotStartRequest(BaseModel):
    id: str
    token: str
    code: str

# --- Инициализация БД ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT,
                email TEXT UNIQUE,
                password_hash TEXT,
                balance REAL DEFAULT 0,
                bots_created INTEGER DEFAULT 0,
                license_expires_at INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bots (
                id TEXT PRIMARY KEY,
                owner_id TEXT,
                config TEXT,
                status TEXT DEFAULT 'IDLE'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS verification_codes (
                email TEXT PRIMARY KEY,
                code TEXT,
                expires_at INTEGER
            )
        """)
        await db.commit()

# --- Хелперы ---
def hash_password(password: str) -> str:
    return hashlib.sha256((password + SECRET_SALT).encode()).hexdigest()

# --- Менеджер процессов ---
class BotProcessManager:
    def __init__(self):
        self.processes: Dict[str, asyncio.subprocess.Process] = {}

    async def start_bot(self, bot_id: str, code: str):
        await self.stop_bot(bot_id)
        os.makedirs("active_bots", exist_ok=True)
        filename = f"active_bots/bot_{bot_id}.py"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(code)
        
        try:
            proc = await asyncio.create_subprocess_exec(
                "python3", filename,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            self.processes[bot_id] = proc
            logger.info(f"Bot {bot_id} started with PID {proc.pid}")
            return True
        except Exception as e:
            logger.error(f"Error starting bot {bot_id}: {e}")
            return False

    async def stop_bot(self, bot_id: str):
        if bot_id in self.processes:
            proc = self.processes[bot_id]
            try:
                proc.terminate()
                await proc.wait()
            except:
                proc.kill()
            del self.processes[bot_id]
            return True
        return False

process_manager = BotProcessManager()

# --- FastAPI Setup ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")

@api.get("/ping")
async def ping():
    return {"status": "online", "time": time.time()}

# --- Auth Endpoints ---
@api.post("/auth/request-verification")
async def request_verification(req: VerificationRequest):
    code = "".join([str(secrets.randbelow(10)) for _ in range(6)])
    expires_at = int(time.time()) + 600 # 10 минут
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO verification_codes (email, code, expires_at) VALUES (?, ?, ?)",
            (req.email.lower(), code, expires_at)
        )
        await db.commit()
    
    success = EmailService.send_verification_code(req.email, code)
    if not success:
        raise HTTPException(status_code=500, detail="Ошибка отправки письма. Проверьте настройки SMTP.")
    
    return {"status": "ok"}

@api.post("/auth/verify-and-register")
async def verify_and_register(req: UserRegister):
    async with aiosqlite.connect(DB_PATH) as db:
        # Проверка кода
        async with db.execute(
            "SELECT code, expires_at FROM verification_codes WHERE email = ?", 
            (req.email.lower(),)
        ) as cursor:
            row = await cursor.fetchone()
            if not row or row[0] != req.code or row[1] < time.time():
                raise HTTPException(status_code=400, detail="Неверный или истекший код")

        # Создание пользователя
        user_id = secrets.token_hex(8)
        pass_hash = hash_password(req.password)
        license_expiry = int(time.time()) + (3 * 24 * 3600) # 3 дня триала
        
        try:
            await db.execute(
                "INSERT INTO users (id, username, email, password_hash, license_expires_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, req.username, req.email.lower(), pass_hash, license_expiry)
            )
            await db.execute("DELETE FROM verification_codes WHERE email = ?", (req.email.lower(),))
            await db.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="Email уже зарегистрирован")

        return {
            "id": user_id,
            "username": req.username,
            "email": req.email.lower(),
            "balance": 0,
            "botsCreated": 0,
            "licenseExpiresAt": license_expiry * 1000
        }

@api.post("/auth/login")
async def login(req: UserLogin):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE email = ?", 
            (req.email.lower(),)
        ) as cursor:
            user = await cursor.fetchone()
            if not user or user['password_hash'] != hash_password(req.password):
                raise HTTPException(status_code=401, detail="Неверный Email или пароль")
            
            return {
                "id": user['id'],
                "username": user['username'],
                "email": user['email'],
                "balance": user['balance'],
                "botsCreated": user['bots_created'],
                "licenseExpiresAt": user['license_expires_at'] * 1000
            }

# --- Bots Endpoints ---
@api.get("/bots/{user_id}")
async def get_bots(user_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT config, status FROM bots WHERE owner_id = ?", (user_id,)) as cursor:
            rows = await cursor.fetchall()
            bots = []
            for row in rows:
                bot_cfg = json.loads(row['config'])
                bot_cfg['status'] = row['status']
                bots.append(bot_cfg)
            return bots

@api.post("/bots/save")
async def save_bot(bot: dict):
    owner_id = bot.get("ownerId")
    bot_id = bot.get("id")
    if not owner_id or not bot_id:
        raise HTTPException(status_code=400, detail="Missing IDs")
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO bots (id, owner_id, config, status) VALUES (?, ?, ?, ?)",
            (bot_id, owner_id, json.dumps(bot), bot.get("status", "IDLE"))
        )
        await db.commit()
    return {"status": "ok"}

@api.post("/bots/start")
async def start_bot_endpoint(req: BotStartRequest):
    success = await process_manager.start_bot(req.id, req.code)
    if success:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE bots SET status = 'RUNNING' WHERE id = ?", (req.id,))
            await db.commit()
        return {"status": "ok"}
    raise HTTPException(status_code=500, detail="Failed to start bot process")

@api.post("/bots/stop/{bot_id}")
async def stop_bot_endpoint(bot_id: str):
    await process_manager.stop_bot(bot_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE bots SET status = 'IDLE' WHERE id = ?", (bot_id,))
        await db.commit()
    return {"status": "ok"}

app.include_router(api)

if __name__ == "__main__":
    asyncio.run(init_db())
    uvicorn.run(app, host="0.0.0.0", port=8000)
