
import asyncio
import logging
import json
import os
import time
import re
import uuid
import secrets
import sys
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException, Header, Request, Depends, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

# --- Инициализация окружения ---
def manual_load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8-sig') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and value:
                        os.environ[key] = value
            return True
        except Exception as e:
            print(f"Error loading .env: {e}")
    return False

manual_load_env()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotEngineCore")

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

from email_service import EmailService

# --- Константы и БД ---
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Optional['Client'] = None
if SUPABASE_AVAILABLE and SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("✅ Supabase connected")
    except Exception as e:
        logger.error(f"❌ Supabase init error: {e}")

verification_codes: Dict[str, dict] = {}
db_content = {"users": [], "bots": [], "issued_keys": []}

# --- Модели ---
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

# --- Жизненный цикл ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Первоначальная загрузка данных
    if supabase:
        try:
            users = supabase.table("users").select("*").execute()
            bots = supabase.table("bots").select("*").execute()
            db_content["users"] = users.data or []
            db_content["bots"] = bots.data or []
            logger.info(f"💾 Data loaded: {len(db_content['users'])} users")
        except Exception as e:
            logger.error(f"❌ Initial load error: {e}")
    yield

# --- Инициализация App ---
app = FastAPI(lifespan=lifespan)

# Настройка CORS: Важно, чтобы CORSMiddleware был настроен корректно для обработки OPTIONS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Глобальный обработчик ошибок валидации (помогает отловить 422)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"❌ Validation Error: {exc.errors()} | Body: {await request.body()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "message": "Ошибка валидации данных"},
    )

# Middleware для логирования запросов
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    logger.info(f"Incoming: {request.method} {request.url.path}")
    response = await call_next(request)
    duration = (time.time() - start_time) * 1000
    logger.info(f"Completed: {request.method} {request.url.path} | Status: {response.status_code} | {duration:.2f}ms")
    return response

# --- Роуты ---

@app.get("/api/ping")
@app.get("/api/ping/")
async def ping():
    return {"status": "online", "timestamp": time.time()}

@app.post("/api/auth/login")
@app.post("/api/auth/login/")
async def login(req: LoginRequest):
    email = req.email.lower().strip()
    if supabase:
        res = supabase.table("users").select("*").eq("email", email).eq("password", req.password).execute()
        if not res.data:
            raise HTTPException(401, "Неверный Email или пароль")
        return res.data[0]
    
    u = next((u for u in db_content["users"] if u["email"] == email and u["password"] == req.password), None)
    if not u:
        raise HTTPException(401, "Неверный Email или пароль")
    return u

@app.post("/api/auth/request-verification")
@app.post("/api/auth/request-verification/")
async def request_verification(req: VerificationRequest):
    email = req.email.lower().strip()
    # Проверка на существование
    if supabase:
        res = supabase.table("users").select("id").eq("email", email).execute()
        if res.data:
            raise HTTPException(400, "Email уже зарегистрирован")
    
    code = "".join([str(secrets.randbelow(10)) for _ in range(6)])
    verification_codes[email] = {"code": code, "timestamp": time.time()}
    
    if EmailService.send_verification_code(email, code):
        return {"status": "ok", "message": "Код отправлен"}
    
    raise HTTPException(500, "Ошибка отправки почты. Проверьте настройки SMTP.")

@app.post("/api/auth/verify-and-register")
@app.post("/api/auth/verify-and-register/")
async def verify_and_register(req: RegisterWithCodeRequest):
    email = req.email.lower().strip()
    stored = verification_codes.get(email)
    
    if not stored or str(stored["code"]) != str(req.code):
        raise HTTPException(400, "Неверный или истекший код")
    
    new_user = {
        "id": f"u_{secrets.token_hex(4)}",
        "username": req.username,
        "email": email,
        "password": req.password,
        "balance": 0.0,
        "botsCreated": 0,
        "licenseExpiresAt": int(time.time() * 1000) + (3 * 24 * 3600 * 1000) # 3 дня триала
    }
    
    if supabase:
        try:
            supabase.table("users").insert(new_user).execute()
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            raise HTTPException(500, "Ошибка сохранения пользователя")
            
    db_content["users"].append(new_user)
    verification_codes.pop(email, None)
    return new_user

@app.get("/api/bots/{user_id}")
@app.get("/api/bots/{user_id}/")
async def get_bots(user_id: str):
    if supabase:
        res = supabase.table("bots").select("*").eq("ownerId", user_id).execute()
        return res.data or []
    return [b for b in db_content["bots"] if str(b["ownerId"]) == str(user_id)]

@app.post("/api/bots/save")
@app.post("/api/bots/save/")
async def save_bot_api(bot_data: dict):
    if supabase:
        try:
            supabase.table("bots").upsert(bot_data).execute()
        except Exception as e:
            logger.error(f"Error saving bot: {e}")
            raise HTTPException(500, "Ошибка базы данных")
    return {"status": "ok"}

if __name__ == "__main__":
    # Запуск на порту 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
