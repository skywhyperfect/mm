import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

class Settings:
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_key: str = os.getenv("SUPABASE_KEY", "")
    alem_api_key: str = os.getenv("ALEM_API_KEY", "")
    alem_base_url: str = os.getenv("ALEM_BASE_URL", "https://llm.alem.ai/v1")

settings = Settings()
