from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import json
from app.database import supabase
from app.ai_client import chat, embed

router = APIRouter()

# ─── Модели запросов ───────────────────────────────────────────────

class InterviewMessage(BaseModel):
    session_id: Optional[str] = None
    curator_id: str
    message: str

class RAGQuestion(BaseModel):
    task_id: str
    question: str

class TaskCreate(BaseModel):
    curator_id: str
    title: str
    description: str
    date: Optional[str] = None
    location: Optional[str] = None
    volunteers_needed: int = 1
    hard_skills: list[str] = []
    soft_skills: list[str] = []

# ─── AI-Интервьюер ─────────────────────────────────────────────────

INTERVIEW_SYSTEM_PROMPT = """Ты — AI-ассистент платформы Sun Proactive для социальных задач.
Твоя цель: провести короткое интервью с куратором и собрать всю необходимую информацию о задаче.

Тебе нужно узнать:
1. Название задачи
2. Подробное описание
3. Дату и время
4. Локацию (место проведения)
5. Сколько волонтёров нужно
6. Необходимые hard skills (конкретные навыки: вождение, SMM, медицина и т.д.)
7. Необходимые soft skills (коммуникабельность, ответственность и т.д.)

Задавай уточняющие вопросы по одному. Будь дружелюбным и кратким.
Когда у тебя есть ВСЯ информация, заверши интервью словом [COMPLETE] и выдай JSON:
{
  "title": "...",
  "description": "...",
  "date": "ISO дата или null",
  "location": "...",
  "volunteers_needed": число,
  "hard_skills": ["навык1", "навык2"],
  "soft_skills": ["навык1", "навык2"]
}"""

@router.post("/interview")
async def interview(data: InterviewMessage):
    """AI-интервьюер: диалог для создания задачи"""

    # Получаем или создаём сессию
    if data.session_id:
        result = supabase.table("interview_sessions").select("*").eq("id", data.session_id).single().execute()
        session = result.data
        messages = session["messages"]
    else:
        messages = []
        session = None

    # Добавляем сообщение пользователя
    messages.append({"role": "user", "content": data.message})

    # Запрос к AI
    full_messages = [{"role": "system", "content": INTERVIEW_SYSTEM_PROMPT}] + messages
    ai_response = await chat(full_messages)

    # Добавляем ответ AI
    messages.append({"role": "assistant", "content": ai_response})

    # Проверяем — завершено ли интервью
    is_complete = "[COMPLETE]" in ai_response
    task_id = None

    if is_complete:
        # Извлекаем JSON из ответа
        try:
            json_start = ai_response.index("{")
            json_end = ai_response.rindex("}") + 1
            task_data = json.loads(ai_response[json_start:json_end])

            # Создаём эмбеддинг задачи
            embed_text = f"{task_data['title']} {task_data['description']} {' '.join(task_data.get('hard_skills', []))} {' '.join(task_data.get('soft_skills', []))}"
            embedding = await embed(embed_text)

            # Сохраняем задачу в БД
            task_result = supabase.table("tasks").insert({
                "curator_id": data.curator_id,
                "title": task_data["title"],
                "description": task_data["description"],
                "date": task_data.get("date"),
                "location": task_data.get("location"),
                "volunteers_needed": task_data.get("volunteers_needed", 1),
                "hard_skills": task_data.get("hard_skills", []),
                "soft_skills": task_data.get("soft_skills", []),
                "embedding": embedding,
            }).execute()

            task_id = task_result.data[0]["id"]
        except Exception as e:
            print(f"Ошибка парсинга задачи: {e}")

    # Сохраняем/обновляем сессию
    if session:
        supabase.table("interview_sessions").update({
            "messages": messages,
            "is_complete": is_complete,
            "task_id": task_id,
        }).eq("id", data.session_id).execute()
        session_id = data.session_id
    else:
        new_session = supabase.table("interview_sessions").insert({
            "curator_id": data.curator_id,
            "messages": messages,
            "is_complete": is_complete,
            "task_id": task_id,
        }).execute()
        session_id = new_session.data[0]["id"]

    return {
        "session_id": session_id,
        "response": ai_response.replace("[COMPLETE]", "").strip(),
        "is_complete": is_complete,
        "task_id": task_id,
    }


# ─── RAG-Консультант ───────────────────────────────────────────────

@router.post("/rag-consult")
async def rag_consult(data: RAGQuestion):
    """RAG-консультант: отвечает на вопросы волонтёра строго из контекста задачи"""

    # Получаем задачу из БД
    result = supabase.table("tasks").select("*").eq("id", data.task_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    task = result.data

    # Формируем контекст из задачи
    context = f"""
Название: {task['title']}
Описание: {task['description']}
Дата: {task.get('date', 'не указана')}
Локация: {task.get('location', 'не указана')}
Нужно волонтёров: {task.get('volunteers_needed', 1)}
Необходимые навыки: {', '.join(task.get('hard_skills', []) + task.get('soft_skills', []))}
"""

    rag_prompt = f"""Ты — помощник волонтёра на платформе Sun Proactive.
У тебя есть ТОЛЬКО следующая информация о задаче:

{context}

ВАЖНЫЕ ПРАВИЛА:
- Отвечай ТОЛЬКО на основе информации выше
- Если ответа нет в описании — честно скажи: "Организатор этого не указал"
- Не придумывай информацию
- Будь кратким и полезным

Вопрос волонтёра: {data.question}"""

    answer = await chat([{"role": "user", "content": rag_prompt}])

    return {
        "question": data.question,
        "answer": answer,
        "source": "task_description",
    }


# ─── CRUD задач ────────────────────────────────────────────────────

@router.get("/")
async def get_tasks(status: Optional[str] = None):
    query = supabase.table("tasks").select("*, users(name, email)")
    if status:
        query = query.eq("status", status)
    result = query.order("created_at", desc=True).execute()
    return result.data

@router.get("/{task_id}")
async def get_task(task_id: str):
    result = supabase.table("tasks").select("*, users(name, email)").eq("id", task_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return result.data

@router.get("/{task_id}/applications")
async def get_task_applications(task_id: str):
    result = supabase.table("applications").select("*, users(name, email, skills, bio)").eq("task_id", task_id).execute()
    return result.data
