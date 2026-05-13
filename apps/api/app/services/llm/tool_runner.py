"""OpenAI-format tool specs + execution."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Expense, User
from app.services.survivability import affordability_dict
from app.services.wallets import apply_delta_to_active_wallet, set_active_wallet_value, sync_estimated_from_active

OPENAI_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "add_expense",
            "description": "PRIMARY: save one user spend in the database. Populate amount_inr (INR), category (short), optional note.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount_inr": {"type": "number", "description": "Amount in INR"},
                    "category": {"type": "string", "description": "Category e.g. food, cab, rent"},
                    "note": {"type": "string", "description": "Optional note"},
                },
                "required": ["amount_inr", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_spending_summary",
            "description": "Summarize spending over recent days.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Lookback days", "default": 7},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_user_context",
            "description": "Update salary day, rent, estimated cash, and/or free-text money profile (savings goals, habits).",
            "parameters": {
                "type": "object",
                "properties": {
                    "salary_day": {"type": "integer", "description": "Day of month 1-31 when salary arrives"},
                    "monthly_rent_inr": {"type": "number"},
                    "estimated_cash_inr": {"type": "number", "description": "Rough liquid cash now"},
                    "money_profile_notes": {
                        "type": "string",
                        "description": "Free-text profile: goals, EMIs, habits, or pasted export PROFILE section (replaces prior notes if set; keep under ~50k chars).",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "adjust_estimated_cash_inr",
            "description": "Add or subtract from user's estimated liquid cash (bonus, gift, refund, correction).",
            "parameters": {
                "type": "object",
                "properties": {
                    "delta_inr": {
                        "type": "number",
                        "description": "INR change: positive for money in, negative for money out of liquid estimate",
                    }
                },
                "required": ["delta_inr"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_meal_options",
            "description": "Rank food/menu options by INR price. User or model supplies structured rows (name + price). Use notes for combo/offer/includes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "Each item: name, price_inr, optional note (e.g. combo + drink, 50% off)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "price_inr": {"type": "number"},
                                "note": {"type": "string"},
                            },
                            "required": ["name", "price_inr"],
                        },
                    },
                    "max_budget_inr": {
                        "type": "number",
                        "description": "If set, also list options at or under this INR total",
                    },
                },
                "required": ["items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_affordability_hint",
            "description": "Deterministic survivability snapshot: runway vs recent burn.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _parse_args(arguments: str) -> dict[str, Any]:
    try:
        return json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return {}


def run_tool(db: Session, user: User, name: str, arguments: str) -> str:
    args = _parse_args(arguments)
    try:
        if name == "add_expense":
            amt = Decimal(str(args["amount_inr"]))
            cat = str(args["category"])[:64]
            note = args.get("note")
            exp = Expense(user_id=user.id, amount_inr=amt, category=cat, note=note)
            db.add(exp)

            cash_after: Decimal | None = None
            if (
                user.wallet_1_inr is not None
                or user.wallet_2_inr is not None
                or user.wallet_3_inr is not None
                or user.wallet_4_inr is not None
                or user.wallet_5_inr is not None
                or user.estimated_cash_inr is not None
            ):
                if user.wallet_1_inr is None and user.estimated_cash_inr is not None:
                    user.wallet_1_inr = user.estimated_cash_inr
                if user.active_wallet_id not in (1, 2, 3, 4, 5):
                    user.active_wallet_id = 1
                cash_after = apply_delta_to_active_wallet(user, -amt)
                db.add(user)

            db.commit()
            db.refresh(exp)
            if cash_after is not None:
                db.refresh(user)
            return json.dumps(
                {
                    "ok": True,
                    "id": str(exp.id),
                    "amount_inr": str(amt),
                    "category": cat,
                    "estimated_cash_inr_after": str(cash_after) if cash_after is not None else None,
                },
                ensure_ascii=False,
            )

        if name == "get_spending_summary":
            days = int(args.get("days") or 7)
            days = max(1, min(days, 90))
            since = datetime.now(timezone.utc) - timedelta(days=days)
            rows = (
                db.query(Expense.category, func.coalesce(func.sum(Expense.amount_inr), 0))
                .filter(Expense.user_id == user.id, Expense.created_at >= since)
                .group_by(Expense.category)
                .all()
            )
            total = sum((Decimal(str(r[1])) for r in rows), Decimal("0"))
            by_cat = {r[0]: str(Decimal(str(r[1]))) for r in rows}
            return json.dumps(
                {"days": days, "total_inr": str(total), "by_category_inr": by_cat},
                ensure_ascii=False,
            )

        if name == "set_user_context":
            if "salary_day" in args and args["salary_day"] is not None:
                sd = int(args["salary_day"])
                if 1 <= sd <= 31:
                    user.salary_day = sd
            if args.get("monthly_rent_inr") is not None:
                user.monthly_rent_inr = Decimal(str(args["monthly_rent_inr"]))
            if args.get("estimated_cash_inr") is not None:
                set_active_wallet_value(user, Decimal(str(args["estimated_cash_inr"])))
            if args.get("money_profile_notes") is not None:
                note = str(args["money_profile_notes"])[:50000]
                user.money_profile_notes = note
            db.add(user)
            db.commit()
            db.refresh(user)
            return json.dumps({"ok": True, "message": "Profile updated."}, ensure_ascii=False)

        if name == "adjust_estimated_cash_inr":
            delta = Decimal(str(args["delta_inr"]))
            if user.wallet_1_inr is None and user.estimated_cash_inr is not None:
                user.wallet_1_inr = user.estimated_cash_inr
            if user.active_wallet_id not in (1, 2, 3, 4, 5):
                user.active_wallet_id = 1
            apply_delta_to_active_wallet(user, delta)
            sync_estimated_from_active(user)
            db.add(user)
            db.commit()
            db.refresh(user)
            return json.dumps(
                {
                    "ok": True,
                    "estimated_cash_inr": str(user.estimated_cash_inr),
                    "delta_inr": str(delta),
                },
                ensure_ascii=False,
            )

        if name == "get_affordability_hint":
            return json.dumps(affordability_dict(db, user), ensure_ascii=False)

        if name == "compare_meal_options":
            raw = args.get("items") or []
            if not isinstance(raw, list) or not raw:
                return json.dumps({"error": "items must be a non-empty array of {name, price_inr, note?}"})
            parsed: list[dict[str, Any]] = []
            for x in raw[:40]:
                if not isinstance(x, dict):
                    continue
                nm = str(x.get("name", "")).strip()[:160]
                if not nm:
                    continue
                try:
                    pr = Decimal(str(x["price_inr"]))
                except (KeyError, ValueError, TypeError, ArithmeticError):
                    continue
                if pr <= 0:
                    continue
                note = str(x.get("note") or "").strip()[:500]
                parsed.append({"name": nm, "price_inr": pr, "note": note})
            if not parsed:
                return json.dumps({"error": "no valid rows: need name + positive price_inr each"})
            parsed.sort(key=lambda i: i["price_inr"])
            cheapest = parsed[0]
            out: dict[str, Any] = {
                "cheapest": {
                    "name": cheapest["name"],
                    "price_inr": str(cheapest["price_inr"]),
                    "note": cheapest["note"] or None,
                },
                "sorted_by_price_asc": [
                    {"name": i["name"], "price_inr": str(i["price_inr"]), "note": i["note"] or None}
                    for i in parsed
                ],
                "count": len(parsed),
            }
            if args.get("max_budget_inr") is not None:
                try:
                    cap = Decimal(str(args["max_budget_inr"]))
                    under = [i for i in parsed if i["price_inr"] <= cap]
                    out["under_max_budget_inr"] = str(cap)
                    out["options_under_budget"] = [
                        {"name": i["name"], "price_inr": str(i["price_inr"]), "note": i["note"] or None}
                        for i in under
                    ]
                except (ValueError, TypeError, ArithmeticError):
                    pass
            return json.dumps(out, ensure_ascii=False)

        return json.dumps({"error": f"unknown tool {name}"})
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return json.dumps({"error": str(e)}, ensure_ascii=False)
