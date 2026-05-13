# AI Financial Survival Assistant

Web client (Vite + React) and FastAPI backend with PostgreSQL, JWT auth, conversational tools, and optional voice (Web Speech + Whisper).

## Repository layout

- `apps/api` — FastAPI, SQLAlchemy, Alembic, OpenAI chat + tools
- `apps/web` — Vite + React + TypeScript

## Local development

### Prerequisites

- Python 3.11+
- Node 20+
- PostgreSQL (local or Docker)

### API

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: DATABASE_URL, JWT_SECRET, CORS_ORIGIN
# LLM keys (server only): OPENAI_API_KEY, and/or OPENROUTER_API_KEY, GEMINI_API_KEY
# Optional: CREDENTIALS_ENCRYPTION_KEY (reserved for future server-side secrets)

alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API keys are **not** entered in the web UI — use **`apps/api/.env`** and/or the **repo root** `.env` (both are loaded: root first, then `apps/api/.env` overrides on duplicate keys). Settings lets each user pick **provider** (OpenAI / OpenRouter / Gemini).

### Web

```bash
cd apps/web
npm install
cp .env.example .env
# VITE_API_URL=http://localhost:8000

npm run dev
```

Open http://localhost:5173 — register, chat, log expenses via natural language or the tools the model uses.

## Environment variables

See [apps/api/.env.example](apps/api/.env.example) and [apps/web/.env.example](apps/web/.env.example).

## Deploy on Render

See [docs/render.md](docs/render.md).
