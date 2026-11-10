import io
import wave
from pathlib import Path

from app.services.runpod import expected_artifacts
from parecut_engine.schemas import PipelineConfig, Transcript, TranscriptSegment
from runpod_app.worker import SpeakerTurn, handler
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


def fake_transcriber(wav_path: Path) -> Transcript:
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
    config = config or PipelineConfig()
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


def test_worker_runs_real_pipeline_stages():
    job = make_job()
    client = FakeClient()

    result = handler(
        job,
        client=client,
        denoiser=fake_denoiser,
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
    assert uploaded[enhanced] == uploaded[cleaned]
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
    assert b"PARECUT ROUGH-CUT SPECIFICATION" in rough
    assert b"SPEAKER_00" in rough

    labels = {artifact["kind"]: artifact["label"] for artifact in result["artifacts"]}
    speaker_labels = [
        artifact["label"]
        for artifact in result["artifacts"]
        if artifact["kind"] == "stem_speaker"
    ]
    assert labels["cleaned_audio"] == "Denoised Audio (DeepFilterNet3)"
    assert labels["stem_music"] == "Music Stem (Demucs)"
    assert speaker_labels == ["Speaker 01 (gated)", "Speaker 02 (gated)"]
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

    def fail_separator(wav_path: Path, workdir: Path) -> tuple[bytes, bytes]:
        raise AssertionError("separator should not run")

    result = handler(
        job,
        client=client,
        denoiser=fail_denoiser,
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
