from decimal import Decimal

import httpx
from sqlmodel import select

from app.config import Settings
from app.main import create_app
from app.models import CreditLedger, Job, JobArtifact
from app.services.runpod import (
    HttpRunpodClient,
    RunpodPipelineRunner,
    expected_artifacts,
)
from parecut_engine.schemas import JobEvent, PipelineConfig
from tests.helpers import make_wav, register, upload


class NullRunner:
    async def spawn(self, job_id: str) -> None:
        return None


class RecordingBroker:
    def __init__(self) -> None:
        self.events: list[JobEvent] = []

    async def publish(self, job_id: str, event: JobEvent) -> None:
        self.events.append(event)

    def subscribe(self, job_id: str):
        raise NotImplementedError


class FakeRunpodClient:
    def __init__(self, statuses: list[dict]) -> None:
        self.statuses = list(statuses)
        self.runs: list[tuple[str, dict]] = []

    async def run(self, endpoint_id: str, payload: dict) -> dict:
        self.runs.append((endpoint_id, payload))
        return {"id": "rp-1", "status": "IN_QUEUE"}

    async def status(self, endpoint_id: str, runpod_job_id: str) -> dict:
        assert endpoint_id == "ep-audio"
        assert runpod_job_id == "rp-1"
        return self.statuses.pop(0)


def test_expected_artifacts_default_to_mp3():
    config = PipelineConfig(
        separate_music=True, transcribe=False, rough_cut=False
    )
    artifacts = expected_artifacts("job-1", config)
    music = next(a for a in artifacts if a["kind"] == "stem_music")
    assert music["key"].endswith(".mp3")
    assert music["format"] == "mp3"


def test_expected_artifacts_honor_wav():
    config = PipelineConfig(
        separate_music=True,
        transcribe=False,
        rough_cut=False,
        audio_format="wav",
    )
    artifacts = expected_artifacts("job-1", config)
    music = next(a for a in artifacts if a["kind"] == "stem_music")
    assert music["key"].endswith(".wav")
    assert music["format"] == "wav"


def test_expected_speaker_artifacts_use_selected_format():
    config = PipelineConfig(
        separate_speakers=True,
        transcribe=False,
        rough_cut=False,
        audio_format="mp3",
    )
    artifacts = expected_artifacts("job-1", config)
    speaker = next(a for a in artifacts if a["kind"] == "stem_speaker")
    assert speaker["key"].endswith(".mp3")
    assert speaker["format"] == "mp3"


async def _create_job(app, client, pipeline: dict | None = None) -> dict:
    await register(client)
    key = await upload(client, make_wav(2))
    app.state.runner = NullRunner()
    response = await client.post(
        "/api/jobs",
        json={
            "upload_key": key,
            "source_filename": "clip.wav",
            "fps": "25",
            "pipeline": pipeline or {},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _runner(app, *, broker=None, runpod):
    app.state.settings.public_base_url = "https://api.parecut.test"
    app.state.settings.runpod_audio_endpoint_id = "ep-audio"
    return RunpodPipelineRunner(
        app.state.sessionmaker,
        app.state.storage,
        broker or RecordingBroker(),
        app.state.settings,
        runpod,
    )


async def test_runner_submits_job_and_records_artifacts(app, client):
    job = await _create_job(app, client)
    output_key = f"jobs/{job['id']}/01_cleaned.mp3"
    runpod = FakeRunpodClient(
        [
            {
                "id": "rp-1",
                "status": "COMPLETED",
                "output": {
                    "artifacts": [
                        {
                            "kind": "cleaned_audio",
                            "label": "Cleaned Audio",
                            "format": "mp3",
                            "key": output_key,
                            "size_bytes": 12,
                        }
                    ],
                    "speaker_roles": {
                        "SPEAKER_01": "presenter",
                        "SPEAKER_02": "feeder",
                    },
                    "stages": {
                        name: {"status": "completed", "percent": 100}
                        for name in [
                            "noise_reduction",
                            "enhance",
                            "separate_music",
                            "separate_speakers",
                            "transcribe",
                            "rough_cut",
                        ]
                    },
                },
            }
        ]
    )

    await _runner(app, runpod=runpod).run(job["id"])

    endpoint_id, payload = runpod.runs[0]
    assert endpoint_id == "ep-audio"
    data = payload["input"]
    assert data["job_id"] == job["id"]
    assert data["source_url"].startswith("https://api.parecut.test/api/uploads/download/")
    assert output_key in data["outputs"]
    assert data["outputs"][output_key].startswith("https://api.parecut.test/api/uploads/")
    assert data["pipeline"]["transcribe"] is True

    async with app.state.sessionmaker() as session:
        stored = await session.get(Job, job["id"])
        assert stored.runpod_job_id == "rp-1"
        assert stored.status == "completed"
        assert stored.speaker_roles == {
            "SPEAKER_01": "presenter",
            "SPEAKER_02": "feeder",
        }
        assert stored.stage_states["transcribe"]["status"] == "completed"
        artifacts = (
            await session.exec(select(JobArtifact).where(JobArtifact.job_id == job["id"]))
        ).all()
        assert [(a.kind, a.r2_key) for a in artifacts] == [("cleaned_audio", output_key)]
        settle = (
            await session.exec(
                select(CreditLedger).where(CreditLedger.reason == "job_settle")
            )
        ).one()
        assert settle.delta_minutes == Decimal("0")


async def test_runner_marks_failed_jobs_and_refunds(app, client):
    job = await _create_job(app, client)
    runpod = FakeRunpodClient(
        [{"id": "rp-1", "status": "FAILED", "error": "worker exploded"}]
    )

    await _runner(app, runpod=runpod).run(job["id"])

    async with app.state.sessionmaker() as session:
        stored = await session.get(Job, job["id"])
        assert stored.status == "failed"
        assert stored.error_code == "runpod_failed"
        refund = (
            await session.exec(
                select(CreditLedger).where(CreditLedger.reason == "job_refund")
            )
        ).one()
        assert refund.delta_minutes == Decimal("1")


async def test_runner_publishes_stage_progress(app, client):
    job = await _create_job(app, client)
    broker = RecordingBroker()
    runpod = FakeRunpodClient(
        [
            {
                "id": "rp-1",
                "status": "IN_PROGRESS",
                "output": {"stage": "transcribe", "percent": 50},
            },
            {
                "id": "rp-1",
                "status": "COMPLETED",
                "output": {"stages": {"transcribe": {"status": "completed", "percent": 100}}},
            },
        ]
    )

    await _runner(app, broker=broker, runpod=runpod).run(job["id"])

    progress = [
        event
        for event in broker.events
        if event.type == "stage.progress" and event.stage == "transcribe"
    ]
    assert progress and progress[0].percent == 50
    assert any(event.type == "job.completed" for event in broker.events)


async def test_http_runpod_client_uses_endpoint_paths():
    seen: list[tuple[str, str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            (
                request.method,
                request.url.path,
                request.headers.get("authorization"),
            )
        )
        if request.url.path.endswith("/run"):
            return httpx.Response(200, json={"id": "rp-1", "status": "IN_QUEUE"})
        return httpx.Response(200, json={"id": "rp-1", "status": "COMPLETED"})

    client = HttpRunpodClient(
        "key",
        base_url="https://api.runpod.ai/v2",
        transport=httpx.MockTransport(handler),
    )

    assert await client.run("ep-audio", {"input": {"x": 1}}) == {
        "id": "rp-1",
        "status": "IN_QUEUE",
    }
    assert await client.status("ep-audio", "rp-1") == {
        "id": "rp-1",
        "status": "COMPLETED",
    }
    await client.aclose()

    assert seen == [
        ("POST", "/v2/ep-audio/run", "Bearer key"),
        ("GET", "/v2/ep-audio/status/rp-1", "Bearer key"),
    ]


async def test_runpod_runner_is_selected_by_settings(tmp_path):
    settings = Settings(
        app_env="test",
        secret_key="test-secret-key-with-at-least-32-bytes",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        storage_dir=tmp_path / "storage",
        storage_backend="local",
        pipeline_runner="runpod",
        runpod_api_key="key",
        runpod_audio_endpoint_id="ep-audio",
        seed_demo=False,
    )

    app = create_app(settings)

    assert isinstance(app.state.runner, RunpodPipelineRunner)
    assert isinstance(app.state.runpod_client, HttpRunpodClient)
    await app.state.runpod_client.aclose()
