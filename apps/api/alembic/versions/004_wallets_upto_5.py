"""add wallet 3 to 5

Revision ID: 004_wallets_upto_5
Revises: 003_wallets
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_wallets_upto_5"
down_revision: Union[str, None] = "003_wallets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("wallet_3_inr", sa.Numeric(14, 2), nullable=True))
    op.add_column("users", sa.Column("wallet_4_inr", sa.Numeric(14, 2), nullable=True))
    op.add_column("users", sa.Column("wallet_5_inr", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "wallet_5_inr")
    op.drop_column("users", "wallet_4_inr")
    op.drop_column("users", "wallet_3_inr")
