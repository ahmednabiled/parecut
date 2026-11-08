import json
import os
from typing import Any

import httpx

from app.demo_data import demo_transcript
from app.renderers import build_cut_plan, render_rough_cut_md, render_transcript
from app.services.stages import enabled_stages
from parecut_engine.schemas import PipelineConfig, RoughCutMeta, SpeakerRole

MIME_TYPES = {
    "wav": "audio/wav",
    "md": "text/markdown",
    "srt": "application/x-subrip",
    "vtt": "text/vtt",
    "json": "application/json",
}


def _progress(job: dict, stage: str, percent: int) -> None:
    if os.getenv("PARECUT_WORKER_PROGRESS", "0") != "1":
        return
    try:
        import runpod

        runpod.serverless.progress_update(
            job, json.dumps({"stage": stage, "percent": percent})
        )
    except Exception:
        return


def _download(client: httpx.Client, url: str) -> bytes:
    response = client.get(url, follow_redirects=True)
    response.raise_for_status()
    return response.content


def _upload(client: httpx.Client, url: str, content: bytes, mime: str) -> None:
    response = client.put(url, content=content, headers={"content-type": mime})
    response.raise_for_status()


def _artifact_content(
    artifact: dict[str, str],
    source: bytes,
    transcript,
    plan,
    roles: dict[str, SpeakerRole],
    meta: RoughCutMeta,
) -> bytes:
    kind = artifact["kind"]
    fmt = artifact["format"]
    if kind == "rough_cut_md":
        return render_rough_cut_md(meta, plan, roles).encode()
    if kind == "transcript_before":
        return render_transcript(
            transcript, [], {}, meta.fps, variant="before", fmt=fmt
        ).encode()
    if kind == "transcript_after":
        return render_transcript(
            transcript, plan, roles, meta.fps, variant="after", fmt=fmt
        ).encode()
    return source


def handler(job: dict, client: httpx.Client | None = None) -> dict[str, Any]:
    data = job["input"]
    config = PipelineConfig.model_validate(data["pipeline"])
    client = client or httpx.Client(timeout=120)

    source = _download(client, data["source_url"])
    transcript = demo_transcript(data.get("duration_seconds"))
    roles: dict[str, SpeakerRole] = {
        speaker: "presenter" for speaker in transcript.speakers
    }
    plan = build_cut_plan(transcript, roles)
    kept_duration = sum(
        item.end - item.start for item in plan if item.action == "keep"
    )
    transcript_end = max((segment.end for segment in transcript.segments), default=0.0)
    meta = RoughCutMeta(
        source_filename=data.get("source_filename", "source"),
        duration_seconds=data.get("duration_seconds") or transcript_end,
        fps=data.get("fps", "25"),
        sample_rate=data.get("sample_rate"),
        estimated_duration_seconds=kept_duration,
    )

    outputs = data["outputs"]
    artifacts: list[dict[str, Any]] = []
    for artifact in data["expected_artifacts"]:
        content = _artifact_content(
            artifact, source, transcript, plan, roles, meta
        )
        mime = MIME_TYPES.get(artifact["format"], "application/octet-stream")
        _upload(client, outputs[artifact["key"]], content, mime)
        artifacts.append(
            {
                "key": artifact["key"],
                "kind": artifact["kind"],
                "label": f"Stub — {artifact['label']}",
                "format": artifact["format"],
                "size_bytes": len(content),
            }
        )

    stages = {
        stage: {"status": "completed", "percent": 100}
        for stage in enabled_stages(config)
    }
    for stage in stages:
        _progress(job, stage, 100)

    return {
        "artifacts": artifacts,
        "stages": stages,
        "speaker_roles": roles,
    }


if __name__ == "__main__":
    import runpod

    runpod.serverless.start({"handler": handler})
