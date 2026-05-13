# AI Financial Survival Assistant — Product, UI, API, and Scale

This document captures the **problem**, **objectives**, **what to build**, **how to build it**, a **UI plan** (layout, states, settings), **backend calls**, **multi-provider LLM keys (including keys from the UI)**, and **server load** assumptions for roughly **20–50 concurrent users**.

---

## 1. Problem statement

Young professionals and students living salary-to-salary often face:

- **Invisible daily overspending** (small spends that add up).
- **Impulsive** food, cab, and e-commerce purchases.
- **Unpredictable bills** (rent, utilities, travel).
- **Decision fatigue** (“Can I afford this right now?”).
- **Low real-time clarity** — spreadsheets and classic trackers show *history*, not *current safety*.

Most trackers answer: *“You spent X.”*  
This product should answer: *“Given your pattern and runway, is this spend safe *now*?”*

---

## 2. Objective

Build an **AI conversational assistant** (text + voice) that:

- Helps users make **better same-day spending decisions**.
- Reduces risk of **running out before salary**.
- Surfaces **patterns** (food, travel, electricity-style notes) without demanding strict budgets.
- Feels like an **“AI roommate + money strategist”** — supportive, specific, INR-aware.

**North star:** **dynamic financial survivability** (runway + pace + context), not traditional budgeting alone.

---

## 3. What to build

### 3.1 MVP (vertical slice)

| Area | Deliverable |
|------|-------------|
| **Identity** | Register / login; session or JWT. |
| **Chat** | Threaded chat; assistant uses **tools** (log expense, spending summary, affordability hint, update profile). |
| **Data** | Expenses + user profile fields (salary day, rent, estimated cash). |
| **Survivability** | Deterministic helper (days to salary, 7-day burn, buffer label: comfortable / tight / risky) + LLM explains it. |
| **Voice** | Text always; browser **Web Speech** optional; optional **server transcription** for quality. |
| **Settings** | Provider choice + **BYOK** (bring your own key) for OpenAI / OpenRouter / Gemini. |
| **Hosting** | API + DB on Render (or similar); static web build. |

### 3.2 Later phases (explicitly out of MVP scope)

- Bank sync, OCR menus, electricity modeling, push notifications, native Flutter shell (same API).

---

## 4. How to build (engineering approach)

### 4.1 High-level architecture

```text
[Web app: Vite + React]
        │ HTTPS (JSON)
        ▼
[API: FastAPI] ──► [PostgreSQL]
        │
        ├──► [User-encrypted LLM keys] (BYOK)
        └──► [Provider adapters: OpenAI | OpenRouter | Gemini]
```

- **Frontend:** Vite + React + TypeScript; chat-first layout; settings for keys and provider.
- **Backend:** FastAPI + SQLAlchemy + Alembic; **all LLM calls server-side** only.
- **DB:** PostgreSQL for users, expenses, chat sessions/messages, and **encrypted provider credentials**.

### 4.2 LLM providers (three options)

| Provider | Typical base URL / SDK | Notes |
|----------|-------------------------|--------|
| **OpenAI** | `https://api.openai.com/v1` | Official SDK; chat + tools + Whisper. |
| **OpenRouter** | OpenAI-compatible base URL (e.g. `https://openrouter.ai/api/v1`) | Same request shape as OpenAI chat; set provider-specific headers if required. |
| **Gemini** | Google Generative Language API | Separate SDK or REST; map **tools** to Gemini function-calling format in an adapter layer. |

**Implementation pattern:** a small **internal interface**, e.g. `complete_chat(messages, tools) -> assistant_message`, with three **adapters**. The chat orchestration (tool loop) stays the same; only the transport differs.

### 4.3 API keys from the UI (BYOK) — behavior and security

**User story:** In **Settings**, the user selects **OpenAI**, **OpenRouter**, or **Gemini**, pastes an API key, saves. Chat uses **their** key for that account.

**Security requirements (non-negotiable):**

1. Keys are sent **only over HTTPS** to your API (`POST /users/me/llm-credentials` or similar).
2. Server **never** returns the full raw key to the client after save — only **masked** display (`sk-...last4`) or “saved”.
3. Store at rest with **application-level encryption** (e.g. Fernet with a server `CREDENTIALS_ENCRYPTION_KEY`) or DB-level encryption; **never** log keys.
4. Optional: allow “use server default key” for your own paid tier later — keep BYOK as a separate code path.

**Data model (conceptual):**

- `users.llm_provider` — enum: `openai` | `openrouter` | `gemini`
- `users.llm_api_key_encrypted` — text (nullable if using server default)
- `users.openrouter_site_url` / app name (optional header for OpenRouter)

**Rotation:** user can “Replace key” or “Remove key” (falls back to server key or blocks chat with a clear message).

---

## 5. UI plan

### 5.1 Information architecture

| Screen / area | Purpose |
|---------------|---------|
| **Login / Register** | Email + password (or magic link later). |
| **Chat (home)** | Primary surface: messages, input, mic, send. |
| **Settings** | LLM provider, API key, profile (salary day, rent, estimated cash), logout. |
| **History** (optional MVP+) | Past sessions list. |

### 5.2 Layout (desktop + mobile)

**Chat (default route)**

```text
┌─────────────────────────────────────────────┐
│  App bar: “Survival”    [Settings gear]     │
├─────────────────────────────────────────────┤
│                                             │
│  Message list (scroll, newest at bottom)   │
│  - User bubbles (right)                     │
│  - Assistant bubbles (left)                 │
│  - Inline system chips: “Logged ₹70 cab”   │
│                                             │
├─────────────────────────────────────────────┤
│  [mic]  [  Type or speak…          ] [Send] │
└─────────────────────────────────────────────┘
```

- **Mobile:** single column; input bar fixed bottom; safe-area padding.
- **Desktop:** max-width container (e.g. 640–720px) centered; comfortable reading width.

**Settings**

```text
┌─────────────────────────────────────────────┐
│  ← Back    Settings                         │
├─────────────────────────────────────────────┤
│  AI provider                                │
│  ( ) OpenAI  ( ) OpenRouter  ( ) Gemini    │
│  API key [password field] [Save] [Remove]  │
│  Hint: keys stay on server, never shown back│
│                                             │
│  Money context                              │
│  Salary day (1–31) [  ]                     │
│  Monthly rent (₹) [    ]                    │
│  Estimated cash (₹) [    ]                  │
│  [Save profile]                             │
└─────────────────────────────────────────────┘
```

### 5.3 Loading, processing, and error states

| State | UI behavior |
|-------|-------------|
| **Initial app load** | Skeleton or spinner on shell; fetch `/auth/me` if token exists. |
| **Sending message** | Disable send; show **typing indicator** on assistant side; optional subtle “Processing…” subline. |
| **Tool execution** | Optional: small text “Updating your ledger…” (only if latency > ~1s). |
| **Voice listening** | Mic button **pulsing** / “Listening…”; on stop, show interim transcript before send. |
| **Transcription** (if server) | Progress on mic line: “Uploading audio…” |
| **Error: network** | Toast: “Couldn’t reach server. Retry?” |
| **Error: 401** | Redirect to login; clear stale token. |
| **Error: LLM / provider** | Friendly message: “Provider refused the request. Check key or model in Settings.” |
| **Error: no key** | Inline banner: “Add an API key in Settings to use chat.” |

**Principles:** never block the whole app on chat; keep **optimistic UI** minimal for money actions — confirm after tool success when possible.

---

## 6. Backend calls (REST shape)

Base URL: `VITE_API_URL` (e.g. `https://api.example.com`). All protected routes: `Authorization: Bearer <jwt>`.

| Method | Path | Body / query | Purpose |
|--------|------|--------------|---------|
| `GET` | `/health` | — | Load balancer / Render health. |
| `POST` | `/auth/register` | `{ email, password }` | Create user; returns JWT. |
| `POST` | `/auth/login` | `{ email, password }` | Returns JWT. |
| `GET` | `/auth/me` | — | Current user profile. |
| `PATCH` | `/users/me` | `{ salary_day?, monthly_rent_inr?, estimated_cash_inr? }` | Profile / survivability inputs. |
| `PUT` | `/users/me/llm` | `{ provider, api_key?, remove_key? }` | Save BYOK (encrypted); mask on read. |
| `GET` | `/users/me/llm` | — | `{ provider, key_masked, has_key }` only. |
| `GET` | `/expenses` | `?limit=100` | List expenses. |
| `POST` | `/expenses` | `{ amount_inr, category, note? }` | Manual add. |
| `POST` | `/chat` | `{ message, session_id? }` | Chat + tools + persist. |
| `POST` | `/transcribe` | `multipart/form-data` audio | Optional Whisper-style STT (provider-dependent). |

**Notes**

- **`/chat`** should be **stateless per request** except for `session_id` + DB history (scales horizontally).
- **`/transcribe`**: implement with OpenAI Whisper when key is OpenAI; for Gemini/OpenRouter, document which path you support or return `501` until implemented.

---

## 7. Structure (repo layout)

```text
apps/
  web/                 # Vite + React
    src/
      components/      # ChatBubble, InputBar, SettingsForm, ProviderSelect
      pages/           # Login, Chat, Settings
      hooks/           # useAuth, useChat, useVoice
      api/             # fetch wrappers per endpoint
  api/                 # FastAPI
    app/
      routers/         # auth, users, expenses, chat, transcribe, health
      services/
        llm/           # adapters: openai.py, openrouter.py, gemini.py
        survivability.py
      models.py
      schemas.py
docs/
  PRODUCT_AND_ARCHITECTURE.md   # this file
  render.md
```

---

## 8. Server load: 20–50 people at once

**Assumption:** “at once” means **20–50 concurrent interactive users** (occasional bursts), not 50 sustained heavy jobs each second.

### 8.1 Order-of-magnitude

- Each **chat turn** may trigger **1–5+ LLM round trips** (tool loop). Dominant cost is **LLM latency** and **egress**, not Python CPU for CRUD.
- A single small **Render Web Service** (1 vCPU, 512MB–1GB) can usually handle **dozens** of concurrent **I/O-bound** FastAPI requests if you avoid blocking the event loop.

### 8.2 Backend practices

| Concern | Recommendation |
|---------|----------------|
| **DB connections** | SQLAlchemy **pool** (`pool_size` ~5–10, `max_overflow` ~10–20); avoid new engine per request. |
| **Async** | Prefer **`async def`** routes + **`httpx.AsyncClient`** or official async clients for LLM calls so one worker doesn’t stall on I/O. |
| **Timeouts** | LLM client timeout **30–60s**; return structured error to UI. |
| **Idempotency** | Optional `client_message_id` on `/chat` to avoid duplicate expenses on double-submit. |
| **Rate limit** | Per-user **token bucket** (e.g. in-memory for single instance, or Redis later): e.g. 20 messages / minute. |
| **Payload limits** | Cap message length and audio upload size (e.g. 5–10 MB). |
| **Indexes** | Index `expenses(user_id, created_at)`, `chat_messages(session_id, created_at)`. |
| **Workers** | Run **2–4 Uvicorn workers** only if CPU-bound; for I/O-bound, **1 worker + async** is often enough on small instances — measure before multiplying workers (memory). |

### 8.3 When to scale past one instance

- **p95 chat latency** or **5xx** increases under load.
- Then: horizontal replicas + **sticky sessions not required** if chat is DB-backed; add **managed Redis** for rate limits / optional job queue.
- **Postgres** on Render: use **connection limit** aware pool sizing when scaling replicas.

### 8.4 Cost note (BYOK)

With **user-provided keys**, **your** LLM variable cost is **$0**; your infra still pays for **compute + DB + bandwidth**.

---

## 9. Implementation checklist (cross-reference)

1. DB columns + migration for `llm_provider`, encrypted key storage.
2. Settings UI: provider radio + key field + save/remove.
3. `PUT /users/me/llm` + `GET /users/me/llm` (masked).
4. Chat service: resolve credentials per user → adapter (`openai` / `openrouter` / `gemini`).
5. Instrument `/health` and basic logging (without secrets); load-test with ~50 parallel `/chat` **mocked** LLM in CI if possible.

---

## 10. Open questions (product)

- **Trust:** Make BYOK risks explicit (“we encrypt at rest; we never display full keys again”).
- **Compliance:** If you later store bank data, revisit PCI / DPDP; MVP avoids bank linking.

This file is the **single reference** for problem/objective, build direction, UI, API surface, multi-provider keys, and **20–50 concurrent user** expectations until the codebase fully matches it.
