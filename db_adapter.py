"""
db_adapter.py
─────────────────────────────────────────────────────────────────────────────
Двухуровневый адаптер БД:
  • ПРИОРИТЕТ 1 — PostgreSQL через asyncpg
    (DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, DB_PORT)
  • FALLBACK — Supabase REST API
    (SUPABASE_URL, SUPABASE_KEY)

Все публичные методы возвращают нативные Python-объекты (list / dict / bool),
НЕ httpx-ответы — это важно при переходе с httpx-клиента.
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone

import asyncpg
import httpx
from dotenv import load_dotenv, find_dotenv

# Загружаем .env — ищем вверх по дереву директорий, чтобы найти его из любого cwd
load_dotenv(find_dotenv(usecwd=True) or find_dotenv())

logger = logging.getLogger("DBAdapter")

# ─── Переменные окружения ─────────────────────────────────────────────────────
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASSWORD")

# Если задан DB_PGBOUNCER_PORT — подключаемся через PgBouncer (рекомендуется).
# Иначе используем DB_PORT (прямое подключение к PostgreSQL).
_pgbouncer_port = os.getenv("DB_PGBOUNCER_PORT")
DB_PORT = int(_pgbouncer_port if _pgbouncer_port else os.getenv("DB_PORT", "5432"))
# Отключаем statement cache если:
# - явно указан DB_PGBOUNCER_PORT, или
# - DB_DISABLE_STATEMENT_CACHE=1 (для случаев когда порт задан через DB_PORT)
_via_pgbouncer = bool(_pgbouncer_port) or os.getenv("DB_DISABLE_STATEMENT_CACHE", "") == "1"

SB_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SB_KEY = os.getenv("SUPABASE_KEY", "")

_pg_pool: asyncpg.Pool | None = None
_pg_available: bool = bool(DB_HOST and DB_NAME and DB_USER and DB_PASS)
_pg_last_fail: float = 0.0          # время последней ошибки подключения
_PG_RETRY_AFTER = 30.0              # через сколько секунд пробуем PG снова после ошибки


# ─── Инициализация пула PostgreSQL ────────────────────────────────────────────

async def _setup_pg_conn(conn: asyncpg.Connection):
    """Регистрируем кодеки для JSON/JSONB — чтобы получать dict, а не строку."""
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )
    await conn.set_type_codec(
        "json",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


async def init_pg_pool(min_size: int = 0, max_size: int = 1) -> asyncpg.Pool | None:
    """
    Создаёт пул подключений к PostgreSQL.

    min_size=0 — соединение НЕ открывается при инициализации, только при первом запросе.
    При ошибке "too many clients" — повторяет попытку с backoff (до 5 раз).
    После других ошибок — временно отключает PG на _PG_RETRY_AFTER секунд (не навсегда!).
    """
    global _pg_pool, _pg_available, _pg_last_fail
    if _pg_pool is not None:
        return _pg_pool
    if not bool(DB_HOST and DB_NAME and DB_USER and DB_PASS):
        logger.info("[DBAdapter] PostgreSQL не настроен — используем Supabase")
        return None

    retries = 5
    for attempt in range(1, retries + 1):
        try:
            _pg_pool = await asyncpg.create_pool(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASS,
                min_size=min_size,
                max_size=max_size,
                command_timeout=10,
                init=_setup_pg_conn,
                statement_cache_size=0 if _via_pgbouncer else 100,
            )
            mode_str = f"via PgBouncer :{DB_PORT}" if _via_pgbouncer else f"direct :{DB_PORT}"
            logger.info(f"✅ [DBAdapter] PostgreSQL пул создан ({DB_HOST}/{DB_NAME}, {mode_str}, min={min_size}, max={max_size})")
            _pg_available = True
            _pg_last_fail  = 0.0
            return _pg_pool
        except Exception as e:
            err = str(e)
            is_overload = "too many clients" in err or "connection slots" in err
            if is_overload and attempt < retries:
                wait = attempt * 3
                logger.warning(f"⚠️ [DBAdapter] PostgreSQL перегружен (попытка {attempt}/{retries}), повтор через {wait}с: {e}")
                await asyncio.sleep(wait)
            else:
                logger.error(f"❌ [DBAdapter] Не удалось создать PostgreSQL пул: {e} — временный fallback на Supabase ({_PG_RETRY_AFTER}с)")
                _pg_pool      = None
                _pg_available = False
                _pg_last_fail  = asyncio.get_event_loop().time()
                return None


async def get_pg_pool() -> asyncpg.Pool | None:
    """Возвращает пул. Если PG временно отключён — пробует восстановить через _PG_RETRY_AFTER."""
    global _pg_pool, _pg_available, _pg_last_fail

    # Если пул жив — проверяем что он ещё работает (быстрая проверка без запроса)
    if _pg_pool is not None:
        if _pg_pool._closed:
            logger.warning("[DBAdapter] PG пул закрыт — пересоздаём")
            _pg_pool      = None
            _pg_available = True   # пробуем заново
        else:
            return _pg_pool

    # Если PG временно отключён — ждём _PG_RETRY_AFTER перед повтором
    if not _pg_available:
        now = asyncio.get_event_loop().time()
        if _pg_last_fail and (now - _pg_last_fail) < _PG_RETRY_AFTER:
            return None   # ещё рано
        logger.info(f"[DBAdapter] Пробуем переподключиться к PostgreSQL...")
        _pg_available = True  # разрешаем попытку

    if _pg_pool is None and _pg_available:
        await init_pg_pool()
    return _pg_pool


# ─── Парсер Supabase-фильтров → SQL WHERE ────────────────────────────────────

_SB_OPS = {
    "eq": "=",
    "neq": "!=",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "like": "LIKE",
    "ilike": "ILIKE",
}

def _cast_value(val_str: str) -> object:
    """Умное приведение типов: строка -> bool / int / float / datetime / str."""
    if val_str == "true":
        return True
    if val_str == "false":
        return False
    if val_str == "null":
        return None

    # ISO datetime: YYYY-MM-DDThh:mm:ss или YYYY-MM-DD
    if len(val_str) >= 10 and val_str[4:5] == "-" and val_str[7:8] == "-":
        try:
            # С timezone-offset или 'Z'
            s = val_str.replace("Z", "+00:00")
            return datetime.fromisoformat(s)
        except ValueError:
            pass

    # Проверка на целое число (вкл. отрицательные)
    if val_str.isdigit() or (val_str.startswith('-') and val_str[1:].isdigit()):
        return int(val_str)

    # Проверка на число с плавающей точкой
    try:
        return float(val_str)
    except ValueError:
        return val_str  # Оставляем строкой, если это текст


def _parse_sb_params(params: dict, start_idx: int = 1):
    """
    Преобразует Supabase-стиль параметров в компоненты SQL-запроса.
    """
    columns = params.get("select", "*")
    order   = params.get("order")
    limit   = params.get("limit")

    conditions: list[str] = []
    values: list = []
    idx = start_idx

    for key, val in params.items():
        if key in ("select", "order", "limit", "offset"):
            continue

        str_val = str(val)
        dot_pos = str_val.find(".")
        if dot_pos > 0:
            op_str = str_val[:dot_pos]
            v_str  = str_val[dot_pos + 1:]
        else:
            op_str = "eq"
            v_str  = str_val

        if op_str in _SB_OPS:
            v = _cast_value(v_str) # <--- ИСПОЛЬЗУЕМ НОВУЮ ФУНКЦИЮ ЗДЕСЬ
            conditions.append(f'"{key}" {_SB_OPS[op_str]} ${idx}')
            values.append(v)
            idx += 1

        elif op_str == "in":
            # in.(a,b,c)
            # <--- ТАКЖЕ ПРИМЕНЯЕМ КО ВСЕМ ЭЛЕМЕНТАМ СПИСКА
            items = [_cast_value(i) for i in v_str.strip("()").split(",")] 
            placeholders = ", ".join(f"${i + idx}" for i in range(len(items)))
            conditions.append(f'"{key}" IN ({placeholders})')
            values.extend(items)
            idx += len(items)

    where = " AND ".join(conditions) if conditions else "TRUE"

    order_clause = ""
    if order:
        parts  = order.split(".")
        col    = parts[0]
        direct = "DESC" if len(parts) > 1 and parts[1].lower() == "desc" else "ASC"
        order_clause = f'ORDER BY "{col}" {direct}'

    limit_clause = f"LIMIT {int(limit)}" if limit else ""

    return columns, where, order_clause, limit_clause, values


def _prepare_value(v) -> object:
    """Передаём dict/list напрямую — asyncpg с JSONB кодеками сам сериализует."""
    return v


def _short_err(e: Exception) -> str:
    """Короткое сообщение об ошибке для лога (без трейсбека)."""
    s = str(e)
    return s[:120] if len(s) > 120 else s


def _reset_pg_pool_on_error(e: Exception):
    """
    При connection-ошибке PG — сбрасываем пул чтобы следующий запрос попробовал переподключиться.
    НЕ сбрасываем при ошибках данных (IntegrityError, SyntaxError и т.п.).
    """
    global _pg_pool, _pg_available, _pg_last_fail
    err = str(e).lower()
    is_conn_err = any(x in err for x in (
        "connection", "timeout", "pool", "unavailable", "closed",
        "too many clients", "connection slots", "ssl", "eof",
        "broken pipe", "network", "reset by peer",
    ))
    if is_conn_err:
        logger.warning(f"[DBAdapter] PG connection error — сбрасываем пул, повтор через {_PG_RETRY_AFTER}с")
        _pg_pool      = None
        _pg_available = False
        try:
            _pg_last_fail = asyncio.get_event_loop().time()
        except RuntimeError:
            import time as _t
            _pg_last_fail = _t.time()


# ─── Главный класс ────────────────────────────────────────────────────────────

class DBAdapter:
    def __init__(self, sb_url: str = None, sb_key: str = None):
        self.sb_url = (sb_url or SB_URL).rstrip("/")
        self.sb_key = sb_key or SB_KEY
        self._sb_h  = {
            "apikey":        self.sb_key,
            "Authorization": f"Bearer {self.sb_key}",
            "Content-Type":  "application/json",
        }

    # ── PostgreSQL ────────────────────────────────────────────────────────────

    async def _pg_get(self, table: str, params: dict) -> list:
        pool = await get_pg_pool()
        if pool is None:
            raise RuntimeError("PG unavailable")

        columns, where, order, limit, values = _parse_sb_params(params)

        if columns == "*":
            col_clause = "*"
        else:
            col_clause = ", ".join(f'"{c.strip()}"' for c in columns.split(",") if c.strip())

        sql = f'SELECT {col_clause} FROM "{table}" WHERE {where}'
        if order: sql += f" {order}"
        if limit: sql += f" {limit}"

        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *values)

        results = []
        for r in rows:
            row_dict = dict(r)
            for k, v in row_dict.items():
                # Если asyncpg уже вернул dict (через кодеки), пропускаем
                if isinstance(v, (dict, list)):
                    continue
                
                # Если пришла строка, похожая на JSON
                if isinstance(v, str):
                    v_s = v.strip()
                    if v_s.startswith(('{', '[')):
                        try:
                            # Парсим строго один раз
                            parsed = json.loads(v_s)
                            
                            # Если внутри оказался еще один слой JSON-строки (бывает при двойной сериализации)
                            if isinstance(parsed, str) and parsed.strip().startswith(('{', '[')):
                                parsed = json.loads(parsed)
                            
                            row_dict[k] = parsed
                        except json.JSONDecodeError as je:
                            # Выводим конкретную ошибку и длину, чтобы понять, где обрыв
                            logger.error(f"❌ Ошибка JSON в боте {row_dict.get('id', '???')} (поле {k}): {je}")
                            logger.error(f"Длина проблемной строки: {len(v_s)} символов")
                            # Оставляем строку как есть, чтобы основная логика поняла, что конфиг битый
                        except Exception as e:
                            logger.error(f"❌ Непредвиденная ошибка парсинга {k}: {e}")
            
            results.append(row_dict)
            
        return results
      
    async def _pg_post(self, table: str, data: dict) -> dict:
        pool = await get_pg_pool()
        if pool is None:
            raise RuntimeError("PG unavailable")

        cols:  list[str] = []
        vals:  list      = []
        for k, v in data.items():
            cols.append(f'"{k}"')
            vals.append(_prepare_value(v))

        placeholders = ", ".join(f"${i + 1}" for i in range(len(vals)))
        sql = (
            f'INSERT INTO "{table}" ({", ".join(cols)}) '
            f"VALUES ({placeholders}) RETURNING *"
        )

        async with pool.acquire() as conn:
            row = await conn.fetchrow(sql, *vals)
        
        if not row: return {}
        
        row_dict = dict(row)
        for k, v in row_dict.items():
            if isinstance(v, str):
                v_stripped = v.strip()
                if v_stripped.startswith(('{', '[')):
                    try:
                        row_dict[k] = json.loads(v_stripped)
                        if isinstance(row_dict[k], str) and row_dict[k].strip().startswith(('{', '[')):
                            row_dict[k] = json.loads(row_dict[k])
                    except Exception:
                        pass
        return row_dict

    async def _pg_patch(self, table: str, filter_params: dict, data: dict) -> bool:
        pool = await get_pg_pool()
        if pool is None:
            raise RuntimeError("PG unavailable")

        set_parts: list[str] = []
        set_vals:  list      = []
        for i, (k, v) in enumerate(data.items(), start=1):
            set_parts.append(f'"{k}" = ${i}')
            set_vals.append(_prepare_value(v))

        _, where, _, _, where_vals = _parse_sb_params(
            filter_params, start_idx=len(set_vals) + 1
        )

        sql = f'UPDATE "{table}" SET {", ".join(set_parts)} WHERE {where}'
        async with pool.acquire() as conn:
            await conn.execute(sql, *(set_vals + where_vals))
        return True

    async def _pg_delete(self, table: str, params: dict) -> bool:
        pool = await get_pg_pool()
        if pool is None:
            raise RuntimeError("PG unavailable")

        _, where, _, _, values = _parse_sb_params(params)
        sql = f'DELETE FROM "{table}" WHERE {where}'
        async with pool.acquire() as conn:
            await conn.execute(sql, *values)
        return True

    async def _pg_rpc(self, func: str, params: dict) -> object:
        pool = await get_pg_pool()
        if pool is None:
            raise RuntimeError("PG unavailable")

        placeholders = ", ".join(f"${i + 1}" for i in range(len(params)))
        sql = f"SELECT {func}({placeholders})"
        vals = [_prepare_value(v) for v in params.values()]

        async with pool.acquire() as conn:
            result = await conn.fetchval(sql, *vals)
        return result

    # ── Supabase REST fallback ────────────────────────────────────────────────

    async def _sb_get(self, table: str, params: dict) -> list:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(
                    f"{self.sb_url}/rest/v1/{table}",
                    headers=self._sb_h,
                    params=params,
                )
                if r.status_code == 200:
                    return r.json()
        except Exception as e:
            logger.warning(f"[DBAdapter] Supabase GET {table} error: {e}")
        return []

    async def _sb_post(self, table: str, data: dict) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.post(
                    f"{self.sb_url}/rest/v1/{table}",
                    headers={**self._sb_h, "Prefer": "return=representation"},
                    json=data,
                )
                if r.status_code in (200, 201):
                    d = r.json()
                    if isinstance(d, list) and d:
                        return d[0]
                    if isinstance(d, dict):
                        return d
        except Exception as e:
            logger.warning(f"[DBAdapter] Supabase POST {table} error: {e}")
        return {}

    async def _sb_patch(self, table: str, params: dict, data: dict) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.patch(
                    f"{self.sb_url}/rest/v1/{table}",
                    headers=self._sb_h,
                    params=params,
                    json=data,
                )
                return r.status_code in (200, 204)
        except Exception as e:
            logger.warning(f"[DBAdapter] Supabase PATCH {table} error: {e}")
        return False

    async def _sb_delete(self, table: str, params: dict) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.delete(
                    f"{self.sb_url}/rest/v1/{table}",
                    headers=self._sb_h,
                    params=params,
                )
                return r.status_code in (200, 204)
        except Exception as e:
            logger.warning(f"[DBAdapter] Supabase DELETE {table} error: {e}")
        return False

    async def _sb_rpc(self, func: str, params: dict) -> object:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.post(
                    f"{self.sb_url}/rest/v1/rpc/{func}",
                    headers=self._sb_h,
                    json=params,
                )
                if r.status_code == 200:
                    return r.json()
        except Exception as e:
            logger.warning(f"[DBAdapter] Supabase RPC {func} error: {e}")
        return None

    # ── Публичный API ─────────────────────────────────────────────────────────

    async def get(self, table: str, params: dict = None) -> list:
        params = params or {}
        if _pg_available or _pg_pool is not None:
            try:
                return await self._pg_get(table, params)
            except Exception as e:
                _reset_pg_pool_on_error(e)
                logger.warning(f"[DBAdapter] PG get({table}) → fallback: {_short_err(e)}")
        return await self._sb_get(table, params)

    async def post(self, table: str, data: dict = None, json: dict = None, headers: dict = None) -> dict:
        payload = data or json or {}
        if _pg_available or _pg_pool is not None:
            try:
                return await self._pg_post(table, payload)
            except Exception as e:
                _reset_pg_pool_on_error(e)
                logger.warning(f"[DBAdapter] PG post({table}) → fallback: {_short_err(e)}")
        return await self._sb_post(table, payload)

    async def patch(self, table: str, params: dict = None, json: dict = None,
                    data: dict = None, headers: dict = None) -> bool:
        filter_p = params or {}
        payload  = json or data or {}
        if _pg_available or _pg_pool is not None:
            try:
                return await self._pg_patch(table, filter_p, payload)
            except Exception as e:
                _reset_pg_pool_on_error(e)
                logger.warning(f"[DBAdapter] PG patch({table}) → fallback: {_short_err(e)}")
        return await self._sb_patch(table, filter_p, payload)

    async def delete(self, table: str, params: dict = None) -> bool:
        filter_p = params or {}
        if _pg_available or _pg_pool is not None:
            try:
                return await self._pg_delete(table, filter_p)
            except Exception as e:
                _reset_pg_pool_on_error(e)
                logger.warning(f"[DBAdapter] PG delete({table}) → fallback: {_short_err(e)}")
        return await self._sb_delete(table, filter_p)

    async def rpc(self, func: str, params: dict) -> object:
        if _pg_available or _pg_pool is not None:
            try:
                return await self._pg_rpc(func, params)
            except Exception as e:
                _reset_pg_pool_on_error(e)
                logger.warning(f"[DBAdapter] PG rpc({func}) → fallback: {_short_err(e)}")
        return await self._sb_rpc(func, params)

    # ── Совместимость с Supabase httpx-клиентом ───────────────────────────────

    async def raw_get(self, path: str, params: dict = None) -> httpx.Response:
        async with httpx.AsyncClient(timeout=15) as c:
            return await c.get(
                f"{self.sb_url}/rest/v1/{path}",
                headers=self._sb_h,
                params=params or {},
            )

    async def raw_post(self, path: str, json_data: dict = None, extra_headers: dict = None) -> httpx.Response:
        h = {**self._sb_h, **(extra_headers or {})}
        async with httpx.AsyncClient(timeout=15) as c:
            return await c.post(
                f"{self.sb_url}/rest/v1/{path}",
                headers=h,
                json=json_data or {},
            )


# ─── Глобальный синглтон ──────────────────────────────────────────────────────

_default_adapter: DBAdapter | None = None

def get_adapter(sb_url: str = None, sb_key: str = None) -> DBAdapter:
    global _default_adapter
    if _default_adapter is None:
        _default_adapter = DBAdapter(sb_url, sb_key)
    return _default_adapter
