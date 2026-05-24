from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import logging
from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import User
from app.services.expense_memory import build_expense_memory_block
from app.services.llm.flow_trace import LlmFlowTrace
from app.services.llm.tool_runner import OPENAI_TOOLS, run_tool

_LOG = logging.getLogger(__name__)


def _usage_dict(usage: Any) -> dict[str, Any] | None:
    if usage is None:
        return None
    try:
        return usage.model_dump()
    except Exception:
        try:
            return dict(usage)  # type: ignore[arg-type]
        except Exception:
            return {"repr": str(usage)}


def _tool_calls_trace_payload(msg: Any, trace: LlmFlowTrace | None) -> list[dict[str, Any]] | None:
    tcs = getattr(msg, "tool_calls", None) or []
    if not tcs:
        return None
    cap = min(trace.max_chars, 4000) if trace else 4000
    out: list[dict[str, Any]] = []
    for tc in tcs:
        fn = tc.function
        args = fn.arguments or ""
        out.append({"id": tc.id, "name": fn.name, "arguments": (args[:cap] + "\n…[truncated]…") if len(args) > cap else args})
    return out

SYSTEM_PROMPT = """You are Pocket Buddy — a personal finance assistant for one user in India. Currency: INR.

LOGGING SPENDS:
- Any clear spend → call add_expense(amount_inr, category, note?). Tool returns wallet_balance_after and buffer_after — always report BOTH to the user. Never compute these yourself.
- Source of truth for logged spends = USER_FACTS_EXPENSES. Never log duplicates.
- Ambiguous amount/category → ask once. Don't guess.

WALLET RULES:
- Wallet 1 is ALWAYS the primary spending wallet. Deduct all expenses from wallet 1 by default.
- Only use a different wallet if the user explicitly names it (e.g. "wallet 2 se", "from savings").
- If multiple wallets exist and it's unclear which to use, ASK before logging.
- "Kitna bacha / balance / how much left" → report wallet 1 balance from USER_WALLETS.
- User gives explicit wallet balance → set_user_context(wallet_N_inr=X, active_wallet_id=N).
- "Borrowed/took X from wallet A to B" → transfer_between_wallets ONLY (it moves money + records loan in one call). Never also call record_loan separately — that doubles the loan.
- User gives final balances after a borrow → set_user_context for each wallet + record_loan(wallet_id=lender, loan_delta_inr=-X).
- Loan indicator is ONLY tracked on wallet 2 and above (savings wallets). NEVER set loan on wallet 1.
- Simple credit/debit delta (not a spend) → adjust_estimated_cash_inr(delta_inr=X).

SAVINGS & BUDGET:
- Daily budget mentioned → set_user_context(daily_budget_inr=X) immediately.
- Buffer/profit set explicitly → set_user_context(profit_inr=X).
- "How am I doing / kitna save hua" → report buffer from USER_WALLETS (positive=saved, negative=overspent vs budget).
- "Aaj kitna spend hua / today's expenses" → get_spending_summary(days=1).
- "Kya afford kar sakta hoon" → get_affordability_hint.
- "Week/month ka breakdown" → get_spending_summary(days=7 or 30).

MONEY DISTRIBUTION:
- "Paisa kahan hai / distribution / split" → list all wallets from USER_WALLETS with their balances and any loans.
- "Savings kitni hai" → sum of all wallet balances minus the active (spending) wallet, or total if only one wallet.

OTHER:
- Menu/food comparison → compare_meal_options. Use USER_FOOD_MENU and REMEMBER if present.
- All math (balances, buffer) is done by the server. Just report tool result values — never calculate yourself.

RESPONSE STYLE: Short, friendly. Hindi/English mixed is fine. ₹3,44,949.76 format. Say "wallet balance" not "estimated cash". No em dash."""


def _wallets_context(user: User) -> str:
    def fmt(v):
        return "null" if v is None else str(v)

    active = user.active_wallet_id if user.active_wallet_id in (1, 2, 3, 4, 5) else 1
    lines = ["---USER_WALLETS---", f"active_wallet: {active} (this is the spending wallet)"]
    for n in range(1, 6):
        bal = getattr(user, f"wallet_{n}_inr")
        loan = getattr(user, f"wallet_{n}_loan_inr")
        if bal is not None:
            loan_str = f"  loan_outstanding: {fmt(loan)}" if loan is not None else ""
            lines.append(f"wallet_{n}: {fmt(bal)}{loan_str}")
    lines.append(f"daily_budget: {fmt(user.daily_budget_inr)} (user's expected daily spend)")
    lines.append(f"buffer: {fmt(user.profit_inr)} (running savings vs daily budget — never resets; positive=saved, negative=overspent)")
    lines.append("---END_USER_WALLETS---")
    return "\n".join(lines)


def _full_system_content(db: Session, user: User) -> str:
    """IST clock + static prompt + DB-backed expense rows so logged spends are never dropped when chat history is short."""
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    clock = now.strftime("%a %d %b %Y, %H:%M:%S IST")
    memory = build_expense_memory_block(db, user)
    wallets = _wallets_context(user)
    extra = _user_pinned_memory_blocks(user)
    tail = memory if not extra else f"{extra}\n\n{memory}"
    return (
        SYSTEM_PROMPT
        + "\n\nCurrent date and time (Asia/Kolkata) for this request: "
        + clock
        + ". For dates in pasted text.\n\n"
        + wallets
        + "\n\n"
        + tail
    )


def _user_pinned_memory_blocks(user: User) -> str:
    parts: list[str] = []
    menu = (getattr(user, "food_menu_text", None) or "").strip()
    if menu:
        parts.append(
            "---USER_FOOD_MENU (trust prices/items as written; use for meal / compare questions)---\n"
            + menu
            + "\n---END_USER_FOOD_MENU---"
        )
    remember = (getattr(user, "remember_text", None) or "").strip()
    if remember:
        parts.append(
            "---REMEMBER (user asked to keep this in mind on every reply)---\n"
            + remember
            + "\n---END_REMEMBER---"
        )
    return "\n\n".join(parts)


def resolve_server_api_key(settings: Settings, provider: str | None) -> str | None:
    """API keys only from server environment (apps/api/.env), not from the client."""
    p = (provider or "openrouter").lower()
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


def _completion_token_limit(settings: Settings) -> int:
    """Minimum 16 for provider rules."""
    return max(16, settings.llm_max_output_tokens)


def _openrouter_model_uses_reasoning_budget(model: str) -> bool:
    m = (model or "").lower()
    needles = (
        "gpt-oss",
        "deepseek-r1",
        "qwq",
        "thinking",
        "reasoning",
        "/o1",
        "o1-preview",
        "o1-mini",
        "o3-mini",
        "o3-pro",
        "o4-mini",
    )
    return any(n in m for n in needles)


def _openrouter_reasoning_extra_body(settings: Settings, model: str) -> dict[str, Any] | None:
    """Reasoning models get a large default reasoning budget on OpenRouter (~16k) unless capped here."""
    spec = settings.openrouter_reasoning_max_tokens
    if spec == 0:
        return None
    out_cap = _completion_token_limit(settings)
    if spec is not None and spec > 0:
        rmax = max(64, min(out_cap, int(spec)))
        return {"reasoning": {"max_tokens": rmax}}
    if not _openrouter_model_uses_reasoning_budget(model):
        return None
    rmax = max(128, min(out_cap, 2048))
    return {"reasoning": {"max_tokens": rmax}}


def _openrouter_reasoning_tokens_from_usage(usage: Any) -> int | None:
    d = getattr(usage, "completion_tokens_details", None)
    if d is None:
        return None
    rt = getattr(d, "reasoning_tokens", None)
    if rt is None:
        return None
    return int(rt) if isinstance(rt, (int, float)) else None


async def chat_openrouter_with_tools(
    db: Session,
    user: User,
    history: list[dict[str, Any]],
    user_message: str,
    *,
    api_key: str,
    model: str,
    http_referer: str,
    app_title: str,
    trace: LlmFlowTrace | None = None,
) -> str:
    """OpenRouter: OpenAI-compatible HTTP client + extra_body so reasoning.* caps apply (fixes 402 / 16k default)."""
    settings = get_settings()
    out_cap = _completion_token_limit(settings)
    reasoning_body = _openrouter_reasoning_extra_body(settings, model)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _full_system_content(db, user)},
        *history,
        {"role": "user", "content": user_message},
    ]
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=settings.openrouter_base_url,
        default_headers={
            "HTTP-Referer": http_referer,
            "X-Title": app_title,
        },
        timeout=_llm_http_timeout(settings),
        max_retries=2,
    )

    for layer in range(1, 9):
        if trace:
            trace.layer_enter(
                layer,
                provider="openrouter",
                model=model,
                messages=messages,
                user_message_preview=user_message if layer == 1 else "",
            )
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "tools": OPENAI_TOOLS,
            "tool_choice": "auto",
            "temperature": 0.2,
            "max_tokens": out_cap,
            "max_completion_tokens": out_cap,
        }
        if reasoning_body is not None:
            kwargs["extra_body"] = reasoning_body
        resp = await client.chat.completions.create(**kwargs)

        usage = getattr(resp, "usage", None)
        if usage is not None:
            rt = _openrouter_reasoning_tokens_from_usage(usage)
            if rt is not None:
                _LOG.debug("OpenRouter reasoning tokens: %s", rt)

        choice = resp.choices[0]
        msg = choice.message
        fr = getattr(choice, "finish_reason", None)
        if trace:
            trace.pass_completion(
                layer,
                response_id=getattr(resp, "id", None),
                model=getattr(resp, "model", None),
                finish_reason=str(fr) if fr is not None else None,
                usage=_usage_dict(usage),
                assistant_content=msg.content or "",
                tool_calls=_tool_calls_trace_payload(msg, trace),
            )
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
            tool_rows: list[dict[str, Any]] = []
            for tc in msg.tool_calls:
                out = run_tool(db, user, tc.function.name, tc.function.arguments or "{}")
                tool_rows.append(
                    {
                        "tool_call_id": tc.id,
                        "name": tc.function.name,
                        "arguments": trace.trunc(tc.function.arguments or "") if trace else (tc.function.arguments or ""),
                        "result": trace.trunc(out) if trace else out,
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": out,
                    }
                )
            if trace:
                trace.pass_tools(layer, tool_results=tool_rows)
            continue
        text = (msg.content or "").strip()
        if text:
            return text
        return "I could not produce a reply. Try again."

    return "Too many tool steps. Please simplify your question."


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
    trace: LlmFlowTrace | None = None,
    trace_provider: str = "openai",
) -> str:
    settings = get_settings()
    out_cap = _completion_token_limit(settings)
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

    for layer in range(1, 9):
        if trace:
            trace.layer_enter(
                layer,
                provider=trace_provider,
                model=model,
                messages=messages,
                user_message_preview=user_message if layer == 1 else "",
            )
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=OPENAI_TOOLS,
            tool_choice="auto",
            temperature=0.2,
            max_tokens=out_cap,
        )
        choice = resp.choices[0]
        msg = choice.message
        usage = getattr(resp, "usage", None)
        fr = getattr(choice, "finish_reason", None)
        if trace:
            trace.pass_completion(
                layer,
                response_id=getattr(resp, "id", None),
                model=getattr(resp, "model", None),
                finish_reason=str(fr) if fr is not None else None,
                usage=_usage_dict(usage),
                assistant_content=msg.content or "",
                tool_calls=_tool_calls_trace_payload(msg, trace),
            )
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
            tool_rows: list[dict[str, Any]] = []
            for tc in msg.tool_calls:
                out = run_tool(db, user, tc.function.name, tc.function.arguments or "{}")
                tool_rows.append(
                    {
                        "tool_call_id": tc.id,
                        "name": tc.function.name,
                        "arguments": trace.trunc(tc.function.arguments or "") if trace else (tc.function.arguments or ""),
                        "result": trace.trunc(out) if trace else out,
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": out,
                    }
                )
            if trace:
                trace.pass_tools(layer, tool_results=tool_rows)
            continue
        text = (msg.content or "").strip()
        if text:
            return text
        return "I could not produce a reply. Try again."

    return "Too many tool steps. Please simplify your question."


async def chat_openai_or_openrouter(
    db: Session, user: User, history: list[dict[str, Any]], user_message: str, *, trace: LlmFlowTrace | None = None
) -> str:
    settings = get_settings()
    prov = (user.llm_provider or "openrouter").lower()
    key = resolve_server_api_key(settings, prov)
    if prov == "openrouter":
        if not key:
            raise ValueError(
                "Server par OpenRouter API key set karo."
            )
        ref = user.openrouter_http_referer or "https://localhost"
        return await chat_openrouter_with_tools(
            db,
            user,
            history,
            user_message,
            api_key=key,
            model=settings.openrouter_model,
            http_referer=ref,
            app_title="AI Financial Survival Assistant",
            trace=trace,
        )

    if not key:
        raise ValueError(
            "Server par OpenAI API key set karo."
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
        trace=trace,
        trace_provider=prov,
    )


async def chat_gemini(
    db: Session, user: User, history: list[dict[str, Any]], user_message: str, *, trace: LlmFlowTrace | None = None
) -> str:
    settings = get_settings()
    key = resolve_server_api_key(settings, "gemini")
    if not key:
        raise ValueError(
            "Server par Gemini API key set karo."
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
        trace=trace,
        trace_provider="gemini",
    )


async def run_provider_chat(
    db: Session, user: User, history: list[dict[str, Any]], user_message: str, *, trace: LlmFlowTrace | None = None
) -> str:
    prov = (user.llm_provider or "openrouter").lower()
    if prov == "gemini":
        return await chat_gemini(db, user, history, user_message, trace=trace)
    return await chat_openai_or_openrouter(db, user, history, user_message, trace=trace)
