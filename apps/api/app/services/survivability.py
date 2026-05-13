from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Expense, User


@dataclass
class AffordabilityResult:
    label: str
    summary: str
    days_until_salary: int | None
    spent_last_7_days_inr: Decimal
    daily_burn_inr: Decimal
    estimated_cash_inr: Decimal | None
    monthly_rent_inr: Decimal | None
    buffer_inr: Decimal | None
    current_balance_estimate_inr: Decimal | None


def _fmt_inr_indian(v: Decimal | None) -> str:
    if v is None:
        return "not set"
    s = format(v, "f")
    neg = s.startswith("-")
    if neg:
        s = s[1:]
    if "." in s:
        int_part, frac = s.split(".", 1)
        frac = frac.rstrip("0")
    else:
        int_part, frac = s, ""
    if len(int_part) > 3:
        last3 = int_part[-3:]
        rest = int_part[:-3]
        parts: list[str] = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        int_part = ",".join(parts + [last3])
    out = int_part + (f".{frac}" if frac else "")
    return f"-₹{out}" if neg else f"₹{out}"


def days_until_next_salary(salary_day: int, today: date | None = None) -> int:
    """Days from today (exclusive of today as 'payday eve' style) to next salary date."""
    t = today or datetime.now(timezone.utc).date()
    y, m = t.year, t.month
    try:
        current_month_pay = date(y, m, salary_day)
    except ValueError:
        import calendar

        last = calendar.monthrange(y, m)[1]
        current_month_pay = date(y, m, min(salary_day, last))

    if t < current_month_pay:
        return (current_month_pay - t).days
    if t == current_month_pay:
        return 0
    if m == 12:
        ny, nm = y + 1, 1
    else:
        ny, nm = y, m + 1
    try:
        next_pay = date(ny, nm, salary_day)
    except ValueError:
        import calendar

        last = calendar.monthrange(ny, nm)[1]
        next_pay = date(ny, nm, min(salary_day, last))
    return (next_pay - t).days


def sum_expenses_since(db: Session, user_id, since: datetime) -> Decimal:
    row = (
        db.query(func.coalesce(func.sum(Expense.amount_inr), 0))
        .filter(Expense.user_id == user_id, Expense.created_at >= since)
        .scalar()
    )
    return Decimal(str(row or 0))


def compute_affordability(db: Session, user: User) -> AffordabilityResult:
    now = datetime.now(timezone.utc)
    since_7d = now - timedelta(days=7)
    spent_7d = sum_expenses_since(db, user.id, since_7d)
    daily = (spent_7d / Decimal(7)) if spent_7d > 0 else Decimal("0")

    if user.salary_day is None:
        return AffordabilityResult(
            label="unknown",
            summary=(
                "Salary day is not set. Please share salary date between 1 and 31."
            ),
            days_until_salary=None,
            spent_last_7_days_inr=spent_7d,
            daily_burn_inr=daily,
            estimated_cash_inr=user.estimated_cash_inr,
            monthly_rent_inr=user.monthly_rent_inr,
            buffer_inr=None,
            current_balance_estimate_inr=user.estimated_cash_inr,
        )

    dus = days_until_next_salary(user.salary_day, now.date())
    projected = daily * Decimal(max(dus, 0))

    cash = user.estimated_cash_inr
    rent = user.monthly_rent_inr or Decimal("0")

    if cash is None:
        return AffordabilityResult(
            label="unknown",
            summary=(
                f"Last 7 days spend is {_fmt_inr_indian(spent_7d)}. "
                f"Daily average is {_fmt_inr_indian(daily)}. "
                "Estimated cash is not set yet. Please share current wallet amount."
            ),
            days_until_salary=dus,
            spent_last_7_days_inr=spent_7d,
            daily_burn_inr=daily,
            estimated_cash_inr=None,
            monthly_rent_inr=user.monthly_rent_inr,
            buffer_inr=None,
            current_balance_estimate_inr=None,
        )

    remaining = cash - rent
    buffer = remaining - projected

    if buffer >= remaining * Decimal("0.2"):
        label = "comfortable"
    elif buffer >= 0:
        label = "tight"
    else:
        label = "risky"

    if label == "comfortable":
        mood = "You look comfortable for now."
    elif label == "tight":
        mood = "It looks a bit tight. Spend carefully."
    else:
        mood = "Risk is high. Please cut spending till salary."

    summary = (
        f"Current cash is {_fmt_inr_indian(cash)}. "
        f"Days to salary date {user.salary_day}: {dus}. "
        f"Last 7 days spend: {_fmt_inr_indian(spent_7d)}. "
        f"Daily average: {_fmt_inr_indian(daily)}. "
        f"Expected spend till salary: {_fmt_inr_indian(projected)}. "
        f"Monthly rent considered: {_fmt_inr_indian(rent)}. "
        f"Remaining buffer estimate: {_fmt_inr_indian(buffer)}. "
        f"{mood}"
    )

    return AffordabilityResult(
        label=label,
        summary=summary,
        days_until_salary=dus,
        spent_last_7_days_inr=spent_7d,
        daily_burn_inr=daily,
        estimated_cash_inr=cash,
        monthly_rent_inr=user.monthly_rent_inr,
        buffer_inr=buffer,
        current_balance_estimate_inr=cash,
    )


def affordability_dict(db: Session, user: User) -> dict:
    r = compute_affordability(db, user)
    return {
        "label": r.label,
        "summary": r.summary,
        "days_until_salary": r.days_until_salary,
        "spent_last_7_days_inr": str(r.spent_last_7_days_inr),
        "daily_burn_inr": str(r.daily_burn_inr),
        "estimated_cash_inr": str(r.estimated_cash_inr) if r.estimated_cash_inr is not None else None,
        "monthly_rent_inr": str(r.monthly_rent_inr) if r.monthly_rent_inr is not None else None,
        "buffer_inr": str(r.buffer_inr) if r.buffer_inr is not None else None,
        "current_balance_estimate_inr": (
            str(r.current_balance_estimate_inr) if r.current_balance_estimate_inr is not None else None
        ),
    }
