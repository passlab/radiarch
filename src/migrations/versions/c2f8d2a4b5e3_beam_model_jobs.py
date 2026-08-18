"""beam_model_jobs

Revision ID: c2f8d2a4b5e3
Revises: b1e7c1f3a4f2
Create Date: 2026-05-08 21:00:00.000000

Adds the ``beam_model_jobs`` table used by the async-mode Beam Model
Service (POST /api/v1/beam-model/build -> 202 + job_id; GET
/api/v1/beam-model/jobs/{job_id}). Mirrors the geometry_jobs table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c2f8d2a4b5e3"
down_revision: Union[str, None] = "b1e7c1f3a4f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "beam_model_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("progress", sa.Float(), nullable=True),
        sa.Column("stage", sa.String(length=32), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("beam_model_id", sa.String(length=36), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_beam_model_jobs_cache_key",
        "beam_model_jobs",
        ["cache_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_beam_model_jobs_cache_key", table_name="beam_model_jobs")
    op.drop_table("beam_model_jobs")
