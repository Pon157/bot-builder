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
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from email_service import EmailService

# Импорты aiogram для рассылки
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

# ==========================================
# 1. КОНФИГУРАЦИЯ И ОКРУЖЕНИЕ
# ==========================================
def init_env():
    env = '.env'
    if os.path.exists(env):
        with open(env, 'r', encoding='utf-8-sig') as f:
            for l in f:
                l = l.strip()
                if l and not l.startswith('#') and '=' in l:
                    k, v = l.split('=', 1)
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")

init_env()

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("BotEngineServer")

S_URL = os.getenv("SUPABASE_URL", "").rstrip('/')
S_KEY = os.getenv("SUPABASE_KEY", "")
A_SECRET = os.getenv("ADMIN_SECRET", "MRAKOTIK")

# ==========================================
# 2. МЕНЕДЖЕР ПРОЦЕССОВ БОТОВ
# ==========================================
class BotManager:
    def __init__(self):
        self.procs: Dict[str, asyncio.subprocess.Process] = {}
        self.logs: Dict[str, str] = {}

    async def start_bot(self, bid: str, config: dict):
        """Запуск процесса бота"""
        await self.stop_bot(bid)  # Гарантируем, что старый процесс убит
        
        os.makedirs("active_bots", exist_ok=True)
        cp = f"active_bots/cfg_{bid}.json"
        lp = f"active_bots/bot_{bid}.log"
        
        config['status'] = 'RUNNING'
        with open(cp, "w", encoding="utf-8") as f: 
            json.dump(config, f, indent=4)
        
        self.logs[bid] = lp
        
        try:
            env = os.environ.copy()
            env.update({"SUPABASE_URL": S_URL, "SUPABASE_KEY": S_KEY})
            l_out = open(lp, "a", encoding="utf-8")
            
            p = await asyncio.create_subprocess_exec(
                sys.executable, "bot_core.py", cp, 
                stdout=l_out, stderr=l_out, env=env
            )
            self.procs[bid] = p
            logger.info(f"✅ Бот {bid} успешно запущен (PID: {p.pid})")
            return True
        except Exception as e: 
            logger.error(f"❌ Ошибка старта бота {bid}: {e}")
            return str(e)

    async def stop_bot(self, bid: str):
        """Остановка процесса бота с защитой от ошибок поиска"""
        p = self.procs.get(bid)
        if p:
            try:
                p.terminate()
                try:
                    await asyncio.wait_for(p.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    p.kill() # Жесткое завершение
            except ProcessLookupError:
                pass 
            except Exception as e:
                logger.error(f"⚠️ Ошибка при остановке {bid}: {e}")
            finally:
                if bid in self.procs:
                    del self.procs[bid]
        return True

    def get_logs(self, bid: str):
        path = self.logs.get(bid)
        if not path or not os.path.exists(path): 
            return "Логов пока нет..."
        try:
            with open(path, "r", encoding="utf-8") as f: 
                return "".join(f.readlines()[-300:])
        except: 
            return "Ошибка при чтении файла логов."

pm = BotManager()

# ==========================================
# 3. ЖИЗНЕННЫЙ ЦИКЛ FASTAPI
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[*] Проверка ботов для автозапуска...")
    try:
        async with httpx.AsyncClient(base_url=f"{S_URL}/rest/v1/", 
                                     headers={"apikey": S_KEY, "Authorization": f"Bearer {S_KEY}"}) as client:
            r = await client.get("bots", params={"status": "eq.RUNNING"})
            if r.status_code == 200:
                for b_data in r.json():
                    bid = b_data['id']
                    config = {**(b_data.get("config") or {}), **b_data}
                    logger.info(f"[*] Автозапуск: {bid}")
                    await pm.start_bot(bid, config)
    except Exception as e:
        logger.error(f"[!] Ошибка автозапуска: {e}")
    
    yield
    
    logger.info("[*] Завершение работы сервера, остановка всех ботов...")
    for bid in list(pm.procs.keys()):
        await pm.stop_bot(bid)

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Клиент для работы с БД
db = httpx.AsyncClient(
    base_url=f"{S_URL}/rest/v1/", 
    headers={"apikey": S_KEY, "Authorization": f"Bearer {S_KEY}", "Content-Type": "application/json"}
)

# ==========================================
# 4. ЭНДПОИНТЫ АВТОРИЗАЦИИ И РЕГИСТРАЦИИ
# ==========================================
@app.post("/api/auth/login")
async def login(d: dict):
    r = await db.get("users", params={"email": f"eq.{d['email'].lower()}", "password": f"eq.{d['password']}"})
    data = r.json()
    if not data: raise HTTPException(401, "Неверный Email или пароль")
    return data[0]

@app.post("/api/auth/request-verification")
async def req_ver(d: dict):
    email = d['email'].lower()
    code = str(random.randint(100000, 999999))
    await db.post("temp_codes", json={
        "email": email, "code": code, "type": "VERIFY", 
        "expires_at": int(time.time()*1000)+600000
    }, headers={"Prefer": "resolution=merge-duplicates"})
    if EmailService.send_verification_code(email, code): return True
    raise HTTPException(500, "Ошибка отправки почты")

@app.post("/api/auth/forgot-password")
async def forgot_p(d: dict):
    email = d['email'].lower()
    code = str(random.randint(100000, 999999))
    await db.post("temp_codes", json={
        "email": email, "code": code, "type": "RESET", 
        "expires_at": int(time.time()*1000)+600000
    }, headers={"Prefer": "resolution=merge-duplicates"})
    if EmailService.send_password_reset(email, code): return True
    raise HTTPException(500, "Ошибка почты")

@app.post("/api/auth/reset-password")
async def reset_p(d: dict):
    email = d['email'].lower()
    r = await db.get("temp_codes", params={"email": f"eq.{email}", "code": f"eq.{d['code']}", "type": "eq.RESET"})
    if not r.json(): raise HTTPException(400, "Неверный код")
    await db.patch("users", params={"email": f"eq.{email}"}, json={"password": d['newPassword']})
    return True

@app.post("/api/auth/verify-and-register")
async def verify_reg(d: dict):
    email = d['email'].lower()
    r = await db.get("temp_codes", params={"email": f"eq.{email}", "code": f"eq.{d['code']}"})
    if not r.json(): raise HTTPException(400, "Код неверен или истек")
    uid = f"u_{secrets.token_hex(4)}"
    user_data = {
        "id": uid, "username": d['username'], "email": email, 
        "password": d['password'], "balance": 0, 
        "license_expires_at": int(time.time()*1000) + 259200000
    }
    await db.post("users", json=user_data)
    return user_data

# ==========================================
# 5. УПРАВЛЕНИЕ БОТАМИ
# ==========================================
@app.get("/api/bots/{uid}")
async def get_user_bots(uid: str):
    r = await db.get("bots", params={"owner_id": f"eq.{uid}"})
    return [{**b, **(b.get("config") or {})} for b in r.json()]

@app.post("/api/bots/save")
async def save_bot(b: dict):
    bid = b['id']
    r = await db.get("bots", params={"id": f"eq.{bid}"})
    curr = r.json()[0] if r.json() else {}
    
    # Слияние конфигов
    old_cfg = curr.get("config") or {}
    sys_keys = ['id', 'owner_id', 'name', 'token', 'status', 'license_expires_at', 'config']
    new_ui_cfg = {k: v for k, v in b.items() if k not in sys_keys}
    merged_cfg = {**old_cfg, **new_ui_cfg}
    
    payload = {
        "id": bid, "owner_id": b['owner_id'], "name": b["name"], 
        "token": b["token"], "status": b.get("status", curr.get("status", "IDLE")),
        "license_expires_at": b.get("license_expires_at") or curr.get("license_expires_at", 0),
        "config": merged_cfg
    }
    await db.post("bots", json=payload, headers={"Prefer": "resolution=merge-duplicates"})
    return {**payload, **merged_cfg}

@app.post("/api/bots/start")
async def start_bot_handler(req: dict):
    r = await db.get("bots", params={"id": f"eq.{req['id']}"})
    if not r.json(): raise HTTPException(404, "Бот не найден")
    data = r.json()[0]
    config = {**data, **(data.get("config") or {})}
    if await pm.start_bot(req['id'], config) is True:
        await db.patch("bots", params={"id": f"eq.{req['id']}"}, json={"status": "RUNNING"})
        return True
    raise HTTPException(500, "Не удалось запустить процесс")

@app.post("/api/bots/stop/{bid}")
async def stop_bot_handler(bid: str):
    await pm.stop_bot(bid)
    await db.patch("bots", params={"id": f"eq.{bid}"}, json={"status": "IDLE"})
    return True

@app.delete("/api/bots/delete/{uid}/{bid}")
async def delete_bot_handler(uid: str, bid: str):
    await pm.stop_bot(bid)
    await db.delete("bots", params={"id": f"eq.{bid}", "owner_id": f"eq.{uid}"})
    return {"status": "ok"}

@app.get("/api/bots/logs/{bid}")
async def get_bot_logs(bid: str):
    return {"logs": pm.get_logs(bid)}

# ==========================================
# 6. ЛИЦЕНЗИИ И КЛЮЧИ
# ==========================================
@app.post("/api/admin/generate-key")
async def gen_key(d: dict, x_admin_token: str = Header(None)):
    if x_admin_token != A_SECRET: raise HTTPException(401, "Доступ запрещен")
    key = f"PRO-{secrets.token_hex(4).upper()}-{random.randint(100, 999)}"
    payload = {"key": key, "months": d.get('months', 1), "days": d.get('days', 0), "used": False}
    await db.post("issued_keys", json=payload)
    return {"key": key}

@app.post("/api/license/activate")
async def activate_license(req: dict):
    k = req['key']
    r = await db.get("issued_keys", params={"key": f"eq.{k}", "used": "eq.false"})
    if not r.json(): return {"status": "error", "message": "Ключ недействителен или уже использован"}
    
    key_data = r.json()[0]
    bid = req['botId']
    
    br = await db.get("bots", params={"id": f"eq.{bid}"})
    if not br.json(): return {"status": "error", "message": "Бот не найден"}
    
    current_expiry = max(br.json()[0].get("license_expires_at") or 0, int(time.time()*1000))
    added_ms = (key_data['months'] * 30 * 86400000) + (key_data['days'] * 86400000)
    
    await db.patch("bots", params={"id": f"eq.{bid}"}, json={"license_expires_at": current_expiry + added_ms})
    await db.patch("issued_keys", params={"key": f"eq.{k}"}, json={"used": True, "used_by_bot": bid})
    return {"status": "ok"}

# ==========================================
# 7. МАССОВАЯ РАССЫЛКА
# ==========================================
@app.post("/api/bots/broadcast")
async def broadcast(d: dict):
    bot_ids = d.get('botIds', [])
    msg = d.get('message', '')
    if not bot_ids or not msg: raise HTTPException(400, "Пустой запрос")
    
    results = {"success": 0, "failed": 0}
    for bid in bot_ids:
        r = await db.get("bots", params={"id": f"eq.{bid}"})
        if not r.json(): continue
        
        b_data = r.json()[0]
        users = (b_data.get('config') or {}).get('connectedUsers', [])
        
        async with Bot(token=b_data['token'], default=DefaultBotProperties(parse_mode=ParseMode.HTML)) as bot_api:
            for u in users:
                if not u.get('is_active', True): continue
                try:
                    await bot_api.send_message(int(u['id']), msg)
                    results["success"] += 1
                    await asyncio.sleep(0.05)
                except TelegramForbiddenError:
                    u['is_active'] = False # Помечаем ушедших
                except Exception:
                    results["failed"] += 1
            
            # Сохраняем обновленный статус юзеров
            cfg = b_data.get('config') or {}
            cfg['connectedUsers'] = users
            await db.patch("bots", params={"id": f"eq.{bid}"}, json={"config": cfg})
            
    return results

@app.get("/api/ping")
async def ping(): return {"status": "online"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
