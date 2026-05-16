"""geometry_jobs

Revision ID: b1e7c1f3a4f2
Revises: a0d6cb2919ee
Create Date: 2026-04-19 20:00:00.000000

Adds the ``geometry_jobs`` table used by the async-mode Geometry Service
(POST /api/v1/geometry/build -> 202 + job_id; GET /api/v1/geometry/jobs/
{job_id}).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1e7c1f3a4f2"
down_revision: Union[str, None] = "a0d6cb2919ee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "geometry_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("progress", sa.Float(), nullable=True),
        sa.Column("stage", sa.String(length=32), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("geometry_id", sa.String(length=36), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_geometry_jobs_cache_key",
        "geometry_jobs",
        ["cache_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_geometry_jobs_cache_key", table_name="geometry_jobs")
    op.drop_table("geometry_jobs")
