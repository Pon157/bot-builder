
import asyncio
import logging
import json
import os
import time
import re
import uuid
import secrets
import sys
import httpx
import random
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any, Union

from fastapi import FastAPI, HTTPException, Header, Request, Depends, APIRouter, status, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ParseMode, ContentType
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, ErrorEvent
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

import uvicorn
from email_service import EmailService

# --- CONFIG & LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(name)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotEngineCore")

def load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip().strip('"').strip("'")

load_env()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")

# --- DATABASE LAYER ---
class SupabaseDB:
    def __init__(self, url: str, key: str):
        self.url = url
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

    async def query(self, table: str, method: str = "GET", params: dict = None, json_data: dict = None):
        async with httpx.AsyncClient() as client:
            url = f"{self.url}/rest/v1/{table}"
            headers = self.headers.copy()
            if method == "POST" and params and "on_conflict" in params:
                headers["Prefer"] = "resolution=merge-duplicates,return=representation"
            try:
                resp = await client.request(method, url, params=params, json=json_data, headers=headers)
                if resp.status_code >= 400:
                    logger.error(f"Supabase Error ({resp.status_code}) on {table}: {resp.text}")
                    return []
                return resp.json() if resp.status_code != 204 else []
            except Exception as e:
                logger.error(f"Database connection error: {e}")
                return []

db = SupabaseDB(SUPABASE_URL, SUPABASE_KEY)

# --- GLOBAL STATE ---
active_tasks: Dict[str, asyncio.Task] = {}
active_bots: Dict[str, Bot] = {}
bot_configs: Dict[str, dict] = {}
pending_verifications: Dict[str, dict] = {} 
pending_resets: Dict[str, dict] = {}

# --- UTILS ---
def is_active_license(expiry: Any) -> bool:
    try:
        return int(expiry or 0) > int(time.time() * 1000)
    except:
        return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Восстановление активных ботов
    rows = await db.query("bots", params={"status": "eq.RUNNING"})
    for b in rows:
        if is_active_license(b.get('license_expires_at')):
            # Здесь должна быть логика запуска воркера
            pass
    yield
    for t in active_tasks.values(): t.cancel()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")

@api.get("/ping")
async def ping(): return {"status": "online", "time": int(time.time())}

# AUTH
@api.post("/auth/login")
async def login_api(req: dict):
    email, password = req.get('email', '').strip().lower(), req.get('password', '')
    res = await db.query("users", params={"email": f"eq.{email}", "password": f"eq.{password}"})
    if not res: raise HTTPException(401, "Неверные данные")
    return res[0]

@api.post("/auth/verify-request")
async def verify_req(req: dict):
    email = req.get("email", "").lower().strip()
    code = str(random.randint(100000, 999999))
    if EmailService.send_verification_code(email, code):
        pending_verifications[email] = {"code": code, "time": time.time()}
        return {"status": "ok"}
    raise HTTPException(500, "Email Error")

@api.post("/auth/register")
async def register_api(req: dict):
    email, code = req.get("email", "").lower().strip(), req.get("code")
    if email not in pending_verifications or pending_verifications[email]["code"] != code:
        raise HTTPException(400, "Код неверен")
    
    payload = {
        "id": str(uuid.uuid4()), "email": email, "username": req.get("username"),
        "password": req.get("password"), "balance": 0, "botsCreated": 0,
        "licenseExpiresAt": int(time.time()*1000) + (3 * 24 * 3600 * 1000)
    }
    await db.query("users", method="POST", json_data=payload)
    del pending_verifications[email]
    return payload

# BOTS
@api.get("/bots/{user_id}")
async def get_user_bots(user_id: str):
    rows = await db.query("bots", params={"owner_id": f"eq.{user_id}"})
    return rows

@api.post("/bots/save")
async def save_bot_api(data: dict):
    bid = data['id']
    await db.query("bots", method="POST", json_data=data, params={"on_conflict": "id"})
    return {"status": "ok"}

@api.post("/bots/start/{bot_id}")
async def start_bot_api(bot_id: str):
    return {"status": "ok"}

@api.post("/bots/stop/{bot_id}")
async def stop_bot_api(bot_id: str):
    return {"status": "ok"}

@api.delete("/bots/delete/{bot_id}")
async def del_bot_api(bot_id: str):
    await db.query("bots", method="DELETE", params={"id": f"eq.{bot_id}"})
    return {"status": "ok"}

app.include_router(api)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
