import os
import asyncio
import logging
import sys
import requests
import json
from datetime import datetime
from typing import List, Optional, Union

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import (
    InlineKeyboardButton, CallbackQuery, Message, 
    BotCommand, BotCommandScopeChat
)
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from supabase import create_client, Client

# ==========================================
# 1. КОНФИГУРАЦИЯ И ГЛУБОКОЕ ЛОГИРОВАНИЕ
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
    """
    Железобетонное чтение .env с очисткой токенов.
    Использует инструкцию по извлечению токена из переменной окружения.
    """
    path = os.path.join(BASE_DIR, '.env')
    conf = {}
    if not os.path.exists(path):
        logger.warning("⚠️ Файл .env отсутствует, используются дефолтные значения")
        return conf
    
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                val = v.strip().strip('"').strip("'")
                
                # Специальная логика извлечения токена
                if k.strip() == "ADMIN_BOT_TOKEN" and "root/" in val:
                    val = val.split("root/")[0].strip()
                conf[k.strip()] = val
    except Exception as e:
        logger.error(f"Критическая ошибка парсинга конфига: {e}")
    return conf

# Загрузка окружения
ENV = load_env_secure()
BOT_TOKEN = ENV.get("ADMIN_BOT_TOKEN")
SB_URL = ENV.get("SUPABASE_URL")
SB_KEY = ENV.get("SUPABASE_KEY")
ADM_CHAT = ENV.get("ADMIN_CHAT_ID")
ADM_SECRET = ENV.get("ADMIN_SECRET", "MRAKOTIK")
SRV_URL = ENV.get("SERVER_URL", "http://localhost:8000")

# Твой личный ID (Super Admin) — жестко вшит для безопасности
# Он используется для рассылки, в то время как ADM_CHAT — для уведомлений.
SUPER_ADMIN_ID = 5883703466

if not all([BOT_TOKEN, SB_URL, SB_KEY]):
    logger.critical("🛑 Ошибка: Проверьте .env (Токен или Supabase отсутствуют)")
    sys.exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
supabase: Client = create_client(SB_URL, SB_KEY)

# ==========================================
# 2. ЭКОНОМИЧЕСКАЯ МОДЕЛЬ И КОНСТАНТЫ
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
    3: {"label": "3 Месяца", "mult": 2.3},
    12: {"label": "1 Год", "mult": 7.7}
}

# ==========================================
# 3. ФУНКЦИИ БАЗЫ ДАННЫХ (SUPABASE)
# ==========================================

async def db_get_user_currency(user_id: int):
    """Получение валюты пользователя из таблицы bot_users"""
    try:
        res = supabase.table("bot_users").select("currency").eq("id", str(user_id)).execute()
        if res.data and 'currency' in res.data[0]:
            return res.data[0]['currency']
    except Exception as e:
        logger.error(f"Ошибка DB при получении валюты: {e}")
    return "RUB"

def db_sync_user(user_id: int, currency: str, username: str = None):
    """Синхронизация данных пользователя в Supabase"""
    try:
        data = {
            "id": str(user_id), 
            "currency": currency,
            "updated_at": datetime.utcnow().isoformat()
        }
        if username:
            data["username"] = username
        supabase.table("bot_users").upsert(data).execute()
    except Exception as e:
        logger.error(f"Ошибка синхронизации юзера {user_id}: {e}")

def db_fetch_all_users_for_broadcast():
    """Извлекает все ID пользователей для массовой рассылки"""
    try:
        res = supabase.table("bot_users").select("id").execute()
        if res.data:
            return [int(u['id']) for u in res.data]
        return []
    except Exception as e:
        logger.error(f"Ошибка получения списка всех юзеров: {e}")
        return []

# ==========================================
# 4. ЛОГИКА ИНТЕРФЕЙСА (UI РЕНДЕРИНГ)
# ==========================================

def calculate_current_price(months: int, code: str):
    """Расчет цены с учетом выбранной валюты и тарифа"""
    c = CURRENCIES.get(code, CURRENCIES["RUB"])
    val = int(round(BASE_PRICE_RUB * PERIODS[months]["mult"] * c["rate"]))
    return f"{val} {c['symbol']}"

async def render_main_menu(m: Union[Message, CallbackQuery], user_id: int, edit: bool = False):
    """Отрисовка главного экрана магазина лицензий"""
    curr = await db_get_user_currency(user_id)
    kb = InlineKeyboardBuilder()
    
    # Генерация кнопок тарифов
    for m_count, info in PERIODS.items():
        price_tag = calculate_current_price(m_count, curr)
        kb.row(InlineKeyboardButton(
            text=f"🔑 {info['label']} — {price_tag}", 
            callback_data=f"buy_{m_count}"
        ))
    
    # Кнопка смены валюты
    kb.row(InlineKeyboardButton(text=f"🌍 Валюта: {curr}", callback_data="ui_currency_select"))
    
    txt = (
        "🚀 <b>BotEngine Pro: Лицензионный центр</b>\n\n"
        "Выберите желаемый период подписки ниже. "
        "Ключ будет сгенерирован автоматически после подтверждения оплаты."
    )
    
    if edit and isinstance(m, CallbackQuery):
        await m.message.edit_text(txt, reply_markup=kb.as_markup(), parse_mode="HTML")
    else:
        await m.answer(txt, reply_markup=kb.as_markup(), parse_mode="HTML")

# ==========================================
# 5. ОБРАБОТЧИКИ (HANDLERS)
# ==========================================

@dp.message(Command("start"))
async def handler_start(m: Message):
    """
    Обработка команды /start. 
    Скрывает команду /broadcast от обычных пользователей.
    """
    # Персональное меню команд для Super Admin
    if m.from_user.id == SUPER_ADMIN_ID:
        admin_cmds = [
            BotCommand(command="start", description="🏠 Главная"),
            BotCommand(command="broadcast", description="📢 Массовая рассылка")
        ]
        await bot.set_my_commands(admin_cmds, scope=BotCommandScopeChat(chat_id=m.from_user.id))
    
    # Регистрация пользователя
    user_curr = await db_get_user_currency(m.from_user.id)
    db_sync_user(m.from_user.id, user_curr, m.from_user.username)
    
    await render_main_menu(m, m.from_user.id)

@dp.message(Command("broadcast"))
async def handler_broadcast(m: Message):
    """
    Функция рассылки. 
    Доступна только для SUPER_ADMIN_ID.
    Реализована защита от флуда и блокировок.
    """
    if m.from_user.id != SUPER_ADMIN_ID:
        logger.warning(f"Попытка доступа к /broadcast от {m.from_user.id}")
        return # Игнорируем всех, кто не админ

    # Извлекаем текст после команды
    broadcast_content = m.text.replace("/broadcast", "").strip()
    if not broadcast_content:
        return await m.answer(
            "⚠️ <b>Ошибка рассылки!</b>\n\n"
            "Введите текст сообщения сразу после команды.\n"
            "Пример: <code>/broadcast Внимание, обновление!</code>", 
            parse_mode="HTML"
        )

    all_users = db_fetch_all_users_for_broadcast()
    if not all_users:
        return await m.answer("❌ База данных пользователей пуста.")

    status_report = await m.answer(f"⏳ <b>Рассылка запущена...</b>\nВсего целей: {len(all_users)}")
    
    success_count = 0
    fail_count = 0
    
    for user_id in all_users:
        try:
            await bot.send_message(user_id, broadcast_content, parse_mode="HTML")
            success_count += 1
            # Задержка для обхода спам-фильтров Telegram
            await asyncio.sleep(0.05) 
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            await bot.send_message(user_id, broadcast_content, parse_mode="HTML")
            success_count += 1
        except (TelegramForbiddenError, Exception):
            fail_count += 1
            continue
    
    final_txt = (
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📧 Доставлено: <code>{success_count}</code>\n"
        f"🚫 Ошибок: <code>{fail_count}</code>"
    )
    await status_report.edit_text(final_txt, parse_mode="HTML")

@dp.callback_query(F.data == "ui_currency_select")
async def handler_currency_menu(cb: CallbackQuery):
    """Меню выбора валюты"""
    kb = InlineKeyboardBuilder()
    for code in CURRENCIES.keys():
        kb.add(InlineKeyboardButton(text=code, callback_data=f"save_curr_{code}"))
    kb.adjust(3)
    await cb.message.edit_text("🌍 <b>Выберите валюту оплаты:</b>", reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("save_curr_"))
async def handler_currency_save(cb: CallbackQuery):
    """Сохранение выбранной валюты в БД"""
    new_code = cb.data.split("_")[2]
    db_sync_user(cb.from_user.id, new_code, cb.from_user.username)
    await cb.answer(f"Валюта изменена на {new_code}")
    await render_main_menu(cb, cb.from_user.id, edit=True)

@dp.callback_query(F.data.startswith("buy_"))
async def handler_buy_init(cb: CallbackQuery):
    """Экран подтверждения покупки и ссылка на оплату"""
    months = int(cb.data.split("_")[1])
    u_curr = await db_get_user_currency(cb.from_user.id)
    price_formatted = calculate_current_price(months, u_curr)
    
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💳 Оплатить заказ", url="https://www.donationalerts.com/r/dialoge_engine"))
    kb.row(InlineKeyboardButton(text="📜 Правила возврата", url="https://telegra.ph/Politika-vozvrata-i-licenzirovaniya-Refund-Policy-02-06"))
    kb.row(InlineKeyboardButton(text="✅ Подтвердить оплату", callback_data=f"verify_pay_{months}"))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="ui_back_to_menu"))
    
    msg_body = (
        f"🛒 <b>Оформление: {PERIODS[months]['label']}</b>\n"
        f"К оплате: <b>{price_formatted}</b>\n\n"
        f"1. Нажмите 'Оплатить' и сделайте перевод.\n"
        f"2. После оплаты нажмите кнопку подтверждения.\n"
        f"3. Админ проверит транзакцию и вышлет ключ."
    )
    
    await cb.message.edit_text(msg_body, reply_markup=kb.as_markup(), parse_mode="HTML", disable_web_page_preview=True)

@dp.callback_query(F.data == "ui_back_to_menu")
async def handler_ui_back(cb: CallbackQuery):
    await render_main_menu(cb, cb.from_user.id, edit=True)

@dp.callback_query(F.data.startswith("verify_pay_"))
async def handler_admin_notification(cb: CallbackQuery):
    """Отправка заявки в чат администратора"""
    months = int(cb.data.split("_")[2])
    u_curr = await db_get_user_currency(cb.from_user.id)
    price_val = calculate_current_price(months, u_curr)
    
    # Кнопки для админ-чата (ADM_CHAT)
    admin_kb = InlineKeyboardBuilder()
    admin_kb.row(
        InlineKeyboardButton(text="✅ Выдать ключ", callback_data=f"api_approve_{cb.from_user.id}_{months}"),
        InlineKeyboardButton(text="❌ Отказать", callback_data=f"api_decline_{cb.from_user.id}")
    )
    
    await bot.send_message(
        ADM_CHAT,
        f"💰 <b>НОВАЯ ЗАЯВКА!</b>\n\n"
        f"👤 Клиент: {cb.from_user.full_name} (@{cb.from_user.username})\n"
        f"🆔 ID: <code>{cb.from_user.id}</code>\n"
        f"📦 Тариф: {months} мес.\n"
        f"💵 Сумма: {price_val}",
        reply_markup=admin_kb.as_markup(),
        parse_mode="HTML"
    )
    
    await cb.message.edit_text(
        "⏳ <b>Заявка на проверке!</b>\n\n"
        "Мы получили ваш запрос. Ключ придет в этот чат после подтверждения.", 
        parse_mode="HTML"
    )

# ==========================================
# 6. АДМИН-ЛОГИКА (УПРАВЛЕНИЕ ЧЕРЕЗ API)
# ==========================================

@dp.callback_query(F.data.startswith("api_approve_"))
async def handler_api_generate(cb: CallbackQuery):
    """Генерация ключа через внешний API и отправка пользователю"""
    _, _, uid, m_count = cb.data.split("_")
    await cb.message.edit_text(f"⚙️ Выполняю генерацию для {uid}...")
    
    try:
        api_req = {
            "months": int(m_count), 
            "user_id": str(uid)
        }
        api_headers = {"x-admin-token": ADM_SECRET}
        
        resp = requests.post(
            f"{SRV_URL}/api/admin/generate-key", 
            json=api_req, 
            headers=api_headers, 
            timeout=15
        )
        
        if resp.status_code == 200:
            lic_key = resp.json().get("key")
            # Отправка юзеру
            await bot.send_message(
                uid, 
                f"🎉 <b>Лицензия активирована!</b>\n\nВаш ключ доступа:\n<code>{lic_key}</code>", 
                parse_mode="HTML"
            )
            # Отчет админу
            await cb.message.edit_text(f"✅ Ключ <code>{lic_key}</code> отправлен пользователю <code>{uid}</code>")
        else:
            await cb.message.edit_text(f"❌ Ошибка API сервера: {resp.status_code}")
            
    except Exception as err:
        logger.error(f"API Error: {err}")
        await cb.message.edit_text(f"❌ Ошибка соединения с API: {err}")

@dp.callback_query(F.data.startswith("api_decline_"))
async def handler_api_reject(cb: CallbackQuery):
    """Отклонение заявки пользователю"""
    user_to_notify = cb.data.split("_")[2]
    try:
        await bot.send_message(user_to_notify, "❌ <b>Ваш платеж не подтвержден администратором.</b>", parse_mode="HTML")
        await cb.message.edit_text(f"🔴 Заявка {user_to_notify} была отклонена.")
    except Exception:
        await cb.message.edit_text(f"🔴 Отклонено, но не удалось уведомить {user_to_notify}.")

# ==========================================
# 7. ЗАПУСК ПРИЛОЖЕНИЯ
# ==========================================

async def main():
    """Точка входа и инициализация лонг-поллинга"""
    logger.info("🚀 Бот BotEngine Pro запускается...")
    
    # Сбрасываем старые команды для чистоты
    await bot.delete_my_commands()
    # Устанавливаем общее меню
    await bot.set_my_commands([BotCommand(command="start", description="🏠 Магазин / Меню")])
    
    # Очистка очереди обновлений и старт
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("👋 Работа бота завершена.")
