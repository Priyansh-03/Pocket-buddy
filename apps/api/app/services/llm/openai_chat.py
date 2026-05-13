from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import User
from app.services.expense_memory import build_expense_memory_block
from app.services.llm.tool_runner import OPENAI_TOOLS, run_tool

SYSTEM_PROMPT = """You are a personal money assistant for one user in India.
Currency is INR.

Rules:
1) Real memory is database entries only.
2) When user states a clear spend amount, call add_expense with amount_inr, category, and optional note.
3) USER_FACTS_EXPENSES in system message is the source of truth for already logged spends. Do not duplicate.
4) If user asks current balance, cash left, or similar, always call get_affordability_hint first.
   If current_balance_estimate_inr or estimated_cash_inr is present, answer with that value.
5) Use set_user_context and adjust_estimated_cash_inr only when user gives profile or cash update numbers.
6) For menu price comparisons, use compare_meal_options.

Response style:
- Use very simple language.
- Keep answers short.
- Format INR in Indian comma style, for example ₹3,44,949.76.
- Do not use em dash.
- Do not use heavy finance words.
- No legal or investment advice."""


def _wallets_context(user: User) -> str:
    def fmt(v):
        return "null" if v is None else str(v)

    active = user.active_wallet_id if user.active_wallet_id in (1, 2, 3, 4, 5) else 1
    return (
        "---USER_FACTS_WALLETS (stored in database)---\n"
        f"active_wallet_id: {active}\n"
        f"wallet_1_inr: {fmt(user.wallet_1_inr)}\n"
        f"wallet_2_inr: {fmt(user.wallet_2_inr)}\n"
        f"wallet_3_inr: {fmt(user.wallet_3_inr)}\n"
        f"wallet_4_inr: {fmt(user.wallet_4_inr)}\n"
        f"wallet_5_inr: {fmt(user.wallet_5_inr)}\n"
        f"estimated_cash_inr(active wallet shadow): {fmt(user.estimated_cash_inr)}\n"
        "---END_USER_FACTS_WALLETS---"
    )


def _full_system_content(db: Session, user: User) -> str:
    """IST clock + static prompt + DB-backed expense rows so logged spends are never dropped when chat history is short."""
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    clock = now.strftime("%a %d %b %Y, %H:%M:%S IST")
    memory = build_expense_memory_block(db, user)
    wallets = _wallets_context(user)
    return (
        SYSTEM_PROMPT
        + "\n\nCurrent date and time (Asia/Kolkata) for this request: "
        + clock
        + ". For dates in pasted text.\n\n"
        + wallets
        + "\n\n"
        + memory
    )


def resolve_server_api_key(settings: Settings, provider: str | None) -> str | None:
    """API keys only from server environment (apps/api/.env), not from the client."""
    p = (provider or "openai").lower()
    if p == "openai":
        k = settings.openai_key_effective()
    elif p == "openrouter":
        k = settings.openrouter_api_key
    elif p == "gemini":
        k = settings.gemini_api_key
    else:
        return None
    k = (k or "").strip()
    return k or None


def server_key_configured(settings: Settings, provider: str | None) -> bool:
    return resolve_server_api_key(settings, provider) is not None


def _llm_http_timeout(settings: Settings) -> httpx.Timeout:
    return httpx.Timeout(
        connect=settings.llm_connect_timeout_seconds,
        read=settings.llm_read_timeout_seconds,
        write=120.0,
        pool=30.0,
    )


async def chat_openai_compatible(
    db: Session,
    user: User,
    history: list[dict[str, Any]],
    user_message: str,
    *,
    api_key: str,
    base_url: str | None,
    model: str,
    extra_headers: dict[str, str] | None = None,
) -> str:
    settings = get_settings()
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        default_headers=extra_headers or {},
        timeout=_llm_http_timeout(settings),
        max_retries=2,
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _full_system_content(db, user)},
        *history,
        {"role": "user", "content": user_message},
    ]

    for _ in range(8):
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=OPENAI_TOOLS,
            tool_choice="auto",
            temperature=0.2,
        )
        choice = resp.choices[0]
        msg = choice.message
        if msg.tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )
            for tc in msg.tool_calls:
                out = run_tool(db, user, tc.function.name, tc.function.arguments or "{}")
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": out,
                    }
                )
            continue
        text = (msg.content or "").strip()
        if text:
            return text
        return "I could not produce a reply. Try again."

    return "Too many tool steps. Please simplify your question."


async def chat_openai_or_openrouter(db: Session, user: User, history: list[dict[str, Any]], user_message: str) -> str:
    settings = get_settings()
    prov = (user.llm_provider or "openai").lower()
    key = resolve_server_api_key(settings, prov)
    if prov == "openrouter":
        if not key:
            raise ValueError(
                "Server par OPENROUTER_API_KEY set karo (apps/api/.env). OpenRouter isi key se chalega."
            )
        ref = user.openrouter_http_referer or "https://localhost"
        headers = {"HTTP-Referer": ref, "X-Title": "AI Financial Survival Assistant"}
        return await chat_openai_compatible(
            db,
            user,
            history,
            user_message,
            api_key=key,
            base_url=settings.openrouter_base_url,
            model=settings.openai_model,
            extra_headers=headers,
        )

    if not key:
        raise ValueError(
            "Server par OPENAI_API_KEY ya OUTSPARK_OPENAI_STAGING_API_KEY set karo (apps/api/.env)."
        )
    return await chat_openai_compatible(
        db,
        user,
        history,
        user_message,
        api_key=key,
        base_url=None,
        model=settings.openai_model,
        extra_headers=None,
    )


async def chat_gemini(db: Session, user: User, history: list[dict[str, Any]], user_message: str) -> str:
    settings = get_settings()
    key = resolve_server_api_key(settings, "gemini")
    if not key:
        raise ValueError(
            "Server par GEMINI_API_KEY set karo (apps/api/.env)."
        )
    return await chat_openai_compatible(
        db,
        user,
        history,
        user_message,
        api_key=key,
        base_url=settings.gemini_openai_base_url,
        model=settings.gemini_model,
        extra_headers=None,
    )


async def run_provider_chat(
    db: Session, user: User, history: list[dict[str, Any]], user_message: str
) -> str:
    prov = (user.llm_provider or "openai").lower()
    if prov == "gemini":
        return await chat_gemini(db, user, history, user_message)
    return await chat_openai_or_openrouter(db, user, history, user_message)
