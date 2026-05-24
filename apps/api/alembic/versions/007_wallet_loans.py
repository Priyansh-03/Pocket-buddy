"""add wallet loan tracking fields

Revision ID: 007
Revises: 006
Create Date: 2026-05-21
"""
from alembic import op
import sqlalchemy as sa

revision = "007_wallet_loans"
down_revision = "006_food_menu_remember"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for n in range(1, 6):
        op.add_column("users", sa.Column(f"wallet_{n}_loan_inr", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    for n in range(1, 6):
        op.drop_column("users", f"wallet_{n}_loan_inr")
