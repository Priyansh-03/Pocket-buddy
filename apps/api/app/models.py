import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    salary_day: Mapped[int | None] = mapped_column(nullable=True)
    monthly_rent_inr: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    estimated_cash_inr: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    wallet_1_inr: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    wallet_2_inr: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    wallet_3_inr: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    wallet_4_inr: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    wallet_5_inr: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    daily_budget_inr: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    profit_inr: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    wallet_1_loan_inr: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    wallet_2_loan_inr: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    wallet_3_loan_inr: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    wallet_4_loan_inr: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    wallet_5_loan_inr: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    active_wallet_id: Mapped[int] = mapped_column(default=1, server_default=text("1"))
    money_profile_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    food_menu_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    remember_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_provider: Mapped[str] = mapped_column(
        String(32), default="openrouter", server_default=text("'openrouter'")
    )
    llm_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    openrouter_http_referer: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    expenses: Mapped[list["Expense"]] = relationship(back_populates="user")
    chat_sessions: Mapped[list["ChatSession"]] = relationship(back_populates="user")


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    amount_inr: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    category: Mapped[str] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="expenses")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="chat_sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(back_populates="session", order_by="ChatMessage.created_at")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extra_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["ChatSession"] = relationship(back_populates="messages")
