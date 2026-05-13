"""Compact expense snapshot for LLM context — survives short chat history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Expense, User

_MAX_ROWS = 80
_MAX_CHARS = 14_000


def _fmt_ist(dt: datetime | None) -> str:
    if dt is None:
        return "?"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M IST")


def build_expense_memory_block(db: Session, user: User) -> str:
    """
    Authoritative list of expenses stored for this user.
    Injected into system prompt so the model does not "forget" logged spends when chat scrolls away.
    """
    now = datetime.now(timezone.utc)
    since_7 = now - timedelta(days=7)
    since_30 = now - timedelta(days=30)

    q7 = (
        db.query(func.coalesce(func.sum(Expense.amount_inr), 0))
        .filter(Expense.user_id == user.id, Expense.created_at >= since_7)
        .scalar()
    )
    q30 = (
        db.query(func.coalesce(func.sum(Expense.amount_inr), 0))
        .filter(Expense.user_id == user.id, Expense.created_at >= since_30)
        .scalar()
    )
    total_7 = Decimal(str(q7 or 0))
    total_30 = Decimal(str(q30 or 0))

    rows = (
        db.query(Expense)
        .filter(Expense.user_id == user.id)
        .order_by(Expense.created_at.desc())
        .limit(_MAX_ROWS)
        .all()
    )

    if not rows:
        inner = "No expenses logged in the app yet.\n"
    else:
        lines: list[str] = []
        for e in rows:
            amt = e.amount_inr
            note = (e.note or "").replace("\n", " ").strip()
            note_bit = f" | {note[:120]}" if note else ""
            lines.append(f"- {_fmt_ist(e.created_at)} | ₹{amt} | {e.category}{note_bit}")
        inner = "\n".join(lines) + "\n"

    header = (
        "---USER_FACTS_EXPENSES (DB rows already saved — source of truth)---\n"
        f"Totals: last 7d ₹{total_7} · last 30d ₹{total_30}.\n"
        f"Rows (newest first, max {_MAX_ROWS}):\n"
    )
    footer = "---END_USER_FACTS_EXPENSES---"

    block = header + inner + footer
    if len(block) > _MAX_CHARS:
        block = block[: _MAX_CHARS - 40] + "\n… (truncated for length)\n" + footer
    return block
