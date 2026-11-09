import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

import httpx

from app.demo_data import demo_transcript
from app.renderers import build_cut_plan, render_rough_cut_md, render_transcript
from app.services.stages import enabled_stages
from parecut_engine.schemas import PipelineConfig, RoughCutMeta, SpeakerRole

logger = logging.getLogger("parecut.worker")

MIME_TYPES = {
    "wav": "audio/wav",
    "md": "text/markdown",
    "srt": "application/x-subrip",
    "vtt": "text/vtt",
    "json": "application/json",
}

Denoiser = Callable[[Path, Path], None]

_MODEL = None
_STATE = None


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


def _convert_to_wav(input_path: Path, output_path: Path) -> None:
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(input_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "48000",
                "-c:a",
                "pcm_s16le",
                str(output_path),
            ],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"").decode("utf-8", "replace")
        raise RuntimeError(f"ffmpeg conversion failed: {stderr[-1000:]}") from exc


def _get_model():
    global _MODEL, _STATE
    if _MODEL is None or _STATE is None:
        from df.enhance import init_df

        logger.info("loading DeepFilterNet3")
        _MODEL, _STATE, _ = init_df(log_file=None)
        logger.info("DeepFilterNet3 ready")
    return _MODEL, _STATE


def _deepfilternet(input_path: Path, output_path: Path) -> None:
    from df.enhance import enhance, load_audio, save_audio

    model, state = _get_model()
    audio, _ = load_audio(str(input_path), sr=state.sr())
    enhanced = enhance(model, state, audio)
    save_audio(str(output_path), enhanced, state.sr())


def denoise_source(
    source: bytes,
    source_filename: str,
    workdir: Path,
    *,
    denoiser: Denoiser | None = None,
) -> bytes:
    suffix = Path(source_filename).suffix or ".bin"
    input_path = workdir / f"source{suffix}"
    wav_path = workdir / "input.wav"
    output_path = workdir / "denoised.wav"
    input_path.write_bytes(source)

    logger.info("converting %s to 48 kHz mono", source_filename)
    _convert_to_wav(input_path, wav_path)

    if denoiser is None:
        _deepfilternet(wav_path, output_path)
    else:
        denoiser(wav_path, output_path)

    return output_path.read_bytes()


def _artifact_content(
    artifact: dict[str, str],
    source: bytes,
    denoised: bytes | None,
    transcript,
    plan,
    roles: dict[str, SpeakerRole],
    meta: RoughCutMeta,
) -> bytes:
    kind = artifact["kind"]
    fmt = artifact["format"]
    if kind in {"cleaned_audio", "enhanced_audio"} and denoised is not None:
        return denoised
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


def _artifact_label(artifact: dict[str, str]) -> str:
    if artifact["kind"] == "cleaned_audio":
        return "Denoised Audio (DeepFilterNet3)"
    if artifact["kind"] == "enhanced_audio":
        return "Denoised Audio (Enhancement pending)"
    return f"Stub — {artifact['label']}"


def handler(
    job: dict,
    client: httpx.Client | None = None,
    denoiser: Denoiser | None = None,
) -> dict[str, Any]:
    data = job["input"]
    config = PipelineConfig.model_validate(data["pipeline"])
    client = client or httpx.Client(timeout=600)
    source_filename = data.get("source_filename", "source")

    logger.info("downloading source %s", data["source_url"])
    source = _download(client, data["source_url"])
    logger.info("downloaded %d bytes", len(source))

    denoised = None
    if config.noise_reduction or config.enhance:
        with tempfile.TemporaryDirectory() as tmp:
            denoised = denoise_source(
                source,
                source_filename,
                Path(tmp),
                denoiser=denoiser,
            )
        logger.info("denoised audio is %d bytes", len(denoised))

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
        source_filename=source_filename,
        duration_seconds=data.get("duration_seconds") or transcript_end,
        fps=data.get("fps", "25"),
        sample_rate=data.get("sample_rate"),
        estimated_duration_seconds=kept_duration,
    )

    outputs = data["outputs"]
    artifacts: list[dict[str, Any]] = []
    for artifact in data["expected_artifacts"]:
        content = _artifact_content(
            artifact, source, denoised, transcript, plan, roles, meta
        )
        mime = MIME_TYPES.get(artifact["format"], "application/octet-stream")
        logger.info("uploading %s (%d bytes)", artifact["key"], len(content))
        _upload(client, outputs[artifact["key"]], content, mime)
        artifacts.append(
            {
                "key": artifact["key"],
                "kind": artifact["kind"],
                "label": _artifact_label(artifact),
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
    logging.basicConfig(
        level=os.getenv("PARECUT_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    import runpod

    runpod.serverless.start({"handler": handler})
