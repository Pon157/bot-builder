"""
free_ads_server.py
──────────────────
ИСПРАВЛЕНИЯ v6:
  • Добавлены эндпоинты для VK-ботов free-плана (/api/free/vk/bots/*).
  • free_update_bot_config: теперь сохраняет inlineButtons в корень config.
  • Все исправления v5 сохранены.

ИСПРАВЛЕНИЯ v5:
  • free_update_bot_config — buttons/triggers сохраняются В КОРЕНЬ config,
    а не только внутри nested объекта. free_bot_core читает их именно оттуда.
  • free_create_bot — buttons/triggers сохраняются правильно.
  • start_free_bot — передаёт конфиг с кнопками/триггерами из корня config.
  • free_bot_stats — корректно читает users_count из connectedUsers.
"""

import os, time, json, secrets, hashlib, uuid, httpx
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Request
from starlette.concurrency import run_in_threadpool

import importlib, sys

def _get_server():
    return sys.modules.get('__main__') or sys.modules.get('server')

router = APIRouter()

FREE_MAX_BUTTONS  = 9999
FREE_MAX_TRIGGERS = 9999
FREE_MEMORY_MB    = 0
PRICE_PER_IMP     = 0.2

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
    ИСПРАВЛЕНО: buttons/triggers сохраняются в корень config (не вложенно).
    """
    user_id = d.get("user_id", "").strip()
    name    = d.get("name", "").strip()
    token   = d.get("token", "").strip()

    if not all([user_id, name, token]):
        raise HTTPException(400, "user_id, name, token обязательны")

    db = _db()

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
        "memory_limit_mb":   0,
        "ad_enabled":        True,
        "license_expires_at": now_ms + 9999 * 24 * 3600 * 1000,
        "created_at":        now_ms,
        "config": {
            "welcomeMessage": f"Добро пожаловать в {name}!",
            "adminChatId":    "",
            # ИСПРАВЛЕНО: buttons/triggers в корне config
            "buttons":        [],
            "triggers":       [],
            "connectedUsers": [],
            "stats": {
                "totalMessages": 0, "incomingToday": 0, "outgoingToday": 0,
                "activeUsers24h": 0, "bannedCount": 0,
                "broadcastsToday": 0, "broadcastsTotal": 0, "history": []
            },
            "settings": {
                "forwardAll": False, "forwardMessages": False,
                "useTopics": False, "topicPerRequest": False, "anonymousTopics": False,
                "rateLimit": 1, "autoBanThreshold": 3,
                "showHeaderId": True, "showHeaderName": True, "showHeaderUsername": True,
                "firstMessageHeader": "🆕 <b>ПЕРВОЕ ОБРАЩЕНИЕ:</b>",
                "ticketMessageHeader": "🆘 <b>ЗАЯВКА [{btn}]:</b>",
                "commonMessageHeader": "📩 <b>СООБЩЕНИЕ:</b>",
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
    ИСПРАВЛЕНО:
    - buttons/triggers сохраняются в КОРЕНЬ config (не вложенно в settings).
    - adminChatId сохраняется в корень config.
    - settings мержатся правильно.
    - При сохранении НЕ затираем connectedUsers и stats.
    """
    user_id = str(d.get("user_id", "")).strip()
    if not user_id:
        raise HTTPException(400, "user_id обязателен")

    db = _db()
    r = await db.get("bots", params={
        "id": f"eq.{bot_id}",
        "owner_id": f"eq.{user_id}",
        "is_free_plan": "eq.true"
    })
    if not r.json():
        raise HTTPException(404, "Free-бот не найден или нет прав")

    existing_bot = r.json()[0]
    existing_cfg = existing_bot.get("config") or {}

    # Входящий config-объект
    inc = d.get("config") or {}

    # Кнопки и триггеры — берём с корня payload, потом из inc
    buttons  = d.get("buttons")
    if buttons is None:
        buttons = inc.get("buttons", existing_cfg.get("buttons", []))

    triggers = d.get("triggers")
    if triggers is None:
        triggers = inc.get("triggers", existing_cfg.get("triggers", []))

    # Убираем Pro-only поля из кнопок
    clean_buttons = []
    for btn in (buttons or []):
        clean_btn = {k: v for k, v in btn.items()
                     if k not in ("flow", "ai_prompt", "ai_enabled", "webhook", "payment")}
        clean_buttons.append(clean_btn)

    # settings: мержим старые + новые
    old_stg    = existing_cfg.get("settings") or {}
    new_stg    = inc.get("settings") or {}
    merged_stg = {**old_stg, **new_stg}

    # adminChatId — явная проверка на None/присутствие ключа,
    # чтобы пустая строка "" корректно сбрасывала значение (or не работает с "")
    if "adminChatId" in inc:
        admin_chat_id = inc["adminChatId"] or ""
    elif "adminChatId" in d:
        admin_chat_id = d["adminChatId"] or ""
    else:
        admin_chat_id = existing_cfg.get("adminChatId") or ""

    # Сохраняем connectedUsers и stats — НЕ трогаем их
    connected_users = existing_cfg.get("connectedUsers", [])
    stats           = existing_cfg.get("stats", {})

    # Собираем новый config
    new_cfg = {
        # Сохраняем всё что было
        **existing_cfg,
        # Перезаписываем нужные поля
        "adminChatId":  admin_chat_id,
        "settings":     merged_stg,
        # ИСПРАВЛЕНО: buttons/triggers всегда в корне config
        "buttons":      clean_buttons,
        "triggers":     triggers or [],
        # НЕ трогаем users и stats
        "connectedUsers": connected_users,
        "stats":          stats,
    }

    # Скалярные поля из inc (только не-settings поля)
    # firstMessageHeader/ticketMessageHeader/commonMessageHeader живут в settings,
    # поэтому их НЕ копируем в корень config во избежание путаницы двух источников
    # FIX v6: сохраняем inlineButtons (новый формат) и welcomeInline (старый)
    inline_buttons = d.get("inlineButtons")
    if inline_buttons is None:
        inline_buttons = inc.get("inlineButtons")
    if inline_buttons is not None:
        new_cfg["inlineButtons"] = inline_buttons
    elif "inlineButtons" in existing_cfg:
        new_cfg["inlineButtons"] = existing_cfg["inlineButtons"]

    for key in ["welcomeMessage", "welcomePhoto", "welcomeInline", "description"]:
        if key in inc:
            new_cfg[key] = inc[key]

    # Числовое значение admin_chat_id для корневой колонки БД
    try:
        admin_chat_id_int = int(str(admin_chat_id).strip()) if admin_chat_id else None
    except (ValueError, TypeError):
        admin_chat_id_int = None

    patch_payload = {
        "config":        new_cfg,
        "name":          d.get("name") or existing_bot.get("name") or "Bot",
        "admin_chat_id": admin_chat_id_int,  # сохраняем в корневую колонку БД
    }

    # Токен — обновляем если пришёл новый
    new_token = d.get("token") or inc.get("token")
    if new_token and new_token.strip() and new_token != existing_bot.get("token"):
        try:
            s = _get_server()
            enc_fn = getattr(s, 'encrypt_val', lambda x: x)
            patch_payload["token"] = enc_fn(new_token.strip())
        except Exception:
            patch_payload["token"] = new_token.strip()

    patch_r = await db.patch("bots",
        params={"id": f"eq.{bot_id}"},
        json=patch_payload,
        headers={"Prefer": "return=representation"})

    result = patch_r.json()
    if not result:
        raise HTTPException(500, "Ошибка сохранения в БД")

    return result[0] if isinstance(result, list) else result


@router.get("/api/free/bots/{user_id}")
async def free_get_user_bots(user_id: str):
    db = _db()
    # Фильтруем только TG-ботов (исключаем platform=vk)
    all_free = await db.get("bots", params={"owner_id": f"eq.{user_id}", "is_free_plan": "eq.true"})
    bots = [b for b in (all_free.json() or []) if b.get("platform") != "vk"]
    return bots


@router.get("/api/free/bots/{bot_id}/stats")
async def free_bot_stats(bot_id: str, user_id: str):
    """
    Полная аналитика.
    ФИКС: stats всегда внутри config, не на корне row.
    bannedCount считаем из реального connectedUsers (не из stats).
    """
    db = _db()
    r = await db.get("bots", params={"id": f"eq.{bot_id}", "owner_id": f"eq.{user_id}"})
    if not r.json():
        raise HTTPException(404, "Бот не найден")
    bot = r.json()[0]
    cfg = bot.get("config") or {}

    # stats всегда живёт внутри config — только оттуда читаем
    cfg_stats = cfg.get("stats") or {}

    history_map: dict = {}
    for entry in (cfg_stats.get("history") or []):
        date = entry.get("date", "")
        if date:
            if date not in history_map:
                history_map[date] = dict(entry)
            else:
                for k in ["incoming", "outgoing", "totalUsers", "activeUsers", "broadcasts"]:
                    history_map[date][k] = max(history_map[date].get(k, 0), entry.get(k, 0))
    merged_history = sorted(history_map.values(), key=lambda x: x.get("date", ""))[-14:]

    connected    = cfg.get("connectedUsers") or []
    users_count  = len(connected)
    active_count = sum(1 for u in connected if u.get("is_active", True) and not u.get("is_banned"))
    # ФИКС: bannedCount считаем из реального списка юзеров, не из устаревшего счётчика
    banned_count = sum(1 for u in connected if u.get("is_banned"))

    merged_stats = {
        "totalMessages":    int(cfg_stats.get("totalMessages",  0)),
        "incomingToday":    int(cfg_stats.get("incomingToday",  0)),
        "outgoingToday":    int(cfg_stats.get("outgoingToday",  0)),
        "bannedCount":      banned_count,
        "activeUsers24h":   int(cfg_stats.get("activeUsers24h", 0)),
        "broadcastsTotal":  int(cfg_stats.get("broadcastsTotal", 0)),
        "broadcastsToday":  int(cfg_stats.get("broadcastsToday", 0)),
        "history":          merged_history,
    }

    return {
        "bot_id":        bot_id,
        "name":          bot.get("name"),
        "status":        bot.get("status"),
        "users_count":   users_count,
        "active_count":  active_count,
        "stats":         merged_stats,
        "connected_users": connected,
        "ad_enabled":    bot.get("ad_enabled", True),
        "memory_limit":  bot.get("memory_limit_mb", 0),
        "plan":          "free"
    }


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
            "broadcast":    True,
            "chatsite":     False,
            "advanced_buttons": False,
        }
    }



# ══════════════════════════════════════════════════════════════════════════════
# FREE VK BOTS
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/api/free/vk/bots/create")
async def free_vk_create_bot(d: dict):
    """
    Создать VK-бота на free-плане.
    token — Community Token из настроек сообщества ВКонтакте.
    admin_chat_id — peer_id беседы/группы для пересылки сообщений (опционально).
    """
    user_id      = d.get("user_id", "").strip()
    name         = d.get("name", "").strip()
    token        = d.get("token", "").strip()

    if not all([user_id, name, token]):
        raise HTTPException(400, "user_id, name, token обязательны")

    db = _db()
    s  = _get_server()
    enc_fn = getattr(s, 'encrypt_val', lambda x: x)
    new_id = f"fvk_{secrets.token_hex(5)}"
    now_ms = int(time.time() * 1000)

    bot_data = {
        "id":                new_id,
        "owner_id":          user_id,
        "name":              name,
        "token":             enc_fn(token),
        "status":            "IDLE",
        "platform":          "vk",
        "is_free_plan":      True,
        "memory_limit_mb":   0,
        "ad_enabled":        True,    # реклама включена для free-плана VK
        "license_expires_at": now_ms + 9999 * 24 * 3600 * 1000,
        "created_at":        now_ms,
        "config": {
            "welcomeMessage": f"Добро пожаловать в {name}!",
            "adminChatId":    d.get("admin_chat_id", ""),
            "vk_group_id":    d.get("admin_chat_id", ""),
            "vkGroupId":      d.get("admin_chat_id", ""),
            "buttons":        [],
            "triggers":       [],
            "inlineButtons":  [],
            "connectedUsers": [],
            "stats": {
                "totalMessages": 0, "incomingToday": 0, "outgoingToday": 0,
                "activeUsers24h": 0, "bannedCount": 0, "history": []
            },
            "settings": {
                "forwardAll": False, "forwardMessages": False,
                "anonymousTopics": False,
                "rateLimit": 1, "autoBanThreshold": 3,
                "showHeaderId": True, "showHeaderName": True, "showHeaderUsername": True,
                "firstMessageHeader": "🆕 ПЕРВОЕ ОБРАЩЕНИЕ:",
                "ticketMessageHeader": "🆘 ЗАЯВКА [{btn}]:",
                "commonMessageHeader": "📩 СООБЩЕНИЕ:",
            }
        }
    }

    r = await db.post("bots", json=bot_data, headers={"Prefer": "return=representation"})
    if r.status_code not in (200, 201):
        raise HTTPException(500, f"Ошибка БД: {r.text}")

    return r.json()[0] if isinstance(r.json(), list) else r.json()


@router.put("/api/free/vk/bots/{bot_id}/config")
async def free_vk_update_bot_config(bot_id: str, d: dict):
    """
    Сохранить конфиг VK-бота.
    Структура payload аналогична TG-боту, кроме отсутствия useTopics/topicPerRequest.
    Добавлено поле admin_chat_id (peer_id беседы ВКонтакте).
    """
    user_id = str(d.get("user_id", "")).strip()
    if not user_id:
        raise HTTPException(400, "user_id обязателен")

    db = _db()
    r  = await db.get("bots", params={
        "id":           f"eq.{bot_id}",
        "owner_id":     f"eq.{user_id}",
        "is_free_plan": "eq.true",
        "platform":     "eq.vk",
    })
    if not r.json():
        raise HTTPException(404, "VK Free-бот не найден или нет прав")

    existing_bot = r.json()[0]
    existing_cfg = existing_bot.get("config") or {}

    inc = d.get("config") or {}

    # buttons/triggers — с корня payload или из inc
    buttons  = d.get("buttons")
    if buttons is None:
        buttons = inc.get("buttons", existing_cfg.get("buttons", []))

    triggers = d.get("triggers")
    if triggers is None:
        triggers = inc.get("triggers", existing_cfg.get("triggers", []))

    # inlineButtons (кнопки под стартовым сообщением)
    inline_buttons = d.get("inlineButtons")
    if inline_buttons is None:
        inline_buttons = inc.get("inlineButtons", existing_cfg.get("inlineButtons", []))

    # Убираем Pro-only поля
    clean_buttons = []
    for btn in (buttons or []):
        clean_btn = {k: v for k, v in btn.items()
                     if k not in ("flow", "ai_prompt", "ai_enabled", "webhook", "payment")}
        clean_buttons.append(clean_btn)

    # settings мержим
    old_stg    = existing_cfg.get("settings") or {}
    new_stg    = inc.get("settings") or {}
    merged_stg = {**old_stg, **new_stg}
    # VK не поддерживает topics — убираем во избежание путаницы
    merged_stg.pop("useTopics", None)
    merged_stg.pop("topicPerRequest", None)

    # admin_chat_id / vk_group_id — ищем во всех источниках
    if "adminChatId" in inc and inc["adminChatId"]:
        admin_chat_id = str(inc["adminChatId"]).strip()
    elif "vk_group_id" in inc and inc["vk_group_id"]:
        admin_chat_id = str(inc["vk_group_id"]).strip()
    elif "adminChatId" in d and d["adminChatId"]:
        admin_chat_id = str(d["adminChatId"]).strip()
    elif "vk_group_id" in d and d["vk_group_id"]:
        admin_chat_id = str(d["vk_group_id"]).strip()
    else:
        admin_chat_id = str(
            existing_cfg.get("adminChatId") or existing_cfg.get("vk_group_id") or
            existing_bot.get("vk_group_id") or existing_bot.get("admin_chat_id") or ""
        ).strip()

    connected_users = existing_cfg.get("connectedUsers", [])
    stats           = existing_cfg.get("stats", {})

    new_cfg = {
        **existing_cfg,
        "adminChatId":    admin_chat_id,
        "vk_group_id":    admin_chat_id,
        "vkGroupId":      admin_chat_id,
        "settings":       merged_stg,
        "buttons":        clean_buttons,
        "triggers":       triggers or [],
        "inlineButtons":  inline_buttons or [],
        "connectedUsers": connected_users,
        "stats":          stats,
    }

    for key in ["welcomeMessage", "welcomePhoto", "description"]:
        if key in inc:
            new_cfg[key] = inc[key]

    # Числовое значение для корневых колонок БД
    try:
        admin_chat_id_int = int(admin_chat_id) if admin_chat_id else None
    except (ValueError, TypeError):
        admin_chat_id_int = None

    patch_payload = {
        "config":        new_cfg,
        "name":          d.get("name") or existing_bot.get("name") or "VK Bot",
        "admin_chat_id": admin_chat_id_int,  # корневая колонка БД
        "vk_group_id":   admin_chat_id_int,  # корневая колонка БД
    }

    new_token = d.get("token") or inc.get("token")
    if new_token and new_token.strip() and new_token != existing_bot.get("token"):
        try:
            s = _get_server()
            enc_fn = getattr(s, 'encrypt_val', lambda x: x)
            patch_payload["token"] = enc_fn(new_token.strip())
        except Exception:
            patch_payload["token"] = new_token.strip()

    patch_r = await db.patch("bots",
        params={"id": f"eq.{bot_id}"},
        json=patch_payload,
        headers={"Prefer": "return=representation"})

    result = patch_r.json()
    if not result:
        raise HTTPException(500, "Ошибка сохранения в БД")

    return result[0] if isinstance(result, list) else result


@router.get("/api/free/vk/bots/{user_id}")
async def free_vk_get_user_bots(user_id: str):
    """Список VK-ботов пользователя на free-плане."""
    db = _db()
    r  = await db.get("bots", params={
        "owner_id":     f"eq.{user_id}",
        "is_free_plan": "eq.true",
        "platform":     "eq.vk",
    })
    return r.json() or []


@router.get("/api/free/vk/bots/{bot_id}/stats")
async def free_vk_bot_stats(bot_id: str, user_id: str):
    """Аналитика VK-бота."""
    db = _db()
    r  = await db.get("bots", params={"id": f"eq.{bot_id}", "owner_id": f"eq.{user_id}"})
    if not r.json():
        raise HTTPException(404, "VK-бот не найден")
    bot = r.json()[0]
    cfg = bot.get("config") or {}

    cfg_stats = cfg.get("stats") or {}

    history_map: dict = {}
    for entry in (cfg_stats.get("history") or []):
        date = entry.get("date", "")
        if date:
            if date not in history_map:
                history_map[date] = dict(entry)
            else:
                for k in ["incoming", "outgoing", "totalUsers", "activeUsers"]:
                    history_map[date][k] = max(history_map[date].get(k, 0), entry.get(k, 0))
    merged_history = sorted(history_map.values(), key=lambda x: x.get("date", ""))[-14:]

    connected    = cfg.get("connectedUsers") or []
    users_count  = len(connected)
    active_count = sum(1 for u in connected if u.get("is_active", True) and not u.get("is_banned"))
    banned_count = sum(1 for u in connected if u.get("is_banned"))

    merged_stats = {
        "totalMessages":   int(cfg_stats.get("totalMessages",  0)),
        "incomingToday":   int(cfg_stats.get("incomingToday",  0)),
        "outgoingToday":   int(cfg_stats.get("outgoingToday",  0)),
        "bannedCount":     banned_count,
        "activeUsers24h":  int(cfg_stats.get("activeUsers24h", 0)),
        "broadcastsTotal": int(cfg_stats.get("broadcastsTotal", 0)),
        "broadcastsToday": int(cfg_stats.get("broadcastsToday", 0)),
        "history":         merged_history,
    }

    return {
        "bot_id":          bot_id,
        "name":            bot.get("name"),
        "status":          bot.get("status"),
        "users_count":     users_count,
        "active_count":    active_count,
        "stats":           merged_stats,
        "connected_users": connected,
        "ad_enabled":      bot.get("ad_enabled", False),
        "memory_limit":    bot.get("memory_limit_mb", 0),
        "plan":            "free",
        "platform":        "vk",
    }


@router.post("/api/free/vk/bots/{bot_id}/start")
async def free_vk_start_bot(bot_id: str):
    """Запустить VK-бота free-плана."""
    server = _get_server()
    pm     = getattr(server, 'pm', None)
    if not pm:
        raise HTTPException(500, "BotManager не инициализирован")

    db = server.db
    r  = await db.get("bots", params={"id": f"eq.{bot_id}"})
    if not r.json():
        raise HTTPException(404, "Бот не найден")

    bot_data = r.json()[0]

    owner_id = bot_data.get("owner_id")
    if owner_id:
        u_r = await db.get("users", params={"id": f"eq.{owner_id}"})
        if u_r.json() and u_r.json()[0].get("is_banned"):
            raise HTTPException(403, "Ваш аккаунт заблокирован")

    inner_cfg = bot_data.get("config") or {}
    if isinstance(inner_cfg, str):
        try:
            inner_cfg = json.loads(inner_cfg)
        except Exception:
            inner_cfg = {}

    merged = {
        **bot_data,
        "config": inner_cfg,
        "is_free_plan": True,
        "platform": "vk",
    }

    success = await pm.start_bot(bot_id, merged)
    if success is True:
        await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"status": "RUNNING"})
        return {"status": "ok", "message": "VK-бот запущен"}
    else:
        raise HTTPException(500, f"Не удалось запустить бота: {success}")


@router.post("/api/free/vk/bots/{bot_id}/stop")
async def free_vk_stop_bot(bot_id: str):
    """Остановить VK-бота free-плана."""
    server = _get_server()
    pm     = getattr(server, 'pm', None)
    if not pm:
        raise HTTPException(500, "BotManager не инициализирован")

    await pm.stop_bot(bot_id)
    try:
        db = server.db
        await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"status": "IDLE"})
    except Exception:
        pass
    return {"status": "ok", "message": "VK-бот остановлен"}


@router.delete("/api/free/vk/bots/{user_id}/{bot_id}")
async def free_vk_delete_bot(user_id: str, bot_id: str):
    """Удалить VK-бота free-плана."""
    server = _get_server()
    pm     = getattr(server, 'pm', None)
    if pm:
        try:
            await pm.stop_bot(bot_id)
        except Exception:
            pass

    db = _db()
    r  = await db.get("bots", params={
        "id":       f"eq.{bot_id}",
        "owner_id": f"eq.{user_id}",
    })
    if not r.json():
        raise HTTPException(404, "VK-бот не найден или нет прав")

    await db.delete("bots", params={"id": f"eq.{bot_id}"})
    return {"ok": True, "deleted": bot_id}


# ══════════════════════════════════════════════════════════════════════════════
# ADS AUTH
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
    import random as _random
    email     = d.get("email", "").strip().lower()
    code_type = d.get("type", "register").upper()
    if not email:
        raise HTTPException(400, "Email обязателен")

    db = _db()

    if code_type == "REGISTER":
        check = await db.get("ad_agents", params={"email": f"eq.{email}"})
        if check.json():
            raise HTTPException(409, "Email уже зарегистрирован")
    elif code_type == "RESET":
        check = await db.get("ad_agents", params={"email": f"eq.{email}"})
        if not check.json():
            return {"ok": True}
    else:
        raise HTTPException(400, f"Неверный тип кода: {code_type}")

    code       = str(_random.randint(100000, 999999))
    now_ms     = int(time.time() * 1000)
    expires_ms = now_ms + 15 * 60 * 1000

    await db.post("ad_email_codes", json={
        "email":      email,
        "code":       code,
        "type":       code_type,
        "expires_at": expires_ms,
        "used":       False,
    }, headers={"Prefer": "resolution=merge-duplicates"})

    s = _get_server()
    email_svc = getattr(s, 'EmailService', None)
    sent = False

    if email_svc:
        try:
            if code_type == "REGISTER":
                sent = await run_in_threadpool(email_svc.send_verification_code, email, code)
            else:
                sent = await run_in_threadpool(email_svc.send_password_reset, email, code)
        except Exception as e:
            _logger().error(f"Email send error: {e}")

    if not sent:
        try:
            base_url = os.getenv("SERVER_BASE_URL", "http://localhost:8000")
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(f"{base_url}/api/ads/auth/_send-email",
                    json={"email": email, "code": code, "type": code_type.lower()})
        except Exception as e:
            _logger().warning(f"Fallback email send failed: {e}")

    _logger().info(f"📧 Код {code_type} отправлен на {email}")
    return {"ok": True}


@router.post("/api/ads/auth/register-verify")
async def ads_register_verify(d: dict):
    email = d.get("email", "").strip().lower()
    code  = d.get("code", "").strip()
    pwd   = d.get("password", "").strip()

    if not email or not code or not pwd or len(pwd) < 6:
        raise HTTPException(400, "Заполните все поля")

    db = _db()
    now_ms = int(time.time() * 1000)

    code_r = await db.get("ad_email_codes", params={
        "email": f"eq.{email}", "code": f"eq.{code}",
        "type":  "eq.REGISTER",  "used": "eq.false",
        "expires_at": f"gt.{now_ms}"
    })
    if not code_r.json():
        raise HTTPException(400, "Неверный или истёкший код. Запросите новый.")

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

    await db.patch("ad_email_codes",
        params={"email": f"eq.{email}", "type": "eq.REGISTER"},
        json={"used": True})

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
    email        = d.get("email", "").strip().lower()
    code         = d.get("code", "").strip()
    new_password = d.get("newPassword", "").strip()

    if not email or not code or not new_password or len(new_password) < 6:
        raise HTTPException(400, "Заполните все поля. Пароль минимум 6 символов.")

    db = _db()
    now_ms = int(time.time() * 1000)

    code_r = await db.get("ad_email_codes", params={
        "email": f"eq.{email}", "code": f"eq.{code}",
        "type":  "eq.RESET",    "used": "eq.false",
        "expires_at": f"gt.{now_ms}"
    })
    if not code_r.json():
        raise HTTPException(400, "Неверный или истёкший код. Запросите новый.")

    r = await db.patch("ad_agents",
        params={"email": f"eq.{email}"},
        json={"password_hash": _hash(new_password)},
        headers={"Prefer": "return=representation"}
    )
    if not r.json():
        raise HTTPException(404, "Агент не найден")

    await db.patch("ad_email_codes",
        params={"email": f"eq.{email}", "type": "eq.RESET"},
        json={"used": True})

    return {"ok": True, "message": "Пароль успешно изменён"}


# ══════════════════════════════════════════════════════════════════════════════
# ADS PORTAL
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

    posts_r = await db.get("ad_posts",
        params={"agent_id": f"eq.{agent['id']}", "order": "created_at.desc", "limit": "50"})
    posts   = posts_r.json() or []

    tx_r  = await db.get("ad_transactions",
        params={"agent_id": f"eq.{agent['id']}", "order": "created_at.desc", "limit": "50"})
    txs   = tx_r.json() or []

    # Грузим все free-боты с config — аудитория хранится в config.connectedUsers,
    # а НЕ в таблице users (там только владельцы ботов, их мало).
    bots_r       = await db.get("bots", params={"is_free_plan": "eq.true", "select": "id,status,config"})
    all_bots     = bots_r.json() or []

    total_users  = 0
    running_bots = 0
    for b in all_bots:
        cfg = b.get("config") or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}
        total_users  += len(cfg.get("connectedUsers") or [])
        if b.get("status") == "RUNNING":
            running_bots += 1

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
            "free_bots":    len(all_bots),   # всего free-ботов
            "running_bots": running_bots,     # сейчас запущенных
            "free_users":   total_users,      # реальная аудитория из connectedUsers
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

    post_r = await db.get("ad_posts", params={"id": f"eq.{post_id}", "agent_id": f"eq.{agent['id']}"})
    if not post_r.json():
        raise HTTPException(404, "Пост не найден")
    post = post_r.json()[0]
    if post["status"] not in ("approved", "active"):
        raise HTTPException(422, f"Пост должен быть одобрен (статус: {post['status']}). Дождитесь модерации.")

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
        cost = impressions * PRICE_PER_IMP
        agent_fresh = await _get_agent(agent["id"])
        if not agent_fresh:
            raise HTTPException(404, "Агент не найден")
        balance = float(agent_fresh.get("balance_rub", 0))
        if balance < cost:
            raise HTTPException(402, f"Недостаточно средств. Нужно {cost:.2f}₽, на балансе {balance:.2f}₽")

        now_ms = int(time.time() * 1000)
        new_balance  = balance - cost
        new_imp_paid = post.get("impressions_paid", 0) + impressions
        tx_id = f"tx_{secrets.token_hex(6)}"

        await db.patch("ad_agents", params={"id": f"eq.{agent['id']}"}, json={"balance_rub": new_balance})
        await db.patch("ad_posts", params={"id": f"eq.{post_id}"}, json={"impressions_paid": new_imp_paid})
        await db.post("ad_transactions", json={
            "id": tx_id, "agent_id": agent["id"], "post_id": post_id,
            "type": "spend", "amount_rub": cost, "impressions": impressions,
            "created_at": now_ms
        }, headers={"Prefer": "return=minimal"})

    if post["status"] == "approved":
        activate_r = await db.patch("ad_posts",
            params={"id": f"eq.{post_id}"},
            json={"status": "active"},
            headers={"Prefer": "return=representation"}
        )
        _logger().info(f"✅ Пост {post_id} активирован после покупки {impressions} показов")
        post_data = activate_r.json()
        if isinstance(post_data, list) and post_data:
            return post_data[0]

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


@router.post("/api/ads/payments/webhook")
async def ads_payment_webhook(request: Request):
    body_bytes = await request.body()
    try:
        data = json.loads(body_bytes)
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    event = data.get("event", "")
    if event != "payment.succeeded":
        return {"ok": True}

    obj        = data.get("object", {})
    payment_id = obj.get("id", "")
    amount_obj = obj.get("amount", {})
    amount     = float(amount_obj.get("value", 0))
    metadata   = obj.get("metadata", {})
    agent_id   = metadata.get("agent_id", "")

    if not agent_id or amount <= 0 or not payment_id:
        return {"ok": True}

    yk_shop_id = os.getenv("YOOKASSA_SHOP_ID", "")
    yk_secret  = os.getenv("YOOKASSA_SECRET_KEY", "")
    if yk_shop_id and yk_secret:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(
                    f"https://api.yookassa.ru/v3/payments/{payment_id}",
                    auth=(yk_shop_id, yk_secret)
                )
                if r.status_code != 200:
                    raise HTTPException(400, "Payment verification failed")
                real = r.json()
                if real.get("status") != "succeeded":
                    return {"ok": True}
                real_amount = float(real.get("amount", {}).get("value", 0))
                real_agent  = real.get("metadata", {}).get("agent_id", "")
                if real_agent != agent_id or abs(real_amount - amount) > 0.01:
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
    agent = await _auth_agent(authorization)
    amount = float(d.get("amount", 0))
    if amount < 10:
        raise HTTPException(400, "Минимальная сумма пополнения — 10 ₽")

    yk_shop_id = os.getenv("YOOKASSA_SHOP_ID", "")
    yk_secret  = os.getenv("YOOKASSA_SECRET_KEY", "")
    if not yk_shop_id or not yk_secret:
        raise HTTPException(503, "YOOKASSA_SHOP_ID / YOOKASSA_SECRET_KEY не настроены")

    return_url  = os.getenv("FRONTEND_URL", os.getenv("SERVER_BASE_URL", "https://dialogengine.webtm.ru")) + "/ads?payment=success"
    idempotency = str(uuid.uuid4())

    payload = {
        "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": return_url},
        "capture":     True,
        "description": f"Пополнение рекламного баланса BotEngine — агент {agent['id']}",
        "metadata":    {"agent_id": agent["id"]}
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://api.yookassa.ru/v3/payments",
                auth=(yk_shop_id, yk_secret),
                headers={"Idempotence-Key": idempotency, "Content-Type": "application/json"},
                json=payload
            )
        if r.status_code not in (200, 201):
            raise HTTPException(502, "Ошибка создания платежа в ЮКассе")

        resp     = r.json()
        conf_url = resp.get("confirmation", {}).get("confirmation_url", "")
        if not conf_url:
            raise HTTPException(502, "ЮКасса не вернула confirmation_url")

        return {"payment_id": resp.get("id"), "confirmation_url": conf_url, "amount": amount}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Ошибка: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN: модерация
# ══════════════════════════════════════════════════════════════════════════════

def _verify_admin(token: str) -> bool:
    s      = _get_server()
    secret = getattr(s, 'A_SECRET', os.getenv("ADMIN_TOKEN", ""))
    return token == secret


@router.get("/api/admin/ads/posts")
async def admin_get_ad_posts(status: str = "pending", x_admin_token: str = Header(...)):
    if not _verify_admin(x_admin_token):
        raise HTTPException(403, "Forbidden")
    db = _db()
    params = {"order": "created_at.desc"}
    if status != "all":
        params["status"] = f"eq.{status}"
    r = await db.get("ad_posts", params=params)
    return r.json() or []


@router.post("/api/admin/ads/posts/{post_id}/approve")
async def admin_approve_post(post_id: str, x_admin_token: str = Header(...)):
    if not _verify_admin(x_admin_token):
        raise HTTPException(403, "Forbidden")
    db     = _db()
    now_ms = int(time.time() * 1000)
    post_r = await db.get("ad_posts", params={"id": f"eq.{post_id}"})
    if not post_r.json():
        raise HTTPException(404, "Пост не найден")
    post       = post_r.json()[0]
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

    total_impressions_sold = sum(p.get("impressions_paid", 0) for p in posts)
    total_impressions_used = sum(p.get("impressions_used", 0) for p in posts)
    total_revenue          = sum(p.get("impressions_paid", 0) * float(p.get("price_per_imp", PRICE_PER_IMP)) for p in posts)

    return {
        "agents_count":           len(agents),
        "agents":                 agents,
        "posts_count":            len(posts),
        "posts_by_status": {
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
# PUBLIC: активная реклама для бота
# ══════════════════════════════════════════════════════════════════════════════

_ad_roundrobin: dict = {}


@router.get("/api/ads/active")
async def get_active_ad(bot_id: str = ""):
    global _ad_roundrobin
    db = _db()

    r = await db.get("ad_posts", params={
        "status": "eq.active",
        "select": "id,text,media_url",
        "order":  "id.asc",
    })
    posts = r.json() or []
    if not posts:
        return {"ad": None}

    last_id = _ad_roundrobin.get(bot_id)
    post    = None

    if last_id is None:
        post = posts[0]
    else:
        ids = [p["id"] for p in posts]
        if last_id in ids:
            next_idx = (ids.index(last_id) + 1) % len(posts)
        else:
            next_idx = 0
        post = posts[next_idx]

    _ad_roundrobin[bot_id] = post["id"]

    try:
        await _rpc_local("record_ad_impression", {"p_post_id": post["id"]})
    except Exception as e:
        _logger().error(f"record_ad_impression error: {e}")

    return {"ad": {"text": post["text"], "media_url": post.get("media_url")}}


# ══════════════════════════════════════════════════════════════════════════════
# FREE: линковка с pro аккаунтом
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/api/free/link-pro")
async def free_link_pro(d: dict):
    free_id = d.get("free_user_id", "").strip()
    pro_id  = d.get("pro_user_id", "").strip()
    if not free_id or not pro_id:
        raise HTTPException(400, "free_user_id и pro_user_id обязательны")

    db = _db()
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


# ══════════════════════════════════════════════════════════════════════════════
# BOT START / STOP
# ══════════════════════════════════════════════════════════════════════════════

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

    owner_id = bot_data.get("owner_id")
    if owner_id:
        u_r = await db.get("users", params={"id": f"eq.{owner_id}"})
        if u_r.json() and u_r.json()[0].get("is_banned"):
            raise HTTPException(403, "Ваш аккаунт заблокирован")

    # ИСПРАВЛЕНО: передаём полный объект row + config развёрнутый
    inner_cfg = bot_data.get("config") or {}
    if isinstance(inner_cfg, str):
        try:
            inner_cfg = json.loads(inner_cfg)
        except Exception:
            inner_cfg = {}

    # Передаём так, чтобы FreeBotInstance.apply_config нашёл buttons/triggers
    merged = {
        **bot_data,      # корень: id, token, owner_id, name, ...
        "config": inner_cfg,  # вложенный config: buttons, triggers, settings, ...
        "is_free_plan": True,
    }

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
    try:
        db = server.db
        await db.patch("bots", params={"id": f"eq.{bot_id}"}, json={"status": "IDLE"})
    except Exception:
        pass
    return {"status": "ok", "message": "Бот остановлен"}
