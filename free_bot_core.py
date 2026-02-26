"""
free_bot_core.py — Ядро бесплатного бота.

Отличия от bot_core.py:
  • Нет AI, нет Flow-логики, нет топиков, нет VK
  • Максимум 3 кнопки и 2 триггера (остальные обрезаются)
  • Минимальный рейт-лимит 2с
  • Вместо copy_message — reply_message (send_message с текстом)
  • После /start показывает рекламный блок из БД (если есть активный)
  • Синхронизация с БД раз в 5 минут (меньше нагрузки)
  • Помечает себя как is_free=true в config
"""

import asyncio
import logging
import json
import httpx
import os
import sys
import hashlib
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any

from aiogram import Bot, Dispatcher, Router, F, BaseMiddleware
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove, CallbackQuery, ChatMemberUpdated
)
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter
from aiogram.filters import ChatMemberUpdatedFilter

from dotenv import load_dotenv
load_dotenv()

# ─── ЛОГИРОВАНИЕ ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("FreeBotCore")

# ─── ЛИМИТЫ БЕСПЛАТНОГО ПЛАНА ─────────────────────────────────────────────────
FREE_MAX_BUTTONS  = 3
FREE_MAX_TRIGGERS = 2
FREE_RATE_LIMIT   = 2.0   # секунды между сообщениями
FREE_SYNC_INTERVAL = 300  # 5 минут

# ─── ХЕЛПЕР ───────────────────────────────────────────────────────────────────
def get_anon_id(user_id: int) -> str:
    return hashlib.md5(str(user_id).encode()).hexdigest()[:6].upper()


# ─── MIDDLEWARE: БАН ───────────────────────────────────────────────────────────
class BanMiddleware(BaseMiddleware):
    def __init__(self, bot_instance):
        self.bot_instance = bot_instance
        super().__init__()

    async def __call__(self, handler, event, data):
        user_tg = getattr(event, 'from_user', None)
        if user_tg:
            user = next((u for u in self.bot_instance.users_list if u.get('id') == user_tg.id), None)
            if user and user.get("is_banned"):
                if isinstance(event, Message):
                    await event.answer("🚫 <b>Вы заблокированы в этом боте.</b>", parse_mode="HTML")
                return
        return await handler(event, data)


# ─── ОСНОВНОЙ КЛАСС ───────────────────────────────────────────────────────────
class FreeBotInstance:
    def __init__(self, config_data: dict):
        token = config_data.get('token', '')
        self.bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher()
        self.router = Router()

        self.bot_id   = config_data.get('id', 'unknown')
        self.sb_url   = os.getenv('SUPABASE_URL', '').rstrip('/')
        self.sb_key   = os.getenv('SUPABASE_KEY', '')
        self.srv_url  = os.getenv('SERVER_URL', 'http://localhost:8000')
        self.headers  = {
            "apikey": self.sb_key,
            "Authorization": f"Bearer {self.sb_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }

        self.users_list: List[dict] = []
        self.flood_cache: Dict[int, float] = {}
        self.msg_map: Dict[int, int] = {}  # admin_msg_id -> user_id
        self.is_running = True
        self.sync_queue = asyncio.Queue()

        self.config = config_data
        self._apply_config(config_data)

    # ── Применение конфига ─────────────────────────────────────────────────────
    def _apply_config(self, data: dict):
        raw_cfg = data.get('config', {}) if isinstance(data.get('config'), dict) else {}
        full    = {**data, **raw_cfg}

        admin_raw = full.get('admin_chat_id') or full.get('adminChatId')
        self.admin_chat_id = int(str(admin_raw).strip()) if admin_raw else None

        # Ограничиваем кнопки и триггеры
        all_btns  = full.get('buttons', [])[:FREE_MAX_BUTTONS]
        all_trigs = full.get('triggers', [])[:FREE_MAX_TRIGGERS]
        self.buttons      = [b for b in all_btns if b.get('text')]
        self.triggers     = all_trigs
        self.welcome_text = full.get('welcomeMessage', 'Привет!')

        rl = float(full.get('settings', {}).get('rateLimit', FREE_RATE_LIMIT))
        self.rate_limit = max(rl, FREE_RATE_LIMIT)  # не меньше 2с

        self.users_list           = full.get('connectedUsers', [])
        self.license_expires_at   = full.get('license_expires_at', 0)
        self.license_expired      = False

    # ── Антиспам ──────────────────────────────────────────────────────────────
    def _check_antispam(self, uid: int) -> bool:
        now = time.time()
        if now - self.flood_cache.get(uid, 0) < self.rate_limit:
            return True
        self.flood_cache[uid] = now
        return False

    # ── Главная клавиатура ─────────────────────────────────────────────────────
    def _main_keyboard(self):
        active = [b for b in self.buttons if b.get('text')]
        if not active:
            return ReplyKeyboardRemove()
        rows = []
        for i in range(0, len(active), 2):
            rows.append([KeyboardButton(text=b['text']) for b in active[i:i+2]])
        return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

    # ── Получить или создать состояние пользователя ────────────────────────────
    async def _get_user(self, m: Message):
        uid = m.from_user.id
        user = next((u for u in self.users_list if u['id'] == uid), None)
        is_new = False
        if not user:
            is_new = True
            user = {
                "id": uid,
                "first_name": m.from_user.first_name,
                "username": m.from_user.username,
                "is_banned": False,
                "joined_at": int(time.time()),
                "last_seen": int(time.time()),
            }
            self.users_list.append(user)
            await self.sync_queue.put(("sync_state", None))
        else:
            user["last_seen"] = int(time.time())
        return user, is_new

    # ── Получить активную рекламу из сервера ──────────────────────────────────
    async def _fetch_ad(self) -> Optional[dict]:
        """Возвращает {text, photo_url, campaign_id} или None."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(
                    f"{self.srv_url}/api/ads/active",
                    params={"bot_id": self.bot_id}
                )
                if r.status_code == 200:
                    data = r.json()
                    return data if data.get("campaign_id") else None
        except Exception as e:
            logger.warning(f"Ad fetch error: {e}")
        return None

    async def _record_impression(self, campaign_id: str, user_id: int):
        """Записывает показ и списывает с баланса рекламодателя."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f"{self.srv_url}/api/ads/impression",
                    json={
                        "campaign_id": campaign_id,
                        "bot_id": self.bot_id,
                        "user_id": user_id
                    }
                )
        except Exception as e:
            logger.warning(f"Ad impression record error: {e}")

    # ── Пересылка сообщения пользователя администратору ───────────────────────
    async def _forward_to_admin(self, m: Message, user: dict, is_first: bool = False, btn_text: str = ""):
        if not self.admin_chat_id:
            return

        uid = m.from_user.id
        name = m.from_user.full_name or "Пользователь"
        username = m.from_user.username

        header_parts = []
        if is_first:
            header_parts.append("🆕 <b>ПЕРВОЕ ОБРАЩЕНИЕ:</b>")
        elif btn_text:
            header_parts.append(f"🆘 <b>ЗАЯВКА [{btn_text}]:</b>")
        else:
            header_parts.append("📩 <b>СООБЩЕНИЕ:</b>")

        user_line = f"<b>{name}</b>"
        if username:
            user_line += f" (@{username})"
        user_line += f" | ID: <code>{uid}</code>"
        header_parts.append(user_line)
        header = "\n".join(header_parts) + "\n\n"

        try:
            if m.text:
                sent = await self.bot.send_message(
                    self.admin_chat_id,
                    f"{header}{m.text}"
                )
            elif m.photo:
                sent = await self.bot.send_photo(
                    self.admin_chat_id,
                    m.photo[-1].file_id,
                    caption=f"{header}{m.caption or ''}"
                )
            elif m.voice:
                sent = await self.bot.send_voice(
                    self.admin_chat_id,
                    m.voice.file_id,
                    caption=f"{header}{m.caption or ''}"
                )
            elif m.document:
                sent = await self.bot.send_document(
                    self.admin_chat_id,
                    m.document.file_id,
                    caption=f"{header}{m.caption or ''}"
                )
            else:
                # Для стикеров и прочего — просто текст с информацией
                sent = await self.bot.send_message(
                    self.admin_chat_id,
                    f"{header}[Медиа-сообщение]"
                )

            if sent:
                self.msg_map[sent.message_id] = uid
        except Exception as e:
            logger.error(f"Forward to admin error: {e}")

    # ── Ответ от администратора пользователю (REPLY MESSAGE) ──────────────────
    async def _reply_to_user(self, m: Message):
        """
        FREE-версия ответа на сообщение пользователя.
        Вместо copy_message использует send_message — только текст.
        Медиа-ответы недоступны на бесплатном плане.
        """
        target_id = None

        # Ищем пользователя по реплаю на пересланное сообщение
        if m.reply_to_message:
            target_id = self.msg_map.get(m.reply_to_message.message_id)

        if not target_id:
            return

        try:
            if m.text:
                await self.bot.send_message(target_id, m.text)
            elif m.caption:
                # Только подпись, без медиа
                await self.bot.send_message(target_id, m.caption)
            else:
                await m.reply("⚠️ <b>Бесплатный план:</b> медиа-ответы не поддерживаются. Отправьте текст.")
                return
        except TelegramForbiddenError:
            await m.reply("❌ Пользователь заблокировал бота.")
        except Exception as e:
            await m.reply(f"❌ Ошибка: {e}")

    # ── Сохранение в БД ────────────────────────────────────────────────────────
    async def _save_to_db(self):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.get(
                    f"{self.sb_url}/rest/v1/free_bots?id=eq.{self.bot_id}",
                    headers=self.headers
                )
                if res.status_code == 200 and res.json():
                    remote = res.json()[0]
                    remote_cfg = remote.get("config", {}) or {}
                    new_cfg = {
                        **remote_cfg,
                        "connectedUsers": self.users_list,
                        "buttons": self.buttons,
                        "triggers": self.triggers,
                        "welcomeMessage": self.welcome_text,
                    }
                    await client.patch(
                        f"{self.sb_url}/rest/v1/free_bots?id=eq.{self.bot_id}",
                        json={"config": new_cfg},
                        headers=self.headers
                    )
        except Exception as e:
            logger.error(f"DB save error: {e}")

    # ── Воркер синхронизации ────────────────────────────────────────────────────
    async def _sync_worker(self):
        while self.is_running:
            try:
                await asyncio.wait_for(self.sync_queue.get(), timeout=FREE_SYNC_INTERVAL)
                await self._save_to_db()
                self.sync_queue.task_done()
            except asyncio.TimeoutError:
                # Раз в 5 минут сохраняем принудительно
                await self._save_to_db()
            except Exception as e:
                logger.error(f"Sync worker error: {e}")
                try:
                    self.sync_queue.task_done()
                except Exception:
                    pass

    # ── Проверка лицензии (бесплатные боты не истекают, но проверяем статус) ──
    async def _license_checker(self):
        while self.is_running:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    r = await client.get(
                        f"{self.sb_url}/rest/v1/free_bots?id=eq.{self.bot_id}",
                        headers=self.headers
                    )
                    if r.status_code == 200 and r.json():
                        status = r.json()[0].get("status", "RUNNING")
                        if status == "BANNED":
                            logger.warning(f"Free bot {self.bot_id} banned, stopping.")
                            self.is_running = False
                            return
            except Exception:
                pass
            await asyncio.sleep(120)

    # ── Регистрация хендлеров ──────────────────────────────────────────────────
    async def _setup_handlers(self):
        self.router.message.middleware(BanMiddleware(self))

        # 1. /start — приветствие + реклама
        @self.router.message(CommandStart())
        async def handle_start(m: Message):
            user, is_new = await self._get_user(m)
            if user.get("is_banned"):
                await m.answer("🚫 <b>Вы заблокированы.</b>")
                return

            # Приветственное сообщение
            try:
                await m.answer(self.welcome_text, reply_markup=self._main_keyboard())
            except Exception as e:
                logger.warning(f"Start msg error: {e}")
                await m.answer(self.welcome_text)

            # 🎯 Показать рекламу после приветствия
            ad = await self._fetch_ad()
            if ad:
                ad_text = ad.get("text", "")
                ad_photo = ad.get("photo_url", "")
                campaign_id = ad.get("campaign_id")

                try:
                    if ad_photo:
                        await self.bot.send_photo(
                            m.chat.id,
                            photo=ad_photo,
                            caption=f"📢 <b>Реклама:</b>\n\n{ad_text}"
                        )
                    elif ad_text:
                        await self.bot.send_message(
                            m.chat.id,
                            f"📢 <b>Реклама:</b>\n\n{ad_text}"
                        )
                    if campaign_id:
                        asyncio.create_task(self._record_impression(campaign_id, m.from_user.id))
                except Exception as e:
                    logger.warning(f"Ad send error: {e}")

            if is_new:
                await self._forward_to_admin(m, user, is_first=True)

        # 2. Ответы от администратора
        @self.router.message(F.chat.id == self.admin_chat_id)
        async def handle_admin(m: Message):
            if m.text and m.text.startswith("/"):
                # Простые команды для бесплатного бота
                cmd = m.text.strip().lower()
                if cmd.startswith("/ban"):
                    parts = cmd.split()
                    if len(parts) > 1 and m.reply_to_message:
                        uid_from_map = self.msg_map.get(m.reply_to_message.message_id)
                        if uid_from_map:
                            target = next((u for u in self.users_list if u['id'] == uid_from_map), None)
                            if target:
                                target["is_banned"] = True
                                await self.sync_queue.put(("sync_state", None))
                                await m.reply(f"✅ Пользователь <code>{uid_from_map}</code> заблокирован.")
                    return
                elif cmd.startswith("/unban"):
                    if m.reply_to_message:
                        uid_from_map = self.msg_map.get(m.reply_to_message.message_id)
                        if uid_from_map:
                            target = next((u for u in self.users_list if u['id'] == uid_from_map), None)
                            if target:
                                target["is_banned"] = False
                                await self.sync_queue.put(("sync_state", None))
                                await m.reply(f"✅ Пользователь <code>{uid_from_map}</code> разблокирован.")
                    return
                return  # остальные команды игнорируем

            # Ответ пользователю (текстовый reply_message)
            await self._reply_to_user(m)

        # 3. Сообщения от пользователей
        @self.router.message()
        async def handle_user(m: Message):
            if self.admin_chat_id and m.chat.id == self.admin_chat_id:
                return

            user, is_new = await self._get_user(m)
            if user.get("is_banned"):
                await m.answer("🚫 <b>Вы заблокированы.</b>")
                return

            if self._check_antispam(user['id']):
                return

            if m.text:
                text = m.text.strip()

                # Кнопки
                matched = next(
                    (b for b in self.buttons if b.get('text', '').lower() == text.lower()),
                    None
                )
                if matched:
                    resp = matched.get('response', 'Принято!')
                    btn_type = matched.get('type', 'info')
                    if btn_type == 'request':
                        user['_in_ticket'] = True
                        await self._forward_to_admin(m, user, btn_text=text)
                        await m.answer(
                            resp or "Ваше обращение принято. Ожидайте ответа.",
                            reply_markup=ReplyKeyboardMarkup(
                                keyboard=[[KeyboardButton(text="Закрыть обращение")]],
                                resize_keyboard=True
                            )
                        )
                    else:
                        await m.answer(resp, reply_markup=self._main_keyboard())
                    return

                # Тикет открыт
                if user.get('_in_ticket'):
                    if text in ("Закрыть обращение",):
                        user.pop('_in_ticket', None)
                        await m.answer("Обращение закрыто.", reply_markup=self._main_keyboard())
                        return
                    await self._forward_to_admin(m, user)
                    return

                # Триггеры
                for trig in self.triggers:
                    kw = trig.get('keyword', '')
                    if kw and kw.lower() in text.lower():
                        await m.answer(trig.get('response', ''))
                        return

                if is_new:
                    await self._forward_to_admin(m, user, is_first=True)
                else:
                    await m.answer(
                        "Воспользуйтесь меню ниже.",
                        reply_markup=self._main_keyboard()
                    )
            else:
                # Медиа — форвардим если тикет открыт
                if user.get('_in_ticket'):
                    await self._forward_to_admin(m, user)
                elif is_new:
                    await self._forward_to_admin(m, user, is_first=True)

    # ── Запуск ─────────────────────────────────────────────────────────────────
    async def run_instance(self):
        logger.info(f"[FreeBotCore] Запускаю бот {self.bot_id}...")

        # Загружаем свежий конфиг из БД
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{self.sb_url}/rest/v1/free_bots?id=eq.{self.bot_id}",
                    headers=self.headers
                )
                if r.status_code == 200 and r.json():
                    data = r.json()[0]
                    cfg = data.get("config") or {}
                    self._apply_config({**data, "config": cfg})
                    logger.info(f"[FreeBotCore] Конфиг загружен: {len(self.buttons)} кнопок, {len(self.triggers)} триггеров")
        except Exception as e:
            logger.error(f"Config load error: {e}")

        asyncio.create_task(self._sync_worker())
        asyncio.create_task(self._license_checker())

        await self._setup_handlers()
        self.dp.include_router(self.router)

        logger.info(f"[FreeBotCore] Бот {self.bot_id} готов. Кнопок: {len(self.buttons)}/{FREE_MAX_BUTTONS}, "
                    f"Триггеров: {len(self.triggers)}/{FREE_MAX_TRIGGERS}")

        try:
            await self.dp.start_polling(self.bot)
        finally:
            self.is_running = False
            await self.bot.session.close()


# ─── ТОЧКА ВХОДА ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 free_bot_core.py <config_path>")
        sys.exit(1)

    async def main():
        cfg_path = sys.argv[1]
        with open(cfg_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        instance = FreeBotInstance(config)
        await instance.run_instance()

    asyncio.run(main())
