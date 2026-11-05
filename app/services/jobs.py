from decimal import Decimal

from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.models import Job, User, UserProfile
from app.schemas import JobCreate
from app.services.credits import add_ledger_entry, reserve_minutes
from app.services.stages import initial_stage_states
from app.storage import ObjectStorage


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
    if not await storage.exists(data.upload_key):
        raise UploadNotFound(data.upload_key)

    metadata = await storage.metadata(data.upload_key)
    duration = metadata.duration_seconds if metadata is not None else None
    minutes = reserve_minutes(duration)

    profile = await session.get(UserProfile, user.id)
    if profile is None:
        raise ProfileNotFound(user.id)

    available = Decimal(profile.credit_balance_minutes or 0)
    if available < minutes:
        raise InsufficientCredits(minutes, available)

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

    await add_ledger_entry(
        session,
        profile,
        delta=-minutes,
        reason="job_reserve",
        job_id=job.id,
    )
    await session.commit()

    try:
        await runner.spawn(job.id)
    except Exception:
        job.status = "failed"
        job.error_code = "spawn_failed"
        session.add(job)
        await add_ledger_entry(
            session,
            profile,
            delta=minutes,
            reason="job_refund",
            job_id=job.id,
        )
        await session.commit()

    return job
