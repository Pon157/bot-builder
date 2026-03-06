"""
free_vk_bot_core.py
================================================================================
VK-бот для FREE-плана.

Функции (как в TG free-плане):
  ✅ Приветственное сообщение (/start → "start"/"начать") + фото + инлайн-кнопки
  ✅ Reply-кнопки (type: default, ticket)
  ✅ Триггеры (ключевые слова → ответ)
  ✅ Пересылка сообщений в беседу-администратора (forward_to_admin)
  ✅ Тикеты (создание, закрытие)
  ✅ Режим forwardAll (пересылать все сообщения)
  ✅ Антиспам (rateLimit)
  ✅ Модерация: /ban, /unban, /warn, /unwarn, /whois, /stats
  ✅ Рассылка: /broadcast (reply на сообщение)
  ✅ Синхронизация конфига каждые 30 сек
  ✅ Статистика (сохраняется в БД)
  ✅ inlineButtons в стартовом сообщении (тип url и message)
  ✅ Автопривязка peer_id при добавлении в беседу

НЕ поддерживается (Pro-only):
  ИИ-ассистент
  Flow-кнопки (сложные цепочки)
  Sandbox (выполнение кода)
  Топики (только для Telegram)
  Лицензионный чекер (free-план бессрочен)
================================================================================
"""

import asyncio
import logging
import json
import httpx
import os
import sys
import hashlib
import re
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from vkbottle import BaseMiddleware, Bot, CtxStorage
from vkbottle.bot import Message, MessageEvent
from vkbottle import Keyboard, KeyboardButtonColor, Text
try:
    from vkbottle import OpenLink as VKLink
except ImportError:
    VKLink = None
from vkbottle.exception_factory import VKAPIError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("FreeVKBotCore")


# ════════════════════════════════════════════════════════════════════════════════
# ХЕЛПЕРЫ
# ════════════════════════════════════════════════════════════════════════════════

def get_anon_id(user_id: int) -> str:
    return hashlib.md5(str(user_id).encode()).hexdigest()[:6].upper()


def format_admin_header(user: dict, settings: dict, is_first: bool = False, btn_text: str = "") -> str:
    is_anon = settings.get("anonymousTopics", False)
    uid     = user["id"]
    anon_tag = f"#{get_anon_id(uid)}"

    if is_anon:
        user_info = f"👤 Аноним {anon_tag}"
    else:
        parts = []
        if settings.get("showHeaderName", True):
            name = user.get("first_name", "Пользователь")
            parts.append(name)
        if settings.get("showHeaderUsername", True) and user.get("domain"):
            parts.append(f"(@{user['domain']})")
        if settings.get("showHeaderId", True):
            parts.append(f"ID: {uid}")
        user_info = " | ".join(parts) if parts else f"Юзер {anon_tag}"

    if btn_text:
        status_line = settings.get("ticketMessageHeader", "🆘 ЗАЯВКА")
        if "{btn}" in status_line:
            status_line = status_line.replace("{btn}", btn_text)
        else:
            status_line += f" [{btn_text}]:"
    elif is_first:
        status_line = settings.get("firstMessageHeader", "🆕 ПЕРВОЕ ОБРАЩЕНИЕ:")
    else:
        status_line = settings.get("commonMessageHeader", "📩 СООБЩЕНИЕ:")

    return f"{status_line}\n{user_info}\n⬇️⬇️⬇️"


# ════════════════════════════════════════════════════════════════════════════════
# MIDDLEWARE
# ════════════════════════════════════════════════════════════════════════════════

class BanMiddleware(BaseMiddleware[Message]):
    async def pre(self):
        bot_instance = getattr(self.event.ctx_api, "bot_instance_ref", None)
        if bot_instance is None:
            return
        user_id = self.event.from_id
        user = next((u for u in bot_instance.users_list if u.get("id") == user_id), None)
        if user and user.get("is_banned"):
            try:
                await self.event.answer("🚫 Вы заблокированы в этом боте.")
            except Exception:
                pass
            self.stop("User is banned")

    async def post(self):
        pass


# ════════════════════════════════════════════════════════════════════════════════
# ОСНОВНОЙ КЛАСС
# ════════════════════════════════════════════════════════════════════════════════

class FreeVKBotInstance:
    def __init__(self, config_data: dict):
        self.bot_id = config_data.get("id")
        self.token  = config_data.get("token")

        self.sb_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.sb_key = os.getenv("SUPABASE_KEY", "")
        self.headers = {
            "apikey":        self.sb_key,
            "Authorization": f"Bearer {self.sb_key}",
            "Content-Type":  "application/json",
            "Prefer":        "return=minimal",
        }

        self.bot = Bot(token=self.token)
        self.bot.api.bot_instance_ref = self

        self.msg_map:     Dict[int, int]   = {}
        self.flood_cache: Dict[int, float] = {}
        self.sync_queue:  asyncio.Queue    = asyncio.Queue()
        self.is_running   = True
        self._last_push:  float = 0.0

        self.users_list = []
        self.stats_data = {}

        self.apply_config(config_data, is_initial=True)

    # ─────────────────────────────────────────────────────────────────────────
    # КОНФИГ
    # ─────────────────────────────────────────────────────────────────────────

    def apply_config(self, data: dict, is_initial: bool = False):
        raw_cfg  = data.get("config", {}) if isinstance(data.get("config"), dict) else {}
        full_cfg = {**data, **raw_cfg}

        # admin_chat_id / vk_group_id
        peer_raw = (
            full_cfg.get("adminChatId") or full_cfg.get("vk_group_id") or
            full_cfg.get("vkGroupId")   or full_cfg.get("admin_chat_id") or
            data.get("vk_group_id")     or data.get("admin_chat_id")
        )
        try:
            self.admin_chat_id = int(str(peer_raw).strip()) if peer_raw else None
        except (ValueError, AttributeError):
            self.admin_chat_id = None

        self.settings       = full_cfg.get("settings", {})
        self.buttons        = full_cfg.get("buttons", [])
        self.triggers       = full_cfg.get("triggers", [])
        self.welcome_text   = full_cfg.get("welcomeMessage", "Здравствуйте!")
        self.welcome_photo  = full_cfg.get("welcomePhoto", "")
        # inlineButtons: новый формат [{id, text, type, value}], fallback — welcomeInline [{text,url}]
        self.inline_buttons = full_cfg.get("inlineButtons") or full_cfg.get("welcomeInline") or []

        self.rate_limit      = float(self.settings.get("rateLimit", 1.0))
        self.auto_ban_limit  = int(self.settings.get("autoBanThreshold", 3))
        self.forward_all     = bool(self.settings.get("forwardAll", False))
        # ad_enabled из корня данных бота (не из config)
        self.ad_enabled      = bool(data.get("ad_enabled", True))

        raw_admin_ids = full_cfg.get("adminIds") or full_cfg.get("admin_ids") or []
        try:
            self.admin_ids: List[int] = [int(x) for x in raw_admin_ids if str(x).strip().isdigit()]
        except Exception:
            self.admin_ids = []

        if is_initial or not hasattr(self, "users_list") or not self.users_list:
            self.users_list = full_cfg.get("connectedUsers", [])

        if is_initial:
            incoming_stats = full_cfg.get("stats")
            if isinstance(incoming_stats, dict) and incoming_stats:
                self.stats_data = {
                    "totalMessages":   incoming_stats.get("totalMessages", 0),
                    "incomingToday":   incoming_stats.get("incomingToday", 0),
                    "outgoingToday":   incoming_stats.get("outgoingToday", 0),
                    "bannedCount":     incoming_stats.get("bannedCount", 0),
                    "activeUsers24h":  incoming_stats.get("activeUsers24h", 0),
                    "broadcastsToday": incoming_stats.get("broadcastsToday", 0),
                    "broadcastsTotal": incoming_stats.get("broadcastsTotal", 0),
                    "history":         incoming_stats.get("history", []),
                }
            else:
                self.stats_data = {
                    "totalMessages": 0, "incomingToday": 0, "outgoingToday": 0,
                    "bannedCount": 0, "activeUsers24h": 0,
                    "broadcastsToday": 0, "broadcastsTotal": 0, "history": [],
                }
            if not self.stats_data["history"]:
                today = datetime.now().strftime("%d.%m")
                self.stats_data["history"] = [{
                    "date": today, "incoming": 0, "outgoing": 0,
                    "totalUsers": len(self.users_list), "activeUsers": 0
                }]

    # ─────────────────────────────────────────────────────────────────────────
    # КЛАВИАТУРЫ
    # ─────────────────────────────────────────────────────────────────────────

    def get_main_keyboard(self) -> str:
        active = [b for b in self.buttons if b.get("text")]
        if not active:
            return Keyboard().get_json()
        kb = Keyboard(one_time=False, inline=False)
        for i, btn in enumerate(active):
            if i % 2 == 0 and i != 0:
                kb.row()
            kb.add(Text(btn["text"]), color=KeyboardButtonColor.PRIMARY)
        return kb.get_json()

    def build_keyboard_from_buttons(self, buttons: list) -> str:
        active = [b for b in buttons if b.get("text")]
        if not active:
            return Keyboard().get_json()
        kb = Keyboard(one_time=True, inline=False)
        for i, btn in enumerate(active):
            if i % 2 == 0 and i != 0:
                kb.row()
            color = KeyboardButtonColor.NEGATIVE if btn["text"] in ("⬅️ Назад", "Закрыть обращение") else KeyboardButtonColor.PRIMARY
            kb.add(Text(btn["text"]), color=color)
        return kb.get_json()

    def build_welcome_inline_keyboard(self) -> Optional[str]:
        """
        Строит инлайн-клавиатуру из нового формата inlineButtons.
        Тип "url" → OpenLink (VKLink), тип "message" → Text reply-кнопка
        (VK не поддерживает callback с текстом как в TG, поэтому message-кнопки
        добавляются как обычные reply-кнопки отдельной клавиатурой).
        Возвращает (inline_kb_json, reply_extra_buttons) или (None, []).
        """
        # Используется в send_welcome_message ниже
        pass

    # ─────────────────────────────────────────────────────────────────────────
    # ОТПРАВКА СТАРТОВОГО СООБЩЕНИЯ
    # ─────────────────────────────────────────────────────────────────────────

    async def send_welcome_message(self, user: dict):
        """
        Отправляет приветственное сообщение пользователю.
        Поддерживает: текст, фото, inlineButtons (url → OpenLink, message → reply-кнопки).
        """
        uid = user["id"]

        # Загружаем фото если есть
        attachment_str = None
        if self.welcome_photo:
            try:
                upload_server = await self.bot.api.photos.get_messages_upload_server(peer_id=uid)
                async with httpx.AsyncClient(timeout=15) as hclient:
                    img_resp    = await hclient.get(self.welcome_photo)
                    upload_resp = await hclient.post(
                        upload_server.upload_url,
                        files={"photo": ("photo.jpg", img_resp.content, "image/jpeg")}
                    )
                    uploaded = upload_resp.json()
                saved = await self.bot.api.photos.save_messages_photo(
                    photo=uploaded["photo"], server=uploaded["server"], hash=uploaded["hash"]
                )
                if saved:
                    p = saved[0]
                    attachment_str = f"photo{p.owner_id}_{p.id}"
            except Exception as e:
                logger.warning(f"VK free welcome photo upload error: {e}")

        # Разбираем inlineButtons на url-кнопки и message-кнопки
        url_buttons     = []
        message_buttons = []
        for btn in (self.inline_buttons or []):
            text  = btn.get("text", "").strip()
            btype = btn.get("type", "url")
            value = btn.get("value", "") or btn.get("url", "")
            if not text:
                continue
            if btype == "url" and value:
                url_buttons.append({"text": text, "url": value})
            elif btype == "message" and value:
                message_buttons.append({"text": value})  # при нажатии отправят этот текст

        # Строим инлайн-клавиатуру из url-кнопок (VKLink)
        inline_kb_json = None
        if url_buttons and VKLink is not None:
            try:
                kb = Keyboard(inline=True)
                for i, btn in enumerate(url_buttons):
                    if i > 0:
                        kb.row()
                    url = btn["url"]
                    if not url.startswith(("http://", "https://")):
                        url = "https://" + url
                    kb.add(VKLink(url, btn["text"]))
                inline_kb_json = kb.get_json()
            except Exception as e:
                logger.warning(f"VK welcome inline keyboard error: {e}")

        # Если нет VKLink — добавим url-кнопки к message-кнопкам как текстовые
        if url_buttons and VKLink is None:
            for btn in url_buttons:
                message_buttons.append({"text": f"🔗 {btn['text']}: {btn['url']}"})

        # Клавиатура для первого сообщения
        # Если есть url-инлайн → отправляем с инлайн-кб, потом reply-кб отдельно
        # Если только message-кнопки → они добавятся в reply-кб вместе с основными
        reply_kb_buttons = list(self.buttons)  # основные кнопки
        if message_buttons:
            reply_kb_buttons = list(message_buttons) + reply_kb_buttons

        if reply_kb_buttons:
            # Строим reply-клавиатуру
            all_active = [b for b in reply_kb_buttons if b.get("text")]
            if all_active:
                kb_reply = Keyboard(one_time=False, inline=False)
                for i, btn in enumerate(all_active):
                    if i % 2 == 0 and i != 0:
                        kb_reply.row()
                    kb_reply.add(Text(btn["text"]), color=KeyboardButtonColor.PRIMARY)
                reply_kb_json = kb_reply.get_json()
            else:
                reply_kb_json = self.get_main_keyboard()
        else:
            reply_kb_json = self.get_main_keyboard()

        # Отправляем сообщение
        if inline_kb_json:
            # Сначала стартовое сообщение с инлайн URL-кнопками
            await self.bot.api.messages.send(
                peer_id=uid,
                message=self.welcome_text,
                attachment=attachment_str,
                keyboard=inline_kb_json,
                random_id=0
            )
            # Затем reply-клавиатура (обычные кнопки)
            try:
                await self.bot.api.messages.send(
                    peer_id=uid,
                    message="👇 Выберите действие:",
                    keyboard=reply_kb_json,
                    random_id=0
                )
            except Exception:
                pass
        else:
            # Всё в одном сообщении
            await self.bot.api.messages.send(
                peer_id=uid,
                message=self.welcome_text,
                attachment=attachment_str,
                keyboard=reply_kb_json,
                random_id=0
            )

        # Реклама после приветствия (free-план)
        await self.send_ad_to_user(uid)

    # ─────────────────────────────────────────────────────────────────────────
    # РЕКЛАМА (FREE PLAN)
    # ─────────────────────────────────────────────────────────────────────────

    async def fetch_ad(self) -> Optional[dict]:
        """Получить актуальное рекламное объявление через API."""
        try:
            import httpx as _httpx
            import os as _os
            base_url = _os.getenv("SERVER_BASE_URL", "http://localhost:8000")
            async with _httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{base_url}/api/ads/active", params={"bot_id": self.bot_id})
                if r.status_code == 200:
                    return r.json().get("ad")
        except Exception as e:
            logger.warning(f"[FREE VK] fetch_ad error: {e}")
        return None

    async def send_ad_to_user(self, uid: int):
        """Отправить рекламное сообщение пользователю."""
        if not self.ad_enabled:
            return
        try:
            ad = await self.fetch_ad()
            if not ad or not ad.get("text"):
                return
            await self.bot.api.messages.send(
                peer_id=uid,
                message=f"📢 Реклама:\n{ad['text']}",
                random_id=0
            )
        except Exception as e:
            logger.warning(f"[FREE VK] send_ad_to_user error: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # СОСТОЯНИЕ ПОЛЬЗОВАТЕЛЯ
    # ─────────────────────────────────────────────────────────────────────────

    async def get_user_state(self, m: Message):
        uid = m.from_id
        user = next((u for u in self.users_list if u["id"] == uid), None)
        is_first = False

        try:
            user_info  = (await self.bot.api.users.get(user_ids=[uid]))[0]
            full_name  = f"{user_info.first_name} {user_info.last_name}".strip()
            domain     = getattr(user_info, "domain", "") or ""
        except Exception:
            full_name  = f"User{uid}"
            domain     = ""

        if not user:
            is_first = True
            user = {
                "id":         uid,
                "first_name": full_name,
                "username":   domain,
                "domain":     domain,
                "is_banned":  False,
                "is_active":  True,
                "warns":      0,
                "joined_at":  int(time.time()),
                "last_seen":  int(time.time()),
            }
            self.users_list.append(user)
            await self.sync_queue.put(("sync_state", None))
        else:
            user["last_seen"]  = int(time.time())
            user["first_name"] = full_name or user.get("first_name", "")
            user["domain"]     = domain or user.get("domain", "")
            user["username"]   = domain or user.get("username", "")
            if not user.get("is_active", True):
                user["is_active"] = True
                await self.sync_queue.put(("sync_state", None))

        return user, is_first

    # ─────────────────────────────────────────────────────────────────────────
    # АНТИСПАМ
    # ─────────────────────────────────────────────────────────────────────────

    async def check_antispam(self, user_id: int) -> bool:
        if self.rate_limit <= 0:
            return False
        now = time.time()
        if now - self.flood_cache.get(user_id, 0) < self.rate_limit:
            return True
        self.flood_cache[user_id] = now
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # ФОРВАРД АДМИНУ
    # ─────────────────────────────────────────────────────────────────────────

    async def forward_to_admin(self, m: Message, user: dict, is_first: bool = False, btn_text: str = ""):
        if not self.admin_chat_id:
            return

        header    = format_admin_header(user, self.settings, is_first, btn_text)
        user_text = m.text or ""
        full_text = (f"{header}\n{user_text}".strip()) if user_text else header

        try:
            attachment_str = None
            if m.attachments:
                parts = []
                for att in m.attachments:
                    try:
                        att_type = str(att.type.value) if hasattr(att.type, "value") else str(att.type)
                        att_obj  = getattr(att, att_type, None)
                        if att_obj:
                            owner = getattr(att_obj, "owner_id", None)
                            aid   = getattr(att_obj, "id", None)
                            if owner and aid:
                                parts.append(f"{att_type}{owner}_{aid}")
                    except Exception:
                        pass
                if parts:
                    attachment_str = ",".join(parts)

            sent_msg_id = await self.bot.api.messages.send(
                peer_id=self.admin_chat_id,
                message=full_text,
                attachment=attachment_str,
                random_id=0
            )
            self.msg_map[sent_msg_id] = user["id"]
        except Exception as e:
            logger.error(f"forward_to_admin error: {e}", exc_info=True)

    # ─────────────────────────────────────────────────────────────────────────
    # СТАТИСТИКА
    # ─────────────────────────────────────────────────────────────────────────

    async def log_and_update(self, uid: int, name: str, text: str, is_admin: bool = False):
        self.stats_data["totalMessages"] = self.stats_data.get("totalMessages", 0) + 1
        key = "outgoingToday" if is_admin else "incomingToday"
        self.stats_data[key] = self.stats_data.get(key, 0) + 1

        if not is_admin:
            for u in self.users_list:
                if u["id"] == uid:
                    u["last_seen"]  = int(time.time())
                    u["first_name"] = name
                    break

        await self.sync_queue.put(("log_message", {
            "bot_id":        self.bot_id,
            "user_id":       uid,
            "first_name":    name,
            "message_text":  text[:950] if text else "[Медиа]",
            "is_from_admin": is_admin,
        }))
        await self.sync_queue.put(("sync_state", None))

    # ─────────────────────────────────────────────────────────────────────────
    # БД: WORKER + ЗАГРУЗКА
    # ─────────────────────────────────────────────────────────────────────────

    async def sync_database_logic(self):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(
                    f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                    headers=self.headers
                )
                if res.status_code == 200 and res.json():
                    row = res.json()[0]
                    remote_cfg = row.get("config") or {}
                    if isinstance(remote_cfg, str):
                        try:
                            remote_cfg = json.loads(remote_cfg)
                        except Exception:
                            remote_cfg = {}
                    self.apply_config({**row, "config": remote_cfg})

                    # Сбрасываем тикеты при рестарте
                    for u in self.users_list:
                        u.pop("_in_ticket", None)
                        u.pop("_ticket_close_label", None)

                    logger.info(
                        f"✅ [FREE VK] [{self.bot_id}] Конфиг загружен: "
                        f"кнопок={len(self.buttons)}, триггеров={len(self.triggers)}, "
                        f"users={len(self.users_list)}, "
                        f"admin_chat={self.admin_chat_id}, "
                        f"forwardAll={self.forward_all}, "
                        f"inlineButtons={len(self.inline_buttons)}"
                    )
        except Exception as e:
            logger.error(f"sync_database_logic FreeVK error: {e}")

    async def database_sync_worker(self):
        async with httpx.AsyncClient(timeout=10.0) as client:
            while self.is_running:
                try:
                    item = await asyncio.wait_for(self.sync_queue.get(), timeout=1.0)
                    if not isinstance(item, tuple):
                        self.sync_queue.task_done()
                        continue

                    action, payload = item

                    if action == "log_message":
                        try:
                            await client.post(
                                f"{self.sb_url}/rest/v1/bot_messages",
                                json=payload,
                                headers=self.headers
                            )
                        except Exception:
                            pass

                    elif action == "sync_state":
                        try:
                            res = await client.get(
                                f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                                headers=self.headers
                            )
                            if res.status_code == 200 and res.json():
                                remote_data   = res.json()[0]
                                remote_config = remote_data.get("config", {}) or {}

                                new_config = {
                                    **remote_config,
                                    "connectedUsers": self.users_list,
                                    "stats":          self.stats_data,
                                    "adminChatId":    self.admin_chat_id,
                                    "vk_group_id":    self.admin_chat_id,
                                    "vkGroupId":      self.admin_chat_id,
                                }
                                await client.patch(
                                    f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                                    json={"config": new_config},
                                    headers=self.headers
                                )

                                # Горячая перезагрузка конфига (кнопки/настройки)
                                saved_users = self.users_list
                                saved_stats = self.stats_data
                                self.apply_config({**remote_data, "config": remote_config}, is_initial=False)
                                self.users_list = saved_users
                                self.stats_data = saved_stats
                        except Exception as e:
                            logger.error(f"FreeVK sync_state error: {e}")

                    self.sync_queue.task_done()

                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"FreeVK SyncWorker error: {e}")
                    try:
                        self.sync_queue.task_done()
                    except Exception:
                        pass

    async def _save_to_db(self):
        await self.sync_queue.put(("sync_state", None))

    # ─────────────────────────────────────────────────────────────────────────
    # РОТАТОР СТАТИСТИКИ
    # ─────────────────────────────────────────────────────────────────────────

    async def daily_stats_rotator(self):
        while self.is_running:
            try:
                now          = datetime.now()
                current_date = now.strftime("%d.%m")
                day_ago      = int((now - timedelta(days=1)).timestamp())
                active_count = sum(1 for u in self.users_list if u.get("last_seen", 0) > day_ago)
                self.stats_data["activeUsers24h"] = active_count

                history = self.stats_data.setdefault("history", [])
                if not history:
                    history.append({
                        "date": current_date, "incoming": 0, "outgoing": 0,
                        "totalUsers": len(self.users_list), "activeUsers": active_count,
                    })

                if history[-1]["date"] != current_date:
                    history[-1].update({
                        "incoming":    self.stats_data.get("incomingToday", 0),
                        "outgoing":    self.stats_data.get("outgoingToday", 0),
                        "totalUsers":  len(self.users_list),
                        "activeUsers": active_count,
                    })
                    self.stats_data["incomingToday"] = 0
                    self.stats_data["outgoingToday"] = 0
                    history.append({
                        "date": current_date, "incoming": 0, "outgoing": 0,
                        "totalUsers": len(self.users_list), "activeUsers": active_count,
                    })
                    self.stats_data["history"] = history[-14:]

                history[-1].update({
                    "incoming":    self.stats_data.get("incomingToday", 0),
                    "outgoing":    self.stats_data.get("outgoingToday", 0),
                    "totalUsers":  len(self.users_list),
                    "activeUsers": active_count,
                })

                await self.sync_queue.put(("sync_state", None))
            except Exception as e:
                logger.error(f"FreeVK Rotator error: {e}")
            await asyncio.sleep(60)

    # ─────────────────────────────────────────────────────────────────────────
    # МОДЕРАЦИЯ
    # ─────────────────────────────────────────────────────────────────────────

    def is_admin(self, user_id: int) -> bool:
        if not self.admin_ids:
            return True
        return user_id in self.admin_ids

    async def admin_control_logic(self, m: Message) -> bool:
        if not m.text or not (m.text.startswith("/") or m.text.startswith("!")):
            return False

        # /getid — без проверки прав
        if m.text.strip().lower() in ["/getid", "!getid"]:
            await self.bot.api.messages.send(
                peer_id=m.peer_id,
                message=(
                    f"ℹ️ Информация о беседе:\n\n"
                    f"📌 peer_id беседы: {m.peer_id}\n"
                    f"👤 Ваш VK ID: {m.from_id}\n"
                    f"🤖 admin_chat_id бота: {self.admin_chat_id}\n"
                    f"🛡 admin_ids: {self.admin_ids or 'не задан (все в беседе)'}"
                ),
                random_id=0
            )
            return True

        if not self.is_admin(m.from_id):
            return False

        cmd_parts = m.text.lower().split()
        command   = cmd_parts[0][1:]

        # /stats
        if command == "stats":
            total  = len(self.users_list)
            banned = sum(1 for u in self.users_list if u.get("is_banned"))
            active = sum(1 for u in self.users_list if u.get("is_active", True) and not u.get("is_banned"))
            await self.bot.api.messages.send(
                peer_id=self.admin_chat_id,
                message=(
                    f"📊 Статистика бота:\n\n"
                    f"👥 Всего пользователей: {total}\n"
                    f"✅ Активных: {active}\n"
                    f"🚫 Заблокировано: {banned}\n"
                    f"📢 Сообщений сегодня: {self.stats_data.get('incomingToday', 0)}"
                ),
                random_id=0
            )
            return True

        # /broadcast
        elif command == "broadcast":
            if m.reply_message and m.reply_message.text:
                broadcast_text = m.reply_message.text
                sent_c, err_c  = 0, 0
                await self.bot.api.messages.send(
                    peer_id=self.admin_chat_id, message="🚀 Запускаю рассылку...", random_id=0
                )
                for user in list(self.users_list):
                    if user.get("is_banned") or not user.get("is_active", True):
                        continue
                    try:
                        await self.bot.api.messages.send(
                            peer_id=int(user["id"]), message=broadcast_text, random_id=0
                        )
                        sent_c += 1
                        await asyncio.sleep(0.05)
                    except Exception:
                        err_c += 1
                        user["is_active"] = False
                await self.bot.api.messages.send(
                    peer_id=self.admin_chat_id,
                    message=f"✅ Рассылка завершена!\n\n👤 Доставлено: {sent_c}\n🚫 Ошибки: {err_c}",
                    random_id=0
                )
                await self._save_to_db()
                return True
            else:
                await self.bot.api.messages.send(
                    peer_id=self.admin_chat_id,
                    message="📢 Ответьте командой /broadcast на сообщение, которое хотите разослать.",
                    random_id=0
                )
                return True

        # Команды модерации — ищем target_user
        target_user = None

        # Реплай на сообщение
        if m.reply_message:
            uid = self.msg_map.get(m.reply_message.id)
            if uid:
                target_user = next((u for u in self.users_list if u["id"] == uid), None)
            if not target_user:
                reply_text = m.reply_message.text or ""
                id_match = re.search(r"ID:\s*(\d+)", reply_text)
                if id_match:
                    try:
                        parsed_id = int(id_match.group(1))
                        target_user = next((u for u in self.users_list if u["id"] == parsed_id), None)
                    except ValueError:
                        pass

        # ID явно
        if not target_user and len(cmd_parts) > 1:
            try:
                manual_id = int(cmd_parts[1])
                target_user = next((u for u in self.users_list if u["id"] == manual_id), None)
                if not target_user and command in ("ban", "unban"):
                    target_user = {
                        "id": manual_id, "first_name": f"User#{manual_id}",
                        "username": None, "is_banned": False, "warns": 0,
                        "joined_at": int(time.time()), "last_seen": int(time.time()),
                    }
                    self.users_list.append(target_user)
            except Exception:
                pass

        if not target_user:
            return False

        uid       = target_user["id"]
        ban_limit = self.settings.get("autoBanThreshold", 3)

        if command == "whois":
            uname     = target_user.get("domain") or target_user.get("username")
            name_line = target_user.get("first_name", "—")
            if uname:
                name_line += f" (@{uname})"
            joined    = datetime.fromtimestamp(target_user.get("joined_at", 0)).strftime("%d.%m.%Y %H:%M") if target_user.get("joined_at") else "—"
            last_seen = datetime.fromtimestamp(target_user.get("last_seen", 0)).strftime("%d.%m.%Y %H:%M") if target_user.get("last_seen") else "—"
            await self.bot.api.messages.send(
                peer_id=self.admin_chat_id,
                message=(
                    f"🔍 Пользователь {uid}:\n\n"
                    f"Имя: {name_line}\n"
                    f"Забанен: {'Да' if target_user.get('is_banned') else 'Нет'}\n"
                    f"Варнов: {target_user.get('warns', 0)}\n"
                    f"Зашёл: {joined}\n"
                    f"Активность: {last_seen}"
                ),
                random_id=0
            )
            return True

        elif command == "ban":
            target_user["is_banned"] = True
            self.stats_data["bannedCount"] = self.stats_data.get("bannedCount", 0) + 1
            await self._save_to_db()
            try:
                await self.bot.api.messages.send(
                    peer_id=uid, message="🚫 Доступ ограничен администратором.", random_id=0
                )
            except Exception:
                pass
            await self.bot.api.messages.send(
                peer_id=self.admin_chat_id,
                message=f"✅ Пользователь {uid} заблокирован.", random_id=0
            )
            return True

        elif command == "unban":
            target_user["is_banned"] = False
            target_user["warns"]     = 0
            self.stats_data["bannedCount"] = max(0, self.stats_data.get("bannedCount", 1) - 1)
            await self._save_to_db()
            try:
                await self.bot.api.messages.send(
                    peer_id=uid, message="✅ Ваш доступ восстановлен.", random_id=0
                )
            except Exception:
                pass
            await self.bot.api.messages.send(
                peer_id=self.admin_chat_id,
                message=f"✅ Пользователь {uid} разблокирован.", random_id=0
            )
            return True

        elif command == "warn":
            target_user["warns"] = target_user.get("warns", 0) + 1
            if ban_limit > 0 and target_user["warns"] >= ban_limit:
                target_user["is_banned"] = True
                self.stats_data["bannedCount"] = self.stats_data.get("bannedCount", 0) + 1
                msg   = f"🚨 АВТО-БАН! {uid}. Варнов: {target_user['warns']}/{ban_limit}"
                notif = f"🚫 Авто-бан: лимит предупреждений ({target_user['warns']}/{ban_limit}) исчерпан."
            else:
                msg   = f"⚠️ Варн {uid}. Всего: {target_user['warns']}/{ban_limit or '∞'}"
                notif = f"⚠️ Предупреждение! ({target_user['warns']}/{ban_limit or '∞'})"
            await self._save_to_db()
            try:
                await self.bot.api.messages.send(peer_id=uid, message=notif, random_id=0)
            except Exception:
                pass
            await self.bot.api.messages.send(
                peer_id=self.admin_chat_id, message=msg, random_id=0
            )
            return True

        elif command == "unwarn":
            target_user["warns"] = max(0, target_user.get("warns", 0) - 1)
            await self._save_to_db()
            await self.bot.api.messages.send(
                peer_id=self.admin_chat_id,
                message=f"✅ Варн снят. У {uid}: {target_user['warns']}",
                random_id=0
            )
            return True

        return False

    # ─────────────────────────────────────────────────────────────────────────
    # АВТОПРИВЯЗКА peer_id
    # ─────────────────────────────────────────────────────────────────────────

    async def bind_peer_id(self, peer_id: int, invited_by: Optional[int] = None):
        if not peer_id or peer_id <= 2_000_000_000:
            return
        if self.admin_chat_id and self.admin_chat_id == peer_id:
            return

        self.admin_chat_id = peer_id

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(
                    f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                    headers=self.headers
                )
                if res.status_code == 200 and res.json():
                    remote_cfg = res.json()[0].get("config", {}) or {}
                    new_cfg    = {
                        **remote_cfg,
                        "adminChatId":  peer_id,
                        "vk_group_id":  peer_id,
                        "vkGroupId":    peer_id,
                    }
                    await client.patch(
                        f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                        json={"config": new_cfg},
                        headers=self.headers
                    )
            logger.info(f"✅ [FREE VK] [{self.bot_id}] peer_id={peer_id} сохранён в БД")
        except Exception as e:
            logger.error(f"❌ FreeVK bind_peer_id error: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # РЕГИСТРАЦИЯ HANDLERS
    # ─────────────────────────────────────────────────────────────────────────

    async def core_handlers_setup(self):
        self.bot.labeler.message_view.register_middleware(BanMiddleware)

        # ── 1. Бот приглашён в беседу → автопривязка ─────────────────────────
        @self.bot.on.message(func=lambda m: (
            m.action is not None and
            m.action.type is not None and
            "invite" in str(m.action.type).lower()
        ))
        async def handle_chat_invite(m: Message):
            if m.peer_id and m.peer_id > 2_000_000_000:
                await self.bind_peer_id(m.peer_id, invited_by=m.from_id)
                try:
                    await self.bot.api.messages.send(
                        peer_id=m.peer_id,
                        message=f"✅ Free VK-бот подключён! Сообщения пользователей будут пересылаться сюда.\nID беседы: {m.peer_id}",
                        random_id=0
                    )
                except Exception:
                    pass

        # ── 2. Сообщения из беседы-администратора ───────────────────────────
        @self.bot.on.message(func=lambda m: (
            self.admin_chat_id is not None and
            m.peer_id == self.admin_chat_id
        ))
        async def handle_admin_message(m: Message):
            # Команды
            if m.text and (m.text.startswith("/") or m.text.startswith("!")):
                handled = await self.admin_control_logic(m)
                if handled:
                    return

            # Reply → ответ пользователю
            if m.reply_message is not None:
                target_id = self.msg_map.get(m.reply_message.id)
                if not target_id:
                    reply_text = m.reply_message.text or ""
                    id_match   = re.search(r"ID:\s*(\d+)", reply_text)
                    if id_match:
                        try:
                            target_id = int(id_match.group(1))
                        except ValueError:
                            pass

                if target_id:
                    try:
                        attachment_str = None
                        if m.attachments:
                            parts = []
                            for att in m.attachments:
                                try:
                                    att_type = str(att.type.value) if hasattr(att.type, "value") else str(att.type)
                                    att_obj  = getattr(att, att_type, None)
                                    if att_obj:
                                        owner = getattr(att_obj, "owner_id", None)
                                        aid   = getattr(att_obj, "id", None)
                                        if owner and aid:
                                            parts.append(f"{att_type}{owner}_{aid}")
                                except Exception:
                                    pass
                            if parts:
                                attachment_str = ",".join(parts)

                        reply_text = m.text or ""
                        if reply_text or attachment_str:
                            await self.bot.api.messages.send(
                                peer_id=target_id,
                                message=reply_text,
                                attachment=attachment_str,
                                random_id=0
                            )
                            await self.log_and_update(target_id, "Admin", reply_text or "[Медиа]", is_admin=True)
                    except VKAPIError[901]:
                        await self.bot.api.messages.send(
                            peer_id=self.admin_chat_id,
                            message="❌ Пользователь запретил сообщения от бота.",
                            random_id=0
                        )
                        user = next((u for u in self.users_list if u["id"] == target_id), None)
                        if user:
                            user["is_active"] = False
                            await self.sync_queue.put(("sync_state", None))
                    except Exception as e:
                        try:
                            await self.bot.api.messages.send(
                                peer_id=self.admin_chat_id,
                                message=f"❌ Ошибка отправки: {e}",
                                random_id=0
                            )
                        except Exception:
                            pass
                else:
                    await self.bot.api.messages.send(
                        peer_id=self.admin_chat_id,
                        message="⚠️ Не могу найти получателя. Ответь на более свежее сообщение.",
                        random_id=0
                    )

        # ── 3. Все сообщения от пользователей ────────────────────────────────
        @self.bot.on.message()
        async def handle_user_message(m: Message):
            # Пропускаем сообщения из admin_chat
            if self.admin_chat_id and m.peer_id == self.admin_chat_id:
                return

            user, is_new = await self.get_user_state(m)

            if user.get("is_banned"):
                try:
                    await self.bot.api.messages.send(
                        peer_id=user["id"], message="🚫 Вы заблокированы в этом боте.", random_id=0
                    )
                except Exception:
                    pass
                return

            if await self.check_antispam(user["id"]):
                return

            # ── Активный тикет ───────────────────────────────────────────────
            if user.get("_in_ticket"):
                close_label = user.get("_ticket_close_label", "Закрыть обращение")
                if m.text and m.text.strip() in (close_label, "Закрыть обращение"):
                    user.pop("_in_ticket", None)
                    user.pop("_ticket_close_label", None)
                    await self.sync_queue.put(("sync_state", None))
                    if self.admin_chat_id:
                        try:
                            name_line = user.get("first_name", str(user["id"]))
                            domain    = user.get("domain") or user.get("username")
                            if domain:
                                name_line += f" (@{domain})"
                            name_line += f" | ID: {user['id']}"
                            await self.bot.api.messages.send(
                                peer_id=self.admin_chat_id,
                                message=f"Обращение закрыто пользователем.\n{name_line}",
                                random_id=0
                            )
                        except Exception:
                            pass
                    await self.bot.api.messages.send(
                        peer_id=user["id"],
                        message="Обращение закрыто.",
                        keyboard=self.get_main_keyboard(),
                        random_id=0
                    )
                    return

                await self.forward_to_admin(m, user)
                await self.log_and_update(user["id"], user["first_name"], m.text or "[Медиа]")
                # Снова показываем кнопку "Закрыть обращение" — она пропадает после каждого ответа
                try:
                    close_kb = self.build_keyboard_from_buttons([{"text": "Закрыть обращение"}])
                    await self.bot.api.messages.send(
                        peer_id=user["id"],
                        message="✅ Оператор получил ваше сообщение.",
                        keyboard=close_kb,
                        random_id=0
                    )
                except Exception:
                    pass
                return

            if m.text:
                clean = m.text.strip()
                lower = clean.lower()

                # ── Кнопка «Назад» ───────────────────────────────────────────
                if clean in ("⬅️ Назад", "Назад"):
                    await self.bot.api.messages.send(
                        peer_id=user["id"],
                        message="Главное меню:",
                        keyboard=self.get_main_keyboard(),
                        random_id=0
                    )
                    return

                # ── START ─────────────────────────────────────────────────────
                if lower in ["start", "/start", "начать"]:
                    await self.send_welcome_message(user)
                    await self.log_and_update(user["id"], user["first_name"], "/start")
                    return

                # ── message-кнопки инлайна — текст который пользователь прислал
                # при нажатии на кнопку типа "message" (текст кнопки = value)
                inline_msg_btn = next(
                    (b for b in self.inline_buttons
                     if b.get("type") == "message" and b.get("value", "").strip().lower() == lower),
                    None
                )
                if inline_msg_btn:
                    # Ищем совпадение с обычными кнопками по тексту value
                    value = inline_msg_btn.get("value", "")
                    matched_btn = next(
                        (b for b in self.buttons if b.get("text", "").strip().lower() == value.lower()),
                        None
                    )
                    if matched_btn:
                        resp = matched_btn.get("response", "") or "✅"
                        await self.bot.api.messages.send(
                            peer_id=user["id"], message=resp,
                            keyboard=self.get_main_keyboard(), random_id=0
                        )
                    else:
                        await self.forward_to_admin(m, user)
                        if not self.forward_all and not is_new:
                            await self.bot.api.messages.send(
                                peer_id=user["id"], message="✅", random_id=0
                            )
                    await self.log_and_update(user["id"], user["first_name"], f"ИНЛАЙН: {value}")
                    return

                # ── Reply-кнопки ─────────────────────────────────────────────
                matched_btn = next(
                    (b for b in self.buttons if b.get("text", "").strip().lower() == lower),
                    None
                )
                if matched_btn:
                    btn_type = matched_btn.get("type", "default")

                    if btn_type == "ticket":
                        user["_in_ticket"]          = True
                        user["_ticket_close_label"] = "Закрыть обращение"
                        await self.forward_to_admin(m, user, btn_text=matched_btn["text"])
                        resp     = matched_btn.get("response") or "Ваше обращение принято. Ожидайте ответа оператора."
                        close_kb = self.build_keyboard_from_buttons([{"text": "Закрыть обращение"}])
                        await self.bot.api.messages.send(
                            peer_id=user["id"],
                            message=f"{resp}\n\nВы можете продолжать писать — сообщения будут доставлены оператору.",
                            keyboard=close_kb,
                            random_id=0
                        )
                        await self.sync_queue.put(("sync_state", None))
                    else:
                        resp = matched_btn.get("response", "") or "✅"
                        # Инлайн URL-кнопки внутри ответа кнопки
                        btn_inline = [b for b in matched_btn.get("inline", []) if b.get("text") and b.get("url")]
                        if btn_inline and VKLink is not None:
                            try:
                                kb_inline = Keyboard(inline=True)
                                for i, ib in enumerate(btn_inline):
                                    if i > 0:
                                        kb_inline.row()
                                    url = ib["url"] if ib["url"].startswith(("http://", "https://")) else "https://" + ib["url"]
                                    kb_inline.add(VKLink(url, ib["text"]))
                                await self.bot.api.messages.send(
                                    peer_id=user["id"], message=resp,
                                    keyboard=kb_inline.get_json(), random_id=0
                                )
                                await self.bot.api.messages.send(
                                    peer_id=user["id"], message="👇",
                                    keyboard=self.get_main_keyboard(), random_id=0
                                )
                            except Exception:
                                await self.bot.api.messages.send(
                                    peer_id=user["id"], message=resp,
                                    keyboard=self.get_main_keyboard(), random_id=0
                                )
                        else:
                            await self.bot.api.messages.send(
                                peer_id=user["id"], message=resp,
                                keyboard=self.get_main_keyboard(), random_id=0
                            )

                    await self.log_and_update(user["id"], user["first_name"], f"КНОПКА: {matched_btn['text']}")
                    return

                # ── Триггеры ─────────────────────────────────────────────────
                for trig in self.triggers:
                    kw = trig.get("keyword", "").strip()
                    if kw and kw.lower() in lower:
                        resp = trig.get("response") or "✅"
                        await self.bot.api.messages.send(
                            peer_id=user["id"], message=resp,
                            keyboard=self.get_main_keyboard(), random_id=0
                        )
                        await self.log_and_update(user["id"], user["first_name"], f"ТРИГГЕР: {kw}")
                        return

            # ── Если ничего не совпало ────────────────────────────────────────
            if is_new or self.forward_all:
                await self.forward_to_admin(m, user, is_first=is_new)
                await self.log_and_update(user["id"], user["first_name"], m.text or "[Медиа]")
                # При forwardAll — подтверждаем получение (не для первого сообщения)
                if self.forward_all and not is_new:
                    try:
                        await self.bot.api.messages.send(
                            peer_id=user["id"],
                            message="✅ Сообщение передано оператору.",
                            keyboard=self.get_main_keyboard(),
                            random_id=0
                        )
                    except Exception:
                        pass
            else:
                # forwardAll выключен и ничего не совпало — сообщаем пользователю
                await self.log_and_update(user["id"], user["first_name"], m.text or "[Медиа]")
                try:
                    await self.bot.api.messages.send(
                        peer_id=user["id"],
                        message="🤖 Команда не распознана. Воспользуйтесь кнопками меню.",
                        keyboard=self.get_main_keyboard(),
                        random_id=0
                    )
                except Exception:
                    pass

    # ─────────────────────────────────────────────────────────────────────────
    # ЗАПУСК
    # ─────────────────────────────────────────────────────────────────────────

    async def run_instance(self):
        logger.info(f"[FREE VK] Бот {self.bot_id} запускается...")

        # Проверка токена
        try:
            response = await self.bot.api.groups.get_by_id()
            if isinstance(response, list):
                group_name = response[0].name
            else:
                group_name = response.groups[0].name
            logger.info(f"✅ [FREE VK] Токен валиден! Группа: {group_name}")
        except Exception as e:
            logger.error(f"❌ [FREE VK] КРИТИЧЕСКАЯ ОШИБКА ТОКЕНА: {e}")
            logger.error("Проверь: 1. Токен (расшифрован ли?). 2. Long Poll (включен ли в ВК?).")
            return

        await self.sync_database_logic()
        await self.core_handlers_setup()

        self.is_running = True

        asyncio.create_task(self.database_sync_worker())
        asyncio.create_task(self.daily_stats_rotator())

        logger.info(
            f"[FREE VK] Бот {self.bot_id} готов. "
            f"Кнопок: {len(self.buttons)}, Триггеров: {len(self.triggers)}, "
            f"admin_chat: {self.admin_chat_id}, forwardAll={self.forward_all}, "
            f"inlineButtons={len(self.inline_buttons)}"
        )

        logger.info("🚀 [FREE VK] Запуск Long Poll поллинга...")
        try:
            asyncio.create_task(self.bot.run_polling())
            while self.is_running:
                await asyncio.sleep(1)
        except Exception as e:
            if "close a running event loop" not in str(e):
                logger.error(f"🚨 [FREE VK] Ошибка в жизненном цикле бота: {e}")
        finally:
            self.is_running = False
            logger.warning(f"⚠️ [FREE VK] Поллинг бота {self.bot_id} завершён.")


# ════════════════════════════════════════════════════════════════════════════════
# ТОЧКА ВХОДА
# ════════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("INFO: free_vk_bot_core.py is a worker script. "
              "Started by server.py with config path argument.\n"
              "Sleeping to prevent PM2 restart loop...", flush=True)
        import signal
        stop_event = asyncio.Event()
        def _sig(*_): stop_event.set()
        signal.signal(signal.SIGTERM, _sig)
        signal.signal(signal.SIGINT, _sig)
        async def _idle():
            await stop_event.wait()
        asyncio.run(_idle())
        sys.exit(0)

    async def main():
        cfg_path = sys.argv[1]
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            instance = FreeVKBotInstance(config)
            await instance.run_instance()
        except Exception as e:
            logger.error(f"FATAL: {e}", exc_info=True)

    asyncio.run(main())
