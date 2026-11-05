import io
import math
import wave
from array import array
from decimal import Decimal

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.demo_data import demo_transcript
from app.models import CreditLedger, Job, JobArtifact, User, UserProfile, utcnow
from app.security import hash_password
from app.services.credits import add_ledger_entry, reserve_minutes
from app.services.pipeline import AUDIO_ARTIFACTS
from app.services.roughcut import write_before_artifacts, write_cut_outputs
from app.services.stages import STAGE_ORDER
from app.storage import ObjectStorage
from parecut_engine.schemas import PipelineConfig

DEMO_EMAIL = "demo@parecut.app"
DEMO_PASSWORD = "parecut-demo"
DEMO_JOB_ID = "00000000-0000-4000-8000-000000000001"
DEMO_SOURCE_KEY = "demo/demo_interview.wav"


def _demo_wav(seconds: float = 20.0, rate: int = 48000) -> bytes:
    frames = int(seconds * rate)
    samples = array(
        "h",
        (int(300 * math.sin(2 * math.pi * 220 * i / rate)) for i in range(frames)),
    )
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(samples.tobytes())
    return buffer.getvalue()


async def seed_demo(
    sessionmaker: async_sessionmaker,
    storage: ObjectStorage,
    settings: Settings,
) -> None:
    async with sessionmaker() as session:
        existing = (
            await session.exec(select(User).where(User.email == DEMO_EMAIL))
        ).first()
        if existing is not None:
            return

        user = User(
            email=DEMO_EMAIL,
            hashed_password=hash_password(DEMO_PASSWORD),
            full_name="Parecut Demo",
        )
        session.add(user)
        await session.flush()

        profile = UserProfile(
            user_id=user.id, credit_balance_minutes=Decimal("0")
        )
        session.add(profile)
        await session.flush()
        await add_ledger_entry(
            session,
            profile,
            delta=settings.signup_bonus_minutes,
            reason="signup_bonus",
        )

        now = utcnow()
        job = Job(
            id=DEMO_JOB_ID,
            user_id=user.id,
            status="completed",
            source_filename="demo_interview.wav",
            source_r2_key=DEMO_SOURCE_KEY,
            duration_seconds=20.0,
            sample_rate=48000,
            fps="25",
            pipeline_config=PipelineConfig().model_dump(),
            speaker_roles={
                "SPEAKER_01": "presenter",
                "SPEAKER_02": "presenter",
            },
            stage_states={
                stage: {
                    "status": "completed",
                    "percent": 100,
                    "started_at": now.isoformat(),
                    "completed_at": now.isoformat(),
                }
                for stage in STAGE_ORDER
            },
            created_at=now,
            started_at=now,
            completed_at=now,
        )
        session.add(job)
        await session.flush()

        await storage.put(DEMO_SOURCE_KEY, _demo_wav(), "audio/wav")
        for stage in STAGE_ORDER:
            for filename, kind, label in AUDIO_ARTIFACTS.get(stage, []):
                key = f"jobs/{job.id}/{filename}"
                await storage.copy(DEMO_SOURCE_KEY, key)
                session.add(
                    JobArtifact(
                        job_id=job.id,
                        kind=kind,
                        label=label,
                        format="wav",
                        r2_key=key,
                        size_bytes=await storage.size(key),
                    )
                )

        transcript = demo_transcript(job.duration_seconds)
        await write_before_artifacts(session, storage, job, transcript, settings)
        await write_cut_outputs(
            session,
            storage,
            job,
            transcript,
            job.speaker_roles,
            settings,
        )
        await session.commit()


async def reconcile_orphan_jobs(
    sessionmaker: async_sessionmaker,
    settings: Settings,
) -> None:
    async with sessionmaker() as session:
        orphaned = (
            await session.exec(
                select(Job).where(Job.status.in_(["queued", "running"]))
            )
        ).all()
        for job in orphaned:
            existing_refund = (
                await session.exec(
                    select(CreditLedger).where(
                        CreditLedger.job_id == job.id,
                        CreditLedger.reason == "job_refund",
                    )
                )
            ).first()
            job.status = "failed"
            job.error_code = "server_restart"
            job.completed_at = utcnow()
            session.add(job)

            if existing_refund is None:
                profile = await session.get(UserProfile, job.user_id)
                if profile is not None:
                    await add_ledger_entry(
                        session,
                        profile,
                        delta=reserve_minutes(job.duration_seconds),
                        reason="job_refund",
                        job_id=job.id,
                    )

        await session.commit()
