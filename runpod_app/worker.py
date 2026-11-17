import json
import logging
import math
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
    StudioChain,
    Transcript,
    TranscriptSegment,
)

logger = logging.getLogger("parecut.worker")

MIME_TYPES = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "md": "text/markdown",
    "srt": "application/x-subrip",
    "vtt": "text/vtt",
    "json": "application/json",
}

AUDIO_ARTIFACT_KINDS = {
    "cleaned_audio",
    "enhanced_audio",
    "stem_music",
    "stem_dialogue",
    "stem_speaker",
}

Denoiser = Callable[[Path, Path], None]
Enhancer = Callable[[Path, Path, float], None]
StudioPolisher = Callable[[Path, Path, StudioChain], None]
Transcriber = Callable[[Path, str], Transcript]
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
_RAW_WHISPER_MODELS: dict[str, Any] = {}
_ARABIC_WHISPER_MODEL = os.getenv(
    "PARECUT_ARABIC_WHISPER_MODEL", "/opt/whisper-ar-dialectal"
)
_ALIGN_MODELS: dict[str, tuple[Any, Any]] = {}
_DEMUCS_MODEL = None
_DEVICE_LOG: set[str] = set()
_CUDA_OK: bool | None = None


def _cuda_usable() -> bool:
    """Probe CUDA with a real allocation, not just torch.cuda.is_available().

    A host can report an available CUDA device while the allocator or NVML is
    broken (for example a stale driver under MIG). Probing here lets every stage
    fall back to CPU instead of failing the job.
    """
    global _CUDA_OK
    if _CUDA_OK is not None:
        return _CUDA_OK
    try:
        import torch

        if not torch.cuda.is_available():
            _CUDA_OK = False
            return False
        torch.zeros(1, device="cuda")
        torch.cuda.synchronize()
        _CUDA_OK = True
    except Exception as exc:  # noqa: BLE001 - any CUDA init failure means CPU
        logger.warning("cuda probe failed, falling back to cpu: %s", exc)
        _CUDA_OK = False
    return _CUDA_OK


@dataclass
class SpeakerTurn:
    speaker: str
    start: float
    end: float


@dataclass
class LanguageSegment:
    language: str
    start: float
    end: float
    text: str
    confidence: float
    words: list[tuple[float, float, str]]


DEFAULT_GPU_STAGES = "noise_reduction,enhance,separate_music"
DF_CHUNK_SECONDS = 120
DF_OVERLAP_SECONDS = 2

ARABIC_DIALECT_PROMPTS = {
    "auto": (
        "محادثة بالعربية. اكتب الكلام كما يُنطق بالعامية دون تحويله إلى الفصحى."
    ),
    "msa": "محادثة بالعربية الفصحى. اكتب الكلام بالعربية دون تشكيل.",
    "egyptian": (
        "محادثة بالعامية المصرية. كلمات شائعة: إيه، عايز، مش، خالص، يعني، "
        "كده، دلوقتي، حاجة، أوي، برضو، لسه، خلاص، تمام، بص، خلينا، عشان."
    ),
    "gulf": (
        "محادثة باللهجة الخليجية. كلمات شائعة: شنو، وايد، الحين، أبي، تكفى، "
        "عشان، يعني، شلون، چذي، مو."
    ),
    "levantine": (
        "محادثة باللهجة الشامية. كلمات شائعة: شو، هلق، كتير، منيح، بدي، "
        "عنجد، هيك، ليش، كيف، هلأ."
    ),
    "maghrebi": (
        "محادثة بالدارجة المغاربية. كلمات شائعة: واش، بزاف، دابا، كيفاش، "
        "مزيان، شنو، غادي، خلاص، بصح، برك."
    ),
    "iraqi": (
        "محادثة باللهجة العراقية. كلمات شائعة: شنو، هواية، هسه، شلون، خوش، "
        "عود، ماكو، أكو، چان، گاعد."
    ),
}


def _dialect_prompt(dialect: str | None) -> str:
    return ARABIC_DIALECT_PROMPTS.get(dialect or "auto", ARABIC_DIALECT_PROMPTS["auto"])


def _gpu_stages() -> set[str] | None:
    raw = os.getenv("PARECUT_GPU_STAGES", DEFAULT_GPU_STAGES).strip().lower()
    if raw in {"", "all", "*"}:
        return None
    if raw in {"none", "cpu", "off"}:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


def _stage_allows_gpu(stage: str) -> bool:
    stages = _gpu_stages()
    if stages is None:
        return True
    if stage in stages:
        return True
    if stage in {"diarize", "diarization"}:
        return bool(stages & {"transcribe", "separate_speakers"})
    return False


def _device_for(stage: str) -> str:
    if not _stage_allows_gpu(stage):
        device = "cpu"
    else:
        try:
            import torch

            device = "cuda" if _cuda_usable() else "cpu"
            if device == "cuda" and "cuda_arch" not in _DEVICE_LOG:
                _DEVICE_LOG.add("cuda_arch")
                logger.info("cuda arch=%s", torch.cuda.get_arch_list())
        except Exception:
            device = "cpu"
    if stage not in _DEVICE_LOG:
        _DEVICE_LOG.add(stage)
        logger.info("%s device=%s", stage, device)
    return device


def _compute_type_for(stage: str) -> str:
    return "float16" if _device_for(stage) == "cuda" else "int8"


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


def _encode_audio(content: bytes, workdir: Path, fmt: str, name: str) -> bytes:
    if fmt == "wav":
        return content
    if fmt != "mp3":
        raise RuntimeError(f"unsupported audio format: {fmt}")

    source = workdir / f"{name}.src"
    target = workdir / f"{name}.mp3"
    source.write_bytes(content)
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-vn",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "192k",
                str(target),
            ],
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, OSError) as exc:
        stderr = getattr(exc, "stderr", None)
        detail = (
            (stderr or b"").decode("utf-8", "replace")
            if stderr
            else str(exc)
        )
        raise RuntimeError(f"mp3 encoding failed: {detail[-1000:]}") from exc
    return target.read_bytes()


def _get_model():
    global _MODEL, _STATE
    if _MODEL is None or _STATE is None:
        if _device_for("noise_reduction") != "cuda":
            # DeepFilterNet picks its own device; pin it before the model loads.
            import df.enhance as df_enhance
            import df.modules as df_modules

            df_enhance.get_device = lambda: "cpu"
            df_modules.get_device = lambda: "cpu"

        from df.enhance import init_df

        logger.info("loading DeepFilterNet3")
        _MODEL, _STATE, _ = init_df(log_file=None)
        logger.info("DeepFilterNet3 ready")
    return _MODEL, _STATE


def _deepfilternet(input_path: Path, output_path: Path) -> None:
    import torch
    from df.enhance import enhance, load_audio, save_audio

    model, state = _get_model()
    sr = state.sr()
    audio, _ = load_audio(str(input_path), sr=sr)

    # DeepFilterNet runs one forward pass over the whole signal, so a long
    # recording exhausts GPU memory. Process it in overlapping chunks and
    # cross-fade the joins; the result is the same length as the input.
    chunk = sr * DF_CHUNK_SECONDS
    overlap = sr * DF_OVERLAP_SECONDS
    total = audio.shape[-1]

    if total <= chunk:
        enhanced = enhance(model, state, audio)
    else:
        pieces: list[torch.Tensor] = []
        position = 0
        while position < total:
            end = min(position + chunk, total)
            segment = enhance(model, state, audio[..., position:end])
            if pieces:
                blend = min(overlap, pieces[-1].shape[-1], segment.shape[-1])
                if blend > 0:
                    fade = torch.linspace(0.0, 1.0, blend)
                    tail = (
                        pieces[-1][..., -blend:] * (1.0 - fade)
                        + segment[..., :blend] * fade
                    )
                    pieces[-1] = torch.cat(
                        [pieces[-1][..., :-blend], tail], dim=-1
                    )
                    segment = segment[..., blend:]
            pieces.append(segment)
            if end >= total:
                break
            position += chunk - overlap
        logger.info("deepfilternet chunks=%d", len(pieces))
        enhanced = torch.cat(pieces, dim=-1)

    save_audio(str(output_path), enhanced, sr)


def _resemble_enhance(input_path: Path, output_path: Path, mix: float) -> None:
    import torch
    import torchaudio
    from resemble_enhance.enhancer.inference import enhance

    device = _device_for("enhance")
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

    dry_rms = torch.sqrt(torch.mean(dry.square()))
    wet_rms = torch.sqrt(torch.mean(blended.square()))
    if wet_rms > 1e-6:
        blended = blended * (dry_rms / wet_rms)

    peak = blended.abs().max()
    if peak > 0.99:
        blended = blended / peak * 0.99

    output_path.parent.mkdir(parents=True, exist_ok=True)
    torchaudio.save(
        str(output_path),
        blended.unsqueeze(0),
        48000,
        bits_per_sample=16,
    )


def _db_to_linear(db: float) -> float:
    return 10 ** (db / 20)


def _studio_filter_chain(chain: StudioChain) -> str:
    filters = [
        f"highpass=f={chain.highpass_hz:.0f}:poles=2",
        f"equalizer=f=120:t=q:w=1:g={chain.body_db:.2f}",
        f"equalizer=f=320:t=q:w=1:g={chain.mud_db:.2f}",
        f"equalizer=f=3500:t=q:w=1:g={chain.presence_db:.2f}",
    ]
    if chain.deesser > 0:
        filters.append(f"deesser=i={chain.deesser:.3f}:m=0.5:f=0.5")
    filters.extend(
        [
            "acompressor=threshold={:.5f}:ratio={:.2f}:attack={:.2f}:release={:.2f}:makeup=1:knee=2.5:detection=rms".format(
                _db_to_linear(chain.compressor_threshold_db),
                chain.compressor_ratio,
                chain.compressor_attack_ms,
                chain.compressor_release_ms,
            ),
            f"alimiter=limit={_db_to_linear(chain.limiter_db):.5f}:attack=5:release=50:level=false",
            f"loudnorm=I={chain.loudness_lufs:.2f}:TP=-1.5:LRA=11",
        ]
    )
    return ",".join(filters)


def _studio_polish(
    input_path: Path,
    output_path: Path,
    chain: StudioChain,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
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
                "-af",
                _studio_filter_chain(chain),
                "-ar",
                "48000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(output_path),
            ],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"").decode("utf-8", "replace")
        raise RuntimeError(f"studio polish failed: {stderr[-1000:]}") from exc


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
            device=_device_for("transcribe"),
            compute_type=_compute_type_for("transcribe"),
            download_root="/root/.cache/whisperx",
        )
        logger.info("WhisperX ready")
    return _WHISPER_MODEL


def _get_raw_whisper_model(language: str = "en"):
    key = "ar" if language == "ar" else "default"
    model = _RAW_WHISPER_MODELS.get(key)
    if model is None:
        from faster_whisper import WhisperModel

        model_ref = "large-v3-turbo"
        if language == "ar":
            if Path(_ARABIC_WHISPER_MODEL).is_dir():
                model_ref = _ARABIC_WHISPER_MODEL
            else:
                logger.warning(
                    "Arabic dialect model missing at %s; using %s",
                    _ARABIC_WHISPER_MODEL,
                    model_ref,
                )
        logger.info("loading faster-whisper model for %s: %s", language, model_ref)
        model = WhisperModel(
            model_ref,
            device=_device_for("transcribe"),
            compute_type=_compute_type_for("transcribe"),
            download_root="/root/.cache/whisperx",
            local_files_only=True,
        )
        _RAW_WHISPER_MODELS[key] = model
        logger.info("faster-whisper model ready for %s", language)
    return model


def _get_align_model(language: str) -> tuple[Any, Any]:
    if language not in _ALIGN_MODELS:
        import whisperx

        logger.info("loading alignment model for %s", language)
        _ALIGN_MODELS[language] = whisperx.load_align_model(
            language_code=language,
            device=_device_for("transcribe"),
        )
        logger.info("alignment model ready for %s", language)
    return _ALIGN_MODELS[language]


def _script_ratio(text: str, language: str) -> float:
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return 1.0
    if language == "ar":
        matching = sum(
            1
            for char in letters
            if "\u0600" <= char <= "\u06ff"
            or "\ufb50" <= char <= "\ufdff"
            or "\ufe70" <= char <= "\ufeff"
        )
    else:
        matching = sum(1 for char in letters if char.isascii())
    return matching / len(letters)


def _confidence_from_logprob(value: float | None) -> float:
    if value is None:
        return 0.5
    return math.exp(min(0.0, max(-5.0, value)))


def _segment_words(
    segment: dict, source: dict
) -> list[tuple[float, float, str]]:
    words: list[tuple[float, float, str]] = []
    for word in segment.get("words", []):
        start = word.get("start")
        end = word.get("end")
        text = str(word.get("word", "")).strip()
        if start is None or end is None or not text:
            continue
        words.append((float(start), float(end), text))
    if words:
        return words

    text = str(source.get("text", "")).strip()
    if not text:
        return []
    try:
        start = float(segment.get("start", source.get("start")))
        end = float(segment.get("end", source.get("end")))
    except (TypeError, ValueError):
        return []
    return [(start, end, text)]


def _segment_confidence(
    segment: dict,
    source: dict,
    words: list[tuple[float, float, str]],
) -> float:
    scores = [
        float(word["score"])
        for word in segment.get("words", [])
        if isinstance(word.get("score"), (int, float))
    ]
    alignment_score = (
        max(0.0, min(1.0, sum(scores) / len(scores))) if scores else None
    )
    avg = source.get("avg_logprob", segment.get("avg_logprob"))
    if isinstance(avg, (int, float)):
        base = _confidence_from_logprob(float(avg))
        if alignment_score is None:
            return base
        return 0.6 * base + 0.4 * alignment_score
    return alignment_score if alignment_score is not None else 0.5


def _raw_segment_confidence(segment) -> float:
    base = _confidence_from_logprob(getattr(segment, "avg_logprob", None))
    probabilities = [
        float(word.probability)
        for word in (getattr(segment, "words", None) or [])
        if getattr(word, "probability", None) is not None
    ]
    if not probabilities:
        return base
    return 0.6 * base + 0.4 * max(
        0.0, min(1.0, sum(probabilities) / len(probabilities))
    )


def _transcribe_raw(
    wav_path: Path, language: str, dialect: str | None = None
) -> list[LanguageSegment]:
    import whisperx

    model = _get_raw_whisper_model(language)
    audio = whisperx.load_audio(str(wav_path))
    prompt = _dialect_prompt(dialect) if language == "ar" else None
    segments, _info = model.transcribe(
        audio,
        language=language,
        beam_size=5,
        condition_on_previous_text=False,
        word_timestamps=True,
        vad_filter=True,
        initial_prompt=prompt,
    )

    candidates: list[LanguageSegment] = []
    for segment in segments:
        text = str(segment.text).strip()
        words = [
            (
                float(word.start),
                float(word.end),
                str(word.word).strip(),
            )
            for word in (getattr(segment, "words", None) or [])
            if word.start is not None
            and word.end is not None
            and str(word.word).strip()
        ]
        if not words and text:
            words = [(float(segment.start), float(segment.end), text)]
        if not words:
            continue
        candidates.append(
            LanguageSegment(
                language=language,
                start=float(segment.start),
                end=float(segment.end),
                text=text or " ".join(word[2] for word in words),
                confidence=_raw_segment_confidence(segment),
                words=words,
            )
        )
    return candidates


def _transcribe_language(
    wav_path: Path, language: str, dialect: str | None = None
) -> list[LanguageSegment]:
    if language == "ar":
        try:
            return _transcribe_raw(wav_path, language, dialect)
        except Exception:
            logger.exception(
                "raw Arabic word-timestamp transcription failed; "
                "using WhisperX segment timestamps"
            )

    import whisperx

    model = _get_whisper_model()
    audio = whisperx.load_audio(str(wav_path))
    result = model.transcribe(audio, batch_size=8, language=language)
    segments = result.get("segments", [])
    aligned_segments = segments

    if language != "ar":
        try:
            align_model, metadata = _get_align_model(language)
            aligned = whisperx.align(
                segments,
                align_model,
                metadata,
                audio,
                device=_device_for("transcribe"),
                return_char_alignments=False,
            )
            aligned_segments = aligned.get("segments", segments)
        except Exception:
            logger.exception(
                "alignment failed for %s; using segment timestamps", language
            )

    candidates: list[LanguageSegment] = []
    for index, segment in enumerate(aligned_segments):
        source = segments[index] if index < len(segments) else segment
        words = _segment_words(segment, source)
        if not words:
            continue
        candidates.append(
            LanguageSegment(
                language=language,
                start=float(segment.get("start", words[0][0])),
                end=float(segment.get("end", words[-1][1])),
                text=" ".join(word[2] for word in words).strip(),
                confidence=_segment_confidence(segment, source, words),
                words=words,
            )
        )
    return candidates


def _transcriber_language_segments(
    transcript: Transcript, language: str
) -> list[LanguageSegment]:
    return [
        LanguageSegment(
            language=language,
            start=segment.start,
            end=segment.end,
            text=segment.text.strip(),
            confidence=0.75,
            words=[(segment.start, segment.end, segment.text.strip())],
        )
        for segment in transcript.segments
        if segment.text.strip()
    ]


def _overlapping(a: LanguageSegment, b: LanguageSegment) -> bool:
    overlap = max(0.0, min(a.end, b.end) - max(a.start, b.start))
    shorter = min(max(0.01, a.end - a.start), max(0.01, b.end - b.start))
    return overlap > 0.35 and overlap > 0.3 * shorter


def _merge_language_segments(
    candidates: list[LanguageSegment],
) -> list[LanguageSegment]:
    scored: list[tuple[float, LanguageSegment]] = []
    for candidate in candidates:
        text = candidate.text.strip()
        if not text:
            continue
        ratio = _script_ratio(text, candidate.language)
        if any(char.isalpha() for char in text) and ratio < 0.2:
            continue
        scored.append((candidate.confidence + 2.0 * ratio, candidate))

    scored.sort(key=lambda item: item[0], reverse=True)
    selected: list[LanguageSegment] = []
    for _score, candidate in scored:
        if any(_overlapping(candidate, other) for other in selected):
            continue
        selected.append(candidate)
    selected.sort(key=lambda item: item.start)
    return selected


def transcribe_languages(
    wav_path: Path,
    languages: list[str] | None = None,
    arabic_dialect: str | None = None,
    *,
    transcriber: Transcriber | None = None,
) -> Transcript:
    selected = list(dict.fromkeys(languages or ["en"]))
    candidates: list[LanguageSegment] = []
    for language in selected:
        if transcriber is not None:
            candidates.extend(
                _transcriber_language_segments(
                    transcriber(wav_path, language), language
                )
            )
        else:
            candidates.extend(
                _transcribe_language(wav_path, language, arabic_dialect)
            )

    if not candidates:
        return Transcript(speakers=[], segments=[])

    kept = (
        candidates
        if len(selected) == 1
        else _merge_language_segments(candidates)
    )
    words = [
        TranscriptSegment(
            speaker="SPEAKER_01",
            start=start,
            end=end,
            text=text,
        )
        for candidate in kept
        for start, end, text in candidate.words
        if text
    ]
    words.sort(key=lambda word: word.start)
    return Transcript(
        speakers=["SPEAKER_01"] if words else [],
        segments=words,
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
                env={
                    **os.environ,
                    "PARECUT_NEMOTRON_DEVICE": _device_for("diarize"),
                },
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
    sources = apply_model(
        model,
        wav[None],
        device=_device_for("separate_music"),
        progress=False,
    )[0]
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


def _artifact_label(
    artifact: dict[str, str],
    *,
    studio: bool = False,
    speaker: str | None = None,
) -> str:
    kind = artifact["kind"]
    if kind == "cleaned_audio":
        return "Denoised Audio (DeepFilterNet3)"
    if kind == "enhanced_audio":
        if studio:
            return "Studio Enhanced Audio (Resemble Enhance)"
        return "Enhanced Audio (Resemble Enhance)"
    if kind == "stem_music":
        return "Music Stem (Demucs)"
    if kind == "stem_dialogue":
        return "Dialogue Stem (Demucs)"
    if kind == "stem_speaker":
        if speaker:
            return f"{speaker.replace('SPEAKER_', 'Speaker ')} (gated)"
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
    polisher: StudioPolisher | None = None,
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

            if config.studio_chain.enabled:
                polished_path = workdir / "enhanced_polished.wav"
                if polisher is None:
                    _studio_polish(
                        enhanced_path,
                        polished_path,
                        config.studio_chain,
                    )
                else:
                    polisher(enhanced_path, polished_path, config.studio_chain)
                enhanced = polished_path.read_bytes()

        turns: list[SpeakerTurn] = []
        diarization_fallback = False
        diarization_error: str | None = None
        source_speaker = data.get("source_speaker")
        if config.transcribe or config.separate_speakers:
            if source_speaker:
                turns = [SpeakerTurn(str(source_speaker), 0.0, duration)]
            else:
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
            transcript = transcribe_languages(
                working_wav,
                config.transcription_languages,
                config.arabic_dialect,
                transcriber=transcriber,
            )
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
        speaker_labels: dict[str, str] = {}
        if config.separate_speakers:
            tracks = gated_speaker_tracks(working_wav, turns)
            speaker_keys = [
                artifact["key"]
                for artifact in data["expected_artifacts"]
                if artifact["kind"] == "stem_speaker"
            ]
            for key, speaker in zip(speaker_keys, sorted(tracks)):
                speaker_outputs[key] = tracks[speaker]
                speaker_labels[key] = speaker

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
            if artifact["kind"] in AUDIO_ARTIFACT_KINDS:
                content = _encode_audio(
                    content,
                    workdir,
                    artifact["format"],
                    Path(artifact["key"]).stem,
                )
            mime = MIME_TYPES.get(artifact["format"], "application/octet-stream")
            logger.info("uploading %s (%d bytes)", artifact["key"], len(content))
            _upload(client, outputs[artifact["key"]], content, mime)
            artifacts.append(
                {
                    "key": artifact["key"],
                    "kind": artifact["kind"],
                    "label": _artifact_label(
                        artifact,
                        studio=(
                            config.enhance and config.studio_chain.enabled
                        ),
                        speaker=speaker_labels.get(artifact["key"]),
                    ),
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
