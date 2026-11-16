import asyncio
from decimal import Decimal
from typing import Protocol

from fastapi import Request
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.demo_data import demo_transcript
from app.events import EventBroker
from app.models import Job, JobArtifact, UserProfile, utcnow
from app.services.credits import add_ledger_entry, reserve_minutes
from app.services.roughcut import write_before_artifacts, write_cut_outputs
from app.services.stages import enabled_stages
from app.storage import ObjectStorage
from parecut_engine.schemas import JobEvent, PipelineConfig, SpeakerRole

AUDIO_ARTIFACTS = {
    "noise_reduction": [
        ("01_cleaned.wav", "cleaned_audio", "Demo — Cleaned Audio"),
    ],
    "enhance": [
        ("02_enhanced.wav", "enhanced_audio", "Demo — Enhanced Audio"),
    ],
    "separate_music": [
        ("stem_music.wav", "stem_music", "Demo — Music Stem"),
        ("stem_dialogue.wav", "stem_dialogue", "Demo — Dialogue Stem"),
    ],
    "separate_speakers": [
        ("speaker_01.wav", "stem_speaker", "Demo — Speaker 01"),
        ("speaker_02.wav", "stem_speaker", "Demo — Speaker 02"),
    ],
}

AUDIO_ARTIFACT_KINDS = {
    kind for entries in AUDIO_ARTIFACTS.values() for _, kind, _ in entries
}


class PipelineRunner(Protocol):
    async def spawn(self, job_id: str) -> None: ...


class NullPipelineRunner:
    async def spawn(self, job_id: str) -> None:
        return None


def get_runner(request: Request) -> PipelineRunner:
    return request.app.state.runner


class MockPipelineRunner:
    def __init__(
        self,
        sessionmaker: async_sessionmaker,
        storage: ObjectStorage,
        broker: EventBroker,
        settings: Settings,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._storage = storage
        self._broker = broker
        self._settings = settings
        self._tasks: set[asyncio.Task] = set()

    async def spawn(self, job_id: str) -> None:
        task = asyncio.create_task(self._run(job_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _job(self, session: AsyncSession, job_id: str) -> Job | None:
        return await session.get(Job, job_id)

    async def _set_status(self, job_id: str, status: str) -> None:
        async with self._sessionmaker() as session:
            job = await self._job(session, job_id)
            if job is None:
                return
            job.status = status
            if status == "running":
                job.started_at = utcnow()
            session.add(job)
            await session.commit()
        await self._broker.publish(
            job_id, JobEvent(type="job.status", job_id=job_id, message=status)
        )

    async def _update_stage(
        self,
        job_id: str,
        stage: str,
        *,
        status: str,
        percent: int,
        started: bool = False,
        completed: bool = False,
    ) -> None:
        async with self._sessionmaker() as session:
            job = await self._job(session, job_id)
            if job is None:
                return
            states = dict(job.stage_states or {})
            state = dict(
                states.get(stage)
                or {
                    "status": "pending",
                    "percent": 0,
                    "started_at": None,
                    "completed_at": None,
                }
            )
            now = utcnow().isoformat()
            state["status"] = status
            state["percent"] = percent
            if started:
                state["started_at"] = now
            if completed:
                state["completed_at"] = now
            states[stage] = state
            job.stage_states = states
            session.add(job)
            await session.commit()

        event_type = {
            "running": "stage.started" if started else "stage.progress",
            "completed": "stage.completed",
        }.get(status)
        if event_type:
            await self._broker.publish(
                job_id,
                JobEvent(
                    type=event_type,
                    job_id=job_id,
                    stage=stage,
                    percent=percent,
                ),
            )

    async def _write_audio_artifacts(
        self, session: AsyncSession, job: Job, stage: str
    ) -> None:
        for filename, kind, label in AUDIO_ARTIFACTS[stage]:
            key = f"jobs/{job.id}/{filename}"
            await self._storage.copy(job.source_r2_key, key)
            session.add(
                JobArtifact(
                    job_id=job.id,
                    kind=kind,
                    label=label,
                    format="wav",
                    r2_key=key,
                    size_bytes=await self._storage.size(key),
                )
            )
        await session.flush()

    async def _complete(self, job_id: str) -> None:
        async with self._sessionmaker() as session:
            job = await self._job(session, job_id)
            if job is None:
                return
            job.status = "completed"
            job.completed_at = utcnow()
            profile = await session.get(UserProfile, job.user_id)
            if profile is not None:
                await add_ledger_entry(
                    session,
                    profile,
                    delta=Decimal("0"),
                    reason="job_settle",
                    job_id=job.id,
                )
            session.add(job)
            await session.commit()
        await self._broker.publish(
            job_id, JobEvent(type="job.completed", job_id=job_id, message="completed")
        )

    async def _fail(self, job_id: str) -> None:
        async with self._sessionmaker() as session:
            job = await self._job(session, job_id)
            if job is None:
                return
            job.status = "failed"
            job.error_code = "mock_pipeline_failed"
            job.completed_at = utcnow()
            profile = await session.get(UserProfile, job.user_id)
            if profile is not None:
                await add_ledger_entry(
                    session,
                    profile,
                    delta=reserve_minutes(job.duration_seconds),
                    reason="job_refund",
                    job_id=job.id,
                )
            session.add(job)
            await session.commit()
        await self._broker.publish(
            job_id,
            JobEvent(
                type="job.failed",
                job_id=job_id,
                message="mock_pipeline_failed",
            ),
        )

    async def _run(self, job_id: str) -> None:
        try:
            await self._set_status(job_id, "running")
            async with self._sessionmaker() as session:
                job = await self._job(session, job_id)
                if job is None:
                    return
                config = PipelineConfig.model_validate(job.pipeline_config)
                transcript = demo_transcript(job.duration_seconds)

            stages = enabled_stages(config)
            roles: dict[str, SpeakerRole] = {}
            tick_delay = self._settings.mock_stage_delay_ms / 1000 / 4

            for stage in stages:
                await self._update_stage(
                    job_id, stage, status="running", percent=0, started=True
                )
                for percent in (0, 25, 50, 75, 100):
                    await asyncio.sleep(tick_delay)
                    if percent:
                        await self._update_stage(
                            job_id, stage, status="running", percent=percent
                        )

                async with self._sessionmaker() as session:
                    job = await self._job(session, job_id)
                    if job is None:
                        return
                    if stage in AUDIO_ARTIFACTS:
                        await self._write_audio_artifacts(session, job, stage)
                    elif stage == "transcribe":
                        roles = {
                            "SPEAKER_01": "presenter",
                            "SPEAKER_02": "presenter",
                        }
                        job.speaker_roles = dict(roles)
                        await write_before_artifacts(
                            session,
                            self._storage,
                            job,
                            transcript,
                            self._settings,
                        )
                    elif stage == "rough_cut":
                        await write_cut_outputs(
                            session,
                            self._storage,
                            job,
                            transcript,
                            roles,
                            self._settings,
                            demo=True,
                        )
                    session.add(job)
                    await session.commit()

                await self._update_stage(
                    job_id, stage, status="completed", percent=100, completed=True
                )

            await self._complete(job_id)
        except Exception:
            await self._fail(job_id)
