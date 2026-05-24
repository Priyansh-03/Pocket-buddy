import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from openai import APIConnectionError, APITimeoutError
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models import ChatMessage, ChatSession, Expense, User
from app.schemas import ChatRequest, ChatResponse
from app.services.llm.flow_trace import maybe_create_flow_trace
from app.services.llm.openai_chat import run_provider_chat
from app.services.wallets import apply_delta_to_active_wallet, set_active_wallet_value, sync_estimated_from_active

router = APIRouter(prefix="/chat", tags=["chat"])

# Whole message is `/update` or `/update …` (case-insensitive); persisted as typed, expanded for the LLM only.
_UPDATE_CMD = re.compile(r"^/update(?:\s+(.*))?$", re.IGNORECASE | re.DOTALL)
_BALANCE_IN_TEXT = re.compile(
    r"(?:current|cur|now)?\s*(?:balance|cash)(?:\s*(?:is|=|:))?\s*(?:₹|rs\.?|rupees?)?\s*([0-9]+(?:\.[0-9]{1,2})?)",
    re.IGNORECASE,
)
_EXPLICIT_BALANCE_STATEMENT = re.compile(
    r"(?:\bmy\b|\bmera\b|\bmeri\b)?\s*(?:current|cur|now|final)?\s*(?:balance|cash)\s*(?:is\s*[:=]?|[:=])\s*(?:₹|rs\.?|rupees?)?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
    re.IGNORECASE,
)
_AMOUNT_IN_TEXT = re.compile(
    r"(?:₹|rs\.?|rupees?)?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
    re.IGNORECASE,
)
_WALLET_AMOUNT_STATEMENT = re.compile(
    r"(?:"
    r"(?:amount|balance|cash)\s+in\s+wallet\s*([1-5])"
    r"|wallet\s*([1-5])\s*(?:amount|balance|cash)"
    r")\s*(?:is\s*[:=]?|[:=])\s*(?:₹|rs\.?|rupees?)?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
    re.IGNORECASE,
)
_BUFFER_STATEMENT = re.compile(
    r"(?:buffer|profit)\s*(?:set\s+to|is\s*[:=]?|[:=])\s*(?:₹|rs\.?|rupees?)?\s*(-?[0-9][0-9,]*(?:\.[0-9]{1,2})?)",
    re.IGNORECASE,
)
_LOAN_CLEAR_STATEMENT = re.compile(
    r"wallet\s*([2-5])\s*(?:ka\s+)?loan\s*(?:clear|hata|remove|zero|done|paid|wapas|return|cleared|off)",
    re.IGNORECASE,
)

_FAST_EXPENSE_QUERY = re.compile(
    r"^(my\s+)?(expenses?|kharch|spending|kharchay?|aaj\s+kitna|kitna\s+kharch|what.*spent|how\s+much.*spent|show.*expenses?|expense\s+summary|mera\s+kharch)(\s+(today|aaj|is\s+week|this\s+week|is\s+month|this\s+month))?[?।\s]*$",
    re.IGNORECASE,
)
_FAST_BALANCE_QUERY = re.compile(
    r"^(my\s+)?(balance|kitna\s+bacha|how\s+much\s+left|wallet\s+balance|paisa\s+kitna|kitna\s+hai)[?।\s]*$",
    re.IGNORECASE,
)

_POSITIVE_CASH_WORDS = (
    "credit",
    "credited",
    "receive",
    "received",
    "got",
    "income",
    "salary",
    "bonus",
    "refund",
    "cashback",
    "topup",
    "top-up",
    "add to wallet",
)
_NEGATIVE_CASH_WORDS = (
    "debit",
    "debited",
    "deduct",
    "deducted",
    "withdraw",
    "withdrew",
    "withdrawn",
)
_EXPENSE_WORDS = (
    "spent",
    "spend",
    "paid",
    "pay",
    "bought",
    "buy",
    "ordered",
    "order",
    "expense",
)


def _fmt_inr(v: Decimal) -> str:
    s = format(v, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def _ist_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Kolkata"))


_FIXED_CATEGORIES = {"rent", "emi", "loan", "insurance", "subscription", "electricity", "utility", "utilities"}


def _by_category(rows: list) -> dict[str, Decimal]:
    cats: dict[str, Decimal] = {}
    for e in rows:
        cat = e.category or "misc"
        cats[cat] = cats.get(cat, Decimal("0")) + e.amount_inr
    return dict(sorted(cats.items(), key=lambda x: x[1], reverse=True))


def _fast_expense_reply(db: Session, user: User) -> str:
    now_ist = _ist_now()
    day_start_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    day_start_utc = day_start_ist.astimezone(timezone.utc)
    week_start_utc = datetime.now(timezone.utc) - timedelta(days=7)
    month_start_utc = datetime.now(timezone.utc) - timedelta(days=30)

    today_rows = (
        db.query(Expense)
        .filter(Expense.user_id == user.id, Expense.created_at >= day_start_utc)
        .order_by(Expense.created_at.desc())
        .all()
    )
    week_rows = (
        db.query(Expense)
        .filter(Expense.user_id == user.id, Expense.created_at >= week_start_utc, Expense.created_at < day_start_utc)
        .all()
    )
    month_rows = (
        db.query(Expense)
        .filter(Expense.user_id == user.id, Expense.created_at >= month_start_utc, Expense.created_at < day_start_utc)
        .all()
    )

    today_total = sum(e.amount_inr for e in today_rows)
    today_daily = sum(e.amount_inr for e in today_rows if e.category.lower() not in _FIXED_CATEGORIES)
    today_fixed = today_total - today_daily

    date_str = now_ist.strftime("%d %b %Y")
    lines = [f"Aaj ({date_str}): ₹{today_total:,.2f}"]
    if today_rows:
        for e in today_rows:
            note = f" — {e.note}" if e.note else ""
            tag = " [fixed]" if e.category.lower() in _FIXED_CATEGORIES else ""
            lines.append(f"  • ₹{e.amount_inr:,.2f} | {e.category}{tag}{note}")
        if today_fixed > 0:
            lines.append(f"  Daily spend (rent/fixed hataake): ₹{today_daily:,.2f}")
    else:
        lines.append("  Koi expense nahi.")

    if week_rows:
        week_total = sum(e.amount_inr for e in week_rows)
        week_cats = _by_category(week_rows)
        lines.append(f"\nPichle 6 din: ₹{week_total:,.2f}")
        for cat, amt in week_cats.items():
            lines.append(f"  • {cat}: ₹{amt:,.2f}")
    else:
        lines.append("\nPichle 6 din: ₹0 (aaj se pehle koi expense nahi)")

    if month_rows:
        month_total = sum(e.amount_inr for e in month_rows)
        month_cats = _by_category(month_rows)
        lines.append(f"\nPichle 29 din (aaj ke alawa): ₹{month_total:,.2f}")
        for cat, amt in month_cats.items():
            lines.append(f"  • {cat}: ₹{amt:,.2f}")

    if user.daily_budget_inr is not None:
        remaining = user.daily_budget_inr - today_daily
        sign = "+" if remaining >= 0 else ""
        lines.append(f"\nAaj ka budget: ₹{user.daily_budget_inr:,.2f} | Daily spend: ₹{today_daily:,.2f} | Bacha: {sign}₹{remaining:,.2f}")

    return "\n".join(lines)


def _fast_balance_reply(user: User) -> str:
    active = user.active_wallet_id if user.active_wallet_id in (1, 2, 3, 4, 5) else 1
    active_bal = getattr(user, f"wallet_{active}_inr")
    lines = []
    if active_bal is not None:
        lines.append(f"Wallet {active} (active): ₹{active_bal:,.2f}")
    else:
        lines.append("Wallet balance set nahi hai. Pehle wallet mein amount daalo.")

    for n in range(1, 6):
        if n == active:
            continue
        bal = getattr(user, f"wallet_{n}_inr")
        if bal is not None:
            loan = getattr(user, f"wallet_{n}_loan_inr")
            loan_str = f" | loan: ₹{loan:,.2f}" if loan is not None else ""
            lines.append(f"Wallet {n}: ₹{bal:,.2f}{loan_str}")

    if user.profit_inr is not None and user.daily_budget_inr is not None:
        sign = "+" if user.profit_inr >= 0 else ""
        lines.append(f"\nBuffer: {sign}₹{user.profit_inr:,.2f}")

    return "\n".join(lines)


def _extract_balance_update(user_message: str) -> Decimal | None:
    """
    Parse `/update ...` balance statements deterministically to avoid accidental expense logging.
    Example: `/update current balance is 3449.76 rupee`
    """
    raw = user_message.strip()
    m = _UPDATE_CMD.match(raw)
    if not m:
        return None
    tail = (m.group(1) or "").strip()
    if not tail:
        return None
    bm = _BALANCE_IN_TEXT.search(tail)
    if not bm:
        return None
    try:
        val = Decimal(bm.group(1))
    except (InvalidOperation, TypeError):
        return None
    if val < 0:
        return None
    return val


def _extract_explicit_balance_statement(user_message: str) -> Decimal | None:
    """
    Parse plain-language explicit balance declarations as source of truth.
    Examples:
    - "my current balance is: 3449.76"
    - "mera balance: ₹3449.76"
    """
    raw = user_message.strip()
    m = _EXPLICIT_BALANCE_STATEMENT.search(raw)
    if not m:
        return None
    try:
        val = Decimal(m.group(1).replace(",", ""))
    except (InvalidOperation, TypeError):
        return None
    if val < 0:
        return None
    return val


def _extract_buffer_statement(user_message: str) -> Decimal | None:
    """Parse 'buffer:27' or 'profit is -500' → Decimal value to set profit_inr directly."""
    m = _BUFFER_STATEMENT.search(user_message.strip())
    if not m:
        return None
    try:
        return Decimal(m.group(1).replace(",", ""))
    except (InvalidOperation, TypeError):
        return None


def _extract_wallet_amount_statement(user_message: str) -> tuple[int, Decimal] | None:
    """Parse 'amount in wallet2 is: 59127.28' → (2, 59127.28) as a SET operation."""
    m = _WALLET_AMOUNT_STATEMENT.search(user_message.strip())
    if not m:
        return None
    wallet_id = int(m.group(1) or m.group(2))
    try:
        val = Decimal(m.group(3).replace(",", ""))
    except (InvalidOperation, TypeError):
        return None
    if val < 0:
        return None
    return wallet_id, val


def _extract_cash_delta(user_message: str) -> Decimal | None:
    """
    Deterministic wallet delta parser for natural text.
    Examples:
    - "I got credited 20 rupees" -> +20
    - "wallet debited by 15" -> -15
    """
    raw = user_message.strip().lower()
    # Let explicit `/update balance ...` handler own this path.
    if _extract_balance_update(user_message) is not None:
        return None
    if _extract_explicit_balance_statement(user_message) is not None:
        return None

    has_positive = any(w in raw for w in _POSITIVE_CASH_WORDS)
    has_negative = any(w in raw for w in _NEGATIVE_CASH_WORDS)
    has_expense = any(w in raw for w in _EXPENSE_WORDS)
    if not has_positive and not has_negative:
        return None
    # Avoid misclassifying normal expense messages that mention "credit card".
    if has_expense and has_positive and not has_negative:
        return None

    m = _AMOUNT_IN_TEXT.search(raw)
    if not m:
        return None
    try:
        amt = Decimal(m.group(1).replace(",", ""))
    except (InvalidOperation, TypeError):
        return None
    if amt <= 0:
        return None

    sign = Decimal("-1") if has_negative and not has_positive else Decimal("1")
    return amt * sign


def _message_for_llm(user_message: str) -> str:
    """Keep DB `ChatMessage.content` as the raw user text; send an instruction expansion for `/update`."""
    raw = user_message.strip()
    m = _UPDATE_CMD.match(raw)
    if not m:
        return user_message
    tail = (m.group(1) or "").strip()
    inline = ("\n\nInline expenses to log now: " + tail) if tail else ""
    return (
        "The user invoked **/update**.\n\n"
        "Step 1 - if there are inline expenses listed after the command, call **add_expense** for each one immediately.\n"
        "Step 2 - use **USER_FACTS_EXPENSES** (system message) as the already-logged list. "
        "Scan this chat for any additional stated spends in INR **not** already in that list; for each, call **add_expense**.\n\n"
        "If amount/category unclear, one short question - do not guess.\n\n"
        'Reply briefly: what you logged or "nothing new".'
        + inline
    )


def _history_from_db(db: Session, session_id: uuid.UUID, limit: int = 28) -> list[dict[str, Any]]:
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    rows = list(reversed(rows))
    out: list[dict[str, Any]] = []
    for r in rows:
        if r.role in ("user", "assistant") and (r.content or "").strip():
            out.append({"role": r.role, "content": r.content or ""})
    return out


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> ChatResponse:
    if body.session_id:
        session = (
            db.query(ChatSession)
            .filter(ChatSession.id == body.session_id, ChatSession.user_id == current.id)
            .first()
        )
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    else:
        session = ChatSession(user_id=current.id, title=None)
        db.add(session)
        db.commit()
        db.refresh(session)

    history = _history_from_db(db, session.id)
    user_row = ChatMessage(session_id=session.id, role="user", content=body.message)
    db.add(user_row)
    db.commit()

    balance_override = _extract_balance_update(body.message)
    if balance_override is not None:
        if current.wallet_1_inr is None and current.estimated_cash_inr is not None:
            current.wallet_1_inr = current.estimated_cash_inr
        if current.active_wallet_id not in (1, 2, 3, 4, 5):
            current.active_wallet_id = 1
        set_active_wallet_value(current, balance_override)
        db.add(current)
        db.commit()
        db.refresh(current)
        reply = f"Updated. Estimated cash is now ₹{_fmt_inr(balance_override)}."
        asst = ChatMessage(session_id=session.id, role="assistant", content=reply)
        db.add(asst)
        db.commit()
        return ChatResponse(session_id=session.id, reply=reply)

    explicit_balance = _extract_explicit_balance_statement(body.message)
    if explicit_balance is not None:
        if current.wallet_1_inr is None and current.estimated_cash_inr is not None:
            current.wallet_1_inr = current.estimated_cash_inr
        if current.active_wallet_id not in (1, 2, 3, 4, 5):
            current.active_wallet_id = 1
        set_active_wallet_value(current, explicit_balance)
        db.add(current)
        db.commit()
        db.refresh(current)
        reply = f"Got it. Latest balance set to ₹{_fmt_inr(explicit_balance)}."
        asst = ChatMessage(session_id=session.id, role="assistant", content=reply)
        db.add(asst)
        db.commit()
        return ChatResponse(session_id=session.id, reply=reply)

    wallet_set = _extract_wallet_amount_statement(body.message)
    if wallet_set is not None:
        wid, wval = wallet_set
        setattr(current, f"wallet_{wid}_inr", wval)
        # do NOT change active_wallet_id — wallet 1 stays primary
        sync_estimated_from_active(current)
        db.add(current)
        db.commit()
        db.refresh(current)
        reply = f"Wallet {wid} set to ₹{_fmt_inr(wval)}."
        asst = ChatMessage(session_id=session.id, role="assistant", content=reply)
        db.add(asst)
        db.commit()
        return ChatResponse(session_id=session.id, reply=reply)

    buffer_val = _extract_buffer_statement(body.message)
    if buffer_val is not None:
        current.profit_inr = buffer_val
        db.add(current)
        db.commit()
        db.refresh(current)
        sign = "+" if buffer_val >= 0 else ""
        reply = f"Buffer set to {sign}₹{_fmt_inr(buffer_val)}."
        asst = ChatMessage(session_id=session.id, role="assistant", content=reply)
        db.add(asst)
        db.commit()
        return ChatResponse(session_id=session.id, reply=reply)

    loan_clear_m = _LOAN_CLEAR_STATEMENT.search(body.message.strip())
    if loan_clear_m:
        wid = int(loan_clear_m.group(1))
        setattr(current, f"wallet_{wid}_loan_inr", None)
        db.add(current)
        db.commit()
        reply = f"Wallet {wid} ka loan clear ho gaya."
        asst = ChatMessage(session_id=session.id, role="assistant", content=reply)
        db.add(asst)
        db.commit()
        return ChatResponse(session_id=session.id, reply=reply)

    if _FAST_EXPENSE_QUERY.match(body.message.strip()):
        reply = _fast_expense_reply(db, current)
        asst = ChatMessage(session_id=session.id, role="assistant", content=reply)
        db.add(asst)
        db.commit()
        return ChatResponse(session_id=session.id, reply=reply)

    if _FAST_BALANCE_QUERY.match(body.message.strip()):
        reply = _fast_balance_reply(current)
        asst = ChatMessage(session_id=session.id, role="assistant", content=reply)
        db.add(asst)
        db.commit()
        return ChatResponse(session_id=session.id, reply=reply)

    cash_delta = _extract_cash_delta(body.message)
    if cash_delta is not None:
        if current.wallet_1_inr is None and current.estimated_cash_inr is not None:
            current.wallet_1_inr = current.estimated_cash_inr
        if current.active_wallet_id not in (1, 2, 3, 4, 5):
            current.active_wallet_id = 1
        apply_delta_to_active_wallet(current, cash_delta)
        sync_estimated_from_active(current)
        db.add(current)
        db.commit()
        db.refresh(current)
        direction = "added to" if cash_delta >= 0 else "deducted from"
        abs_delta = abs(cash_delta)
        reply = (
            f"Got it. ₹{_fmt_inr(abs_delta)} {direction} wallet. "
            f"Estimated cash is now ₹{_fmt_inr(current.estimated_cash_inr)}."
        )
        asst = ChatMessage(session_id=session.id, role="assistant", content=reply)
        db.add(asst)
        db.commit()
        return ChatResponse(session_id=session.id, reply=reply)

    try:
        settings = get_settings()
        prov = (current.llm_provider or "openrouter").lower()
        model = settings.gemini_model if prov == "gemini" else settings.openai_model
        trace = maybe_create_flow_trace(
            settings,
            user_id=str(current.id),
            session_id=str(session.id),
            provider=prov,
            model=model,
        )
        reply = await run_provider_chat(
            db, current, history, _message_for_llm(body.message), trace=trace
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except APITimeoutError as e:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=(
                "The AI provider took too long to respond. Try again, shorten the message, "
                "or increase LLM_READ_TIMEOUT_SECONDS in apps/api/.env and restart the API."
            ),
        ) from e
    except (APIConnectionError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"Could not reach the AI provider ({e!s}). Check internet/VPN, model name, "
                "and (for OpenRouter/Gemini) the correct provider + base URL."
            ),
        ) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM provider error: {e!s}",
        ) from e

    db.refresh(current)

    asst = ChatMessage(session_id=session.id, role="assistant", content=reply)
    db.add(asst)
    db.commit()
    return ChatResponse(session_id=session.id, reply=reply)
