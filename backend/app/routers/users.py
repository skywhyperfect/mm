# app/routers/users.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.database import supabase
from app.ai_client import embed

router = APIRouter()

class UserCreate(BaseModel):
    email: str
    name: str
    role: str  # 'curator' or 'volunteer'
    bio: Optional[str] = None
    skills: list[str] = []
    interests: list[str] = []
    goals: Optional[str] = None

@router.post("/")
async def create_user(data: UserCreate):
    # Создаём эмбеддинг профиля волонтёра
    embedding = None
    if data.role == "volunteer":
        bio_text = f"{data.name} {data.bio or ''} {' '.join(data.skills)} {data.goals or ''}"
        embedding = await embed(bio_text)

    result = supabase.table("users").insert({
        "email": data.email,
        "name": data.name,
        "role": data.role,
        "bio": data.bio,
        "skills": data.skills,
        "interests": data.interests,
        "goals": data.goals,
        "embedding": embedding,
    }).execute()
    return result.data[0]

@router.get("/{user_id}")
async def get_user(user_id: str):
    result = supabase.table("users").select("id,email,name,role,bio,skills,interests,goals,created_at").eq("id", user_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return result.data

@router.get("/{user_id}/tasks")
async def get_user_tasks(user_id: str):
    """Задачи куратора"""
    result = supabase.table("tasks").select("*").eq("curator_id", user_id).order("created_at", desc=True).execute()
    return result.data

@router.get("/{user_id}/applications")
async def get_user_applications(user_id: str):
    """Отклики волонтёра"""
    result = supabase.table("applications").select("*, tasks(title, date, location, status)").eq("volunteer_id", user_id).execute()
    return result.data
@router.get("/by-email/{email}")
async def get_user_by_email(email: str):
    result = supabase.table("users").select("id,email,name,role,bio,skills,interests,goals,created_at").eq("email", email).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return result.data