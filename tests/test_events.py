import asyncio

from app.services.pipeline import NullPipelineRunner
from parecut_engine.schemas import JobEvent
from tests.helpers import make_wav, register, upload


async def _collect(client, job_id: str) -> list[str]:
    lines: list[str] = []
    async with client.stream("GET", f"/api/jobs/{job_id}/events") as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            lines.append(line)
    return lines


async def test_sse_sends_snapshot_then_live_event(app, client):
    app.state.runner = NullPipelineRunner()
    await register(client)
    key = await upload(client, make_wav(2))
    created = await client.post(
        "/api/jobs",
        json={"upload_key": key, "source_filename": "clip.wav", "fps": "25", "pipeline": {}},
    )
    job_id = created.json()["id"]

    async with app.state.sessionmaker() as session:
        from app.models import Job

        job = await session.get(Job, job_id)
        job.status = "running"
        session.add(job)
        await session.commit()

    collector = asyncio.create_task(_collect(client, job_id))
    for _ in range(100):
        if app.state.broker._subscribers.get(job_id):
            break
        await asyncio.sleep(0.01)
    assert app.state.broker._subscribers.get(job_id)

    await app.state.broker.publish(
        job_id,
        JobEvent(type="stage.progress", job_id=job_id, stage="enhance", percent=50),
    )
    await app.state.broker.publish(
        job_id,
        JobEvent(type="job.completed", job_id=job_id),
    )

    lines = await asyncio.wait_for(collector, timeout=3)
    output = "\n".join(lines)
    assert "event: snapshot" in output
    assert "stage.progress" in output
    assert "job.completed" in output
    assert output.index("event: snapshot") < output.index("stage.progress")
