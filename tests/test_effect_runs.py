import asyncio
from decimal import Decimal
from pathlib import Path

from app.models import Job, JobArtifact, UserProfile
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
    assert parent["source_peaks_url"].endswith(
        f"/api/jobs/{parent['id']}/source/peaks"
    )

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

    peaks = await client.get(parent["source_peaks_url"])
    assert peaks.status_code == 200
    peak_values = peaks.json()["peaks"]
    assert 0 < len(peak_values) <= 512
    assert max(peak_values) > 0

    artifact = finished["artifacts"][0]
    content = await client.get(artifact["content_url"])
    assert content.status_code == 200
    assert content.content == created["source"]

    artifact_peaks = await client.get(artifact["peaks_url"])
    assert artifact_peaks.status_code == 200
    assert max(artifact_peaks.json()["peaks"]) > 0

    partial_content = await client.get(
        artifact["content_url"], headers={"Range": "bytes=-8"}
    )
    assert partial_content.status_code == 206
    assert partial_content.content == created["source"][-8:]


async def test_enhance_effect_stores_studio_chain(app, client):
    created = await _draft_job(client)
    parent = created["job"]
    response = await client.post(
        f"/api/jobs/{parent['id']}/effects",
        json={
            "effect": "enhance",
            "enhance_mix": 0.7,
            "studio": {
                "highpass_hz": 90,
                "body_db": 4,
                "presence_db": 2.5,
                "compressor_threshold_db": -20,
                "compressor_ratio": 4,
                "limiter_db": -1.5,
                "loudness_lufs": -14,
            },
        },
    )
    assert response.status_code == 201, response.text
    child = response.json()
    studio = child["pipeline_config"]["studio_chain"]
    assert studio["enabled"] is True
    assert studio["highpass_hz"] == 90
    assert studio["body_db"] == 4
    assert studio["presence_db"] == 2.5
    assert studio["compressor_threshold_db"] == -20
    assert studio["compressor_ratio"] == 4
    assert studio["limiter_db"] == -1.5
    assert studio["loudness_lufs"] == -14
    assert child["pipeline_config"]["enhance_mix"] == 0.7


async def test_transcribe_effect_stores_languages(app, client):
    created = await _draft_job(client)
    parent = created["job"]

    response = await client.post(
        f"/api/jobs/{parent['id']}/effects",
        json={
            "effect": "transcribe",
            "languages": ["en", "ar"],
            "arabic_dialect": "egyptian",
        },
    )
    assert response.status_code == 201, response.text
    child = response.json()
    assert child["pipeline_config"]["transcribe"] is True
    assert child["pipeline_config"]["rough_cut"] is True
    assert child["pipeline_config"]["transcription_languages"] == ["en", "ar"]
    assert child["pipeline_config"]["arabic_dialect"] == "egyptian"

    invalid = await client.post(
        f"/api/jobs/{parent['id']}/effects",
        json={"effect": "transcribe", "arabic_dialect": "klingon"},
    )
    assert invalid.status_code == 422


async def test_enhance_effect_stores_audio_format(app, client):
    created = await _draft_job(client)
    parent = created["job"]

    response = await client.post(
        f"/api/jobs/{parent['id']}/effects",
        json={"effect": "enhance", "audio_format": "wav"},
    )
    assert response.status_code == 201, response.text
    child = response.json()
    assert child["pipeline_config"]["audio_format"] == "wav"


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


async def test_effect_uses_selected_source_artifact(app, client):
    created = await _draft_job(client)
    parent = created["job"]

    applied = await client.post(
        f"/api/jobs/{parent['id']}/effects", json={"effect": "noise_reduction"}
    )
    assert applied.status_code == 201, applied.text
    first = await _wait(client, applied.json()["id"])
    artifact_id = first["artifacts"][0]["id"]

    chained = await client.post(
        f"/api/jobs/{parent['id']}/effects",
        json={"effect": "enhance", "source_artifact_id": artifact_id},
    )
    assert chained.status_code == 201, chained.text
    second = chained.json()

    async with app.state.sessionmaker() as session:
        source_artifact = await session.get(JobArtifact, artifact_id)
        chained_job = await session.get(Job, second["id"])
        assert chained_job.source_r2_key == source_artifact.r2_key
        assert chained_job.source_filename == Path(source_artifact.r2_key).name

    missing = await client.post(
        f"/api/jobs/{parent['id']}/effects",
        json={"effect": "enhance", "source_artifact_id": "does-not-exist"},
    )
    assert missing.status_code == 404

    async with app.state.sessionmaker() as session:
        transcript = JobArtifact(
            job_id=parent["id"],
            kind="transcript_after",
            label="Transcript",
            format="json",
            r2_key="jobs/transcript_after.json",
        )
        session.add(transcript)
        await session.commit()
        await session.refresh(transcript)
        transcript_id = transcript.id

    rejected = await client.post(
        f"/api/jobs/{parent['id']}/effects",
        json={"effect": "noise_reduction", "source_artifact_id": transcript_id},
    )
    assert rejected.status_code == 422


async def test_delete_generated_track_removes_artifact_and_run(app, client):
    created = await _draft_job(client)
    parent = created["job"]

    applied = await client.post(
        f"/api/jobs/{parent['id']}/effects", json={"effect": "noise_reduction"}
    )
    finished = await _wait(client, applied.json()["id"])
    artifact = finished["artifacts"][0]

    deleted = await client.delete(
        f"/api/jobs/{parent['id']}/artifacts/{artifact['id']}"
    )
    assert deleted.status_code == 204, deleted.text

    assert (await client.get(artifact["content_url"])).status_code == 404
    assert (await client.get(f"/api/jobs/{parent['id']}/effects")).json() == []


async def test_delete_project_artifact_keeps_project(app, client):
    created = await _draft_job(client)
    parent = created["job"]

    async with app.state.sessionmaker() as session:
        artifact = JobArtifact(
            job_id=parent["id"],
            kind="cleaned_audio",
            label="Track",
            format="mp3",
            r2_key="jobs/project/track.mp3",
        )
        session.add(artifact)
        await session.commit()
        await session.refresh(artifact)
        artifact_id = artifact.id

    deleted = await client.delete(
        f"/api/jobs/{parent['id']}/artifacts/{artifact_id}"
    )
    assert deleted.status_code == 204, deleted.text

    assert (await client.get(f"/api/jobs/{parent['id']}")).status_code == 200
    assert (await client.delete(
        f"/api/jobs/{parent['id']}/artifacts/{artifact_id}"
    )).status_code == 404
