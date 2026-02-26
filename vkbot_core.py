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
from typing import Dict, Optional, List, Any, Union

# --- Загрузка переменных из .env ---
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Импорты vkbottle
from vkbottle import BaseMiddleware, Bot, CtxStorage
from vkbottle.bot import Message, MessageEvent
from vkbottle.dispatch.rules import ABCRule
from vkbottle import Keyboard, KeyboardButtonColor, Text
try:
    from vkbottle import Callback as VKCallback
except ImportError:
    VKCallback = None  # fallback: колбэк-кнопки недоступны
try:
    from vkbottle import OpenLink as VKLink
except ImportError:
    VKLink = None  # fallback: URL-кнопки недоступны
from vkbottle.exception_factory import VKAPIError
from typing import Dict, List, Optional

# ── SANDBOX ──────────────────────────────────────────────────────────────────
# Пользовательский код запускается в изолированном дочернем процессе Python.
# Данные передаются через stdin/stdout как JSON.
# OS-лимиты (RLIMIT_CPU) устанавливаются внутри дочернего процесса.
# Wall-clock таймаут контролируется asyncio.wait_for.

_SANDBOX_RUNNER_PY = r'''
import sys, json, os

try:
    _raw = sys.stdin.buffer.read()
    _data = json.loads(_raw)
    _code = _data["code"]
    _ctx  = _data["ctx"]
except Exception as e:
    sys.stdout.write(json.dumps({"ok": False, "error": "Input error: " + str(e)}) + "\n")
    sys.exit(1)

try:
    os.environ.clear()
except Exception:
    pass

try:
    import resource as _res
    _res.setrlimit(_res.RLIMIT_CPU, (4, 4))
except Exception:
    pass

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
    pass

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

try:
    exec(_code, _sb)
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

# --- ГЛОБАЛЬНАЯ КОНФИГУРАЦИЯ ЛОГИРОВАНИЯ ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BotCoreEngineVK")

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_anon_id(user_id: int) -> str:
    """Генерация короткого хеша для анонимности"""
    return hashlib.md5(str(user_id).encode()).hexdigest()[:6].upper()

def format_admin_header(user: dict, settings: dict, is_first: bool = False, btn_text: str = "") -> str:
    """Формирование заголовка сообщения для админа (текст)"""
    is_anon = settings.get('anonymousTopics', False)
    uid = user['id']
    anon_tag = f"#{get_anon_id(uid)}"
    
    if is_anon:
        user_info = f"👤 Аноним {anon_tag}"
    else:
        info_parts = []
        if settings.get('showHeaderName', True):
            name = user.get('first_name', "Пользователь")
            info_parts.append(f"{name}")
        
        if settings.get('showHeaderUsername', True) and user.get('domain'):
             info_parts.append(f"(@{user['domain']})")
            
        if settings.get('showHeaderId', True):
            info_parts.append(f"ID: {uid}")
            
        user_info = " | ".join(info_parts) if info_parts else f"Юзер {anon_tag}"

    status_line = ""
    if btn_text:
        status_line = settings.get('ticketMessageHeader', "🆘 ЗАЯВКА")
        if "{btn}" in status_line:
            status_line = status_line.replace("{btn}", btn_text)
        elif "[Кнопка" not in status_line:
            status_line += f" [Кнопка: {btn_text}]:"
    elif is_first:
        status_line = settings.get('firstMessageHeader', "🆕 ПЕРВОЕ ОБРАЩЕНИЕ:")
    else:
        status_line = settings.get('commonMessageHeader', "📩 СООБЩЕНИЕ:")

    return f"{status_line}\n{user_info}\n⬇️⬇️⬇️"

# --- MIDDLEWARE ---
class LicenseMiddleware(BaseMiddleware[Message]):
    async def pre(self):
        bot_instance = getattr(self.event.ctx_api, "bot_instance_ref", None)
        
        if bot_instance and getattr(bot_instance, 'license_expired', False):
            await self.event.answer("❌ Лицензия этого бота истекла.\nПожалуйста, продлите её в панели управления.")
            self.stop("License expired")

    async def post(self):
        pass

class BanMiddleware(BaseMiddleware[Message]):
    """Middleware проверки бана — блокирует всех забаненных до любой логики."""
    async def pre(self):
        bot_instance = getattr(self.event.ctx_api, "bot_instance_ref", None)
        if bot_instance is None:
            return
        user_id = self.event.from_id
        user = next((u for u in bot_instance.users_list if u.get('id') == user_id), None)
        if user and user.get("is_banned"):
            try:
                await self.event.answer("🚫 Вы заблокированы в этом боте.")
            except Exception:
                pass
            self.stop("User is banned")

    async def post(self):
        pass


# --- ОСНОВНОЙ КЛАСС БОТА ---
class BotInstance:
    def __init__(self, config_data: dict):
        self.bot_id = config_data.get('id')
        self.token = config_data.get('token')
        
        self.license_expired = False 
        
        self.sb_url = os.getenv("SUPABASE_URL")
        self.sb_key = os.getenv("SUPABASE_KEY")

        if not self.sb_url:
            self.sb_url = config_data.get("config", {}).get("api_url", "http://localhost:8000")
        
        if not self.sb_key:
            logger.warning(f"⚠️ [{self.bot_id}] SUPABASE_KEY не найден в окружении!")
            self.sb_key = ""

        self.sb_url = self.sb_url.rstrip('/')
        
        # Инициализация бота VK
        self.bot = Bot(token=self.token)
        self.bot.api.bot_instance_ref = self
        
        self.msg_map = {} 
        self.flood_cache = {}
        self.is_running = True
        self.sync_queue = asyncio.Queue()
        
        self.apply_config(config_data, is_initial=True)

    # ─────────────────────────────────────────────
    # СТАТИСТИКА
    # ─────────────────────────────────────────────
    async def update_stats(self, is_incoming: bool = True):
        try:
            today = datetime.now().strftime("%d.%m")
            st = self.stats_data

            st["totalMessages"] = st.get("totalMessages", 0) + 1
            if is_incoming:
                st["incomingToday"] = st.get("incomingToday", 0) + 1
            else:
                st["outgoingToday"] = st.get("outgoingToday", 0) + 1

            history = st.get("history", [])
            if not isinstance(history, list):
                history = []

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
                    "totalUsers": len(self.users_list),
                    "activeUsers": 1
                })

            st["history"] = history[-30:]
            self.config["stats"] = st

            headers = {
                "apikey": self.sb_key,
                "Authorization": f"Bearer {self.sb_key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            }
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.patch(
                    f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                    headers=headers,
                    json={"stats": st}
                )
        except Exception as e:
            logger.error(f"Error updating stats: {e}", exc_info=True)

    async def license_checker_logic(self):
        try:
            curr_time = int(time.time() * 1000)
            if self.license_expires_at and self.license_expires_at < curr_time:
                if not self.license_expired:
                    logger.warning(f" [!] Лицензия {self.bot_id} истекла!")
                    self.license_expired = True 
                    
                    async with httpx.AsyncClient() as client:
                        headers = {"apikey": self.sb_key, "Authorization": f"Bearer {self.sb_key}"}
                        await client.patch(
                            f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                            json={"status": "IDLE"},
                            headers=headers
                        )
            else:
                self.license_expired = False
        except Exception as e:
            logger.error(f"Ошибка в license_checker_logic: {e}")

    async def license_checker(self):
        logger.info(f"[*] Мониторинг лицензии для {self.bot_id} запущен")
        while self.is_running:
            await self.license_checker_logic()
            await asyncio.sleep(120)

    def apply_config(self, data: dict, is_initial: bool = False):
        raw_cfg = data.get('config', {}) if isinstance(data.get('config'), dict) else {}
        full_cfg = {**data, **raw_cfg}
        self.config = full_cfg

        vk_peer_raw = (
            full_cfg.get('vk_group_id') or full_cfg.get('vkGroupId') or
            full_cfg.get('admin_chat_id') or full_cfg.get('adminChatId')
        )
        try:
            self.admin_chat_id = int(str(vk_peer_raw).strip()) if vk_peer_raw else None
        except (ValueError, AttributeError):
            self.admin_chat_id = None

        try:
            vg_raw = full_cfg.get('vk_group_id') or full_cfg.get('vkGroupId')
            self.vk_group_id = int(str(vg_raw).strip()) if vg_raw else self.admin_chat_id
        except (ValueError, AttributeError):
            self.vk_group_id = self.admin_chat_id

        self.buttons       = full_cfg.get('buttons', [])
        self.triggers      = full_cfg.get('triggers', [])
        self.welcome_text  = full_cfg.get('welcomeMessage', 'Здравствуйте!')
        self.welcome_photo = full_cfg.get('welcomePhoto', '')
        self.welcome_inline= full_cfg.get('welcomeInline', [])  # [{text, url}]
        self.settings      = full_cfg.get('settings', {})
        self.rate_limit    = float(self.settings.get('rateLimit', 1.0))
        self.auto_ban_limit= int(self.settings.get('autoBanThreshold', 3))
        self.forward_all   = self.settings.get('forwardAll', False)  # Режим «без тикетов»

        # -- Список ID администраторов (из редактора, поле adminIds) --
        # Если список пустой -- команды разрешены всем участникам беседы
        raw_admin_ids = full_cfg.get('adminIds') or full_cfg.get('admin_ids') or []
        try:
            self.admin_ids: List[int] = [int(x) for x in raw_admin_ids if str(x).strip().isdigit()]
        except Exception:
            self.admin_ids = []
        
        if is_initial or not hasattr(self, 'users_list'):
            self.users_list = full_cfg.get('connectedUsers', [])
        
        self.license_expires_at = full_cfg.get('license_expires_at', 0)

        # ── ИИ-конфиг ──
        ai_cfg = full_cfg.get('ai', {}) or {}
        self.ai_enabled       = ai_cfg.get('enabled', False)
        self.ai_mode          = ai_cfg.get('mode', 'off')
        self.ai_button_name   = ai_cfg.get('buttonName', 'ИИ-ассистент')
        self.ai_system_prompt = ai_cfg.get('systemPrompt', 'Ты полезный ИИ-ассистент.')
        self.ai_max_tokens    = int(ai_cfg.get('maxTokensPerReply', 800))
        self.ai_context_len   = int(ai_cfg.get('contextMessages', 6))
        self.ai_model         = ai_cfg.get('model', 'gpt-4o')
        self.qwen_api_key     = os.getenv('TIMEWEB_API_KEY') or os.getenv('QWEN_API_KEY')
        agent_id = os.getenv('TIMEWEB_AGENT_ID', '14ce55f9-dce2-4f2d-ad98-ff2cffe19ca2')
        self.ai_url = f"https://agent.timeweb.cloud/api/v1/cloud-ai/agents/{agent_id}/v1/chat/completions"
        if not hasattr(self, 'ai_context_cache'):
            self.ai_context_cache: Dict[int, List[dict]] = {}

        if is_initial:
            incoming_stats = full_cfg.get('stats')
            if isinstance(incoming_stats, dict) and incoming_stats:
                self.stats_data = {
                    "totalMessages": incoming_stats.get("totalMessages", 0),
                    "incomingToday": incoming_stats.get("incomingToday", 0),
                    "outgoingToday": incoming_stats.get("outgoingToday", 0),
                    "bannedCount":   incoming_stats.get("bannedCount", 0),
                    "activeUsers24h":incoming_stats.get("activeUsers24h", 0),
                    "history":       incoming_stats.get("history", [])
                }
            else:
                self.stats_data = {
                    "totalMessages": 0, "incomingToday": 0, "outgoingToday": 0,
                    "bannedCount": 0, "history": [], "activeUsers24h": 0
                }
            if not self.stats_data["history"]:
                today = datetime.now().strftime("%d.%m")
                self.stats_data["history"] = [{
                    "date": today, "incoming": 0, "outgoing": 0,
                    "totalUsers": len(self.users_list), "activeUsers": 0
                }]

    async def sync_database_logic(self):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = {
                    "apikey": self.sb_key,
                    "Authorization": f"Bearer {self.sb_key}",
                    "Content-Type": "application/json",
                }
                res = await client.get(
                    f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                    headers=headers
                )
                if res.status_code == 200 and res.json():
                    remote_data = res.json()[0]
                    remote_config = remote_data.get("config") or {}
                    if not isinstance(remote_config, dict):
                        try:
                            remote_config = json.loads(remote_config)
                        except Exception:
                            remote_config = {}
                    self.apply_config({**remote_data, "config": remote_config})
                    logger.info(f"✅ VK [{self.bot_id}] Конфиг загружен (кнопок: {len(self.buttons)}, триггеров: {len(self.triggers)})")
        except Exception as e:
            logger.error(f"sync_database_logic VK error: {e}")

    async def daily_stats_rotator(self):
        while self.is_running:
            try:
                now = datetime.now()
                current_date = now.strftime("%d.%m")
                
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

                if history[-1]["date"] != current_date:
                    history[-1]["incoming"] = self.stats_data.get("incomingToday", 0)
                    history[-1]["outgoing"] = self.stats_data.get("outgoingToday", 0)
                    history[-1]["totalUsers"] = len(self.users_list)
                    history[-1]["activeUsers"] = active_count
                    
                    self.stats_data["incomingToday"] = 0
                    self.stats_data["outgoingToday"] = 0
                    
                    new_point = {
                        "date": current_date,
                        "incoming": 0, "outgoing": 0,
                        "totalUsers": len(self.users_list),
                        "activeUsers": active_count
                    }
                    history.append(new_point)
                    self.stats_data["history"] = history[-14:]
                    history = self.stats_data["history"]
                
                last_point = history[-1]
                last_point["incoming"] = self.stats_data.get("incomingToday", 0)
                last_point["outgoing"] = self.stats_data.get("outgoingToday", 0)
                last_point["totalUsers"] = len(self.users_list)
                last_point["activeUsers"] = active_count

                await self.sync_queue.put(("sync_state", None))
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Rotator Error: {e}")
                await asyncio.sleep(60)

    async def database_sync_worker(self):
        async with httpx.AsyncClient(timeout=10.0) as client:
            if not self.sb_url or not self.sb_url.startswith("http"):
                logger.warning(f"⚠️ SUPABASE_URL некорректен ('{self.sb_url}'). Восстановление...")
                self.sb_url = os.getenv("SERVER_URL", "http://localhost:8000").rstrip('/')

            headers = {
                "apikey": self.sb_key,
                "Authorization": f"Bearer {self.sb_key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            }
            
            while self.is_running:
                try:
                    item = await asyncio.wait_for(self.sync_queue.get(), timeout=1.0)
                    if not isinstance(item, tuple):
                        self.sync_queue.task_done()
                        continue

                    action, payload = item

                    if action == "log_message":
                        if self.sb_url.startswith("http"):
                            await client.post(f"{self.sb_url}/rest/v1/bot_messages", json=payload, headers=headers)

                    elif action == "sync_state":
                        if not self.sb_url or not self.sb_url.startswith("http"):
                            self.sync_queue.task_done()
                            continue
        
                        res = await client.get(
                            f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                            headers=headers
                        )

                        if res.status_code == 200 and res.json():
                            remote_data = res.json()[0]
                            remote_config = remote_data.get("config", {}) or {}

                            new_config = {
                                **remote_config,
                                "connectedUsers": self.users_list,
                                "admin_chat_id": self.admin_chat_id,
                                "adminChatId": self.admin_chat_id,
                                "vk_group_id": self.vk_group_id,
                                "vkGroupId": self.vk_group_id,
                            }

                            await client.patch(
                                f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                                json={"config": new_config, "stats": self.stats_data},
                                headers=headers
                            )

                            # Обновляем только кнопки/триггеры/настройки из БД,
                            # НЕ трогая users_list и stats в памяти
                            saved_users = self.users_list
                            saved_stats = self.stats_data
                            self.apply_config({**remote_data, "config": remote_config}, is_initial=False)
                            self.users_list = saved_users
                            self.stats_data = saved_stats

                    self.sync_queue.task_done()
                    
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"🚨 VK Sync Worker Error: {e}")
                    try:
                        self.sync_queue.task_done()
                    except:
                        pass

    # ─────────────────────────────────────────────
    # AI / TIMEWEB INTEGRATION
    # ─────────────────────────────────────────────
    async def ai_call(self, user_id: int, user_text: str) -> Optional[str]:
        if not self.qwen_api_key or not self.ai_url:
            return None
        ctx = self.ai_context_cache.setdefault(user_id, [])
        ctx.append({"role": "user", "content": user_text})
        if len(ctx) > self.ai_context_len * 2:
            ctx = ctx[-(self.ai_context_len * 2):]
            self.ai_context_cache[user_id] = ctx
        messages = [{"role": "system", "content": self.ai_system_prompt}] + ctx
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    self.ai_url,
                    headers={"Authorization": f"Bearer {self.qwen_api_key}", "Content-Type": "application/json"},
                    json={"model": self.ai_model, "messages": messages, "max_tokens": self.ai_max_tokens, "temperature": 0.7}
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
                    logger.error(f"AI API error {resp.status_code}: {resp.text[:200]}")
                    return None
        except Exception as e:
            logger.error(f"AI call error: {e}")
            return None

    async def _deduct_tokens(self, user_id: int, usage: dict, total: int):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                headers = {"apikey": self.sb_key, "Authorization": f"Bearer {self.sb_key}", "Content-Type": "application/json"}
                await client.post(f"{self.sb_url}/rest/v1/rpc/deduct_ai_tokens", headers=headers,
                                  json={"p_bot_id": self.bot_id, "p_amount": total})
                await client.post(f"{self.sb_url}/rest/v1/ai_token_usage_log",
                                  headers={**headers, "Prefer": "return=minimal"},
                                  json={"bot_id": self.bot_id, "user_id": user_id,
                                        "prompt_tokens": usage.get("prompt_tokens", 0),
                                        "response_tokens": usage.get("completion_tokens", 0),
                                        "total_tokens": total, "model": self.ai_model})
        except Exception as e:
            logger.warning(f"Token deduct error: {e}")

    async def check_ai_tokens(self) -> int:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                headers = {"apikey": self.sb_key, "Authorization": f"Bearer {self.sb_key}"}
                r = await client.get(f"{self.sb_url}/rest/v1/ai_token_balances?bot_id=eq.{self.bot_id}", headers=headers)
                if r.status_code == 200 and r.json():
                    return r.json()[0].get("tokens_balance", 0)
        except Exception:
            pass
        return 0

    def clear_ai_context(self, user_id: int):
        self.ai_context_cache.pop(user_id, None)

    # ─────────────────────────────────────────────
    # KEYBOARD HELPERS
    # ─────────────────────────────────────────────
    def get_main_keyboard(self) -> str:
        """Главная reply-клавиатура из кнопок + ИИ-кнопка (если нужно)."""
        active_btns = [b for b in self.buttons if b.get('text')]
        ai_btn_name = self.ai_button_name if self.ai_enabled and self.ai_mode == 'button' else None
        if not active_btns and not ai_btn_name:
            return Keyboard().get_json()
        
        kb = Keyboard(one_time=False, inline=False)
        all_btns = list(active_btns)
        for i, btn in enumerate(all_btns):
            if i % 2 == 0 and i != 0:
                kb.row()
            kb.add(Text(btn['text']), color=KeyboardButtonColor.PRIMARY)
        
        if ai_btn_name:
            if active_btns:
                kb.row()
            kb.add(Text(ai_btn_name), color=KeyboardButtonColor.SECONDARY)
            
        return kb.get_json()

    def build_keyboard_from_buttons(self, buttons: list) -> str:
        """Строит reply-клавиатуру из произвольного списка [{text}]."""
        active = [b for b in buttons if b.get('text')]
        if not active:
            return Keyboard().get_json()
        kb = Keyboard(one_time=True, inline=False)
        for i, btn in enumerate(active):
            if i % 2 == 0 and i != 0:
                kb.row()
            color = KeyboardButtonColor.NEGATIVE if btn['text'] == "⬅️ Назад" else KeyboardButtonColor.PRIMARY
            kb.add(Text(btn['text']), color=color)
        return kb.get_json()

    def get_ai_keyboard(self) -> str:
        """Инлайн-клавиатура для ИИ-диалога (кнопка закрытия).
        
        Используем Callback-кнопку если доступна, иначе — текстовую reply-кнопку.
        """
        if VKCallback is not None:
            kb = Keyboard(one_time=False, inline=True)
            kb.add(VKCallback("✖ Закрыть ИИ-диалог", payload={"cmd": "ai_close"}))
            return kb.get_json()
        else:
            kb = Keyboard(one_time=False, inline=False)
            kb.add(Text("✖ Закрыть ИИ-диалог"), color=KeyboardButtonColor.NEGATIVE)
            return kb.get_json()

    def build_inline_url_keyboard(self, buttons: list) -> Optional[str]:
        """Строит инлайн-клавиатуру из [{text, url}] для URL-кнопок."""
        if not buttons or VKLink is None:
            return None
        try:
            kb = Keyboard(inline=True)
            for i, btn in enumerate(buttons):
                if i > 0:
                    kb.row()
                kb.add(VKLink(btn['url'], btn['text']))
            return kb.get_json()
        except Exception as e:
            logger.warning(f"build_inline_url_keyboard error: {e}")
            return None

    def get_button_by_text(self, text: str, buttons=None) -> Optional[dict]:
        """Рекурсивно ищет кнопку по тексту (включая дочерние)."""
        if buttons is None:
            buttons = self.buttons
        for b in buttons:
            if b.get('text', '').lower() == text.lower():
                return b
            children = b.get('children', [])
            if children:
                found = self.get_button_by_text(text, children)
                if found:
                    return found
        return None

    # ─────────────────────────────────────────────
    # FLOW-ЛОГИКА РАСШИРЕННЫХ КНОПОК
    # ─────────────────────────────────────────────

    def _format_flow_text(self, text: str, m: Message) -> str:
        """Подставляет переменные в текст flow-действия."""
        uid = str(m.from_id)
        username = ""
        first_name = ""
        # Ищем кэшированные данные юзера
        user = next((u for u in self.users_list if u.get('id') == m.from_id), None)
        if user:
            username  = user.get('username') or user.get('domain') or ''
            first_name = user.get('first_name', '')
        return (text or '')\
            .replace('{username}', f'@{username}' if username else first_name)\
            .replace('{first_name}', first_name)\
            .replace('{last_name}', '')\
            .replace('{user_id}', uid)\
            .replace('{text}', m.text or '')

    async def execute_flow_actions(self, actions: list, m: Message, user: dict) -> bool:
        """
        Выполняет список action-объектов для одной flow-ноды.
        Возвращает True если была отправлена клавиатура с под-кнопками.
        """
        uid = user['id']
        showed_sub_keyboard = False

        for action in actions:
            atype = action.get('type', 'message')

            if atype == 'message':
                text = self._format_flow_text(action.get('text', ''), m)
                if text:
                    await self.bot.api.messages.send(
                        peer_id=user['id'],
                        message=text,
                        keyboard=self.get_main_keyboard(),
                        random_id=0
                    )

            elif atype == 'admin_notify':
                text = self._format_flow_text(action.get('text', ''), m)
                if text and self.admin_chat_id:
                    try:
                        await self.bot.api.messages.send(
                            peer_id=self.admin_chat_id,
                            message=text,
                            random_id=0
                        )
                    except Exception as e:
                        logger.warning(f"Flow admin_notify error: {e}")

            elif atype == 'code':
                code = action.get('code', '').strip()
                if code:
                    await self._execute_flow_code(code, m, user)

            elif atype == 'create_ticket':
                await self._flow_create_ticket(action, m, user)

            elif atype == 'buttons':
                sub_nodes = action.get('buttons', [])
                if sub_nodes:
                    raw_buttons = [{'text': node.get('label', '')} for node in sub_nodes if node.get('label')]
                    raw_buttons.append({'text': '⬅️ Назад'})
                    kb = self.build_keyboard_from_buttons(raw_buttons)
                    user['_flow_nodes'] = sub_nodes
                    await self.bot.api.messages.send(
                        peer_id=uid,
                        message='Выберите:',
                        keyboard=kb,
                        random_id=0
                    )
                    showed_sub_keyboard = True

        return showed_sub_keyboard

    async def _flow_create_ticket(self, action: dict, m: Message, user: dict):
        """Создаёт тикет из flow-действия (пересылает сообщение админу).
        Поля action совпадают с BotEditor: ticketBtnLabel, ticketUserText, ticketAdminText.
        """
        btn_text  = action.get('ticketAdminText', '') or action.get('btnText', '')
        resp_text = action.get('ticketUserText', '') or action.get('response', 'Ваше обращение принято. Ожидайте ответа оператора.')
        label     = action.get('ticketBtnLabel', '') or 'Закрыть обращение'
        user['_in_ticket'] = True
        user['_ticket_close_label'] = label
        await self.forward_to_admin(m, user, btn_text=btn_text)
        close_kb = self.build_keyboard_from_buttons([{'text': label}])
        await self.bot.api.messages.send(
            peer_id=user['id'],
            message=f"{resp_text}\n\nВы можете продолжать писать — сообщения будут доставлены оператору.",
            keyboard=close_kb,
            random_id=0
        )
        await self.sync_queue.put(("sync_state", None))

    def find_flow_node_by_label(self, label: str, nodes: list) -> Optional[dict]:
        """Рекурсивный поиск flow-ноды по тексту кнопки."""
        for node in nodes:
            if node.get('label', '').strip().lower() == label.strip().lower():
                return node
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
                    await self.bot.api.messages.send(
                        peer_id=user['id'],
                        message='Готово.',
                        keyboard=self.get_main_keyboard(),
                        random_id=0
                    )
                return True

        # Ищем в основных кнопках
        for btn in self.buttons:
            if btn.get('text', '').strip().lower() != text.lower():
                continue

            handled = False

            direct_actions = btn.get('directActions', [])
            if direct_actions:
                await self.execute_flow_actions(direct_actions, m, user)
                handled = True

            flow = btn.get('flow', [])
            if flow:
                raw_buttons = [{'text': node.get('label', '')} for node in flow if node.get('label')]
                raw_buttons.append({'text': '⬅️ Назад'})
                kb = self.build_keyboard_from_buttons(raw_buttons)
                user['_flow_nodes'] = flow
                resp = btn.get('response', '')
                await self.bot.api.messages.send(
                    peer_id=user['id'],
                    message=resp or 'Выберите:',
                    keyboard=kb,
                    random_id=0
                )
                handled = True

            if handled:
                return True

            return False

        return False

    async def _execute_flow_code(self, code: str, m: Message, user: dict):
        """
        Выполняет пользовательский код через изолированный дочерний процесс.
        Уровни защиты:
          1. AST-scan (статические лимиты + security-scan)
          2. Subprocess: отдельный Python-процесс с RLIMIT_CPU=4с
          3. asyncio.wait_for: wall-clock timeout 6 секунд
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
                    return False, "Оператор import запрещён"
            return True, None

        ok, ast_err = _ast_check(code)
        if not ok:
            logger.warning(f"Flow AST blocked (bot {self.bot_id}): {ast_err}")
            await m.answer(f"Код отклонён: {ast_err}")
            return

        ctx = {
            "user_id":    user['id'],
            "username":   user.get('username') or user.get('domain') or '',
            "first_name": user.get('first_name', ''),
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
                env={k: v for k, v in _os.environ.items() if k in (
                    "PATH", "LD_LIBRARY_PATH", "LD_PRELOAD",
                    "PYTHONPATH", "PYTHONHOME",
                    "LANG", "LC_ALL", "LC_CTYPE",
                    "HOME", "TMPDIR", "TMP", "TEMP",
                    "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED",
                    "VIRTUAL_ENV",
                )},
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(payload),
                timeout=_WALL_TIMEOUT,
            )

            if proc.returncode != 0 and not stdout.strip():
                rc = proc.returncode
                if rc in (-9, -15):
                    await m.answer("Код остановлен: превышен лимит CPU или памяти.")
                else:
                    err_txt = stderr.decode(errors="replace")[:200]
                    await m.answer(f"Процесс завершился с ошибкой (код {rc}).")
                    logger.warning(f"Flow sandbox exit {rc} for bot {self.bot_id}: {err_txt}")
                return

            if not stdout.strip():
                return

            result = _json.loads(stdout.decode().strip())
            if result.get("ok"):
                reply = result.get("reply", "").strip()
                if reply:
                    if len(reply) > _MAX_REPLY_LEN:
                        reply = reply[:_MAX_REPLY_LEN] + "…"
                    await m.answer(reply)
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

    async def check_antispam(self, user_id: int) -> bool:
        if self.rate_limit <= 0: return False
        now = time.time()
        last_time = self.flood_cache.get(user_id, 0)
        if now - last_time < self.rate_limit: return True
        self.flood_cache[user_id] = now
        return False

    async def log_and_update(self, uid: int, name: str, text: str, is_admin: bool = False):
        await self.sync_queue.put(("log_message", {
            "bot_id": self.bot_id, 
            "user_id": uid, 
            "first_name": name,
            "message_text": text[:950] if text else "[Медиа]", 
            "is_from_admin": is_admin
        }))
        
        if not is_admin:
            for u in self.users_list:
                if u['id'] == uid:
                    u['last_seen'] = int(time.time())
                    u['first_name'] = name 
                    break
        
        await self.update_stats(is_incoming=not is_admin)
        await self.sync_queue.put(("sync_state", None))

    async def get_user_state(self, m: Message):
        uid = m.from_id
        user = next((u for u in self.users_list if u['id'] == uid), None)
        is_first_time = False
        
        user_info = (await self.bot.api.users.get(user_ids=[uid]))[0]
        full_name = f"{user_info.first_name} {user_info.last_name}"
        
        if not user:
            is_first_time = True
            user = {
                "id": uid, 
                "first_name": full_name, 
                "username": user_info.domain, 
                "domain": user_info.domain,
                "is_banned": False, 
                "is_active": True, 
                "warns": 0, 
                "joined_at": int(time.time()),
                "last_seen": int(time.time()),
            }
            self.users_list.append(user)
            await self.sync_queue.put(("sync_state", None))
        else:
            user["last_seen"] = int(time.time())
            if not user.get("is_active", True):
                user["is_active"] = True
                await self.sync_queue.put(("sync_state", None))
            
        return user, is_first_time

    async def forward_to_admin(self, m: Message, user: dict, is_first: bool = False, btn_text: str = ""):
        if not self.admin_chat_id:
            return
        
        header = format_admin_header(user, self.settings, is_first, btn_text)
        user_text = m.text or ""
        full_text = (f"{header}\n{user_text}".strip()) if user_text else header

        try:
            attachment_str = None
            if m.attachments:
                parts = []
                for att in m.attachments:
                    try:
                        att_type = str(att.type.value) if hasattr(att.type, 'value') else str(att.type)
                        att_obj = getattr(att, att_type, None)
                        if att_obj:
                            owner = getattr(att_obj, 'owner_id', None)
                            aid   = getattr(att_obj, 'id', None)
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
            self.msg_map[sent_msg_id] = user['id']
            logger.debug(f"[msg_map] {sent_msg_id} -> {user['id']}")

        except Exception as e:
            logger.error(f"forward_to_admin error: {e}", exc_info=True)

    # ─────────────────────────────────────────────
    # СОХРАНЕНИЕ В БД (хелпер)
    # ─────────────────────────────────────────────
    async def _save_to_db(self):
        """Принудительная запись users_list и stats в БД."""
        try:
            headers = {
                "apikey": self.sb_key,
                "Authorization": f"Bearer {self.sb_key}",
                "Content-Type": "application/json"
            }
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.get(f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}", headers=headers)
                if res.status_code == 200 and res.json():
                    remote_config = res.json()[0].get("config", {})
                    new_config = {
                        **remote_config,
                        "connectedUsers": self.users_list,
                        "stats": self.stats_data
                    }
                    await client.patch(
                        f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                        json={"config": new_config, "stats": self.stats_data},
                        headers=headers
                    )
            await self.sync_queue.put(("sync_state", None))
        except Exception as e:
            logger.error(f"❌ VK _save_to_db error: {e}")

    # ─────────────────────────────────────────────
    # КОМАНДЫ АДМИНИСТРАТОРА
    # ─────────────────────────────────────────────
    def is_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь администратором бота.
        
        Если self.admin_ids пустой (не задан в редакторе) — разрешаем всем
        участникам беседы (обратная совместимость).
        Если задан — проверяем вхождение.
        """
        if not self.admin_ids:
            return True  # Список пустой = доверяем всем в беседе
        return user_id in self.admin_ids

    async def admin_control_logic(self, m: Message):
        """Единая логика всех админ-команд: /stats, /broadcast, /ban, /unban, /warn, /unwarn"""
        if not m.text or not (m.text.startswith("/") or m.text.startswith("!")): 
            return False

        # /getid — специальная команда, доступна без проверки прав
        if m.text.strip().lower() in ["/getid", "!getid"]:
            await self.bot.api.messages.send(
                peer_id=m.peer_id,
                message=(
                    "ℹ️ Информация о беседе:\n\n"
                    f"📌 peer_id беседы: {m.peer_id}\n"
                    f"👤 Ваш VK ID: {m.from_id}\n"
                    f"🤖 Текущий admin_chat_id бота: {self.admin_chat_id}\n"
                    f"🛡 admin_ids: {self.admin_ids or 'не задан (все в беседе)'}"
                ),
                random_id=0
            )
            return True

        # Проверка прав для всех остальных команд
        if not self.is_admin(m.from_id):
            logger.info(f"[VK] Команда от незнакомого юзера {m.from_id} отклонена (не в admin_ids)")
            return False

        cmd_parts = m.text.lower().split()
        command = cmd_parts[0][1:]

        # ── ГРУППА 1: ГЛОБАЛЬНЫЕ КОМАНДЫ (не требуют юзера) ──

        # 📊 СТАТИСТИКА
        if command == "stats":
            total_users = len(self.users_list)
            banned = self.stats_data.get("bannedCount", 0)
            active = self.stats_data.get("activeUsers24h", 0)
            total_msgs = self.stats_data.get("totalMessages", 0)
            await self.bot.api.messages.send(
                peer_id=self.admin_chat_id,
                message=(
                    f"📊 Статистика бота:\n\n"
                    f"👥 Всего пользователей: {total_users}\n"
                    f"🟢 Активных за 24ч: {active}\n"
                    f"💬 Всего сообщений: {total_msgs}\n"
                    f"🚫 Заблокировано: {banned}"
                ),
                random_id=0
            )
            return True

        # 📢 РАССЫЛКА
        elif command == "broadcast":
            # /broadcast с реплаем на сообщение — рассылаем это сообщение
            if m.reply_message and m.reply_message.text:
                broadcast_text = m.reply_message.text
                sent_count, err_count = 0, 0
                await self.bot.api.messages.send(
                    peer_id=self.admin_chat_id,
                    message="🚀 Запускаю рассылку...",
                    random_id=0
                )
                for user in list(self.users_list):
                    if user.get("is_banned") or not user.get("is_active", True):
                        continue
                    try:
                        await self.bot.api.messages.send(
                            peer_id=int(user['id']),
                            message=broadcast_text,
                            random_id=0
                        )
                        sent_count += 1
                        await asyncio.sleep(0.05)
                    except Exception:
                        err_count += 1
                        user["is_active"] = False
                await self.bot.api.messages.send(
                    peer_id=self.admin_chat_id,
                    message=(
                        f"✅ Рассылка завершена!\n\n"
                        f"👤 Доставлено: {sent_count}\n"
                        f"🚫 Ошибки/неактивные: {err_count}"
                    ),
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

        # ── ГРУППА 2: КОМАНДЫ МОДЕРАЦИИ (требуют юзера) ──

        target_user = None
        
        # А) Реплай на сообщение бота
        if m.reply_message:
            uid = self.msg_map.get(m.reply_message.id)
            if uid:
                target_user = next((u for u in self.users_list if u['id'] == uid), None)
            
            if not target_user and m.reply_message.fwd_messages:
                original_sender = m.reply_message.fwd_messages[0].from_id
                target_user = next((u for u in self.users_list if u['id'] == original_sender), None)
            
            # Фолбек: парсим ID из шапки сообщения
            if not target_user:
                reply_text = m.reply_message.text or ""
                id_match = re.search(r'ID:\s*(\d+)', reply_text)
                if id_match:
                    try:
                        parsed_id = int(id_match.group(1))
                        target_user = next((u for u in self.users_list if u['id'] == parsed_id), None)
                    except ValueError:
                        pass
        
        # Б) ID указан явно (!ban 12345)
        if not target_user and len(cmd_parts) > 1:
            try:
                manual_id = int(cmd_parts[1])
                target_user = next((u for u in self.users_list if u['id'] == manual_id), None)
            except: pass

        if not target_user:
            return False

        uid = target_user['id']

        # 🔍 ИНФО О ПОЛЬЗОВАТЕЛЕ (/whois)
        if command == "whois":
            username = target_user.get("username") or target_user.get("domain")
            name_line = target_user.get("first_name", "—")
            if username:
                name_line += f" (@{username})"
            joined = datetime.fromtimestamp(target_user.get("joined_at", 0)).strftime("%d.%m.%Y %H:%M") if target_user.get("joined_at") else "—"
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

        # 🚫 БАН
        if command == "ban":
            target_user["is_banned"] = True
            self.stats_data["bannedCount"] = self.stats_data.get("bannedCount", 0) + 1
            await self._save_to_db()
            try: await self.bot.api.messages.send(peer_id=uid, message="🚫 Доступ ограничен администратором.", random_id=0)
            except: pass
            await self.bot.api.messages.send(peer_id=self.admin_chat_id, message=f"✅ Пользователь {uid} заблокирован.", random_id=0)
            return True

        # 🟢 РАЗБАН
        elif command == "unban":
            target_user["is_banned"] = False
            target_user["warns"] = 0
            self.stats_data["bannedCount"] = max(0, self.stats_data.get("bannedCount", 1) - 1)
            await self._save_to_db()
            try: await self.bot.api.messages.send(peer_id=uid, message="✅ Ваш доступ восстановлен администратором.", random_id=0)
            except: pass
            await self.bot.api.messages.send(peer_id=self.admin_chat_id, message=f"✅ Пользователь {uid} разблокирован.", random_id=0)
            return True

        # ⚠️ ВАРН
        elif command == "warn":
            target_user["warns"] = target_user.get("warns", 0) + 1
            if self.auto_ban_limit > 0 and target_user["warns"] >= self.auto_ban_limit:
                target_user["is_banned"] = True
                self.stats_data["bannedCount"] = self.stats_data.get("bannedCount", 0) + 1
                await self._save_to_db()
                try: await self.bot.api.messages.send(peer_id=uid, message=f"🚫 Авто-бан: лимит предупреждений ({target_user['warns']}) исчерпан.", random_id=0)
                except: pass
                await self.bot.api.messages.send(peer_id=self.admin_chat_id, message=f"🚨 АВТО-БАН! Юзер {uid} (варнов: {target_user['warns']}/{self.auto_ban_limit}).", random_id=0)
            else:
                await self._save_to_db()
                try: await self.bot.api.messages.send(peer_id=uid, message=f"⚠️ Предупреждение! ({target_user['warns']}/{self.auto_ban_limit})", random_id=0)
                except: pass
                await self.bot.api.messages.send(peer_id=self.admin_chat_id, message=f"⚠️ Варн выдан. Всего: {target_user['warns']}/{self.auto_ban_limit}", random_id=0)
            return True

        # 🔄 СНЯТЬ ВАРН
        elif command == "unwarn":
            target_user["warns"] = max(0, target_user.get("warns", 0) - 1)
            await self._save_to_db()
            await self.bot.api.messages.send(peer_id=self.admin_chat_id, message=f"✅ Предупреждение снято. Текущее: {target_user['warns']}", random_id=0)
            return True

        return False

    async def bind_peer_id(self, peer_id: int, invited_by: int = None):
        if peer_id == self.admin_chat_id:
            return

        cfg = self.config or {}
        invite_owner = cfg.get("vk_invite_owner_id")

        should_bind = False
        if not self.admin_chat_id:
            should_bind = True
        elif invited_by and invite_owner and invited_by == invite_owner:
            should_bind = True

        if not should_bind:
            return

        self.admin_chat_id = peer_id
        self.vk_group_id = peer_id
        logger.info(f"🔗 [{self.bot_id}] Auto-bind: peer_id={peer_id} (invited_by={invited_by})")

        cfg["vk_group_id"]  = peer_id
        cfg["vkGroupId"]    = peer_id
        cfg["admin_chat_id"]= peer_id
        cfg["adminChatId"]  = peer_id
        if invited_by:
            cfg["vk_invite_owner_id"] = invited_by
        self.config = cfg

        headers = {
            "apikey": self.sb_key,
            "Authorization": f"Bearer {self.sb_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.patch(
                    f"{self.sb_url}/rest/v1/bots?id=eq.{self.bot_id}",
                    headers=headers,
                    json={
                        "vk_group_id": peer_id,
                        "admin_chat_id": None,
                        "config": cfg
                    }
                )
            logger.info(f"✅ [{self.bot_id}] peer_id={peer_id} сохранён в БД")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения peer_id: {e}")

    # ─────────────────────────────────────────────
    # ХЕНДЛЕРЫ
    # ─────────────────────────────────────────────
    async def core_handlers_setup(self):
        self.bot.labeler.message_view.register_middleware(LicenseMiddleware)
        self.bot.labeler.message_view.register_middleware(BanMiddleware)

        # ── Бот приглашён в беседу ──
        @self.bot.on.message(func=lambda m: (
            m.action is not None and
            m.action.type is not None and
            "invite" in str(m.action.type).lower()
        ))
        async def handle_chat_invite(m: Message):
            if m.peer_id and m.peer_id > 2000000000:
                inviter_id = m.from_id
                await self.bind_peer_id(m.peer_id, invited_by=inviter_id)
                try:
                    await self.bot.api.messages.send(
                        peer_id=m.peer_id,
                        message=f"✅ Бот подключён! Сообщения пользователей будут пересылаться сюда.\nID беседы: {m.peer_id}",
                        random_id=0
                    )
                except Exception as e:
                    logger.warning(f"Не удалось отправить приветствие в беседу: {e}")

        # ── Ответы и команды из беседы администратора ──
        @self.bot.on.message(func=lambda m: (
            self.admin_chat_id is not None and
            m.peer_id == self.admin_chat_id
        ))
        async def handle_admin_message(m: Message):
            # Команды (/ban, /unban, /warn, /unwarn, /stats, /broadcast)
            if m.text and (m.text.startswith("/") or m.text.startswith("!")):
                handled = await self.admin_control_logic(m)
                if handled:
                    return

            # Reply → отправляем ответ юзеру
            if m.reply_message is not None:
                target_id = self.msg_map.get(m.reply_message.id)

                if not target_id:
                    reply_text = m.reply_message.text or ""
                    id_match = re.search(r'ID:\s*(\d+)', reply_text)
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
                                    att_type = str(att.type.value) if hasattr(att.type, 'value') else str(att.type)
                                    att_obj = getattr(att, att_type, None)
                                    if att_obj:
                                        owner = getattr(att_obj, 'owner_id', None)
                                        aid   = getattr(att_obj, 'id', None)
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
                        else:
                            await self.bot.api.messages.send(peer_id=target_id, message="✉️", random_id=0)

                    except VKAPIError[901]:
                        await self.bot.api.messages.send(
                            peer_id=self.admin_chat_id,
                            message="❌ Пользователь запретил сообщения от бота.",
                            random_id=0
                        )
                        user = next((u for u in self.users_list if u['id'] == target_id), None)
                        if user:
                            user["is_active"] = False
                            await self.sync_queue.put(("sync_state", None))
                    except Exception as e:
                        logger.error(f"handle_admin_message reply error: {e}", exc_info=True)
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
                        message="⚠️ Не могу найти получателя. Попробуй ответить на более свежее сообщение.",
                        random_id=0
                    )

        # ── Обработка Callback-кнопок (инлайн) ──
        if VKCallback is not None:
            @self.bot.on.raw_event("message_event", MessageEvent, func=lambda e: True)
            async def handle_message_event(event: MessageEvent):
                payload = event.payload or {}
                cmd = payload.get("cmd", "")
                user_id = event.user_id

                # Закрытие ИИ-диалога
                if cmd == "ai_close":
                    user = next((u for u in self.users_list if u['id'] == user_id), None)
                    if user:
                        user.pop('_ai_session', None)
                        self.clear_ai_context(user_id)
                    try:
                        # Показываем снэкбар и убираем инлайн-кнопку
                        await event.show_snackbar("Диалог с ИИ закрыт.")
                        await self.bot.api.messages.send(
                            peer_id=user_id,
                            message="✅ Диалог с ИИ завершён.",
                            keyboard=self.get_main_keyboard(),
                            random_id=0
                        )
                    except Exception as e:
                        logger.warning(f"ai_close callback error: {e}")

        # ── Сообщения от пользователей ──
        @self.bot.on.message()
        async def handle_user_input(m: Message):
            # Авто-привязка беседы
            if not self.admin_chat_id and m.peer_id and m.peer_id > 2000000000:
                await self.bind_peer_id(m.peer_id, invited_by=m.from_id)
                return

            # Игнорируем беседы
            if self.admin_chat_id and m.peer_id == self.admin_chat_id:
                return
            if m.peer_id and m.peer_id > 2000000000:
                return
            
            user, is_new = await self.get_user_state(m)
            
            # БАН (дополнительная проверка на случай, если middleware пропустил)
            if user.get("is_banned"):
                try:
                    await self.bot.api.messages.send(
                        peer_id=user['id'],
                        message="🚫 Вы заблокированы в этом боте.",
                        random_id=0
                    )
                except Exception:
                    pass
                return

            # Анти-спам
            if await self.check_antispam(user['id']):
                return

            # ── РЕЖИМ АКТИВНОГО ТИКЕТА ──
            if user.get('_in_ticket'):
                _close_label = user.get('_ticket_close_label', 'Закрыть обращение')
                if m.text and m.text.strip() in (_close_label, "Закрыть обращение"):
                    user.pop('_in_ticket', None)
                    user.pop('_ticket_close_label', None)
                    await self.sync_queue.put(("sync_state", None))
                    if self.admin_chat_id:
                        name = user.get("first_name", str(user['id']))
                        username_str = user.get("username") or user.get("domain")
                        user_line = name
                        if username_str:
                            user_line += f" (@{username_str})"
                        user_line += f" | ID: {user['id']}"
                        try:
                            await self.bot.api.messages.send(
                                peer_id=self.admin_chat_id,
                                message=f"Обращение закрыто пользователем.\n{user_line}",
                                random_id=0
                            )
                        except Exception:
                            pass
                    await self.bot.api.messages.send(
                        peer_id=user['id'],
                        message="Обращение закрыто.",
                        keyboard=self.get_main_keyboard(),
                        random_id=0
                    )
                    return

                # Тикет открыт — пересылаем всё админу
                await self.forward_to_admin(m, user)
                await self.log_and_update(user['id'], user['first_name'], m.text or "[Медиа]")
                return

            if m.text:
                clean_text = m.text.strip()
                clean_lower = clean_text.lower()

                # ── Кнопка «Назад» (высший приоритет) ──
                if clean_text in ("⬅️ Назад", "Назад"):
                    user.pop('_ai_session', None)
                    user.pop('_flow_nodes', None)
                    self.clear_ai_context(user['id'])
                    await self.bot.api.messages.send(
                        peer_id=user['id'],
                        message="Главное меню:",
                        keyboard=self.get_main_keyboard(),
                        random_id=0
                    )
                    return

                # ── Закрытие ИИ-диалога (текстовая кнопка, фолбек) ──
                if clean_text == "✖ Закрыть ИИ-диалог":
                    user.pop('_ai_session', None)
                    self.clear_ai_context(user['id'])
                    await m.answer("✅ Диалог с ИИ завершён.", keyboard=self.get_main_keyboard())
                    return

                # ── START ──
                if clean_lower in ["start", "/start", "начать"]:
                    attachment_str = None
                    if self.welcome_photo:
                        try:
                            upload_server = await self.bot.api.photos.get_messages_upload_server(peer_id=user['id'])
                            async with httpx.AsyncClient(timeout=15) as hclient:
                                img_resp = await hclient.get(self.welcome_photo)
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
                            logger.warning(f"VK welcome photo upload error: {e}")
                    
                    inline_buttons = [b for b in (self.welcome_inline or []) if b.get('text') and b.get('url')]
                    inline_kb_json = self.build_inline_url_keyboard(inline_buttons) if inline_buttons else None

                    await self.bot.api.messages.send(
                        peer_id=user['id'],
                        message=self.welcome_text,
                        attachment=attachment_str,
                        keyboard=inline_kb_json if inline_kb_json else self.get_main_keyboard(),
                        random_id=0
                    )
                    
                    if inline_kb_json:
                        try:
                            await self.bot.api.messages.send(
                                peer_id=user['id'],
                                message="👇 Выберите действие:",
                                keyboard=self.get_main_keyboard(),
                                random_id=0
                            )
                        except Exception:
                            pass
                    elif inline_buttons and VKLink is None:
                        links_text = "\n".join([f"🔗 {b['text']}: {b['url']}" for b in inline_buttons])
                        try:
                            await self.bot.api.messages.send(peer_id=user['id'], message=links_text, random_id=0)
                        except Exception:
                            pass
                    
                    await self.log_and_update(user['id'], user['first_name'], "/start")
                    return

                # ── /ai, /gpt, /nn — открыть ИИ-сессию ──
                if clean_lower in ['/ai', '/gpt', '/nn']:
                    if self.ai_enabled:
                        bal = await self.check_ai_tokens()
                        if bal <= 0:
                            await m.answer("⚠️ AI-токены закончились. Пополните баланс в панели управления.", keyboard=self.get_main_keyboard())
                            return
                        user['_ai_session'] = True
                        await m.answer("🤖 ИИ-ассистент активирован. Задайте вопрос:", keyboard=self.get_ai_keyboard())
                    else:
                        await m.answer("ИИ-ассистент не подключён.")
                    return

                # ── /reset_ai — сбросить контекст ИИ ──
                if clean_lower == '/reset_ai':
                    self.clear_ai_context(user['id'])
                    user.pop('_ai_session', None)
                    await m.answer("Контекст и сессия ИИ сброшены.", keyboard=self.get_main_keyboard())
                    return

                # ── Активная ИИ-сессия ──
                if user.get('_ai_session') and self.ai_enabled:
                    bal = await self.check_ai_tokens()
                    if bal <= 0:
                        user.pop('_ai_session', None)
                        self.clear_ai_context(user['id'])
                        await m.answer("⚠️ AI-токены закончились. Диалог завершён.", keyboard=self.get_main_keyboard())
                        return
                    reply = await self.ai_call(user['id'], m.text)
                    if reply:
                        await m.answer(reply, keyboard=self.get_ai_keyboard())
                    else:
                        await m.answer("⚠️ ИИ не смог ответить. Попробуйте позже.", keyboard=self.get_ai_keyboard())
                    await self.log_and_update(user['id'], user['first_name'], m.text)
                    return

                # ── FLOW-ЛОГИКА расширенных кнопок ──
                flow_handled = await self.handle_flow_button(m, user)
                if flow_handled:
                    await self.log_and_update(user['id'], user['first_name'], f"FLOW: {clean_text}")
                    return

                # ── КНОПКИ (рекурсивный поиск, sub-кнопки, инлайн URL) ──
                matched_btn = self.get_button_by_text(clean_text)
                if matched_btn:
                    user.pop('_ai_session', None)

                    # Кнопка ИИ-ассистента
                    if self.ai_enabled and self.ai_mode == 'button' and matched_btn['text'] == self.ai_button_name:
                        bal = await self.check_ai_tokens()
                        if bal <= 0:
                            await m.answer("⚠️ AI-токены закончились.", keyboard=self.get_main_keyboard())
                        else:
                            user['_ai_session'] = True
                            await m.answer("🤖 ИИ-ассистент активирован. Задайте вопрос:", keyboard=self.get_ai_keyboard())
                        await self.log_and_update(user['id'], user['first_name'], f"КНОПКА: {matched_btn['text']}")
                        return

                    children = matched_btn.get('children', [])
                    if children:
                        child_kb = self.build_keyboard_from_buttons(children + [{"text": "⬅️ Назад"}])
                        response_text = matched_btn.get('response') or "Выберите действие:"
                        await m.answer(response_text, keyboard=child_kb)
                    else:
                        if matched_btn.get('type') == 'request':
                            user['_in_ticket'] = True
                            label = 'Закрыть обращение'
                            user['_ticket_close_label'] = label
                            await self.forward_to_admin(m, user, btn_text=matched_btn['text'])
                            await self.sync_queue.put(("sync_state", None))
                        
                        resp_text = matched_btn.get('response', 'Принято!')
                        
                        btn_inline = [b for b in matched_btn.get('inline', []) if b.get('text') and b.get('url')]
                        inline_kb = self.build_inline_url_keyboard(btn_inline) if btn_inline else None
                        
                        if matched_btn.get('type') == 'request':
                            close_kb = self.build_keyboard_from_buttons([{'text': 'Закрыть обращение'}])
                            await self.bot.api.messages.send(
                                peer_id=user['id'],
                                message=f"{resp_text}\n\nВы можете продолжать писать — сообщения будут доставлены оператору.",
                                keyboard=close_kb,
                                random_id=0
                            )
                        elif inline_kb:
                            await self.bot.api.messages.send(
                                peer_id=user['id'],
                                message=resp_text,
                                keyboard=inline_kb,
                                random_id=0
                            )
                            await self.bot.api.messages.send(
                                peer_id=user['id'],
                                message="👇",
                                keyboard=self.get_main_keyboard(),
                                random_id=0
                            )
                        else:
                            await m.answer(resp_text, keyboard=self.get_main_keyboard())

                    await self.log_and_update(user['id'], user['first_name'], f"КНОПКА: {matched_btn['text']}")
                    return
                
                # ── ТРИГГЕРЫ (с поддержкой children) ──
                for trig in self.triggers:
                    if trig.get('keyword') and trig['keyword'].lower() in clean_lower:
                        trig_children = trig.get('children', [])
                        resp_text = trig.get('response', '')
                        if trig_children:
                            child_kb = self.build_keyboard_from_buttons(trig_children + [{"text": "⬅️ Назад"}])
                            await m.answer(resp_text or "Выберите:", keyboard=child_kb)
                        else:
                            await m.answer(resp_text, keyboard=self.get_main_keyboard())
                        await self.log_and_update(user['id'], user['first_name'], f"ТРИГГЕР: {trig['keyword']}")
                        return

                # ── ИИ режим «отвечать на всё» ──
                if self.ai_enabled and self.ai_mode == 'all':
                    bal = await self.check_ai_tokens()
                    if bal > 0:
                        reply = await self.ai_call(user['id'], m.text)
                        if reply:
                            await m.answer(reply, keyboard=self.get_main_keyboard())
                            await self.log_and_update(user['id'], user['first_name'], m.text)
                            return
            
            # ── Если ничего не совпало ──
            if is_new:
                # Первое обращение — пересылаем админу
                await self.forward_to_admin(m, user, is_first=True)
                await self.log_and_update(user['id'], user['first_name'], m.text or "[Медиа]")
            elif self.forward_all:
                # Режим «без тикетов» — пересылаем всё
                await self.forward_to_admin(m, user)
                await self.log_and_update(user['id'], user['first_name'], m.text or "[Медиа]")
            # Иначе — молчим (или можно дать fallback-текст если задан)

    async def run_instance(self):
        logger.info(f"[*] Бот VK {self.bot_id} запускается...")
        
        # Проверка токена
        try:
            response = await self.bot.api.groups.get_by_id()
            if isinstance(response, list):
                group_name = response[0].name
            else:
                group_name = response.groups[0].name
            logger.info(f"✅ Токен валиден! Группа: {group_name}")
        except Exception as e:
            logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА ТОКЕНА: {e}")
            logger.error("Проверь: 1. Токен (расшифрован ли?). 2. Long Poll (включен ли в ВК?).")
            return 

        await self.license_checker_logic()
        await self.sync_database_logic()
        await self.core_handlers_setup()

        logger.info(f"[*] Бот VK {self.bot_id} готов. AdminID: {self.admin_chat_id}")

        self.is_running = True

        asyncio.create_task(self.database_sync_worker())
        asyncio.create_task(self.daily_stats_rotator())
        asyncio.create_task(self.license_checker())

        logger.info("🚀 Запуск Long Poll поллинга...")
        
        try:
            asyncio.create_task(self.bot.run_polling())
            while self.is_running:
                await asyncio.sleep(1)
        except Exception as e:
            if "close a running event loop" not in str(e):
                logger.error(f"🚨 Ошибка в жизненном цикле бота: {e}")
        finally:
            self.is_running = False
            logger.warning(f"⚠️ Поллинг бота {self.bot_id} завершен.")

# ==========================================================
# БЛОК ЗАПУСКА
# ==========================================================
if __name__ == "__main__":
    import sys
    import json
    import asyncio

    if len(sys.argv) < 2:
        print("Usage: python3 vkbot_core.py <config_path>")
        sys.exit(1)

    cfg_path = sys.argv[1]
    
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Не удалось прочитать конфиг {cfg_path}: {e}")
        sys.exit(1)

    instance = BotInstance(config)
    loop = asyncio.get_event_loop()

    async def main():
        await instance.run_instance()

    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем (Ctrl+C)")
    except Exception as e:
        logger.error(f"🚨 Критическая ошибка при работе: {e}", exc_info=True)
    finally:
        try:
            loop.run_until_complete(asyncio.sleep(0.1))
        except:
            pass
        if not loop.is_closed():
            loop.close()
