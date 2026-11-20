import re
from decimal import Decimal
from pathlib import Path

from fastapi import HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.models import Job, JobArtifact, User, UserProfile, utcnow
from app.schemas import EffectCreate, EffectName, JobCreate
from app.services.credits import add_ledger_entry, reserve_credits, reserve_minutes
from app.services.pipeline import AUDIO_ARTIFACT_KINDS
from app.services.stages import initial_stage_states
from app.storage import ObjectStorage
from parecut_engine.schemas import (
    ArabicDialect,
    AudioFormat,
    PipelineConfig,
    StudioChain,
    TranscriptionLanguage,
)

DRAFT_CONFIG = PipelineConfig(
    noise_reduction=False,
    enhance=False,
    separate_music=False,
    separate_speakers=False,
    transcribe=False,
    rough_cut=False,
)


def effect_config(
    effect: EffectName,
    enhance_mix: float | None = None,
    studio: StudioChain | None = None,
    languages: list[TranscriptionLanguage] | None = None,
    arabic_dialect: ArabicDialect | None = None,
    audio_format: AudioFormat | None = None,
) -> PipelineConfig:
    values = DRAFT_CONFIG.model_dump()
    if audio_format is not None:
        values["audio_format"] = audio_format
    if effect == "noise_reduction":
        values["noise_reduction"] = True
    elif effect == "enhance":
        values["enhance"] = True
        values["enhance_mix"] = enhance_mix if enhance_mix is not None else 0.8
        if studio is not None:
            values["studio_chain"] = studio.model_dump()
    elif effect == "separate_music":
        values["separate_music"] = True
    elif effect == "separate_speakers":
        values["separate_speakers"] = True
    elif effect == "transcribe":
        values["transcribe"] = True
        values["rough_cut"] = True
        if languages:
            values["transcription_languages"] = languages
        if arabic_dialect is not None:
            values["arabic_dialect"] = arabic_dialect
    return PipelineConfig.model_validate(values)


async def load_job(session: AsyncSession, user: User, job_id: str) -> Job:
    job = await session.get(Job, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


class UploadNotFound(Exception):
    pass


class ProfileNotFound(Exception):
    pass


class InsufficientCredits(Exception):
    def __init__(self, required: Decimal, available: Decimal) -> None:
        self.required = required
        self.available = available
        super().__init__("Insufficient credits")


async def create_job(
    session: AsyncSession,
    user: User,
    storage: ObjectStorage,
    runner,
    settings: Settings,
    data: JobCreate,
) -> Job:
    expected_prefix = f"uploads/{user.id}/"
    key_path = Path(data.upload_key)
    if (
        not data.upload_key.startswith(expected_prefix)
        or key_path.is_absolute()
        or ".." in key_path.parts
        or not await storage.exists(data.upload_key)
    ):
        raise UploadNotFound(data.upload_key)

    metadata = await storage.metadata(data.upload_key)
    duration = metadata.duration_seconds if metadata is not None else None

    if data.draft:
        now = utcnow()
        job = Job(
            user_id=user.id,
            status="completed",
            source_filename=data.source_filename,
            source_r2_key=data.upload_key,
            duration_seconds=duration,
            sample_rate=metadata.sample_rate if metadata is not None else None,
            fps=data.fps,
            pipeline_config=DRAFT_CONFIG.model_dump(),
            speaker_roles={},
            stage_states={
                stage: state.model_dump(mode="json")
                for stage, state in initial_stage_states(DRAFT_CONFIG).items()
            },
            started_at=now,
            completed_at=now,
        )
        session.add(job)
        await session.commit()
        return job

    minutes = reserve_minutes(duration)

    job = Job(
        user_id=user.id,
        status="queued",
        source_filename=data.source_filename,
        source_r2_key=data.upload_key,
        duration_seconds=duration,
        sample_rate=metadata.sample_rate if metadata is not None else None,
        fps=data.fps,
        pipeline_config=data.pipeline.model_dump(),
        speaker_roles={},
        stage_states={
            stage: state.model_dump(mode="json")
            for stage, state in initial_stage_states(data.pipeline).items()
        },
    )
    session.add(job)
    await session.flush()

    reserved, available = await reserve_credits(
        session, user.id, minutes=minutes, job_id=job.id
    )
    if not reserved:
        await session.rollback()
        if available is None:
            raise ProfileNotFound(user.id)
        raise InsufficientCredits(minutes, available)

    await session.commit()

    try:
        await runner.spawn(job.id)
    except Exception:
        job.status = "failed"
        job.error_code = "spawn_failed"
        job.completed_at = utcnow()
        session.add(job)
        profile = await session.get(UserProfile, user.id)
        if profile is not None:
            await add_ledger_entry(
                session,
                profile,
                delta=minutes,
                reason="job_refund",
                job_id=job.id,
            )
        await session.commit()

    return job


async def create_effect_run(
    session: AsyncSession,
    user: User,
    parent: Job,
    runner,
    data: EffectCreate,
) -> Job:
    minutes = reserve_minutes(parent.duration_seconds)

    config = effect_config(
        data.effect,
        data.enhance_mix,
        data.studio,
        data.languages,
        data.arabic_dialect,
        data.audio_format,
    )

    source_key = parent.source_r2_key
    source_filename = parent.source_filename
    source_speaker: str | None = None
    if data.source_artifact_id:
        artifact = await session.get(JobArtifact, data.source_artifact_id)
        owner = (
            await session.get(Job, artifact.job_id) if artifact is not None else None
        )
        if (
            artifact is None
            or owner is None
            or (owner.id != parent.id and owner.parent_job_id != parent.id)
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Source track not found",
            )
        if owner.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Source track is not ready",
            )
        if artifact.kind not in AUDIO_ARTIFACT_KINDS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Source track is not an audio track",
            )
        source_key = artifact.r2_key
        source_filename = Path(artifact.r2_key).name
        if artifact.kind == "stem_speaker":
            match = re.search(
                r"speaker[\s_-]*0*(\d+)", artifact.label or "", re.IGNORECASE
            )
            if match is not None:
                source_speaker = f"SPEAKER_{int(match.group(1)):02d}"

    job = Job(
        user_id=user.id,
        parent_job_id=parent.id,
        effect=data.effect,
        status="queued",
        source_filename=source_filename,
        source_r2_key=source_key,
        source_artifact_id=data.source_artifact_id,
        source_speaker=source_speaker,
        duration_seconds=parent.duration_seconds,
        sample_rate=parent.sample_rate,
        fps=parent.fps,
        pipeline_config=config.model_dump(),
        speaker_roles={},
        stage_states={
            stage: state.model_dump(mode="json")
            for stage, state in initial_stage_states(config).items()
        },
    )
    session.add(job)
    await session.flush()

    reserved, available = await reserve_credits(
        session, user.id, minutes=minutes, job_id=job.id
    )
    if not reserved:
        await session.rollback()
        if available is None:
            raise ProfileNotFound(user.id)
        raise InsufficientCredits(minutes, available)

    await session.commit()

    try:
        await runner.spawn(job.id)
    except Exception:
        job.status = "failed"
        job.error_code = "spawn_failed"
        job.completed_at = utcnow()
        session.add(job)
        profile = await session.get(UserProfile, user.id)
        if profile is not None:
            await add_ledger_entry(
                session,
                profile,
                delta=minutes,
                reason="job_refund",
                job_id=job.id,
            )
        await session.commit()

    return job
