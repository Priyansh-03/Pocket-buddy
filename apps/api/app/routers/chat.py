import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from openai import APIConnectionError, APITimeoutError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import ChatMessage, ChatSession, User
from app.schemas import ChatRequest, ChatResponse
from app.services.llm.openai_chat import run_provider_chat
from app.services.wallets import apply_delta_to_active_wallet, set_active_wallet_value, sync_estimated_from_active

router = APIRouter(prefix="/chat", tags=["chat"])

# Whole message is `/update` or `/update …` (case-insensitive); persisted as typed, expanded for the LLM only.
_UPDATE_CMD = re.compile(r"^/update(?:\s+(.*))?$", re.IGNORECASE | re.DOTALL)
_BALANCE_IN_TEXT = re.compile(
    r"(?:current|cur|now)?\s*balance(?:\s*(?:is|=|:))?\s*(?:₹|rs\.?|rupees?)?\s*([0-9]+(?:\.[0-9]{1,2})?)",
    re.IGNORECASE,
)
_EXPLICIT_BALANCE_STATEMENT = re.compile(
    r"(?:\bmy\b|\bmera\b|\bmeri\b)?\s*(?:current|cur|now)?\s*balance\s*(?:is\s*[:=]?|[:=])\s*(?:₹|rs\.?|rupees?)?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
    re.IGNORECASE,
)
_AMOUNT_IN_TEXT = re.compile(
    r"(?:₹|rs\.?|rupees?)?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
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
    extra = f"\n\nUser note after the command: {tail}" if tail else ""
    return (
        "The user invoked **/update**.\n\n"
        "Use **USER_FACTS_EXPENSES** (system message) for what is already in the DB. "
        "Scan this chat for stated spends in INR that are **not** already in that list; for each, call **add_expense** with amount_inr, category, note.\n\n"
        "If amount/category unclear, one short question—do not guess.\n\n"
        "Reply briefly: what you logged or “nothing new”."
        + extra
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
        reply = await run_provider_chat(db, current, history, _message_for_llm(body.message))
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
