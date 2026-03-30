import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

# Явно указываем путь к .env
load_dotenv(Path(__file__).parent.parent / ".env")

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

print(f"[DB] URL: {url}")
print(f"[DB] KEY: {key[:20] if key else 'НЕТ'}...")

supabase: Client = create_client(url, key)
