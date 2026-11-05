from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, model_validator

SpeakerRole = Literal["presenter", "feeder", "cohost"]
StageName = Literal[
    "noise_reduction",
    "enhance",
    "separate_music",
    "separate_speakers",
    "transcribe",
    "rough_cut",
]


class PipelineConfig(BaseModel):
    noise_reduction: bool = True
    enhance: bool = True
    enhance_mix: float = Field(default=0.8, ge=0, le=1)
    separate_music: bool = True
    separate_speakers: bool = True
    transcribe: bool = True
    rough_cut: bool = True

    @model_validator(mode="after")
    def _rough_cut_requires_transcribe(self) -> "PipelineConfig":
        if self.rough_cut and not self.transcribe:
            raise ValueError("rough_cut requires transcribe")
        return self


class StageState(BaseModel):
    status: Literal["pending", "running", "completed", "skipped", "failed"] = "pending"
    percent: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None


class JobEvent(BaseModel):
    type: Literal[
        "snapshot",
        "job.status",
        "stage.started",
        "stage.progress",
        "stage.completed",
        "job.completed",
        "job.failed",
    ]
    job_id: str
    stage: str | None = None
    percent: int | None = None
    message: str | None = None
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TranscriptSegment(BaseModel):
    speaker: str
    start: float
    end: float
    text: str


class Transcript(BaseModel):
    speakers: list[str]
    segments: list[TranscriptSegment]


class CutRange(BaseModel):
    start: float
    end: float
    action: Literal["keep", "remove"]
    reason: str
    speaker: str | None = None
    text: str | None = None


class RoughCutMeta(BaseModel):
    source_filename: str
    duration_seconds: float
    fps: str
    sample_rate: int | None = None
    estimated_duration_seconds: float
