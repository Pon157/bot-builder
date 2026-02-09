import os
import asyncio
import logging
import sys
import requests
import json
import signal
from datetime import datetime
from typing import List, Optional, Union

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, CallbackQuery, Message, BotCommand
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from supabase import create_client, Client

# ==========================================
# 1. ГЛОБАЛЬНАЯ КОНФИГУРАЦИЯ И ЛОГИРОВАНИЕ
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("LicenseBotEngine")

def load_env_secure():
    """Железобетонная загрузка переменных окружения с очисткой токенов"""
    path = os.path.join(BASE_DIR, '.env')
    conf = {}
    if not os.path.exists(path):
        logger.critical(f"🛑 Файл .env не найден по пути: {path}")
        return conf
    
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                clean_val = value.strip().strip('"').strip("'")
                
                # Твоя специфическая логика извлечения токена из .env
                if key.strip() == "ADMIN_BOT_TOKEN" and "root/" in clean_val:
                    clean_val = clean_val.split("root/")[0].strip()
                
                conf[key.strip()] = clean_val
    except Exception as e:
        logger.error(f"❌ Ошибка при чтении .env: {e}")
    return conf

# Загружаем конфиг
ENV = load_env_secure()
BOT_TOKEN = ENV.get("ADMIN_BOT_TOKEN")
SB_URL = ENV.get("SUPABASE_URL")
SB_KEY = ENV.get("SUPABASE_KEY")
# ID чата для заявок (группа или канал)
ADM_CHAT = ENV.get("ADMIN_CHAT_ID")
# Твой личный ID для рассылки и управления (Super Admin)
SUPER_ADM = ENV.get("SUPER_ADMIN_ID")
# Секретный ключ для API
ADM_SECRET = ENV.get("ADMIN_SECRET", "MRAKOTIK")
SRV_URL = ENV.get("SERVER_URL", "http://localhost:8000")

if not all([BOT_TOKEN, SB_URL, SB_KEY]):
    logger.critical("🚨 Критическая ошибка: Не все параметры указаны в .env!")
    sys.exit(1)

# Инициализация объектов
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
supabase: Client = create_client(SB_URL, SB_KEY)

# ==========================================
# 2. ЭКОНОМИЧЕСКИЙ БЛОК И КОНСТАНТЫ
# ==========================================
BASE_PRICE_RUB = 89.9

CURRENCIES = {
    "RUB": {"symbol": "₽", "rate": 1.0},
    "USD": {"symbol": "$", "rate": 0.011},
    "EUR": {"symbol": "€", "rate": 0.010},
    "BYN": {"symbol": "BYN", "rate": 0.035},
    "UAH": {"symbol": "₴", "rate": 0.43},
    "KZT": {"symbol": "₸", "rate": 5.20}
}

PERIODS = {
    1: {"label": "1 Месяц", "mult": 0.9},
    3: {"label": "3 Месяца", "mult": 2.4},
    12: {"label": "1 Год", "mult": 7.9}
}

# ==========================================
# 3. ФУНКЦИИ РАБОТЫ С ДАННЫМИ (SUPABASE)
# ==========================================

async def get_user_data(user_id: int) -> dict:
    """Получение полных данных пользователя из базы"""
    try:
        res = supabase.table("bot_users").select("*").eq("id", str(user_id)).execute()
        return res.data[0] if res.data else {}
    except Exception as e:
        logger.error(f"Error fetching user {user_id}: {e}")
        return {}

def sync_set_user(user_id: int, currency: str, username: Optional[str] = None):
    """Синхронная запись пользователя (upsert)"""
    try:
        payload = {
            "id": str(user_id),
            "currency": currency,
            "last_seen": int(datetime.utcnow().timestamp())
        }
        if username:
            payload["username"] = username
        supabase.table("bot_users").upsert(payload).execute()
    except Exception as e:
        logger.error(f"❌ DB Upsert Error: {e}")

def fetch_all_broadcast_ids() -> List[int]:
    """Загрузка всех ID для рассылки"""
    try:
        res = supabase.table("bot_users").select("id").execute()
        if not res.data:
            return []
        return [int(row['id']) for row in res.data]
    except Exception as e:
        logger.error(f"❌ DB Select All Error: {e}")
        return []

# ==========================================
# 4. ЛОГИКА ИНТЕРФЕЙСА
# ==========================================

def get_price_formatted(months: int, curr_code: str) -> str:
    conf = CURRENCIES.get(curr_code, CURRENCIES["RUB"])
    raw_price = BASE_PRICE_RUB * PERIODS[months]["mult"] * conf["rate"]
    return f"{int(round(raw_price))} {conf['symbol']}"

async def main_menu_renderer(m: Union[Message, CallbackQuery], user_id: int, edit: bool = False):
    u_data = await get_user_data(user_id)
    curr = u_data.get("currency", "RUB")
    
    kb = InlineKeyboardBuilder()
    for m_count, info in PERIODS.items():
        p_str = get_price_formatted(m_count, curr)
        kb.row(InlineKeyboardButton(text=f"🔑 {info['label']} — {p_str}", callback_data=f"buy_{m_count}"))
    
    kb.row(InlineKeyboardButton(text=f"🌍 Валюта: {curr}", callback_data="ui_currency"))
    
    text = (
        "🚀 <b>BotEngine Pro v2.0</b>\n\n"
        "Лицензия дает полный доступ к функциям конструктора. "
        "Выберите желаемый период подписки ниже:"
    )
    
    if edit and isinstance(m, CallbackQuery):
        await m.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    else:
        await m.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

# ==========================================
# 5. ОБРАБОТЧИКИ КОМАНД (HANDLERS)
# ==========================================

@dp.message(Command("start"))
async def handler_start(m: Message):
    # Регистрируем пользователя при первом входе
    sync_set_user(m.from_user.id, "RUB", m.from_user.username)
    await main_menu_renderer(m, m.from_user.id)

@dp.message(Command("broadcast"))
async def handler_broadcast(m: Message):
    """Железобетонная рассылка только для SUPER_ADMIN_ID"""
    if str(m.from_user.id) != str(SUPER_ADM):
        logger.warning(f"🚫 Попытка доступа к рассылке: {m.from_user.id}")
        return

    content = m.text.replace("/broadcast", "").strip()
    if not content:
        return await m.answer("❗ <b>Ошибка:</b> Введите текст рассылки.\nПример: <code>/broadcast Сообщение</code>", parse_mode="HTML")

    targets = fetch_all_broadcast_ids()
    if not targets:
        return await m.answer("❌ База пользователей пуста.")

    status_msg = await m.answer(f"⏳ <b>Подготовка рассылки...</b>\nЦелей: {len(targets)}", parse_mode="HTML")
    
    counts = {"ok": 0, "bad": 0, "retry": 0}
    for uid in targets:
        try:
            await bot.send_message(uid, content, parse_mode="HTML")
            counts["ok"] += 1
            await asyncio.sleep(0.05) # Плавная отправка (20 сообщений в сек)
        except TelegramForbiddenError:
            counts["bad"] += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            counts["retry"] += 1
        except Exception:
            counts["bad"] += 1

    summary = (
        f"📢 <b>Рассылка завершена!</b>\n\n"
        f"✅ Успешно: <code>{counts['ok']}</code>\n"
        f"🚫 Заблокировали: <code>{counts['bad']}</code>\n"
        f"⏳ Повторов: <code>{counts['retry']}</code>"
    )
    await status_msg.edit_text(summary, parse_mode="HTML")

@dp.callback_query(F.data == "ui_currency")
async def callback_currency_list(cb: CallbackQuery):
    kb = InlineKeyboardBuilder()
    for code in CURRENCIES.keys():
        kb.add(InlineKeyboardButton(text=code, callback_data=f"set_cur_{code}"))
    kb.adjust(3)
    await cb.message.edit_text("🌍 <b>Выберите валюту оплаты:</b>", reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("set_cur_"))
async def callback_currency_apply(cb: CallbackQuery):
    new_curr = cb.data.split("_")[2]
    sync_set_user(cb.from_user.id, new_curr, cb.from_user.username)
    await cb.answer(f"Валюта изменена на {new_curr}")
    await main_menu_renderer(cb, cb.from_user.id, edit=True)

@dp.callback_query(F.data.startswith("buy_"))
async def callback_buy_init(cb: CallbackQuery):
    months = int(cb.data.split("_")[1])
    u_data = await get_user_data(cb.from_user.id)
    price = get_price_formatted(months, u_data.get("currency", "RUB"))
    
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💳 Перейти к оплате", url="https://www.donationalerts.com/r/dialoge_engine"))
    kb.row(InlineKeyboardButton(text="✅ Подтвердить оплату", callback_data=f"check_pay_{months}"))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="ui_back"))
    
    msg = (
        f"💳 <b>Оформление подписки</b>\n"
        f"Период: <b>{PERIODS[months]['label']}</b>\n"
        f"К оплате: <b>{price}</b>\n\n"
        f"После перевода средств нажмите кнопку подтверждения."
    )
    await cb.message.edit_text(msg, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "ui_back")
async def callback_to_main(cb: CallbackQuery):
    await main_menu_renderer(cb, cb.from_user.id, edit=True)

@dp.callback_query(F.data.startswith("check_pay_"))
async def callback_verify_request(cb: CallbackQuery):
    months = int(cb.data.split("_")[2])
    u_data = await get_user_data(cb.from_user.id)
    price = get_price_formatted(months, u_data.get("currency", "RUB"))
    
    # Кнопки для админ-чата
    akb = InlineKeyboardBuilder()
    akb.row(
        InlineKeyboardButton(text="✅ Выдать", callback_data=f"api_gen_{cb.from_user.id}_{months}"),
        InlineKeyboardButton(text="❌ Отказ", callback_data=f"api_den_{cb.from_user.id}")
    )
    
    await bot.send_message(
        ADM_CHAT,
        f"📥 <b>Новая заявка на лицензию!</b>\n\n"
        f"👤 Юзер: {cb.from_user.full_name} (@{cb.from_user.username})\n"
        f"🆔 ID: <code>{cb.from_user.id}</code>\n"
        f"📦 Тариф: <b>{PERIODS[months]['label']}</b>\n"
        f"💰 Сумма: <b>{price}</b>",
        reply_markup=akb.as_markup(),
        parse_mode="HTML"
    )
    await cb.message.edit_text("⏳ <b>Заявка отправлена. Ожидайте подтверждения администратором.</b>", parse_mode="HTML")

# ==========================================
# 6. АДМИН-ЛОГИКА (УДАЛЕННОЕ УПРАВЛЕНИЕ)
# ==========================================

@dp.callback_query(F.data.startswith("api_gen_"))
async def callback_admin_approve(cb: CallbackQuery):
    _, _, uid, months = cb.data.split("_")
    await cb.message.edit_text(f"⚙️ <b>Генерация ключа для {uid}...</b>", parse_mode="HTML")
    
    try:
        api_payload = {"months": int(months), "user_id": uid}
        headers = {"x-admin-token": ADM_SECRET}
        
        response = requests.post(
            f"{SRV_URL}/api/admin/generate-key",
            json=api_payload,
            headers=headers,
            timeout=15
        )
        
        if response.status_code == 200:
            license_key = response.json().get("key")
            # Уведомляем пользователя
            await bot.send_message(
                uid, 
                f"🎉 <b>Оплата подтверждена!</b>\n\nВаш ключ:\n<code>{license_key}</code>", 
                parse_mode="HTML"
            )
            # Уведомляем админа
            await cb.message.edit_text(f"✅ Ключ <code>{license_key}</code> успешно отправлен пользователю <code>{uid}</code>", parse_mode="HTML")
        else:
            await cb.message.edit_text(f"❌ <b>Ошибка API:</b> {response.status_code}\n{response.text}", parse_mode="HTML")
    except Exception as ex:
        logger.error(f"API Connection Error: {ex}")
        await cb.message.edit_text(f"❌ <b>Ошибка связи с сервером:</b> {ex}", parse_mode="HTML")

@dp.callback_query(F.data.startswith("api_den_"))
async def callback_admin_decline(cb: CallbackQuery):
    uid = cb.data.split("_")[2]
    try:
        await bot.send_message(uid, "❌ <b>Ваш платеж не был подтвержден администратором.</b>", parse_mode="HTML")
        await cb.message.edit_text(f"🔴 Заявка пользователя <code>{uid}</code> отклонена.", parse_mode="HTML")
    except Exception:
        await cb.message.edit_text("🔴 Отклонено (юзер заблокировал бота).")

# ==========================================
# 7. ЖИЗНЕННЫЙ ЦИКЛ БОТА
# ==========================================

async def on_startup():
    logger.info("🚀 Запуск процесса LicenseBot...")
    # Установка команд в меню
    commands = [
        BotCommand(command="start", description="🏠 Главное меню / Магазин"),
        BotCommand(command="broadcast", description="📢 Рассылка (Admin Only)")
    ]
    await bot.set_my_commands(commands)

async def main():
    await on_startup()
    # Удаляем вебхук и запускаем лонг-поллинг
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("👋 Бот остановлен пользователем.")
