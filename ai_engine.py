import httpx
import json
import os
import time

class DeepSeekEngine:
    def __init__(self):
        # Токен из твоего .env
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        
        # ВАЖНО: Никаких лишних слешей в конце
        self.base_url = "https://openrouter.ai"
        self.endpoint = "/api/v1/chat/completions"
        
        # ID модели (без лишних префиксов)
        self.model = "deepseek/deepseek-r1-distill-qwen-14b"
        
        self.last_call = 0
        self.cooldown = 10 

    async def get_new_config(self, prompt, current_json):
        if time.time() - self.last_call < self.cooldown:
            return {"error": "Подождите 10 секунд (защита от спама токенами)."}

        self.last_call = time.time()
        
        full_url = f"{self.base_url}{self.endpoint}"
        
        # Обязательные заголовки для OpenRouter
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "http://localhost:3000", 
            "X-Title": "Bot Management System",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Ты — AI-админ. Возвращай ТОЛЬКО чистый JSON конфиг."},
                {"role": "user", "content": f"Config: {json.dumps(current_json)}\nRequest: {prompt}"}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"} # Чтобы не спамить лишним текстом
        }

        async with httpx.AsyncClient() as client:
            try:
                # Печатаем в консоль для проверки (потом удалишь)
                print(f"DEBUG: Отправка запроса на {full_url}")
                
                response = await client.post(
                    full_url, 
                    json=payload, 
                    headers=headers, 
                    timeout=60.0
                )
                
                # Если здесь будет 404, мы увидим это в логах
                if response.status_code != 200:
                    print(f"DEBUG: Ошибка {response.status_code}: {response.text}")
                    return {"error": f"API вернул {response.status_code}"}
                
                data = response.json()
                content = data['choices'][0]['message']['content']
                
                return json.loads(content.replace("```json", "").replace("```", "").strip())
            except Exception as e:
                return {"error": f"Connection Error: {str(e)}"}

ai_handler = DeepSeekEngine()
