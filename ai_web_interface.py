from fastapi import FastAPI, Body
from ai_engine import ai_handler
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Разрешаем запросы с твоего сайта
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.post("/process_ai")
async def process_ai(data: dict = Body(...)):
    bot_id = data.get("bot_id")
    command = data.get("command")
    current_cfg = data.get("current_config") # Оверлей присылает текущий конфиг из браузера

    new_cfg = await ai_handler.get_new_config(command, current_cfg)
    
    if "error" in new_cfg:
        return {"status": "error", "message": new_cfg["error"]}
    
    # Тут можно добавить сохранение в Supabase напрямую
    return {"status": "success", "new_config": new_cfg}
