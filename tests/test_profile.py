async def _register(client):
    await client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "password": "password123", "full_name": "A"},
    )


async def test_profile_returns_user_profile_and_ledger(client):
    await _register(client)
    response = await client.get("/api/profile")
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "a@example.com"
    assert body["profile"]["default_fps"] == "25"
    assert body["ledger"][0]["reason"] == "signup_bonus"
    assert body["jobs"] == []


async def test_profile_patch_updates_defaults(client):
    await _register(client)
    response = await client.patch(
        "/api/profile",
        json={"full_name": "Renamed", "default_fps": "29.97", "default_enhance_mix": 65},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["full_name"] == "Renamed"
    assert body["profile"]["default_fps"] == "29.97"
    assert body["profile"]["default_enhance_mix"] == 65


async def test_profile_patch_rejects_invalid_defaults(client):
    await _register(client)
    assert (await client.patch("/api/profile", json={"default_fps": "23"})).status_code == 422
    assert (await client.patch("/api/profile", json={"default_enhance_mix": 101})).status_code == 422
