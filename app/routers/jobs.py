import array
import asyncio
import hashlib
import json
import mimetypes
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.config import Settings
from app.db import get_session
from app.deps import get_current_user, get_current_user_id, get_settings_dep
from app.events import EventBroker, get_broker
from app.models import Job, JobArtifact, User
from app.ratelimit import rate_limit
from app.schemas import (
    EffectCreate,
    JobCreate,
    JobRead,
    JobUpdate,
    SpeakerRolesUpdate,
    to_job_read,
)
from app.services.jobs import (
    InsufficientCredits,
    ProfileNotFound,
    UploadNotFound,
    create_effect_run,
    create_job,
    load_job,
)
from app.services.pipeline import PipelineRunner, get_runner
from app.services.roughcut import regenerate_cut_outputs
from app.storage import ObjectStorage, get_storage

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


async def _load_job_for_user(
    session: AsyncSession, user_id: str, job_id: str
) -> Job:
    job = await session.get(Job, job_id)
    if job is None or job.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )
    return job

TEXT_MEDIA_TYPES = {
    "md": "text/markdown",
    "srt": "application/x-subrip",
    "vtt": "text/vtt",
    "json": "application/json",
}

CONTENT_MEDIA_TYPES = {
    **TEXT_MEDIA_TYPES,
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
}


def insufficient_credits(exc: InsufficientCredits) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        content={
            "detail": "Insufficient credits",
            "required_minutes": float(exc.required),
            "available_minutes": float(exc.available),
        },
    )


def range_bounds(value: str | None, total: int) -> tuple[int, int] | None:
    if not value:
        return None
    header = value.strip()
    if not header.startswith("bytes="):
        return None
    spec = header.removeprefix("bytes=").split(",", 1)[0].strip()
    if "-" not in spec:
        return None

    start_text, end_text = (part.strip() for part in spec.split("-", 1))
    try:
        if not start_text:
            if not end_text:
                return None
            suffix = int(end_text)
            if suffix <= 0:
                return None
            start = max(0, total - suffix)
            end = total - 1
        else:
            start = int(start_text)
            end = int(end_text) if end_text else total - 1
    except ValueError:
        return None

    if start < 0 or start >= total:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{total}"},
        )
    end = min(end, total - 1)
    if end < start:
        return None
    return start, end


async def media_response(
    request: Request,
    storage: ObjectStorage,
    key: str,
    media_type: str,
    filename: str,
) -> Response:
    if not await storage.exists(key):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found"
        )
    total = await storage.size(key)
    bounds = range_bounds(request.headers.get("range"), total)
    safe_filename = filename.replace('"', "").replace("\r", "").replace("\n", "")
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f'inline; filename="{safe_filename}"',
    }
    if total <= 0:
        return Response(content=b"", media_type=media_type, headers=headers)
    if bounds is None:
        headers["Content-Length"] = str(total)
        return StreamingResponse(
            storage.iter_range(key, 0, total - 1),
            media_type=media_type,
            headers=headers,
        )

    start, end = bounds
    headers["Content-Range"] = f"bytes {start}-{end}/{total}"
    headers["Content-Length"] = str(end - start + 1)
    return StreamingResponse(
        storage.iter_range(key, start, end),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=media_type,
        headers=headers,
    )


PEAKS_CACHE: dict[tuple[str, int], list[float]] = {}
PEAKS_CACHE_LIMIT = 256


def _cache_peaks(cache_key: tuple[str, int], peaks: list[float]) -> None:
    PEAKS_CACHE[cache_key] = peaks
    while len(PEAKS_CACHE) > PEAKS_CACHE_LIMIT:
        PEAKS_CACHE.pop(next(iter(PEAKS_CACHE)))


def compute_peaks(data: bytes, points: int) -> list[float]:
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                "pipe:0",
                "-vn",
                "-ac",
                "1",
                "-ar",
                "8000",
                "-f",
                "s16le",
                "pipe:1",
            ],
            input=data,
            check=True,
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Could not decode audio for waveform",
        ) from exc

    samples = array.array("h")
    sample_bytes = len(result.stdout) - (len(result.stdout) % 2)
    samples.frombytes(result.stdout[:sample_bytes])
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        return []

    bucket = max(1, len(samples) // points)
    peaks: list[float] = []
    for start in range(0, len(samples), bucket):
        chunk = samples[start : start + bucket]
        peaks.append(min(1.0, max(abs(value) for value in chunk) / 32768.0))
        if len(peaks) >= points:
            break
    return peaks


async def peaks_payload(
    storage: ObjectStorage,
    key: str,
    points: int,
) -> dict[str, list[float]]:
    cache_key = (key, points)
    peaks = PEAKS_CACHE.get(cache_key)
    if peaks is not None:
        return {"peaks": peaks}

    cache_object = (
        "peaks/" + hashlib.sha256(f"{key}:{points}".encode()).hexdigest() + ".json"
    )
    try:
        if await storage.exists(cache_object):
            cached = json.loads(await storage.get(cache_object))
            if isinstance(cached, list):
                peaks = [float(value) for value in cached]
                _cache_peaks(cache_key, peaks)
                return {"peaks": peaks}
    except Exception:
        # A missing or unreadable cache must never block the waveform.
        pass

    if not await storage.exists(key):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found"
        )
    data = await storage.get(key)
    peaks = await asyncio.to_thread(compute_peaks, data, points)
    _cache_peaks(cache_key, peaks)
    try:
        await storage.put(
            cache_object, json.dumps(peaks).encode(), "application/json"
        )
    except Exception:
        # Caching is best effort.
        pass
    return {"peaks": peaks}


@router.post(
    "",
    response_model=JobRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("job"))],
)
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
    except ProfileNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found"
        ) from exc
    except InsufficientCredits as exc:
        return insufficient_credits(exc)
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
            .where(Job.user_id == user.id, Job.parent_job_id.is_(None))
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


@router.patch("/{job_id}", response_model=JobRead)
async def update_job(
    job_id: str,
    payload: JobUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> JobRead:
    job = await load_job(session, user, job_id)
    if job.parent_job_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Only projects can be renamed",
        )
    job.source_filename = payload.source_filename
    session.add(job)
    await session.commit()
    artifacts = (
        await session.exec(
            select(JobArtifact)
            .where(JobArtifact.job_id == job.id)
            .order_by(JobArtifact.created_at)
        )
    ).all()
    return to_job_read(job, artifacts)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    storage: ObjectStorage = Depends(get_storage),
) -> Response:
    job = await load_job(session, user, job_id)
    if job.parent_job_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Only projects can be deleted",
        )

    children = (
        await session.exec(select(Job).where(Job.parent_job_id == job.id))
    ).all()
    all_jobs = [job, *children]
    if any(item.status in {"queued", "running"} for item in all_jobs):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a project while processing is active",
        )

    artifacts = (
        await session.exec(
            select(JobArtifact).where(
                JobArtifact.job_id.in_([item.id for item in all_jobs])
            )
        )
    ).all()

    storage_keys = {artifact.r2_key for artifact in artifacts}
    source_key = job.source_r2_key

    for artifact in artifacts:
        await session.delete(artifact)
    for child in children:
        await session.delete(child)
    await session.delete(job)
    await session.flush()

    if source_key and not source_key.startswith("demo/"):
        still_referenced = (
            await session.exec(
                select(Job.id).where(Job.source_r2_key == source_key).limit(1)
            )
        ).first()
        if still_referenced is None:
            storage_keys.add(source_key)

    await session.commit()

    for key in storage_keys:
        try:
            await storage.delete(key)
        except Exception:
            pass

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{job_id}/effects", response_model=list[JobRead])
async def list_effects(
    job_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[JobRead]:
    parent = await load_job(session, user, job_id)
    children = (
        await session.exec(
            select(Job)
            .where(Job.parent_job_id == parent.id)
            .order_by(Job.created_at)
        )
    ).all()
    if not children:
        return []

    artifacts = (
        await session.exec(
            select(JobArtifact)
            .where(JobArtifact.job_id.in_([child.id for child in children]))
            .order_by(JobArtifact.created_at)
        )
    ).all()
    grouped: dict[str, list[JobArtifact]] = defaultdict(list)
    for artifact in artifacts:
        grouped[artifact.job_id].append(artifact)

    return [to_job_read(child, grouped[child.id]) for child in children]


@router.post(
    "/{job_id}/effects",
    response_model=JobRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("job"))],
)
async def apply_effect(
    job_id: str,
    payload: EffectCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    runner: PipelineRunner = Depends(get_runner),
):
    parent = await load_job(session, user, job_id)
    if parent.parent_job_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Effects can only be applied to a project",
        )
    try:
        job = await create_effect_run(session, user, parent, runner, payload)
    except ProfileNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found"
        ) from exc
    except InsufficientCredits as exc:
        return insufficient_credits(exc)
    return to_job_read(job)


@router.get("/{job_id}/source")
async def get_source(
    job_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_id),
    storage: ObjectStorage = Depends(get_storage),
) -> Response:
    async with request.app.state.sessionmaker() as session:
        job = await _load_job_for_user(session, user_id, job_id)
        media_type = (
            mimetypes.guess_type(job.source_filename)[0]
            or "application/octet-stream"
        )
        filename = Path(job.source_filename).name.replace('"', "")
        key = job.source_r2_key
    return await media_response(request, storage, key, media_type, filename)


@router.get("/{job_id}/source/peaks")
async def source_peaks(
    job_id: str,
    request: Request,
    points: int = Query(default=512, ge=64, le=2048),
    user_id: str = Depends(get_current_user_id),
    storage: ObjectStorage = Depends(get_storage),
) -> dict[str, list[float]]:
    async with request.app.state.sessionmaker() as session:
        job = await _load_job_for_user(session, user_id, job_id)
        key = job.source_r2_key
    return await peaks_payload(storage, key, points)


@router.get("/{job_id}/artifacts/{artifact_id}/content")
async def artifact_content(
    job_id: str,
    artifact_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_id),
    storage: ObjectStorage = Depends(get_storage),
) -> Response:
    async with request.app.state.sessionmaker() as session:
        job = await _load_job_for_user(session, user_id, job_id)
        artifact = await session.get(JobArtifact, artifact_id)
        if artifact is None or artifact.job_id != job.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found"
            )
        media_type = CONTENT_MEDIA_TYPES.get(artifact.format) or (
            mimetypes.guess_type(Path(artifact.r2_key).name)[0]
            or "application/octet-stream"
        )
        filename = Path(artifact.r2_key).name.replace('"', "")
        key = artifact.r2_key
    return await media_response(request, storage, key, media_type, filename)


@router.get("/{job_id}/artifacts/{artifact_id}/peaks")
async def artifact_peaks(
    job_id: str,
    artifact_id: str,
    request: Request,
    points: int = Query(default=512, ge=64, le=2048),
    user_id: str = Depends(get_current_user_id),
    storage: ObjectStorage = Depends(get_storage),
) -> dict[str, list[float]]:
    async with request.app.state.sessionmaker() as session:
        job = await _load_job_for_user(session, user_id, job_id)
        artifact = await session.get(JobArtifact, artifact_id)
        if artifact is None or artifact.job_id != job.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found"
            )
        key = artifact.r2_key
    return await peaks_payload(storage, key, points)


@router.patch("/{job_id}/speakers", response_model=JobRead)
async def update_speakers(
    job_id: str,
    payload: SpeakerRolesUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    storage: ObjectStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings_dep),
) -> JobRead:
    job = await load_job(session, user, job_id)
    if set(payload.roles) != set((job.speaker_roles or {}).keys()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="roles must match detected speakers",
        )

    job.speaker_roles = dict(payload.roles)
    try:
        await regenerate_cut_outputs(
            session, storage, job, job.speaker_roles, settings
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Transcript is not available for this job",
        ) from exc

    session.add(job)
    await session.commit()

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
    settings: Settings = Depends(get_settings_dep),
    broker: EventBroker = Depends(get_broker),
):
    # Subscribe before reading the snapshot so terminal events published during
    # the DB read cannot be missed. Open and close the DB session before
    # returning EventSourceResponse so long-lived SSE streams do not hold
    # connections from SQLAlchemy's pool.
    subscription = broker.subscribe(job_id)
    try:
        async with request.app.state.sessionmaker() as session:
            user = await get_current_user(request, session=session, settings=settings)
            job = await load_job(session, user, job_id)
            artifacts = (
                await session.exec(select(JobArtifact).where(JobArtifact.job_id == job.id))
            ).all()
            job_status = job.status
            snapshot = to_job_read(job, artifacts).model_dump(mode="json")
    except Exception:
        close = getattr(subscription, "close", None)
        if close is not None:
            await close()
        raise

    async def event_stream():
        try:
            yield {"event": "snapshot", "data": json.dumps(snapshot)}
            if job_status in {"completed", "failed"}:
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


@router.delete(
    "/{job_id}/artifacts/{artifact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_artifact(
    job_id: str,
    artifact_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    storage: ObjectStorage = Depends(get_storage),
) -> Response:
    parent = await load_job(session, user, job_id)
    artifact = await session.get(JobArtifact, artifact_id)
    owner = await session.get(Job, artifact.job_id) if artifact is not None else None
    if (
        artifact is None
        or owner is None
        or (owner.id != parent.id and owner.parent_job_id != parent.id)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Track not found"
        )

    artifact_key = artifact.r2_key
    await session.delete(artifact)
    await session.flush()

    # A generated track's effect run disappears with its last output, so the
    # inspector does not keep claiming the effect is applied with no track.
    if owner.parent_job_id is not None:
        remaining = (
            await session.exec(
                select(JobArtifact).where(JobArtifact.job_id == owner.id)
            )
        ).all()
        if not remaining:
            await session.delete(owner)
    await session.commit()

    try:
        await storage.delete(artifact_key)
    except Exception:
        pass
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{job_id}/artifacts/{artifact_id}/download")
async def download_artifact(
    job_id: str,
    artifact_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    storage: ObjectStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings_dep),
) -> Response:
    job = await load_job(session, user, job_id)
    artifact = await session.get(JobArtifact, artifact_id)
    if artifact is None or artifact.job_id != job.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found"
        )

    filename = (
        Path(artifact.r2_key).name.replace('"', "").replace("\r", "").replace("\n", "")
    )
    if artifact.format in TEXT_MEDIA_TYPES:
        if not await storage.exists(artifact.r2_key):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Artifact file not found"
            )
        data = await storage.get(artifact.r2_key)
        return Response(
            content=data,
            media_type=TEXT_MEDIA_TYPES[artifact.format],
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    url = storage.signed_download_url(
        artifact.r2_key,
        filename,
        settings.download_url_ttl_seconds,
    )
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)
