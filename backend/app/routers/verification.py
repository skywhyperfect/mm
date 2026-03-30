# app/routers/verification.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime
from app.database import supabase
from app.ai_client import chat_with_image

router = APIRouter()

class VerifyRequest(BaseModel):
    application_id: str
    photo_url: str  # URL загруженного фото (через Supabase Storage)

@router.post("/verify")
async def verify_work(data: VerifyRequest):
    """Vision верификация: анализируем фото и выдаём вердикт"""

    # Получаем заявку и задачу
    app_res = supabase.table("applications").select("*, tasks(title, description, location)").eq("id", data.application_id).single().execute()
    if not app_res.data:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    application = app_res.data
    task = application["tasks"]

    prompt = f"""Ты — система верификации выполненных волонтёрских задач.

Задача была: "{task['title']}"
Описание: {task['description']}
Место: {task.get('location', 'не указано')}

Волонтёр загрузил фото как подтверждение выполнения работы.

Проанализируй фото и ответь:
1. Соответствует ли фото описанию задачи?
2. Видно ли, что работа выполнена?

Выдай ответ СТРОГО в формате:
VERDICT: approved или rejected
COMMENT: твой комментарий на русском (1-2 предложения)"""

    ai_response = await chat_with_image([], data.photo_url, prompt)

    # Парсим вердикт
    verdict = "pending"
    comment = ai_response
    if "VERDICT: approved" in ai_response:
        verdict = "approved"
    elif "VERDICT: rejected" in ai_response:
        verdict = "rejected"

    comment = ai_response.replace("VERDICT: approved", "").replace("VERDICT: rejected", "").replace("COMMENT:", "").strip()

    # Сохраняем верификацию
    result = supabase.table("verifications").insert({
        "application_id": data.application_id,
        "photo_url": data.photo_url,
        "verdict": verdict,
        "ai_comment": comment,
        "verified_at": datetime.utcnow().isoformat(),
    }).execute()

    # Обновляем статус заявки
    if verdict == "approved":
        supabase.table("applications").update({"status": "accepted"}).eq("id", data.application_id).execute()

    return {
        "verdict": verdict,
        "comment": comment,
        "verification_id": result.data[0]["id"],
    }
