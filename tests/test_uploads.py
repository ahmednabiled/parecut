ALLOWED = {"filename": "clip.wav", "size_bytes": 1024, "content_type": "audio/wav"}


async def test_presign_upload_and_download_round_trip(app, client):
    await client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "password": "password123", "full_name": "A"},
    )
    created = await client.post("/api/uploads", json=ALLOWED)
    assert created.status_code == 201
    body = created.json()
    assert body["upload_key"].startswith("uploads/")

    put = await client.put(body["upload_url"], content=b"audio-bytes")
    assert put.status_code == 204

    token = body["upload_url"].rsplit("/", 1)[-1]
    fetched = await client.get(f"/api/uploads/download/{token}?filename=clip.wav")
    assert fetched.status_code == 403  # purpose-swapped token must fail

    download_token = body["upload_key"]
    assert await app.state.storage.get(download_token) == b"audio-bytes"


async def test_upload_rejects_disallowed_type_and_oversize(client):
    await client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "password": "password123", "full_name": "A"},
    )
    bad = await client.post("/api/uploads", json={**ALLOWED, "filename": "clip.exe"})
    assert bad.status_code == 422
    big = await client.post("/api/uploads", json={**ALLOWED, "size_bytes": 10**13})
    assert big.status_code == 413


async def test_invalid_upload_token_is_rejected(client):
    assert (await client.put("/api/uploads/not-a-token", content=b"x")).status_code == 403
