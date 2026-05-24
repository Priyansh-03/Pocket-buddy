"""default llm_provider to openrouter for all users

Revision ID: 005_llm_default_openrouter
Revises: 004_wallets_upto_5
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_llm_default_openrouter"
down_revision: Union[str, None] = "004_wallets_upto_5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE users SET llm_provider = 'openrouter'"))
    op.alter_column(
        "users",
        "llm_provider",
        server_default=sa.text("'openrouter'"),
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "llm_provider",
        server_default=sa.text("'openai'"),
    )
