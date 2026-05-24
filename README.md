# Pocket Buddy — AI Expense Tracker

A conversational AI assistant that helps you track daily spending, manage multiple wallets, and stay within budget — all through natural language chat.

> "Spent ₹100 on Uber" → logged instantly. Wallet balance updated. Daily buffer shown.

---

## What is this?

Pocket Buddy is a personal finance assistant built for people who want to track money the way they talk — not through forms or spreadsheets. You chat with it like a person. It understands English, Hindi, and Hinglish, logs expenses, updates your wallet balances, and tells you how much budget you have left for the day.

The core idea: most expense trackers tell you **what you spent**. Pocket Buddy tells you **how much runway you have left today**, and keeps it updated after every expense.

---

## Use Cases

### 1. Logging expenses on the go
Say "Swiggy 250 lagaya" or "spent 500 on groceries" — the assistant logs it, deducts from your wallet, and shows your remaining daily buffer. No tapping categories, no filling forms.

### 2. Tracking multiple wallets
Keep wallet 1 as your primary spending account (cash/UPI) and wallet 2+ as savings. Expenses always deduct from wallet 1 unless you say otherwise. You can say "wallet 2 has ₹15,000" to update the balance without affecting which wallet is active.

### 3. Daily budget awareness
Set a daily budget (e.g. ₹500/day). After every expense, the app shows how much buffer you have left today. Fixed costs like rent, EMI, and subscriptions are excluded from the daily budget calculation so they don't distort your day-to-day picture.

### 4. Loan / borrow tracking between wallets
If you borrow from your savings to cover a shortfall — "transferred ₹5,000 from wallet 2 to wallet 1" — the app tracks it as a loan on wallet 2. When you repay: "wallet 2 loan clear" removes the marker. Wallet 1 never shows a loan indicator.

### 5. Importing financial history from other apps
Pocket Buddy includes a one-step import flow: copy a prompt from Settings → paste it into ChatGPT or Claude along with your bank statements or existing data → paste the JSON output into Settings → review the editable table → import. Your full financial history can be loaded in minutes.

### 6. Voice input
Tap the mic, speak your expense, and the app transcribes and logs it. Works with both browser-native speech and server-side Whisper (OpenAI) for better accuracy.

### 7. Expense history queries
"mere expenses batao" / "what did I spend this week?" — the assistant shows a clean breakdown: today's itemized list, the past 6 days, and the past 30 days, all in one reply. Fixed categories are tagged separately so you can see variable vs. committed spend at a glance.

### 8. Balance check
"kitna bacha?" / "wallet balance" — instant reply with all wallet balances, active wallet highlighted, and today's remaining buffer.

---

## Features

- **Natural language logging** — English, Hindi, Hinglish all work
- **Multi-wallet support** — up to 5 wallets; wallet 1 always the primary spending wallet
- **Daily buffer** — `daily_budget − today_variable_spend`, live-updated after every expense
- **Fixed category exclusion** — rent, EMI, insurance, subscriptions don't eat into daily buffer
- **Loan tracking** — wallets 2–5 can carry a loan indicator; cleared via chat or Settings
- **Voice input** — Web Speech API (browser) or OpenAI Whisper (server-side)
- **JSON import** — paste AI-generated structured data from any external assistant
- **Budget & Profile panel** — always-visible in Settings; edit daily budget, rent, salary day, wallet balances
- **Multi-provider LLM** — OpenAI, OpenRouter (free models supported), or Gemini; keys stay on the server
- **JWT auth** — per-user isolated data, passwords hashed with bcrypt

---

## Architecture

```
┌──────────────────────┐        ┌──────────────────────────────────┐
│  Web (Vite + React)  │  HTTP  │  API (FastAPI + PostgreSQL)       │
│  TypeScript          │◄──────►│  SQLAlchemy + Alembic migrations  │
│  Tailwind CSS        │        │  OpenAI-compatible LLM client     │
└──────────────────────┘        └──────────────────────────────────┘
```

**Chat flow:**  
User message → deterministic fast-path check (balance statements, expense queries, loan clear) → if no match, LLM with tool-use (add_expense, set_user_context, transfer_between_wallets, …) → tool results committed to DB → reply returned.

**Why a fast-path?** Statements like "wallet 2 balance is ₹50,000" or "aaj ka kharch batao" have a single correct deterministic answer. Bypassing the LLM for these makes them near-instant and avoids wasting tokens.

---

## Tech Stack

| Layer | Stack |
|---|---|
| Frontend | React 18, Vite, TypeScript, Tailwind CSS |
| Backend | FastAPI, SQLAlchemy, Alembic |
| Database | PostgreSQL |
| Auth | JWT (python-jose), bcrypt |
| LLM | OpenAI SDK (provider-agnostic: OpenAI / OpenRouter / Gemini) |
| Voice | Web Speech API + OpenAI Whisper (optional) |
| Deploy | Render (API + DB + static site) |

---

## Local Development

### Prerequisites

- Python 3.11+
- Node 20+
- PostgreSQL (local or via Docker)

### 1. Clone

```bash
git clone git@github.com:Priyansh-03/Pocket-buddy.git
cd Pocket-buddy
```

### 2. API

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env — minimum required:
#   DATABASE_URL   postgresql+psycopg2://user:pass@localhost:5432/pocketbuddy
#   JWT_SECRET     any long random string  (openssl rand -hex 32)
#   OPENAI_API_KEY  (or OPENROUTER_API_KEY / GEMINI_API_KEY)

alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Web

```bash
cd apps/web
npm install
cp .env.example .env
# leave VITE_API_URL commented out in dev (Vite proxy handles it)

npm run dev
```

Open http://localhost:5173 — register an account and start chatting.

### 4. Quick start (both together)

```bash
# From repo root
./run.sh
```

---

## Environment Variables

### `apps/api/.env`

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `JWT_SECRET` | Yes | Secret for signing JWTs — use a long random string |
| `OPENAI_API_KEY` | One of these | Used when provider = `openai` |
| `OPENROUTER_API_KEY` | One of these | Used when provider = `openrouter` |
| `GEMINI_API_KEY` | One of these | Used when provider = `gemini` |
| `OPENAI_MODEL` | No | Default: `gpt-4o-mini` |
| `OPENROUTER_MODEL` | No | Default: `meta-llama/llama-3.3-70b-instruct:free` |
| `GEMINI_MODEL` | No | Default: `gemini-2.0-flash` |
| `CORS_ORIGIN` | No | Comma-separated allowed origins. Default: `http://localhost:5173` |
| `LLM_MAX_OUTPUT_TOKENS` | No | Cap LLM output size. Try `700`–`1024` on low OpenRouter credits |

See [apps/api/.env.example](apps/api/.env.example) for the full list with comments.

### `apps/web/.env`

| Variable | Required | Description |
|---|---|---|
| `VITE_API_URL` | Production only | API base URL. Leave unset in dev — Vite proxy handles it |

---

## LLM Provider Notes

API keys live **only on the server** in `.env`. The web UI never collects or stores keys. Each user picks their provider in Settings → AI Provider.

**Free option:** Set `OPENROUTER_API_KEY` and use `OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct:free`. Free models have rate limits; set `LLM_MAX_OUTPUT_TOKENS=700` to stay within credit limits.

**Recommended:** `OPENAI_API_KEY` with `OPENAI_MODEL=gpt-4o-mini` — reliable tool-use, fast, low cost.

---

## Deploy on Render

See [docs/render.md](docs/render.md) for step-by-step instructions using the included `render.yaml` (API service + PostgreSQL + static web build).

---

## Database Migrations

```bash
cd apps/api

# Apply all pending migrations
alembic upgrade head

# Create a new migration after changing models
alembic revision --autogenerate -m "describe the change"
```

---

## Project Structure

```
Pocket-buddy/
├── apps/
│   ├── api/                          # FastAPI backend
│   │   ├── alembic/versions/         # DB migrations (001–009)
│   │   ├── app/
│   │   │   ├── routers/              # auth, chat, expenses, users, transcribe
│   │   │   ├── services/
│   │   │   │   ├── llm/
│   │   │   │   │   ├── openai_chat.py   # system prompt + LLM call
│   │   │   │   │   └── tool_runner.py   # tool definitions + execution
│   │   │   │   └── wallets.py        # wallet balance helpers
│   │   │   ├── models.py             # SQLAlchemy models
│   │   │   ├── schemas.py            # Pydantic schemas
│   │   │   └── config.py             # Settings loaded from .env
│   │   └── requirements.txt
│   └── web/                          # Vite + React frontend
│       └── src/
│           ├── pages/                # ChatPage, SettingsPage, LoginPage
│           ├── components/           # ChatComposer, UI primitives
│           ├── context/              # AuthContext (JWT + user state)
│           └── prompts/              # JSON import prompt template
├── docs/
│   ├── render.md                     # Render deploy guide
│   └── PRODUCT_AND_ARCHITECTURE.md  # Detailed product spec
├── render.yaml                       # Render.com service definitions
└── run.sh                            # Local dev startup (API + web)
```

---

## Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Commit your changes
4. Open a pull request

Do not commit `.env` files or real API keys.

---

## License

MIT
