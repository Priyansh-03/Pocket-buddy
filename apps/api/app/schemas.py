from datetime import datetime
from decimal import Decimal
from uuid import UUID

from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: UUID
    email: str
    salary_day: int | None
    monthly_rent_inr: Decimal | None
    estimated_cash_inr: Decimal | None
    daily_budget_inr: Decimal | None = None
    profit_inr: Decimal | None = None
    wallet_1_inr: Decimal | None = None
    wallet_2_inr: Decimal | None = None
    wallet_3_inr: Decimal | None = None
    wallet_4_inr: Decimal | None = None
    wallet_5_inr: Decimal | None = None
    wallet_1_loan_inr: Decimal | None = None
    wallet_2_loan_inr: Decimal | None = None
    wallet_3_loan_inr: Decimal | None = None
    wallet_4_loan_inr: Decimal | None = None
    wallet_5_loan_inr: Decimal | None = None
    active_wallet_id: int = 1
    money_profile_notes: str | None = None
    food_menu_text: str | None = None
    remember_text: str | None = None
    llm_provider: str = "openrouter"

    model_config = {"from_attributes": True}


class TodaySummary(BaseModel):
    budget_inr: Decimal | None
    spent_inr: Decimal
    profit_inr: Decimal | None


class UserContextUpdate(BaseModel):
    salary_day: int | None = Field(
        default=None,
        ge=1,
        le=31,
        description="Day of month (1–31) when salary is credited",
    )
    monthly_rent_inr: Decimal | None = None
    estimated_cash_inr: Decimal | None = None
    daily_budget_inr: Decimal | None = None
    wallet_1_inr: Decimal | None = None
    wallet_2_inr: Decimal | None = None
    wallet_3_inr: Decimal | None = None
    wallet_4_inr: Decimal | None = None
    wallet_5_inr: Decimal | None = None
    active_wallet_id: int | None = Field(default=None, ge=1, le=5)
    remove_wallet_ids: list[int] | None = None
    clear_loan_wallet_ids: list[int] | None = None  # set these wallet loans to null
    money_profile_notes: str | None = Field(default=None, max_length=50000)
    food_menu_text: str | None = Field(default=None, max_length=50000)
    remember_text: str | None = Field(default=None, max_length=50000)


class ExpenseCreate(BaseModel):
    amount_inr: Decimal = Field(gt=0)
    category: str = Field(max_length=64)
    note: str | None = None


class ExpenseOut(BaseModel):
    id: UUID
    amount_inr: Decimal
    category: str
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=100_000)
    session_id: UUID | None = None


class ChatResponse(BaseModel):
    session_id: UUID
    reply: str


class ImportWallet(BaseModel):
    id: int = Field(ge=1, le=5)
    label: str = ""
    balance_inr: Decimal = Decimal("0")


class ImportRecurring(BaseModel):
    item: str
    amount_inr: Decimal = Decimal("0")
    cadence: str = "monthly"
    note: str = ""


class ImportExpenseRow(BaseModel):
    date: str = "unknown"
    description: str
    amount_inr: Decimal = Field(gt=0)
    category: str = "misc"


class ImportProfile(BaseModel):
    salary_day_of_month: int | None = Field(default=None, ge=1, le=31)
    monthly_rent_inr: Decimal | None = None
    daily_budget_inr: Decimal | None = None
    wallets: list[ImportWallet] = []


class FinancialImport(BaseModel):
    profile: ImportProfile = ImportProfile()
    recurring: list[ImportRecurring] = []
    expenses: list[ImportExpenseRow] = []


class LlmSettingsOut(BaseModel):
    provider: str
    openrouter_http_referer: str | None = None
    server_key_configured: bool = False


class LlmSettingsPut(BaseModel):
    provider: Literal["openai", "openrouter", "gemini"]
    openrouter_http_referer: str | None = Field(default=None, max_length=512)
