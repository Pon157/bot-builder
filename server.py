
import asyncio
import logging
import json
import os
import time
import sys
import secrets
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException, Header, Request, Depends, Response, status, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

# --- Инициализация логирования ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotEngineCore")

# --- Попытка импорта Supabase ---
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logger.warning("Supabase library not found. Running in demo mode.")

# --- БД и Константы ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Optional['Client'] = None
if SUPABASE_AVAILABLE and SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("✅ Supabase connected successfully")
    except Exception as e:
        logger.error(f"❌ Supabase initialization error: {e}")

# --- Модели данных ---
class LoginRequest(BaseModel):
    email: str
    password: str

class VerificationRequest(BaseModel):
    email: str

class RegisterWithCodeRequest(BaseModel):
    email: str
    code: str
    password: str
    username: str

# --- Жизненный цикл приложения ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Логика при старте (например, прогрев кэша)
    logger.info("Application startup...")
    yield
    # Логика при завершении
    logger.info("Application shutdown...")

# --- Инициализация FastAPI ---
app = FastAPI(lifespan=lifespan, redirect_slashes=False)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API Роутер ---
api_router = APIRouter(prefix="/api")

@api_router.get("/ping")
async def ping():
    return {"status": "online", "timestamp": time.time()}

@api_router.post("/auth/login")
async def login(req: LoginRequest):
    email = req.email.lower().strip()
    if supabase:
        try:
            res = supabase.table("users").select("*").eq("email", email).eq("password", req.password).execute()
            if res.data:
                return res.data[0]
            raise HTTPException(401, "Неверный логин или пароль")
        except Exception as e:
            logger.error(f"Login error: {e}")
            raise HTTPException(500, "Ошибка базы данных")
    
    # Демо-режим, если нет БД
    if email == "admin@test.com" and req.password == "admin":
        return {"id": "demo_user", "username": "Admin", "email": email, "balance": 100}
    raise HTTPException(401, "Пользователь не найден (Demo Mode: admin@test.com / admin)")

@api_router.post("/auth/request-verification")
async def request_verification(req: VerificationRequest):
    email = req.email.lower().strip()
    logger.info(f"Verification requested for: {email}")
    # В реальности здесь отправка письма через email_service.py
    return {"status": "ok", "message": "Код отправлен (имитация)"}

@api_router.get("/bots/{user_id}")
async def get_bots(user_id: str):
    if supabase:
        try:
            res = supabase.table("bots").select("*").eq("ownerId", user_id).execute()
            return res.data or []
        except Exception as e:
            logger.error(f"Get bots error: {e}")
            return []
    return []

@api_router.post("/bots/save")
async def save_bot(bot: dict):
    if supabase:
        try:
            supabase.table("bots").upsert(bot).execute()
            return {"status": "ok"}
        except Exception as e:
            logger.error(f"Save bot error: {e}")
            raise HTTPException(500, "Ошибка сохранения")
    return {"status": "ok"}

@api_router.post("/bots/start")
async def start_bot(bot: dict):
    bot_id = bot.get("id")
    logger.info(f"Starting bot: {bot_id}")
    return {"status": "ok"}

@api_router.post("/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    logger.info(f"Stopping bot: {bot_id}")
    return {"status": "ok"}

@api_router.get("/bots/messages/{bot_id}")
async def get_bot_messages(bot_id: str):
    return []

# Подключаем роутер
app.include_router(api_router)

# Обработка исключений для чистого вывода в логи
@app.exception_handler(Exception)
async def universal_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутренняя ошибка сервера"}
    )

if __name__ == "__main__":
    # Запуск сервера
    uvicorn.run(app, host="0.0.0.0", port=8000)
