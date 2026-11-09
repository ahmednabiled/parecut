import wave
from pathlib import Path

from app.services.runpod import expected_artifacts
from parecut_engine.schemas import PipelineConfig
from runpod_app.worker import handler
from tests.helpers import make_wav

SOURCE = make_wav(0.5)
DENOISED = b"denoised-audio-bytes"


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
    output_path.write_bytes(DENOISED)


def make_job(config: PipelineConfig | None = None) -> dict:
    config = config or PipelineConfig()
    artifacts = expected_artifacts("job-1", config)
    return {
        "input": {
            "job_id": "job-1",
            "source_url": "https://source.example/clip.wav",
            "source_filename": "clip.wav",
            "duration_seconds": 24.72,
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


def test_worker_denoises_cleaned_and_enhanced_artifacts():
    job = make_job()
    client = FakeClient()

    result = handler(job, client=client, denoiser=fake_denoiser)

    expected = job["input"]["expected_artifacts"]
    assert {artifact["key"] for artifact in result["artifacts"]} == {
        artifact["key"] for artifact in expected
    }
    uploaded = _uploaded(client, job)
    cleaned = next(a["key"] for a in expected if a["kind"] == "cleaned_audio")
    enhanced = next(a["key"] for a in expected if a["kind"] == "enhanced_audio")
    stem = next(a["key"] for a in expected if a["kind"] == "stem_music")

    assert uploaded[cleaned] == DENOISED
    assert uploaded[enhanced] == DENOISED
    assert uploaded[stem] == SOURCE

    labels = {artifact["kind"]: artifact["label"] for artifact in result["artifacts"]}
    assert labels["cleaned_audio"] == "Denoised Audio (DeepFilterNet3)"
    assert labels["enhanced_audio"] == "Denoised Audio (Enhancement pending)"
    assert labels["stem_music"].startswith("Stub — ")
    assert result["stages"]["noise_reduction"]["status"] == "completed"
    assert result["speaker_roles"] == {
        "SPEAKER_01": "presenter",
        "SPEAKER_02": "presenter",
    }


def test_worker_skips_denoise_when_audio_stages_are_disabled():
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

    result = handler(job, client=client, denoiser=fail_denoiser)

    kinds = [artifact["kind"] for artifact in result["artifacts"]]
    assert kinds == ["transcript_before"] * 4
    assert "noise_reduction" not in result["stages"]
    assert "transcribe" in result["stages"]
