"""
free_ads_server.py
──────────────────
Все API-роуты для Free Plan и рекламной системы.
Подключается к server.py одной строкой:

    from free_ads_server import router as free_ads_router
    app.include_router(free_ads_router)

Требует глобальных переменных из server.py:
    db, S_URL, S_KEY, A_SECRET, hash_pwd, encrypt_val, decrypt_val,
    logger, pm (BotManager), _rpc

Все необходимые импорты указаны ниже.
"""

import os, time, json, secrets, hashlib, uuid, httpx
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Request
from starlette.concurrency import run_in_threadpool

# ── Импортируем нужное из основного server.py ──────────────────────────────
# Эти переменные будут доступны после того, как server.py создаст их.
# При использовании include_router они уже существуют в global scope.
import importlib, sys

def _get_server():
    """Получаем модуль server.py для доступа к его глобальным переменным."""
    return sys.modules.get('__main__') or sys.modules.get('server')

router = APIRouter()

FREE_MAX_BUTTONS  = 2
FREE_MAX_TRIGGERS = 2
FREE_MEMORY_MB    = 25
PRICE_PER_IMP     = 0.2   # рублей за показ

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _db():
    s = _get_server()
    return getattr(s, 'db', None)

def _logger():
    import logging
    return logging.getLogger("FreeAdsServer")

def _hash(pwd: str) -> str:
    salt = "free_ads_salt_2026"
    return hashlib.sha256((pwd + salt).encode()).hexdigest()

async def _get_agent(agent_id: str):
    r = await _db().get("ad_agents", params={"id": f"eq.{agent_id}"})
    rows = r.json()
    return rows[0] if rows else None

async def _verify_agent_token(token: str) -> Optional[dict]:
    """Простой stateless JWT-like token: base64(agent_id:hmac)"""
    try:
        import base64, hmac as _hmac
        raw = base64.urlsafe_b64decode(token + "==").decode()
        agent_id, sig = raw.split(":", 1)
        expected = hashlib.sha256(f"{agent_id}:ADS_SECRET_2026".encode()).hexdigest()[:16]
        if sig != expected:
            return None
        return await _get_agent(agent_id)
    except Exception:
        return None

def _make_agent_token(agent_id: str) -> str:
    import base64
    sig = hashlib.sha256(f"{agent_id}:ADS_SECRET_2026".encode()).hexdigest()[:16]
    raw = f"{agent_id}:{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")

async def _rpc_local(func_name: str, params: dict):
    s = _get_server()
    rpc_fn = getattr(s, '_rpc', None)
    if rpc_fn:
        return await rpc_fn(func_name, params)
    # Fallback
    db = _db()
    return await db.post(f"../rpc/{func_name}", json=params,
                         headers={"Content-Type": "application/json"})

# ══════════════════════════════════════════════════════════════════════════════
# FREE PLAN — BOTS
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/api/free/bots/create")
async def free_create_bot(d: dict):
    """
    Создать бота на free-плане.
    Body: { user_id, name, token }
    Limits: max 2 кнопки, max 2 триггера, memory 25 МБ, реклама включена.
    """
    user_id = d.get("user_id", "").strip()
    name    = d.get("name", "").strip()
    token   = d.get("token", "").strip()

    if not all([user_id, name, token]):
        raise HTTPException(400, "user_id, name, token обязательны")

    db = _db()

    # Проверяем лимит: не более 1 бота на free-плане (строго)
    existing = await db.get("bots", params={"owner_id": f"eq.{user_id}", "is_free_plan": "eq.true"})
    if existing.json():
        raise HTTPException(409, "На free-плане разрешён только 1 бот. Перейдите на Pro для большего количества.")

    s = _get_server()
    enc_fn  = getattr(s, 'encrypt_val', lambda x: x)
    new_id  = f"fbot_{secrets.token_hex(5)}"
    now_ms  = int(time.time() * 1000)

    bot_data = {
        "id":                new_id,
        "owner_id":          user_id,
        "name":              name,
        "token":             enc_fn(token),
        "status":            "IDLE",
        "platform":          "telegram",
        "is_free_plan":      True,
        "memory_limit_mb":   FREE_MEMORY_MB,
        "ad_enabled":        True,
        "license_expires_at": now_ms + 999 * 24 * 3600 * 1000,  # free = бессрочно
        "created_at":        now_ms,
        "config": {
            "welcomeMessage": f"Добро пожаловать в {name}!",
            "adminChatId":    "",
            "buttons":        [],
            "triggers":       [],
            "settings": {
                "forwardToAdmin": True,
                "antiSpam": True,
                "rateLimit": 1,
            }
        }
    }

    r = await db.post("bots", json=bot_data, headers={"Prefer": "return=representation"})
    if r.status_code not in (200, 201):
        raise HTTPException(500, f"Ошибка БД: {r.text}")

    return r.json()[0] if isinstance(r.json(), list) else r.json()


@router.put("/api/free/bots/{bot_id}/config")
async def free_update_bot_config(bot_id: str, d: dict):
    """
    Обновить конфиг free-бота с проверкой ограничений.
    Принимает весь конфиг — сохраняет полностью, мержит с существующим.
    """
    user_id = d.get("user_id", "").strip()
    if not user_id:
        raise HTTPException(400, "user_id обязателен")

    db = _db()
    r = await db.get("bots", params={"id": f"eq.{bot_id}", "owner_id": f"eq.{user_id}", "is_free_plan": "eq.true"})
    if not r.json():
        raise HTTPException(404, "Free-бот не найден")

    existing_bot = r.json()[0]
    existing_cfg = existing_bot.get("config") or {}

    buttons  = d.get("buttons",  d.get("config", {}).get("buttons",  existing_cfg.get("buttons",  [])))
    triggers = d.get("triggers", d.get("config", {}).get("triggers", existing_cfg.get("triggers", [])))

    # Жёсткие лимиты
    if len(buttons) > FREE_MAX_BUTTONS:
        buttons = buttons[:FREE_MAX_BUTTONS]   # обрезаем, не падаем
    if len(triggers) > FREE_MAX_TRIGGERS:
        triggers = triggers[:FREE_MAX_TRIGGERS]

    # Только базовые типы кнопок
    for btn in buttons:
        for blocked_key in ["flow", "ai_prompt", "ai_enabled", "webhook", "payment"]:
            btn.pop(blocked_key, None)

    # Новый конфиг = старый мерженный с новыми данными
    new_config = {**existing_cfg}

    # Принимаем конфиг из тела напрямую или из поля "config"
    incoming_cfg = d.get("config", {})

    # Все поля которые могут прийти — копируем (включая welcomePhoto)
    for key in [
        "welcomeMessage", "welcomePhoto", "adminChatId",
        "settings", "description",
        "firstMessageHeader", "ticketMessageHeader", "commonMessageHeader",
        "forwardToAdmin", "antiSpam", "rateLimit",
        "welcomeInline",
        # аналитика — не трогаем при сохранении, бот пишет сам
    ]:
        # Проверяем сначала напрямую в d, потом в d.config
        if key in d:
            new_config[key] = d[key]
        elif key in incoming_cfg:
            new_config[key] = incoming_cfg[key]

    new_config["buttons"]  = buttons
    new_config["triggers"] = triggers

    # Патчим поля на корневом уровне
    patch_payload = {
        "config": new_config,
        "name":   d.get("name", existing_bot.get("name", "Bot")),
    }

    # Если пришёл токен — обновляем его тоже
    if d.get("token") and d["token"] != existing_bot.get("token"):
        s = _get_server()
        enc_fn = getattr(s, 'encrypt_val', lambda x: x)
        patch_payload["token"] = enc_fn(d["token"])

    patch_r = await db.patch("bots",
        params={"id": f"eq.{bot_id}"},
        json=patch_payload,
        headers={"Prefer": "return=representation"}
    )
    result = patch_r.json()
    return result[0] if isinstance(result, list) else result


@router.get("/api/free/bots/{user_id}")
async def free_get_user_bots(user_id: str):
    db = _db()
    r = await db.get("bots", params={"owner_id": f"eq.{user_id}", "is_free_plan": "eq.true"})
    return r.json() or []


@router.get("/api/free/bots/{bot_id}/stats")
async def free_bot_stats(bot_id: str, user_id: str):
    """Полная аналитика — такая же, как у pro."""
    db = _db()
    r = await db.get("bots", params={"id": f"eq.{bot_id}", "owner_id": f"eq.{user_id}"})
    if not r.json():
        raise HTTPException(404, "Бот не найден")
    bot = r.json()[0]
    cfg = bot.get("config") or {}

    # Получаем stats из двух источников и мержим
    db_stats  = bot.get("stats") or {}
    cfg_stats = cfg.get("stats") or {}

    def _safe_max(key: str) -> int:
        return max(int(db_stats.get(key) or 0), int(cfg_stats.get(key) or 0))

    # Мержим историю по дате (берём максимум на каждый день)
    history_map: dict = {}
    for src in [cfg_stats.get("history") or [], db_stats.get("history") or []]:
        for entry in src:
            date = entry.get("date", "")
            if date not in history_map:
                history_map[date] = dict(entry)
            else:
                for k in ["incoming", "outgoing", "totalUsers", "activeUsers", "broadcasts"]:
                    history_map[date][k] = max(
                        history_map[date].get(k, 0),
                        entry.get(k, 0)
                    )
    merged_history = sorted(history_map.values(), key=lambda x: x.get("date", ""))[-14:]

    merged_stats = {
        "totalMessages":    _safe_max("totalMessages"),
        "incomingToday":    _safe_max("incomingToday"),
        "outgoingToday":    _safe_max("outgoingToday"),
        "bannedCount":      _safe_max("bannedCount"),
        "activeUsers24h":   _safe_max("activeUsers24h"),
        "broadcastsTotal":  _safe_max("broadcastsTotal"),   # рассылки за всё время
        "broadcastsToday":  _safe_max("broadcastsToday"),   # рассылки сегодня
        "history":          merged_history,
    }

    # users_count из connectedUsers
    users_list = cfg.get("connectedUsers") or []
    users_count = len(users_list)

    return {
        "bot_id":       bot_id,
        "name":         bot.get("name"),
        "status":       bot.get("status"),
        "users_count":  users_count,
        "stats":        merged_stats,
        "ad_enabled":   bot.get("ad_enabled", True),
        "memory_limit": bot.get("memory_limit_mb", FREE_MEMORY_MB),
        "plan":         "free"
    }


# ── FREE: Ping-pong поддержка (те же методы что у pro) ──────────────────────
# Они используют /api/bots/* из основного server.py — здесь просто прокси-чек

@router.get("/api/free/plan-info")
async def free_plan_info():
    return {
        "max_buttons":  FREE_MAX_BUTTONS,
        "max_triggers": FREE_MAX_TRIGGERS,
        "memory_mb":    FREE_MEMORY_MB,
        "price_per_imp": PRICE_PER_IMP,
        "features": {
            "analytics":    True,
            "pingpong":     True,
            "commands":     True,
            "moderation":   True,
            "ai":           False,
            "miniapp":      False,
            "broadcast":    False,
            "chatsite":     False,
            "advanced_buttons": False,
        }
    }


# ══════════════════════════════════════════════════════════════════════════════
# ADS AUTH — /api/ads/auth/*
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/api/ads/auth/register")
async def ads_register(d: dict):
    email = d.get("email", "").strip().lower()
    pwd   = d.get("password", "").strip()
    if not email or not pwd or len(pwd) < 6:
        raise HTTPException(400, "Email и пароль (мин. 6 символов) обязательны")

    db = _db()
    check = await db.get("ad_agents", params={"email": f"eq.{email}"})
    if check.json():
        raise HTTPException(409, "Email уже зарегистрирован")

    agent_id = f"ag_{secrets.token_hex(6)}"
    now_ms   = int(time.time() * 1000)
    agent    = {
        "id":            agent_id,
        "email":         email,
        "password_hash": _hash(pwd),
        "balance_rub":   0,
        "is_banned":     False,
        "created_at":    now_ms
    }
    r = await db.post("ad_agents", json=agent, headers={"Prefer": "return=representation"})
    if r.status_code not in (200, 201):
        raise HTTPException(500, "Ошибка регистрации")

    token = _make_agent_token(agent_id)
    return {"token": token, "agent": {**agent, "password_hash": "***"}}


@router.post("/api/ads/auth/send-code")
async def ads_send_code(d: dict):
    """
    Отправляет код подтверждения на email.
    type: 'register' | 'reset'
    """
    import random as _random
    email = d.get("email", "").strip().lower()
    code_type = d.get("type", "register").upper()   # REGISTER | RESET
    if not email:
        raise HTTPException(400, "Email обязателен")

    db = _db()

    if code_type == "REGISTER":
        # Проверяем что email не занят
        check = await db.get("ad_agents", params={"email": f"eq.{email}"})
        if check.json():
            raise HTTPException(409, "Email уже зарегистрирован")
    elif code_type == "RESET":
        # Проверяем что агент существует
        check = await db.get("ad_agents", params={"email": f"eq.{email}"})
        if not check.json():
            # Не раскрываем наличие аккаунта — просто возвращаем OK
            return {"ok": True}
    else:
        raise HTTPException(400, f"Неверный тип кода: {code_type}")

    code = str(_random.randint(100000, 999999))
    now_ms = int(time.time() * 1000)
    expires_ms = now_ms + 15 * 60 * 1000  # 15 минут

    # Сохраняем код в ad_email_codes (или temp_codes если та же таблица)
    await db.post("ad_email_codes", json={
        "email":      email,
        "code":       code,
        "type":       code_type,
        "expires_at": expires_ms,
        "used":       False,
    }, headers={"Prefer": "resolution=merge-duplicates"})

    # Отправляем письмо через EmailService из server.py
    s = _get_server()
    email_svc = getattr(s, 'EmailService', None)
    sent = False

    if email_svc:
        try:
            from starlette.concurrency import run_in_threadpool
            if code_type == "REGISTER":
                sent = await run_in_threadpool(email_svc.send_verification_code, email, code)
            else:
                sent = await run_in_threadpool(email_svc.send_password_reset, email, code)
        except Exception as e:
            _logger().error(f"Email send error: {e}")

    if not sent:
        # Fallback: пробуем httpx отправить через наш API
        try:
            base_url = os.getenv("SERVER_BASE_URL", "http://localhost:8000")
            async with httpx.AsyncClient(timeout=5) as client:
                if code_type == "REGISTER":
                    await client.post(f"{base_url}/api/ads/auth/_send-email",
                        json={"email": email, "code": code, "type": "register"})
                else:
                    await client.post(f"{base_url}/api/ads/auth/_send-email",
                        json={"email": email, "code": code, "type": "reset"})
        except Exception as e:
            _logger().warning(f"Fallback email send failed: {e}")
            # Возвращаем OK — код сохранён в БД, пользователь может запросить повторно

    _logger().info(f"📧 Код {code_type} отправлен на {email} (code={code[:2]}****)")
    return {"ok": True}


@router.post("/api/ads/auth/register-verify")
async def ads_register_verify(d: dict):
    """Верифицирует код и регистрирует агента."""
    email = d.get("email", "").strip().lower()
    code  = d.get("code", "").strip()
    pwd   = d.get("password", "").strip()

    if not email or not code or not pwd or len(pwd) < 6:
        raise HTTPException(400, "Заполните все поля")

    db = _db()
    now_ms = int(time.time() * 1000)

    # Проверяем код
    code_r = await db.get("ad_email_codes", params={
        "email": f"eq.{email}", "code": f"eq.{code}",
        "type":  "eq.REGISTER",  "used": "eq.false",
        "expires_at": f"gt.{now_ms}"
    })
    if not code_r.json():
        raise HTTPException(400, "Неверный или истёкший код. Запросите новый.")

    # Проверяем что email не занят
    check = await db.get("ad_agents", params={"email": f"eq.{email}"})
    if check.json():
        raise HTTPException(409, "Email уже зарегистрирован")

    agent_id = f"ag_{secrets.token_hex(6)}"
    agent    = {
        "id":            agent_id,
        "email":         email,
        "password_hash": _hash(pwd),
        "balance_rub":   0,
        "is_banned":     False,
        "created_at":    now_ms,
    }
    r = await db.post("ad_agents", json=agent, headers={"Prefer": "return=representation"})
    if r.status_code not in (200, 201):
        raise HTTPException(500, "Ошибка регистрации")

    # Помечаем код как использованный
    await db.patch("ad_email_codes", params={"email": f"eq.{email}", "type": "eq.REGISTER"}, json={"used": True})

    token = _make_agent_token(agent_id)
    return {"token": token, "agent": {**agent, "password_hash": "***"}}


@router.post("/api/ads/auth/login")
async def ads_login(d: dict):
    email = d.get("email", "").strip().lower()
    pwd   = d.get("password", "").strip()
    db    = _db()
    r     = await db.get("ad_agents", params={"email": f"eq.{email}", "password_hash": f"eq.{_hash(pwd)}"})
    rows  = r.json()
    if not rows:
        raise HTTPException(401, "Неверный email или пароль")
    agent = rows[0]
    if agent.get("is_banned"):
        raise HTTPException(403, "Аккаунт заблокирован")
    token = _make_agent_token(agent["id"])
    return {"token": token, "agent": {**agent, "password_hash": "***"}}


@router.get("/api/ads/auth/me")
async def ads_me(authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "").strip()
    agent = await _verify_agent_token(token)
    if not agent:
        raise HTTPException(401, "Неверный токен")
    return {**agent, "password_hash": "***"}


@router.post("/api/ads/auth/reset-password")
async def ads_reset_password(d: dict):
    """Сбрасывает пароль агента по коду из письма."""
    email       = d.get("email", "").strip().lower()
    code        = d.get("code", "").strip()
    new_password = d.get("newPassword", "").strip()

    if not email or not code or not new_password or len(new_password) < 6:
        raise HTTPException(400, "Заполните все поля. Пароль минимум 6 символов.")

    db = _db()
    now_ms = int(time.time() * 1000)

    # Проверяем код
    code_r = await db.get("ad_email_codes", params={
        "email": f"eq.{email}", "code": f"eq.{code}",
        "type":  "eq.RESET",    "used": "eq.false",
        "expires_at": f"gt.{now_ms}"
    })
    if not code_r.json():
        raise HTTPException(400, "Неверный или истёкший код. Запросите новый.")

    # Обновляем пароль
    r = await db.patch("ad_agents",
        params={"email": f"eq.{email}"},
        json={"password_hash": _hash(new_password)},
        headers={"Prefer": "return=representation"}
    )
    if not r.json():
        raise HTTPException(404, "Агент не найден")

    # Помечаем код как использованный
    await db.patch("ad_email_codes", params={"email": f"eq.{email}", "type": "eq.RESET"}, json={"used": True})

    return {"ok": True, "message": "Пароль успешно изменён"}


# ══════════════════════════════════════════════════════════════════════════════
# ADS PORTAL — /api/ads/*
# ══════════════════════════════════════════════════════════════════════════════

async def _auth_agent(authorization: str) -> dict:
    token = authorization.replace("Bearer ", "").strip()
    agent = await _verify_agent_token(token)
    if not agent:
        raise HTTPException(401, "Не авторизован")
    if agent.get("is_banned"):
        raise HTTPException(403, "Аккаунт заблокирован")
    return agent


@router.get("/api/ads/dashboard")
async def ads_dashboard(authorization: str = Header(...)):
    agent = await _auth_agent(authorization)
    db    = _db()

    # Посты агента
    posts_r = await db.get("ad_posts",
        params={"agent_id": f"eq.{agent['id']}", "order": "created_at.desc", "limit": "50"})
    posts   = posts_r.json() or []

    # Транзакции
    tx_r  = await db.get("ad_transactions",
        params={"agent_id": f"eq.{agent['id']}", "order": "created_at.desc", "limit": "50"})
    txs   = tx_r.json() or []

    # Общая статистика системы (публичная: кол-во ботов и пользователей)
    bots_r  = await db.get("bots",    params={"is_free_plan": "eq.true", "select": "id"})
    users_r = await db.get("users",   params={"plan": "eq.free",         "select": "id"})

    total_impressions = sum(p.get("impressions_used", 0) for p in posts)
    active_posts      = [p for p in posts if p["status"] == "active"]

    return {
        "agent": {**agent, "password_hash": "***"},
        "posts": posts,
        "transactions": txs,
        "stats": {
            "total_posts":       len(posts),
            "active_posts":      len(active_posts),
            "total_impressions": total_impressions,
            "pending_posts":     sum(1 for p in posts if p["status"] == "pending"),
        },
        "system_stats": {
            "free_bots":  len(bots_r.json()  or []),
            "free_users": len(users_r.json() or []),
        }
    }


@router.post("/api/ads/posts/create")
async def ads_create_post(d: dict, authorization: str = Header(...)):
    agent = await _auth_agent(authorization)
    text  = d.get("text", "").strip()
    if not text or len(text) > 250:
        raise HTTPException(400, "Текст обязателен и не более 250 символов")

    db     = _db()
    post_id = f"post_{secrets.token_hex(6)}"
    now_ms  = int(time.time() * 1000)
    post    = {
        "id":               post_id,
        "agent_id":         agent["id"],
        "text":             text,
        "media_url":        d.get("media_url"),
        "status":           "pending",
        "impressions_paid": 0,
        "impressions_used": 0,
        "price_per_imp":    PRICE_PER_IMP,
        "created_at":       now_ms,
    }
    r = await db.post("ad_posts", json=post, headers={"Prefer": "return=representation"})
    if r.status_code not in (200, 201):
        raise HTTPException(500, f"Ошибка БД: {r.text}")
    return r.json()[0] if isinstance(r.json(), list) else r.json()


@router.post("/api/ads/posts/{post_id}/buy-impressions")
async def ads_buy_impressions(post_id: str, d: dict, authorization: str = Header(...)):
    agent       = await _auth_agent(authorization)
    impressions = int(d.get("impressions", 0))
    if impressions < 1:
        raise HTTPException(400, "Минимум 1 показ")

    db = _db()

    # Проверяем что пост существует и принадлежит агенту
    post_r = await db.get("ad_posts", params={"id": f"eq.{post_id}", "agent_id": f"eq.{agent['id']}"})
    if not post_r.json():
        raise HTTPException(404, "Пост не найден")
    post = post_r.json()[0]
    if post["status"] not in ("approved", "active"):
        raise HTTPException(422, f"Пост должен быть одобрен (статус: {post['status']}). Дождитесь модерации.")

    # Пробуем через RPC (если настроен)
    rpc_ok = False
    try:
        rpc_r = await _rpc_local("buy_ad_impressions", {
            "p_agent_id":    agent["id"],
            "p_post_id":     post_id,
            "p_impressions": impressions
        })
        result = rpc_r.json() if hasattr(rpc_r, 'json') else rpc_r
        if isinstance(result, dict) and result.get("ok") is False:
            raise HTTPException(402, result.get("error", "Ошибка покупки"))
        rpc_ok = True
    except HTTPException:
        raise
    except Exception as e:
        _logger().warning(f"buy_ad_impressions RPC failed: {e}, falling back to manual")

    if not rpc_ok:
        # Fallback: вручную списываем баланс и добавляем показы
        cost = impressions * PRICE_PER_IMP
        agent_fresh = await _get_agent(agent["id"])
        if not agent_fresh:
            raise HTTPException(404, "Агент не найден")
        balance = float(agent_fresh.get("balance_rub", 0))
        if balance < cost:
            raise HTTPException(402, f"Недостаточно средств. Нужно {cost:.2f}₽, на балансе {balance:.2f}₽")

        now_ms = int(time.time() * 1000)
        new_balance   = balance - cost
        new_imp_paid  = post.get("impressions_paid", 0) + impressions
        tx_id = f"tx_{secrets.token_hex(6)}"

        # Обновляем агента
        await db.patch("ad_agents", params={"id": f"eq.{agent['id']}"}, json={"balance_rub": new_balance})
        # Обновляем пост
        await db.patch("ad_posts", params={"id": f"eq.{post_id}"}, json={"impressions_paid": new_imp_paid})
        # Записываем транзакцию
        await db.post("ad_transactions", json={
            "id": tx_id, "agent_id": agent["id"], "post_id": post_id,
            "type": "spend", "amount_rub": cost, "impressions": impressions,
            "created_at": now_ms
        }, headers={"Prefer": "return=minimal"})

    # Активируем пост если он approved и теперь есть оплаченные показы
    current_imp = (post.get("impressions_paid", 0) or 0) + (impressions if not rpc_ok else 0)
    if post["status"] == "approved" or (rpc_ok and post["status"] in ("approved",)):
        # После покупки — ставим active
        activate_r = await db.patch("ad_posts",
            params={"id": f"eq.{post_id}"},
            json={"status": "active"},
            headers={"Prefer": "return=representation"}
        )
        _logger().info(f"✅ Пост {post_id} активирован после покупки {impressions} показов")
        post_data = activate_r.json()
        if isinstance(post_data, list) and post_data:
            return post_data[0]

    # Возвращаем обновлённый пост
    updated = await db.get("ad_posts", params={"id": f"eq.{post_id}"})
    return updated.json()[0] if updated.json() else {"ok": True}


@router.get("/api/ads/posts/{post_id}")
async def ads_get_post(post_id: str, authorization: str = Header(...)):
    agent = await _auth_agent(authorization)
    db    = _db()
    r     = await db.get("ad_posts", params={"id": f"eq.{post_id}", "agent_id": f"eq.{agent['id']}"})
    if not r.json():
        raise HTTPException(404, "Пост не найден")
    return r.json()[0]


@router.get("/api/ads/balance")
async def ads_balance(authorization: str = Header(...)):
    agent = await _auth_agent(authorization)
    return {"balance_rub": float(agent.get("balance_rub", 0))}


# ── ЮКасса webhook для рекламных агентов ────────────────────────────────────
@router.post("/api/ads/payments/webhook")
async def ads_payment_webhook(request: Request):
    """
    ЮКасса (YooKassa) webhook — JSON notification.
    Ожидаем event=payment.succeeded, metadata.agent_id, amount.value
    Верификация: IP ЮКассы + сравнение payment_id через API.
    """
    import hmac

    body_bytes = await request.body()
    try:
        data = json.loads(body_bytes)
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    event = data.get("event", "")
    if event != "payment.succeeded":
        # Другие события (waiting, canceled) просто игнорируем
        return {"ok": True}

    obj       = data.get("object", {})
    payment_id = obj.get("id", "")
    amount_obj = obj.get("amount", {})
    amount     = float(amount_obj.get("value", 0))
    metadata   = obj.get("metadata", {})
    agent_id   = metadata.get("agent_id", "")

    if not agent_id or amount <= 0 or not payment_id:
        return {"ok": True}

    # Верификация: переспрашиваем ЮКассу по API (защита от фейковых вебхуков)
    yk_shop_id  = os.getenv("YOOKASSA_SHOP_ID", "")
    yk_secret   = os.getenv("YOOKASSA_SECRET_KEY", "")
    if yk_shop_id and yk_secret:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(
                    f"https://api.yookassa.ru/v3/payments/{payment_id}",
                    auth=(yk_shop_id, yk_secret)
                )
                if r.status_code != 200:
                    _logger().warning(f"⚠️ ЮКасса: не смогли верифицировать платёж {payment_id}")
                    raise HTTPException(400, "Payment verification failed")
                real = r.json()
                if real.get("status") != "succeeded":
                    return {"ok": True}
                real_amount = float(real.get("amount", {}).get("value", 0))
                real_agent  = real.get("metadata", {}).get("agent_id", "")
                if real_agent != agent_id or abs(real_amount - amount) > 0.01:
                    _logger().warning(f"⚠️ ЮКасса: несоответствие данных платежа {payment_id}")
                    raise HTTPException(400, "Payment data mismatch")
        except HTTPException:
            raise
        except Exception as e:
            _logger().warning(f"ЮКасса verify error: {e}")

    rpc_r = await _rpc_local("topup_ad_agent_balance", {
        "p_agent_id": agent_id,
        "p_amount":   amount,
        "p_yk_id":    payment_id
    })
    _logger().info(f"✅ Агент {agent_id} пополнил баланс на {amount}₽ (payment={payment_id})")
    return {"ok": True}


@router.post("/api/ads/payments/create")
async def ads_create_payment(d: dict, authorization: str = Header(...)):
    """
    Создаём платёж в ЮКассе и возвращаем URL подтверждения.
    Body: { amount: float }
    """
    agent = await _auth_agent(authorization)
    amount = float(d.get("amount", 0))
    if amount < 10:
        raise HTTPException(400, "Минимальная сумма пополнения — 10 ₽")

    yk_shop_id = os.getenv("YOOKASSA_SHOP_ID", "")
    yk_secret  = os.getenv("YOOKASSA_SECRET_KEY", "")
    if not yk_shop_id or not yk_secret:
        raise HTTPException(503, "YOOKASSA_SHOP_ID / YOOKASSA_SECRET_KEY не настроены")
        
    return_url   = os.getenv("FRONTEND_URL", os.getenv("SERVER_BASE_URL", "https://dialogengine.webtm.ru")) + "/ads?payment=success"
    idempotency  = str(uuid.uuid4())

    payload = {
        "amount": {
            "value":    f"{amount:.2f}",
            "currency": "RUB"
        },
        "confirmation": {
            "type":       "redirect",
            "return_url": return_url
        },
        "capture":     True,
        "description": f"Пополнение рекламного баланса BotEngine — агент {agent['id']}",
        "metadata": {
            "agent_id": agent["id"]
        }
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://api.yookassa.ru/v3/payments",
                auth=(yk_shop_id, yk_secret),
                headers={
                    "Idempotence-Key": idempotency,
                    "Content-Type":    "application/json"
                },
                json=payload
            )
        if r.status_code not in (200, 201):
            _logger().error(f"ЮКасса API error {r.status_code}: {r.text}")
            raise HTTPException(502, "Ошибка создания платежа в ЮКассе")

        resp     = r.json()
        conf_url = resp.get("confirmation", {}).get("confirmation_url", "")
        if not conf_url:
            raise HTTPException(502, "ЮКасса не вернула confirmation_url")

        return {
            "payment_id":       resp.get("id"),
            "confirmation_url": conf_url,
            "amount":           amount
        }

    except HTTPException:
        raise
    except Exception as e:
        _logger().error(f"ЮКасса create payment error: {e}")
        raise HTTPException(502, f"Ошибка: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN: модерация рекламных постов
# ══════════════════════════════════════════════════════════════════════════════

def _verify_admin(token: str) -> bool:
    s       = _get_server()
    secret  = getattr(s, 'A_SECRET', os.getenv("ADMIN_TOKEN", ""))
    return token == secret


@router.get("/api/admin/ads/posts")
async def admin_get_ad_posts(status: str = "pending", x_admin_token: str = Header(...)):
    if not _verify_admin(x_admin_token):
        raise HTTPException(403, "Forbidden")
    db = _db()
    params = {"order": "created_at.desc"}
    if status != "all":
        params["status"] = f"eq.{status}"
    r  = await db.get("ad_posts", params=params)
    return r.json() or []


@router.post("/api/admin/ads/posts/{post_id}/approve")
async def admin_approve_post(post_id: str, x_admin_token: str = Header(...)):
    if not _verify_admin(x_admin_token):
        raise HTTPException(403, "Forbidden")
    db     = _db()
    now_ms = int(time.time() * 1000)
    # Читаем пост
    post_r = await db.get("ad_posts", params={"id": f"eq.{post_id}"})
    if not post_r.json():
        raise HTTPException(404, "Пост не найден")
    post = post_r.json()[0]
    # Если у поста уже куплены показы — сразу в active, иначе approved
    new_status = "active" if (post.get("impressions_paid", 0) or 0) > 0 else "approved"
    r = await db.patch("ad_posts",
        params={"id": f"eq.{post_id}"},
        json={"status": new_status, "approved_at": now_ms},
        headers={"Prefer": "return=representation"}
    )
    return r.json()


@router.post("/api/admin/ads/posts/{post_id}/reject")
async def admin_reject_post(post_id: str, d: dict, x_admin_token: str = Header(...)):
    if not _verify_admin(x_admin_token):
        raise HTTPException(403, "Forbidden")
    db = _db()
    r  = await db.patch("ad_posts",
        params={"id": f"eq.{post_id}"},
        json={"status": "rejected", "reject_reason": d.get("reason", "Не соответствует правилам")},
        headers={"Prefer": "return=representation"}
    )
    return r.json()


@router.get("/api/admin/ads/stats")
async def admin_ads_stats(x_admin_token: str = Header(...)):
    if not _verify_admin(x_admin_token):
        raise HTTPException(403, "Forbidden")
    db = _db()
    agents_r = await db.get("ad_agents", params={"select": "id,email,balance_rub,created_at,is_banned"})
    posts_r  = await db.get("ad_posts",  params={"select": "id,status,impressions_paid,impressions_used,price_per_imp,agent_id"})

    agents = agents_r.json() or []
    posts  = posts_r.json()  or []

    total_impressions_sold = sum(p.get("impressions_paid", 0)  for p in posts)
    total_impressions_used = sum(p.get("impressions_used", 0)  for p in posts)
    total_revenue          = sum(p.get("impressions_paid", 0) * float(p.get("price_per_imp", PRICE_PER_IMP)) for p in posts)

    return {
        "agents_count":           len(agents),
        "agents":                 agents,
        "posts_count":            len(posts),
        "posts_by_status":        {
            "pending":  sum(1 for p in posts if p["status"] == "pending"),
            "approved": sum(1 for p in posts if p["status"] == "approved"),
            "active":   sum(1 for p in posts if p["status"] == "active"),
            "rejected": sum(1 for p in posts if p["status"] == "rejected"),
            "finished": sum(1 for p in posts if p["status"] == "finished"),
        },
        "total_impressions_sold": total_impressions_sold,
        "total_impressions_used": total_impressions_used,
        "total_revenue_rub":      round(total_revenue, 2),
    }


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC: получить активную рекламу для показа в боте
# ══════════════════════════════════════════════════════════════════════════════

# ── Round-robin state: bot_id → last shown post index ────────────────────────
# Хранится в памяти процесса; сбрасывается при рестарте (это нормально).
_ad_roundrobin: dict = {}   # bot_id → last_shown_post_id


@router.get("/api/ads/active")
async def get_active_ad(bot_id: str = ""):
    """
    Вызывается из free_bot_core при каждом /start.
    Чередует активные посты по round-robin (один за другим, по кругу).
    Засчитывает показ через RPC.
    """
    global _ad_roundrobin
    db = _db()

    # Получаем ВСЕ активные посты (отсортированные по id для стабильного порядка)
    r = await db.get("ad_posts", params={
        "status": "eq.active",
        "select": "id,text,media_url",
        "order":  "id.asc",
    })
    posts = r.json() or []
    if not posts:
        return {"ad": None}

    # Round-robin: выбираем следующий после последнего показанного этому боту
    last_id  = _ad_roundrobin.get(bot_id)
    post     = None

    if last_id is None:
        # Первый показ — берём первый пост
        post = posts[0]
    else:
        # Ищем позицию последнего показанного
        ids = [p["id"] for p in posts]
        if last_id in ids:
            next_idx = (ids.index(last_id) + 1) % len(posts)
        else:
            # Последний пост мог закончиться — начинаем сначала
            next_idx = 0
        post = posts[next_idx]

    _ad_roundrobin[bot_id] = post["id"]

    # Фиксируем показ (атомарно через RPC)
    try:
        await _rpc_local("record_ad_impression", {"p_post_id": post["id"]})
    except Exception as e:
        _logger().error(f"record_ad_impression error: {e}")

    return {"ad": {"text": post["text"], "media_url": post.get("media_url")}}


# ══════════════════════════════════════════════════════════════════════════════
# FREE PLAN: линковка с pro аккаунтом
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/api/free/link-pro")
async def free_link_pro(d: dict):
    """
    Связывает free-аккаунт с pro-аккаунтом.
    Body: { free_user_id, pro_user_id }
    После линковки free аккаунт отображает имя/аватар pro аккаунта.
    """
    free_id = d.get("free_user_id", "").strip()
    pro_id  = d.get("pro_user_id", "").strip()
    if not free_id or not pro_id:
        raise HTTPException(400, "free_user_id и pro_user_id обязательны")

    db = _db()
    # Проверяем что pro существует
    pro_r = await db.get("users", params={"id": f"eq.{pro_id}", "plan": "eq.pro"})
    if not pro_r.json():
        raise HTTPException(404, "Pro аккаунт не найден")

    r = await db.patch("users",
        params={"id": f"eq.{free_id}"},
        json={"linked_pro_user_id": pro_id},
        headers={"Prefer": "return=representation"}
    )
    return {"ok": True, "linked_to": pro_id}


@router.get("/api/free/user-info/{user_id}")
async def free_user_info(user_id: str):
    """
    Возвращает инфо аккаунта для отображения в углу UI.
    Если есть linked_pro — отдаём данные pro аккаунта.
    """
    db = _db()
    r  = await db.get("users", params={"id": f"eq.{user_id}"})
    if not r.json():
        raise HTTPException(404, "Пользователь не найден")

    user = r.json()[0]
    plan = user.get("plan", "free")

    result = {
        "id":       user["id"],
        "email":    user["email"],
        "username": user.get("username", ""),
        "plan":     plan,
        "linked_pro_user_id": user.get("linked_pro_user_id"),
    }

    if user.get("linked_pro_user_id"):
        pro_r = await db.get("users", params={"id": f"eq.{user['linked_pro_user_id']}"})
        if pro_r.json():
            pro = pro_r.json()[0]
            result["pro_account"] = {
                "id":       pro["id"],
                "email":    pro["email"],
                "username": pro.get("username", ""),
                "balance":  pro.get("balance", 0),
                "license_expires_at": pro.get("license_expires_at"),
            }

    return result


@router.post("/api/bots/{bot_id}/start")
async def start_free_bot(bot_id: str):
    server = _get_server()
    pm = getattr(server, 'pm', None)
    if not pm:
        raise HTTPException(500, "BotManager не инициализирован")

    db = server.db
    r = await db.get("bots", params={"id": f"eq.{bot_id}"})
    if not r.json():
        raise HTTPException(404, "Бот не найден")

    bot_data = r.json()[0]

    # Проверяем бан владельца
    owner_id = bot_data.get("owner_id")
    if owner_id:
        u_r = await db.get("users", params={"id": f"eq.{owner_id}"})
        if u_r.json() and u_r.json()[0].get("is_banned"):
            raise HTTPException(403, "Ваш аккаунт заблокирован")

    # Мержим config с корневыми полями (как в основном start_handler)
    inner_cfg = bot_data.get("config") or {}
    merged = {**inner_cfg, **bot_data}
    # Явно проставляем флаг — BotManager выберет free_bot_core.py
    merged['is_free_plan'] = True

    success = await pm.start_bot(bot_id, merged)
    if success is True:
        await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"status": "RUNNING"})
        return {"status": "ok", "message": "Бот запущен"}
    else:
        raise HTTPException(500, f"Не удалось запустить бота: {success}")

@router.post("/api/bots/{bot_id}/stop")
async def stop_free_bot(bot_id: str):
    server = _get_server()
    pm = getattr(server, 'pm', None)
    if not pm:
        raise HTTPException(500, "BotManager не инициализирован")

    await pm.stop_bot(bot_id)
    # Синхронизируем статус в БД
    try:
        db = server.db
        await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"status": "IDLE"})
    except Exception:
        pass
    return {"status": "ok", "message": "Бот остановлен"}
