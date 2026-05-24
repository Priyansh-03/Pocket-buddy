"""OpenAI-format tool specs + execution."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

_FIXED_CATS = {"rent", "emi", "loan", "insurance", "subscription", "electricity", "utility", "utilities"}

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
                    "wallet_id": {"type": "integer", "description": "Wallet to deduct from (1-5). Default: 1 (primary). Only pass if user explicitly says 'wallet 2 se' or similar."},
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
            "description": "Update salary day, rent, estimated cash, wallet amounts, and/or free-text money profile. Use wallet_N_inr to create or update a specific wallet (N = 1–5). Set active_wallet_id to switch the active wallet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "salary_day": {"type": "integer", "description": "Day of month 1-31 when salary arrives"},
                    "monthly_rent_inr": {"type": "number"},
                    "daily_budget_inr": {"type": "number", "description": "User's daily spending budget in INR — set when user mentions their daily estimate or daily budget"},
                    "estimated_cash_inr": {"type": "number", "description": "Rough liquid cash now (sets active wallet)"},
                    "wallet_1_inr": {"type": "number", "description": "Set wallet 1 amount in INR"},
                    "wallet_2_inr": {"type": "number", "description": "Set wallet 2 amount in INR"},
                    "wallet_3_inr": {"type": "number", "description": "Set wallet 3 amount in INR"},
                    "wallet_4_inr": {"type": "number", "description": "Set wallet 4 amount in INR"},
                    "wallet_5_inr": {"type": "number", "description": "Set wallet 5 amount in INR"},
                    "active_wallet_id": {"type": "integer", "description": "Switch active wallet (1–5)"},
                    "profit_inr": {"type": "number", "description": "Set the running buffer/profit directly — use ONLY when user explicitly states their current buffer or profit value (e.g. 'buffer:27'). Do NOT compute this; just pass the number the user gave."},
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
            "name": "record_loan",
            "description": (
                "Record a loan/borrow on a specific wallet WITHOUT changing its balance. "
                "Use this when the user gives explicit final wallet values AND mentions a borrow/transfer — "
                "e.g. 'wallet 2 has 52127 after giving 7000'. "
                "Set wallet_id = the wallet that gave the money, loan_delta = -7000 (negative = lent out). "
                "For repayment, loan_delta = +amount. Loan persists until cleared."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "wallet_id": {"type": "integer", "description": "Wallet that has the outstanding loan (1-5)"},
                    "loan_delta_inr": {"type": "number", "description": "Change to loan: negative = money lent out, positive = repaid"},
                },
                "required": ["wallet_id", "loan_delta_inr"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "transfer_between_wallets",
            "description": (
                "Move money between wallets and track the loan. "
                "Use when user says 'borrowed X from wallet A to wallet B' or 'transferred X from wallet A to B'. "
                "For repayments say is_repayment=true. "
                "from_wallet loses the amount; to_wallet gains it. "
                "Loan indicator is set on from_wallet (negative = borrowed from it, tracks until repaid)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "from_wallet_id": {"type": "integer", "description": "Wallet to take money from (1-5)"},
                    "to_wallet_id": {"type": "integer", "description": "Wallet to add money to (1-5)"},
                    "amount_inr": {"type": "number", "description": "Amount to transfer in INR"},
                    "is_repayment": {"type": "boolean", "description": "True if this is paying back a previous borrow (reverses the loan indicator)"},
                },
                "required": ["from_wallet_id", "to_wallet_id", "amount_inr"],
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

            # --- deterministic wallet deduction — always wallet 1 unless caller set active_wallet_id ---
            cash_after: Decimal | None = None
            any_wallet = any(
                getattr(user, f"wallet_{n}_inr") is not None for n in range(1, 6)
            ) or user.estimated_cash_inr is not None
            if any_wallet:
                if user.wallet_1_inr is None and user.estimated_cash_inr is not None:
                    user.wallet_1_inr = user.estimated_cash_inr
                # default to wallet 1 unless caller explicitly specified
                explicit_wallet = args.get("wallet_id")
                user.active_wallet_id = int(explicit_wallet) if explicit_wallet and 1 <= int(explicit_wallet) <= 5 else 1
                cash_after = apply_delta_to_active_wallet(user, -amt)
                db.add(user)

            db.commit()
            db.refresh(exp)
            db.refresh(user)

            # compute buffer = daily_budget - today's variable spend (excludes rent/fixed)
            buffer_after: str | None = None
            if user.daily_budget_inr is not None:
                now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
                day_start = now_ist.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
                today_var = db.query(func.coalesce(func.sum(Expense.amount_inr), 0)).filter(
                    Expense.user_id == user.id,
                    Expense.created_at >= day_start,
                    ~func.lower(Expense.category).in_(list(_FIXED_CATS)),
                ).scalar()
                buffer_after = str(user.daily_budget_inr - Decimal(str(today_var)))

            return json.dumps(
                {
                    "ok": True,
                    "id": str(exp.id),
                    "amount_inr": str(amt),
                    "category": cat,
                    "wallet_balance_after": str(cash_after) if cash_after is not None else None,
                    "buffer_after": buffer_after,
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
            for wn in (1, 2, 3, 4, 5):
                key = f"wallet_{wn}_inr"
                if args.get(key) is not None:
                    setattr(user, key, Decimal(str(args[key])))
            if args.get("active_wallet_id") is not None:
                wid = int(args["active_wallet_id"])
                if 1 <= wid <= 5:
                    user.active_wallet_id = wid
            if args.get("daily_budget_inr") is not None:
                user.daily_budget_inr = Decimal(str(args["daily_budget_inr"]))
            if args.get("estimated_cash_inr") is not None:
                set_active_wallet_value(user, Decimal(str(args["estimated_cash_inr"])))
            sync_estimated_from_active(user)
            if args.get("profit_inr") is not None:
                user.profit_inr = Decimal(str(args["profit_inr"]))
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

        if name == "record_loan":
            wid = int(args["wallet_id"])
            if not (1 <= wid <= 5):
                return json.dumps({"error": "wallet_id must be 1-5"})
            if wid == 1:
                return json.dumps({"error": "Loans are never tracked on wallet 1 (primary spending wallet)"})
            delta = Decimal(str(args["loan_delta_inr"]))
            current_loan = getattr(user, f"wallet_{wid}_loan_inr") or Decimal("0")
            new_loan = current_loan + delta
            setattr(user, f"wallet_{wid}_loan_inr", new_loan if new_loan != Decimal("0") else None)
            db.add(user)
            db.commit()
            db.refresh(user)
            return json.dumps({"ok": True, f"wallet_{wid}_loan_inr": str(getattr(user, f"wallet_{wid}_loan_inr"))}, ensure_ascii=False)

        if name == "adjust_profit":
            delta = Decimal(str(args["delta_inr"]))
            user.profit_inr = (user.profit_inr or Decimal("0")) + delta
            db.add(user)
            db.commit()
            db.refresh(user)
            return json.dumps({"ok": True, "profit_inr": str(user.profit_inr)}, ensure_ascii=False)

        if name == "transfer_between_wallets":
            fid = int(args["from_wallet_id"])
            tid = int(args["to_wallet_id"])
            amt = Decimal(str(args["amount_inr"]))
            is_repayment = bool(args.get("is_repayment", False))
            if not (1 <= fid <= 5 and 1 <= tid <= 5 and fid != tid):
                return json.dumps({"error": "from_wallet_id and to_wallet_id must be 1-5 and different"})
            f_bal = getattr(user, f"wallet_{fid}_inr") or Decimal("0")
            t_bal = getattr(user, f"wallet_{tid}_inr") or Decimal("0")
            setattr(user, f"wallet_{fid}_inr", f_bal - amt)
            setattr(user, f"wallet_{tid}_inr", t_bal + amt)
            # loan indicator only on savings wallets (never wallet 1)
            if fid != 1:
                f_loan = getattr(user, f"wallet_{fid}_loan_inr") or Decimal("0")
                new_loan = f_loan + amt if is_repayment else f_loan - amt
                setattr(user, f"wallet_{fid}_loan_inr", new_loan if new_loan != Decimal("0") else None)
            sync_estimated_from_active(user)
            db.add(user)
            db.commit()
            db.refresh(user)
            return json.dumps({
                "ok": True,
                f"wallet_{fid}_inr": str(getattr(user, f"wallet_{fid}_inr")),
                f"wallet_{tid}_inr": str(getattr(user, f"wallet_{tid}_inr")),
                f"wallet_{fid}_loan_inr": str(getattr(user, f"wallet_{fid}_loan_inr")),
            }, ensure_ascii=False)

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
