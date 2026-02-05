
import asyncio
import logging
import os
import sys
import time
import json
import httpx
import secrets
import random
from typing import Dict, List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from email_service import EmailService

# Настройка окружения
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
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("BotEngineServer")

SB_URL = os.getenv("SUPABASE_URL", "").rstrip('/')
SB_KEY = os.getenv("SUPABASE_KEY", "")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")

class BotProcessManager:
    def __init__(self):
        self.processes: Dict[str, asyncio.subprocess.Process] = {}
        self.log_paths: Dict[str, str] = {}

    async def start_bot(self, bot_id: str, config: dict):
        await self.stop_bot(bot_id)
        active_dir = os.path.join(os.getcwd(), "active_bots")
        os.makedirs(active_dir, exist_ok=True)
        config_path = os.path.join(active_dir, f"config_{bot_id}.json")
        log_path = os.path.join(active_dir, f"bot_{bot_id}.log")
        
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        self.log_paths[bot_id] = log_path
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = os.getcwd()
            env["SUPABASE_URL"] = SB_URL
            env["SUPABASE_KEY"] = SB_KEY
            
            with open(log_path, "w") as f: f.write(f"--- Запуск инстанса {bot_id} ---\n")
            
            log_file = open(log_path, "a", encoding="utf-8")
            process = await asyncio.create_subprocess_exec(
                sys.executable, "bot_core.py", config_path,
                stdout=log_file, stderr=log_file, env=env, cwd=os.getcwd()
            )
            self.processes[bot_id] = process
            logger.info(f"Bot {bot_id} started. PID: {process.pid}")
            return True
        except Exception as e:
            logger.error(f"Error starting bot {bot_id}: {e}")
            return str(e)

    async def stop_bot(self, bot_id: str):
        if bot_id in self.processes:
            p = self.processes[bot_id]
            p.terminate()
            try: await asyncio.wait_for(p.wait(), timeout=3.0)
            except: p.kill()
            del self.processes[bot_id]
            return True
        return False

    def get_logs(self, bot_id: str, lines: int = 500):
        path = self.log_paths.get(bot_id)
        if not path or not os.path.exists(path): return "Лог пуст. Запустите бота."
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.readlines()
                return "".join(content[-lines:])
        except Exception as e:
            return f"Ошибка чтения логов: {e}"

pm = BotProcessManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    for bid in list(pm.processes.keys()): await pm.stop_bot(bid)

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

db = httpx.AsyncClient(
    base_url=f"{SB_URL}/rest/v1/",
    headers={"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}", "Content-Type": "application/json"},
    timeout=30
)

# --- AUTH API ---
@app.post("/api/auth/login")
async def login(data: dict):
    res = await db.get("users", params={"email": f"eq.{data['email'].lower()}", "password": f"eq.{data['password']}"})
    if not res.json(): raise HTTPException(401, "Invalid credentials")
    return res.json()[0]

@app.post("/api/auth/request-verification")
async def req_verif(data: dict):
    email = data.get("email", "").lower()
    code = "".join([str(random.randint(0, 9)) for _ in range(6)])
    expires = int(time.time() * 1000) + (10 * 60 * 1000)
    await db.post("temp_codes", json={"email": email, "code": code, "type": "REG", "expires_at": expires}, headers={"Prefer": "resolution=merge-duplicates"})
    EmailService.send_verification_code(email, code)
    return {"status": "ok"}

@app.post("/api/auth/verify-and-register")
async def verify_reg(data: dict):
    email = data.get("email", "").lower()
    res_code = await db.get("temp_codes", params={"email": f"eq.{email}", "code": f"eq.{data['code']}"})
    if not res_code.json(): raise HTTPException(400, "Invalid code")
    user_id = f"u_{secrets.token_hex(4)}"
    payload = {"id": user_id, "username": data['username'], "email": email, "password": data['password'], "license_expires_at": int(time.time()*1000) + 259200000}
    await db.post("users", json=payload)
    await db.delete("temp_codes", params={"email": f"eq.{email}"})
    return payload

@app.post("/api/auth/forgot-password")
async def forgot_password(data: dict):
    email = data.get("email", "").lower()
    # Проверяем существование пользователя
    res_user = await db.get("users", params={"email": f"eq.{email}"})
    if not res_user.json(): return {"status": "ok"} # Не палим наличие почты
    
    code = "".join([str(random.randint(0, 9)) for _ in range(6)])
    expires = int(time.time() * 1000) + (15 * 60 * 1000)
    await db.post("temp_codes", json={"email": email, "code": code, "type": "RESET", "expires_at": expires}, headers={"Prefer": "resolution=merge-duplicates"})
    EmailService.send_password_reset(email, code)
    return {"status": "ok"}

@app.post("/api/auth/reset-password")
async def reset_password(data: dict):
    email = data.get("email", "").lower()
    code = data.get("code")
    new_password = data.get("newPassword")
    
    res_code = await db.get("temp_codes", params={"email": f"eq.{email}", "code": f"eq.{code}", "type": "eq.RESET"})
    if not res_code.json(): raise HTTPException(400, "Invalid or expired reset code")
    
    await db.patch("users", params={"email": f"eq.{email}"}, json={"password": new_password})
    await db.delete("temp_codes", params={"email": f"eq.{email}"})
    return {"status": "ok"}

@app.get("/api/auth/user/{user_id}")
async def get_user_info(user_id: str):
    res = await db.get("users", params={"id": f"eq.{user_id}"})
    if res.json(): return res.json()[0]
    raise HTTPException(404)

# --- BOTS API ---
@app.get("/api/bots/{user_id}")
async def get_user_bots(user_id: str):
    res = await db.get("bots", params={"owner_id": f"eq.{user_id}"})
    bots = res.json() if res.status_code == 200 else []
    return [{**b, **(b.get("config") or {})} for b in bots]

@app.post("/api/bots/save")
async def save_bot(bot: dict):
    bid = bot.get("id")
    sys_keys = ['id', 'owner_id', 'name', 'token', 'status', 'license_expires_at', 'config']
    config_payload = {k: v for k, v in bot.items() if k not in sys_keys}
    payload = {
        "id": bid, 
        "owner_id": bot.get("owner_id"), 
        "name": bot["name"], 
        "token": bot["token"], 
        "status": bot.get("status", "IDLE"),
        "license_expires_at": int(bot.get("license_expires_at") or 0),
        "config": config_payload
    }
    await db.post("bots", json=payload, headers={"Prefer": "resolution=merge-duplicates"})
    return {"status": "ok"}

@app.post("/api/bots/moderate")
async def moderate_user(data: dict):
    bot_id = data.get("botId")
    user_id = data.get("userId")
    action = data.get("action")
    
    res = await db.get("bots", params={"id": f"eq.{bot_id}"})
    if not res.json(): raise HTTPException(404, "Bot not found")
    bot = res.json()[0]
    config = bot.get("config") or {}
    users = config.get("connectedUsers", [])
    settings = config.get("settings", {})
    
    target_user = next((u for u in users if u['id'] == user_id), None)
    if not target_user: raise HTTPException(404, "User not found")
    
    tg_msg = ""
    if action == "ban":
        target_user["is_banned"] = True
        tg_msg = "🚫 <b>Вы заблокированы администратором.</b>"
    elif action == "unban":
        target_user["is_banned"] = False
        tg_msg = "✅ <b>Блокировка снята.</b>"
    elif action == "warn":
        target_user["warns"] = target_user.get("warns", 0) + 1
        threshold = int(settings.get("autoBanThreshold", 0))
        msg = f"⚠️ <b>Предупреждение!</b> ({target_user['warns']}/{threshold or '∞'})"
        if threshold > 0 and target_user["warns"] >= threshold:
            target_user["is_banned"] = True
            msg += "\n\n🚫 Авто-бан."
        tg_msg = msg
    elif action == "unwarn":
        target_user["warns"] = max(0, target_user.get("warns", 0) - 1)
        tg_msg = f"✅ <b>Предупреждение снято.</b>"

    await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"config": config})
    if tg_msg:
        url = f"https://api.telegram.org/bot{bot['token']}/sendMessage"
        async with httpx.AsyncClient() as client:
            await client.post(url, json={"chat_id": user_id, "text": tg_msg, "parse_mode": "HTML"})
    return {"status": "ok", "user": target_user}

@app.post("/api/bots/broadcast")
async def send_broadcast(data: dict):
    bot_ids = data.get("botIds", [])
    message = data.get("message", "")
    if not bot_ids or not message: return {"success": 0, "failed": 0}

    results = {"success": 0, "failed": 0}
    async with httpx.AsyncClient() as client:
        for bid in bot_ids:
            res = await db.get("bots", params={"id": f"eq.{bid}"})
            if not res.json(): continue
            bot = res.json()[0]
            token = bot["token"]
            config = bot.get("config", {})
            users = config.get("connectedUsers", [])
            
            for u in users:
                if u.get("is_active") and not u.get("is_banned"):
                    try:
                        url = f"https://api.telegram.org/bot{token}/sendMessage"
                        r = await client.post(url, json={"chat_id": u["id"], "text": message, "parse_mode": "HTML"}, timeout=5)
                        if r.status_code == 200: results["success"] += 1
                        else: results["failed"] += 1
                    except: results["failed"] += 1
                    # Небольшая задержка чтобы не спамить API телеграма слишком быстро
                    await asyncio.sleep(0.05) 
    return results

@app.post("/api/bots/activate-license")
async def activate_license(data: dict):
    bid = data.get("botId")
    key_str = data.get("key")
    
    res_key = await db.get("issued_keys", params={"key": f"eq.{key_str}", "used": "is.false"})
    if not res_key.json(): return {"status": "error", "message": "Invalid or used key"}
    
    key_data = res_key.json()[0]
    res_bot = await db.get("bots", params={"id": f"eq.{bid}"})
    if not res_bot.json(): return {"status": "error", "message": "Bot not found"}
    
    bot = res_bot.json()[0]
    current_expiry = int(bot.get("license_expires_at") or time.time()*1000)
    if current_expiry < time.time()*1000: current_expiry = int(time.time()*1000)
    
    months = key_data.get("months") or 0
    days = key_data.get("days") or 0
    added_ms = (months * 30 * 24 * 3600 * 1000) + (days * 24 * 3600 * 1000)
    new_expiry = current_expiry + added_ms
    
    await db.patch("bots", params={"id": f"eq.{bid}"}, json={"license_expires_at": new_expiry})
    await db.patch("issued_keys", params={"key": f"eq.{key_str}"}, json={"used": True, "used_by_bot": bid})
    
    return {"status": "ok", "new_expiry": new_expiry}

@app.post("/api/admin/generate-key")
async def generate_key(data: dict, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET: raise HTTPException(403)
    months = data.get("months", 0)
    days = data.get("days", 0)
    new_key = f"PRO-{months}M-{secrets.token_hex(4).upper()}"
    await db.post("issued_keys", json={"key": new_key, "months": months, "days": days})
    return {"key": new_key}

@app.delete("/api/bots/delete/{user_id}/{bot_id}")
async def delete_bot(user_id: str, bot_id: str):
    await pm.stop_bot(bot_id)
    await db.delete("bots", params={"id": f"eq.{bot_id}", "owner_id": f"eq.{user_id}"})
    return {"status": "ok"}

@app.post("/api/bots/start")
async def start_bot(req: dict):
    res = await db.get("bots", params={"id": f"eq.{req['id']}"})
    if res.json():
        bot = res.json()[0]
        if await pm.start_bot(bot['id'], {**bot, **(bot.get("config") or {})}):
            await db.patch("bots", params={"id": f"eq.{bot['id']}"}, json={"status": "RUNNING"})
            return {"status": "ok"}
    raise HTTPException(500, "Start failed")

@app.post("/api/bots/stop/{bot_id}")
async def stop_bot(bot_id: str):
    await pm.stop_bot(bot_id)
    await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"status": "IDLE"})
    return {"status": "ok"}

@app.get("/api/bots/messages/{bot_id}")
async def get_bot_msgs(bot_id: str):
    res = await db.get("bot_messages", params={"bot_id": f"eq.{bot_id}", "order": "created_at.desc", "limit": "50"})
    return [{"text": m["message_text"], "timestamp": m["created_at"], "is_admin": m["is_from_admin"], "user": {"name": m["first_name"]}} for m in res.json()][::-1]

@app.get("/api/bots/logs/{bot_id}")
async def bot_logs_api(bot_id: str): return {"logs": pm.get_logs(bot_id)}

@app.get("/api/ping")
async def ping(): return {"status": "online"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
