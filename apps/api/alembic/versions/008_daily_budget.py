"""add daily_budget_inr to users

Revision ID: 008_daily_budget
Revises: 007_wallet_loans
Create Date: 2026-05-21
"""
from alembic import op
import sqlalchemy as sa

revision = "008_daily_budget"
down_revision = "007_wallet_loans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("daily_budget_inr", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "daily_budget_inr")
