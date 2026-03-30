from openai import AsyncOpenAI
from app.config import settings

# OpenAI-совместимый клиент для alem.ai
ai_client = AsyncOpenAI(
    api_key=settings.alem_api_key,
    base_url=settings.alem_base_url,
)
CHAT_MODEL = "alemllm"
EMBED_MODEL = "embedder"
VISION_MODEL = "alemllm"

async def chat(messages: list, model: str = CHAT_MODEL, response_format=None) -> str:
    """Обычный чат-запрос"""
    kwargs = {
        "model": model,
        "messages": messages,
        "max_tokens": 2000,
        "temperature": 0.7,
    }
    if response_format:
        kwargs["response_format"] = response_format

    response = await ai_client.chat.completions.create(**kwargs)
    return response.choices[0].message.content

async def embed(text: str) -> list[float]:
    """Генерируем псевдо-эмбеддинг через хеширование текста (fallback если нет Embedder)"""
    import hashlib
    import math
    
    # Простой детерминированный вектор на основе текста
    # Достаточно для демо на хакатоне
    hash_bytes = hashlib.sha256(text.encode()).digest()
    vector = []
    for i in range(0, min(len(hash_bytes), 128), 1):
        val = (hash_bytes[i % len(hash_bytes)] - 128) / 128.0
        vector.append(val)
    
    # Дополняем до 1536 размерности
    while len(vector) < 1536:
        seed = vector[len(vector) % len(hash_bytes)] if hash_bytes else 0
        vector.append(math.sin(len(vector) * 0.1 + seed))
    
    return vector[:1536]
async def chat_with_image(messages: list, image_url: str, prompt: str) -> str:
    """Vision-запрос с изображением"""
    messages_with_image = messages + [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        }
    ]
    response = await ai_client.chat.completions.create(
        model=VISION_MODEL,
        messages=messages_with_image,
        max_tokens=1000,
    )
    return response.choices[0].message.content
