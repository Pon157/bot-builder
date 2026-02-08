import httpx
import json
import os
import time

class DeepSeekEngine:
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY") # Берем из .env
        self.url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = "deepseek/deepseek-r1-distill-qwen-14b"
        self.cooldown = 10 
        self.last_call = 0

    async def get_new_config(self, prompt, current_json):
        if time.time() - self.last_call < self.cooldown:
            return {"error": "Подожди 10 секунд, не спамь токенами."}
        
        self.last_call = time.time()
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "http://localhost:3000",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Ты AI-админ. Измени JSON конфиг бота. Верни ТОЛЬКО чистый JSON без текста."},
                {"role": "user", "content": f"Запрос: {prompt}\nТекущий конфиг: {json.dumps(current_json)}"}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }

        async with httpx.AsyncClient() as client:
            try:
                r = await client.post(self.url, json=payload, headers=headers, timeout=60.0)
                res = r.json()
                content = res['choices'][0]['message']['content']
                return json.loads(content.replace("```json", "").replace("```", "").strip())
            except Exception as e:
                return {"error": str(e)}

ai_handler = DeepSeekEngine()
