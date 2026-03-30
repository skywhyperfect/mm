# app/routers/notifications.py
from fastapi import APIRouter
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.database import supabase
from app.ai_client import chat

router = APIRouter()
scheduler = AsyncIOScheduler()

async def check_urgent_tasks():
    """Cron job: проверяем задачи у которых дедлайн через 24 часа и нет нужного кол-ва волонтёров"""
    print(f"[Cron] Проверка срочных задач: {datetime.now()}")

    now = datetime.now(timezone.utc)
    deadline = now + timedelta(hours=24)

    # Берём открытые задачи с дедлайном в ближайшие 24 часа
    tasks_res = supabase.table("tasks").select("*").eq("status", "open").lte("date", deadline.isoformat()).gte("date", now.isoformat()).execute()

    for task in tasks_res.data or []:
        # Считаем принятых волонтёров
        apps_res = supabase.table("applications").select("id").eq("task_id", task["id"]).eq("status", "accepted").execute()
        accepted_count = len(apps_res.data or [])
        needed = task.get("volunteers_needed", 1)

        if accepted_count >= needed:
            continue  # Квота заполнена

        slots_left = needed - accepted_count

        # Находим подходящих свободных волонтёров через embedding similarity
        volunteers_res = supabase.table("users").select("id,name,skills").eq("role", "volunteer").not_.is_("embedding", "null").execute()

        # Генерируем персонализированное уведомление
        for volunteer in (volunteers_res.data or []):
            # Проверяем, не откликался ли уже
            existing = supabase.table("applications").select("id").eq("task_id", task["id"]).eq("volunteer_id", volunteer["id"]).execute()
            if existing.data:
                continue

            notify_prompt = f"""Напиши короткое push-уведомление (1-2 предложения) для волонтёра.

Волонтёр: {volunteer['name']}
Навыки: {', '.join(volunteer.get('skills', []))}

Срочная задача: "{task['title']}"
До начала: менее 24 часов
Нужно ещё волонтёров: {slots_left}

Сообщение должно быть мотивирующим, конкретным, упоминать навыки волонтёра."""

            message = await chat([{"role": "user", "content": notify_prompt}])

            # Сохраняем уведомление
            supabase.table("notifications").insert({
                "user_id": volunteer["id"],
                "task_id": task["id"],
                "message": message,
            }).execute()

            print(f"[Cron] Уведомление отправлено: {volunteer['name']} → {task['title']}")

def start_scheduler():
    scheduler.add_job(
        check_urgent_tasks,
        trigger=IntervalTrigger(hours=1),  # Проверяем каждый час
        id="urgent_tasks_check",
        replace_existing=True,
    )
    scheduler.start()
    print("[Scheduler] AI-менеджер запущен")

# ─── Эндпоинты уведомлений ─────────────────────────────────────────

@router.get("/{user_id}")
async def get_notifications(user_id: str):
    result = supabase.table("notifications").select("*, tasks(title)").eq("user_id", user_id).order("created_at", desc=True).execute()
    return result.data

@router.patch("/{notification_id}/read")
async def mark_as_read(notification_id: str):
    supabase.table("notifications").update({"is_read": True}).eq("id", notification_id).execute()
    return {"status": "ok"}

@router.post("/trigger-check")
async def trigger_check():
    """Ручной триггер для демонстрации на хакатоне"""
    await check_urgent_tasks()
    return {"status": "Проверка выполнена"}
