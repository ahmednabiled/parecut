from app.services.runpod import expected_artifacts
from parecut_engine.schemas import PipelineConfig
from runpod_app.worker import handler


class FakeResponse:
    status_code = 200
    content = b"downloaded audio bytes"

    def raise_for_status(self) -> None:
        return None


class FakeClient:
    def __init__(self) -> None:
        self.puts: list[tuple[str, bytes, str]] = []

    def get(self, url: str, follow_redirects: bool = True) -> FakeResponse:
        assert url == "https://source.example/clip.wav"
        return FakeResponse()

    def put(self, url: str, content: bytes, headers: dict[str, str]) -> FakeResponse:
        self.puts.append((url, content, headers["content-type"]))
        return FakeResponse()


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


def test_stub_worker_uploads_every_expected_artifact():
    job = make_job()
    client = FakeClient()

    result = handler(job, client=client)

    expected_keys = {artifact["key"] for artifact in job["input"]["expected_artifacts"]}
    assert {artifact["key"] for artifact in result["artifacts"]} == expected_keys
    assert len(client.puts) == len(expected_keys)
    assert all(len(content) > 0 for _, content, _ in client.puts)
    assert result["stages"]["noise_reduction"]["status"] == "completed"
    assert result["speaker_roles"] == {
        "SPEAKER_01": "presenter",
        "SPEAKER_02": "presenter",
    }


def test_stub_worker_respects_disabled_stages():
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

    result = handler(job, client=client)

    kinds = [artifact["kind"] for artifact in result["artifacts"]]
    assert kinds == ["transcript_before"] * 4
    assert "noise_reduction" not in result["stages"]
    assert "transcribe" in result["stages"]
