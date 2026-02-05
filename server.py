
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
from typing import Dict, List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from email_service import EmailService

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

class BotManager:
    def __init__(self):
        self.procs: Dict[str, asyncio.subprocess.Process] = {}
        self.logs: Dict[str, str] = {}

    async def start_bot(self, bid: str, config: dict):
        await self.stop_bot(bid)
        os.makedirs("active_bots", exist_ok=True)
        cp = f"active_bots/cfg_{bid}.json"
        lp = f"active_bots/bot_{bid}.log"
        with open(cp, "w", encoding="utf-8") as f: json.dump(config, f, indent=4)
        self.logs[bid] = lp
        try:
            env = os.environ.copy()
            env.update({"SUPABASE_URL": S_URL, "SUPABASE_KEY": S_KEY})
            l_out = open(lp, "a", encoding="utf-8")
            p = await asyncio.create_subprocess_exec(sys.executable, "bot_core.py", cp, stdout=l_out, stderr=l_out, env=env)
            self.procs[bid] = p
            return True
        except Exception as e: return str(e)

    async def stop_bot(self, bid: str):
        if bid in self.procs:
            p = self.procs[bid]
            p.terminate()
            try: await asyncio.wait_for(p.wait(), 2.0)
            except: p.kill()
            del self.procs[bid]
            return True
        return False

    def get_logs(self, bid: str):
        path = self.logs.get(bid)
        if not path or not os.path.exists(path): return "Логов нет."
        try:
            with open(path, "r", encoding="utf-8") as f: return "".join(f.readlines()[-300:])
        except: return "Ошибка чтения."

pm = BotManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    for b in list(pm.procs.keys()): await pm.stop_bot(b)

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
db = httpx.AsyncClient(base_url=f"{S_URL}/rest/v1/", headers={"apikey": S_KEY, "Authorization": f"Bearer {S_KEY}", "Content-Type": "application/json"})

# --- AUTH & REGISTRATION ---
@app.post("/api/auth/login")
async def login(d: dict):
    r = await db.get("users", params={"email": f"eq.{d['email'].lower()}", "password": f"eq.{d['password']}"})
    if not r.json(): raise HTTPException(401, "Неверные данные")
    return r.json()[0]

@app.post("/api/auth/request-verification")
async def req_ver(d: dict):
    email = d['email'].lower()
    code = str(random.randint(100000, 999999))
    await db.post("temp_codes", json={"email": email, "code": code, "type": "VERIFY", "expires_at": int(time.time()*1000)+600000}, headers={"Prefer": "resolution=merge-duplicates"})
    if EmailService.send_verification_code(email, code): return True
    raise HTTPException(500, "Ошибка почты")

@app.post("/api/auth/verify-and-register")
async def verify_reg(d: dict):
    email = d['email'].lower()
    r = await db.get("temp_codes", params={"email": f"eq.{email}", "code": f"eq.{d['code']}"})
    if not r.json(): raise HTTPException(400, "Неверный код")
    uid = f"u_{secrets.token_hex(4)}"
    p = {"id": uid, "username": d['username'], "email": email, "password": d['password'], "balance": 0, "license_expires_at": int(time.time()*1000) + 259200000}
    await db.post("users", json=p)
    return p

@app.post("/api/auth/forgot-password")
async def forgot(d: dict):
    email = d['email'].lower()
    r = await db.get("users", params={"email": f"eq.{email}"})
    if not r.json(): raise HTTPException(404)
    code = str(random.randint(100000, 999999))
    await db.post("temp_codes", json={"email": email, "code": code, "type": "RESET", "expires_at": int(time.time()*1000)+600000}, headers={"Prefer": "resolution=merge-duplicates"})
    EmailService.send_password_reset(email, code)
    return True

@app.post("/api/auth/reset-password")
async def reset(d: dict):
    email = d['email'].lower()
    r = await db.get("temp_codes", params={"email": f"eq.{email}", "code": f"eq.{d['code']}"})
    if not r.json(): raise HTTPException(400)
    await db.patch("users", params={"email": f"eq.{email}"}, json={"password": d['newPassword']})
    return True

# --- BOTS MANAGEMENT ---
@app.get("/api/bots/{uid}")
async def get_bots(uid: str):
    r = await db.get("bots", params={"owner_id": f"eq.{uid}"})
    return [{**b, **(b.get("config") or {})} for b in r.json()]

@app.post("/api/bots/save")
async def save_bot(b: dict):
    bid, owner = b['id'], b['owner_id']
    sys = ['id', 'owner_id', 'name', 'token', 'status', 'license_expires_at', 'config']
    cfg = {k: v for k, v in b.items() if k not in sys}
    p = {"id": bid, "owner_id": owner, "name": b["name"], "token": b["token"], "status": b.get("status", "IDLE"), "license_expires_at": int(b.get("license_expires_at") or 0), "config": cfg}
    await db.post("bots", json=p, headers={"Prefer": "resolution=merge-duplicates"})
    return {"status": "ok"}

@app.delete("/api/bots/delete/{uid}/{bid}")
async def del_bot(uid: str, bid: str):
    await pm.stop_bot(bid)
    await db.delete("bots", params={"id": f"eq.{bid}", "owner_id": f"eq.{uid}"})
    return {"status": "ok"}

@app.post("/api/bots/start")
async def start_bot(req: dict):
    r = await db.get("bots", params={"id": f"eq.{req['id']}"})
    if not r.json(): raise HTTPException(404)
    data = r.json()[0]
    merged = {**data, **(data.get("config") or {})}
    if await pm.start_bot(req['id'], merged) is True:
        await db.patch("bots", params={"id": f"eq.{req['id']}"}, json={"status": "RUNNING"})
        return True
    raise HTTPException(500)

@app.post("/api/bots/stop/{bid}")
async def stop_bot(bid: str):
    await pm.stop_bot(bid)
    await db.patch("bots", params={"id": f"eq.{bid}"}, json={"status": "IDLE"})
    return True

# --- CRM & UTILS ---
@app.get("/api/bots/logs/{bid}")
async def get_logs(bid: str): return {"logs": pm.get_logs(bid)}

@app.get("/api/bots/messages/{bid}")
async def get_msgs(bid: str):
    r = await db.get("bot_messages", params={"bot_id": f"eq.{bid}", "order": "created_at.desc", "limit": "50"})
    return [{"text": m["message_text"], "timestamp": m["created_at"], "is_admin": m["is_from_admin"], "user": {"name": m["first_name"]}} for m in r.json()][::-1]

@app.post("/api/admin/generate-key")
async def gen_key(req: dict, x_admin_token: str = Header(None)):
    if x_admin_token != A_SECRET: raise HTTPException(403)
    m, d = req.get('months', 1), req.get('days', 0)
    key = f"PRO-{m}M-{secrets.token_hex(4).upper()}"
    await db.post("issued_keys", json={"key": key, "months": m, "days": d, "used": False})
    return {"key": key}

@app.post("/api/bots/activate-license")
async def activate(req: dict):
    k = req['key']
    r = await db.get("issued_keys", params={"key": f"eq.{k}", "used": "eq.false"})
    if not r.json(): return {"status": "error", "message": "Ключ невалиден"}
    kd = r.json()[0]
    bid = req['botId']
    br = await db.get("bots", params={"id": f"eq.{bid}"})
    if not br.json(): return {"status": "error"}
    cur = max(br.json()[0].get("license_expires_at") or 0, int(time.time()*1000))
    add = (kd['months'] * 30 * 86400000) + (kd['days'] * 86400000)
    await db.patch("bots", params={"id": f"eq.{bid}"}, json={"license_expires_at": cur + add})
    await db.patch("issued_keys", params={"key": f"eq.{k}"}, json={"used": True, "used_by_bot": bid})
    return {"status": "ok"}

@app.get("/api/ping")
async def ping(): return {"status": "online"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
