from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from parecut_engine.schemas import PipelineConfig, SpeakerRole, StageState

FPS = Literal["24", "25", "29.97", "30", "60"]


class UserRead(BaseModel):
    id: str
    email: str
    full_name: str
    avatar_url: str | None = None
    created_at: datetime


class ProfileRead(BaseModel):
    credit_balance_minutes: float
    default_fps: str
    default_enhance_mix: int
    default_silence_pad_ms: int


class SessionUser(BaseModel):
    user: UserRead
    profile: ProfileRead


class ArtifactRead(BaseModel):
    id: str
    kind: str
    label: str
    format: str
    size_bytes: int
    download_url: str
    content_url: str


class JobRead(BaseModel):
    id: str
    parent_job_id: str | None = None
    effect: str | None = None
    status: str
    source_filename: str
    source_url: str
    duration_seconds: float | None = None
    sample_rate: int | None = None
    fps: str
    pipeline_config: PipelineConfig
    speaker_roles: dict[str, SpeakerRole]
    stage_states: dict[str, StageState]
    error_code: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    artifacts: list[ArtifactRead] = Field(default_factory=list)


class LedgerRead(BaseModel):
    id: str
    job_id: str | None = None
    delta_minutes: float
    reason: str
    created_at: datetime


class ProfileResponse(BaseModel):
    user: UserRead
    profile: ProfileRead
    jobs: list[JobRead]
    ledger: list[LedgerRead]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


EffectName = Literal[
    "noise_reduction",
    "enhance",
    "separate_music",
    "separate_speakers",
    "transcribe",
]


class JobCreate(BaseModel):
    upload_key: str
    source_filename: str = Field(min_length=1)
    fps: FPS = "25"
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    draft: bool = False


class EffectCreate(BaseModel):
    effect: EffectName
    enhance_mix: float | None = Field(default=None, ge=0, le=1)


class SpeakerRolesUpdate(BaseModel):
    roles: dict[str, SpeakerRole]


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1)
    default_fps: str | None = Field(default=None, pattern=r"^(24|25|29\.97|30|60)$")
    default_enhance_mix: int | None = Field(default=None, ge=0, le=100)
    default_silence_pad_ms: int | None = Field(default=None, ge=0, le=2000)


def to_user_read(user) -> UserRead:
    return UserRead(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
    )


def to_profile_read(profile) -> ProfileRead:
    return ProfileRead(
        credit_balance_minutes=float(profile.credit_balance_minutes),
        default_fps=profile.default_fps,
        default_enhance_mix=profile.default_enhance_mix,
        default_silence_pad_ms=profile.default_silence_pad_ms,
    )


def to_job_read(job, artifacts=()) -> JobRead:
    return JobRead(
        id=job.id,
        parent_job_id=job.parent_job_id,
        effect=job.effect,
        status=job.status,
        source_filename=job.source_filename,
        source_url=f"/api/jobs/{job.id}/source",
        duration_seconds=job.duration_seconds,
        sample_rate=job.sample_rate,
        fps=job.fps,
        pipeline_config=PipelineConfig.model_validate(job.pipeline_config),
        speaker_roles=job.speaker_roles,
        stage_states=job.stage_states,
        error_code=job.error_code,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        artifacts=[
            ArtifactRead(
                id=artifact.id,
                kind=artifact.kind,
                label=artifact.label,
                format=artifact.format,
                size_bytes=artifact.size_bytes,
                download_url=f"/api/jobs/{job.id}/artifacts/{artifact.id}/download",
                content_url=f"/api/jobs/{job.id}/artifacts/{artifact.id}/content",
            )
            for artifact in artifacts
        ],
    )
