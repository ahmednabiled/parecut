from decimal import Decimal

from sqlmodel import select

from app.models import CreditLedger
from tests.helpers import make_wav, register, upload


class RecordingRunner:
    def __init__(self):
        self.spawned = []

    async def spawn(self, job_id):
        self.spawned.append(job_id)


async def test_create_job_reserves_credits_and_records_stages(app, client):
    await register(client)
    key = await upload(client, make_wav(2))
    runner = RecordingRunner()
    app.state.runner = runner

    response = await client.post(
        "/api/jobs",
        json={
            "upload_key": key,
            "source_filename": "clip.wav",
            "fps": "25",
            "pipeline": {"transcribe": True, "rough_cut": True},
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "queued"
    assert body["duration_seconds"] == 2.0
    assert body["stage_states"]["noise_reduction"]["status"] == "pending"
    assert body["stage_states"]["separate_music"]["status"] == "pending"
    assert runner.spawned == [body["id"]]

    async with app.state.sessionmaker() as session:
        ledger = (
            await session.exec(
                select(CreditLedger).where(CreditLedger.reason == "job_reserve")
            )
        ).one()
        assert ledger.delta_minutes == Decimal("-1")


async def test_rough_cut_without_transcribe_is_rejected(client):
    await register(client)
    key = await upload(client, make_wav(2))
    response = await client.post(
        "/api/jobs",
        json={
            "upload_key": key,
            "source_filename": "clip.wav",
            "fps": "25",
            "pipeline": {"transcribe": False, "rough_cut": True},
        },
    )
    assert response.status_code == 422


async def test_insufficient_credits_returns_402(app, client):
    await register(client)
    async with app.state.sessionmaker() as session:
        from app.models import UserProfile

        profile = (await session.exec(select(UserProfile))).one()
        profile.credit_balance_minutes = Decimal("0")
        session.add(profile)
        await session.commit()

    key = await upload(client, make_wav(2))
    response = await client.post(
        "/api/jobs",
        json={"upload_key": key, "source_filename": "clip.wav", "fps": "25", "pipeline": {}},
    )
    assert response.status_code == 402
    assert response.json()["required_minutes"] == 1
    assert response.json()["available_minutes"] == 0


async def test_unknown_duration_reserves_minimum(app, client):
    await register(client)
    key = await upload(client, b"not audio", filename="clip.wav")
    response = await client.post(
        "/api/jobs",
        json={"upload_key": key, "source_filename": "clip.wav", "fps": "25", "pipeline": {}},
    )
    assert response.status_code == 201
    assert response.json()["duration_seconds"] is None
