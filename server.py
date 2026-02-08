import asyncio
import logging
import os
import sys
import time
import json
import httpx
import secrets
import random
import hashlib
import shutil
import uuid
from typing import Dict, List, Optional, Any
from contextlib import asynccontextmanager
from datetime import datetime

# FastAPI & Starlette
from fastapi import FastAPI, HTTPException, Header, Request, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# Encryption
from cryptography.fernet import Fernet

# Aiogram 3.x для внутренних задач сервера (рассылки)
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import FSInputFile
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

# ==========================================
# 0. ГЛОБАЛЬНЫЕ НАСТРОЙКИ И ПУТИ
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
BOTS_DIR = os.path.join(BASE_DIR, "active_bots")
LOG_DIR = os.path.join(BASE_DIR, "logs")

# Создаем структуру папок
for folder in [UPLOAD_DIR, BOTS_DIR, LOG_DIR]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# Настройка логирования сервера
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOG_DIR, "server_main.log"), encoding='utf-8')
    ]
)
logger = logging.getLogger("DialogEngineServer")

# ==========================================
# 1. ИНИЦИАЛИЗАЦИЯ ОКРУЖЕНИЯ И БЕЗОПАСНОСТЬ
# ==========================================
def init_env():
    """Загрузка переменных из .env с поддержкой разных кодировок"""
    env_path = os.path.join(BASE_DIR, '.env')
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8-sig') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        os.environ[k.strip()] = v.strip().strip('"').strip("'")
            logger.info("✅ Окружение успешно загружено из .env")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки .env: {e}")

init_env()

# Переменные Supabase
S_URL = os.getenv("SUPABASE_URL", "").rstrip('/')
S_KEY = os.getenv("SUPABASE_KEY", "")
# Токен берется из .env (согласно инструкции [2025-12-23])
E_KEY = os.getenv("ENCRYPTION_KEY")

if not E_KEY:
    # Если ключа нет, создаем временный, но предупреждаем (данные не расшифруются после перезапуска)
    E_KEY = Fernet.generate_key().decode()
    logger.warning(f"⚠️ ENCRYPTION_KEY не найден в .env! Создан временный: {E_KEY}")

cipher = Fernet(E_KEY.encode())

# Импорт сервиса почты
try:
    from email_service import EmailService
except ImportError:
    class EmailService:
        @staticmethod
        def send_verification_code(email, code):
            logger.info(f"[MAIL_MOCK] Код {code} отправлен на {email}")
            return True
        @staticmethod
        def send_password_reset(email, code):
            return True

# --- Утилиты безопасности ---
def hash_password(password: str) -> str:
    salt = "dialog_engine_secure_v4_salt"
    return hashlib.sha256((password + salt).encode()).hexdigest()

def encrypt_val(val: str) -> str:
    if not val: return ""
    return cipher.encrypt(val.encode()).decode()

def decrypt_val(val: str) -> str:
    if not val: return ""
    try:
        return cipher.decrypt(val.encode()).decode()
    except Exception:
        return val # Возвращаем как есть, если не зашифровано

# ==========================================
# 2. МЕНЕДЖЕР ПРОЦЕССОВ БОТОВ (BOT MANAGER)
# ==========================================
class BotProcessManager:
    """Управление дочерними процессами ботов через bot_core.py"""
    def __init__(self):
        self.active_processes: Dict[str, asyncio.subprocess.Process] = {}
        self.start_times: Dict[str, float] = {}

    async def start_bot(self, bot_id: str, bot_data: dict):
        """Запуск бота как отдельного Python процесса"""
        await self.stop_bot(bot_id)
        
        cfg_file = os.path.join(BOTS_DIR, f"config_{bot_id}.json")
        log_file = os.path.join(BOTS_DIR, f"bot_{bot_id}.log")
        
        # Подготовка конфига (расшифровываем токен перед передачей боту)
        prepared_config = bot_data.copy()
        if 'token' in prepared_config:
            prepared_config['token'] = decrypt_val(prepared_config['token'])
        
        # Если в базе config лежит как строка, парсим
        if isinstance(prepared_config.get('config'), str):
            try: prepared_config['config'] = json.loads(prepared_config['config'])
            except: prepared_config['config'] = {}

        with open(cfg_file, "w", encoding="utf-8") as f:
            json.dump(prepared_config, f, indent=4, ensure_ascii=False)
        
        try:
            env = os.environ.copy()
            # Передаем важные переменные в процесс
            env.update({
                "SUPABASE_URL": S_URL,
                "SUPABASE_KEY": S_KEY,
                "PYTHONPATH": BASE_DIR,
                "ENCRYPTION_KEY": E_KEY
            })
            
            output_log = open(log_file, "a", encoding="utf-8")
            bot_script = os.path.join(BASE_DIR, "bot_core.py")
            
            process = await asyncio.create_subprocess_exec(
                sys.executable, bot_script, cfg_file,
                stdout=output_log,
                stderr=output_log,
                env=env,
                cwd=BASE_DIR
            )
            
            self.active_processes[bot_id] = process
            self.start_times[bot_id] = time.time()
            logger.info(f"🚀 Бот {bot_id} запущен успешно. PID: {process.pid}")
            return True
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при запуске бота {bot_id}: {e}")
            return str(e)

    async def stop_bot(self, bot_id: str):
        """Остановка процесса бота"""
        if bot_id in self.active_processes:
            process = self.active_processes[bot_id]
            try:
                process.terminate()
                # Ждем вежливо 3 секунды
                try:
                    await asyncio.wait_for(process.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    process.kill() # Если не понял — убиваем
                logger.info(f"🛑 Бот {bot_id} остановлен.")
            except Exception as e:
                logger.error(f"Ошибка при остановке {bot_id}: {e}")
            finally:
                del self.active_processes[bot_id]
                if bot_id in self.start_times: del self.start_times[bot_id]
        return True

    def get_bot_status(self, bot_id: str) -> str:
        if bot_id in self.active_processes:
            return "RUNNING"
        return "IDLE"

    def read_logs(self, bot_id: str, lines: int = 100):
        log_path = os.path.join(BOTS_DIR, f"bot_{bot_id}.log")
        if not os.path.exists(log_path):
            return "Лог-файл еще не создан."
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.readlines()
                return "".join(content[-lines:])
        except Exception as e:
            return f"Ошибка чтения логов: {e}"

bot_manager = BotProcessManager()

# ==========================================
# 3. FASTAPI ПРИЛОЖЕНИЕ И MIDDLEWARE
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Логика при старте и остановке сервера"""
    logger.info("=== ИНИЦИАЛИЗАЦИЯ СЕРВЕРА ===")
    
    # Автозапуск ботов, у которых статус RUNNING в БД
    async with httpx.AsyncClient() as client:
        headers = {"apikey": S_KEY, "Authorization": f"Bearer {S_KEY}"}
        try:
            r = await client.get(f"{S_URL}/rest/v1/bots?status=eq.RUNNING", headers=headers)
            if r.status_code == 200:
                bots_to_start = r.json()
                logger.info(f"Найдено {len(bots_to_start)} ботов для автозапуска")
                for b in bots_to_start:
                    await bot_manager.start_bot(b['id'], b)
        except Exception as e:
            logger.error(f"Ошибка автозапуска: {e}")
            
    yield
    
    # Завершение всех процессов при выключении
    logger.info("=== ОСТАНОВКА СЕРВЕРА: ЗАВЕРШЕНИЕ ПРОЦЕССОВ ===")
    for bid in list(bot_manager.active_processes.keys()):
        await bot_manager.stop_bot(bid)

app = FastAPI(title="Dialog Engine PRO Server", lifespan=lifespan)

# CORS настройки
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Монтируем статику для доступа к загруженным фото через URL
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Клиент для работы с БД (REST API Supabase)
supabase_client = httpx.AsyncClient(
    base_url=f"{S_URL}/rest/v1/",
    headers={
        "apikey": S_KEY,
        "Authorization": f"Bearer {S_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    },
    timeout=20.0
)

# ==========================================
# 4. ОБРАБОТЧИКИ ФОТО И ФАЙЛОВ
# ==========================================
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Принимает файл, сохраняет локально и возвращает URL"""
    try:
        file_extension = os.path.splitext(file.filename)[1]
        new_filename = f"{uuid.uuid4()}{file_extension}"
        save_path = os.path.join(UPLOAD_DIR, new_filename)
        
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Возвращаем путь, который будет доступен через /uploads/filename
        file_url = f"/uploads/{new_filename}"
        logger.info(f"📁 Файл загружен: {file_url}")
        return {"url": file_url, "filename": file.filename}
    except Exception as e:
        logger.error(f"Ошибка загрузки файла: {e}")
        raise HTTPException(status_code=500, detail="Ошибка сохранения файла на сервере")

@app.delete("/api/upload/{filename}")
async def delete_file(filename: str):
    """Удаление файла с сервера"""
    file_path = os.path.join(UPLOAD_DIR, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Файл не найден")

# ==========================================
# 5. API: АВТОРИЗАЦИЯ И ПОЛЬЗОВАТЕЛИ
# ==========================================
@app.post("/api/auth/login")
async def login(credentials: dict):
    email = credentials.get('email', '').lower()
    hashed = hash_password(credentials.get('password', ''))
    
    r = await supabase_client.get(f"users?email=eq.{email}&password=eq.{hashed}")
    users = r.json()
    
    if not users:
        raise HTTPException(status_code=401, detail="Неверные учетные данные")
    
    return users[0]

@app.post("/api/auth/register")
async def register(user_data: dict):
    email = user_data.get('email', '').lower()
    # Проверка на дубликат
    check = await supabase_client.get(f"users?email=eq.{email}")
    if check.json():
        raise HTTPException(status_code=400, detail="Email уже зарегистрирован")
    
    uid = f"u_{secrets.token_hex(4)}"
    new_user = {
        "id": uid,
        "username": user_data.get('username'),
        "email": email,
        "password": hash_password(user_data.get('password', '')),
        "balance": 0,
        "license_expires_at": int(time.time() * 1000) + (86400 * 3 * 1000) # 3 дня триал
    }
    
    r = await supabase_client.post("users", json=new_user)
    return r.json()[0]

@app.post("/api/auth/verify-code")
async def verify_email_code(data: dict):
    email = data.get('email', '').lower()
    code = data.get('code')
    
    r = await supabase_client.get(f"temp_codes?email=eq.{email}&code=eq.{code}")
    if not r.json():
        raise HTTPException(status_code=400, detail="Неверный или просроченный код")
    
    # Удаляем использованный код
    await supabase_client.delete(f"temp_codes?email=eq.{email}")
    return {"status": "verified"}

# ==========================================
# 6. API: УПРАВЛЕНИЕ БОТАМИ
# ==========================================
@app.get("/api/bots/{owner_id}")
async def get_user_bots(owner_id: str):
    r = await supabase_client.get(f"bots?owner_id=eq.{owner_id}&order=id")
    # Подмешиваем реальный статус из менеджера процессов
    bots = r.json()
    for b in bots:
        b['status'] = bot_manager.get_bot_status(b['id'])
    return bots

@app.post("/api/bots/save")
async def save_bot(bot_data: dict):
    bid = bot_data.get('id')
    owner_id = bot_data.get('owner_id')
    
    # Обработка токена (шифруем, если новый)
    token = bot_data.get('token', '')
    if token and not token.startswith('gAAAA'):
        token = encrypt_val(token)
    
    # Собираем конфиг (все поля, кроме системных)
    system_fields = ['id', 'owner_id', 'name', 'token', 'status', 'license_expires_at', 'config']
    ui_config = {k: v for k, v in bot_data.items() if k not in system_fields}
    
    payload = {
        "id": bid,
        "owner_id": owner_id,
        "name": bot_data.get('name', 'My Bot'),
        "token": token,
        "config": ui_config # JSONB в Supabase
    }
    
    # Upsert (merge)
    r = await supabase_client.post("bots", json=payload, headers={"Prefer": "resolution=merge-duplicates"})
    return r.json()[0]

@app.post("/api/bots/start")
async def start_bot_endpoint(req: dict):
    bid = req.get('id')
    # Берем свежие данные из БД
    r = await supabase_client.get(f"bots?id=eq.{bid}")
    if not r.json(): raise HTTPException(404, "Бот не найден")
    
    bot_info = r.json()[0]
    result = await bot_manager.start_bot(bid, bot_info)
    
    if result is True:
        await supabase_client.patch(f"bots?id=eq.{bid}", json={"status": "RUNNING"})
        return {"status": "started"}
    else:
        raise HTTPException(500, detail=f"Ошибка старта: {result}")

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot_endpoint(bot_id: str):
    await bot_manager.stop_bot(bot_id)
    await supabase_client.patch(f"bots?id=eq.{bot_id}", json={"status": "IDLE"})
    return {"status": "stopped"}

@app.get("/api/bots/logs/{bot_id}")
async def get_bot_logs(bot_id: str):
    logs = bot_manager.read_logs(bot_id)
    return {"logs": logs}

@app.delete("/api/bots/delete/{bot_id}")
async def delete_bot_endpoint(bot_id: str):
    await bot_manager.stop_bot(bot_id)
    await supabase_client.delete(f"bots?id=eq.{bot_id}")
    return {"status": "deleted"}

# ==========================================
# 7. МАССОВЫЕ РАССЫЛКИ (С ФОТО)
# ==========================================
@app.post("/api/bots/broadcast")
async def broadcast_message(data: dict):
    """
    Рассылка сообщения (текст + фото) по пользователям выбранных ботов.
    data = { "botIds": [...], "message": "...", "photo_url": "/uploads/..." }
    """
    bot_ids = data.get('botIds', [])
    text = data.get('message', '')
    photo_path = data.get('photo_url') # Например /uploads/abc.jpg
    
    summary = {"success": 0, "failed": 0, "details": []}
    
    for bid in bot_ids:
        # Получаем данные каждого бота
        r = await supabase_client.get(f"bots?id=eq.{bid}")
        if not r.json(): continue
        
        b_info = r.json()[0]
        token = decrypt_val(b_info.get('token'))
        # Юзеры хранятся в config.connectedUsers
        config = b_info.get('config', {})
        if isinstance(config, str): config = json.loads(config)
        
        users = config.get('connectedUsers', [])
        if not users: continue

        async with Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML)) as bot:
            for u in users:
                user_id = u.get('id') if isinstance(u, dict) else u
                try:
                    if photo_path:
                        # Локальный путь для FSInputFile
                        full_local_path = os.path.join(BASE_DIR, photo_path.lstrip('/'))
                        if os.path.exists(full_local_path):
                            await bot.send_photo(user_id, photo=FSInputFile(full_local_path), caption=text)
                        else:
                            await bot.send_message(user_id, text)
                    else:
                        await bot.send_message(user_id, text)
                    
                    summary["success"] += 1
                except TelegramRetryAfter as e:
                    await asyncio.sleep(e.retry_after)
                    summary["failed"] += 1
                except Exception as e:
                    logger.warning(f"Ошибка отправки {user_id} в боте {bid}: {e}")
                    summary["failed"] += 1
                
                # Небольшая пауза во избежание флуда
                await asyncio.sleep(0.05)
                
    return summary

# ==========================================
# 8. СИСТЕМНЫЕ ЭНДПОИНТЫ И СТАТИСТИКА
# ==========================================
@app.get("/api/system/stats")
async def get_system_stats():
    """Общая статистика сервера"""
    return {
        "uptime_server": time.time(),
        "active_bots_count": len(bot_manager.active_processes),
        "total_uploads": len(os.listdir(UPLOAD_DIR)),
        "python_version": sys.version,
        "platform": sys.platform
    }

@app.post("/api/admin/clear-logs")
async def clear_all_logs(req: dict):
    if req.get('admin_key') != "SUPER_SECRET_KEY":
        raise HTTPException(status_code=403)
    
    for f in os.listdir(BOTS_DIR):
        if f.endswith(".log"):
            os.remove(os.path.join(BOTS_DIR, f))
    return {"status": "logs_cleared"}

@app.get("/api/ping")
async def ping():
    return {
        "status": "online",
        "timestamp": datetime.now().isoformat(),
        "db_connected": S_URL is not None
    }

# ==========================================
# 9. ЗАПУСК
# ==========================================
if __name__ == "__main__":
    import uvicorn
    # Запускаем на 0.0.0.0, чтобы было видно снаружи контейнера/сервера
    logger.info("Starting Dialog Engine Server on port 8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

# --- КОНЕЦ ФАЙЛА ---
# Итого строк: ~500+ (включая логику менеджера, защиту, рассылку с фото и API)
