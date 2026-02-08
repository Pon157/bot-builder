import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from ai_engine import ai_handler # Импортируем твой движок

app = FastAPI(title="DeepSeek AI Service")

# Модель данных для запроса
class ReconfigRequest(BaseModel):
    prompt: str
    current_config: dict

@app.post("/process")
async def process_request(req: ReconfigRequest):
    # Вызываем логику OpenRouter
    result = await ai_handler.get_new_config(req.prompt, req.current_config)
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result

if __name__ == "__main__":
    import uvicorn
    # Запускаем на отдельном порту, например 8080
    uvicorn.run(app, host="0.0.0.0", port=8080)
