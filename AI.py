import os
import json
import httpx
import asyncio
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from supabase import create_client, Client

from dotenv import load_dotenv

load_dotenv()

# --- КОНФИГУРАЦИЯ ---
# Токен берем из .env, как ты просил
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY") # Твой ключ OpenRouter

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

class BotAIInstance:
    def __init__(self, bot_id, admin_chat_id):
        self.bot_id = bot_id
        self.admin_chat_id = int(admin_chat_id)
        self.bot = Bot(token=API_TOKEN)
        self.dp = Dispatcher()
        self.router = Router()
        
        # Состояние бота (подгружается из Supabase)
        self.welcome_text = "Привет! Я твой бот."
        self.buttons = [] # Список кнопок
        
        self.register_handlers()
        self.dp.include_router(self.router)

    def get_keyboard(self):
        """Генерирует клавиатуру на основе self.buttons"""
        if not self.buttons:
            return None
        keyboard = [[KeyboardButton(text=btn['text'])] for btn in self.buttons]
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

    async def ai_reconfigure(self, prompt: str):
        """Обращение к DeepSeek R1 через OpenRouter"""
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "HTTP-Referer": "http://localhost:3000",
            "Content-Type": "application/json"
        }
        
        # Текущий конфиг для контекста ИИ
        current_config = {
            "welcome_text": self.welcome_text,
            "buttons": self.buttons
        }

        payload = {
            "model": "deepseek/deepseek-r1-distill-qwen-14b",
            "messages": [
                {"role": "system", "content": "Ты AI-админ. Измени JSON конфиг бота по запросу. Верни ТОЛЬКО чистый JSON. Формат: {'welcome_text': str, 'buttons': [{'text': str, 'answer': str}]}"},
                {"role": "user", "content": f"Запрос: {prompt}\nТекущий конфиг: {json.dumps(current_config)}"}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }

        async with httpx.AsyncClient() as client:
            try:
                r = await client.post(url, json=payload, headers=headers, timeout=60.0)
                data = r.json()
                new_cfg = json.loads(data['choices'][0]['message']['content'])
                
                # Применяем изменения
                self.welcome_text = new_cfg.get("welcome_text", self.welcome_text)
                self.buttons = new_cfg.get("buttons", self.buttons)
                
                # Сохраняем в Supabase
                supabase.table("bots").update({
                    "welcome_text": self.welcome_text,
                    "buttons": self.buttons
                }).eq("id", self.bot_id).execute()
                
                return True
            except Exception as e:
                print(f"AI Error: {e}")
                return False

    def register_handlers(self):
        # Команда /start
        @self.router.message(F.text == "/start")
        async def start_cmd(m: Message):
            await m.answer(self.welcome_text, reply_markup=self.get_keyboard())

        # Обработка ИИ-команд от админа
        @self.router.message(F.chat.id == self.admin_chat_id, F.text.lower().startswith("ии "))
        async def admin_ai_mode(m: Message):
            prompt = m.text[3:].strip()
            wait = await m.answer("⏳ <b>DeepSeek перенастраивает бота...</b>", parse_mode="HTML")
            
            if await self.ai_reconfigure(prompt):
                await wait.edit_text("✅ <b>Настройки обновлены и сохранены!</b>", parse_mode="HTML")
            else:
                await wait.edit_text("❌ Ошибка при связи с OpenRouter.")

        # Обработка нажатий на кнопки
        @self.router.message()
        async def handle_buttons(m: Message):
            for btn in self.buttons:
                if m.text == btn['text']:
                    await m.answer(btn.get('answer', 'Нет ответа'))
                    return

    async def start(self):
        print(f"Бот {self.bot_id} запущен...")
        await self.dp.start_polling(self.bot)

# --- ЗАПУСК ---
if __name__ == "__main__":
    # ID бота и твой ID из Supabase/Env
    admin_id = os.getenv("ADMIN_CHAT_ID, 5883703466")
    bot_instance = BotAIInstance(bot_id="main_bot", admin_chat_id=admin_id)
    asyncio.run(bot_instance.start())
