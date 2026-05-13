from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import LlmSettingsOut, LlmSettingsPut, UserContextUpdate, UserOut
from app.services.llm.openai_chat import server_key_configured
from app.services.wallets import active_wallet_value, set_active_wallet_value, sync_estimated_from_active

router = APIRouter(prefix="/users", tags=["users"])


@router.patch("/me", response_model=UserOut)
def update_me(
    data: UserContextUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> User:
    def _set_wallet(i: int, value):
        if i == 1:
            current.wallet_1_inr = value
        elif i == 2:
            current.wallet_2_inr = value
        elif i == 3:
            current.wallet_3_inr = value
        elif i == 4:
            current.wallet_4_inr = value
        elif i == 5:
            current.wallet_5_inr = value

    def _get_wallet(i: int):
        if i == 1:
            return current.wallet_1_inr
        if i == 2:
            return current.wallet_2_inr
        if i == 3:
            return current.wallet_3_inr
        if i == 4:
            return current.wallet_4_inr
        if i == 5:
            return current.wallet_5_inr
        return None

    if current.wallet_1_inr is None and current.estimated_cash_inr is not None:
        current.wallet_1_inr = current.estimated_cash_inr
    if current.active_wallet_id not in (1, 2, 3, 4, 5):
        current.active_wallet_id = 1

    if data.salary_day is not None:
        current.salary_day = data.salary_day
    if data.monthly_rent_inr is not None:
        current.monthly_rent_inr = data.monthly_rent_inr
    if data.estimated_cash_inr is not None:
        set_active_wallet_value(current, data.estimated_cash_inr)
    if data.wallet_1_inr is not None:
        current.wallet_1_inr = data.wallet_1_inr
    if data.wallet_2_inr is not None:
        current.wallet_2_inr = data.wallet_2_inr
    if data.wallet_3_inr is not None:
        current.wallet_3_inr = data.wallet_3_inr
    if data.wallet_4_inr is not None:
        current.wallet_4_inr = data.wallet_4_inr
    if data.wallet_5_inr is not None:
        current.wallet_5_inr = data.wallet_5_inr
    if data.active_wallet_id is not None:
        current.active_wallet_id = data.active_wallet_id
    if data.remove_wallet_ids:
        ids = [x for x in data.remove_wallet_ids if 1 <= x <= 5]
        for wid in ids:
            _set_wallet(wid, None)
        if current.active_wallet_id in ids:
            nxt = next((i for i in range(1, 6) if _get_wallet(i) is not None), 1)
            current.active_wallet_id = nxt
    if (
        data.wallet_1_inr is not None
        or data.wallet_2_inr is not None
        or data.wallet_3_inr is not None
        or data.wallet_4_inr is not None
        or data.wallet_5_inr is not None
        or data.active_wallet_id is not None
        or bool(data.remove_wallet_ids)
    ):
        sync_estimated_from_active(current)
    elif data.estimated_cash_inr is None:
        # keep shadow in sync if active wallet changed externally
        current.estimated_cash_inr = active_wallet_value(current)
    if data.money_profile_notes is not None:
        current.money_profile_notes = data.money_profile_notes
    db.add(current)
    db.commit()
    db.refresh(current)
    return current


def _llm_status(user: User) -> LlmSettingsOut:
    settings = get_settings()
    prov = user.llm_provider or "openai"
    return LlmSettingsOut(
        provider=prov,
        openrouter_http_referer=user.openrouter_http_referer,
        server_key_configured=server_key_configured(settings, prov),
    )


@router.get("/me/llm", response_model=LlmSettingsOut)
def get_llm_settings(current: User = Depends(get_current_user)) -> LlmSettingsOut:
    return _llm_status(current)


@router.put("/me/llm", response_model=LlmSettingsOut)
def put_llm_settings(
    data: LlmSettingsPut,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> LlmSettingsOut:
    current.llm_provider = data.provider
    if data.openrouter_http_referer is not None:
        current.openrouter_http_referer = data.openrouter_http_referer or None
    db.add(current)
    db.commit()
    db.refresh(current)
    return _llm_status(current)
