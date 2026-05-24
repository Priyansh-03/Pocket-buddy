"""add persistent profit_inr balance to users

Revision ID: 009_profit_balance
Revises: 008_daily_budget
Create Date: 2026-05-21
"""
from alembic import op
import sqlalchemy as sa

revision = "009_profit_balance"
down_revision = "008_daily_budget"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("profit_inr", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "profit_inr")
