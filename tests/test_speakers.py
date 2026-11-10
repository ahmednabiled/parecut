import asyncio

from sqlmodel import select

from app.models import JobArtifact
from tests.helpers import make_wav, register, upload


async def _completed_job(app, client):
    await register(client)
    key = await upload(client, make_wav(4))
    created = await client.post(
        "/api/jobs",
        json={"upload_key": key, "source_filename": "clip.wav", "fps": "25", "pipeline": {}},
    )
    job_id = created.json()["id"]

    for _ in range(60):
        body = (await client.get(f"/api/jobs/{job_id}")).json()
        if body["status"] == "completed":
            return body
        await asyncio.sleep(0.05)
    raise AssertionError("job did not complete")


async def _artifact_text(client, job, kind):
    artifact = next(
        a for a in job["artifacts"] if a["kind"] == kind and a["format"] == "srt"
    )
    response = await client.get(artifact["download_url"], follow_redirects=True)
    return response.text


async def test_marking_feeder_removes_lines_from_after_cut(app, client):
    job = await _completed_job(app, client)
    assert "SPEAKER_02" in await _artifact_text(client, job, "transcript_after")

    response = await client.patch(
        f"/api/jobs/{job['id']}/speakers",
        json={"roles": {"SPEAKER_01": "presenter", "SPEAKER_02": "feeder"}},
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["speaker_roles"]["SPEAKER_02"] == "feeder"
    assert "SPEAKER_02" not in await _artifact_text(client, updated, "transcript_after")
    md = next(a for a in updated["artifacts"] if a["kind"] == "rough_cut_md")
    assert "FEEDER_PROMPT" in (
        await client.get(md["download_url"], follow_redirects=True)
    ).text


async def test_demo_job_keeps_demo_labels_after_regeneration(app, client):
    job = await _completed_job(app, client)

    response = await client.patch(
        f"/api/jobs/{job['id']}/speakers",
        json={"roles": {"SPEAKER_01": "presenter", "SPEAKER_02": "feeder"}},
    )
    assert response.status_code == 200
    labels = [
        artifact["label"]
        for artifact in response.json()["artifacts"]
        if artifact["kind"] in {"transcript_after", "rough_cut_md"}
    ]
    assert labels
    assert all(label.startswith("Demo — ") for label in labels)


async def test_non_demo_job_regenerates_with_real_labels(app, client):
    job = await _completed_job(app, client)
    async with app.state.sessionmaker() as session:
        canonical = (
            await session.exec(
                select(JobArtifact).where(
                    JobArtifact.job_id == job["id"],
                    JobArtifact.kind == "transcript_before",
                    JobArtifact.format == "json",
                )
            )
        ).one()
        canonical.label = "Transcript (Before Cut)"
        session.add(canonical)
        await session.commit()

    response = await client.patch(
        f"/api/jobs/{job['id']}/speakers",
        json={"roles": {"SPEAKER_01": "presenter", "SPEAKER_02": "feeder"}},
    )
    assert response.status_code == 200
    labels = [
        artifact["label"]
        for artifact in response.json()["artifacts"]
        if artifact["kind"] in {"transcript_after", "rough_cut_md"}
    ]
    assert labels
    assert not any(label.startswith("Demo — ") for label in labels)


async def test_unknown_speaker_keys_are_rejected(app, client):
    job = await _completed_job(app, client)
    response = await client.patch(
        f"/api/jobs/{job['id']}/speakers",
        json={"roles": {"SPEAKER_99": "feeder"}},
    )
    assert response.status_code == 422
    assert "roles must match detected speakers" in response.json()["detail"]
