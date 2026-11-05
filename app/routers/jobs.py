import json
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.config import Settings
from app.db import get_session
from app.deps import get_current_user, get_settings_dep
from app.events import EventBroker, get_broker
from app.models import Job, JobArtifact, User
from app.schemas import JobCreate, JobRead, to_job_read
from app.services.jobs import (
    InsufficientCredits,
    UploadNotFound,
    create_job,
    load_job,
)
from app.services.pipeline import PipelineRunner, get_runner
from app.storage import ObjectStorage, get_storage

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", response_model=JobRead, status_code=status.HTTP_201_CREATED)
async def create(
    payload: JobCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    storage: ObjectStorage = Depends(get_storage),
    runner: PipelineRunner = Depends(get_runner),
    settings: Settings = Depends(get_settings_dep),
):
    try:
        job = await create_job(session, user, storage, runner, settings, payload)
    except UploadNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found"
        ) from exc
    except InsufficientCredits as exc:
        return JSONResponse(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            content={
                "detail": "Insufficient credits",
                "required_minutes": float(exc.required),
                "available_minutes": float(exc.available),
            },
        )
    return to_job_read(job)


@router.get("", response_model=list[JobRead])
async def list_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[JobRead]:
    jobs = (
        await session.exec(
            select(Job)
            .where(Job.user_id == user.id)
            .order_by(Job.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    if not jobs:
        return []

    artifacts = (
        await session.exec(
            select(JobArtifact)
            .where(JobArtifact.job_id.in_([job.id for job in jobs]))
            .order_by(JobArtifact.created_at)
        )
    ).all()
    grouped: dict[str, list[JobArtifact]] = defaultdict(list)
    for artifact in artifacts:
        grouped[artifact.job_id].append(artifact)

    return [to_job_read(job, grouped[job.id]) for job in jobs]


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    job_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> JobRead:
    job = await load_job(session, user, job_id)
    artifacts = (
        await session.exec(
            select(JobArtifact)
            .where(JobArtifact.job_id == job.id)
            .order_by(JobArtifact.created_at)
        )
    ).all()
    return to_job_read(job, artifacts)


@router.get("/{job_id}/events")
async def job_events(
    job_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    broker: EventBroker = Depends(get_broker),
):
    job = await load_job(session, user, job_id)
    artifacts = (
        await session.exec(select(JobArtifact).where(JobArtifact.job_id == job.id))
    ).all()
    snapshot = to_job_read(job, artifacts).model_dump(mode="json")
    subscription = broker.subscribe(job_id)

    async def event_stream():
        try:
            yield {"event": "snapshot", "data": json.dumps(snapshot)}
            if job.status in {"completed", "failed"}:
                return
            async for event in subscription:
                yield {"event": event.type, "data": event.model_dump_json()}
                if event.type in {"job.completed", "job.failed"}:
                    break
                if await request.is_disconnected():
                    break
        finally:
            close = getattr(subscription, "close", None)
            if close is not None:
                await close()

    return EventSourceResponse(event_stream(), ping=15)


@router.get("/{job_id}/artifacts/{artifact_id}/download")
async def download_artifact(
    job_id: str,
    artifact_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    storage: ObjectStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings_dep),
) -> RedirectResponse:
    job = await load_job(session, user, job_id)
    artifact = await session.get(JobArtifact, artifact_id)
    if artifact is None or artifact.job_id != job.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found"
        )

    url = storage.signed_download_url(
        artifact.r2_key,
        Path(artifact.r2_key).name,
        settings.download_url_ttl_seconds,
    )
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)
