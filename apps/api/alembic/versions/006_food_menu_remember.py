"""user food menu + remember text for assistant context

Revision ID: 006_food_menu_remember
Revises: 005_llm_default_openrouter
Create Date: 2026-05-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_food_menu_remember"
down_revision: Union[str, None] = "005_llm_default_openrouter"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("food_menu_text", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("remember_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "remember_text")
    op.drop_column("users", "food_menu_text")
