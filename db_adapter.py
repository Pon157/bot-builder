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

import asyncpg
import httpx
from dotenv import load_dotenv  

load_dotenv()

logger = logging.getLogger("DBAdapter")

# ─── Переменные окружения ─────────────────────────────────────────────────────
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASSWORD")
DB_PORT = int(os.getenv("DB_PORT", "5432"))

SB_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SB_KEY = os.getenv("SUPABASE_KEY", "")

_pg_pool: asyncpg.Pool | None = None
_pg_available: bool = bool(DB_HOST and DB_NAME and DB_USER and DB_PASS)


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


async def init_pg_pool() -> asyncpg.Pool | None:
    """Создаёт пул подключений к PostgreSQL. Вызывать при старте приложения."""
    global _pg_pool, _pg_available
    if not _pg_available:
        logger.info("[DBAdapter] PostgreSQL не настроен (нет DB_HOST/DB_NAME/DB_USER/DB_PASSWORD) — используем Supabase")
        return None
    try:
        _pg_pool = await asyncpg.create_pool(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            min_size=2,
            max_size=15,
            command_timeout=10,
            init=_setup_pg_conn,
        )
        logger.info(f"✅ [DBAdapter] PostgreSQL пул создан ({DB_HOST}:{DB_PORT}/{DB_NAME})")
        return _pg_pool
    except Exception as e:
        logger.error(f"❌ [DBAdapter] Не удалось создать PostgreSQL пул: {e} — переходим на Supabase")
        _pg_available = False
        return None


async def get_pg_pool() -> asyncpg.Pool | None:
    global _pg_pool
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


def _parse_sb_params(params: dict, start_idx: int = 1):
    """
    Преобразует Supabase-стиль параметров в компоненты SQL-запроса.

    Пример:
        {"id": "eq.bot_abc", "status": "eq.RUNNING", "order": "created_at.desc", "limit": "10"}
    →   WHERE id = $1 AND status = $2  ORDER BY created_at DESC  LIMIT 10

    Возвращает: (columns_str, where_str, order_str, limit_str, values_list)
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
            # Приводим к нативным типам
            if v_str == "true":
                v: object = True
            elif v_str == "false":
                v = False
            elif v_str == "null":
                v = None
            else:
                v = v_str

            conditions.append(f'"{key}" {_SB_OPS[op_str]} ${idx}')
            values.append(v)
            idx += 1

        elif op_str == "in":
            # in.(a,b,c)
            items = v_str.strip("()").split(",")
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
    """Сериализуем dict/list → JSON-строку для PostgreSQL."""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return v


# ─── Главный класс ────────────────────────────────────────────────────────────

class DBAdapter:
    """
    Двухуровневый адаптер.

    Использование:
        dba = DBAdapter()                          # глобальные .env
        dba = DBAdapter(sb_url="...", sb_key="...") # явные ключи Supabase

        rows   = await dba.get("bots", {"id": "eq.bot_1"})
        row    = await dba.post("users", {"name": "Ivan"})
        ok     = await dba.patch("bots", {"id": "eq.bot_1"}, {"status": "IDLE"})
        ok     = await dba.delete("users", {"id": "eq.u_1"})
        result = await dba.rpc("deduct_ai_tokens", {"p_bot_id": "bot_1", "p_amount": 100})
    """

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
            col_clause = ", ".join(
                f'"{c.strip()}"' for c in columns.split(",") if c.strip()
            )

        sql = f'SELECT {col_clause} FROM "{table}" WHERE {where}'
        if order:
            sql += f" {order}"
        if limit:
            sql += f" {limit}"

        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *values)
        return [dict(r) for r in rows]

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
        return dict(row) if row else {}

    async def _pg_patch(self, table: str, filter_params: dict, data: dict) -> bool:
        pool = await get_pg_pool()
        if pool is None:
            raise RuntimeError("PG unavailable")

        set_parts: list[str] = []
        set_vals:  list      = []
        for i, (k, v) in enumerate(data.items(), start=1):
            set_parts.append(f'"{k}" = ${i}')
            set_vals.append(_prepare_value(v))

        # WHERE плейсхолдеры начинаются с индекса len(set_vals)+1
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
        """Вызывает хранимую процедуру: SELECT func($1, $2, ...)"""
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
        """Вернуть список строк. Primary: PostgreSQL. Fallback: Supabase."""
        params = params or {}
        if _pg_available:
            try:
                return await self._pg_get(table, params)
            except Exception as e:
                logger.warning(f"[DBAdapter] PG get({table}) → fallback: {e}")
        return await self._sb_get(table, params)

    async def post(self, table: str, data: dict = None, json: dict = None, headers: dict = None) -> dict:
        """Вставить строку и вернуть её. Primary: PostgreSQL. Fallback: Supabase."""
        payload = data or json or {}
        if _pg_available:
            try:
                return await self._pg_post(table, payload)
            except Exception as e:
                logger.warning(f"[DBAdapter] PG post({table}) → fallback: {e}")
        return await self._sb_post(table, payload)

    async def patch(self, table: str, params: dict = None, json: dict = None,
                    data: dict = None, headers: dict = None) -> bool:
        """Обновить строки. Primary: PostgreSQL. Fallback: Supabase."""
        filter_p = params or {}
        payload  = json or data or {}
        if _pg_available:
            try:
                return await self._pg_patch(table, filter_p, payload)
            except Exception as e:
                logger.warning(f"[DBAdapter] PG patch({table}) → fallback: {e}")
        return await self._sb_patch(table, filter_p, payload)

    async def delete(self, table: str, params: dict = None) -> bool:
        """Удалить строки. Primary: PostgreSQL. Fallback: Supabase."""
        filter_p = params or {}
        if _pg_available:
            try:
                return await self._pg_delete(table, filter_p)
            except Exception as e:
                logger.warning(f"[DBAdapter] PG delete({table}) → fallback: {e}")
        return await self._sb_delete(table, filter_p)

    async def rpc(self, func: str, params: dict) -> object:
        """Вызвать хранимую процедуру. Primary: PostgreSQL. Fallback: Supabase."""
        if _pg_available:
            try:
                return await self._pg_rpc(func, params)
            except Exception as e:
                logger.warning(f"[DBAdapter] PG rpc({func}) → fallback: {e}")
        return await self._sb_rpc(func, params)

    # ── Совместимость с Supabase httpx-клиентом (для server.py helpers) ───────

    async def raw_get(self, path: str, params: dict = None) -> httpx.Response:
        """Прямой httpx-GET к Supabase REST (для обратной совместимости)."""
        async with httpx.AsyncClient(timeout=15) as c:
            return await c.get(
                f"{self.sb_url}/rest/v1/{path}",
                headers=self._sb_h,
                params=params or {},
            )

    async def raw_post(self, path: str, json_data: dict = None, extra_headers: dict = None) -> httpx.Response:
        """Прямой httpx-POST к Supabase REST (для обратной совместимости)."""
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
    """Вернуть (или создать) глобальный адаптер."""
    global _default_adapter
    if _default_adapter is None:
        _default_adapter = DBAdapter(sb_url, sb_key)
    return _default_adapter
