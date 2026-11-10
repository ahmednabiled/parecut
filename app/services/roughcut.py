from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.models import Job, JobArtifact
from app.renderers import build_cut_plan, render_rough_cut_md, render_transcript
from app.storage import ObjectStorage
from parecut_engine.schemas import RoughCutMeta, SpeakerRole, Transcript

_MIME = {
    "wav": "audio/wav",
    "md": "text/markdown",
    "srt": "application/x-subrip",
    "vtt": "text/vtt",
    "json": "application/json",
}


async def _write_artifact(
    session: AsyncSession,
    storage: ObjectStorage,
    job: Job,
    *,
    kind: str,
    label: str,
    fmt: str,
    key: str,
    content: str,
) -> JobArtifact:
    data = content.encode("utf-8")
    await storage.put(key, data, _MIME.get(fmt, "application/octet-stream"))
    artifact = JobArtifact(
        job_id=job.id,
        kind=kind,
        label=label,
        format=fmt,
        r2_key=key,
        size_bytes=len(data),
    )
    session.add(artifact)
    await session.flush()
    return artifact


async def _delete_kinds(
    session: AsyncSession,
    storage: ObjectStorage,
    job_id: str,
    kinds: set[str],
) -> None:
    rows = (
        await session.exec(
            select(JobArtifact).where(
                JobArtifact.job_id == job_id, JobArtifact.kind.in_(kinds)
            )
        )
    ).all()
    for row in rows:
        await storage.delete(row.r2_key)
        await session.delete(row)
    await session.flush()


async def write_before_artifacts(
    session: AsyncSession,
    storage: ObjectStorage,
    job: Job,
    transcript: Transcript,
    settings: Settings,
) -> None:
    root = f"jobs/{job.id}"
    entries = [
        ("json", "transcript_raw.json"),
        ("md", "transcript_before.md"),
        ("srt", "transcript_before.srt"),
        ("vtt", "transcript_before.vtt"),
    ]
    for fmt, filename in entries:
        content = render_transcript(
            transcript,
            [],
            {},
            job.fps,
            variant="before",
            fmt=fmt,
        )
        await _write_artifact(
            session,
            storage,
            job,
            kind="transcript_before",
            label="Demo — Transcript (Before Cut)",
            fmt=fmt,
            key=f"{root}/{filename}",
            content=content,
        )


async def write_cut_outputs(
    session: AsyncSession,
    storage: ObjectStorage,
    job: Job,
    transcript: Transcript,
    roles: dict[str, SpeakerRole],
    settings: Settings,
    *,
    demo: bool = False,
) -> None:
    root = f"jobs/{job.id}"
    after_label = (
        "Demo — Transcript (After Cut)" if demo else "Transcript (After Cut)"
    )
    rough_label = "Demo — ROUGH-CUT.md" if demo else "ROUGH-CUT.md"
    plan = build_cut_plan(transcript, roles)
    kept_duration = sum(
        range_.end - range_.start for range_ in plan if range_.action == "keep"
    )
    transcript_end = max((segment.end for segment in transcript.segments), default=0.0)
    meta = RoughCutMeta(
        source_filename=job.source_filename,
        duration_seconds=job.duration_seconds or transcript_end,
        fps=job.fps,
        sample_rate=job.sample_rate,
        estimated_duration_seconds=kept_duration,
    )

    for fmt in ("md", "srt", "vtt", "json"):
        content = render_transcript(
            transcript,
            plan,
            roles,
            job.fps,
            variant="after",
            fmt=fmt,
        )
        await _write_artifact(
            session,
            storage,
            job,
            kind="transcript_after",
            label=after_label,
            fmt=fmt,
            key=f"{root}/transcript_after.{fmt}",
            content=content,
        )

    await _write_artifact(
        session,
        storage,
        job,
        kind="rough_cut_md",
        label=rough_label,
        fmt="md",
        key=f"{root}/ROUGH-CUT.md",
        content=render_rough_cut_md(meta, plan, roles),
    )


async def regenerate_cut_outputs(
    session: AsyncSession,
    storage: ObjectStorage,
    job: Job,
    roles: dict[str, SpeakerRole],
    settings: Settings,
) -> None:
    canonical = (
        await session.exec(
            select(JobArtifact).where(
                JobArtifact.job_id == job.id,
                JobArtifact.kind == "transcript_before",
                JobArtifact.format == "json",
            )
        )
    ).first()
    if canonical is None:
        raise ValueError("canonical transcript is missing")

    raw = await storage.get(canonical.r2_key)
    transcript = Transcript.model_validate_json(raw)
    demo = canonical.label.startswith("Demo — ")

    await _delete_kinds(session, storage, job.id, {"transcript_after", "rough_cut_md"})
    await write_cut_outputs(
        session, storage, job, transcript, roles, settings, demo=demo
    )
