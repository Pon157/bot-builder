import asyncio
import logging
import json
import httpx
import os
import sys
import hashlib
import time
import re
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any, Union, Callable, Awaitable

# Добавили BaseMiddleware
from aiogram import Bot, Dispatcher, Router, F, BaseMiddleware
from aiogram.enums import ParseMode, ContentType, ChatMemberStatus
from aiogram.filters import CommandStart, Command, ChatMemberUpdatedFilter
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
    ReplyKeyboardRemove, ForumTopicCreated, ChatMemberUpdated,
    MessageReactionUpdated
)
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter
from aiogram.client.session.aiohttp import AiohttpSession
try:
    from aiohttp_socks import ProxyConnector as _ProxyConnector
    _PROXY_URL = os.getenv("TG_PROXY_URL", "socks5://ZpqqLu:fsgQGg@45.93.68.226:8000")
    def _make_session():
        if _PROXY_URL:
            return AiohttpSession(connector=_ProxyConnector.from_url(_PROXY_URL))
        return None
except ImportError:
    def _make_session():
        return None


from dotenv import load_dotenv
load_dotenv()
from db_adapter import DBAdapter, init_pg_pool

class LicenseMiddleware(BaseMiddleware):
    def __init__(self, bot_instance):
        self.bot_instance = bot_instance
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        # Проверка лицензии
        if getattr(self.bot_instance, 'license_expired', False):
            if isinstance(event, Message):
                await event.answer("❌ <b>Лицензия этого бота истекла.</b>\nПожалуйста, продлите её в панели управления.")
            return 
        return await handler(event, data)

class SubscriptionMiddleware(BaseMiddleware):
    """
    Проверяет обязательную подписку на каналы/чаты перед обработкой сообщения.
    Если пользователь не подписан — отправляет список каналов с кнопкой проверки.
    Пропускает: администраторов бота, callback с check_sub.
    """
    def __init__(self, bot_instance):
        self.bot_instance = bot_instance
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any]
    ) -> Any:
        required_channels = getattr(self.bot_instance, 'required_channels', [])

        if not required_channels:
            return await handler(event, data)

        user_tg = getattr(event, 'from_user', None)
        if not user_tg:
            return await handler(event, data)

        user_id = user_tg.id

        logger.info(f"[SubCheck] user={user_id} channels={[c.get('id') for c in required_channels]}")

        # Пропускаем администраторов
        if user_id in (self.bot_instance.admin_ids or set()):
            logger.info(f"[SubCheck] user={user_id} — ADMIN, skip")
            return await handler(event, data)

        # Пропускаем callback "check_sub"
        if isinstance(event, CallbackQuery) and event.data == "check_sub":
            return await handler(event, data)

        # Проверяем подписку на все каналы
        not_subscribed = []
        for ch in required_channels:
            ch_id = ch.get('id', '').strip()
            if not ch_id:
                continue
            try:
                member = await self.bot_instance.bot.get_chat_member(ch_id, user_id)
                logger.info(f"[SubCheck] user={user_id} ch={ch_id} status={member.status}")
                if member.status in ('left', 'kicked', 'banned'):
                    not_subscribed.append(ch)
            except Exception as e:
                logger.warning(f"[SubCheck] get_chat_member error ch={ch_id}: {e}")
                not_subscribed.append(ch)

        if not_subscribed:
            logger.info(f"[SubCheck] user={user_id} NOT subscribed to: {[c.get('id') for c in not_subscribed]}")
            rows = []
            for ch in not_subscribed:
                label = ch.get('title') or ch.get('id', 'Канал')
                url = ch.get('url', '') or f"https://t.me/{str(ch.get('id', '')).lstrip('@')}"
                rows.append([InlineKeyboardButton(text=f"📢 {label}", url=url)])
            rows.append([InlineKeyboardButton(text="✅ Я подписался — проверить", callback_data="check_sub")])
            kb = InlineKeyboardMarkup(inline_keyboard=rows)

            msg_text = (
                "🔒 <b>Для использования бота необходимо подписаться на наши каналы:</b>\n\n"
                + "\n".join(f"• {ch.get('title') or ch.get('id', 'Канал')}" for ch in not_subscribed)
                + "\n\nПосле подписки нажмите кнопку ниже 👇"
            )
            if isinstance(event, Message):
                await event.answer(msg_text, reply_markup=kb)
            elif isinstance(event, CallbackQuery):
                await event.answer("❌ Вы ещё не подписались на все каналы!", show_alert=True)
            return

        logger.info(f"[SubCheck] user={user_id} — OK, all subscribed")
        return await handler(event, data)


class BanMiddleware(BaseMiddleware):
    def __init__(self, bot_instance):
        self.bot_instance = bot_instance
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any]
    ) -> Any:
        # Извлекаем пользователя из события (сообщения или кнопки)
        user_tg = getattr(event, 'from_user', None)
        
        if user_tg:
            user_id = user_tg.id
            # Ищем юзера в кэше бота
            user = next((u for u in self.bot_instance.users_list if u.get('id') == user_id), None)
            
            # ЖЕЛЕЗОБЕТОН: Если забанен — СРАЗУ БЛОК без проверки админа
            if user and user.get("is_banned"):
                # Если это АДМИН — предлагаем разбаниться, не блокируем
                is_admin = (user_id in self.bot_instance.admin_ids) if self.bot_instance.admin_ids else False
                if is_admin:
                    # Пропускаем callback с разбаном
                    if isinstance(event, CallbackQuery) and event.data == "selfunban":
                        return await handler(event, data)
                    unban_kb = InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔓 Разбанить себя", callback_data="selfunban")
                    ]])
                    if isinstance(event, Message):
                        await event.answer(
                            "⚠️ <b>Вы случайно забанили себя (администратора).</b>\n"
                            "Нажмите кнопку ниже, чтобы снять блокировку:",
                            reply_markup=unban_kb
                        )
                    elif isinstance(event, CallbackQuery):
                        await event.answer("⚠️ Вы забанили себя. Используйте /start чтобы разбаниться.", show_alert=True)
                    return  # ПРЕРЫВАЕМ, но кнопка предложена
                # Если это сообщение — пишем текстом
                if isinstance(event, Message):
                    await event.answer("🚫 <b>Вы заблокированы в этом боте.</b>")
                # Если это кнопка — показываем уведомление
                elif isinstance(event, CallbackQuery):
                    await event.answer("🚫 Вы заблокированы.", show_alert=True)
                    
                return # ПРЕРЫВАЕМ выполнение
        
        return await handler(event, data)


class MemoryBaseMiddleware(BaseMiddleware):
    """
    Проверяет входящих пользователей по антиспам-базе MemoryBase.
    Если пользователь найден и его причина совпадает с выбранными фильтрами —
    ограничивает доступ к боту и уведомляет администраторов.
    """
    def __init__(self, bot_instance):
        self.bi = bot_instance
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any]
    ) -> Any:
        # Проверяем, включена ли MemoryBase
        settings = getattr(self.bi, 'settings', {})
        _uid = getattr(getattr(event, 'from_user', None), 'id', '?')
        logger.info(f"[MB] middleware called uid={_uid} enabled={settings.get('memoryBaseEnabled')} settings_keys={list(settings.keys())[:5]}")
        if not settings.get('memoryBaseEnabled', False):
            return await handler(event, data)

        user_tg = getattr(event, 'from_user', None)
        if not user_tg:
            return await handler(event, data)

        user_id = user_tg.id

        # Пропускаем администраторов
        if user_id in (self.bi.admin_ids or set()):
            return await handler(event, data)

        # Пропускаем callback с разбаном MB
        if isinstance(event, CallbackQuery) and event.data and event.data.startswith("mb_unban_"):
            return await handler(event, data)

        # Ищем пользователя в локальном кэше
        user_rec = next((u for u in self.bi.users_list if u.get('id') == user_id), None)

        # ── Локальный TTL-кэш: не ходим в Supabase чаще раза в 5 минут ──────
        # Исключение: если mb_restricted=True — перепроверяем каждые 5 мин (вдруг разбанили)
        MB_LOCAL_TTL = 300  # 5 минут
        last_mb_check = user_rec.get('last_mb_check', 0) if user_rec else 0
        mb_restricted = user_rec.get('mb_restricted', False) if user_rec else False

        if user_rec and not mb_restricted and (time.time() - last_mb_check < MB_LOCAL_TTL):
            # Знаем статус, он свежий и пользователь чист — пропускаем без запроса
            return await handler(event, data)

        # ── Проверяем актуальный статус в Supabase ──────────────────────────
        # Только если: новый пользователь / кэш устарел / пользователь был заблокирован
        try:
            _rows = await self.bi.db.get(
                "memory_base_cache",
                {"user_id": f"eq.{user_id}", "select": "status,reasons,expires_at"},
            )
            if _rows:
                _cache_row = _rows[0]
                _status  = _cache_row.get('status', 'not_found')
                _reasons = _cache_row.get('reasons', [])
                logger.info(f"[MB] uid={user_id} supabase status={_status} reasons={_reasons}")

                if _status == 'in_base':
                    _block_reasons = settings.get('memoryBaseBlockReasons', [])
                    _should_block  = (not _block_reasons or any(r in _block_reasons for r in _reasons))
                    if _should_block:
                        if user_rec:
                            user_rec['mb_restricted'] = True
                            user_rec['mb_reasons']    = _reasons
                        if isinstance(event, Message):
                            await event.answer(
                                "🚫 <b>Доступ ограничен.</b>\n\n"
                                "Вы находитесь в антиспам-базе "
                                "<a href=\"https://t.me/MemoryBaseBot\">MemoryBase</a>.\n"
                                "Для восстановления доступа обратитесь к владельцу бота."
                            )
                        elif isinstance(event, CallbackQuery):
                            await event.answer("🚫 Доступ ограничен (MemoryBase).", show_alert=True)
                        # ── Уведомление в админ чат (один раз) ──────────
                        _already_notified = user_rec.get('mb_notified', False) if user_rec else False
                        if self.bi.admin_chat_id and not _already_notified:
                            try:
                                _rh = {"scammer":"Мошенник ⛔️","bad_admin":"Плохой админ ❌",
                                       "bad_owner":"Плохой владелец ❌","bad_behavior":"Нарушитель 🐔",
                                       "spammer":"Спамер 🚫","raider":"Рейдер 💥"}
                                _rt = ", ".join(_rh.get(r,r) for r in _reasons if not r.startswith("other:"))
                                _ot = [r.replace("other:","") for r in _reasons if r.startswith("other:")]
                                if _ot: _rt += (", " if _rt else "") + ", ".join(_ot)
                                _nm = user_tg.full_name or f"User {user_id}"
                                _un = f" (@{user_tg.username})" if user_tg.username else ""
                                _is_start = isinstance(event, Message) and bool(getattr(event, 'text', '') or '') and (event.text or '').strip().startswith("/start")
                                _act = "написал /start" if _is_start else "написал сообщение"
                                _kb = InlineKeyboardMarkup(inline_keyboard=[[
                                    InlineKeyboardButton(text="✅ Разрешить доступ", callback_data=f"mb_unban_{user_id}")
                                ]])
                                await self.bi.bot.send_message(
                                    self.bi.admin_chat_id,
                                    f"🔴 <b>MemoryBase: пользователь в базе</b>\n\n"
                                    f"👤 {_nm}{_un}\n🆔 <code>{user_id}</code>\n"
                                    f"📌 <b>Причина(ы):</b> {_rt or '—'}\n\n"
                                    f"Пользователь {_act} и был заблокирован.\n"
                                    f"Если хотите разрешить ему писать — нажмите кнопку ниже 👇",
                                    reply_markup=_kb,
                                )
                                if user_rec:
                                    user_rec['mb_notified'] = True
                                    await self.bi.sync_queue.put(("sync_state", None))
                            except Exception as _ne:
                                logger.warning(f"[MB] admin notify error: {_ne}")
                        return  # БЛОКИРУЕМ
                else:
                    # Статус clean/not_found — снимаем локальный флаг если был
                    if user_rec and user_rec.get('mb_restricted'):
                        user_rec['mb_restricted'] = False
                        user_rec['mb_reasons']    = []
                    # Обновляем метку — при следующем сообщении не будем ходить в Supabase
                    if user_rec:
                        user_rec['last_mb_check'] = int(time.time())
                # Запись есть, статус не in_base — пропускаем если last_mb_check достаточно свежий
                if time.time() - last_mb_check < 86400:
                    return await handler(event, data)
                # Иначе — ставим в очередь на перепроверку (могло устареть)
            else:
                # Записей в кэше вообще нет — нужна первичная проверка
                logger.info(f"[MB] uid={user_id} no cache row — queuing check")
        except Exception as _e:
            logger.warning(f"[MB] db pre-check error: {_e} — всё равно ставим в очередь")
            # Не пропускаем — ставим в очередь на проверку несмотря на ошибку кэша

        # Уведомляем пользователя что идёт проверка
        wait_msg = None
        try:
            if isinstance(event, Message):
                wait_msg = await event.answer(
                    "🔍 <b>Проверяю вас по базе пользователей в Memory Base...</b>\nПожалуйста, подождите."
                )
        except Exception:
            pass

        # Ждём результат проверки (блокируем до ответа чекера)
        should_block = await self._check_and_restrict(event, user_tg, user_rec, settings)

        # Удаляем сообщение о проверке
        if wait_msg:
            try:
                await wait_msg.delete()
            except Exception:
                pass

        if should_block:
            return
        return await handler(event, data)

    async def _check_and_restrict(self, event: Any, user_tg, user_rec: Optional[dict], settings: dict):
        """Проверяет пользователя и ограничивает при необходимости."""
        user_id = user_tg.id
        _db = self.bi.db

        try:
            logger.info(f"[MB] _check_and_restrict started for user_id={user_id}")

            # ── ШАГ 1: Ставим задачу в очередь ──────────────────────────
            existing = await _db.get("mb_check_queue", {
                "user_id": f"eq.{user_id}",
                "status":  "in.(pending,processing)",
                "select":  "id",
            })
            logger.info(f"[MB] queue check existing={existing}")
            if not existing:
                ins = await _db.post("mb_check_queue", {
                    "user_id":    user_id,
                    "username":   user_tg.username or "",
                    "status":     "pending",
                    "created_at": datetime.now(timezone.utc),
                })
                logger.info(f"[MB] queue insert result={bool(ins)}")
            else:
                logger.info(f"[MB] task already in queue for user={user_id}, waiting...")

            # ── ШАГ 2: Поллим кэш до 30 сек ─────────────────────────────
            import time as _time
            deadline = _time.time() + 30
            row = None
            while _time.time() < deadline:
                await asyncio.sleep(3)
                rows = await _db.get("memory_base_cache", {"user_id": f"eq.{user_id}"})
                if rows:
                    row = rows[0]
                    logger.info(f"[MB] cache hit for user={user_id}: {row.get('status')}")
                    break
                logger.debug(f"[MB] cache miss for user={user_id}, retrying...")

            if row is None:
                # Таймаут — пускаем, обновляем метку
                if user_rec:
                    user_rec['last_mb_check'] = int(_time.time())
                return False

            status  = row.get('status', 'clean')
            reasons = row.get('reasons', [])

            # Обновляем метку проверки
            if user_rec:
                user_rec['last_mb_check'] = int(time.time())

            if status != 'in_base':
                return False

            # Определяем причины для блокировки из настроек
            block_reasons = settings.get('memoryBaseBlockReasons', [])
            # Если список пуст — блокируем по всем причинам
            should_block = (
                not block_reasons or
                any(r in block_reasons for r in reasons)
            )

            if not should_block:
                return False

            # Ограничиваем пользователя
            if user_rec:
                user_rec['mb_restricted'] = True
                user_rec['mb_reasons']    = reasons
            else:
                # Создаём запись
                user_rec = {
                    "id": user_id,
                    "first_name": user_tg.first_name or "",
                    "username": user_tg.username or "",
                    "is_banned": False,
                    "mb_restricted": True,
                    "mb_reasons": reasons,
                    "warns": 0,
                    "joined_at": int(time.time()),
                    "last_seen": int(time.time()),
                    "last_topic_id": None,
                    "last_mb_check": int(time.time()),
                }
                self.bi.users_list.append(user_rec)

            await self.bi.sync_queue.put(("sync_state", None))

            # Уведомляем пользователя
            reasons_human = {
                "scammer":      "Мошенник ⛔️",
                "bad_admin":    "Плохой админ ❌",
                "bad_owner":    "Плохой владелец ❌",
                "bad_behavior": "Нарушитель правил 🐔",
                "spammer":      "Спамер 🚫",
                "raider":       "Рейдер 💥",
            }
            r_text = ", ".join(reasons_human.get(r, r) for r in reasons if not r.startswith("other:"))
            other  = [r.replace("other:", "") for r in reasons if r.startswith("other:")]
            if other:
                r_text += (", " if r_text else "") + ", ".join(other)

            # ── Уведомление пользователю ─────────────────────────────────
            try:
                await self.bi.bot.send_message(
                    user_id,
                    f"🚫 <b>Ваш доступ к боту ограничен.</b>\n\n"
                    f"Вы найдены в антиспам-базе "
                    f"<a href=\"https://t.me/MemoryBaseBot\">MemoryBase</a>.\n"
                    f"<b>Причина:</b> {r_text or '—'}\n\n"
                    f"Для восстановления доступа обратитесь к владельцу бота."
                )
            except Exception:
                pass

            # ── Уведомление администраторов (только один раз) ────────────
            already_notified = user_rec.get('mb_notified', False) if user_rec else False
            if self.bi.admin_chat_id and not already_notified:
                try:
                    name_str  = user_tg.full_name or f"User {user_id}"
                    uname_str = f" (@{user_tg.username})" if user_tg.username else ""

                    # Определяем что именно написал пользователь
                    is_start = (
                        isinstance(event, Message) and
                        event.text and event.text.strip().startswith("/start")
                    )
                    action_str = "написал /start" if is_start else "написал сообщение"

                    unban_kb = InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(
                            text="✅ Разрешить доступ",
                            callback_data=f"mb_unban_{user_id}"
                        )
                    ]])

                    await self.bi.bot.send_message(
                        self.bi.admin_chat_id,
                        f"🔴 <b>MemoryBase: пользователь в базе</b>\n\n"
                        f"👤 {name_str}{uname_str}\n"
                        f"🆔 <code>{user_id}</code>\n"
                        f"📌 <b>Причина(ы):</b> {r_text or '—'}\n\n"
                        f"Пользователь {action_str} и был заблокирован.\n"
                        f"Если хотите разрешить ему писать — нажмите кнопку ниже 👇",
                        reply_markup=unban_kb,
                    )
                    # Ставим флаг чтобы не спамить повторно
                    if user_rec:
                        user_rec['mb_notified'] = True
                        await self.bi.sync_queue.put(("sync_state", None))
                except Exception as e:
                    logger.warning(f"[MB] admin notify error: {e}")

            return True  # Заблокирован

        except Exception as e:
            logger.error(f"[MB] _check_and_restrict error: {e}")
            return False


# --- ГЛОБАЛЬНАЯ КОНФИГУРАЦИЯ ЛОГИРОВАНИЯ ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotCoreEngine")

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_anon_id(user_id: int) -> str:
    """Генерация короткого хеша для анонимности"""
    return hashlib.md5(str(user_id).encode()).hexdigest()[:6].upper()

# ── ПРИОРИТЕТЫ ТИКЕТОВ ────────────────────────────────────────────────────────
PRIORITY_LEVELS = {
    "normal": {
        "label": "Нейтральный",
        "prefix": "🟡",
        "notify_user": "ℹ️ <b>Приоритет вашего обращения:</b> Нейтральный.",
    },
    "high": {
        "label": "Высокий",
        "prefix": "🔴",
        "notify_user": "🔴 <b>Приоритет вашего обращения повышен!</b>\nОператоры рассмотрят его в первую очередь.",
    },
    "low": {
        "label": "Низкий",
        "prefix": "⚪",
        "notify_user": "⚪ <b>Приоритет вашего обращения снижен.</b>\nОбращение будет рассмотрено в порядке общей очереди.",
    },
}

def build_topic_name(user: dict, settings: dict, priority: str = "normal") -> str:
    """Формирует название топика с учётом приоритета."""
    is_anon = settings.get('anonymousTopics', False)
    prefix = PRIORITY_LEVELS.get(priority, PRIORITY_LEVELS["normal"])["prefix"]
    if is_anon:
        base = f"#{get_anon_id(user['id'])}"
    else:
        base = f"{user.get('first_name', 'Пользователь')} [{user['id']}]"
    return f"{prefix} {base}"

def format_admin_header(m: Message, settings: dict, is_first: bool = False, btn_text: str = "") -> str:
    """Формирование заголовка сообщения для админа"""
    is_anon = settings.get('anonymousTopics', False)
    uid = m.from_user.id
    anon_tag = f"#{get_anon_id(uid)}"
    
    if is_anon:
        user_info = f"👤 <b>Аноним {anon_tag}</b>"
    else:
        info_parts = []
        if settings.get('showHeaderName', True):
            name = m.from_user.full_name or "Пользователь"
            info_parts.append(f"<b>{name}</b>")
        
        if settings.get('showHeaderUsername', True) and m.from_user.username:
            info_parts.append(f"(@{m.from_user.username})")
            
        if settings.get('showHeaderId', True):
            info_parts.append(f"ID: <code>{uid}</code>")
            
        user_info = " | ".join(info_parts) if info_parts else f"Юзер {anon_tag}"

    status_line = ""
    if btn_text:
        status_line = settings.get('ticketMessageHeader', "🆘 <b>ЗАЯВКА</b>")
        if "{btn}" in status_line:
            status_line = status_line.replace("{btn}", btn_text)
        elif "[Кнопка" not in status_line:
            status_line += f" [Кнопка: {btn_text}]:"
    elif is_first:
        status_line = settings.get('firstMessageHeader', "🆕 <b>ПЕРВОЕ ОБРАЩЕНИЕ:</b>")
    else:
        status_line = settings.get('commonMessageHeader', "📩 <b>СООБЩЕНИЕ:</b>")

    return f"{status_line}\n{user_info}\n\n"

# ── SANDBOX ─────────────────────────────────────────────────────────────────────
#
# Архитектура: пользовательский код выполняется через asyncio.create_subprocess_exec
# в дочернем python-процессе. Данные передаются через stdin/stdout как JSON.
# OS-лимиты (RLIMIT_CPU, RLIMIT_AS) устанавливаются внутри дочернего процесса.
# Wall-clock таймаут контролируется asyncio.wait_for.
#
# Такой подход полностью изолирует выполнение и корректно работает в asyncio/uvicorn.

# ── Скрипт, который запускается как дочерний процесс ─────────────────────────
_SANDBOX_RUNNER_PY = r'''
import sys, json, os

# 1. Read stdin first — before anything else
try:
    _raw = sys.stdin.buffer.read()
    _data = json.loads(_raw)
    _code = _data["code"]
    _ctx  = _data["ctx"]
except Exception as e:
    sys.stdout.write(json.dumps({"ok": False, "error": "Input error: " + str(e)}) + "\n")
    sys.exit(1)

# 2. Clear ALL environment variables immediately.
#    Even if code somehow reaches os, environ will be empty.
try:
    os.environ.clear()
except Exception:
    pass

# 3. CPU time limit — kills process via SIGXCPU after 4 seconds
try:
    import resource as _res
    _res.setrlimit(_res.RLIMIT_CPU, (4, 4))
except Exception:
    pass

# 4. Import allowed modules.
#    NOTE: We do NOT set RLIMIT_AS here — it breaks imports on many systems
#    because Python's virtual address space includes memory-mapped libs.
#    Memory is bounded by CPU timeout + wall-clock timeout in parent instead.
try:
    import requests  as _req
    import json      as _json
    import datetime  as _dt
    import math      as _math
    import re        as _re
    import xml.etree.ElementTree as _ET
except ImportError as e:
    sys.stdout.write(json.dumps({"ok": False, "error": "Module error: " + str(e)}) + "\n")
    sys.exit(1)

# 5. Memory watchdog via RSS (works on Linux without RLIMIT_AS issues)
#    We check RSS after exec — if it exceeds 200MB, the code probably caused it.
_RSS_LIMIT_MB = 200

def _rss_mb():
    try:
        with open("/proc/self/status") as _f:
            for _line in _f:
                if _line.startswith("VmRSS:"):
                    return int(_line.split()[1]) // 1024
    except Exception:
        pass
    return 0

# 6. SafeModuleProxy — wraps ALL modules passed to sandbox.
#    Blocks: for mod in (json, re, ET): mod.sys  ->  os.environ  (the real attack)
#    Uses AttributeError so hasattr() returns False cleanly.
class _SMP:
    _BLK = frozenset([
        "sys", "os", "__builtins__", "__loader__", "__spec__", "__file__",
        "__cached__", "__path__", "__package__", "builtins", "environ",
        "__import__", "__build_class__", "__initializing__", "modules",
        "__doc__", "__name__",
    ])
    def __init__(self, mod, name=""):
        object.__setattr__(self, "_m", mod)
        object.__setattr__(self, "_n", name)
    def __getattr__(self, attr):
        if (attr.startswith("__") and attr.endswith("__")) or attr in self._BLK:
            raise AttributeError("'" + object.__getattribute__(self,"_n") + "' has no attribute '" + attr + "'")
        return getattr(object.__getattribute__(self, "_m"), attr)
    def __setattr__(self, attr, val):
        raise PermissionError("Module modification forbidden")
    def __repr__(self):
        return "<module '" + object.__getattribute__(self,"_n") + "'>"

# 7. Safe helpers
_ALL_DUNDERS = frozenset(
    [n for n in dir(object) if n.startswith("__") and n.endswith("__")] +
    ["_module","__wrapped__","__closure__","__annotations__",
     "__build_class__","__loader__","__spec__","__file__","__cached__"]
)

def _safe_getattr(obj, name, *args):
    if isinstance(name, str) and (
        name in _ALL_DUNDERS or (name.startswith("__") and name.endswith("__"))
    ):
        raise PermissionError("Access to '" + str(name) + "' forbidden")
    return getattr(obj, name, *args)

def _safe_pow(base, exp, mod=None):
    if isinstance(exp, (int, float)) and abs(exp) > 1000:
        raise ValueError("Exponent too large (max 1000)")
    return pow(base, exp, mod) if mod is not None else pow(base, exp)

_BH = ("localhost","127.","0.0.0.0","::1","169.254","10.","192.168.","172.",
       "metadata.google","metadata.internal")

class _SR:
    @staticmethod
    def _chk(url):
        u = str(url).lower()
        if u.startswith("file://"): raise PermissionError("file:// forbidden")
        for h in _BH:
            if h in u: raise PermissionError("Internal network forbidden")
    def get(self, url, **kw):
        self._chk(url); kw.setdefault("timeout",8); return _req.get(url,**kw)
    def post(self, url, **kw):
        self._chk(url); kw.setdefault("timeout",8); return _req.post(url,**kw)
    def put(self, url, **kw):
        self._chk(url); kw.setdefault("timeout",8); return _req.put(url,**kw)
    def delete(self, url, **kw):
        self._chk(url); kw.setdefault("timeout",8); return _req.delete(url,**kw)

def _blk(*a, **kw): raise PermissionError("Function disabled in sandbox")

# 7b. AST re-validation inside subprocess (defense in depth)
#     Parent process already checked, but we verify again in case of future refactoring.
try:
    import ast as _ast
    _BLOCKED_ATTRS_R = frozenset([
        "__class__","__base__","__bases__","__mro__","__subclasses__",
        "__globals__","__builtins__","__dict__","__code__","__func__",
        "__self__","__module__","__qualname__","__init__","__new__",
        "__reduce__","__reduce_ex__","__getattribute__","__import__",
        "__loader__","__spec__","__file__","__cached__","__wrapped__",
        "__weakref__","__build_class__","__closure__","__annotations__",
    ])
    _BLOCKED_CALLS_R = frozenset([
        "eval","exec","compile","open","input","breakpoint","vars","dir",
        "locals","globals","memoryview","type","object","super",
        "classmethod","staticmethod","property",
    ])
    _BLOCKED_STR_R = frozenset([
        "__class__","__base__","__subclasses__","__globals__","__builtins__",
        "__dict__","__import__","__reduce__","__init__","__new__",
        ".env","/etc/passwd","/etc/shadow","/proc/","/sys/",
        "subprocess","ctypes","cffi","pty",
    ])
    def _ast_recheck(source):
        try:
            _tree = _ast.parse(source, mode="exec")
        except SyntaxError as _e:
            return False, "SyntaxError: " + str(_e)
        for _node in _ast.walk(_tree):
            if isinstance(_node, _ast.Attribute):
                _a = _node.attr
                if _a in _BLOCKED_ATTRS_R or (_a.startswith("__") and _a.endswith("__")):
                    return False, "Blocked attr: " + _a
            if isinstance(_node, _ast.Call):
                _f = _node.func
                if isinstance(_f, _ast.Name) and _f.id in _BLOCKED_CALLS_R:
                    return False, "Blocked call: " + _f.id
                if isinstance(_f, _ast.Attribute) and _f.attr in _BLOCKED_CALLS_R:
                    return False, "Blocked method: " + _f.attr
            if isinstance(_node, _ast.Constant) and isinstance(_node.value, str):
                for _p in _BLOCKED_STR_R:
                    if _p in _node.value:
                        return False, "Blocked string: " + _p
            if isinstance(_node, (_ast.Import, _ast.ImportFrom)):
                return False, "import forbidden"
        return True, None
    _ast_ok, _ast_err = _ast_recheck(_code)
    if not _ast_ok:
        sys.stdout.write(json.dumps({"ok": False, "error": "Blocked: " + _ast_err}) + "\n")
        sys.exit(1)
except Exception as _e:
    pass  # AST check failed unexpectedly - proceed anyway (parent already checked)

# 8. Build sandbox
_sb = {
    "user_id":    _ctx.get("user_id", 0),
    "username":   _ctx.get("username", ""),
    "first_name": _ctx.get("first_name", ""),
    "text":       _ctx.get("text", ""),
    "bot_id":     _ctx.get("bot_id", ""),
    "requests":   _SR(),
    "json":       _SMP(_json,    "json"),
    "datetime":   _SMP(_dt,      "datetime"),
    "math":       _SMP(_math,    "math"),
    "re":         _SMP(_re,      "re"),
    "ET":         _SMP(_ET,      "ET"),
    "reply_text": "",
    "__builtins__": {
        "str":str,"int":int,"float":float,"bool":bool,"bytes":bytes,
        "list":list,"dict":dict,"tuple":tuple,"set":set,"frozenset":frozenset,
        "len":len,"range":range,"enumerate":enumerate,"zip":zip,
        "map":map,"filter":filter,"reversed":reversed,"iter":iter,"next":next,
        "min":min,"max":max,"sum":sum,"abs":abs,"round":round,
        "sorted":sorted,"pow":_safe_pow,"divmod":divmod,
        "repr":repr,"format":format,"chr":chr,"ord":ord,
        "hex":hex,"oct":oct,"bin":bin,
        "isinstance":isinstance,"issubclass":issubclass,
        "hasattr":hasattr,"callable":callable,
        "getattr":_safe_getattr,
        "Exception":Exception,"ValueError":ValueError,"TypeError":TypeError,
        "KeyError":KeyError,"IndexError":IndexError,"AttributeError":AttributeError,
        "PermissionError":PermissionError,"RuntimeError":RuntimeError,
        "StopIteration":StopIteration,"AssertionError":AssertionError,
        "True":True,"False":False,"None":None,
        "print":lambda *a,**kw:None,
        "__import__":_blk,"open":_blk,"eval":_blk,"exec":_blk,
        "compile":_blk,"globals":_blk,"locals":_blk,"vars":_blk,
        "dir":_blk,"type":_blk,"object":_blk,"super":_blk,
        "delattr":_blk,"setattr":_blk,"input":_blk,
        "memoryview":_blk,"breakpoint":_blk,
        "classmethod":_blk,"staticmethod":_blk,"property":_blk,
        "__loader__":None,"__spec__":None,"__build_class__":_blk,
    },
}

# 9. Execute and check memory
try:
    exec(_code, _sb)

    # Memory check after execution
    rss = _rss_mb()
    if rss > _RSS_LIMIT_MB:
        sys.stdout.write(json.dumps({"ok": False, "error": "Memory limit exceeded"}) + "\n")
        sys.exit(1)

    _reply = str(_sb.get("reply_text","")).strip()
    if len(_reply) > 4000:
        _reply = _reply[:4000] + "..."
    sys.stdout.write(json.dumps({"ok": True, "reply": _reply}) + "\n")
except PermissionError as e:
    sys.stdout.write(json.dumps({"ok": False, "error": "Blocked: " + str(e)}) + "\n")
except MemoryError:
    sys.stdout.write(json.dumps({"ok": False, "error": "Memory limit exceeded"}) + "\n")
except Exception as e:
    sys.stdout.write(json.dumps({"ok": False, "error": str(e)}) + "\n")

'''



# --- ОСНОВНОЙ КЛАСС БОТА ---
class BotInstance:
    def __init__(self, config_data: dict):
        self.bot_id = config_data.get('id')
        self.token = config_data.get('token')
        
        # 1. ОБЯЗАТЕЛЬНО: Объявляем переменную сразу, чтобы Middleware её видел
        self.license_expired = False 
        
        self.sb_url = os.getenv("SUPABASE_URL", "").rstrip('/')
        self.sb_key = os.getenv("SUPABASE_KEY", "")

        # Новая БД (первичная) + Supabase (резерв)
        self.db = DBAdapter(self.sb_url, self.sb_key)

        # Авторизационные заголовки для прямых запросов к Supabase (legacy fallback)
        self.headers = {
            "apikey": self.sb_key,
            "Authorization": f"Bearer {self.sb_key}",
            "Content-Type": "application/json"
        }
        
        # Берем токен из конфига/окружения
        self.bot = Bot(token=self.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML), session=_make_session() or AiohttpSession())
        self.dp = Dispatcher()
        self.router = Router()
        
        self.msg_map = {}           # admin_msg_id → user_id
        self.user_to_admin_map = {}  # (user_id, user_msg_id) → admin_msg_id
        self.flood_cache = {}
        self.is_running = True
        self.sync_queue = asyncio.Queue()
        self.broadcast_cache = {}
        # Буфер для media group: {media_group_id: {"messages": [...], "user": ..., "task": ...}}
        self.media_group_buffer: Dict[str, dict] = {}
        
        # Сохраняем ссылку на конфиг для работы register_event
        self.config = config_data 
        
        # Сначала парсим конфиг, чтобы подгрузить настройки
        self.apply_config(config_data)

    async def register_event(self, is_incoming: bool = True):
        """Обновляет статистику в памяти и отправляет в Supabase"""
        try:
            today = datetime.now().strftime("%d.%m")
            
            # 1. Проверяем наличие stats в конфиге
            if not isinstance(self.config.get("stats"), dict):
                self.config["stats"] = {"history": [], "totalMessages": 0}
            
            st = self.config["stats"]
            
            # 2. Обновляем счетчики
            st["totalMessages"] = st.get("totalMessages", 0) + 1
            
            if is_incoming:
                st["incomingToday"] = st.get("incomingToday", 0) + 1
                if "outgoingToday" not in st: st["outgoingToday"] = 0
            else:
                st["outgoingToday"] = st.get("outgoingToday", 0) + 1
                if "incomingToday" not in st: st["incomingToday"] = 0

            # 3. Работа с историей
            history = st.get("history", [])
            if not isinstance(history, list): history = []
            
            day_entry = next((item for item in history if item.get("date") == today), None)

            if day_entry:
                if is_incoming:
                    day_entry["incoming"] = day_entry.get("incoming", 0) + 1
                else:
                    day_entry["outgoing"] = day_entry.get("outgoing", 0) + 1
            else:
                history.append({
                    "date": today, 
                    "incoming": 1 if is_incoming else 0, 
                    "outgoing": 0 if is_incoming else 1,
                    "totalUsers": len(self.config.get("connectedUsers", [])),
                    "activeUsers": 1
                })

            st["history"] = history[-14:] 
            self.config["stats"] = st 

            # 4. Отправка в БД
            ok = await self.db.patch("bots", {"id": f"eq.{self.bot_id}"}, {"stats": st})
            if not ok:
                logger.error("⚠️ Ошибка записи статы в БД")

        except Exception as e:
            logger.error(f"❌ Ошибка обновления статистики: {e}", exc_info=True)
        

    async def license_checker_logic(self):
        #Вынесли логику в отдельный метод, чтобы вызывать её при старте
        try:
            curr_time = int(time.time() * 1000)
            if self.license_expires_at and self.license_expires_at < curr_time:
                # Проверяем через getattr для безопасности или просто по флагу
                if not self.license_expired:
                    logger.warning(f" [!] Лицензия {self.bot_id} истекла!")
                    self.license_expired = True 
                    
                    await self.db.patch("bots", {"id": f"eq.{self.bot_id}"}, {"status": "IDLE"})
            else:
                self.license_expired = False
        except Exception as e:
            logger.error(f"Ошибка в license_checker_logic: {e}")

    async def license_checker(self):
        """Теперь воркер просто крутит логику в цикле"""
        logger.info(f"[*] Мониторинг лицензии для {self.bot_id} запущен")
        while self.is_running:
            await self.license_checker_logic()
            await asyncio.sleep(120)

    # ══════════════════════════════════════════════════════════════════
    # СТАФФ-СИСТЕМА
    # ══════════════════════════════════════════════════════════════════

    def _get_active_staff(self) -> list:
        """Возвращает список активных стафф-администраторов."""
        return [a for a in self.staff_admins if a.get('active', True) and a.get('tg_id')]

    def _assign_staff(self) -> dict | None:
        """Назначить администратора согласно режиму (random / least)."""
        active = self._get_active_staff()
        if not active:
            return None
        if self.staff_assign_mode == 'least':
            # Тот у кого меньше всего принятых тикетов
            return min(active, key=lambda a: a.get('stats', {}).get('ticketsAccepted', 0))
        # random
        import random as _rnd
        return _rnd.choice(active)

    def _find_staff_by_arg(self, arg: str) -> dict | None:
        """Ищет стафф-admin по ID (числу) или псевдониму."""
        arg = arg.strip().lstrip('@')
        for a in self.staff_admins:
            if str(a.get('tg_id', '')) == arg:
                return a
            if a.get('alias', '').lower() == arg.lower():
                return a
            if a.get('name', '').lower() == arg.lower():
                return a
        return None

    def _get_user_staff(self, user: dict) -> dict | None:
        """Возвращает текущего назначенного стафф-admin пользователя."""
        sid = user.get('assigned_staff_id')
        if not sid:
            return None
        return next((a for a in self.staff_admins if a.get('id') == sid), None)

    async def _post_staff_stat(self, staff_id: str, event: str, value: int = 1):
        """Отправляет обновление статистики на сервер."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f"{self.sb_url.replace('/rest/v1', '')}/api/bots/{self.bot_id}/staff/stat",
                    json={"staff_id": staff_id, "event": event, "value": value},
                    headers={"apikey": self.sb_key}
                )
        except Exception as e:
            logger.warning(f"[STAFF] Не удалось обновить стату: {e}")

    async def _assign_staff_to_user(self, user: dict, staff: dict, m=None):
        """Привязывает стафф-admin к пользователю, уведомляет обе стороны."""
        uid = user['id']
        old_staff_id = user.get('assigned_staff_id')

        user['assigned_staff_id'] = staff['id']
        user['assigned_staff_alias'] = staff.get('alias', staff.get('name', '?'))
        user['assigned_staff_tg'] = staff.get('tg_id')
        # Засекаем время назначения для расчёта avg response
        user['_staff_assigned_at'] = int(time.time() * 1000)

        # Уведомляем пользователя
        if self.staff_notify:
            try:
                await self.bot.send_message(
                    uid,
                    f"👤 <b>Ваше обращение принял:</b> {staff.get('alias', staff.get('name'))}",
                    parse_mode="HTML"
                )
            except Exception:
                pass

        # Уведомляем нового стафф-admin в личку
        try:
            thread_id = user.get('last_topic_id')
            topic_link = f"\nТопик: #{thread_id}" if thread_id else ""
            user_name = user.get('first_name', f"User#{uid}")
            username  = f" (@{user.get('username')})" if user.get('username') else ""
            await self.bot.send_message(
                staff['tg_id'],
                f"📨 <b>Новое обращение!</b>\n"
                f"Пользователь: <b>{user_name}{username}</b> (<code>{uid}</code>){topic_link}",
                parse_mode="HTML"
            )
        except Exception:
            pass

        # Статистика: принято
        asyncio.create_task(self._post_staff_stat(staff['id'], 'accepted'))

        # Если был старый и он другой — обновляем его стату (закрытие не считаем, просто логируем)
        if old_staff_id and old_staff_id != staff['id']:
            logger.info(f"[STAFF] Тикет {uid} перешёл от {old_staff_id} к {staff['id']}")

    async def _staff_keyboard_for_user(self, user: dict):
        """Строит ReplyKeyboardMarkup с кнопкой смены админа и (опционально) списком."""
        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
        buttons = []
        if self.staff_allow_switch:
            buttons.append([KeyboardButton(text="🔄 Сменить админа")])
        if self.staff_show_list:
            buttons.append([KeyboardButton(text=self.staff_list_btn_name)])
        if not buttons:
            return None
        return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=False)

    async def _handle_staff_list_request(self, uid: int):
        """Отправляет пользователю inline-список активных администраторов."""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        active = self._get_active_staff()
        if not active:
            await self.bot.send_message(uid, "😔 В данный момент нет доступных администраторов.", parse_mode="HTML")
            return
        buttons = []
        for a in active:
            buttons.append([InlineKeyboardButton(
                text=f"👤 {a.get('alias', a.get('name', '?'))}",
                callback_data=f"choose_staff:{a['id']}"
            )])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await self.bot.send_message(uid, "👥 <b>Выберите администратора:</b>", reply_markup=kb, parse_mode="HTML")

    def apply_config(self, data: dict):
        """Парсинг конфигурации с приоритетом новых полей"""
        raw_cfg = data.get('config', {}) if isinstance(data.get('config'), dict) else {}
        full_cfg = {**data, **raw_cfg} 
        
        self.vk_group_id = full_cfg.get('vk_group_id') or full_cfg.get('vkGroupId')

        # Читаем Admin ID (ID чата/форума для пересылки)
        admin_id_raw = full_cfg.get('admin_chat_id') or full_cfg.get('adminChatId')
        self.admin_chat_id = int(str(admin_id_raw).strip()) if admin_id_raw else None

        # Читаем список личных Telegram ID владельцев/администраторов бота
        raw_admin_ids = full_cfg.get('adminIds', [])
        self.admin_ids: set = set(int(x) for x in raw_admin_ids if x)

        # Настройки безопасности и тем
        self.settings = full_cfg.get('settings', {})
        self.use_topics = self.settings.get('useTopics', False)
        self.topic_per_req = self.settings.get('topicPerRequest', False)
        self.forward_all = self.settings.get('forwardAll', False)  # Режим без тикетов: пересылать всё
        
        # Кнопки и триггеры
        self.buttons = full_cfg.get('buttons', [])
        self.triggers = full_cfg.get('triggers', [])
        self.welcome_text = full_cfg.get('welcomeMessage', 'Здравствуйте!')
        
        self.rate_limit = float(self.settings.get('rateLimit', 1.0))
        self.auto_ban_limit = int(self.settings.get('autoBanThreshold', 3))
        self.users_list = full_cfg.get('connectedUsers', [])
        self.license_expires_at = full_cfg.get('license_expires_at', 0)

        # ── Стафф-система (администраторы поддержки) ──
        staff_cfg = full_cfg.get('staffSettings', {}) or {}
        self.staff_enabled        = staff_cfg.get('enabled', False)
        self.staff_notify         = staff_cfg.get('notifyOnAssign', True)
        self.staff_show_list      = staff_cfg.get('showStaffList', False)
        self.staff_list_btn_name  = staff_cfg.get('staffListButtonName', 'Список администрации')
        self.staff_allow_switch   = staff_cfg.get('allowUserSwitch', True)
        self.staff_assign_mode    = staff_cfg.get('assignMode', 'random')
        # Список стафф-админов: [{id, tg_id, alias, name, active, stats}]
        self.staff_admins: list = full_cfg.get('staffAdmins', []) or []

        # ── ИИ-конфиг (ПОДПРАВЛЕННЫЙ) ──
        ai_cfg = full_cfg.get('ai', {}) or {}
        self.ai_enabled       = ai_cfg.get('enabled', False)
        self.ai_mode          = ai_cfg.get('mode', 'all')      # 'all' | 'button' | 'command' | 'off'
        self.ai_button_name   = ai_cfg.get('buttonName', 'ИИ-ассистент')
        self.ai_system_prompt = ai_cfg.get('systemPrompt', 'Ты полезный ИИ-ассистент.')
        self.ai_max_tokens    = int(ai_cfg.get('maxTokensPerReply', 800))
        self.ai_context_len   = int(ai_cfg.get('contextMessages', 6))
        
        # Модель: если в Timeweb настроен GPT-4o, лучше по умолчанию ставить её
        self.ai_model         = ai_cfg.get('model', 'gpt-4o')

        # Ключ: Берем ТОЛЬКО из .env (игнорируем то, что ввел юзер в панели)
        # [2025-12-23] Remember to take the token from the .env file.
        self.qwen_api_key     = os.getenv('TIMEWEB_API_KEY') or os.getenv('QWEN_API_KEY')

        # URL Агента: Формируем динамически на основе твоего ID агента
        # Если в .env нет ID, используем твой текущий как запасной
        agent_id = os.getenv('TIMEWEB_AGENT_ID', '14ce55f9-dce2-4f2d-ad98-ff2cffe19ca2')
        self.ai_url = f"https://agent.timeweb.cloud/api/v1/cloud-ai/agents/{agent_id}/v1/chat/completions"

        # Контекст диалогов: {user_id: [{"role":..,"content":..}]}
        if not hasattr(self, 'ai_context_cache'):
            self.ai_context_cache: Dict[int, List[dict]] = {}

        # ── Стартовое медиа и инлайн-кнопки ──
        self.welcome_photo    = full_cfg.get('welcomePhoto', '')   # file_id или URL
        self.welcome_inline   = full_cfg.get('welcomeInline', [])  # [{text, url}]

        # ── If/else логика кнопок ──
        # buttons теперь могут содержать children: [{text, response, type, children:[...]}]
        # и triggerFlow: {...}
        
        # ── Обязательная подписка ──
        # Список: [{id: "@channel", title: "Название", url: "https://..."}]
        sub_enabled = full_cfg.get('requiredSubEnabled', False)
        self.required_channels = full_cfg.get('requiredChannels', []) if sub_enabled else []

        # ── MemoryBase антиспам ──
        stg = self.settings
        self.mb_enabled       = stg.get('memoryBaseEnabled', False)
        self.mb_block_reasons = stg.get('memoryBaseBlockReasons', [])
        # Список строк: ["scammer","bad_admin","bad_owner","bad_behavior","spammer","raider"]

        # ── DVR мониторинг ──
        self.dvr_enabled = stg.get('dvrEnabled', False)

        # Статистика
        incoming_stats = full_cfg.get('stats', {})
        self.stats_data = {
            "totalMessages": incoming_stats.get("totalMessages", 0),
            "incomingToday": incoming_stats.get("incomingToday", 0),
            "outgoingToday": incoming_stats.get("outgoingToday", 0),
            "bannedCount": incoming_stats.get("bannedCount", 0),
            "activeUsers24h": incoming_stats.get("activeUsers24h", 0),
            "history": incoming_stats.get("history", [])
        }

    # ─────────────────────────────────────────────
    # AI / QWEN INTEGRATION
    # ─────────────────────────────────────────────
    async def ai_call(self, user_id: int, user_text: str) -> Optional[str]:
        """Вызов Qwen API через прокси Timeweb с контекстом диалога."""
        # Проверяем наличие ключа и URL
        if not self.qwen_api_key or not self.ai_url:
            logger.error("AI Error: Ключ или URL не настроены в .env")
            return None

        # Добавляем сообщение в контекст
        ctx = self.ai_context_cache.setdefault(user_id, [])
        ctx.append({"role": "user", "content": user_text})
        
        # Обрезаем контекст
        if len(ctx) > self.ai_context_len * 2:
            ctx = ctx[-(self.ai_context_len * 2):]
            self.ai_context_cache[user_id] = ctx

        messages = [{"role": "system", "content": self.ai_system_prompt}] + ctx

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # ИСПОЛЬЗУЕМ self.ai_url вместо жесткой ссылки на aliyuncs
                resp = await client.post(
                    self.ai_url, 
                    headers={
                        "Authorization": f"Bearer {self.qwen_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.ai_model,
                        "messages": messages,
                        "max_tokens": self.ai_max_tokens,
                        "temperature": 0.7
                    }
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    answer = data["choices"][0]["message"]["content"]
                    usage = data.get("usage", {})
                    total = usage.get("total_tokens", 0)
                    
                    ctx.append({"role": "assistant", "content": answer})
                    asyncio.create_task(self._deduct_tokens(user_id, usage, total))
                    return answer
                else:
                    # Теперь ошибка в логах покажет реальный статус (например, если токен пустой)
                    logger.error(f"AI API error {resp.status_code}: {resp.text}")
                    return None
        except Exception as e:
            logger.error(f"AI call error: {e}")
            return None
            
    async def _deduct_tokens(self, user_id: int, usage: dict, total: int):
        """Списывает токены с баланса бота в БД."""
        try:
            await self.db.rpc("deduct_ai_tokens", {"p_bot_id": self.bot_id, "p_amount": total})
            await self.db.post("ai_token_usage_log", {
                "bot_id":          self.bot_id,
                "user_id":         user_id,
                "prompt_tokens":   usage.get("prompt_tokens", 0),
                "response_tokens": usage.get("completion_tokens", 0),
                "total_tokens":    total,
                "model":           self.ai_model,
            })
        except Exception as e:
            logger.warning(f"Token deduct error: {e}")

    async def check_ai_tokens(self) -> int:
        """Возвращает остаток токенов бота. 0 если нет баланса."""
        try:
            rows = await self.db.get("ai_token_balances", {"bot_id": f"eq.{self.bot_id}"})
            if rows:
                return rows[0].get("tokens_balance", 0)
        except Exception:
            pass
        return 0

    def clear_ai_context(self, user_id: int):
        """Сбросить контекст диалога с ИИ для пользователя."""
        self.ai_context_cache.pop(user_id, None)

    # ─────────────────────────────────────────────
    # IF/ELSE BUTTON FLOW HELPERS
    # ─────────────────────────────────────────────
    def get_button_by_text(self, text: str, buttons=None) -> Optional[dict]:
        """Рекурсивно ищет кнопку по тексту (включая дочерние)."""
        if buttons is None:
            buttons = self.buttons
        for b in buttons:
            if b.get('text', '').lower() == text.lower():
                return b
            # Рекурсивный поиск в children
            children = b.get('children', [])
            if children:
                found = self.get_button_by_text(text, children)
                if found:
                    return found
        return None

    def build_keyboard_from_buttons(self, buttons: list):
        """Строит ReplyKeyboardMarkup из списка кнопок."""
        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
        active = [b for b in buttons if b.get('text')]
        if not active:
            return ReplyKeyboardRemove()
        rows = []
        for i in range(0, len(active), 2):
            rows.append([KeyboardButton(text=b['text']) for b in active[i:i+2]])
        return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

    def build_inline_from_list(self, buttons: list) -> Optional[InlineKeyboardMarkup]:
        """Строит InlineKeyboardMarkup из [{text, url}]."""
        if not buttons:
            return None
        rows = []
        for i in range(0, len(buttons), 2):
            rows.append([
                InlineKeyboardButton(text=b['text'], url=b.get('url', 'https://t.me'))
                for b in buttons[i:i+2] if b.get('text')
            ])
        return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None

    # ─────────────────────────────────────────────
    # FLOW-ЛОГИКА РАСШИРЕННЫХ КНОПОК
    # ─────────────────────────────────────────────

    def _format_flow_text(self, text: str, m: Message) -> str:
        """Подставляет переменные в текст flow-действия."""
        return (text or '').\
            replace('{username}', f'@{m.from_user.username}' if m.from_user.username else m.from_user.full_name).\
            replace('{first_name}', m.from_user.first_name or '').\
            replace('{last_name}', m.from_user.last_name or '').\
            replace('{user_id}', str(m.from_user.id)).\
            replace('{text}', m.text or '')

    async def execute_flow_actions(self, actions: list, m: Message, user: dict) -> bool:
        """
        Выполняет список action-объектов для одной flow-ноды.
        Возвращает True если была отправлена клавиатура с под-кнопками
        (чтобы не показывать основное меню после).
        """
        uid = m.from_user.id
        showed_sub_keyboard = False

        for action in actions:
            atype = action.get('type', 'message')

            if atype == 'message':
                text = self._format_flow_text(action.get('text', ''), m)
                if text:
                    await m.answer(text, parse_mode='HTML')

            elif atype == 'admin_notify':
                text = self._format_flow_text(action.get('text', ''), m)
                if text and self.admin_chat_id:
                    try:
                        thread_id = user.get('last_topic_id') if self.use_topics else None
                        await self.bot.send_message(
                            self.admin_chat_id,
                            text,
                            message_thread_id=thread_id,
                            parse_mode='HTML'
                        )
                    except Exception as e:
                        logger.warning(f"Flow admin_notify error: {e}")

            elif atype == 'code':
                code = action.get('code', '').strip()
                if code:
                    await self._execute_flow_code(code, m, user)
                # Если после кода пользователь оказался в тикете — сохраняем флаг
                if user.get('_in_ticket'):
                    showed_sub_keyboard = True

            elif atype == 'create_ticket':
                await self._flow_create_ticket(action, m, user)
                # После открытия тикета прерываем цепочку действий —
                # клавиатура закрытия уже показана, дальнейшие action её перебьют
                showed_sub_keyboard = True
                break

            elif atype == 'buttons':
                sub_nodes = action.get('buttons', [])
                if sub_nodes:
                    # Показываем клавиатуру из под-узлов
                    raw_buttons = [{'text': node.get('label', '')} for node in sub_nodes if node.get('label')]
                    raw_buttons.append({'text': 'Назад'})
                    kb = self.build_keyboard_from_buttons(raw_buttons)
                    # Сохраняем sub_nodes в сессии пользователя для обработки нажатия
                    user['_flow_nodes'] = sub_nodes
                    await m.answer('Выберите:', reply_markup=kb)
                    showed_sub_keyboard = True

        return showed_sub_keyboard

    async def _flow_create_ticket(self, action: dict, m: Message, user: dict):
        """Создаёт тикет из flow-действия (переводит пользователя в режим обращения).
        Поля action совпадают с BotEditor: ticketBtnLabel, ticketUserText, ticketAdminText.
        """
        btn_text  = action.get('ticketAdminText', '') or action.get('btnText', '')
        resp_text = action.get('ticketUserText', '') or action.get('response', 'Ваше обращение принято. Ожидайте ответа оператора.')
        label     = action.get('ticketBtnLabel', '') or 'Закрыть обращение'

        user['_in_ticket'] = True
        user['_ticket_close_label'] = label

        # Пересылаем сообщение в чат администраторов
        await self.forward_to_admin(m, user, btn_text=btn_text)

        # Показываем пользователю кнопку закрытия тикета
        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
        close_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=label)]],
            resize_keyboard=True
        )
        await m.answer(
            f"{resp_text}\n\nВы можете продолжать писать — сообщения будут доставлены оператору.",
            reply_markup=close_kb
        )
        await self.sync_queue.put(("sync_state", None))

    async def _execute_flow_code(self, code: str, m: Message, user: dict):
        """
        Выполняет код через дочерний процесс (asyncio subprocess).

        Уровни защиты:
          1. AST-scan: статические лимиты (длина, числа, степени, range, повторы строк)
             + security-scan (дандеры, import, eval, open и т.д.)
          2. Subprocess: код запускается в отдельном python-процессе с OS-лимитами
             RLIMIT_CPU=4с и RLIMIT_AS=96МБ. Передача данных через stdin/stdout JSON.
          3. asyncio.wait_for: wall-clock timeout 6 секунд — процесс убивается если завис.
        """
        import asyncio, ast as _ast, json as _json, sys as _sys, os as _os, traceback

        _MAX_CODE_LEN   = 4_000
        _MAX_CODE_LINES = 100
        _MAX_INT_LIT    = 1_000_000
        _MAX_POW_EXP    = 1_000
        _MAX_STR_REPEAT = 100_000
        _MAX_RANGE      = 100_000
        _MAX_REPLY_LEN  = 4_000
        _WALL_TIMEOUT   = 6.0

        _BLOCKED_ATTRS = {
            "__class__","__base__","__bases__","__mro__","__subclasses__",
            "__globals__","__builtins__","__dict__","__code__","__func__",
            "__self__","__module__","__qualname__","__init__","__new__",
            "__reduce__","__reduce_ex__","__getattribute__","__setattr__",
            "__delattr__","__import__","__loader__","__spec__","__file__",
            "__cached__","__wrapped__","_module","__weakref__",
            "__build_class__","__closure__","__annotations__",
        }
        _BLOCKED_NAMES = {"__import__","__builtins__","__spec__","__loader__","__build_class__","breakpoint"}
        _BLOCKED_CALLS = {
            "eval","exec","compile","open","input","breakpoint",
            "vars","dir","locals","globals","memoryview",
            "type","object","super","classmethod","staticmethod","property",
        }
        _BLOCKED_STR_PATTERNS = {
            "__class__","__base__","__bases__","__mro__","__subclasses__",
            "__globals__","__builtins__","__dict__","__code__","__import__",
            "__reduce__","__init__","__new__","_module","__closure__",
            "__getattribute__",".env","/etc/passwd","/etc/shadow",
            "/proc/","/sys/","subprocess","pty","ctypes","cffi",
        }

        # ── 1. AST-проверка ───────────────────────────────────────────────────
        if len(code) > _MAX_CODE_LEN:
            await m.answer(f"Код отклонён: слишком длинный (максимум {_MAX_CODE_LEN} символов)")
            return
        if code.count("\n") + 1 > _MAX_CODE_LINES:
            await m.answer(f"Код отклонён: слишком много строк (максимум {_MAX_CODE_LINES})")
            return

        def _ast_check(source: str):
            try:
                tree = _ast.parse(source, mode="exec")
            except SyntaxError as e:
                return False, f"Синтаксическая ошибка: {e}"
            for node in _ast.walk(tree):
                if isinstance(node, _ast.Constant):
                    if isinstance(node.value, int) and abs(node.value) > _MAX_INT_LIT:
                        return False, f"Число слишком большое (максимум {_MAX_INT_LIT:,})"
                    if isinstance(node.value, str):
                        for pat in _BLOCKED_STR_PATTERNS:
                            if pat in node.value:
                                return False, f"Запрещённый паттерн в строке: '{pat}'"
                if isinstance(node, _ast.BinOp) and isinstance(node.op, _ast.Pow):
                    r = node.right
                    if isinstance(r, _ast.Constant) and isinstance(r.value, (int, float)):
                        if r.value > _MAX_POW_EXP:
                            return False, f"Степень слишком большая (максимум {_MAX_POW_EXP})"
                if isinstance(node, _ast.BinOp) and isinstance(node.op, _ast.Mult):
                    for a, b in [(node.left, node.right), (node.right, node.left)]:
                        if (isinstance(a, _ast.Constant) and isinstance(a.value, (str, bytes)) and
                                isinstance(b, _ast.Constant) and isinstance(b.value, int)):
                            if b.value > _MAX_STR_REPEAT:
                                return False, f"Повтор строки слишком большой (максимум {_MAX_STR_REPEAT:,})"
                if (isinstance(node, _ast.Call) and isinstance(node.func, _ast.Name)
                        and node.func.id == "range"):
                    for arg in node.args:
                        if isinstance(arg, _ast.Constant) and isinstance(arg.value, int):
                            if arg.value > _MAX_RANGE:
                                return False, f"range() слишком большой (максимум {_MAX_RANGE:,})"
                if isinstance(node, _ast.Attribute):
                    nm = node.attr
                    if nm in _BLOCKED_ATTRS or (nm.startswith("__") and nm.endswith("__")):
                        return False, f"Запрещён доступ к атрибуту '{nm}'"
                if isinstance(node, _ast.Name) and node.id in _BLOCKED_NAMES:
                    return False, f"Запрещено имя '{node.id}'"
                if isinstance(node, _ast.Call):
                    func = node.func
                    if isinstance(func, _ast.Name) and func.id in _BLOCKED_CALLS:
                        return False, f"Запрещён вызов '{func.id}()'"
                    if isinstance(func, _ast.Attribute) and func.attr in _BLOCKED_CALLS:
                        return False, f"Запрещён вызов метода '{func.attr}()'"
                if isinstance(node, (_ast.Import, _ast.ImportFrom)):
                    return False, "Оператор import запрещён — модули предоставлены автоматически"
            return True, None

        ok, ast_err = _ast_check(code)
        if not ok:
            logger.warning(f"Flow AST blocked (bot {self.bot_id}): {ast_err}")
            await m.answer(f"Код отклонён: {ast_err}")
            return

        # ── 2. Запуск в дочернем процессе ────────────────────────────────────
        ctx = {
            "user_id":    m.from_user.id,
            "username":   m.from_user.username or "",
            "first_name": m.from_user.first_name or "",
            "text":       m.text or "",
            "bot_id":     self.bot_id,
        }
        payload = _json.dumps({"code": code, "ctx": ctx}).encode()

        try:
            proc = await asyncio.create_subprocess_exec(
                _sys.executable, "-c", _SANDBOX_RUNNER_PY,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                # Полностью пустое окружение — никакие env-переменные родителя
                # (токены, ключи БД, .env) не видны дочернему процессу.
                # Минимальный PATH нужен только чтобы Python нашёл себя.
                env={k: v for k, v in _os.environ.items() if k in (
                    "PATH", "LD_LIBRARY_PATH", "LD_PRELOAD",
                    "PYTHONPATH", "PYTHONHOME",
                    "LANG", "LC_ALL", "LC_CTYPE",
                    "HOME", "TMPDIR", "TMP", "TEMP",
                    "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED",
                    "VIRTUAL_ENV",  # needed if requests is in a venv
                )},
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(payload),
                timeout=_WALL_TIMEOUT,
            )

            # Процесс убит OS-лимитом или завершился с ошибкой без вывода
            if proc.returncode != 0 and not stdout.strip():
                rc = proc.returncode
                if rc in (-9, -15):   # SIGKILL / SIGTERM
                    await m.answer("Код остановлен: превышен лимит CPU или памяти.")
                else:
                    err_txt = stderr.decode(errors="replace")[:200]
                    await m.answer(f"Процесс завершился с ошибкой (код {rc}).")
                    logger.warning(f"Flow sandbox exit {rc} for bot {self.bot_id}: {err_txt}")
                return

            if not stdout.strip():
                return  # Код выполнился, но reply_text не задан — ничего не отвечаем

            result = _json.loads(stdout.decode().strip())
            if result.get("ok"):
                reply = result.get("reply", "").strip()
                if reply:
                    if len(reply) > _MAX_REPLY_LEN:
                        reply = reply[:_MAX_REPLY_LEN] + "…"
                    # Если пользователь в тикете — сохраняем кнопку закрытия
                    if user.get('_in_ticket'):
                        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
                        _close_label = user.get('_ticket_close_label', 'Закрыть обращение')
                        _close_kb = ReplyKeyboardMarkup(
                            keyboard=[[KeyboardButton(text=_close_label)]],
                            resize_keyboard=True
                        )
                        await m.answer(reply, parse_mode="HTML", reply_markup=_close_kb)
                    else:
                        await m.answer(reply, parse_mode="HTML")
            else:
                err = result.get("error", "Неизвестная ошибка")
                logger.warning(f"Flow code error (bot {self.bot_id}): {err}")
                await m.answer(f"Ошибка выполнения: {err}")

        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            logger.warning(f"Flow code wall-clock timeout for bot {self.bot_id}")
            await m.answer("Код завершён по таймауту (более 6 секунд).")
        except Exception as e:
            logger.warning(f"Flow code unexpected error (bot {self.bot_id}): {e}\n{traceback.format_exc()}")

    def find_flow_node_by_label(self, label: str, nodes: list) -> Optional[dict]:
        """Рекурсивный поиск flow-ноды по тексту кнопки."""
        for node in nodes:
            if node.get('label', '').strip().lower() == label.strip().lower():
                return node
            # Искать во вложенных buttons-действиях
            for action in node.get('actions', []):
                if action.get('type') == 'buttons':
                    found = self.find_flow_node_by_label(label, action.get('buttons', []))
                    if found:
                        return found
        return None

    async def handle_flow_button(self, m: Message, user: dict) -> bool:
        """
        Пытается обработать нажатую кнопку как flow-узел.
        Возвращает True если кнопка была найдена и обработана в flow.
        """
        text = m.text.strip() if m.text else ''

        # Сначала ищем в сохранённых под-нодах (если пользователь в под-меню)
        session_nodes = user.get('_flow_nodes')
        if session_nodes:
            node = self.find_flow_node_by_label(text, session_nodes)
            if node:
                showed_kb = await self.execute_flow_actions(node.get('actions', []), m, user)
                if not showed_kb:
                    user.pop('_flow_nodes', None)
                    await m.answer('Готово.', reply_markup=self.get_main_keyboard())
                return True

        # Ищем в основных кнопках
        for btn in self.buttons:
            if btn.get('text', '').strip().lower() != text.lower():
                continue

            handled = False

            # directActions — выполняем сразу при нажатии кнопки
            direct_actions = btn.get('directActions', [])
            if direct_actions:
                await self.execute_flow_actions(direct_actions, m, user)
                handled = True

            # flow — показываем под-кнопки (ветки)
            flow = btn.get('flow', [])
            if flow:
                raw_buttons = [{'text': node.get('label', '')} for node in flow if node.get('label')]
                raw_buttons.append({'text': 'Назад'})
                kb = self.build_keyboard_from_buttons(raw_buttons)
                user['_flow_nodes'] = flow
                resp = btn.get('response', '')
                await m.answer(resp or 'Выберите:', reply_markup=kb)
                handled = True

            if handled:
                return True

            # Кнопка найдена, но flow нет — пусть обрабатывает стандартная логика
            return False

        return False

    async def dvr_notify_worker(self):
        """Поллим dvr_events из Supabase и отправляем уведомления владельцу бота."""
        if not self.admin_chat_id:
            return
        while True:
            try:
                events = await self.db.get("dvr_events", {
                    "bot_id": f"eq.{self.bot_id}", "status": "eq.pending"
                })
                for ev in events:
                    try:
                        bot_username = ev.get("bot_username", "")
                        await self.bot.send_message(
                            self.admin_chat_id,
                            f"🚨 <b>Система безопасности Dialoge Engine</b>\n\n"
                            f"Обнаружена рейдерская атака на вашего бота"
                            f"{f' <b>@{bot_username}</b>' if bot_username else ''}.\n\n"
                            f"✅ Бот был автоматически <b>остановлен</b> для защиты.\n\n"
                            f"Восстановите работу на: "
                            f"<a href=\"https://dialogengine.webtm.ru\">dialogengine.webtm.ru</a>"
                        )
                        await self.db.patch("dvr_events", {"id": f"eq.{ev['id']}"}, {"status": "done"})
                        logger.info(f"[DVR] ✅ Notify sent to {self.admin_chat_id}")
                    except Exception as e:
                        logger.warning(f"[DVR] notify error: {e}")
            except Exception as e:
                logger.warning(f"[DVR] worker error: {e}")
            await asyncio.sleep(30)  # DVR-события редкие, 5с — расточительство ресурсов

    async def database_sync_worker(self):
        # Дебаунс: не чаще раза в 15 сек для sync_state.
        # log_message — всегда немедленно (важно для лога).
        SYNC_DEBOUNCE = 15.0
        _last_sync: float = 0.0
        _pending_sync: bool = False

        async def _do_sync_state():
                nonlocal _last_sync, _pending_sync
                try:
                    rows = await self.db.get("bots", {"id": f"eq.{self.bot_id}"})
                    if rows:
                        remote_data   = rows[0]
                        remote_config = remote_data.get("config", {})
                        new_config = {
                            **remote_config,
                            "stats":          self.stats_data,
                            "connectedUsers": self.users_list,
                            "admin_chat_id":  self.admin_chat_id,
                            "adminChatId":    self.admin_chat_id,
                        }
                        await self.db.patch(
                            "bots", {"id": f"eq.{self.bot_id}"}, {"config": new_config}
                        )
                        saved_users = self.users_list
                        saved_stats = self.stats_data
                        self.apply_config({"config": remote_config})
                        self.users_list = saved_users
                        self.stats_data = saved_stats
                except Exception as e:
                    logger.error(f"Sync Worker _do_sync_state error: {e}")
                finally:
                    _last_sync    = time.time()
                    _pending_sync = False

        while self.is_running:
            try:
                item = await asyncio.wait_for(self.sync_queue.get(), timeout=1.0)
                action, payload = item

                if action == "log_message":
                    # Лог — всегда немедленно
                    await self.db.post("bot_messages", payload)

                elif action == "sync_state":
                    now = time.time()
                    if now - _last_sync >= SYNC_DEBOUNCE:
                        await _do_sync_state()
                    else:
                        _pending_sync = True

                self.sync_queue.task_done()

            except asyncio.TimeoutError:
                if _pending_sync and (time.time() - _last_sync >= SYNC_DEBOUNCE):
                    await _do_sync_state()
                continue
            except Exception as e:
                logger.error(f"Sync Worker Error: {e}")
                try: self.sync_queue.task_done()
                except: pass

    async def sync_database_logic(self):
        """Одноразовая синхронизация при старте: загружает актуальный конфиг из БД."""
        try:
            rows = await self.db.get("bots", {"id": f"eq.{self.bot_id}"})
            if rows:
                remote_data   = rows[0]
                remote_config = remote_data.get("config") or {}
                if not isinstance(remote_config, dict):
                    try:
                        remote_config = json.loads(remote_config)
                    except Exception:
                        remote_config = {}
                self.apply_config({**remote_data, "config": remote_config})
                logger.info(f"✅ [{self.bot_id}] Конфиг загружен из БД (кнопок: {len(self.buttons)}, триггеров: {len(self.triggers)})")
        except Exception as e:
            logger.error(f"sync_database_logic error: {e}")

    async def daily_stats_rotator(self):
        """
        Ротация статистики с корректным сохранением данных при смене дня.
        """
        while self.is_running:
            try:
                now = datetime.now()
                current_date = now.strftime("%d.%m")
                
                # Подсчет активных пользователей
                day_ago = int((now - timedelta(days=1)).timestamp())
                active_count = sum(1 for u in self.users_list if u.get('last_seen', 0) > day_ago)
                self.stats_data["activeUsers24h"] = active_count

                history = self.stats_data.get("history", [])
                if not history:
                    history = [{
                        "date": current_date, "incoming": 0, "outgoing": 0,
                        "totalUsers": len(self.users_list), "activeUsers": active_count
                    }]
                    self.stats_data["history"] = history

                # ПРОВЕРКА СМЕНЫ ДНЯ
                if history[-1]["date"] != current_date:
                    # 1. ФИКСИРУЕМ финальные данные в последнюю точку ВЧЕРАШНЕГО дня
                    # Это гарантирует, что в Supabase улетят полные цифры за вчера
                    history[-1]["incoming"] = self.stats_data.get("incomingToday", 0)
                    history[-1]["outgoing"] = self.stats_data.get("outgoingToday", 0)
                    history[-1]["totalUsers"] = len(self.users_list)
                    history[-1]["activeUsers"] = active_count
                    
                    # 2. Только после сохранения обнуляем суточные счетчики
                    self.stats_data["incomingToday"] = 0
                    self.stats_data["outgoingToday"] = 0
                    
                    # 3. Создаем НОВУЮ точку для сегодняшнего дня (с нулями)
                    new_point = {
                        "date": current_date,
                        "incoming": 0,
                        "outgoing": 0,
                        "totalUsers": len(self.users_list),
                        "activeUsers": active_count
                    }
                    history.append(new_point)
                    
                    # Оставляем 14 дней
                    self.stats_data["history"] = history[-14:]
                    # Важно обновить локальную ссылку после среза
                    history = self.stats_data["history"]
                
                # 4. ОБНОВЛЕНИЕ ТЕКУЩЕГО ДНЯ (Real-time)
                # Это работает всегда, обновляя самую последнюю запись в истории
                last_point = history[-1]
                last_point["incoming"] = self.stats_data.get("incomingToday", 0)
                last_point["outgoing"] = self.stats_data.get("outgoingToday", 0)
                last_point["totalUsers"] = len(self.users_list)
                last_point["activeUsers"] = active_count

                # Отправляем на синхронизацию в Supabase
                await self.sync_queue.put(("sync_state", None))
                
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Rotator Error: {e}")
                await asyncio.sleep(60)
                

    async def check_antispam(self, user_id: int) -> bool:
        if self.rate_limit <= 0: return False
        now = time.time()
        last_time = self.flood_cache.get(user_id, 0)
        if now - last_time < self.rate_limit: return True
        self.flood_cache[user_id] = now
        return False

    async def log_and_update(self, uid: int, name: str, text: str, is_admin: bool = False):
        """Логирование и обновление статистики для графиков"""
        # Лог сообщения
        await self.sync_queue.put(("log_message", {
            "bot_id": self.bot_id, 
            "user_id": uid, 
            "first_name": name,
            "message_text": text[:950] if text else "[Медиа]", 
            "is_from_admin": is_admin
        }))
        
        # Обновление счетчиков
        self.stats_data["totalMessages"] = self.stats_data.get("totalMessages", 0) + 1
        stat_key = "outgoingToday" if is_admin else "incomingToday"
        self.stats_data[stat_key] = self.stats_data.get(stat_key, 0) + 1
        
        # Обновление пользователя
        if not is_admin:
            for u in self.users_list:
                if u['id'] == uid:
                    u['last_seen'] = int(time.time())
                    u['name'] = name # Обновляем имя, если изменилось
                    break
        
        # Сразу пушим обновление для графиков
        await self.sync_queue.put(("sync_state", None))

    async def get_user_state(self, m: Message):
        uid = m.from_user.id
        user = next((u for u in self.users_list if u['id'] == uid), None)
        is_first_time = False
        
        if not user:
            is_first_time = True
            user = {
                "id": uid, 
                "first_name": m.from_user.first_name, 
                "username": m.from_user.username, 
                "is_banned": False, 
                "is_active": True, 
                "warns": 0, 
                "joined_at": int(time.time()),
                "last_seen": int(time.time()),
                "last_topic_id": None
            }
            self.users_list.append(user)
            await self.sync_queue.put(("sync_state", None))
        else:
            user["last_seen"] = int(time.time())
            if not user.get("is_active", True):
                user["is_active"] = True
                await self.sync_queue.put(("sync_state", None))
            
        return user, is_first_time

    async def resolve_thread(self, user: dict, force_new: bool = False):
        if not self.use_topics or not self.admin_chat_id: 
            return None
        
        tid = user.get("last_topic_id")
        
        # Если топик есть и мы не заставляем создавать новый — возвращаем старый
        if tid and not force_new:
            return tid

        # Создаем новый топик
        try:
            priority = user.get("priority", "normal")
            topic_name = build_topic_name(user, self.settings, priority)
            
            # Сама команда создания в Telegram
            new_topic = await self.bot.create_forum_topic(self.admin_chat_id, topic_name)
            
            # Сохраняем и синхронизируем с БД (важно для Supabase)
            user["last_topic_id"] = new_topic.message_thread_id
            await self.sync_queue.put(("sync_state", None))
            
            logger.info(f"Successfully created new topic {new_topic.message_thread_id} for user {user['id']}")
            return new_topic.message_thread_id
        except Exception as e:
            logger.error(f"Critical Topic Creation Error: {e}")
            return None
            
    async def forward_to_admin(self, m: Message, user: dict, is_first: bool = False, btn_text: str = "", is_ai_request: bool = False):
        if not self.admin_chat_id: return

        # ── Стафф-система: назначаем администратора при первом сообщении/тикете ──
        if self.staff_enabled and is_first and not user.get('assigned_staff_id'):
            staff = self._assign_staff()
            if staff:
                await self._assign_staff_to_user(user, staff, m)
                # Добавляем кнопки "Сменить админа" / "Список администрации" к клавиатуре пользователя
                kb = await self._staff_keyboard_for_user(user)
                if kb:
                    try:
                        await self.bot.send_message(user['id'], "ℹ️ Выберите действие:", reply_markup=kb, parse_mode="HTML")
                    except Exception:
                        pass

        # Добавляем имя назначенного стафф-admin в заголовок для панели
        if self.staff_enabled and user.get('assigned_staff_alias'):
            staff_note = f"\n🧑‍💼 Администратор: <b>{user['assigned_staff_alias']}</b>"
        else:
            staff_note = ""
        
        force_new_topic = self.topic_per_req and (btn_text != "" or is_first)
        thread_id = await self.resolve_thread(user, force_new=force_new_topic)
        header_text = format_admin_header(m, self.settings, is_first, btn_text) + staff_note

        if is_ai_request:
            header_text = header_text.rstrip('\n') + "\n<b>[ИИ-запрос · не отвечать]</b>\n"
        
        try:
            # Если по какой-то причине thread_id пустой, а топики включены - пробуем создать
            if not thread_id and self.use_topics:
                thread_id = await self.resolve_thread(user, force_new=True)

            await self._send_content_to_admin(m, thread_id, header_text, user)

            # Статистика: считаем входящее сообщение для стаффера
            if self.staff_enabled and user.get('assigned_staff_id'):
                asyncio.create_task(self._post_staff_stat(user['assigned_staff_id'], 'message'))
            
        except TelegramBadRequest as e:
            if "message thread not found" in e.message:
                logger.warning(f"Thread {thread_id} was deleted. Re-creating...")
                # СБРОС: удаляем битый ID из памяти пользователя
                user["last_topic_id"] = None
                # Создаем новый топик ПРИНУДИТЕЛЬНО
                new_tid = await self.resolve_thread(user, force_new=True)
                
                if new_tid:
                    await self._send_content_to_admin(m, new_tid, header_text, user)
                else:
                    logger.error("Could not recreate topic, message might go to General or fail.")
            else:
                logger.error(f"Forwarding Error: {e}")

    # НЕ ЗАБУДЬТЕ ДОБАВИТЬ ЭТОТ МЕТОД, иначе forward_to_admin выдаст ошибку отсутствия атрибута
    async def _send_content_to_admin(self, m: Message, thread_id: int, header_text: str, user: dict):
        sent_msg = None
        try:
            # Проверяем наличие премиум-эмодзи в тексте или подписи
            has_premium_emoji = False
            entities = m.entities or m.caption_entities
            if entities:
                for entity in entities:
                    if entity.type == "custom_emoji":
                        has_premium_emoji = True
                        break

            # Если это стикер ИЛИ сообщение с премиум-эмодзи
            if m.sticker or has_premium_emoji:
                # 1. Сначала отправляем заголовок с данными пользователя
                if header_text:
                    await self.bot.send_message(self.admin_chat_id, header_text, message_thread_id=thread_id)
                
                # 2. Затем ПЕРЕСЫЛАЕМ оригинал сообщения (forward)
                sent_msg = await self.bot.forward_message(
                    chat_id=self.admin_chat_id,
                    from_chat_id=m.chat.id,
                    message_id=m.message_id,
                    message_thread_id=thread_id
                )
            
            # Стандартная логика для остальных типов контента
            elif m.text:
                sent_msg = await self.bot.send_message(self.admin_chat_id, f"{header_text}{m.text}", message_thread_id=thread_id)
            elif m.photo:
                sent_msg = await self.bot.send_photo(self.admin_chat_id, m.photo[-1].file_id, caption=f"{header_text}{m.caption or ''}", message_thread_id=thread_id)
            elif m.video:
                sent_msg = await self.bot.send_video(self.admin_chat_id, m.video.file_id, caption=f"{header_text}{m.caption or ''}", message_thread_id=thread_id)
            elif m.voice:
                sent_msg = await self.bot.send_voice(self.admin_chat_id, m.voice.file_id, caption=f"{header_text}{m.caption or ''}", message_thread_id=thread_id)
            else:
                if header_text:
                    await self.bot.send_message(self.admin_chat_id, header_text, message_thread_id=thread_id)
                sent_msg = await self.bot.copy_message(self.admin_chat_id, m.chat.id, m.message_id, message_thread_id=thread_id)
            
            if sent_msg:
                self.msg_map[sent_msg.message_id] = user['id']
                self.user_to_admin_map[(user['id'], m.message_id)] = sent_msg.message_id
        except Exception as e:
            logger.error(f"Error inside _send_content_to_admin: {e}")
            raise e

    async def _send_media_group_to_admin(self, messages: list, user: dict, is_first: bool = False, btn_text: str = ""):
        """Отправляет список медиа-сообщений (media group) администратору как альбом."""
        if not self.admin_chat_id or not messages:
            return
        first_m = messages[0]
        force_new_topic = self.topic_per_req and (btn_text != "" or is_first)
        thread_id = await self.resolve_thread(user, force_new=force_new_topic)
        if not thread_id and self.use_topics:
            thread_id = await self.resolve_thread(user, force_new=True)
        header_text = format_admin_header(first_m, self.settings, is_first, btn_text)

        from aiogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument, InputMediaAudio
        media_items = []
        for i, msg in enumerate(messages):
            cap = (header_text if i == 0 else "") + (msg.caption or "")
            if msg.photo:
                media_items.append(InputMediaPhoto(media=msg.photo[-1].file_id, caption=cap or None, parse_mode="HTML"))
            elif msg.video:
                media_items.append(InputMediaVideo(media=msg.video.file_id, caption=cap or None, parse_mode="HTML"))
            elif msg.document:
                media_items.append(InputMediaDocument(media=msg.document.file_id, caption=cap or None, parse_mode="HTML"))
            elif msg.audio:
                media_items.append(InputMediaAudio(media=msg.audio.file_id, caption=cap or None, parse_mode="HTML"))

        if not media_items:
            return
        try:
            sent_msgs = await self.bot.send_media_group(
                chat_id=self.admin_chat_id,
                media=media_items,
                message_thread_id=thread_id
            )
            if sent_msgs:
                self.msg_map[sent_msgs[0].message_id] = user['id']
        except TelegramBadRequest as e:
            if "message thread not found" in e.message:
                user["last_topic_id"] = None
                new_tid = await self.resolve_thread(user, force_new=True)
                if new_tid:
                    try:
                        sent_msgs = await self.bot.send_media_group(
                            chat_id=self.admin_chat_id,
                            media=media_items,
                            message_thread_id=new_tid
                        )
                        if sent_msgs:
                            self.msg_map[sent_msgs[0].message_id] = user['id']
                    except Exception as e2:
                        logger.error(f"MediaGroup retry error: {e2}")
            else:
                logger.error(f"MediaGroup send error: {e}")
        except Exception as e:
            logger.error(f"Error in _send_media_group_to_admin: {e}")

    async def _flush_media_group(self, group_id: str, user: dict, is_first: bool = False, btn_text: str = ""):
        """Отправляет накопленную media group администратору как альбом."""
        await asyncio.sleep(0.8)  # Ждём, пока все части группы придут

        buf = self.media_group_buffer.pop(group_id, None)
        if not buf:
            return

        messages = buf["messages"]
        if not messages:
            return

        first_m = messages[0]
        if not self.admin_chat_id:
            return

        force_new_topic = self.topic_per_req and (btn_text != "" or is_first)
        thread_id = await self.resolve_thread(user, force_new=force_new_topic)
        header_text = format_admin_header(first_m, self.settings, is_first, btn_text)

        try:
            if not thread_id and self.use_topics:
                thread_id = await self.resolve_thread(user, force_new=True)

            from aiogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument, InputMediaAudio

            media_items = []
            for i, msg in enumerate(messages):
                cap = (header_text if i == 0 else "") + (msg.caption or "")
                if msg.photo:
                    media_items.append(InputMediaPhoto(media=msg.photo[-1].file_id, caption=cap or None, parse_mode="HTML"))
                elif msg.video:
                    media_items.append(InputMediaVideo(media=msg.video.file_id, caption=cap or None, parse_mode="HTML"))
                elif msg.document:
                    media_items.append(InputMediaDocument(media=msg.document.file_id, caption=cap or None, parse_mode="HTML"))
                elif msg.audio:
                    media_items.append(InputMediaAudio(media=msg.audio.file_id, caption=cap or None, parse_mode="HTML"))

            if media_items:
                sent_msgs = await self.bot.send_media_group(
                    chat_id=self.admin_chat_id,
                    media=media_items,
                    message_thread_id=thread_id
                )
                if sent_msgs:
                    self.msg_map[sent_msgs[0].message_id] = user['id']

        except TelegramBadRequest as e:
            if "message thread not found" in e.message:
                user["last_topic_id"] = None
                new_tid = await self.resolve_thread(user, force_new=True)
                if new_tid:
                    await self._flush_media_group_retry(messages, user, new_tid, header_text)
            else:
                logger.error(f"MediaGroup Forwarding Error: {e}")
        except Exception as e:
            logger.error(f"Error in _flush_media_group: {e}")

    async def _flush_media_group_retry(self, messages: list, user: dict, thread_id: int, header_text: str):
        """Повтор отправки media group при ошибке топика."""
        try:
            from aiogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument, InputMediaAudio
            media_items = []
            for i, msg in enumerate(messages):
                cap = (header_text if i == 0 else "") + (msg.caption or "")
                if msg.photo:
                    media_items.append(InputMediaPhoto(media=msg.photo[-1].file_id, caption=cap or None, parse_mode="HTML"))
                elif msg.video:
                    media_items.append(InputMediaVideo(media=msg.video.file_id, caption=cap or None, parse_mode="HTML"))
                elif msg.document:
                    media_items.append(InputMediaDocument(media=msg.document.file_id, caption=cap or None, parse_mode="HTML"))
                elif msg.audio:
                    media_items.append(InputMediaAudio(media=msg.audio.file_id, caption=cap or None, parse_mode="HTML"))
            if media_items:
                sent_msgs = await self.bot.send_media_group(
                    chat_id=self.admin_chat_id,
                    media=media_items,
                    message_thread_id=thread_id
                )
                if sent_msgs:
                    self.msg_map[sent_msgs[0].message_id] = user['id']
        except Exception as e:
            logger.error(f"Error in _flush_media_group_retry: {e}")

    async def admin_control_logic(self, m: Message):
        """
        ЕДИНАЯ ЛОГИКА АДМИН-КОМАНД (Статистика, Рассылка, Бан, Варн, Разбан)
        """
        # 1. Проверка на наличие текста и префикса команды (/ или !)
        if not m.text or not (m.text.startswith("/") or m.text.startswith("!")): 
            return False
        
        cmd_parts = m.text.split()
        command = cmd_parts[0][1:].lower()
        
        # Заголовки для Supabase (используются в модерации)
        headers = {
            "apikey": self.sb_key, 
            "Authorization": f"Bearer {self.sb_key}", 
            "Content-Type": "application/json"
        }

        # --- ГРУППА 1: ГЛОБАЛЬНЫЕ КОМАНДЫ (НЕ ТРЕБУЮТ ЮЗЕРА) ---
        
        # 📊 СТАТИСТИКА
        if command == "stats":
            total_users = len(self.users_list)
            banned = self.stats_data.get("bannedCount", 0)
            await m.reply(
                f"📊 <b>Статистика бота:</b>\n\n"
                f"👥 Всего пользователей: {total_users}\n"
                f"🚫 Заблокировано: {banned}"
            )
            return True

        # 📊 СТАТИСТИКА СТАФФ-АДМИНИСТРАТОРА
        elif command == "stat" and self.staff_enabled:
            # /stat — своя статистика (если отправитель — стафф-admin)
            # /stat <id|псевдоним> — статистика конкретного
            sender_id = m.from_user.id
            if len(cmd_parts) >= 2:
                target_staff = self._find_staff_by_arg(cmd_parts[1])
                if not target_staff:
                    await m.reply(f"❌ Администратор <code>{cmd_parts[1]}</code> не найден.")
                    return True
            else:
                # Ищем по Telegram ID отправителя
                target_staff = next((a for a in self.staff_admins if a.get('tg_id') == sender_id), None)
                if not target_staff:
                    await m.reply("❌ Ваш Telegram ID не найден среди администраторов.\nИспользуйте: /stat <code>ID</code> или /stat <code>псевдоним</code>")
                    return True
            await m.reply(await self._format_staff_stat(target_staff))
            return True

        # 📢 РАССЫЛКА
        elif command == "broadcast":
            if m.reply_to_message:
                target_msg_id = m.reply_to_message.message_id
                sent_count, err_count = 0, 0
                status_msg = await m.reply("🚀 <b>Запускаю полную рассылку...</b>")
                
                for user in self.users_list:
                    try:
                        u_id = int(user['id'])
                        await self.bot.copy_message(
                            chat_id=u_id,
                            from_chat_id=m.chat.id,
                            message_id=target_msg_id
                        )
                        sent_count += 1
                        await asyncio.sleep(0.05) # Защита от Flood Limit
                    except Exception:
                        err_count += 1
                        user["is_active"] = False

                await status_msg.edit_text(
                    f"✅ <b>Рассылка завершена!</b>\n\n"
                    f"👤 Доставлено: {sent_count}\n"
                    f"🚫 Ошибки: {err_count}"
                )
                await self._save_to_db(headers)
                return True
            else:
                # Если просто ввели /broadcast без реплая
                self.broadcast_cache[m.from_user.id] = "WAITING"
                await m.reply("📢 <b>Режим рассылки.</b>\nПришлите сообщение (текст/фото/видео), которое нужно разослать.")
                return True

        # --- ГРУППА 2: КОМАНДЫ МОДЕРАЦИИ (ТРЕБУЮТ КОНТЕКСТ ЮЗЕРА) ---
        
        target_user = None
        # А) Поиск по топику (если пишем в ветке форума)
        if m.message_thread_id:
            target_user = next((u for u in self.users_list if u.get("last_topic_id") == m.message_thread_id), None)
        
        # Б) Поиск по реплаю (на сообщение, которое переслал бот)
        if not target_user and m.reply_to_message:
            uid_from_map = self.msg_map.get(m.reply_to_message.message_id)
            if uid_from_map:
                target_user = next((u for u in self.users_list if int(u['id']) == int(uid_from_map)), None)

        # В) Поиск по прямому ID в аргументе команды: /ban 123456789
        if not target_user and len(cmd_parts) > 1:
            try:
                direct_id = int(cmd_parts[1])
                target_user = next((u for u in self.users_list if int(u['id']) == direct_id), None)
                if not target_user:
                    # Создаём минимальную запись, чтобы можно было забанить превентивно
                    if command in ('ban', 'unban'):
                        target_user = {
                            "id": direct_id,
                            "first_name": f"User#{direct_id}",
                            "username": None,
                            "is_banned": False,
                            "warns": 0,
                            "joined_at": int(time.time()),
                            "last_seen": int(time.time()),
                        }
                        self.users_list.append(target_user)
                    else:
                        await m.reply(f"Пользователь с ID <code>{direct_id}</code> не найден в базе.")
                        return True
            except ValueError:
                pass

        # Если команда модерации, но юзер не определен — выходим
        if not target_user:
            return False 

        uid = target_user['id']
        ban_limit = self.config.get("settings", {}).get("autoBanThreshold", 3)

        # 🔍 ИНФО О ПОЛЬЗОВАТЕЛЕ (/whois)
        if command == "whois":
            username = target_user.get("username")
            name_line = target_user.get("first_name", "—")
            if username:
                name_line += f" (@{username})"
            joined = datetime.fromtimestamp(target_user.get("joined_at", 0)).strftime("%d.%m.%Y %H:%M") if target_user.get("joined_at") else "—"
            last_seen = datetime.fromtimestamp(target_user.get("last_seen", 0)).strftime("%d.%m.%Y %H:%M") if target_user.get("last_seen") else "—"
            await m.reply(
                f"🔍 <b>Пользователь <code>{uid}</code>:</b>\n\n"
                f"Имя: {name_line}\n"
                f"Забанен: {'Да' if target_user.get('is_banned') else 'Нет'}\n"
                f"Варнов: {target_user.get('warns', 0)}\n"
                f"Зашёл: {joined}\n"
                f"Активность: {last_seen}"
            )
            return True

        # 🚫 БАН
        if command == "ban":
            # Защита: нельзя забанить администратора
            if uid in self.admin_ids:
                await m.reply("⛔ <b>Нельзя забанить администратора бота.</b>")
                return True
            target_user["is_banned"] = True
            self.stats_data["bannedCount"] = self.stats_data.get("bannedCount", 0) + 1
            await self._save_to_db(headers)
            try: await self.bot.send_message(uid, "🚫 <b>Доступ к боту ограничен администратором.</b>")
            except: pass
            await m.reply(f"✅ Пользователь <code>{uid}</code> заблокирован.")
            return True

        # 🟢 РАЗБАН
        elif command == "unban":
            target_user["is_banned"] = False
            target_user["warns"] = 0
            self.stats_data["bannedCount"] = max(0, self.stats_data.get("bannedCount", 1) - 1)
            await self._save_to_db(headers)
            try: await self.bot.send_message(uid, "✅ <b>Ваш доступ к боту восстановлен.</b>")
            except: pass
            await m.reply(f"✅ Пользователь <code>{uid}</code> разблокирован.")
            return True

        # ⚠️ ВАРН
        elif command == "warn":
            # Защита: нельзя выдать варн администратору
            if uid in self.admin_ids:
                await m.reply("⛔ <b>Нельзя выдать варн администратору бота.</b>")
                return True
            target_user["warns"] = target_user.get("warns", 0) + 1
            if target_user["warns"] >= ban_limit:
                target_user["is_banned"] = True
                self.stats_data["bannedCount"] = self.stats_data.get("bannedCount", 0) + 1
                msg_text = f"🚨 <b>АВТО-БАН!</b>\nЮзер: <code>{uid}</code>\nВарнов: {target_user['warns']}/{ban_limit}"
                user_notif = f"🚫 <b>Авто-бан:</b> Лимит предупреждений ({target_user['warns']}/{ban_limit}) исчерпан."
            else:
                msg_text = f"⚠️ Варн выдан пользователю <code>{uid}</code>. Всего: {target_user['warns']}/{ban_limit}"
                user_notif = f"⚠️ <b>Предупреждение!</b> ({target_user['warns']}/{ban_limit})"

            await self._save_to_db(headers)
            try: await self.bot.send_message(uid, user_notif)
            except: pass
            await m.reply(msg_text)
            return True

        # 🔄 СНЯТЬ ВАРН
        elif command == "unwarn":
            target_user["warns"] = max(0, target_user.get("warns", 0) - 1)
            await self._save_to_db(headers)
            await m.reply(f"✅ Предупреждение снято. Теперь варнов у <code>{uid}</code>: {target_user['warns']}")
            return True

        # 🎯 ПРИОРИТЕТ ТИКЕТА
        elif command == "priority":
            if len(cmd_parts) < 2:
                await m.reply(
                    "🎯 <b>Управление приоритетом:</b>\n\n"
                    "/priority high — 🔴 Высокий\n"
                    "/priority normal — 🟡 Нейтральный\n"
                    "/priority low — ⚪ Низкий\n\n"
                    "<i>Используйте команду в топике пользователя или с реплаем на его сообщение.</i>"
                )
                return True

            level = cmd_parts[1].lower()
            if level not in PRIORITY_LEVELS:
                await m.reply("❌ Неверный уровень. Доступны: <code>high</code>, <code>normal</code>, <code>low</code>")
                return True

            pinfo = PRIORITY_LEVELS[level]
            target_user["priority"] = level

            # Переименовываем топик
            thread_id = target_user.get("last_topic_id")
            if thread_id and self.use_topics:
                new_name = build_topic_name(target_user, self.settings, level)
                try:
                    await self.bot.edit_forum_topic(
                        chat_id=self.admin_chat_id,
                        message_thread_id=thread_id,
                        name=new_name
                    )
                except Exception as e:
                    logger.warning(f"Не удалось переименовать топик: {e}")

            # Уведомляем пользователя
            try:
                await self.bot.send_message(uid, pinfo["notify_user"], parse_mode="HTML")
            except Exception:
                pass

            # Уведомление в топик для команды
            admin_note_lines = {
                "high": "🔴 <b>ВЫСОКИЙ ПРИОРИТЕТ</b>\nОбращение помечено как срочное и требует первоочередной обработки.",
                "normal": "🟡 <b>Нейтральный приоритет</b>\nОбращение переведено в стандартную очередь.",
                "low": "⚪ <b>Низкий приоритет</b>\nОбращение помечено как несрочное.",
            }
            try:
                if thread_id:
                    await self.bot.send_message(
                        chat_id=self.admin_chat_id,
                        message_thread_id=thread_id,
                        text=admin_note_lines[level],
                        parse_mode="HTML"
                    )
            except Exception:
                pass

            await self._save_to_db(headers)
            await m.reply(f"✅ Приоритет установлен: {pinfo['prefix']} <b>{pinfo['label']}</b>\nПользователь уведомлён.")
            return True

        # ── СТАФФ: /give <id|псевдоним> — передать тикет другому администратору ──
        if command == "give":
            if not self.staff_enabled:
                return False
            if len(cmd_parts) < 2:
                await m.reply(
                    "🔄 <b>Передача тикета:</b>\n\n"
                    "/give <code>ID</code> или /give <code>псевдоним</code>\n\n"
                    "<i>Используйте в топике пользователя или с реплаем на его сообщение.</i>"
                )
                return True
            new_staff = self._find_staff_by_arg(cmd_parts[1])
            if not new_staff:
                await m.reply(f"❌ Администратор <code>{cmd_parts[1]}</code> не найден.\nПроверьте ID или псевдоним.")
                return True
            if not new_staff.get('active'):
                await m.reply(f"⚠️ Администратор <b>{new_staff.get('alias', new_staff.get('name'))}</b> сейчас неактивен.")
                return True
            await self._assign_staff_to_user(target_user, new_staff)
            await self._save_to_db(headers)
            await m.reply(
                f"✅ Тикет передан администратору <b>{new_staff.get('alias', new_staff.get('name'))}</b>.\n"
                f"Пользователь уведомлён."
            )
            return True

        return False

    async def _format_staff_stat(self, staff: dict) -> str:
        """Форматирует статистику стафф-администратора."""
        st = staff.get('stats', {})
        accepted  = st.get('ticketsAccepted', 0)
        closed    = st.get('ticketsClosed', 0)
        msgs      = st.get('messagesSent', 0)
        avg_ms    = st.get('avgResponseMs', 0)
        if avg_ms < 60000:
            avg_str = f"{round(avg_ms / 1000)}с" if avg_ms else "—"
        else:
            avg_str = f"{round(avg_ms / 60000)}м"
        return (
            f"📊 <b>Статистика: {staff.get('alias', staff.get('name', '?'))}</b>\n\n"
            f"🎫 Принято тикетов: <b>{accepted}</b>\n"
            f"✅ Закрыто тикетов: <b>{closed}</b>\n"
            f"💬 Отправлено сообщений: <b>{msgs}</b>\n"
            f"⏱ Среднее время ответа: <b>{avg_str}</b>"
        )

    async def _save_to_db(self, headers=None):
        """
        Вспомогательная функция для синхронизации состояния с БД и очередью.
        """
        try:
            rows = await self.db.get("bots", {"id": f"eq.{self.bot_id}"})
            if rows:
                remote_config = rows[0].get("config", {})
                new_config = {
                    **remote_config,
                    "connectedUsers": self.users_list,
                    "stats":          self.stats_data,
                }
                await self.db.patch("bots", {"id": f"eq.{self.bot_id}"}, {"config": new_config})
            await self.sync_queue.put(("sync_state", None))
        except Exception as e:
            logging.error(f"❌ Ошибка сохранения в БД: {e}")
        
    async def core_handlers_setup(self):
        # В aiogram 3 middleware выполняются в ОБРАТНОМ порядке регистрации.
        # Последний зарегистрированный — выполняется первым (стек/onion).
        # Поэтому SubscriptionMiddleware регистрируем ПОСЛЕДНЕЙ — она сработает ПЕРВОЙ.

        # Порядок выполнения (снизу вверх): Subscription -> MemoryBase -> Ban -> License
        self.router.message.middleware(LicenseMiddleware(self))
        self.router.callback_query.middleware(LicenseMiddleware(self))

        self.router.message.middleware(BanMiddleware(self))
        self.router.callback_query.middleware(BanMiddleware(self))

        # MemoryBase — проверка перед подпиской
        self.router.message.middleware(MemoryBaseMiddleware(self))
        self.router.callback_query.middleware(MemoryBaseMiddleware(self))

        # Подписка — регистрируем последней, выполняется первой
        self.router.message.middleware(SubscriptionMiddleware(self))
        self.router.callback_query.middleware(SubscriptionMiddleware(self))

        # Обработчик разбана через MemoryBase (только для администраторов)
        @self.router.callback_query(lambda c: c.data and c.data.startswith("mb_unban_"))
        async def handle_mb_unban(cb: CallbackQuery):
            uid_cb = cb.from_user.id
            if uid_cb not in (self.admin_ids or set()):
                await cb.answer("⛔ Только для администраторов.", show_alert=True)
                return
            try:
                target_uid = int(cb.data.split("mb_unban_")[1])
            except (IndexError, ValueError):
                await cb.answer("❌ Ошибка.", show_alert=True)
                return
            target = next((u for u in self.users_list if u.get('id') == target_uid), None)
            if target:
                target['mb_restricted'] = False
                target['mb_notified']    = False  # сброс — следующая блокировка снова уведомит
                target['mb_reasons']    = []
                target['last_mb_check'] = 0
                await self.sync_queue.put(("sync_state", None))

            # ── КРИТИЧНО: удаляем запись из memory_base_cache в Supabase ──
            # Иначе при следующем сообщении middleware снова заблокирует
            try:
                ok = await self.db.patch(
                    "memory_base_cache",
                    {"user_id": f"eq.{target_uid}"},
                    {"status": "clean", "reasons": []},
                )
                logger.info(f"[MB] cache unban uid={target_uid} → clean, ok={ok}")
            except Exception as _de:
                logger.warning(f"[MB] cache delete error: {_de}")

            try:
                await self.bot.send_message(
                    target_uid,
                    "✅ <b>Доступ восстановлен!</b>\n\n"
                    "Администратор бота разрешил вам пользоваться ботом.\n"
                    "Нажмите /start чтобы начать."
                )
            except Exception:
                pass
            await cb.message.edit_reply_markup(reply_markup=None)
            await cb.answer("✅ Пользователь разбанен и уведомлён.", show_alert=True)
            try:
                await cb.message.reply(
                    f"✅ <b>Разблокировано через MemoryBase.</b>\n"
                    f"ID: <code>{target_uid}</code>"
                )
            except Exception:
                pass

        # Обработчик кнопки "Я подписался — проверить"
        @self.router.callback_query(F.data == "check_sub")
        async def handle_check_sub(cb: CallbackQuery):
            required_channels = getattr(self, 'required_channels', [])
            user_id = cb.from_user.id
            not_subscribed = []
            for ch in required_channels:
                ch_id = ch.get('id', '').strip()
                if not ch_id:
                    continue
                try:
                    member = await self.bot.get_chat_member(ch_id, user_id)
                    if member.status in ('left', 'kicked', 'banned'):
                        not_subscribed.append(ch)
                except Exception:
                    not_subscribed.append(ch)

            if not_subscribed:
                await cb.answer("❌ Вы ещё не подписались на все каналы!", show_alert=True)
            else:
                await cb.answer("✅ Отлично! Теперь вы можете пользоваться ботом.", show_alert=True)
                try:
                    await cb.message.delete()
                except Exception:
                    pass
                # Показываем стартовое сообщение
                user_rec = next((u for u in self.users_list if u['id'] == user_id), None)
                if not user_rec:
                    user_rec = {
                        "id": user_id, "first_name": cb.from_user.first_name,
                        "username": cb.from_user.username, "is_banned": False,
                        "is_active": True, "warns": 0,
                        "joined_at": int(time.time()), "last_seen": int(time.time()),
                        "last_topic_id": None
                    }
                    self.users_list.append(user_rec)
                reply_kb  = self.get_main_keyboard()
                inline_kb = self.build_inline_from_list(self.welcome_inline)
                try:
                    if self.welcome_photo:
                        await self.bot.send_photo(
                            chat_id=user_id, photo=self.welcome_photo,
                            caption=self.welcome_text,
                            reply_markup=inline_kb if inline_kb else reply_kb
                        )
                    else:
                        await self.bot.send_message(
                            chat_id=user_id, text=self.welcome_text,
                            reply_markup=inline_kb if inline_kb else reply_kb
                        )
                except Exception as e:
                    logger.warning(f"check_sub welcome error: {e}")

        # 1. Обработка блокировки бота пользователем
        @self.router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=ChatMemberStatus.KICKED))
        async def on_user_blocked_bot(event: ChatMemberUpdated):
            user_id = event.from_user.id
            user = next((u for u in self.users_list if u['id'] == user_id), None)
            if user:
                user["is_active"] = False
                await self.sync_queue.put(("sync_state", None))
                if self.admin_chat_id:
                    thread_id = user.get("last_topic_id")
                    text = f"🔴 <b>Внимание!</b>\nПользователь <b>{event.from_user.full_name}</b> (@{event.from_user.username or '---'}) заблокировал бота."
                    try: 
                        await self.bot.send_message(self.admin_chat_id, text, message_thread_id=thread_id)
                    except: 
                        pass
            logger.info(f"[!] Пользователь {user_id} заблокировал бота.")

        # 2. Команда /start
        @self.router.message(CommandStart())
        async def handle_start_msg(m: Message):
            user, is_new = await self.get_user_state(m)
            if user.get("is_banned"):
                if m.from_user.id in self.admin_ids:
                    unban_kb = InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔓 Разбанить себя", callback_data="selfunban")
                    ]])
                    await m.answer(
                        "⚠️ <b>Вы случайно забанили себя (администратора).</b>\n"
                        "Нажмите кнопку ниже, чтобы снять блокировку:",
                        reply_markup=unban_kb
                    )
                else:
                    await m.answer("🚫 <b>Вы заблокированы в этом боте.</b>")
                return

            # Сбрасываем состояние flow и тикетов при /start
            user.pop('_flow_nodes', None)
            user.pop('_in_ticket', None)
            user.pop('_ticket_close_label', None)
            user.pop('_ai_session', None)

            reply_kb  = self.get_main_keyboard()
            inline_kb = self.build_inline_from_list(self.welcome_inline)

            try:
                if self.welcome_photo:
                    # Фото + подпись + инлайн (или reply, если инлайна нет)
                    await m.answer_photo(
                        photo=self.welcome_photo,
                        caption=self.welcome_text,
                        reply_markup=inline_kb if inline_kb else reply_kb
                    )
                else:
                    # Просто текст + инлайн (или reply, если инлайна нет)
                    await m.answer(
                        text=self.welcome_text, 
                        reply_markup=inline_kb if inline_kb else reply_kb
                    )
            except Exception as _pe:
                logger.warning(f"start msg error: {_pe}")
                await m.answer(text=self.welcome_text, reply_markup=reply_kb)

            await self.log_and_update(user['id'], m.from_user.full_name, "/start")

        # 3. Ввод от админа (Команды и Ответы)
        @self.router.message(F.chat.id == self.admin_chat_id)
        async def admin_input_router(m: Message):
            # Проверяем, является ли сообщение командой
            if m.text and (m.text.startswith("/") or m.text.startswith("!")):
                # Выполняем логику админки
                await self.admin_control_logic(m)
                # ОБЯЗАТЕЛЬНО делаем return, чтобы никакие команды (даже опечатки) 
                # не улетали обычному пользователю
                return

            target_id = None
            if m.message_thread_id:
                u = next((u for u in self.users_list if u.get("last_topic_id") == m.message_thread_id), None)
                if u: target_id = u["id"]
            
            if not target_id and m.reply_to_message:
                target_id = self.msg_map.get(m.reply_to_message.message_id)
            
            if target_id:
                try:
                    sent = await self.bot.copy_message(target_id, m.chat.id, m.message_id)
                    if sent:
                        # admin_msg_id → target_id, и (target_id, user_msg_id) → admin_msg_id
                        self.msg_map[m.message_id] = target_id
                        self.user_to_admin_map[(target_id, sent.message_id)] = m.message_id
                    await self.log_and_update(target_id, "Admin", m.text or "[Медиа]", is_admin=True)
                except TelegramForbiddenError:
                    await m.reply("❌ <b>Ошибка:</b> Пользователь заблокировал бота.")
                except Exception as e:
                    await m.reply(f"❌ <b>Ошибка:</b> {e}")

        # 3а. Редактирование сообщения администратором → обновить у пользователя
        @self.router.edited_message(F.chat.id == self.admin_chat_id)
        async def admin_edited_message(m: Message):
            # Не обрабатываем команды
            if m.text and (m.text.startswith("/") or m.text.startswith("!")):
                return
            admin_msg_id = m.message_id
            # Получаем target_id из msg_map (сохраняется при отправке)
            target_id = self.msg_map.get(admin_msg_id)
            # Ищем user_msg_id: ключ в user_to_admin_map где value == admin_msg_id
            user_msg_id = next(
                (umid for (uid, umid), amid in self.user_to_admin_map.items()
                 if amid == admin_msg_id),
                None
            )
            if not target_id and user_msg_id:
                # Попробуем найти target_id через ключ маппинга
                target_id = next(
                    (uid for (uid, umid) in self.user_to_admin_map
                     if umid == user_msg_id and self.user_to_admin_map.get((uid, umid)) == admin_msg_id),
                    None
                )
            if target_id and user_msg_id:
                try:
                    if m.text:
                        await self.bot.edit_message_text(
                            chat_id=target_id,
                            message_id=user_msg_id,
                            text=m.text,
                            parse_mode="HTML"
                        )
                    elif m.caption is not None:
                        await self.bot.edit_message_caption(
                            chat_id=target_id,
                            message_id=user_msg_id,
                            caption=m.caption,
                            parse_mode="HTML"
                        )
                except TelegramBadRequest as e:
                    logger.warning(f"Admin edit → user failed: {e}")
                except Exception as e:
                    logger.warning(f"Admin edit → user error: {e}")

        # 3б. Редактирование сообщения пользователем → обновить у админа
        @self.router.edited_message()
        async def user_edited_message(m: Message):
            if self.admin_chat_id and m.chat.id == self.admin_chat_id:
                return
            uid = m.from_user.id
            admin_msg_id = self.user_to_admin_map.get((uid, m.message_id))
            if admin_msg_id and self.admin_chat_id:
                try:
                    if m.text:
                        await self.bot.edit_message_text(
                            chat_id=self.admin_chat_id,
                            message_id=admin_msg_id,
                            text=m.text,
                            parse_mode="HTML"
                        )
                    elif m.caption is not None:
                        await self.bot.edit_message_caption(
                            chat_id=self.admin_chat_id,
                            message_id=admin_msg_id,
                            caption=m.caption,
                            parse_mode="HTML"
                        )
                except TelegramBadRequest as e:
                    logger.warning(f"User edit → admin failed: {e}")
                except Exception as e:
                    logger.warning(f"User edit → admin error: {e}")

        # 3в. Зеркалирование реакций между юзером и админом
        @self.router.message_reaction()
        async def mirror_reactions(reaction: MessageReactionUpdated):
            chat_id = reaction.chat.id
            msg_id = reaction.message_id
            
            # Сценарий А: Реакцию поставили в админ-чате
            if self.admin_chat_id and chat_id == self.admin_chat_id:
                # Ищем ID пользователя по сообщению
                target_user_id = self.msg_map.get(msg_id)
                if not target_user_id:
                    # Запасной поиск
                    target_user_id = next((uid for (uid, umid), amid in self.user_to_admin_map.items() if amid == msg_id), None)
                
                if target_user_id:
                    # Ищем ID сообщения на стороне пользователя
                    user_msg_id = next((umid for (uid, umid), amid in self.user_to_admin_map.items() if amid == msg_id and uid == target_user_id), None)
                    if user_msg_id:
                        try:
                            await self.bot.set_message_reaction(
                                chat_id=target_user_id, 
                                message_id=user_msg_id, 
                                reaction=reaction.new_reaction
                            )
                        except Exception as e:
                            logger.warning(f"Ошибка переноса реакции пользователю {target_user_id}: {e}")

            # Сценарий Б: Реакцию поставил обычный пользователь
            else:
                user_id = chat_id
                # Ищем ID сообщения на стороне админа
                admin_msg_id = self.user_to_admin_map.get((user_id, msg_id))
                
                if admin_msg_id and self.admin_chat_id:
                    try:
                        await self.bot.set_message_reaction(
                            chat_id=self.admin_chat_id, 
                            message_id=admin_msg_id, 
                            reaction=reaction.new_reaction
                        )
                    except Exception as e:
                        logger.warning(f"Ошибка переноса реакции админу от {user_id}: {e}")

        # 4. Сообщения от обычных пользователей
        @self.router.message()
        async def user_input_router(m: Message):
            # Пропускаем, если пишет админ в админ-чате
            if self.admin_chat_id and m.chat.id == self.admin_chat_id:
                return

            user, is_new = await self.get_user_state(m)
            
            # Заблокированный — отвечаем и СРАЗУ выходим
            if user.get("is_banned"):
                if m.from_user.id in self.admin_ids:
                    unban_kb = InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔓 Разбанить себя", callback_data="selfunban")
                    ]])
                    await m.answer(
                        "⚠️ <b>Вы случайно забанили себя (администратора).</b>\n"
                        "Нажмите кнопку ниже, чтобы снять блокировку:",
                        reply_markup=unban_kb
                    )
                else:
                    await m.answer("🚫 <b>Вы заблокированы в этом боте.</b>")
                return

            uid = user['id']

            # ── ОБРАБОТКА MEDIA GROUP (несколько медиа за раз) ──
            # ВАЖНО: делаем это ДО антиспама, иначе второе фото блокируется rate limit-ом
            if m.media_group_id:
                gid = m.media_group_id
                # Сначала добавляем сообщение, потом запускаем задачу только для первого
                if gid not in self.media_group_buffer:
                    self.media_group_buffer[gid] = {
                        "messages": [],
                        "user": user,
                        "is_first": is_new,
                        "in_ticket": user.get('_in_ticket', False),
                        "forward_all": self.forward_all,
                    }
                    async def _schedule_flush(group_id=gid):
                        await asyncio.sleep(1.0)  # Ждём все части альбома
                        buf = self.media_group_buffer.pop(group_id, None)
                        if not buf or not buf["messages"]:
                            return
                        _user = buf["user"]
                        _is_first = buf["is_first"]
                        _in_ticket = buf["in_ticket"]
                        _forward_all = buf["forward_all"]
                        logger.info(f"[MediaGroup] Flush {group_id}: {len(buf['messages'])} msgs, in_ticket={_in_ticket}, forward_all={_forward_all}, is_first={_is_first}")
                        if _in_ticket or _forward_all or _is_first:
                            await self._send_media_group_to_admin(buf["messages"], _user, _is_first)
                            await self.log_and_update(_user['id'], buf["messages"][0].from_user.full_name, "[Медиагруппа]")
                    asyncio.create_task(_schedule_flush())
                self.media_group_buffer[gid]["messages"].append(m)
                logger.info(f"[MediaGroup] +msg {m.message_id} -> group {gid}, total={len(self.media_group_buffer[gid]['messages'])}")
                return

            # Антиспам проверяем только для обычных сообщений (не media group)
            if await self.check_antispam(user['id']):
                return

            # ── РЕЖИМ АКТИВНОГО ТИКЕТА ──
            if user.get('_in_ticket'):
                # Если нажата текстовая кнопка закрытия
                _close_label = user.get('_ticket_close_label', 'Закрыть обращение')
                if m.text and m.text.strip() in (_close_label, "Закрыть обращение"):
                    user.pop('_in_ticket', None)
                    user.pop('_ticket_close_label', None)
                    # Сразу сохраняем состояние в БД
                    await self.sync_queue.put(("sync_state", None))
                    
                    if self.admin_chat_id:
                        thread_id = user.get("last_topic_id")
                        name = user.get("first_name", str(uid))
                        username_str = user.get("username")
                        user_line = name
                        if username_str:
                            user_line += f" (@{username_str})"
                        user_line += f" | ID: <code>{uid}</code>"
                        try:
                            await self.bot.send_message(
                                self.admin_chat_id,
                                f"Обращение закрыто пользователем.\n{user_line}",
                                message_thread_id=thread_id,
                                parse_mode="HTML"
                            )
                        except Exception:
                            pass

                    # Стафф: закрытие тикета
                    if self.staff_enabled and user.get('assigned_staff_id'):
                        asyncio.create_task(self._post_staff_stat(user['assigned_staff_id'], 'closed'))
                        # Считаем время ответа
                        assigned_at = user.get('_staff_assigned_at')
                        if assigned_at:
                            elapsed_ms = int(time.time() * 1000) - assigned_at
                            asyncio.create_task(self._post_staff_stat(user['assigned_staff_id'], 'response_ms', elapsed_ms))
                        user.pop('assigned_staff_id', None)
                        user.pop('assigned_staff_alias', None)
                        user.pop('assigned_staff_tg', None)
                        user.pop('_staff_assigned_at', None)
                    
                    await m.answer("Обращение закрыто.", reply_markup=self.get_main_keyboard())
                    return

                # ── СТАФФ: кнопка "Сменить админа" ──
                if self.staff_enabled and self.staff_allow_switch and m.text and m.text.strip() == "🔄 Сменить админа":
                    active = self._get_active_staff()
                    # Исключаем текущего
                    current_id = user.get('assigned_staff_id')
                    candidates = [a for a in active if a.get('id') != current_id]
                    if not candidates:
                        await m.answer("😔 Других доступных администраторов нет.", parse_mode="HTML")
                    else:
                        import random as _rnd
                        new_staff = _rnd.choice(candidates)
                        await self._assign_staff_to_user(user, new_staff, m)
                        await self.sync_queue.put(("sync_state", None))
                        await m.answer(f"✅ Обращение передано администратору: <b>{new_staff.get('alias', new_staff.get('name'))}</b>", parse_mode="HTML")
                    return

                # ── СТАФФ: кнопка "Список администрации" ──
                if self.staff_enabled and self.staff_show_list and m.text and m.text.strip() == self.staff_list_btn_name:
                    await self._handle_staff_list_request(uid)
                    return

                # Если тикет открыт и это НЕ кнопка закрытия — пересылаем админу и выходим
                await self.forward_to_admin(m, user)
                await self.log_and_update(uid, m.from_user.full_name, m.text or "[Медиа]")
                return

            if m.text:
                clean_text = m.text.strip()
                clean_lower = clean_text.lower()

                # ── А) Кнопка "Назад" ──
                if clean_text in ("⬅️ Назад", "Назад"):
                    user.pop('_ai_session', None)
                    user.pop('_flow_nodes', None)
                    self.clear_ai_context(uid)
                    await m.answer("Главное меню:", reply_markup=self.get_main_keyboard())
                    return

                # ── А1) СТАФФ: кнопки вне тикетного режима ──
                if self.staff_enabled and self.staff_allow_switch and clean_text == "🔄 Сменить админа":
                    active = self._get_active_staff()
                    current_id = user.get('assigned_staff_id')
                    candidates = [a for a in active if a.get('id') != current_id]
                    if not candidates:
                        await m.answer("😔 Других доступных администраторов нет.")
                    else:
                        import random as _rnd
                        new_staff = _rnd.choice(candidates)
                        await self._assign_staff_to_user(user, new_staff, m)
                        await self.sync_queue.put(("sync_state", None))
                        await m.answer(f"✅ Администратор изменён: <b>{new_staff.get('alias', new_staff.get('name'))}</b>", parse_mode="HTML")
                    return

                if self.staff_enabled and self.staff_show_list and clean_text == self.staff_list_btn_name:
                    await self._handle_staff_list_request(uid)
                    return

                # ── Б) Кнопка ИИ-ассистента из клавиатуры ──
                if self.ai_enabled and self.ai_mode == 'button' and clean_text == self.ai_button_name:
                    bal = await self.check_ai_tokens()
                    if bal <= 0:
                        await m.answer("⚠️ AI-токены закончились. Обратитесь к администратору.")
                        return
                    user['_ai_session'] = True
                    close_kb = InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="✖ Закрыть диалог с ИИ", callback_data="ai_close")
                    ]])
                    await m.answer("🤖 <b>ИИ-ассистент активирован.</b>\nЗадайте вопрос:", reply_markup=close_kb)
                    return

                # ── В) Проверка flow-логики расширенных кнопок ──
                flow_handled = await self.handle_flow_button(m, user)
                if flow_handled:
                    await self.log_and_update(uid, m.from_user.full_name, f"FLOW: {clean_text}")
                    return

                # ── Г) Проверка на кнопки меню (с поддержкой вложенности) ──
                matched_btn = self.get_button_by_text(clean_text)
                if matched_btn:
                    user.pop('_ai_session', None)
                    user.pop('_flow_nodes', None)
                    children = matched_btn.get('children', [])
                    # Инлайн URL-кнопки (только TG — VK не поддерживает в этом формате)
                    inline_links = matched_btn.get('inline', [])
                    inline_kb = self.build_inline_from_list(inline_links) if inline_links else None

                    if children:
                        child_kb = self.build_keyboard_from_buttons(children + [{"text": "⬅️ Назад"}])
                        resp = matched_btn.get('response', '')
                        await m.answer(resp or "Выберите вариант:", reply_markup=child_kb)
                        # Инлайн-кнопки идут отдельным сообщением если есть под-меню
                        if inline_kb:
                            await m.answer("Полезные ссылки:", reply_markup=inline_kb)
                    else:
                        if matched_btn.get('type') == 'request':
                            user['_in_ticket'] = True
                            await self.forward_to_admin(m, user, btn_text=matched_btn['text'])
                            resp_text = matched_btn.get('response', 'Ваше обращение принято. Ожидайте ответа оператора.')
                            close_ticket_kb = ReplyKeyboardMarkup(
                                keyboard=[[KeyboardButton(text="Закрыть обращение")]],
                                resize_keyboard=True
                            )
                            await m.answer(
                                f"{resp_text}\n\nВы можете продолжать писать — сообщения будут доставлены оператору.",
                                reply_markup=close_ticket_kb
                            )
                            if inline_kb:
                                await m.answer("Полезные ссылки:", reply_markup=inline_kb)
                        else:
                            resp_text = matched_btn.get('response', 'Принято!')
                            # Если есть инлайн-кнопки — отправляем их вместе с ответом
                            await m.answer(resp_text, reply_markup=inline_kb if inline_kb else self.get_main_keyboard())
                            # Если были инлайн-кнопки — дополнительно показать основную клавиатуру
                            if inline_kb:
                                await m.answer("Главное меню:", reply_markup=self.get_main_keyboard())

                    await self.log_and_update(uid, m.from_user.full_name, f"КНОПКА: {matched_btn['text']}")
                    return

                # ── Д) /ai, /gpt, /nn ──
                if clean_lower in ('/ai', '/gpt', '/nn'):
                    if self.ai_enabled and self.ai_mode in ('command', 'all', 'button'):
                        bal = await self.check_ai_tokens()
                        if bal <= 0:
                            await m.answer("AI-токены закончились. Обратитесь к администратору.")
                            return
                        user['_ai_session'] = True
                        close_kb = InlineKeyboardMarkup(inline_keyboard=[[
                            InlineKeyboardButton(text="✖ Закрыть диалог с ИИ", callback_data="ai_close")
                        ]])
                        await m.answer("ИИ-ассистент активирован. Задайте вопрос. Для выхода — нажмите кнопку ниже.", reply_markup=close_kb)
                    else:
                        await m.answer("ИИ-ассистент не подключён к этому боту.")
                    return

                if clean_lower == '/reset_ai':
                    self.clear_ai_context(uid)
                    user.pop('_ai_session', None)
                    user.pop('_flow_nodes', None)
                    await m.answer("Контекст и сессия ИИ сброшены.", reply_markup=self.get_main_keyboard())
                    return

                # ── Д) ТРИГГЕРЫ ──
                triggered = False
                for trig in self.triggers:
                    if trig.get('keyword') and trig['keyword'].lower() in clean_lower:
                        resp_text = trig.get('response', '')
                        trig_children = trig.get('children', [])
                        if trig_children:
                            child_kb = self.build_keyboard_from_buttons(trig_children)
                            await m.answer(resp_text or "Выберите:", reply_markup=child_kb)
                        else:
                            await m.answer(resp_text or "")
                        await self.log_and_update(uid, m.from_user.full_name, f"ТРИГГЕР: {trig['keyword']}")
                        triggered = True
                        break
                if triggered:
                    return

                # ── Е) ИИ-АССИСТЕНТ — режим «отвечать на всё» ──
                if self.ai_enabled and self.ai_mode == 'all':
                    bal = await self.check_ai_tokens()
                    if bal > 0:
                        thinking = await m.answer("🤖 Думаю...")
                        answer = await self.ai_call(uid, clean_text)
                        if answer:
                            await thinking.delete()
                            await m.answer(answer)
                            await self.forward_to_admin(m, user, is_ai_request=True)
                            await self.log_and_update(uid, m.from_user.full_name, f"AI: {clean_text[:50]}")
                            return
                        else:
                            await thinking.delete()
                    else:
                        await m.answer("⚠️ Лимит AI-токенов исчерпан. Обратитесь к администратору.")
                        return

            # ── Ж) Активная AI-сессия ──
            if user.get('_ai_session') and self.ai_enabled and m.text:
                bal = await self.check_ai_tokens()
                if bal <= 0:
                    user.pop('_ai_session', None)
                    user.pop('_flow_nodes', None)
                    self.clear_ai_context(uid)
                    await m.answer("⚠️ AI-токены закончились. Сессия закрыта.", reply_markup=self.get_main_keyboard())
                    return
                close_kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="✖ Закрыть диалог с ИИ", callback_data="ai_close")
                ]])
                thinking = await m.answer("🤖 Думаю...")
                answer_text = await self.ai_call(uid, m.text)
                await thinking.delete()
                if answer_text:
                    await m.answer(answer_text, reply_markup=close_kb)
                    await self.forward_to_admin(m, user, is_ai_request=True)
                    await self.log_and_update(uid, m.from_user.full_name, f"AI: {m.text[:50]}")
                else:
                    await m.answer("⚠️ Ошибка ИИ, попробуйте ещё раз.", reply_markup=close_kb)
                return

            # ── ЗАЩИТА ОТ СПАМА АДМИНУ ПОСЛЕ ЗАКРЫТИЯ ТИКЕТА ──
            if is_new:
                # Если человек пишет впервые, пересылаем админу
                await self.forward_to_admin(m, user, is_first=True)
                await self.log_and_update(uid, m.from_user.full_name, m.text or "[Медиа]")
            elif self.forward_all:
                # Режим «без тикетов» — пересылаем все сообщения, тикет не нужен
                await self.forward_to_admin(m, user)
                await self.log_and_update(uid, m.from_user.full_name, m.text or "[Медиа]")
            else:
                # Если тикет закрыт, это не кнопка и не триггер — просто напоминаем меню
                await m.answer("Пожалуйста, воспользуйтесь меню или нажмите кнопку для открытия обращения.", reply_markup=self.get_main_keyboard())


        # 5. Саморазбан администратора (inline callback)
        @self.router.callback_query(lambda c: c.data == 'selfunban')
        async def on_selfunban(cb: CallbackQuery):
            uid_cb = cb.from_user.id
            # Только администратор может использовать эту кнопку
            if uid_cb not in self.admin_ids:
                await cb.answer("⛔ Эта кнопка только для администратора.", show_alert=True)
                return
            user_cb = next((u for u in self.users_list if u.get('id') == uid_cb), None)
            if user_cb:
                user_cb["is_banned"] = False
                user_cb["warns"] = 0
                self.stats_data["bannedCount"] = max(0, self.stats_data.get("bannedCount", 1) - 1)
                headers = {
                    "apikey": self.sb_key,
                    "Authorization": f"Bearer {self.sb_key}",
                    "Content-Type": "application/json"
                }
                await self._save_to_db(headers)
            await cb.message.edit_text("✅ <b>Блокировка снята. Вы снова администратор бота.</b>")
            await cb.answer("✅ Разбан выполнен!", show_alert=False)

        # 6. Закрытие AI-сессии (inline callback)
        @self.router.callback_query(lambda c: c.data == 'ai_close')
        async def on_ai_close(cb: CallbackQuery):
            uid_cb = cb.from_user.id
            user_cb = next((u for u in self.users_list if u['id'] == uid_cb), None)
            
            if user_cb:
                user_cb.pop('_ai_session', None)
                self.clear_ai_context(uid_cb)
            
            try:
                await cb.message.delete()
            except Exception:
                pass
            
            await cb.answer("Диалог с ИИ закрыт.")
            
            try:
                await self.bot.send_message(
                    chat_id=uid_cb,
                    text="✅ Диалог с ИИ завершён.",
                    reply_markup=self.get_main_keyboard()
                )
            except Exception:
                pass

        # 6. Закрытие тикета пользователем (Inline кнопка)
        @self.router.callback_query(lambda c: c.data == 'ticket_close')
        async def on_ticket_close(cb: CallbackQuery):
            uid_cb = cb.from_user.id
            user_cb = next((u for u in self.users_list if u['id'] == uid_cb), None)

            if user_cb:
                user_cb.pop('_in_ticket', None)
                
                # ВАЖНО: Синхронизация
                await self.sync_queue.put(("sync_state", None))

                if self.admin_chat_id:
                    thread_id = user_cb.get("last_topic_id")
                    name = user_cb.get("first_name", str(uid_cb))
                    username = user_cb.get("username")
                    
                    user_line = f"<b>{name}</b>"
                    if username:
                        user_line += f" (@{username})"
                    user_line += f" | ID: <code>{uid_cb}</code>"
                    
                    try:
                        await self.bot.send_message(
                            chat_id=self.admin_chat_id,
                            text=f"Обращение закрыто пользователем.\n{user_line}",
                            message_thread_id=thread_id,
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass

            try:
                await cb.message.delete()
            except Exception:
                pass
            
            try:
                await cb.answer("Обращение закрыто.")
            except Exception:
                pass

            try:
                await self.bot.send_message(
                    uid_cb,
                    "<b>Обращение закрыто.</b>\nВы вышли из режима диалога с оператором.",
                    reply_markup=self.get_main_keyboard(),
                    parse_mode="HTML"
                )
            except Exception:
                pass

        # ── СТАФФ: выбор конкретного администратора из inline-списка ──
        @self.router.callback_query(lambda c: c.data and c.data.startswith("choose_staff:"))
        async def on_choose_staff(cb: CallbackQuery):
            uid_cb   = cb.from_user.id
            staff_id = cb.data.split(":", 1)[1]
            user_cb  = next((u for u in self.users_list if u['id'] == uid_cb), None)
            if not user_cb:
                await cb.answer("Сессия не найдена.", show_alert=True)
                return

            staff = next((a for a in self.staff_admins if a.get('id') == staff_id), None)
            if not staff:
                await cb.answer("Администратор не найден.", show_alert=True)
                return
            if not staff.get('active'):
                await cb.answer("Этот администратор сейчас недоступен.", show_alert=True)
                return

            await self._assign_staff_to_user(user_cb, staff, None)
            await self.sync_queue.put(("sync_state", None))

            try:
                await cb.message.delete()
            except Exception:
                pass
            try:
                await cb.answer(f"✅ Обращение принял: {staff.get('alias', staff.get('name'))}")
            except Exception:
                pass

    # ==========================================
    # ВНИМАНИЕ: Этот метод находится ВНЕ core_handlers_setup, 
    # поэтому отступ (indent) у него меньше!
    # ==========================================
    def get_main_keyboard(self):
        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
        active_btns = [b for b in self.buttons if b.get('text')]
        # Добавляем AI-кнопку если режим 'button'
        if self.ai_enabled and self.ai_mode == 'button' and self.ai_button_name:
            active_btns = active_btns + [{'text': self.ai_button_name}]
        if not active_btns: return ReplyKeyboardRemove()
        keyboard_rows = []
        for i in range(0, len(active_btns), 2):
            keyboard_rows.append([KeyboardButton(text=b['text']) for b in active_btns[i:i+2]])
        return ReplyKeyboardMarkup(keyboard=keyboard_rows, resize_keyboard=True)

    async def run_instance(self):
        # 1. Инициализируем пул PostgreSQL (приоритетная БД)
        await init_pg_pool()

        logger.info(f"[*] Бот {self.bot_id} проверяет данные перед запуском...")
        try:
            await self.license_checker_logic()
            await self.sync_database_logic()
        except Exception as e:
            logger.error(f"Ошибка при первичной загрузке данных: {e}")

        # 2. Теперь запускаем их как фоновые задачи для обновления в будущем
        asyncio.create_task(self.database_sync_worker())
        asyncio.create_task(self.daily_stats_rotator())
        asyncio.create_task(self.license_checker())
        
        # 3. Настраиваем хендлеры и роутеры
        await self.core_handlers_setup()
        self.dp.include_router(self.router)
        
        logger.info(f"[*] Бот {self.bot_id} готов к работе. Лицензия: {'Истекла' if self.license_expired else 'ОК'}")
        
        try:
            # Сбрасываем webhook — иначе getUpdates (polling) даёт TelegramConflictError
            await self.bot.delete_webhook(drop_pending_updates=True)
            await self.dp.start_polling(
                self.bot,
                drop_pending_updates=True,
                allowed_updates=["message", "edited_message", "callback_query", "my_chat_member", "message_reaction"]
            )
        finally:
            self.is_running = False
            await self.bot.session.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 bot_core.py <config_path>")
        sys.exit(1)
        
    async def main():
        # Читаем конфиг из JSON-файла, который создал server.py
        cfg_path = sys.argv[1]
        try:
            with open(cfg_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Инициализируем и запускаем
            instance = BotInstance(config)
            await instance.run_instance()
            
        except Exception as e:
            logger.error(f"FATAL ERROR: {e}")

    asyncio.run(main())
