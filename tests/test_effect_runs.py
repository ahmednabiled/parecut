import asyncio
from decimal import Decimal

from app.models import UserProfile
from tests.helpers import make_wav, register, upload


async def _draft_job(client) -> dict:
    await register(client)
    source = make_wav(4)
    key = await upload(client, source)
    response = await client.post(
        "/api/jobs",
        json={
            "upload_key": key,
            "source_filename": "clip.wav",
            "fps": "25",
            "draft": True,
        },
    )
    assert response.status_code == 201, response.text
    return {"job": response.json(), "source": source}


async def _wait(client, job_id: str) -> dict:
    for _ in range(80):
        body = (await client.get(f"/api/jobs/{job_id}")).json()
        if body["status"] in {"completed", "failed"}:
            return body
        await asyncio.sleep(0.05)
    raise AssertionError("job did not finish")


async def test_draft_project_and_effect_run(app, client):
    created = await _draft_job(client)
    parent = created["job"]
    assert parent["status"] == "completed"
    assert parent["parent_job_id"] is None
    assert parent["effect"] is None
    assert parent["artifacts"] == []
    assert parent["source_url"].endswith(f"/api/jobs/{parent['id']}/source")

    effects = await client.get(f"/api/jobs/{parent['id']}/effects")
    assert effects.status_code == 200
    assert effects.json() == []

    applied = await client.post(
        f"/api/jobs/{parent['id']}/effects", json={"effect": "noise_reduction"}
    )
    assert applied.status_code == 201, applied.text
    child = applied.json()
    assert child["parent_job_id"] == parent["id"]
    assert child["effect"] == "noise_reduction"
    assert child["pipeline_config"]["noise_reduction"] is True
    assert child["pipeline_config"]["transcribe"] is False

    finished = await _wait(client, child["id"])
    assert finished["status"] == "completed"
    assert [artifact["kind"] for artifact in finished["artifacts"]] == [
        "cleaned_audio"
    ]

    runs = (await client.get(f"/api/jobs/{parent['id']}/effects")).json()
    assert [run["id"] for run in runs] == [child["id"]]
    assert runs[0]["artifacts"][0]["content_url"].startswith(
        f"/api/jobs/{child['id']}/artifacts/"
    )

    # Effect runs are not separate projects in the dashboard/list.
    listed = (await client.get("/api/jobs")).json()
    assert [job["id"] for job in listed] == [parent["id"]]

    # Source and generated audio are available same-origin for the editor.
    source = await client.get(parent["source_url"])
    assert source.status_code == 200
    assert source.content == created["source"]

    partial = await client.get(
        parent["source_url"], headers={"Range": "bytes=4-7"}
    )
    assert partial.status_code == 206
    assert partial.content == created["source"][4:8]
    assert partial.headers["content-range"] == (
        f"bytes 4-7/{len(created['source'])}"
    )

    artifact = finished["artifacts"][0]
    content = await client.get(artifact["content_url"])
    assert content.status_code == 200
    assert content.content == created["source"]

    partial_content = await client.get(
        artifact["content_url"], headers={"Range": "bytes=-8"}
    )
    assert partial_content.status_code == 206
    assert partial_content.content == created["source"][-8:]


async def test_effect_run_requires_credits_and_project_parent(app, client):
    created = await _draft_job(client)
    parent = created["job"]

    applied = await client.post(
        f"/api/jobs/{parent['id']}/effects", json={"effect": "enhance"}
    )
    assert applied.status_code == 201, applied.text
    child = applied.json()

    rejected = await client.post(
        f"/api/jobs/{child['id']}/effects", json={"effect": "noise_reduction"}
    )
    assert rejected.status_code == 422

    profile_response = await client.get("/api/profile")
    user_id = profile_response.json()["user"]["id"]
    async with app.state.sessionmaker() as session:
        profile = await session.get(UserProfile, user_id)
        profile.credit_balance_minutes = Decimal("0.5")
        session.add(profile)
        await session.commit()

    response = await client.post(
        f"/api/jobs/{parent['id']}/effects",
        json={"effect": "separate_music"},
    )
    assert response.status_code == 402
    assert response.json()["required_minutes"] == 1.0
    assert response.json()["available_minutes"] == 0.5
