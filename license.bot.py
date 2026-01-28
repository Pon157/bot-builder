
import os
import asyncio
import logging
import sys
import requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, CallbackQuery, Message

# --- Инициализация ---
BASE_DIR = "/root/bot-builder/bot-builder"
if os.path.exists(BASE_DIR):
    os.chdir(BASE_DIR)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("LicenseBot")

def load_config():
    path = os.path.join(BASE_DIR, '.env')
    conf = {}
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8-sig') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    val = v.strip().strip('"').strip("'")
                    if k.strip() == "ADMIN_BOT_TOKEN" and "root/" in val:
                        val = val.split("root/")[0].strip()
                    conf[k.strip()] = val
    return conf

CONFIG = load_config()
TOKEN = CONFIG.get("ADMIN_BOT_TOKEN")
ADMIN_SECRET = CONFIG.get("ADMIN_SECRET", "MRAKOTIK")
# ID чата администраторов, где будут подтверждаться заявки
ADMIN_CHAT_ID = CONFIG.get("ADMIN_CHAT_ID") 
SERVER_URL = "http://localhost:8000"

if not TOKEN:
    logger.critical("🛑 ADMIN_BOT_TOKEN не найден в .env!")
    sys.exit(1)

async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()

    # --- Клиентская часть ---

    @dp.message(Command("start"))
    async def cmd_start(m: Message):
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="🔑 1 Месяц (50 ⭐)", callback_data="buy_1"))
        kb.row(InlineKeyboardButton(text="🔑 3 Месяца (120 ⭐)", callback_data="buy_3"))
        kb.row(InlineKeyboardButton(text="💎 1 Год (400 ⭐)", callback_data="buy_12"))
        
        await m.answer(
            "🚀 <b>BotEngine Pro: Магазин лицензий</b>\n\n"
            "Выберите период подписки для получения ключа.\n"
            "После выбора вы получите ссылку на оплату.",
            reply_markup=kb.as_markup(), 
            parse_mode="HTML"
        )

    @dp.callback_query(F.data.startswith("buy_"))
    async def handle_buy_request(cb: CallbackQuery):
        months = int(cb.data.split("_")[1])
        price = "50 ⭐" if months == 1 else "120 ⭐" if months == 3 else "400 ⭐"
        
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="💳 Оплатить", url="https://t.me/Kotickr"))
        kb.row(InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"verify_{months}"))
        kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_start"))

        await cb.message.edit_text(
            f"🛒 <b>Оформление подписки</b>\n\n"
            f"Тариф: <b>{months} мес.</b>\n"
            f"К оплате: <b>{price}</b>\n\n"
            f"1. Напишите оператору по ссылке ниже.\n"
            f"2. Совершите перевод.\n"
            f"3. Нажмите кнопку «Я оплатил».\n\n"
            f"<i>Ваша заявка будет отправлена модераторам.</i>",
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )

    @dp.callback_query(F.data.startswith("verify_"))
    async def handle_verify_payment(cb: CallbackQuery):
        if not ADMIN_CHAT_ID:
            return await cb.answer("❌ Ошибка: чат админов не настроен", show_alert=True)
            
        months = int(cb.data.split("_")[1])
        user = cb.from_user
        
        # Отправляем уведомление в чат админов
        admin_kb = InlineKeyboardBuilder()
        admin_kb.row(
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"adm_approve_{user.id}_{months}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm_decline_{user.id}")
        )

        try:
            await bot.send_message(
                ADMIN_CHAT_ID,
                f"🆕 <b>Новая заявка на оплату!</b>\n\n"
                f"Пользователь: {user.full_name} (@{user.username})\n"
                f"ID: <code>{user.id}</code>\n"
                f"Тариф: <b>{months} мес.</b>\n\n"
                f"Проверьте оплату и нажмите кнопку ниже:",
                reply_markup=admin_kb.as_markup(),
                parse_mode="HTML"
            )
            await cb.message.edit_text(
                "✅ <b>Заявка отправлена!</b>\n\n"
                "Администраторы проверят ваш платеж. Обычно это занимает от 5 до 30 минут.\n"
                "Вы получите уведомление в этом боте вместе с ключом активации.",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Error sending to admin: {e}")
            await cb.answer("❌ Ошибка отправки заявки", show_alert=True)

    @dp.callback_query(F.data == "back_to_start")
    async def back_to_start(cb: CallbackQuery):
        await cmd_start(cb.message)

    # --- Админская часть (Обработка кнопок в админ-чате) ---

    @dp.callback_query(F.data.startswith("adm_approve_"))
    async def admin_approve(cb: CallbackQuery):
        # Проверка, что нажал админ (в нужном чате)
        if str(cb.message.chat.id) != str(ADMIN_CHAT_ID):
            return await cb.answer("У вас нет прав здесь.", show_alert=True)

        parts = cb.data.split("_")
        target_user_id = int(parts[2])
        months = int(parts[3])

        await cb.message.edit_text(f"⏳ Генерирую ключ для {target_user_id}...")

        try:
            # Запрос к серверу на генерацию ключа
            r = requests.post(
                f"{SERVER_URL}/api/admin/generate-key",
                json={"months": months},
                headers={"x-admin-token": ADMIN_SECRET},
                timeout=10
            )
            
            if r.status_code == 200:
                key = r.json().get("key")
                # Уведомляем пользователя
                try:
                    await bot.send_message(
                        target_user_id,
                        f"🎉 <b>Оплата подтверждена!</b>\n\n"
                        f"Ваш ключ активации ({months} мес.):\n"
                        f"<code>{key}</code>\n\n"
                        f"Скопируйте его и вставьте в личном кабинете.",
                        parse_mode="HTML"
                    )
                    await cb.message.edit_text(f"✅ Оплачено. Ключ {key} отправлен пользователю {target_user_id}.")
                except:
                    await cb.message.edit_text(f"⚠️ Ключ {key} создан, но не удалось отправить его юзеру (бот заблокирован?).")
            else:
                await cb.message.edit_text(f"❌ Ошибка API сервера: {r.status_code}")
        except Exception as e:
            await cb.message.edit_text(f"❌ Ошибка связи с API: {e}")

    @dp.callback_query(F.data.startswith("adm_decline_"))
    async def admin_decline(cb: CallbackQuery):
        if str(cb.message.chat.id) != str(ADMIN_CHAT_ID):
            return await cb.answer("У вас нет прав.", show_alert=True)

        target_user_id = int(cb.data.split("_")[2])
        
        try:
            await bot.send_message(
                target_user_id,
                "❌ <b>Ваш платеж не был подтвержден.</b>\n\n"
                "Если вы уверены, что оплата прошла, свяжитесь с поддержкой: @Kotickr",
                parse_mode="HTML"
            )
            await cb.message.edit_text(f"🔴 Заявка пользователя {target_user_id} отклонена.")
        except:
            await cb.message.edit_text(f"🔴 Отклонено. Не удалось уведомить пользователя.")

    logger.info("✨ Бот лицензий запущен в режиме модерации")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
