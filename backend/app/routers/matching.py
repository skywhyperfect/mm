from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import numpy as np
from app.database import supabase
from app.ai_client import chat, embed

router = APIRouter()

class ApplyRequest(BaseModel):
    task_id: str
    volunteer_id: str

def cosine_similarity(a, b) -> float:
    """Вычисляем cosine similarity между двумя векторами"""
    # Конвертируем из строк если нужно
    if isinstance(a, str):
        import json
        a = json.loads(a)
    if isinstance(b, str):
        import json
        b = json.loads(b)
    a, b = np.array(a, dtype=float), np.array(b, dtype=float)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    if norm == 0:
        return 0.0
    return float(np.dot(a, b) / norm)

@router.post("/apply")
async def apply_to_task(data: ApplyRequest):
    """Волонтёр откликается на задачу — система считает match score и генерирует объяснение"""

    # Получаем задачу и волонтёра
    task_res = supabase.table("tasks").select("*").eq("id", data.task_id).single().execute()
    user_res = supabase.table("users").select("*").eq("id", data.volunteer_id).single().execute()

    if not task_res.data or not user_res.data:
        raise HTTPException(status_code=404, detail="Задача или пользователь не найдены")

    task = task_res.data
    volunteer = user_res.data

    # Если у волонтёра нет эмбеддинга — создаём
    if not volunteer.get("embedding"):
        bio_text = f"{volunteer['name']} {volunteer.get('bio', '')} {' '.join(volunteer.get('skills', []))} {volunteer.get('goals', '')}"
        volunteer_embedding = await embed(bio_text)
        supabase.table("users").update({"embedding": volunteer_embedding}).eq("id", data.volunteer_id).execute()
    else:
        volunteer_embedding = volunteer["embedding"]

    # Считаем cosine similarity
    task_embedding = task.get("embedding")
    if not task_embedding:
        raise HTTPException(status_code=400, detail="У задачи нет эмбеддинга")

    match_score = cosine_similarity(task_embedding, volunteer_embedding)
    match_percent = round(match_score * 100, 1)

    # Explainable AI: генерируем объяснение мэтча
    explain_prompt = f"""Ты — AI-рекрутер платформы Sun Proactive.
Объясни куратору, почему этот волонтёр подходит (или не подходит) для задачи.

ЗАДАЧА:
- Название: {task['title']}
- Описание: {task['description']}
- Нужные навыки: {', '.join(task.get('hard_skills', []) + task.get('soft_skills', []))}

ВОЛОНТЁР:
- Имя: {volunteer['name']}
- О себе: {volunteer.get('bio', 'не указано')}
- Навыки: {', '.join(volunteer.get('skills', []))}
- Цели: {volunteer.get('goals', 'не указаны')}

Оценка совместимости: {match_percent}%

Напиши 2-3 предложения объяснения на русском языке. Будь конкретным — ссылайся на конкретные навыки и опыт волонтёра."""

    explanation = await chat([{"role": "user", "content": explain_prompt}])

    # Сохраняем отклик в БД
    app_result = supabase.table("applications").upsert({
        "task_id": data.task_id,
        "volunteer_id": data.volunteer_id,
        "match_score": match_score,
        "match_explanation": explanation,
        "status": "pending",
    }).execute()

    return {
        "application_id": app_result.data[0]["id"],
        "match_score": match_score,
        "match_percent": match_percent,
        "match_explanation": explanation,
    }


@router.get("/recommend/{task_id}")
async def recommend_volunteers(task_id: str, limit: int = 5):
    """Рекомендовать топ-N волонтёров для задачи по semantic similarity"""

    task_res = supabase.table("tasks").select("*").eq("id", task_id).single().execute()
    if not task_res.data:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    task = task_res.data
    task_embedding = task.get("embedding")
    if not task_embedding:
        raise HTTPException(status_code=400, detail="У задачи нет эмбеддинга")

    # Получаем всех волонтёров с эмбеддингами
    volunteers_res = supabase.table("users").select("*").eq("role", "volunteer").not_.is_("embedding", "null").execute()
    volunteers = volunteers_res.data

    # Считаем similarity для каждого
    scored = []
    for v in volunteers:
        if v.get("embedding"):
            score = cosine_similarity(task_embedding, v["embedding"])
            scored.append({**v, "match_score": score, "match_percent": round(score * 100, 1)})

    # Сортируем по убыванию score
    scored.sort(key=lambda x: x["match_score"], reverse=True)
    top = scored[:limit]

    # Генерируем объяснение для каждого
    for candidate in top:
        explain_prompt = f"""Объясни в 1-2 предложениях, почему {candidate['name']} подходит для задачи "{task['title']}".
Навыки задачи: {', '.join(task.get('hard_skills', []) + task.get('soft_skills', []))}.
Навыки волонтёра: {', '.join(candidate.get('skills', []))}.
Опыт: {candidate.get('bio', 'не указан')}.
Будь конкретным."""
        candidate["match_explanation"] = await chat([{"role": "user", "content": explain_prompt}])
        # Убираем вектор из ответа (слишком большой)
        candidate.pop("embedding", None)

    return {"task_id": task_id, "recommendations": top}
