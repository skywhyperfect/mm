from fastapi import APIRouter, HTTPException
import json
from app.database import supabase
from app.ai_client import chat

router = APIRouter()

@router.get("/{user_id}")
async def get_reputation(user_id: str):
    """Генерация Trust Score и предсказания поведения на лету"""
    
    # 1. Получаем данные пользователя
    user_res = supabase.table("users").select("name,role,skills").eq("id", user_id).single().execute()
    if not user_res.data:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    user = user_res.data
    
    if user["role"] != "volunteer":
        raise HTTPException(status_code=400, detail="Репутация доступна только для волонтёров")

    # 2. Получаем историю заявок (applications)
    apps_res = supabase.table("applications").select("*, tasks(title)").eq("volunteer_id", user_id).execute()
    applications = apps_res.data or []
    
    # 3. Собираем статистику и отзывы
    total_tasks = len(applications)
    accepted_tasks = 0
    rejected_tasks = 0
    feedbacks = []
    
    for app in applications:
        if app["status"] == "accepted":
            accepted_tasks += 1
        elif app["status"] == "rejected":
            rejected_tasks += 1
            
        # Проверяем, есть ли верификация для этой задачи (откуда берем AI comment/feedback)
        ver_res = supabase.table("verifications").select("verdict, ai_comment").eq("application_id", app["id"]).execute()
        if ver_res.data:
            verdict = ver_res.data[0]["verdict"]
            comment = ver_res.data[0]["ai_comment"]
            feedbacks.append(f"Задача '{app['tasks']['title']}': Вердикт - {verdict}, Отзыв ИИ - {comment}")

    # 4. Формируем досье для LLM
    dossier = f"""
    Имя волонтёра: {user['name']}
    Навыки: {', '.join(user.get('skills', []))}
    Всего откликов: {total_tasks}
    Принято на задач: {accepted_tasks}
    Отказано/не пройдено: {rejected_tasks}
    
    Отзывы по выполненным задачам (от ИИ верификатора):
    {'\n'.join(feedbacks) if feedbacks else "Пока нет отзывов по выполненным задачам."}
    """

    # 5. Промпт для генерации Trust Score
    prompt = f"""Ты — AI-репутационный аналитик платформы Sun Proactive.
Твоя задача — оценить надежность волонтёра (Trust Score) и предсказать его поведение на основе истории.

ДОСЬЕ ВОЛОНТЁРА:
{dossier}

Проанализируй эти данные и верни результат СТРОГО в формате JSON:
{{
  "trust_score": <число от 0 до 100>,
  "risk_level": "<low | medium | high>",
  "explanation": "<Краткое объяснение (1-2 предложения), почему такой score>",
  "prediction": "<Прогноз (например: С вероятностью 85% выполнит задачу без напоминаний)>"
}}
Убедись, что твой ответ содержит ТОЛЬКО валидный JSON!"""

    # 6. Запрашиваем ответ у LLM
    ai_response = await chat([{"role": "user", "content": prompt}])
    
    # Пытаемся распарсить JSON
    try:
        json_start = ai_response.find("{")
        json_end = ai_response.rfind("}") + 1
        parsed_response = json.loads(ai_response[json_start:json_end])
        
        return {
            "user_id": user_id,
            "stats": {
                "total_applications": total_tasks,
                "accepted": accepted_tasks,
                "rejected": rejected_tasks
            },
            "reputation": parsed_response
        }
    except Exception as e:
        print(f"Ошибка парсинга ответа репутации: {e}\nОтвет LLM: {ai_response}")
        # Запасной вариант если LLM не выдал JSON
        return {
            "user_id": user_id,
            "stats": {"total_applications": total_tasks, "accepted": accepted_tasks, "rejected": rejected_tasks},
            "reputation": {
                "trust_score": 50 if total_tasks == 0 else 75,
                "risk_level": "medium",
                "explanation": "Не удалось сгенерировать точный анализ из-за ошибки формата ответа ИИ.",
                "prediction": "Недостаточно данных для точного прогноза."
            }
        }
