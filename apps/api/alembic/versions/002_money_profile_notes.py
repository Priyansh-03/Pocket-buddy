"""add money_profile_notes to users

Revision ID: 002_money_notes
Revises: 001_initial
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_money_notes"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("money_profile_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "money_profile_notes")
