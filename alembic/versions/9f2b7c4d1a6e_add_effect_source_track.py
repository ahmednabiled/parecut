"""add effect source track

Revision ID: 9f2b7c4d1a6e
Revises: c41e28897718
Create Date: 2026-11-17
"""

import sqlalchemy as sa
from alembic import op

revision = "9f2b7c4d1a6e"
down_revision = "c41e28897718"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs", sa.Column("source_artifact_id", sa.String(), nullable=True)
    )
    op.add_column("jobs", sa.Column("source_speaker", sa.String(), nullable=True))
    op.create_index(
        "ix_jobs_source_artifact_id",
        "jobs",
        ["source_artifact_id"],
        unique=False,
    )
    op.execute(
        "UPDATE jobs SET source_artifact_id = ("
        "SELECT id FROM job_artifacts "
        "WHERE job_artifacts.r2_key = jobs.source_r2_key LIMIT 1"
        ") WHERE source_r2_key IS NOT NULL AND source_artifact_id IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_source_artifact_id", table_name="jobs")
    op.drop_column("jobs", "source_speaker")
    op.drop_column("jobs", "source_artifact_id")
