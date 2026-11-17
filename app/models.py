from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Column, Numeric
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=new_id, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    full_name: str
    avatar_url: str | None = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class UserProfile(SQLModel, table=True):
    __tablename__ = "user_profiles"

    user_id: str = Field(foreign_key="users.id", primary_key=True, ondelete="CASCADE")
    credit_balance_minutes: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(10, 2), nullable=False),
    )
    default_fps: str = Field(default="25")
    default_enhance_mix: int = Field(default=80)
    default_silence_pad_ms: int = Field(default=150)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class CreditLedger(SQLModel, table=True):
    __tablename__ = "credit_ledger"

    id: str = Field(default_factory=new_id, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True, ondelete="CASCADE")
    job_id: str | None = Field(
        default=None, foreign_key="jobs.id", index=True, ondelete="SET NULL"
    )
    delta_minutes: Decimal = Field(
        sa_column=Column(Numeric(10, 2), nullable=False)
    )
    reason: str = Field(index=True)
    gpu_seconds_internal: float | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: str = Field(default_factory=new_id, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True, ondelete="CASCADE")
    parent_job_id: str | None = Field(default=None, index=True)
    effect: str | None = Field(default=None, index=True)
    status: str = Field(default="queued", index=True)
    source_filename: str
    source_r2_key: str
    source_artifact_id: str | None = Field(default=None, index=True)
    source_speaker: str | None = None
    runpod_job_id: str | None = Field(default=None, index=True)
    duration_seconds: float | None = None
    sample_rate: int | None = None
    fps: str = Field(default="25")
    pipeline_config: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    speaker_roles: dict[str, str] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    stage_states: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    error_code: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class JobArtifact(SQLModel, table=True):
    __tablename__ = "job_artifacts"

    id: str = Field(default_factory=new_id, primary_key=True)
    job_id: str = Field(foreign_key="jobs.id", index=True, ondelete="CASCADE")
    kind: str = Field(index=True)
    label: str
    format: str
    r2_key: str
    size_bytes: int = 0
    created_at: datetime = Field(default_factory=utcnow)
