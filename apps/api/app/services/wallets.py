from __future__ import annotations

from decimal import Decimal

from app.models import User


def active_wallet_value(user: User) -> Decimal | None:
    if user.active_wallet_id == 2:
        return user.wallet_2_inr
    if user.active_wallet_id == 3:
        return user.wallet_3_inr
    if user.active_wallet_id == 4:
        return user.wallet_4_inr
    if user.active_wallet_id == 5:
        return user.wallet_5_inr
    return user.wallet_1_inr


def set_active_wallet_value(user: User, value: Decimal | None) -> None:
    if user.active_wallet_id == 2:
        user.wallet_2_inr = value
    elif user.active_wallet_id == 3:
        user.wallet_3_inr = value
    elif user.active_wallet_id == 4:
        user.wallet_4_inr = value
    elif user.active_wallet_id == 5:
        user.wallet_5_inr = value
    else:
        user.wallet_1_inr = value
    user.estimated_cash_inr = value


def sync_estimated_from_active(user: User) -> None:
    user.estimated_cash_inr = active_wallet_value(user)


def apply_delta_to_active_wallet(user: User, delta: Decimal) -> Decimal:
    cur = active_wallet_value(user)
    base = cur if cur is not None else Decimal("0")
    nxt = base + delta
    set_active_wallet_value(user, nxt)
    return nxt
