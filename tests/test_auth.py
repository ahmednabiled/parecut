from decimal import Decimal


async def test_register_creates_profile_bonus_and_cookie(client):
    response = await client.post(
        "/api/auth/register",
        json={"email": "New@Example.com", "password": "password123", "full_name": "New User"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "new@example.com"
    assert body["profile"]["credit_balance_minutes"] == 30
    assert "parecut_session" in response.cookies

    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "new@example.com"


async def test_duplicate_email_returns_409(client):
    payload = {"email": "a@example.com", "password": "password123", "full_name": "A"}
    assert (await client.post("/api/auth/register", json=payload)).status_code == 201
    assert (await client.post("/api/auth/register", json=payload)).status_code == 409


async def test_login_and_logout(client):
    await client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "password": "password123", "full_name": "A"},
    )
    await client.post("/api/auth/logout")
    assert (await client.get("/api/auth/me")).status_code == 401

    bad = await client.post("/api/auth/login", json={"email": "a@example.com", "password": "nope"})
    assert bad.status_code == 401

    good = await client.post(
        "/api/auth/login", json={"email": "a@example.com", "password": "password123"}
    )
    assert good.status_code == 200
    assert (await client.get("/api/auth/me")).status_code == 200


async def test_signup_bonus_is_in_ledger(app, client):
    await client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "password": "password123", "full_name": "A"},
    )
    from sqlmodel import select

    from app.models import CreditLedger

    async with app.state.sessionmaker() as session:
        rows = (await session.exec(select(CreditLedger))).all()
    assert [(row.reason, row.delta_minutes) for row in rows] == [("signup_bonus", Decimal("30"))]


async def test_inactive_user_cannot_login_and_blank_name_rejected(app, client):
    blank = await client.post(
        "/api/auth/register",
        json={"email": "blank@example.com", "password": "password123", "full_name": "   "},
    )
    assert blank.status_code == 422

    reg = await client.post(
        "/api/auth/register",
        json={"email": "inactive@example.com", "password": "password123", "full_name": "User"},
    )
    assert reg.status_code == 201
    user_id = reg.json()["user"]["id"]
    await client.post("/api/auth/logout")

    from app.models import User

    async with app.state.sessionmaker() as session:
        user = await session.get(User, user_id)
        user.is_active = False
        session.add(user)
        await session.commit()

    login = await client.post(
        "/api/auth/login",
        json={"email": "inactive@example.com", "password": "password123"},
    )
    assert login.status_code == 401
