import json
import logging
import os
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpx

from app.renderers import build_cut_plan, render_rough_cut_md, render_transcript
from app.services.stages import enabled_stages
from parecut_engine.schemas import (
    PipelineConfig,
    RoughCutMeta,
    SpeakerRole,
    Transcript,
    TranscriptSegment,
)

logger = logging.getLogger("parecut.worker")

MIME_TYPES = {
    "wav": "audio/wav",
    "md": "text/markdown",
    "srt": "application/x-subrip",
    "vtt": "text/vtt",
    "json": "application/json",
}

Denoiser = Callable[[Path, Path], None]
Enhancer = Callable[[Path, Path, float], None]
Transcriber = Callable[[Path], Transcript]
Diarizer = Callable[[Path], list["SpeakerTurn"]]
Separator = Callable[[Path, Path], tuple[bytes, bytes]]

NEMOTRON_PYTHON = "/opt/nemotron/bin/python"
NEMOTRON_SCRIPT = "/opt/nemotron/diarize.py"
RESEMBLE_RUN_DIR = Path(
    os.getenv(
        "PARECUT_RESEMBLE_RUN_DIR",
        "/opt/resemble-enhance/enhancer_stage2",
    )
)

_MODEL = None
_STATE = None
_WHISPER_MODEL = None
_ALIGN_MODELS: dict[str, tuple[Any, Any]] = {}
_DEMUCS_MODEL = None


@dataclass
class SpeakerTurn:
    speaker: str
    start: float
    end: float


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


def _convert_to_wav(
    input_path: Path, output_path: Path, sample_rate: int = 48000
) -> None:
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
                str(sample_rate),
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


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as reader:
        return reader.getnframes() / reader.getframerate()


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


def _resemble_enhance(input_path: Path, output_path: Path, mix: float) -> None:
    import torch
    import torchaudio
    from resemble_enhance.enhancer.inference import enhance

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dry, dry_rate = torchaudio.load(str(input_path))
    dry = dry.mean(dim=0).to(torch.float32)
    if dry_rate != 48000:
        dry = torchaudio.functional.resample(dry, dry_rate, 48000)

    wet, wet_rate = enhance(
        dwav=dry,
        sr=48000,
        device=device,
        nfe=32,
        solver="midpoint",
        lambd=0.5,
        tau=0.5,
        run_dir=RESEMBLE_RUN_DIR,
    )
    wet = wet.to(torch.float32)
    if wet_rate != 48000:
        wet = torchaudio.functional.resample(wet, wet_rate, 48000)

    length = min(wet.numel(), dry.numel())
    wet = wet[:length]
    dry = dry[:length]
    amount = max(0.0, min(1.0, mix))
    blended = wet * amount + dry * (1.0 - amount)
    peak = blended.abs().max()
    if peak > 1.0:
        blended = blended / peak

    output_path.parent.mkdir(parents=True, exist_ok=True)
    torchaudio.save(
        str(output_path),
        blended.unsqueeze(0),
        48000,
        bits_per_sample=16,
    )


def prepare_audio(
    source: bytes,
    source_filename: str,
    workdir: Path,
    *,
    denoiser: Denoiser | None = None,
    denoise: bool = True,
) -> tuple[bytes, Path]:
    suffix = Path(source_filename).suffix or ".bin"
    input_path = workdir / f"source{suffix}"
    wav_path = workdir / "input.wav"
    input_path.write_bytes(source)

    logger.info("converting %s to 48 kHz mono", source_filename)
    _convert_to_wav(input_path, wav_path)

    if not denoise:
        return wav_path.read_bytes(), wav_path

    output_path = workdir / "denoised.wav"
    if denoiser is None:
        _deepfilternet(wav_path, output_path)
    else:
        denoiser(wav_path, output_path)

    return output_path.read_bytes(), output_path


def denoise_source(
    source: bytes,
    source_filename: str,
    workdir: Path,
    *,
    denoiser: Denoiser | None = None,
) -> bytes:
    return prepare_audio(
        source, source_filename, workdir, denoiser=denoiser, denoise=True
    )[0]


def _get_whisper_model():
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        import whisperx

        logger.info("loading WhisperX large-v3-turbo")
        _WHISPER_MODEL = whisperx.load_model(
            "large-v3-turbo",
            device="cpu",
            compute_type="int8",
            download_root="/root/.cache/whisperx",
        )
        logger.info("WhisperX ready")
    return _WHISPER_MODEL


def _get_align_model(language: str) -> tuple[Any, Any]:
    if language not in _ALIGN_MODELS:
        import whisperx

        logger.info("loading alignment model for %s", language)
        _ALIGN_MODELS[language] = whisperx.load_align_model(
            language_code=language,
            device="cpu",
        )
        logger.info("alignment model ready for %s", language)
    return _ALIGN_MODELS[language]


def transcribe_audio(
    wav_path: Path, *, transcriber: Transcriber | None = None
) -> Transcript:
    if transcriber is not None:
        return transcriber(wav_path)

    import whisperx

    model = _get_whisper_model()
    audio = whisperx.load_audio(str(wav_path))
    result = model.transcribe(audio, batch_size=8)
    segments = result.get("segments", [])
    language = str(result.get("language") or "en")

    words: list[TranscriptSegment] = []
    try:
        align_model, metadata = _get_align_model(language)
        aligned = whisperx.align(
            segments,
            align_model,
            metadata,
            audio,
            device="cpu",
            return_char_alignments=False,
        )
        for segment in aligned.get("segments", []):
            for word in segment.get("words", []):
                start = word.get("start")
                end = word.get("end")
                text = str(word.get("word", "")).strip()
                if start is None or end is None or not text:
                    continue
                words.append(
                    TranscriptSegment(
                        speaker="SPEAKER_01",
                        start=float(start),
                        end=float(end),
                        text=text,
                    )
                )
    except Exception:
        logger.exception("alignment failed; using segment timestamps")

    if words:
        return Transcript(speakers=["SPEAKER_01"], segments=words)

    fallback = [
        TranscriptSegment(
            speaker="SPEAKER_01",
            start=float(segment["start"]),
            end=float(segment["end"]),
            text=str(segment.get("text", "")).strip(),
        )
        for segment in segments
        if str(segment.get("text", "")).strip()
    ]
    return Transcript(
        speakers=["SPEAKER_01"] if fallback else [],
        segments=fallback,
    )


def merge_words(transcript: Transcript) -> Transcript:
    if not transcript.segments:
        return transcript

    merged: list[TranscriptSegment] = []
    current = transcript.segments[0].model_copy()
    for segment in transcript.segments[1:]:
        text = current.text.rstrip()
        same_speaker = segment.speaker == current.speaker
        sentence_end = text.endswith((".", "!", "?"))
        too_long = current.end - current.start >= 8.0
        if same_speaker and not sentence_end and not too_long:
            current.text = f"{text} {segment.text.lstrip()}".strip()
            current.end = segment.end
        else:
            merged.append(current)
            current = segment.model_copy()
    merged.append(current)
    return Transcript(speakers=transcript.speakers, segments=merged)


def diarize_audio(
    wav_path: Path, *, diarizer: Diarizer | None = None
) -> list[SpeakerTurn]:
    if diarizer is not None:
        return diarizer(wav_path)

    with tempfile.TemporaryDirectory() as tmp:
        diar_wav = Path(tmp) / "diarize.wav"
        turns_path = Path(tmp) / "turns.json"
        logger.info("running Nemotron diarization")
        _convert_to_wav(wav_path, diar_wav, sample_rate=16000)

        try:
            subprocess.run(
                [
                    NEMOTRON_PYTHON,
                    NEMOTRON_SCRIPT,
                    str(diar_wav),
                    str(turns_path),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=900,
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "")[-1000:]
            raise RuntimeError(f"Nemotron diarization failed: {stderr}") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Nemotron diarization timed out") from exc

        payload = json.loads(turns_path.read_text(encoding="utf-8"))

    return [
        SpeakerTurn(
            speaker=str(item["speaker"]),
            start=float(item["start"]),
            end=float(item["end"]),
        )
        for item in payload
    ]


def _overlap(segment: TranscriptSegment, turn: SpeakerTurn) -> float:
    return max(0.0, min(segment.end, turn.end) - max(segment.start, turn.start))


def assign_speakers(
    transcript: Transcript, turns: list[SpeakerTurn]
) -> Transcript:
    if not turns:
        return transcript

    speakers = sorted({turn.speaker for turn in turns})
    segments = []
    for segment in transcript.segments:
        best = max(turns, key=lambda turn: _overlap(segment, turn))
        speaker = best.speaker if _overlap(segment, best) > 0 else speakers[0]
        segments.append(segment.model_copy(update={"speaker": speaker}))

    return Transcript(speakers=speakers, segments=segments)


def _get_demucs_model():
    global _DEMUCS_MODEL
    if _DEMUCS_MODEL is None:
        from demucs.pretrained import get_model

        logger.info("loading Demucs htdemucs_ft")
        _DEMUCS_MODEL = get_model("htdemucs_ft")
        logger.info("Demucs ready")
    return _DEMUCS_MODEL


def separate_music(
    wav_path: Path,
    workdir: Path,
    *,
    separator: Separator | None = None,
) -> tuple[bytes, bytes]:
    if separator is not None:
        return separator(wav_path, workdir)

    import torchaudio
    from demucs.apply import apply_model
    from demucs.audio import AudioFile

    model = _get_demucs_model()
    wav = AudioFile(str(wav_path)).read(
        streams=0, samplerate=model.samplerate, channels=model.audio_channels
    )
    ref = wav.mean(0)
    wav = (wav - ref.mean()) / (ref.std() + 1e-8)
    sources = apply_model(model, wav[None], device="cpu", progress=False)[0]
    sources = sources * ref.std() + ref.mean()

    music = sources[0] + sources[1] + sources[2]
    dialogue = sources[3]

    music_path = workdir / "music.wav"
    dialogue_path = workdir / "dialogue.wav"
    torchaudio.save(str(music_path), music.cpu(), model.samplerate)
    torchaudio.save(str(dialogue_path), dialogue.cpu(), model.samplerate)
    return music_path.read_bytes(), dialogue_path.read_bytes()


def gated_speaker_tracks(
    wav_path: Path, turns: list[SpeakerTurn]
) -> dict[str, bytes]:
    with wave.open(str(wav_path), "rb") as reader:
        params = reader.getparams()
        frames = reader.readframes(reader.getnframes())

    width = params.sampwidth
    total = len(frames) // width
    tracks: dict[str, bytes] = {}

    for speaker in sorted({turn.speaker for turn in turns}):
        out = bytearray(len(frames))
        for turn in turns:
            if turn.speaker != speaker:
                continue
            start = max(0, int(turn.start * params.framerate))
            end = min(total, int(turn.end * params.framerate))
            if end <= start:
                continue
            out[start * width : end * width] = frames[start * width : end * width]

        path = wav_path.parent / f"{speaker}.wav"
        with wave.open(str(path), "wb") as writer:
            writer.setparams(params)
            writer.writeframes(bytes(out))
        tracks[speaker] = path.read_bytes()

    return tracks


def _artifact_content(
    artifact: dict[str, str],
    source: bytes,
    denoised: bytes | None,
    enhanced: bytes | None,
    transcript: Transcript,
    plan,
    roles: dict[str, SpeakerRole],
    meta: RoughCutMeta,
    music: bytes | None,
    dialogue: bytes | None,
    speaker_outputs: dict[str, bytes],
) -> bytes | None:
    kind = artifact["kind"]
    fmt = artifact["format"]

    if kind == "cleaned_audio":
        return denoised or source
    if kind == "enhanced_audio":
        if enhanced is None:
            raise RuntimeError(
                "Enhancement is enabled but the enhancer produced no audio"
            )
        return enhanced
    if kind == "stem_music":
        return music
    if kind == "stem_dialogue":
        return dialogue
    if kind == "stem_speaker":
        return speaker_outputs.get(artifact["key"])
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
    kind = artifact["kind"]
    if kind == "cleaned_audio":
        return "Denoised Audio (DeepFilterNet3)"
    if kind == "enhanced_audio":
        return "Enhanced Audio (Resemble Enhance)"
    if kind == "stem_music":
        return "Music Stem (Demucs)"
    if kind == "stem_dialogue":
        return "Dialogue Stem (Demucs)"
    if kind == "stem_speaker":
        suffix = Path(artifact["key"]).stem.rsplit("_", 1)[-1]
        return f"Speaker {suffix} (gated)"
    if kind == "transcript_before":
        return "Transcript (Before Cut)"
    if kind == "transcript_after":
        return "Transcript (After Cut)"
    if kind == "rough_cut_md":
        return "ROUGH-CUT.md"
    return artifact["label"]


def handler(
    job: dict,
    client: httpx.Client | None = None,
    *,
    denoiser: Denoiser | None = None,
    enhancer: Enhancer | None = None,
    transcriber: Transcriber | None = None,
    diarizer: Diarizer | None = None,
    separator: Separator | None = None,
) -> dict[str, Any]:
    data = job["input"]
    config = PipelineConfig.model_validate(data["pipeline"])
    client = client or httpx.Client(timeout=600)
    source_filename = data.get("source_filename", "source")

    logger.info("downloading source %s", data["source_url"])
    source = _download(client, data["source_url"])
    logger.info("downloaded %d bytes", len(source))

    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        denoise = config.noise_reduction or config.enhance
        denoised, working_wav = prepare_audio(
            source,
            source_filename,
            workdir,
            denoiser=denoiser,
            denoise=denoise,
        )
        duration = float(data.get("duration_seconds") or _wav_duration(working_wav))

        enhanced: bytes | None = None
        if config.enhance:
            enhanced_path = workdir / "enhanced.wav"
            if enhancer is None:
                _resemble_enhance(
                    working_wav,
                    enhanced_path,
                    config.enhance_mix,
                )
            else:
                enhancer(working_wav, enhanced_path, config.enhance_mix)
            enhanced = enhanced_path.read_bytes()

        turns: list[SpeakerTurn] = []
        diarization_fallback = False
        diarization_error: str | None = None
        if config.transcribe or config.separate_speakers:
            try:
                turns = diarize_audio(working_wav, diarizer=diarizer)
            except Exception as exc:
                logger.exception("diarization failed; using one speaker")
                diarization_fallback = True
                diarization_error = f"{type(exc).__name__}: {exc}"
            if not turns:
                diarization_fallback = True
                turns = [SpeakerTurn("SPEAKER_01", 0.0, duration)]

        transcript = Transcript(speakers=[], segments=[])
        if config.transcribe:
            transcript = transcribe_audio(working_wav, transcriber=transcriber)
            transcript = assign_speakers(transcript, turns)
            transcript = merge_words(transcript)

        roles: dict[str, SpeakerRole] = {
            speaker: "presenter" for speaker in transcript.speakers
        }
        plan = build_cut_plan(transcript, roles) if transcript.segments else []
        kept_duration = sum(
            item.end - item.start for item in plan if item.action == "keep"
        )
        meta = RoughCutMeta(
            source_filename=source_filename,
            duration_seconds=duration,
            fps=data.get("fps", "25"),
            sample_rate=data.get("sample_rate"),
            estimated_duration_seconds=kept_duration,
        )

        music = dialogue = None
        if config.separate_music:
            music, dialogue = separate_music(
                working_wav, workdir, separator=separator
            )

        speaker_outputs: dict[str, bytes] = {}
        if config.separate_speakers:
            tracks = gated_speaker_tracks(working_wav, turns)
            speaker_keys = [
                artifact["key"]
                for artifact in data["expected_artifacts"]
                if artifact["kind"] == "stem_speaker"
            ]
            for key, speaker in zip(speaker_keys, sorted(tracks)):
                speaker_outputs[key] = tracks[speaker]

        outputs = data["outputs"]
        artifacts: list[dict[str, Any]] = []
        for artifact in data["expected_artifacts"]:
            content = _artifact_content(
                artifact,
                source,
                denoised if denoise else None,
                enhanced,
                transcript,
                plan,
                roles,
                meta,
                music,
                dialogue,
                speaker_outputs,
            )
            if content is None:
                continue
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
        "diarization": {
            "fallback": diarization_fallback,
            "error": diarization_error,
            "turns": len(turns),
            "speakers": sorted({turn.speaker for turn in turns}),
        },
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("PARECUT_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    import runpod

    runpod.serverless.start({"handler": handler})
