import asyncio
from decimal import Decimal

from sqlmodel import select

from app.models import CreditLedger
from app.services.pipeline import MockPipelineRunner
from tests.helpers import make_wav, register, upload


async def _wait_completed(client, job_id, timeout=5.0):
    for _ in range(int(timeout / 0.05)):
        body = (await client.get(f"/api/jobs/{job_id}")).json()
        if body["status"] in {"completed", "failed"}:
            return body
        await asyncio.sleep(0.05)
    raise AssertionError("job did not finish")


async def test_full_pipeline_writes_all_artifacts(app, client):
    await register(client)
    key = await upload(client, make_wav(4))
    created = await client.post(
        "/api/jobs",
        json={"upload_key": key, "source_filename": "clip.wav", "fps": "25", "pipeline": {}},
    )
    job = await _wait_completed(client, created.json()["id"])
    assert job["status"] == "completed"
    kinds = [artifact["kind"] for artifact in job["artifacts"]]
    assert kinds.count("transcript_before") == 4
    assert kinds.count("transcript_after") == 4
    assert kinds.count("rough_cut_md") == 1
    assert kinds.count("stem_speaker") == 2
    assert job["speaker_roles"] == {"SPEAKER_01": "presenter", "SPEAKER_02": "presenter"}

    async with app.state.sessionmaker() as session:
        ledger = (
            await session.exec(select(CreditLedger).where(CreditLedger.reason == "job_settle"))
        ).one()
        assert ledger.delta_minutes == Decimal("0")


async def test_transcription_only_skips_audio_stages(app, client):
    await register(client)
    key = await upload(client, make_wav(4))
    created = await client.post(
        "/api/jobs",
        json={
            "upload_key": key,
            "source_filename": "clip.wav",
            "fps": "25",
            "pipeline": {"noise_reduction": False, "enhance": False,
                         "separate_music": False, "separate_speakers": False,
                         "transcribe": True, "rough_cut": False},
        },
    )
    job = await _wait_completed(client, created.json()["id"])
    assert job["stage_states"]["enhance"]["status"] == "skipped"
    assert [a["kind"] for a in job["artifacts"]] == ["transcript_before"] * 4


async def test_failure_refunds_credits(app, client):
    await register(client)
    key = await upload(client, make_wav(4))

    class BrokenStorage:
        def __getattr__(self, name):
            return getattr(app.state.storage, name)

        async def copy(self, src, dst):
            raise RuntimeError("storage down")

    app.state.runner = MockPipelineRunner(
        app.state.sessionmaker, BrokenStorage(), app.state.broker, app.state.settings
    )
    created = await client.post(
        "/api/jobs",
        json={
            "upload_key": key,
            "source_filename": "clip.wav",
            "fps": "25",
            "pipeline": {"noise_reduction": True, "enhance": False, "separate_music": False,
                         "separate_speakers": False, "transcribe": False, "rough_cut": False},
        },
    )
    job = await _wait_completed(client, created.json()["id"])
    assert job["status"] == "failed"
    assert job["error_code"] == "mock_pipeline_failed"

    async with app.state.sessionmaker() as session:
        refund = (
            await session.exec(select(CreditLedger).where(CreditLedger.reason == "job_refund"))
        ).one()
        assert refund.delta_minutes == Decimal("1")
