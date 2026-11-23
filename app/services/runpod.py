import asyncio
import json
import logging
import time
from decimal import Decimal
from typing import Any, Protocol

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.events import EventBroker
from app.models import CreditLedger, Job, JobArtifact, UserProfile, utcnow
from app.services.credits import add_ledger_entry, reserve_minutes
from app.services.pipeline import AUDIO_ARTIFACTS
from app.services.stages import STAGE_ORDER, enabled_stages
from app.storage import ObjectStorage
from parecut_engine.schemas import JobEvent, PipelineConfig

TERMINAL_STATUSES = {"COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"}

logger = logging.getLogger(__name__)


class RunpodError(Exception):
    pass


class RunpodConfigurationError(RunpodError):
    pass


class RunpodClient(Protocol):
    async def run(self, endpoint_id: str, payload: dict) -> dict: ...

    async def status(self, endpoint_id: str, runpod_job_id: str) -> dict: ...


class HttpRunpodClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.runpod.ai/v2",
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise RunpodConfigurationError("Runpod API key is not configured")
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )

    async def run(self, endpoint_id: str, payload: dict) -> dict:
        response = await self._client.post(f"{endpoint_id}/run", json=payload)
        response.raise_for_status()
        return response.json()

    async def status(self, endpoint_id: str, runpod_job_id: str) -> dict:
        response = await self._client.get(
            f"{endpoint_id}/status/{runpod_job_id}"
        )
        response.raise_for_status()
        return response.json()

    async def aclose(self) -> None:
        await self._client.aclose()


def _audio_filename(filename: str, audio_format: str) -> str:
    return f"{filename.rsplit('.', 1)[0]}.{audio_format}"


def expected_artifacts(job_id: str, config: PipelineConfig) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    audio_format = config.audio_format
    for stage in enabled_stages(config):
        if stage == "separate_speakers":
            continue
        for filename, kind, label in AUDIO_ARTIFACTS.get(stage, []):
            artifacts.append(
                {
                    "key": f"jobs/{job_id}/{_audio_filename(filename, audio_format)}",
                    "kind": kind,
                    "label": label.removeprefix("Demo — "),
                    "format": audio_format,
                }
            )

    if config.separate_speakers:
        for index in range(1, 9):
            artifacts.append(
                {
                    "key": (
                        f"jobs/{job_id}/speaker_{index:02d}.{audio_format}"
                    ),
                    "kind": "stem_speaker",
                    "label": f"Speaker {index:02d}",
                    "format": audio_format,
                }
            )

    if config.transcribe:
        for fmt, filename in (
            ("json", "transcript_raw.json"),
            ("md", "transcript_before.md"),
            ("srt", "transcript_before.srt"),
            ("vtt", "transcript_before.vtt"),
        ):
            artifacts.append(
                {
                    "key": f"jobs/{job_id}/{filename}",
                    "kind": "transcript_before",
                    "label": "Transcript (Before Cut)",
                    "format": fmt,
                }
            )

    if config.rough_cut:
        for fmt in ("md", "srt", "vtt", "json"):
            artifacts.append(
                {
                    "key": f"jobs/{job_id}/transcript_after.{fmt}",
                    "kind": "transcript_after",
                    "label": "Transcript (After Cut)",
                    "format": fmt,
                }
            )
        artifacts.append(
            {
                "key": f"jobs/{job_id}/ROUGH-CUT.md",
                "kind": "rough_cut_md",
                "label": "ROUGH-CUT.md",
                "format": "md",
            }
        )

    return artifacts


def _progress_updates(output: Any) -> list[tuple[str, int]]:
    if isinstance(output, str):
        try:
            output = json.loads(output)
        except json.JSONDecodeError:
            return []
    if not isinstance(output, dict):
        return []

    if "stage" in output and "percent" in output:
        try:
            stage = str(output["stage"])
            percent = int(output["percent"])
        except (TypeError, ValueError):
            return []
        return [(stage, percent)] if stage in STAGE_ORDER else []

    stages = output.get("stages")
    if not isinstance(stages, dict):
        return []
    updates: list[tuple[str, int]] = []
    for stage, state in stages.items():
        if stage not in STAGE_ORDER or not isinstance(state, dict):
            continue
        try:
            updates.append((stage, int(state.get("percent", 100))))
        except (TypeError, ValueError):
            continue
    return updates


class RunpodPipelineRunner:
    def __init__(
        self,
        sessionmaker: async_sessionmaker,
        storage: ObjectStorage,
        broker: EventBroker,
        settings: Settings,
        client: RunpodClient,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._storage = storage
        self._broker = broker
        self._settings = settings
        self._client = client
        self._tasks: set[asyncio.Task] = set()

    async def spawn(self, job_id: str) -> None:
        task = asyncio.create_task(self.run(job_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def spawn_resume(self, job_id: str) -> None:
        task = asyncio.create_task(self.resume(job_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def resume(self, job_id: str) -> None:
        async with self._sessionmaker() as session:
            job = await session.get(Job, job_id)
            if (
                job is None
                or job.status in {"completed", "failed"}
                or not job.runpod_job_id
            ):
                return
            endpoint_id = self._settings.runpod_audio_endpoint_id
            if not endpoint_id:
                await self._fail(session, job, "runpod_not_configured")
                return
            runpod_job_id = job.runpod_job_id
            config = PipelineConfig.model_validate(job.pipeline_config)

        logger.info("resuming runpod polling for job %s (%s)", job_id, runpod_job_id)
        try:
            await self._poll(job_id, endpoint_id, runpod_job_id, config)
        except Exception:
            logger.exception("resumed runpod job %s failed", job_id)
            async with self._sessionmaker() as session:
                job = await session.get(Job, job_id)
                if job is not None:
                    await self._fail(session, job, "runpod_failed")

    def _absolute(self, url: str) -> str:
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return f"{self._settings.public_base_url.rstrip('/')}/{url.lstrip('/')}"

    def _payload(self, job: Job, config: PipelineConfig) -> dict:
        ttl = self._settings.runpod_url_ttl_seconds
        expected = expected_artifacts(job.id, config)
        outputs = {
            artifact["key"]: self._absolute(
                self._storage.signed_direct_upload_url(artifact["key"], ttl)
            )
            for artifact in expected
        }
        return {
            "input": {
                "job_id": job.id,
                "source_url": self._absolute(
                    self._storage.signed_download_url(
                        job.source_r2_key, job.source_filename, ttl
                    )
                ),
                "source_filename": job.source_filename,
                "source_speaker": job.source_speaker,
                "duration_seconds": job.duration_seconds,
                "sample_rate": job.sample_rate,
                "fps": job.fps,
                "pipeline": config.model_dump(),
                "outputs": outputs,
                "expected_artifacts": expected,
            }
        }

    async def run(self, job_id: str) -> None:
        async with self._sessionmaker() as session:
            job = await session.get(Job, job_id)
            if job is None or job.status in {"completed", "failed"}:
                return
            endpoint_id = self._settings.runpod_audio_endpoint_id
            if not endpoint_id:
                await self._fail(session, job, "runpod_not_configured")
                return
            config = PipelineConfig.model_validate(job.pipeline_config)
            payload = self._payload(job, config)

        try:
            response = await self._client.run(endpoint_id, payload)
            runpod_job_id = response.get("id")
            if not runpod_job_id:
                raise RunpodError("Runpod did not return a job id")
            async with self._sessionmaker() as session:
                job = await session.get(Job, job_id)
                if job is None:
                    return
                job.runpod_job_id = str(runpod_job_id)
                session.add(job)
                await session.commit()
            await self._poll(job_id, endpoint_id, str(runpod_job_id), config)
        except Exception:
            logger.exception("runpod job %s failed", job_id)
            async with self._sessionmaker() as session:
                job = await session.get(Job, job_id)
                if job is not None:
                    await self._fail(session, job, "runpod_failed")

    async def _poll(
        self,
        job_id: str,
        endpoint_id: str,
        runpod_job_id: str,
        config: PipelineConfig,
    ) -> None:
        deadline = time.monotonic() + self._settings.runpod_job_timeout_seconds
        consecutive_errors = 0
        max_transient_errors = 5
        while True:
            try:
                status = await self._client.status(endpoint_id, runpod_job_id)
                consecutive_errors = 0
            except httpx.HTTPError as exc:
                is_transient = not isinstance(exc, httpx.HTTPStatusError) or (
                    exc.response.status_code >= 500
                    or exc.response.status_code == 429
                )
                consecutive_errors += 1
                if not is_transient or consecutive_errors > max_transient_errors:
                    raise
                logger.warning(
                    "transient runpod poll error (%d/%d) for job %s: %s",
                    consecutive_errors,
                    max_transient_errors,
                    job_id,
                    exc,
                )
                await asyncio.sleep(self._settings.runpod_poll_interval_seconds)
                continue

            state = str(status.get("status") or "")
            output = status.get("output")

            if state == "IN_QUEUE":
                await self._set_status(job_id, "queued")
            elif state == "IN_PROGRESS":
                await self._set_status(job_id, "running")
                await self._apply_progress(job_id, output)
            elif state == "COMPLETED":
                await self._complete(job_id, config, output or {})
                return
            elif state in TERMINAL_STATUSES:
                async with self._sessionmaker() as session:
                    job = await session.get(Job, job_id)
                    if job is not None:
                        await self._fail(session, job, "runpod_failed")
                return

            if time.monotonic() >= deadline:
                async with self._sessionmaker() as session:
                    job = await session.get(Job, job_id)
                    if job is not None:
                        await self._fail(session, job, "runpod_timeout")
                return

            await asyncio.sleep(self._settings.runpod_poll_interval_seconds)

    async def _set_status(self, job_id: str, status: str) -> None:
        changed = False
        async with self._sessionmaker() as session:
            job = await session.get(Job, job_id)
            if job is None or job.status in {"completed", "failed"}:
                return
            if job.status != status:
                job.status = status
                if status == "running" and job.started_at is None:
                    job.started_at = utcnow()
                session.add(job)
                await session.commit()
                changed = True
        if changed:
            await self._broker.publish(
                job_id, JobEvent(type="job.status", job_id=job_id, message=status)
            )

    async def _apply_progress(self, job_id: str, output: Any) -> None:
        updates = _progress_updates(output)
        if not updates:
            return

        events: list[JobEvent] = []
        async with self._sessionmaker() as session:
            job = await session.get(Job, job_id)
            if job is None or job.status in {"completed", "failed"}:
                return
            states = dict(job.stage_states or {})
            for stage, percent in updates:
                percent = max(0, min(100, percent))
                state = dict(states.get(stage) or {})
                state["percent"] = percent
                state["status"] = "completed" if percent >= 100 else "running"
                now = utcnow().isoformat()
                if state["status"] == "running" and not state.get("started_at"):
                    state["started_at"] = now
                if state["status"] == "completed":
                    state["completed_at"] = now
                states[stage] = state
                events.append(
                    JobEvent(
                        type=(
                            "stage.completed"
                            if state["status"] == "completed"
                            else "stage.progress"
                        ),
                        job_id=job_id,
                        stage=stage,
                        percent=percent,
                    )
                )
            job.stage_states = states
            session.add(job)
            await session.commit()

        for event in events:
            await self._broker.publish(job_id, event)

    async def _complete(
        self, job_id: str, config: PipelineConfig, output: dict
    ) -> None:
        async with self._sessionmaker() as session:
            job = await session.get(Job, job_id)
            if job is None or job.status in {"completed", "failed"}:
                return

            diarization = output.get("diarization") if isinstance(output, dict) else None
            if diarization is not None:
                logger.info("worker diarization: %s", diarization)

            valid_stage_statuses = {"pending", "running", "completed", "skipped", "failed"}
            states = dict(job.stage_states or {})
            now = utcnow().isoformat()
            final_stages = output.get("stages") if isinstance(output, dict) else None
            if isinstance(final_stages, dict):
                for stage, raw in final_stages.items():
                    if stage not in STAGE_ORDER or not isinstance(raw, dict):
                        continue
                    state = dict(states.get(stage) or {})
                    raw_status = raw.get("status", "completed")
                    safe_status = (
                        raw_status if raw_status in valid_stage_statuses else "completed"
                    )
                    try:
                        safe_percent = max(0, min(100, int(raw.get("percent", 100))))
                    except (TypeError, ValueError):
                        safe_percent = 100
                    state.update(
                        {
                            "status": safe_status,
                            "percent": safe_percent,
                            "started_at": raw.get("started_at") or state.get("started_at") or now,
                            "completed_at": raw.get("completed_at") or now,
                        }
                    )
                    states[stage] = state
            else:
                for stage in enabled_stages(config):
                    state = dict(states.get(stage) or {})
                    state.update(
                        {
                            "status": "completed",
                            "percent": 100,
                            "started_at": state.get("started_at") or now,
                            "completed_at": now,
                        }
                    )
                    states[stage] = state
            job.stage_states = states

            valid_roles = {"presenter", "feeder", "cohost"}
            roles = output.get("speaker_roles") if isinstance(output, dict) else None
            if isinstance(roles, dict):
                job.speaker_roles = {
                    str(key): (value if value in valid_roles else "presenter")
                    for key, value in roles.items()
                }

            artifacts = output.get("artifacts") if isinstance(output, dict) else None
            if isinstance(artifacts, list):
                for raw in artifacts:
                    if not isinstance(raw, dict):
                        continue
                    key = raw.get("key")
                    kind = raw.get("kind")
                    label = raw.get("label")
                    fmt = raw.get("format")
                    if not all(isinstance(value, str) and value for value in (key, kind, label, fmt)):
                        continue
                    existing = (
                        await session.exec(
                            select(JobArtifact).where(
                                JobArtifact.job_id == job.id,
                                JobArtifact.r2_key == key,
                            )
                        )
                    ).first()
                    if existing is None:
                        session.add(
                            JobArtifact(
                                job_id=job.id,
                                kind=kind,
                                label=label,
                                format=fmt,
                                r2_key=key,
                                size_bytes=int(raw.get("size_bytes") or 0),
                            )
                        )
                    else:
                        existing.kind = kind
                        existing.label = label
                        existing.format = fmt
                        existing.size_bytes = int(raw.get("size_bytes") or 0)
                        session.add(existing)

            job.status = "completed"
            job.completed_at = utcnow()
            session.add(job)

            profile = await session.get(UserProfile, job.user_id)
            if profile is not None:
                settle = (
                    await session.exec(
                        select(CreditLedger).where(
                            CreditLedger.job_id == job.id,
                            CreditLedger.reason == "job_settle",
                        )
                    )
                ).first()
                if settle is None:
                    await add_ledger_entry(
                        session,
                        profile,
                        delta=Decimal("0"),
                        reason="job_settle",
                        job_id=job.id,
                    )
            await session.commit()

        await self._broker.publish(
            job_id, JobEvent(type="job.completed", job_id=job_id, message="completed")
        )

    async def _fail(self, session: AsyncSession, job: Job, error_code: str) -> None:
        if job.status in {"completed", "failed"}:
            return
        job.status = "failed"
        job.error_code = error_code
        job.completed_at = utcnow()
        session.add(job)

        profile = await session.get(UserProfile, job.user_id)
        if profile is not None:
            refund = (
                await session.exec(
                    select(CreditLedger).where(
                        CreditLedger.job_id == job.id,
                        CreditLedger.reason == "job_refund",
                    )
                )
            ).first()
            if refund is None:
                await add_ledger_entry(
                    session,
                    profile,
                    delta=reserve_minutes(job.duration_seconds),
                    reason="job_refund",
                    job_id=job.id,
                )
        await session.commit()
        await self._broker.publish(
            job.id, JobEvent(type="job.failed", job_id=job.id, message=error_code)
        )
