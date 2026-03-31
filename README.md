# Sun Proactive — AI-биржа социальных задач

**Финальный проект для AIS Hack 3.0**

AI-инфраструктура, которая автоматически собирает требования к задачам, делает семантический подбор волонтёров, отвечает без галлюцинаций и верифицирует результат.

## Что уже реализовано

- ✅ AI-Интервьюер для куратора (Structured Outputs + диалог)
- ✅ AI-Консультант для волонтёра (RAG-архитектура)
- ✅ Семантический Matching (Embeddings + Cosine Similarity + Explainable AI)
- ✅ Trust UI — плашки с объяснением решений ИИ
- ✅ Профили волонтёров и кабинет куратора
- ✅ Кабинет организатора с задачами и откликами
- ✅Загрузка фото + Vision-верификация
- ✅Автономный AI-Менеджер (cron job)

## Технологический стек

- **Frontend + Backend**: Next.js 15 (App Router) + TypeScript
- **UI**: Tailwind + shadcn/ui
- **База данных**: Supabase (PostgreSQL + pgvector)
- **AI**:
  - OpenAI (text-embedding-3-small + GPT-4o Vision)
  - RAG + Structured Outputs
- **Деплой**: Vercel + Supabase

## Как запустить локально

```bash
git clone https://github.com/skywhyperfect/mm.git
cd mm

npm install

# Создай .env.local и заполни переменные
cp .env.example .env.local
