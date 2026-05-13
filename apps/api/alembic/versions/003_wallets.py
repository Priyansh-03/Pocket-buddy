"""add wallet1 wallet2 and active wallet

Revision ID: 003_wallets
Revises: 002_money_notes
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_wallets"
down_revision: Union[str, None] = "002_money_notes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("wallet_1_inr", sa.Numeric(14, 2), nullable=True))
    op.add_column("users", sa.Column("wallet_2_inr", sa.Numeric(14, 2), nullable=True))
    op.add_column("users", sa.Column("active_wallet_id", sa.Integer(), nullable=False, server_default="1"))
    op.execute("UPDATE users SET wallet_1_inr = estimated_cash_inr WHERE wallet_1_inr IS NULL")
    op.execute("UPDATE users SET active_wallet_id = 1 WHERE active_wallet_id IS NULL")


def downgrade() -> None:
    op.drop_column("users", "active_wallet_id")
    op.drop_column("users", "wallet_2_inr")
    op.drop_column("users", "wallet_1_inr")
