"""plans.parameters: the workflow parameters of a plan (R15).

Revision ID: b7e2c4d9a1f0
Revises: a6d3e4f5b7c8
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e2c4d9a1f0"
down_revision: Union[str, None] = "a6d3e4f5b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("plans", sa.Column("parameters", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("plans", "parameters")
