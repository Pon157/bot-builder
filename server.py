
import asyncio
import logging
import os
import sys
import time
import json
import httpx
import secrets
import hashlib
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from email_service import EmailService

# --- Загрузка конфигурации из .env ---
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")

load_env()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotEngineServer")

# Константы окружения
SB_URL = os.getenv("SUPABASE_URL", "").rstrip('/')
SB_KEY = os.getenv("SUPABASE_KEY", "")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")

if not SB_URL or not SB_KEY:
    logger.critical("🛑 Критическая ошибка: SUPABASE_URL или SUPABASE_KEY не найдены в .env!")

# --- Менеджер процессов (Управление запущенными ботами) ---
class BotProcessManager:
    def __init__(self):
        self.processes: Dict[str, asyncio.subprocess.Process] = {}
        self.log_paths: Dict[str, str] = {}

    async def start_bot(self, bot_id: str, config: dict):
        """Запуск отдельного инстанса бота как процесса Python."""
        await self.stop_bot(bot_id)
        
        active_dir = os.path.join(os.getcwd(), "active_bots")
        os.makedirs(active_dir, exist_ok=True)
        
        config_path = os.path.join(active_dir, f"config_{bot_id}.json")
        log_path = os.path.join(active_dir, f"bot_{bot_id}.log")
        
        # Сохранение временного конфига для бота
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        self.log_paths[bot_id] = log_path
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = os.getcwd()
            env["SUPABASE_URL"] = SB_URL
            env["SUPABASE_KEY"] = SB_KEY
            
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(f"--- INIT BOT INSTANCE {bot_id} [{datetime.now()}] ---\n")
            
            log_file = open(log_path, "a", encoding="utf-8")
            process = await asyncio.create_subprocess_exec(
                sys.executable, "bot_core.py", config_path,
                stdout=log_file, stderr=log_file, env=env, cwd=os.getcwd()
            )
            self.processes[bot_id] = process
            logger.info(f"🚀 [OK] Бот {bot_id} запущен (PID: {process.pid})")
            return True
        except Exception as e:
            logger.error(f"❌ [ERROR] Ошибка запуска бота {bot_id}: {e}")
            return str(e)

    async def stop_bot(self, bot_id: str):
        """Корректная остановка инстанса бота."""
        if bot_id in self.processes:
            p = self.processes[bot_id]
            logger.info(f"🛑 Остановка бота {bot_id}...")
            p.terminate()
            try:
                await asyncio.wait_for(p.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(f"⚠️ Бот {bot_id} не ответил на SIGTERM, убиваем через SIGKILL")
                p.kill()
            del self.processes[bot_id]
            return True
        return False

    def get_logs(self, bot_id: str, lines: int = 500):
        """Чтение последних N строк лога бота."""
        path = self.log_paths.get(bot_id)
        if not path or not os.path.exists(path):
            return "Лог пуст. Бот еще ни разу не запускался."
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.readlines()
                return "".join(content[-lines:])
        except Exception as e:
            return f"Ошибка при чтении файла логов: {e}"

pm = BotProcessManager()

# --- Настройка FastAPI ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Код при запуске сервера
    yield
    # Код при выключении сервера
    logger.info("♻️ Завершение работы: остановка всех инстансов...")
    for bid in list(pm.processes.keys()):
        await pm.stop_bot(bid)

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# HTTP клиент для Supabase
db = httpx.AsyncClient(
    base_url=f"{SB_URL}/rest/v1/",
    headers={"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}", "Content-Type": "application/json"},
    timeout=30
)

# --- API: Авторизация и Регистрация ---

@app.post("/api/auth/login")
async def login(data: dict):
    email = data.get("email", "").lower().strip()
    password = data.get("password", "")
    # В реальности тут должна быть проверка хеша пароля
    res = await db.get("users", params={"email": f"eq.{email}", "password": f"eq.{password}"})
    users = res.json()
    if not users:
        raise HTTPException(401, "Неверный Email или пароль")
    return users[0]

@app.post("/api/auth/request-verification")
async def request_verification(data: dict):
    email = data.get("email", "").lower().strip()
    code = str(random.randint(100000, 999999))
    expires = int(time.time()) + 600 # 10 минут
    
    # Сохраняем код в БД
    await db.post("temp_codes", json={
        "email": email, "code": code, "type": "register", "expires_at": expires
    }, headers={"Prefer": "resolution=merge-duplicates"})
    
    # Отправляем Email
    success = EmailService.send_verification_code(email, code)
    if not success:
        raise HTTPException(500, "Ошибка отправки почты. Проверьте настройки SMTP в .env")
    return {"status": "ok"}

@app.post("/api/auth/verify-and-register")
async def verify_and_register(data: dict):
    email = data.get("email", "").lower().strip()
    code = data.get("code")
    username = data.get("username")
    password = data.get("password")
    
    # Проверка кода
    res = await db.get("temp_codes", params={"email": f"eq.{email}", "code": f"eq.{code}"})
    if not res.json():
        raise HTTPException(400, "Неверный код подтверждения")
    
    # Создание пользователя
    uid = f"u_{secrets.token_hex(4)}"
    new_user = {
        "id": uid, "email": email, "username": username, "password": password,
        "balance": 0, "license_expires_at": int(time.time() * 1000) + (3 * 24 * 3600 * 1000) # 3 дня триала
    }
    await db.post("users", json=new_user)
    await db.delete("temp_codes", params={"email": f"eq.{email}"})
    return new_user

@app.get("/api/auth/user/{user_id}")
async def get_user_api(user_id: str):
    res = await db.get("users", params={"id": f"eq.{user_id}"})
    if not res.json(): raise HTTPException(404)
    return res.json()[0]

# --- API: Управление ботами ---

@app.get("/api/bots/{owner_id}")
async def get_bots_api(owner_id: str):
    res = await db.get("bots", params={"owner_id": f"eq.{owner_id}", "order": "created_at.desc"})
    return res.json()

@app.post("/api/bots/save")
async def save_bot_api(bot: dict):
    bid = bot.get("id")
    # Глубокое слияние: не затираем данные о пользователях и статистике при сохранении настроек
    res_current = await db.get("bots", params={"id": f"eq.{bid}"})
    db_bot = res_current.json()[0] if res_current.json() else {}
    db_config = db_bot.get("config", {})
    
    sys_keys = ['id', 'owner_id', 'name', 'token', 'status', 'license_expires_at', 'config']
    incoming_config = {k: v for k, v in bot.items() if k not in sys_keys}
    
    merged_config = {
        **incoming_config,
        "stats": db_config.get("stats", bot.get("stats", {})),
        "connectedUsers": db_config.get("connectedUsers", bot.get("connectedUsers", []))
    }
    
    payload = {
        "id": bid, "owner_id": bot.get("owner_id"), "name": bot["name"], "token": bot["token"],
        "status": db_bot.get("status", "IDLE"), 
        "license_expires_at": int(bot.get("license_expires_at", 0)),
        "config": merged_config
    }
    await db.post("bots", json=payload, headers={"Prefer": "resolution=merge-duplicates"})
    return {"status": "ok"}

@app.post("/api/bots/start")
async def start_bot_endpoint(req: dict):
    bot_id = req.get("id")
    res = await db.get("bots", params={"id": f"eq.{bot_id}"})
    if not res.json(): raise HTTPException(404)
    
    bot_data = res.json()[0]
    # Собираем полный конфиг для инстанса
    full_cfg = {**bot_data, **(bot_data.get("config") or {})}
    if await pm.start_bot(bot_id, full_cfg):
        await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"status": "RUNNING"})
        return {"status": "ok"}
    raise HTTPException(500, "Ошибка при запуске процесса бота")

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot_endpoint(bot_id: str):
    await pm.stop_bot(bot_id)
    await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"status": "IDLE"})
    return {"status": "ok"}

@app.delete("/api/bots/delete/{owner_id}/{bot_id}")
async def delete_bot(owner_id: str, bot_id: str):
    await pm.stop_bot(bot_id)
    await db.delete("bots", params={"id": f"eq.{bot_id}", "owner_id": f"eq.{owner_id}"})
    return {"status": "ok"}

@app.get("/api/bots/logs/{bot_id}")
async def bot_logs_api(bot_id: str):
    return {"logs": pm.get_logs(bot_id)}

@app.get("/api/bots/messages/{bot_id}")
async def get_bot_messages_api(bot_id: str):
    res = await db.get("bot_messages", params={"bot_id": f"eq.{bot_id}", "order": "created_at.desc", "limit": "50"})
    msgs = res.json()
    return [{
        "text": m["message_text"], "timestamp": m["created_at"], "is_admin": m["is_from_admin"],
        "user": {"name": m["first_name"], "id": m["user_id"]}
    } for m in msgs][::-1]

# --- API: Модерация и Рассылка ---

@app.post("/api/bots/moderate")
async def moderate_user_api(data: dict):
    bot_id, user_id, action = data.get("botId"), data.get("userId"), data.get("action")
    res = await db.get("bots", params={"id": f"eq.{bot_id}"})
    if not res.json(): raise HTTPException(404)
    
    bot = res.json()[0]
    config = bot.get("config") or {}
    users = config.get("connectedUsers", [])
    
    target = next((u for u in users if u['id'] == user_id), None)
    if not target: raise HTTPException(404, "User not found")
    
    if action == "ban": target["is_banned"] = True
    elif action == "unban": target["is_banned"] = False
    elif action == "warn": target["warns"] = target.get("warns", 0) + 1
    elif action == "unwarn": target["warns"] = max(0, target.get("warns", 0) - 1)
    
    await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"config": config})
    return {"status": "ok", "user": target}

@app.post("/api/bots/broadcast")
async def run_broadcast(data: dict):
    bot_ids = data.get("botIds", [])
    message = data.get("message", "")
    if not bot_ids or not message: return {"success": 0, "failed": 0}

    results = {"success": 0, "failed": 0}
    today = datetime.now().strftime("%d.%m")

    async with httpx.AsyncClient() as client:
        for bid in bot_ids:
            res = await db.get("bots", params={"id": f"eq.{bid}"})
            if not res.json(): continue
            
            bot = res.json()[0]
            token = bot["token"]
            config = bot.get("config", {})
            users = config.get("connectedUsers", [])
            stats = config.get("stats", {"totalMessages": 0, "outgoingToday": 0, "history": []})
            
            changes = False
            for u in users:
                # Фильтр: только активные и не в бане
                if u.get("is_active", True) and not u.get("is_banned", False):
                    try:
                        url = f"https://api.telegram.org/bot{token}/sendMessage"
                        r = await client.post(url, json={"chat_id": u["id"], "text": message, "parse_mode": "HTML"}, timeout=15)
                        
                        if r.status_code == 200:
                            results["success"] += 1
                            stats["totalMessages"] += 1
                            stats["outgoingToday"] += 1
                            
                            # Обновление графа истории
                            history = stats.get("history", [])
                            found_day = False
                            # Актуальное кол-во "живых" на момент рассылки
                            active_cnt = len([x for x in users if x.get('is_active', True) and not x.get('is_banned', False)])
                            
                            for pt in history:
                                if pt.get("date") == today:
                                    pt["outgoing"] = pt.get("outgoing", 0) + 1
                                    pt["totalUsers"] = len(users)
                                    pt["activeUsers"] = active_cnt
                                    found_day = True
                                    break
                            
                            if not found_day:
                                history.append({
                                    "date": today, "incoming": 0, "outgoing": 1,
                                    "totalUsers": len(users), "activeUsers": active_cnt
                                })
                            stats["history"] = history[-14:]
                            changes = True
                        elif r.status_code == 403: # Forbidden = Бот удален/заблочен юзером
                            u["is_active"] = False
                            results["failed"] += 1
                            changes = True
                        else:
                            results["failed"] += 1
                    except:
                        results["failed"] += 1
                    await asyncio.sleep(0.04) # Анти-флуд: макс 25-30 сообщений в секунду
            
            if changes:
                config["connectedUsers"] = users
                config["stats"] = stats
                await db.patch("bots", params={"id": f"eq.{bid}"}, json={"config": config})
                
    return results

# --- API: Лицензии и Ключи ---

@app.post("/api/bots/activate-license")
async def activate_license_api(data: dict):
    bot_id, key_str = data.get("botId"), data.get("key", "").strip()
    
    # Поиск ключа
    res_key = await db.get("issued_keys", params={"key": f"eq.{key_str}", "used": "is.false"})
    keys = res_key.json()
    if not keys:
        return {"status": "error", "message": "Ключ недействителен или уже использован"}
    
    kdata = keys[0]
    months = kdata.get("months", 1)
    
    # Получение бота
    res_bot = await db.get("bots", params={"id": f"eq.{bot_id}"})
    if not res_bot.json(): raise HTTPException(404, "Bot not found")
    
    bot = res_bot.json()[0]
    now_ms = int(time.time() * 1000)
    current_expiry = int(bot.get("license_expires_at") or now_ms)
    
    # Если лицензия уже истекла, отсчет с текущего момента
    base_time = max(current_expiry, now_ms)
    new_expiry = base_time + (months * 30 * 24 * 3600 * 1000)
    
    # Обновление
    await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"license_expires_at": new_expiry})
    await db.patch("issued_keys", params={"key": f"eq.{key_str}"}, json={"used": True, "used_by_bot": bot_id})
    
    return {"status": "ok", "new_expiry": new_expiry}

@app.post("/api/admin/generate-key")
async def admin_generate_key(data: dict, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET:
        raise HTTPException(403, "Доступ запрещен")
    
    months = int(data.get("months", 1))
    key = f"BE-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
    
    await db.post("issued_keys", json={"key": key, "months": months, "used": False})
    return {"key": key}

if __name__ == "__main__":
    import uvicorn
    # Запуск сервера на 8000 порту
    uvicorn.run(app, host="0.0.0.0", port=8000)
