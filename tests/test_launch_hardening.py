import asyncio
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.db import create_db_and_tables
from app.main import create_app
from app.models import Job, UserProfile
from app.services.pipeline import NullPipelineRunner
from app.services.runpod import RunpodPipelineRunner
from tests.helpers import make_wav, register, upload
from tests.test_runpod_runner import FakeRunpodClient, RecordingBroker


async def test_security_headers_attached_on_responses(client, tmp_path):
    res = await client.get("/api/health")
    assert res.status_code == 200
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"
    assert res.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert res.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    assert "strict-transport-security" not in res.headers

    prod_app = create_app(
        Settings(
            _env_file=None,
            app_env="prod",
            secret_key="a-very-strong-production-secret-key-32-plus",
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'prod.db'}",
            storage_dir=tmp_path / "prod_storage",
            seed_demo=False,
        )
    )
    async with AsyncClient(
        transport=ASGITransport(app=prod_app), base_url="http://test"
    ) as prod_client:
        prod_res = await prod_client.get("/api/health")
        assert prod_res.status_code == 200
        assert (
            prod_res.headers["strict-transport-security"]
            == "max-age=31536000; includeSubDomains"
        )


async def test_rate_limiting_blocks_excess_auth_upload_and_job_requests(tmp_path):
    settings = Settings(
        _env_file=None,
        app_env="test",
        secret_key="test-secret-key-with-at-least-32-bytes",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'rl.db'}",
        storage_dir=tmp_path / "rl_storage",
        seed_demo=False,
        rate_limit_enabled=True,
        rate_limit_auth_per_minute=2,
        rate_limit_upload_per_minute=1,
        rate_limit_job_per_minute=1,
    )
    application = create_app(settings)
    application.state.runner = NullPipelineRunner()
    await create_db_and_tables(application.state.engine)

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as c:
        reg = await c.post(
            "/api/auth/register",
            json={"email": "u@example.com", "password": "password123", "full_name": "U"},
        )
        assert reg.status_code == 201

        login1 = await c.post(
            "/api/auth/login",
            json={"email": "u@example.com", "password": "password123"},
        )
        assert login1.status_code == 200

        # 3rd auth request exceeds limit of 2/min
        login2 = await c.post(
            "/api/auth/login",
            json={"email": "u@example.com", "password": "password123"},
        )
        assert login2.status_code == 429
        assert int(login2.headers["retry-after"]) >= 1

        # Upload presign limit = 1/min
        up1 = await c.post(
            "/api/uploads",
            json={"filename": "a.wav", "size_bytes": 100, "content_type": "audio/wav"},
        )
        assert up1.status_code == 201
        key = up1.json()["upload_key"]
        await c.put(up1.json()["upload_url"], content=make_wav(1))

        up2 = await c.post(
            "/api/uploads",
            json={"filename": "b.wav", "size_bytes": 100, "content_type": "audio/wav"},
        )
        assert up2.status_code == 429

        # Job creation limit = 1/min
        job1 = await c.post(
            "/api/jobs",
            json={
                "upload_key": key,
                "source_filename": "a.wav",
                "fps": "25",
                "draft": True,
            },
        )
        assert job1.status_code == 201

        job2 = await c.post(
            "/api/jobs",
            json={
                "upload_key": key,
                "source_filename": "a.wav",
                "fps": "25",
                "draft": True,
            },
        )
        assert job2.status_code == 429


async def test_ready_returns_503_when_database_fails(app, client):
    class BrokenSession:
        async def __aenter__(self):
            raise RuntimeError("db down")

        async def __aexit__(self, *args):
            return False

    original = app.state.sessionmaker
    app.state.sessionmaker = lambda: BrokenSession()
    try:
        res = await client.get("/api/ready")
        assert res.status_code == 503
        assert res.json()["status"] == "unavailable"
    finally:
        app.state.sessionmaker = original


async def test_unhandled_exception_returns_clean_json_500(app):
    @app.get("/api/_boom")
    async def boom():
        raise RuntimeError("sensitive internal traceback")

    # Place before the SPA catch-all route.
    app.router.routes.insert(0, app.router.routes.pop())

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as c:
        res = await c.get("/api/_boom")
        assert res.status_code == 500
        assert res.json() == {"detail": "Internal server error"}
        assert "sensitive" not in res.text


async def test_upload_validation_and_streaming_download_sanitizes_headers(app, client):
    await register(client)
    zero = await client.post(
        "/api/uploads",
        json={"filename": "clip.wav", "size_bytes": 0, "content_type": "audio/wav"},
    )
    assert zero.status_code == 422

    negative = await client.post(
        "/api/uploads",
        json={"filename": "clip.wav", "size_bytes": -10, "content_type": "audio/wav"},
    )
    assert negative.status_code == 422

    # Signed download streams content and strips CR/LF from Content-Disposition
    key = "jobs/test/audio.wav"
    await app.state.storage.put(key, b"RIFFtest", "audio/wav")
    url = app.state.storage.signed_download_url(key, 'bad\r\n"name.wav', 60)
    res = await client.get(url)
    assert res.status_code == 200
    assert res.content == b"RIFFtest"
    assert "\r" not in res.headers["content-disposition"]
    assert "\n" not in res.headers["content-disposition"]


async def test_delete_job_preserves_shared_source_key(app, client):
    app.state.runner = NullPipelineRunner()
    await register(client)
    key = await upload(client, make_wav(1))

    j1 = (
        await client.post(
            "/api/jobs",
            json={"upload_key": key, "source_filename": "a.wav", "fps": "25", "draft": True},
        )
    ).json()
    j2 = (
        await client.post(
            "/api/jobs",
            json={"upload_key": key, "source_filename": "b.wav", "fps": "25", "draft": True},
        )
    ).json()

    assert (await client.delete(f"/api/jobs/{j1['id']}")).status_code == 204
    assert await app.state.storage.exists(key) is True

    assert (await client.delete(f"/api/jobs/{j2['id']}")).status_code == 204
    assert await app.state.storage.exists(key) is False


async def test_runpod_sanitizes_malformed_speaker_roles_and_stage_states(app, client):
    app.state.runner = NullPipelineRunner()
    await register(client)
    key = await upload(client, make_wav(2))
    created = await client.post(
        "/api/jobs",
        json={"upload_key": key, "source_filename": "clip.wav", "fps": "25", "pipeline": {}},
    )
    job_id = created.json()["id"]

    app.state.settings.runpod_audio_endpoint_id = "ep-audio"
    runpod = FakeRunpodClient(
        [
            {"id": "rp-1", "status": "IN_QUEUE"},
            {
                "id": "rp-1",
                "status": "COMPLETED",
                "output": {
                    "speaker_roles": {"SPEAKER_01": "unknown_role", "SPEAKER_02": "feeder"},
                    "stages": {
                        "noise_reduction": {"status": "weird_status", "percent": 150}
                    },
                    "artifacts": [],
                },
            },
        ]
    )
    runner = RunpodPipelineRunner(
        app.state.sessionmaker,
        app.state.storage,
        RecordingBroker(),
        app.state.settings,
        runpod,
    )
    await runner.run(job_id)

    detail = await client.get(f"/api/jobs/{job_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["speaker_roles"] == {"SPEAKER_01": "presenter", "SPEAKER_02": "feeder"}
    assert body["stage_states"]["noise_reduction"]["status"] == "completed"
    assert body["stage_states"]["noise_reduction"]["percent"] == 100


async def test_concurrent_duplicate_registration_returns_409_not_500(app):
    payload = {"email": "race@example.com", "password": "password123", "full_name": "Race"}
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c1,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c2,
    ):
        r1, r2 = await asyncio.gather(
            c1.post("/api/auth/register", json=payload),
            c2.post("/api/auth/register", json=payload),
        )
    assert sorted([r1.status_code, r2.status_code]) == [201, 409]
