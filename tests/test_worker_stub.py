import io
import subprocess
import sys
import types
import wave
from pathlib import Path

import pytest

from app.services.runpod import expected_artifacts
from parecut_engine.schemas import (
    PipelineConfig,
    StudioChain,
    Transcript,
    TranscriptSegment,
)
from runpod_app.worker import (
    LanguageSegment,
    SpeakerTurn,
    _device_for,
    _encode_audio,
    _gpu_stages,
    _merge_language_segments,
    _stage_allows_gpu,
    _studio_filter_chain,
    handler,
    transcribe_languages,
)
from tests.helpers import make_wav

SOURCE = make_wav(2.0)


class FakeResponse:
    status_code = 200

    def __init__(self, content: bytes = b"") -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


class FakeClient:
    def __init__(self) -> None:
        self.puts: list[tuple[str, bytes, str]] = []

    def get(self, url: str, follow_redirects: bool = True) -> FakeResponse:
        assert url == "https://source.example/clip.wav"
        return FakeResponse(SOURCE)

    def put(self, url: str, content: bytes, headers: dict[str, str]) -> FakeResponse:
        self.puts.append((url, content, headers["content-type"]))
        return FakeResponse()


def fake_denoiser(input_path: Path, output_path: Path) -> None:
    with wave.open(str(input_path)) as reader:
        assert reader.getframerate() == 48000
        assert reader.getnchannels() == 1
    output_path.write_bytes(input_path.read_bytes())


ENHANCED_AUDIO = make_wav(1.0)


def fake_enhancer(input_path: Path, output_path: Path, mix: float) -> None:
    with wave.open(str(input_path)) as reader:
        assert reader.getframerate() == 48000
        assert reader.getnchannels() == 1
    assert 0 <= mix <= 1
    output_path.write_bytes(ENHANCED_AUDIO)


def fake_polisher(
    input_path: Path,
    output_path: Path,
    chain: StudioChain,
) -> None:
    assert chain.enabled
    output_path.write_bytes(input_path.read_bytes())


def fake_transcriber(wav_path: Path, language: str) -> Transcript:
    return Transcript(
        speakers=["SPEAKER_01"],
        segments=[
            TranscriptSegment(
                speaker="SPEAKER_01",
                start=0.2,
                end=0.8,
                text="Hello from the presenter.",
            ),
            TranscriptSegment(
                speaker="SPEAKER_01",
                start=1.0,
                end=1.6,
                text="And this is the second line.",
            ),
        ],
    )


def fake_diarizer(wav_path: Path) -> list[SpeakerTurn]:
    return [
        SpeakerTurn("SPEAKER_00", 0.0, 1.0),
        SpeakerTurn("SPEAKER_01", 1.0, 2.0),
    ]


def fake_separator(wav_path: Path, workdir: Path) -> tuple[bytes, bytes]:
    return b"music-stem", b"dialogue-stem"


def make_job(config: PipelineConfig | None = None) -> dict:
    # Most stub tests assert WAV passthrough; format-specific tests opt in.
    config = config or PipelineConfig(audio_format="wav")
    artifacts = expected_artifacts("job-1", config)
    return {
        "input": {
            "job_id": "job-1",
            "source_url": "https://source.example/clip.wav",
            "source_filename": "clip.wav",
            "duration_seconds": 2.0,
            "sample_rate": 48000,
            "fps": "25",
            "pipeline": config.model_dump(),
            "outputs": {
                artifact["key"]: f"https://upload.example/{index}"
                for index, artifact in enumerate(artifacts)
            },
            "expected_artifacts": artifacts,
        }
    }


def _uploaded(client: FakeClient, job: dict) -> dict[str, bytes]:
    outputs = job["input"]["outputs"]
    key_by_url = {outputs[key]: key for key in outputs}
    return {key_by_url[url]: content for url, content, _ in client.puts}


def _frames(data: bytes) -> int:
    with wave.open(io.BytesIO(data)) as reader:
        return reader.getnframes()


def test_gpu_stages_default_uses_the_fast_stages(monkeypatch):
    monkeypatch.delenv("PARECUT_GPU_STAGES", raising=False)
    assert _gpu_stages() == {
        "noise_reduction",
        "enhance",
        "separate_music",
    }
    assert _stage_allows_gpu("enhance") is True
    assert _stage_allows_gpu("transcribe") is False
    assert _stage_allows_gpu("diarize") is False


def test_gpu_stages_reads_csv(monkeypatch):
    monkeypatch.setenv("PARECUT_GPU_STAGES", "enhance,separate_music")
    assert _gpu_stages() == {"enhance", "separate_music"}


def test_device_for_disabled_stage_is_cpu(monkeypatch):
    monkeypatch.setenv("PARECUT_GPU_STAGES", "enhance")
    assert _device_for("separate_music") == "cpu"


def test_diarize_follows_transcribe_stage(monkeypatch):
    monkeypatch.setenv("PARECUT_GPU_STAGES", "transcribe")
    assert _stage_allows_gpu("diarize") is True


def test_diarize_is_excluded_when_its_stages_are(monkeypatch):
    monkeypatch.setenv("PARECUT_GPU_STAGES", "enhance")
    assert _stage_allows_gpu("diarize") is False


def test_encode_audio_failure_raises(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "ffmpeg", stderr=b"boom")

    monkeypatch.setattr("runpod_app.worker.subprocess.run", fail)
    with pytest.raises(RuntimeError, match="mp3 encoding failed"):
        _encode_audio(make_wav(0.5), tmp_path, "mp3", "tone")


def test_handler_uploads_nothing_when_encoding_fails(monkeypatch):
    job = make_job(
        PipelineConfig(
            audio_format="wav",
            noise_reduction=True,
            enhance=False,
            separate_music=False,
            separate_speakers=False,
            transcribe=False,
            rough_cut=False,
        )
    )
    job["input"]["expected_artifacts"] = [
        artifact
        for artifact in job["input"]["expected_artifacts"]
        if artifact["kind"] == "cleaned_audio"
    ]
    job["input"]["outputs"] = {
        artifact["key"]: f"https://upload.example/{index}"
        for index, artifact in enumerate(job["input"]["expected_artifacts"])
    }
    client = FakeClient()

    def fail(*args, **kwargs):
        raise RuntimeError("mp3 encoding failed")

    monkeypatch.setattr("runpod_app.worker._encode_audio", fail)
    with pytest.raises(RuntimeError, match="mp3 encoding failed"):
        handler(job, client=client, denoiser=fake_denoiser)
    assert client.puts == []


def test_encode_audio_writes_mp3(tmp_path):
    encoded = _encode_audio(make_wav(0.5), tmp_path, "mp3", "tone")
    assert encoded[:3] == b"ID3" or (
        encoded[0] == 0xFF and (encoded[1] & 0xE0) == 0xE0
    )


def test_encode_audio_passthrough_wav(tmp_path):
    payload = b"RIFF....WAVE"
    assert _encode_audio(payload, tmp_path, "wav", "tone") == payload


def test_worker_uploads_mp3_when_selected():
    config = PipelineConfig(
        audio_format="mp3",
        separate_music=True,
        transcribe=False,
        rough_cut=False,
    )
    job = make_job(config)
    client = FakeClient()

    def real_separator(wav_path: Path, workdir: Path) -> tuple[bytes, bytes]:
        return make_wav(1.0), make_wav(1.0)

    handler(
        job,
        client=client,
        denoiser=fake_denoiser,
        enhancer=fake_enhancer,
        polisher=fake_polisher,
        transcriber=fake_transcriber,
        diarizer=fake_diarizer,
        separator=real_separator,
    )

    audio_puts = [
        (content, mime)
        for _url, content, mime in client.puts
        if mime.startswith("audio/")
    ]
    assert audio_puts
    assert all(mime == "audio/mpeg" for _content, mime in audio_puts)

    uploaded = _uploaded(client, job)
    music_key = next(
        artifact["key"]
        for artifact in job["input"]["expected_artifacts"]
        if artifact["kind"] == "stem_music"
    )
    music = uploaded[music_key]
    assert music[:3] == b"ID3" or (music[0] == 0xFF and (music[1] & 0xE0) == 0xE0)


def test_worker_runs_real_pipeline_stages():
    job = make_job()
    client = FakeClient()

    result = handler(
        job,
        client=client,
        denoiser=fake_denoiser,
        enhancer=fake_enhancer,
        polisher=fake_polisher,
        transcriber=fake_transcriber,
        diarizer=fake_diarizer,
        separator=fake_separator,
    )

    uploaded = _uploaded(client, job)
    expected = job["input"]["expected_artifacts"]
    cleaned = next(a["key"] for a in expected if a["kind"] == "cleaned_audio")
    enhanced = next(a["key"] for a in expected if a["kind"] == "enhanced_audio")
    music = next(a["key"] for a in expected if a["kind"] == "stem_music")
    dialogue = next(a["key"] for a in expected if a["kind"] == "stem_dialogue")
    speaker_keys = [a["key"] for a in expected if a["kind"] == "stem_speaker"]

    assert uploaded[cleaned].startswith(b"RIFF")
    assert uploaded[enhanced] == ENHANCED_AUDIO
    assert uploaded[enhanced] != uploaded[cleaned]
    assert uploaded[music] == b"music-stem"
    assert uploaded[dialogue] == b"dialogue-stem"
    assert _frames(uploaded[speaker_keys[0]]) == _frames(uploaded[cleaned])
    assert _frames(uploaded[speaker_keys[1]]) == _frames(uploaded[cleaned])
    assert speaker_keys[2] not in uploaded

    before_json = uploaded[
        next(
            a["key"]
            for a in expected
            if a["kind"] == "transcript_before" and a["format"] == "json"
        )
    ].decode()
    assert "Hello from the presenter." in before_json
    assert "SPEAKER_00" in before_json
    assert "SPEAKER_01" in before_json

    rough = uploaded[next(a["key"] for a in expected if a["kind"] == "rough_cut_md")]
    assert b"PARECUT DETAILED TRANSCRIPTION" in rough
    assert b"SPEAKER_00" in rough
    assert b"Hello from the presenter." in rough

    labels = {artifact["kind"]: artifact["label"] for artifact in result["artifacts"]}
    speaker_labels = [
        artifact["label"]
        for artifact in result["artifacts"]
        if artifact["kind"] == "stem_speaker"
    ]
    assert labels["cleaned_audio"] == "Denoised Audio (DeepFilterNet3)"
    assert labels["enhanced_audio"] == "Studio Enhanced Audio (Resemble Enhance)"
    assert labels["stem_music"] == "Music Stem (Demucs)"
    assert speaker_labels == ["Speaker 00 (gated)", "Speaker 01 (gated)"]
    assert labels["transcript_before"] == "Transcript (Before Cut)"
    assert result["speaker_roles"] == {
        "SPEAKER_00": "presenter",
        "SPEAKER_01": "presenter",
    }
    assert result["diarization"] == {
        "fallback": False,
        "error": None,
        "turns": 2,
        "speakers": ["SPEAKER_00", "SPEAKER_01"],
    }
    assert result["stages"]["noise_reduction"]["status"] == "completed"


def test_worker_skips_disabled_models():
    config = PipelineConfig(
        noise_reduction=False,
        enhance=False,
        separate_music=False,
        separate_speakers=False,
        transcribe=True,
        rough_cut=False,
    )
    job = make_job(config)
    client = FakeClient()

    def fail_denoiser(input_path: Path, output_path: Path) -> None:
        raise AssertionError("denoiser should not run")

    def fail_enhancer(input_path: Path, output_path: Path, mix: float) -> None:
        raise AssertionError("enhancer should not run")

    def fail_separator(wav_path: Path, workdir: Path) -> tuple[bytes, bytes]:
        raise AssertionError("separator should not run")

    result = handler(
        job,
        client=client,
        denoiser=fail_denoiser,
        enhancer=fail_enhancer,
        transcriber=fake_transcriber,
        diarizer=fake_diarizer,
        separator=fail_separator,
    )

    kinds = [artifact["kind"] for artifact in result["artifacts"]]
    assert kinds == ["transcript_before"] * 4
    assert "noise_reduction" not in result["stages"]
    assert "transcribe" in result["stages"]


def test_worker_falls_back_to_one_speaker_when_diarization_fails():
    job = make_job()
    client = FakeClient()

    def broken_diarizer(wav_path: Path) -> list[SpeakerTurn]:
        raise RuntimeError("diarization unavailable")

    result = handler(
        job,
        client=client,
        denoiser=fake_denoiser,
        enhancer=fake_enhancer,
        transcriber=fake_transcriber,
        diarizer=broken_diarizer,
        separator=fake_separator,
    )

    assert result["speaker_roles"] == {"SPEAKER_01": "presenter"}
    assert result["diarization"]["fallback"] is True
    assert result["diarization"]["error"] == "RuntimeError: diarization unavailable"
    speaker_artifacts = [
        artifact for artifact in result["artifacts"] if artifact["kind"] == "stem_speaker"
    ]
    assert len(speaker_artifacts) == 1


def test_enhance_only_runs_after_denoise_and_uses_mix():
    config = PipelineConfig(
        noise_reduction=False,
        enhance=True,
        separate_music=False,
        separate_speakers=False,
        transcribe=False,
        rough_cut=False,
        enhance_mix=0.65,
        audio_format="wav",
        studio_chain=StudioChain(
            body_db=3.5,
            presence_db=-1.0,
            compressor_ratio=3.2,
            loudness_lufs=-14.0,
        ),
    )
    job = make_job(config)
    client = FakeClient()
    mixes: list[float] = []
    chains: list[StudioChain] = []

    def enhancer(input_path: Path, output_path: Path, mix: float) -> None:
        fake_enhancer(input_path, output_path, mix)
        mixes.append(mix)

    def polisher(
        input_path: Path,
        output_path: Path,
        chain: StudioChain,
    ) -> None:
        fake_polisher(input_path, output_path, chain)
        chains.append(chain)

    result = handler(
        job,
        client=client,
        denoiser=fake_denoiser,
        enhancer=enhancer,
        polisher=polisher,
    )

    expected = job["input"]["expected_artifacts"]
    enhanced_key = next(
        artifact["key"]
        for artifact in expected
        if artifact["kind"] == "enhanced_audio"
    )
    uploaded = _uploaded(client, job)

    assert mixes == [0.65]
    assert chains[0].body_db == 3.5
    assert chains[0].presence_db == -1.0
    assert chains[0].compressor_ratio == 3.2
    assert uploaded[enhanced_key] == ENHANCED_AUDIO
    assert [artifact["kind"] for artifact in result["artifacts"]] == [
        "enhanced_audio"
    ]
    assert result["artifacts"][0]["label"] == (
        "Studio Enhanced Audio (Resemble Enhance)"
    )
    assert result["stages"]["enhance"]["status"] == "completed"


def test_enhance_skips_studio_when_disabled():
    config = PipelineConfig(
        noise_reduction=False,
        enhance=True,
        separate_music=False,
        separate_speakers=False,
        transcribe=False,
        rough_cut=False,
        studio_chain=StudioChain(enabled=False),
    )
    job = make_job(config)
    client = FakeClient()

    def fail_polisher(
        input_path: Path,
        output_path: Path,
        chain: StudioChain,
    ) -> None:
        raise AssertionError("studio polish should not run")

    result = handler(
        job,
        client=client,
        denoiser=fake_denoiser,
        enhancer=fake_enhancer,
        polisher=fail_polisher,
    )

    assert [artifact["kind"] for artifact in result["artifacts"]] == [
        "enhanced_audio"
    ]
    assert result["artifacts"][0]["label"] == "Enhanced Audio (Resemble Enhance)"


def test_studio_filter_chain_matches_controls():
    chain = StudioChain(
        highpass_hz=80,
        body_db=2.5,
        mud_db=-1.5,
        presence_db=3.0,
        deesser=0.4,
        compressor_threshold_db=-20,
        compressor_ratio=3.0,
        compressor_attack_ms=12,
        compressor_release_ms=180,
        limiter_db=-1.5,
        loudness_lufs=-14,
    )
    filters = _studio_filter_chain(chain)

    assert "highpass=f=80" in filters
    assert "equalizer=f=120:t=q:w=1:g=2.50" in filters
    assert "equalizer=f=320:t=q:w=1:g=-1.50" in filters
    assert "equalizer=f=3500:t=q:w=1:g=3.00" in filters
    assert "deesser=i=0.400" in filters
    assert "acompressor=threshold=0.10000:ratio=3.00" in filters
    assert "attack=12.00:release=180.00" in filters
    assert "alimiter=limit=0.84140" in filters
    assert "loudnorm=I=-14.00" in filters


def test_transcribe_languages_merges_english_and_arabic():
    def mixed_transcriber(wav_path: Path, language: str) -> Transcript:
        if language == "ar":
            return Transcript(
                speakers=["SPEAKER_01"],
                segments=[
                    TranscriptSegment(
                        speaker="SPEAKER_01",
                        start=1.0,
                        end=1.6,
                        text="هذا اختبار عربي.",
                    ),
                    TranscriptSegment(
                        speaker="SPEAKER_01",
                        start=1.8,
                        end=2.2,
                        text="مرحبا بالعالم.",
                    ),
                ],
            )
        return Transcript(
            speakers=["SPEAKER_01"],
            segments=[
                TranscriptSegment(
                    speaker="SPEAKER_01",
                    start=0.2,
                    end=0.8,
                    text="Hello from the presenter.",
                ),
                TranscriptSegment(
                    speaker="SPEAKER_01",
                    start=2.4,
                    end=2.9,
                    text="Back in English.",
                ),
            ],
        )

    transcript = transcribe_languages(
        Path("clip.wav"),
        ["en", "ar"],
        transcriber=mixed_transcriber,
    )
    text = " ".join(segment.text for segment in transcript.segments)
    assert "Hello from the presenter." in text
    assert "هذا اختبار عربي." in text
    assert "مرحبا بالعالم." in text
    assert "Back in English." in text
    assert [segment.start for segment in transcript.segments] == sorted(
        segment.start for segment in transcript.segments
    )


def test_merge_language_segments_filters_wrong_script_and_prefers_confidence():
    candidates = [
        LanguageSegment(
            language="en",
            start=0.0,
            end=2.0,
            text="Hello there",
            confidence=0.8,
            words=[(0.0, 1.0, "Hello")],
        ),
        LanguageSegment(
            language="ar",
            start=0.0,
            end=2.0,
            text="مرحبا بكم",
            confidence=0.9,
            words=[(0.0, 2.0, "مرحبا")],
        ),
        LanguageSegment(
            language="en",
            start=3.0,
            end=4.0,
            text="مرحبا",
            confidence=0.99,
            words=[(3.0, 4.0, "مرحبا")],
        ),
    ]
    selected = _merge_language_segments(candidates)
    assert [segment.language for segment in selected] == ["ar"]
    assert selected[0].text == "مرحبا بكم"


def test_worker_transcribes_selected_languages_into_before_json():
    config = PipelineConfig(
        noise_reduction=False,
        enhance=False,
        separate_music=False,
        separate_speakers=False,
        transcribe=True,
        rough_cut=True,
        transcription_languages=["en", "ar"],
    )
    job = make_job(config)
    client = FakeClient()

    def mixed_transcriber(wav_path: Path, language: str) -> Transcript:
        if language == "ar":
            return Transcript(
                speakers=["SPEAKER_01"],
                segments=[
                    TranscriptSegment(
                        speaker="SPEAKER_01",
                        start=1.0,
                        end=1.6,
                        text="مرحبا بالعالم.",
                    )
                ],
            )
        return Transcript(
            speakers=["SPEAKER_01"],
            segments=[
                TranscriptSegment(
                    speaker="SPEAKER_01",
                    start=0.2,
                    end=0.8,
                    text="Hello from the presenter.",
                )
            ],
        )

    result = handler(
        job,
        client=client,
        transcriber=mixed_transcriber,
        diarizer=fake_diarizer,
    )
    uploaded = _uploaded(client, job)
    before_json = uploaded[
        next(
            artifact["key"]
            for artifact in job["input"]["expected_artifacts"]
            if artifact["kind"] == "transcript_before"
            and artifact["format"] == "json"
        )
    ].decode()
    assert "Hello from the presenter." in before_json
    assert "مرحبا بالعالم." in before_json
    assert result["stages"]["transcribe"]["status"] == "completed"


def test_deepfilternet_chunks_long_audio(monkeypatch, tmp_path):
    torch = pytest.importorskip("torch")

    import runpod_app.worker as worker

    calls: list[int] = []
    saved: dict[str, object] = {}

    class FakeState:
        def sr(self) -> int:
            return 1000

    def fake_load_audio(path: str, sr: int):
        return torch.zeros(1, 5000), sr

    def fake_enhance(model, state, audio):
        calls.append(int(audio.shape[-1]))
        return audio

    def fake_save_audio(path: str, audio, sr: int) -> None:
        saved["audio"] = audio

    fake_module = types.ModuleType("df.enhance")
    fake_module.enhance = fake_enhance
    fake_module.load_audio = fake_load_audio
    fake_module.save_audio = fake_save_audio
    package = types.ModuleType("df")
    package.enhance = fake_module
    monkeypatch.setitem(sys.modules, "df", package)
    monkeypatch.setitem(sys.modules, "df.enhance", fake_module)

    monkeypatch.setattr(worker, "_get_model", lambda: (object(), FakeState()))
    monkeypatch.setattr(worker, "DF_CHUNK_SECONDS", 2)
    monkeypatch.setattr(worker, "DF_OVERLAP_SECONDS", 0.2)

    worker._deepfilternet(tmp_path / "in.wav", tmp_path / "out.wav")

    assert calls == [2000, 2000, 1400]
    assert saved["audio"].shape[-1] == 5000


def test_merge_words_splits_on_pause_gaps_and_preserves_word_timestamps():
    from parecut_engine.schemas import TranscriptWord
    from runpod_app.worker import merge_words

    raw = Transcript(
        speakers=["SPEAKER_01"],
        segments=[
            TranscriptSegment(
                speaker="SPEAKER_01",
                start=0.5,
                end=0.8,
                text="Hello",
                words=[TranscriptWord(start=0.5, end=0.8, text="Hello")],
            ),
            TranscriptSegment(
                speaker="SPEAKER_01",
                start=0.85,
                end=1.1,
                text="world",
                words=[TranscriptWord(start=0.85, end=1.1, text="world")],
            ),
            # 1.9s pause — must not merge across silence
            TranscriptSegment(
                speaker="SPEAKER_01",
                start=3.0,
                end=3.4,
                text="after",
                words=[TranscriptWord(start=3.0, end=3.4, text="after")],
            ),
            TranscriptSegment(
                speaker="SPEAKER_01",
                start=3.45,
                end=3.9,
                text="pause",
                words=[TranscriptWord(start=3.45, end=3.9, text="pause")],
            ),
        ],
    )

    merged = merge_words(raw)
    assert len(merged.segments) == 2
    assert merged.segments[0].text == "Hello world"
    assert merged.segments[0].start == 0.5
    assert merged.segments[0].end == 1.1
    assert [(w.start, w.end, w.text) for w in merged.segments[0].words] == [
        (0.5, 0.8, "Hello"),
        (0.85, 1.1, "world"),
    ]
    assert merged.segments[1].text == "after pause"
    assert merged.segments[1].start == 3.0
    assert merged.segments[1].end == 3.9


def test_assign_speakers_uses_nearest_turn_when_word_falls_in_gap():
    from runpod_app.worker import assign_speakers

    turns = [
        SpeakerTurn("SPEAKER_00", 0.0, 2.0),
        SpeakerTurn("SPEAKER_01", 5.0, 8.0),
    ]
    transcript = Transcript(
        speakers=["SPEAKER_01"],
        segments=[
            TranscriptSegment(speaker="SPEAKER_01", start=8.05, end=8.3, text="trailing"),
        ],
    )
    assigned = assign_speakers(transcript, turns)
    assert assigned.segments[0].speaker == "SPEAKER_01"


def test_normalize_for_transcription_creates_16k_copy_without_mutating_source(tmp_path):
    import struct
    import math
    from runpod_app.worker import _normalize_for_transcription

    src = tmp_path / "working.wav"
    sr = 48000
    # 1s loud 440Hz tone followed by 1s very quiet (-30dB) 440Hz tone
    loud = [int(20000 * math.sin(2 * math.pi * 440 * i / sr)) for i in range(sr)]
    quiet = [int(600 * math.sin(2 * math.pi * 440 * i / sr)) for i in range(sr)]
    samples = loud + quiet
    with wave.open(str(src), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sr)
        writer.writeframes(struct.pack(f"<{len(samples)}h", *samples))

    original_bytes = src.read_bytes()
    out = tmp_path / "norm.wav"
    result = _normalize_for_transcription(src, out)

    assert result == out
    assert out.exists()
    assert src.read_bytes() == original_bytes
    with wave.open(str(out), "rb") as reader:
        assert reader.getframerate() == 16000
        assert reader.getnchannels() == 1
        frames = reader.readframes(reader.getnframes())
    norm_samples = struct.unpack(f"<{len(frames) // 2}h", frames)
    half = len(norm_samples) // 2
    quiet_peak_after = max(abs(s) for s in norm_samples[half:])
    assert quiet_peak_after > 1500


def test_normalize_for_transcription_falls_back_on_ffmpeg_error(tmp_path, monkeypatch):
    from runpod_app.worker import _normalize_for_transcription

    src = tmp_path / "working.wav"
    src.write_bytes(make_wav(0.5))

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "ffmpeg", stderr=b"filter error")

    monkeypatch.setattr("runpod_app.worker.subprocess.run", fail)
    result = _normalize_for_transcription(src, tmp_path / "norm.wav")
    assert result == src


def test_transcribe_languages_normalizes_temp_copy_once_and_cleans_up(
    tmp_path, monkeypatch
):
    src = tmp_path / "working.wav"
    src.write_bytes(make_wav(0.5))
    original_bytes = src.read_bytes()

    seen_paths: list[Path] = []
    norm_calls: list[tuple[Path, Path]] = []

    def fake_normalize(input_path: Path, output_path: Path) -> Path:
        norm_calls.append((input_path, output_path))
        output_path.write_bytes(b"normalized-temp")
        return output_path

    def fake_transcribe_lang(
        wav_path: Path, language: str, dialect: str | None = None
    ) -> list[LanguageSegment]:
        seen_paths.append(wav_path)
        assert wav_path.exists()
        assert wav_path != src
        text = "hello" if language == "en" else "مرحبا"
        start = 0.0 if language == "en" else 1.0
        return [
            LanguageSegment(
                language=language,
                start=start,
                end=start + 0.5,
                text=text,
                confidence=0.9,
                words=[(start, start + 0.5, text)],
            )
        ]

    monkeypatch.setattr(
        "runpod_app.worker._normalize_for_transcription", fake_normalize
    )
    monkeypatch.setattr(
        "runpod_app.worker._transcribe_language", fake_transcribe_lang
    )

    transcript = transcribe_languages(src, ["en", "ar"])
    assert len(norm_calls) == 1
    assert norm_calls[0][0] == src
    assert len(seen_paths) == 2
    assert seen_paths[0] == seen_paths[1] == norm_calls[0][1]
    assert not norm_calls[0][1].exists()
    assert src.read_bytes() == original_bytes
    assert len(transcript.segments) == 2


def test_transcribe_raw_uses_gentler_silero_vad_parameters(tmp_path, monkeypatch):
    from runpod_app.worker import _transcribe_raw

    captured: dict[str, object] = {}

    class FakeWord:
        start = 0.1
        end = 0.4
        word = "مرحبا"
        probability = 0.9

    class FakeSegment:
        start = 0.1
        end = 0.4
        text = "مرحبا"
        avg_logprob = -0.2
        words = [FakeWord()]

    class FakeModel:
        def transcribe(self, audio, **kwargs):
            captured.update(kwargs)
            return [FakeSegment()], None

    fake_whisperx = types.ModuleType("whisperx")
    fake_whisperx.load_audio = lambda path: b"pcm"
    monkeypatch.setitem(sys.modules, "whisperx", fake_whisperx)
    monkeypatch.setattr(
        "runpod_app.worker._get_raw_whisper_model", lambda language: FakeModel()
    )

    segments = _transcribe_raw(tmp_path / "norm.wav", "ar", "egyptian")
    assert len(segments) == 1
    assert captured["vad_filter"] is True
    assert captured["vad_parameters"] == {
        "threshold": 0.35,
        "min_silence_duration_ms": 500,
    }


def test_transcribe_language_skips_align_when_segments_empty(tmp_path, monkeypatch):
    from runpod_app.worker import _transcribe_language

    class FakeModel:
        def transcribe(self, audio, **kwargs):
            return {"segments": []}

    fake_whisperx = types.ModuleType("whisperx")
    fake_whisperx.load_audio = lambda path: b"pcm"

    def fail_align(*args, **kwargs):
        raise AssertionError("align should not be called for empty segments")

    fake_whisperx.align = fail_align
    monkeypatch.setitem(sys.modules, "whisperx", fake_whisperx)
    monkeypatch.setattr("runpod_app.worker._get_whisper_model", lambda: FakeModel())

    assert _transcribe_language(tmp_path / "norm.wav", "en") == []


def test_redact_url_strips_query_string():
    from runpod_app.worker import _redact_url

    url = "https://r2.example.com/bucket/clip.wav?X-Amz-Signature=secret&X-Amz-Expires=300"
    assert _redact_url(url) == "https://r2.example.com/bucket/clip.wav"
    assert _redact_url("https://r2.example.com/bucket/clip.wav") == (
        "https://r2.example.com/bucket/clip.wav"
    )


def test_gated_speaker_tracks_handles_unsafe_speaker_names_in_memory(tmp_path):
    from runpod_app.worker import gated_speaker_tracks

    wav_path = tmp_path / "working.wav"
    wav_path.write_bytes(make_wav(1.0))
    tracks = gated_speaker_tracks(
        wav_path, [SpeakerTurn("../weird:speaker/01", 0.0, 0.5)]
    )
    assert "../weird:speaker/01" in tracks
    assert _frames(tracks["../weird:speaker/01"]) == _frames(wav_path.read_bytes())
    assert list(tmp_path.iterdir()) == [wav_path]


def test_encode_audio_cleans_up_temp_files(tmp_path):
    encoded = _encode_audio(make_wav(0.5), tmp_path, "mp3", "cleanup_test")
    assert encoded
    assert list(tmp_path.iterdir()) == []


def test_convert_to_wav_and_studio_polish_wrap_oserror(tmp_path, monkeypatch):
    from runpod_app.worker import _convert_to_wav, _studio_polish

    def fail(*args, **kwargs):
        raise OSError("ffmpeg not found")

    monkeypatch.setattr("runpod_app.worker.subprocess.run", fail)
    with pytest.raises(RuntimeError, match="ffmpeg conversion failed"):
        _convert_to_wav(tmp_path / "in.wav", tmp_path / "out.wav")
    with pytest.raises(RuntimeError, match="studio polish failed"):
        _studio_polish(tmp_path / "in.wav", tmp_path / "out.wav", StudioChain())


def test_studio_filter_chain_includes_agate_when_enabled():
    enabled = _studio_filter_chain(
        StudioChain(
            gate_enabled=True,
            gate_threshold_db=-40.0,
            gate_range_db=-12.0,
            gate_ratio=2.0,
        )
    )
    assert "agate=threshold=0.01000:ratio=2.00:range=0.25119:attack=10:release=180:knee=3:detection=rms" in enabled

    disabled = _studio_filter_chain(StudioChain(gate_enabled=False))
    assert "agate=" not in disabled

    zero_range = _studio_filter_chain(StudioChain(gate_enabled=True, gate_range_db=0.0))
    assert "agate=" not in zero_range


def test_handler_runs_dereverb_before_enhancer_and_skips_when_disabled():
    dereverbed_audio = make_wav(1.0)
    seen_inputs: list[bytes] = []

    def fake_dereverber(input_path: Path, output_path: Path) -> None:
        output_path.write_bytes(dereverbed_audio)

    def checking_enhancer(input_path: Path, output_path: Path, mix: float) -> None:
        seen_inputs.append(input_path.read_bytes())
        output_path.write_bytes(ENHANCED_AUDIO)

    on_cfg = PipelineConfig(
        noise_reduction=False,
        enhance=True,
        dereverb=True,
        separate_music=False,
        separate_speakers=False,
        transcribe=False,
        rough_cut=False,
        studio_chain=StudioChain(enabled=False),
    )
    handler(
        make_job(on_cfg),
        client=FakeClient(),
        denoiser=fake_denoiser,
        dereverber=fake_dereverber,
        enhancer=checking_enhancer,
    )
    assert seen_inputs == [dereverbed_audio]

    seen_inputs.clear()

    def fail_dereverber(input_path: Path, output_path: Path) -> None:
        raise AssertionError("dereverber should not run when disabled")

    off_cfg = PipelineConfig(
        noise_reduction=False,
        enhance=True,
        dereverb=False,
        separate_music=False,
        separate_speakers=False,
        transcribe=False,
        rough_cut=False,
        studio_chain=StudioChain(enabled=False),
    )
    handler(
        make_job(off_cfg),
        client=FakeClient(),
        denoiser=fake_denoiser,
        dereverber=fail_dereverber,
        enhancer=checking_enhancer,
    )
    assert seen_inputs and seen_inputs[0] != dereverbed_audio

