from httpx import ASGITransport, AsyncClient

from app.models import JobArtifact
from tests.helpers import make_wav, register, upload


async def _create_job(client) -> dict:
    await register(client)
    key = await upload(client, make_wav(2))
    response = await client.post(
        "/api/jobs",
        json={"upload_key": key, "source_filename": "clip.wav", "fps": "25", "pipeline": {}},
    )
    return response.json()


async def test_list_and_detail_return_only_own_jobs(app, client):
    job = await _create_job(client)
    listed = await client.get("/api/jobs")
    assert [row["id"] for row in listed.json()] == [job["id"]]
    assert (await client.get(f"/api/jobs/{job['id']}")).status_code == 200

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        await register(other, email="b@example.com")
        assert (await other.get(f"/api/jobs/{job['id']}")).status_code == 404
        assert (await other.get("/api/jobs")).json() == []


async def test_text_artifact_download_serves_same_origin_content(app, client):
    job = await _create_job(client)
    key = f"jobs/{job['id']}/ROUGH-CUT.md"
    await app.state.storage.put(key, b"# Spec\n", "text/markdown")
    async with app.state.sessionmaker() as session:
        artifact = JobArtifact(
            job_id=job["id"],
            kind="rough_cut_md",
            label="ROUGH-CUT.md",
            format="md",
            r2_key=key,
            size_bytes=7,
        )
        session.add(artifact)
        await session.commit()
        await session.refresh(artifact)
        artifact_id = artifact.id

    response = await client.get(
        f"/api/jobs/{job['id']}/artifacts/{artifact_id}/download"
    )

    assert response.status_code == 200
    assert response.text == "# Spec\n"
    assert response.headers["content-type"].startswith("text/markdown")
    assert "attachment" in response.headers["content-disposition"]


async def test_download_redirects_to_signed_url_and_hides_foreign_artifacts(app, client):
    job = await _create_job(client)
    async with app.state.sessionmaker() as session:
        artifact = JobArtifact(
            job_id=job["id"],
            kind="enhanced_audio",
            label="Demo — Enhanced",
            format="wav",
            r2_key="jobs/demo.wav",
            size_bytes=4,
        )
        session.add(artifact)
        await session.commit()
        await session.refresh(artifact)
        artifact_id = artifact.id

    path = f"/api/jobs/{job['id']}/artifacts/{artifact_id}/download"
    response = await client.get(path, follow_redirects=False)
    assert response.status_code == 302
    assert "/api/uploads/download/" in response.headers["location"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        await register(other, email="b@example.com")
        assert (await other.get(path)).status_code == 404
