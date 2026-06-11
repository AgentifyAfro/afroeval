# AfroEval — Claude Code Instructions

## Do NOT modify these files automatically

Files in `benchmarks/packs/*.jsonl` are **SME-validated benchmark data**.
They must never be rewritten, reformatted, or "simplified" by any automated tool or agent.
Each line is a carefully authored test case. Treat them as read-only unless the user explicitly asks to edit them.

## Running the project

```powershell
# Start server (from afroeval/)
.\.venv\Scripts\python.exe -m uvicorn api.main:app --port 8001

# Run tests
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

## Key facts

- Venv: `.venv/` (Python 3.12) — has all dependencies including fairlearn, deepeval, ragas, openai
- DB: Supabase PostgreSQL (session pooler) — configured via DATABASE_URL in .env
- API key for local dev: `dev-secret-change-in-production` (X-API-Key header)
- Azure deployment: `gpt-4.1-mini` — credentials in .env (never commit .env)
