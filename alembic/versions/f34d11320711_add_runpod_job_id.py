"""add runpod job id

Revision ID: f34d11320711
Revises: d926df59bd52
Create Date: 2026-11-08 21:32:40.710530

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'f34d11320711'
down_revision: Union[str, Sequence[str], None] = 'd926df59bd52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "jobs",
        sa.Column("runpod_job_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.create_index(
        op.f("ix_jobs_runpod_job_id"), "jobs", ["runpod_job_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_jobs_runpod_job_id"), table_name="jobs")
    op.drop_column("jobs", "runpod_job_id")
