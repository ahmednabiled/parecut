import asyncio
from decimal import Decimal

import pytest
from sqlmodel import select

from app.config import Settings
from app.main import create_app
from app.models import Job, JobArtifact, UserProfile
from app.services.pipeline import NullPipelineRunner
from tests.helpers import make_wav, register, upload


def test_prod_rejects_default_or_short_secret(tmp_path):
    with pytest.raises(ValueError, match="PARECUT_SECRET_KEY"):
        create_app(
            Settings(
                _env_file=None,
                app_env="prod",
                database_url=f"sqlite+aiosqlite:///{tmp_path / 'prod.db'}",
                storage_dir=tmp_path / "storage",
                seed_demo=False,
            )
        )

    with pytest.raises(ValueError, match="PARECUT_SECRET_KEY"):
        create_app(
            Settings(
                _env_file=None,
                app_env="prod",
                secret_key="too-short",
                database_url=f"sqlite+aiosqlite:///{tmp_path / 'prod.db'}",
                storage_dir=tmp_path / "storage",
                seed_demo=False,
            )
        )


def test_prod_rejects_incomplete_r2_or_runpod_config(tmp_path):
    secret = "a-very-strong-production-secret-key-32-plus"
    with pytest.raises(ValueError, match="R2 storage backend"):
        create_app(
            Settings(
                _env_file=None,
                app_env="prod",
                secret_key=secret,
                storage_backend="r2",
                database_url=f"sqlite+aiosqlite:///{tmp_path / 'prod.db'}",
                storage_dir=tmp_path / "storage",
                seed_demo=False,
            )
        )

    with pytest.raises(ValueError, match="Runpod pipeline runner"):
        create_app(
            Settings(
                _env_file=None,
                app_env="prod",
                secret_key=secret,
                pipeline_runner="runpod",
                database_url=f"sqlite+aiosqlite:///{tmp_path / 'prod.db'}",
                storage_dir=tmp_path / "storage",
                seed_demo=False,
            )
        )


async def test_streaming_upload_rejects_oversize_and_cleans_up_part_file(
    app, client
):
    await register(client)
    app.state.settings.max_upload_bytes = 64

    presign = await client.post(
        "/api/uploads",
        json={"filename": "clip.wav", "size_bytes": 32, "content_type": "audio/wav"},
    )
    assert presign.status_code == 201
    body = presign.json()

    too_big = await client.put(body["upload_url"], content=b"x" * 100)
    assert too_big.status_code == 413
    assert await app.state.storage.exists(body["upload_key"]) is False


async def test_atomic_credit_reservation_prevents_double_spend(app, client):
    app.state.runner = NullPipelineRunner()
    await register(client)
    key = await upload(client, make_wav(2))

    async with app.state.sessionmaker() as session:
        profile = (await session.exec(select(UserProfile))).one()
        profile.credit_balance_minutes = Decimal("1")
        session.add(profile)
        await session.commit()

    payload = {
        "upload_key": key,
        "source_filename": "clip.wav",
        "fps": "25",
        "pipeline": {},
    }
    first, second = await asyncio.gather(
        client.post("/api/jobs", json=payload),
        client.post("/api/jobs", json=payload),
    )
    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [201, 402]

    async with app.state.sessionmaker() as session:
        profile = (await session.exec(select(UserProfile))).one()
        assert profile.credit_balance_minutes == Decimal("0")


async def test_project_rename_and_delete_cleans_up_children_and_storage(
    app, client
):
    app.state.runner = NullPipelineRunner()
    await register(client)
    key = await upload(client, make_wav(2))

    created = await client.post(
        "/api/jobs",
        json={
            "upload_key": key,
            "source_filename": "clip.wav",
            "fps": "25",
            "draft": True,
        },
    )
    assert created.status_code == 201
    job_id = created.json()["id"]

    # Blank rename rejected
    blank = await client.patch(
        f"/api/jobs/{job_id}", json={"source_filename": "   "}
    )
    assert blank.status_code == 422

    # Valid rename succeeds
    renamed = await client.patch(
        f"/api/jobs/{job_id}", json={"source_filename": "Interview Ep 4.wav"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["source_filename"] == "Interview Ep 4.wav"

    # Active child effect blocks deletion with 409
    effect = await client.post(
        f"/api/jobs/{job_id}/effects", json={"effect": "noise_reduction"}
    )
    assert effect.status_code == 201
    effect_id = effect.json()["id"]

    blocked = await client.delete(f"/api/jobs/{job_id}")
    assert blocked.status_code == 409

    # Mark effect completed and attach an artifact
    artifact_key = f"jobs/{effect_id}/01_cleaned.wav"
    await app.state.storage.put(artifact_key, b"cleaned", "audio/wav")
    async with app.state.sessionmaker() as session:
        child = await session.get(Job, effect_id)
        child.status = "completed"
        session.add(child)
        session.add(
            JobArtifact(
                job_id=effect_id,
                kind="cleaned_audio",
                label="Cleaned Audio",
                format="wav",
                r2_key=artifact_key,
                size_bytes=7,
            )
        )
        await session.commit()

    # Now deletion succeeds and cleans up DB rows + storage
    deleted = await client.delete(f"/api/jobs/{job_id}")
    assert deleted.status_code == 204
    assert (await client.get(f"/api/jobs/{job_id}")).status_code == 404
    assert await app.state.storage.exists(key) is False
    assert await app.state.storage.exists(artifact_key) is False


def test_normalize_database_url_rewrites_postgres_schemes():
    from app.db import normalize_database_url

    assert (
        normalize_database_url("postgres://u:p@host:5432/db")
        == "postgresql+asyncpg://u:p@host:5432/db"
    )
    assert (
        normalize_database_url("postgresql://u:p@host:5432/db")
        == "postgresql+asyncpg://u:p@host:5432/db"
    )
    assert (
        normalize_database_url("sqlite+aiosqlite:///./var/parecut.db")
        == "sqlite+aiosqlite:///./var/parecut.db"
    )


async def test_ready_endpoint_checks_database(client):
    res = await client.get("/api/ready")
    assert res.status_code == 200
    assert res.json() == {"status": "ready"}


async def test_cleanup_abandoned_uploads_preserves_referenced_and_recent(app, client):
    import os
    import time

    from app.services.cleanup import cleanup_abandoned_uploads

    await register(client)
    referenced_key = await upload(client, make_wav(1), filename="used.wav")
    abandoned_old_key = await upload(client, make_wav(1), filename="old.wav")
    abandoned_new_key = await upload(client, make_wav(1), filename="new.wav")

    res = await client.post(
        "/api/jobs",
        json={
            "upload_key": referenced_key,
            "source_filename": "used.wav",
            "fps": "25",
            "draft": True,
        },
    )
    assert res.status_code == 201

    now = time.time()
    old_ts = now - 90_000
    os.utime(app.state.storage._path(referenced_key), (old_ts, old_ts))
    os.utime(app.state.storage._path(abandoned_old_key), (old_ts, old_ts))

    deleted = await cleanup_abandoned_uploads(
        app.state.sessionmaker, app.state.storage, max_age_seconds=86_400, now=now
    )
    assert deleted == 1
    assert await app.state.storage.exists(abandoned_old_key) is False
    assert await app.state.storage.exists(referenced_key) is True
    assert await app.state.storage.exists(abandoned_new_key) is True


async def test_reconcile_resumes_in_flight_runpod_job_instead_of_failing(app, client):
    from app.seed import reconcile_orphan_jobs
    from app.services.runpod import RunpodPipelineRunner
    from tests.test_runpod_runner import FakeRunpodClient, RecordingBroker

    app.state.runner = NullPipelineRunner()
    await register(client)
    key = await upload(client, make_wav(2))
    created = await client.post(
        "/api/jobs",
        json={
            "upload_key": key,
            "source_filename": "clip.wav",
            "fps": "25",
            "pipeline": {},
        },
    )
    job_id = created.json()["id"]

    async with app.state.sessionmaker() as session:
        job = await session.get(Job, job_id)
        job.status = "running"
        job.runpod_job_id = "rp-1"
        session.add(job)
        await session.commit()

    app.state.settings.runpod_audio_endpoint_id = "ep-audio"
    runpod = FakeRunpodClient(
        [
            {
                "id": "rp-1",
                "status": "COMPLETED",
                "output": {"artifacts": [], "speaker_roles": {}},
            }
        ]
    )
    runner = RunpodPipelineRunner(
        app.state.sessionmaker,
        app.state.storage,
        RecordingBroker(),
        app.state.settings,
        runpod,
    )

    await reconcile_orphan_jobs(
        app.state.sessionmaker, app.state.settings, runner=runner
    )
    await asyncio.gather(*list(runner._tasks))

    async with app.state.sessionmaker() as session:
        stored = await session.get(Job, job_id)
        assert stored.status == "completed"
        assert stored.error_code is None
