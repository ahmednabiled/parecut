# Parecut Phase 1 — Web Shell + Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete Parecut web shell — auth, profile, uploads, job flow, results UI — with every third-party dependency replaced by a local implementation behind a stable interface.

**Architecture:** FastAPI serves a React SPA and owns all state in SQLModel/SQLite. Three protocols (`ObjectStorage`, `EventBroker`, `PipelineRunner`) isolate the local Phase 1 implementations from future R2, Redis, and Modal swaps. Jobs run through a mock pipeline that writes real artifact rows/files and streams progress over SSE.

**Tech Stack:** Python 3.12, FastAPI, SQLModel/SQLAlchemy 2 async, Alembic, Pydantic v2, pwdlib/argon2, PyJWT, SSE-Starlette, SQLite (aiosqlite); React 19, Vite, TypeScript, Tailwind v4, React Router, TanStack Query, Vitest.

**Spec:** `docs/superpowers/specs/2026-11-06-parecut-v1-web-shell-design.md`

## Global Constraints

- Python 3.12 via `uv`; Node 22 via npm. No external services, API keys, Docker, Redis, Modal, R2, or LLM calls are required to boot or test.
- All API routes live under `/api`. Responses are JSON except upload bytes, SSE, and download redirects. Errors are `{"detail": "..."}` with 400/401/402/403/404/409/413/422.
- Auth: Argon2 hashing, HS256 JWT in httpOnly cookie `parecut_session`, `SameSite=Lax`, `Secure` only when `app_env == "prod"`, 7-day TTL.
- Credits are `Decimal` minutes: signup `+30`; reserve `max(1, ceil(duration_seconds / 60))`; settle writes a `0` delta marker; failure/restart writes `+reserve`.
- FPS values: `"24"`, `"25"`, `"29.97"` (30000/1001), `"30"`, `"60"`. Timecodes: clock `HH:MM:SS.mmm`, SMPTE `HH:MM:SS:FF`.
- Pipeline stages in order: `noise_reduction`, `enhance`, `separate_music`, `separate_speakers`, `transcribe`, `rough_cut`. `rough_cut` requires `transcribe`.
- Mock artifacts that are not real audio/transcript results carry a `Demo — ` label prefix or "Demo transcript" text.
- Frontend is desktop-first at 768 px+, dark editor-tool aesthetic, no external font CDN.
- Every task ends with `uv run pytest` (or the stated frontend gate) green and a commit.

## Review Focus

These are the failure modes most likely to hurt a real user; each is pinned by a test in the task that owns the code.

1. One user reading another user's job or downloading their artifact → must return 404, never 403-with-existence-leak or 200.
2. Forged, expired, or purpose-swapped upload/download token → must be rejected before any read or write.
3. API process restart mid-job → job must end `failed` and the reserved credits must be refunded, never stranded in `running`.
4. Speaker-role edit on a seeded or completed job, including unknown/missing speaker IDs → must either re-render consistently or reject with 422 without corrupting artifacts.
5. Pipeline subsets (rough cut without transcription, transcription off, single stage) → must reject invalid combos or produce correct `skipped` states and no dangling empty result tabs.

---

## Task 1: Project Scaffold, Settings, Health, Test Harness

**Files:**
- Create: `pyproject.toml` (via `uv init`), `.gitignore`, `.env.example`, `app/__init__.py`, `app/config.py`, `app/main.py`, `tests/conftest.py`, `tests/test_health.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Settings(BaseSettings)` with fields: `app_env: Literal["dev","test","prod"]="dev"`, `secret_key: str="dev-only-insecure-secret-change-me"`, `database_url: str="sqlite+aiosqlite:///./var/parecut.db"`, `storage_dir: Path=Path("var/storage")`, `session_cookie: str="parecut_session"`, `session_ttl_days: int=7`, `signup_bonus_minutes: Decimal=Decimal("30")`, `max_upload_bytes: int=2_147_483_648`, `upload_url_ttl_seconds: int=900`, `download_url_ttl_seconds: int=900`, `mock_stage_delay_ms: int=1500`, `seed_demo: bool=True`, `frontend_dist: Path=Path("web/dist")`. Env prefix `PARECUT_`, `.env` supported.
  - `get_settings() -> Settings` (lru-cached).
  - `create_app(settings: Settings | None = None) -> FastAPI` storing settings at `app.state.settings`.
  - Pytest fixtures `settings` (tmp dirs, `app_env="test"`, `mock_stage_delay_ms=0`, `seed_demo=False`) and `client` (httpx `AsyncClient` over `ASGITransport`).

- [ ] **Step 1: Scaffold the repo and install dependencies**

```bash
cd /home/ahmednabil/Desktop/Station/parecut
git init
uv init --python 3.12 --name parecut --no-workspace .
uv add fastapi "uvicorn[standard]" pydantic-settings sqlmodel "sqlalchemy[asyncio]" aiosqlite alembic "pwdlib[argon2]" pyjwt sse-starlette email-validator
uv add --dev pytest pytest-asyncio httpx asgi-lifespan
```

Add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

`.gitignore` must include `var/`, `web/node_modules/`, `web/dist/`, `.env`, `__pycache__/`, `.pytest_cache/`, `*.pyc`.

- [ ] **Step 2: Write the failing test**

`tests/test_health.py`:

```python
async def test_health(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

`tests/conftest.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(
        app_env="test",
        secret_key="test-secret",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        storage_dir=tmp_path / "storage",
        mock_stage_delay_ms=0,
        seed_demo=False,
    )


@pytest.fixture
async def app(settings):
    return create_app(settings)


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/test_health.py -v`
Expected: FAIL — `ModuleNotFoundError: app.main` (or missing route once the module is added).

- [ ] **Step 4: Implement settings and the app factory**

`app/config.py`: `Settings` as specified, with `model_config = SettingsConfigDict(env_file=".env", env_prefix="PARECUT_")` and `@lru_cache def get_settings()`.

`app/main.py`:

```python
def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Parecut", version="0.1.0")
    app.state.settings = settings
    settings.storage_dir.mkdir(parents=True, exist_ok=True)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
```

`.env.example` lists every `PARECUT_*` variable with its default.

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_health.py -v`
Expected: PASS (1 passed).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock .gitignore .env.example app tests
git commit -m "chore: scaffold FastAPI project, settings, and test harness"
```

---

## Task 2: Database Engine, Models, Migrations

**Files:**
- Create: `app/db.py`, `app/models.py`, `alembic/` (async template), `alembic.ini`, `tests/test_models.py`
- Modify: `tests/conftest.py`, `app/main.py`

**Interfaces:**
- Consumes: `Settings` from Task 1.
- Produces:
  - `create_engine(settings: Settings) -> AsyncEngine`
  - `create_db_and_tables(engine: AsyncEngine) -> None` (tests/dev bootstrap; production uses Alembic)
  - `async def get_session(request: Request) -> AsyncIterator[AsyncSession]`
  - SQLModel classes `User`, `UserProfile`, `CreditLedger`, `Job`, `JobArtifact` with the exact columns from spec §5.3. `Job.pipeline_config`, `Job.speaker_roles`, `Job.stage_states` are `dict` columns (`Column(JSON)`). `User.email` is unique and indexed. Decimal columns use `Numeric(10, 2)`.
  - `app.state.engine`, `app.state.sessionmaker`, `app.state.settings` on the FastAPI app.

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:

```python
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.models import CreditLedger, User, UserProfile


async def test_user_profile_and_ledger_round_trip(app):
    async with app.state.sessionmaker() as session:
        user = User(email="a@example.com", hashed_password="x", full_name="A")
        session.add(user)
        await session.flush()
        session.add(UserProfile(user_id=user.id, credit_balance_minutes=Decimal("30")))
        session.add(CreditLedger(user_id=user.id, delta_minutes=Decimal("30"), reason="signup_bonus"))
        await session.commit()

        found = (await session.exec(select(User).where(User.email == "a@example.com"))).one()
        profile = await session.get(UserProfile, found.id)
        assert profile.credit_balance_minutes == Decimal("30.00")


async def test_user_email_is_unique(app):
    async with app.state.sessionmaker() as session:
        session.add(User(email="dup@example.com", hashed_password="x", full_name="A"))
        await session.commit()
        session.add(User(email="dup@example.com", hashed_password="y", full_name="B"))
        with pytest.raises(IntegrityError):
            await session.commit()
```

Update `tests/conftest.py` so the `app` fixture creates the engine and tables before yielding:

```python
@pytest.fixture
async def app(settings):
    application = create_app(settings)
    await create_db_and_tables(application.state.engine)
    yield application
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL — `app.models` / `create_db_and_tables` missing.

- [ ] **Step 3: Implement the engine and models**

`app/db.py`:

```python
def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(settings.database_url, echo=False)

async def create_db_and_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session
```

`create_app` must create `app.state.engine = create_engine(settings)` and `app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)`.

Define models exactly as spec §5.3, with `id` defaulting to `str(uuid4())`, UTC `datetime` defaults (`datetime.now(timezone.utc)`), and `ondelete="CASCADE"` FKs. `Job.status` defaults to `"queued"`, `fps` to `"25"`.

- [ ] **Step 4: Create and verify the initial Alembic migration**

```bash
uv run alembic init -t async alembic
```

Edit `alembic/env.py` to read `get_settings().database_url` into `config.set_main_option("sqlalchemy.url", ...)` and set `target_metadata = SQLModel.metadata` (import `app.models`). Then:

```bash
uv run alembic revision --autogenerate -m "initial schema"
uv run alembic upgrade head
```

Expected: `var/parecut.db` created with five tables.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add app/db.py app/models.py app/main.py alembic alembic.ini tests
git commit -m "feat: add database engine, SQLModel tables, and initial migration"
```

---

## Task 3: Shared Engine Schemas

**Files:**
- Create: `parecut_engine/__init__.py`, `parecut_engine/schemas.py`, `tests/test_schemas.py`

**Interfaces:**
- Consumes: nothing from the app layer (Pydantic only).
- Produces:
  - `SpeakerRole = Literal["presenter", "feeder", "cohost"]`
  - `StageName = Literal["noise_reduction", "enhance", "separate_music", "separate_speakers", "transcribe", "rough_cut"]`
  - `PipelineConfig` with booleans `noise_reduction/enhance/separate_music/separate_speakers/transcribe/rough_cut` (all default `True`) and `enhance_mix: float = 0.8` (`ge=0, le=1`); validator rejects `rough_cut=True, transcribe=False` with message `"rough_cut requires transcribe"`.
  - `StageState { status: Literal["pending","running","completed","skipped","failed"], percent: int = 0, started_at: datetime|None, completed_at: datetime|None }`
  - `JobEvent { type: Literal["snapshot","job.status","stage.started","stage.progress","stage.completed","job.completed","job.failed"], job_id: str, stage: str|None, percent: int|None, message: str|None, at: datetime }`
  - `TranscriptSegment { speaker: str, start: float, end: float, text: str }`
  - `Transcript { speakers: list[str], segments: list[TranscriptSegment] }`
  - `CutRange { start: float, end: float, action: Literal["keep","remove"], reason: str, speaker: str|None, text: str|None }`
  - `RoughCutMeta { source_filename: str, duration_seconds: float, fps: str, sample_rate: int|None, estimated_duration_seconds: float }`

- [ ] **Step 1: Write the failing test**

`tests/test_schemas.py`:

```python
import pytest
from pydantic import ValidationError

from parecut_engine.schemas import JobEvent, PipelineConfig


def test_pipeline_defaults_are_full_run():
    config = PipelineConfig()
    assert config.rough_cut is True
    assert config.enhance_mix == 0.8


def test_rough_cut_requires_transcribe():
    with pytest.raises(ValidationError, match="rough_cut requires transcribe"):
        PipelineConfig(transcribe=False, rough_cut=True)


def test_enhance_mix_is_bounded():
    with pytest.raises(ValidationError):
        PipelineConfig(enhance_mix=1.5)


def test_job_event_has_timestamp():
    event = JobEvent(type="stage.progress", job_id="j1", stage="enhance", percent=50)
    assert event.at.tzinfo is not None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_schemas.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the schemas**

Use `field_validator`/`model_validator(mode="after")` for the cross-field rule and `Field(default_factory=lambda: datetime.now(timezone.utc))` for `at`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_schemas.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add parecut_engine tests/test_schemas.py
git commit -m "feat: add shared pipeline, transcript, and event schemas"
```

---

## Task 4: Password Hashing and Session Tokens

**Files:**
- Create: `app/security.py`, `tests/test_security.py`

**Interfaces:**
- Consumes: `Settings`.
- Produces:
  - `hash_password(password: str) -> str`
  - `verify_password(password: str, hashed: str) -> bool`
  - `create_session_token(user_id: str, settings: Settings) -> str` (claims `sub`, `exp`, `iat`)
  - `decode_session_token(token: str, settings: Settings) -> str | None`
  - `set_session_cookie(response: Response, token: str, settings: Settings) -> None`
  - `clear_session_cookie(response: Response, settings: Settings) -> None`

- [ ] **Step 1: Write the failing test**

`tests/test_security.py`:

```python
from app.security import (
    create_session_token,
    decode_session_token,
    hash_password,
    verify_password,
)


def test_password_hash_round_trip(settings):
    hashed = hash_password("correct horse")
    assert hashed != "correct horse"
    assert verify_password("correct horse", hashed)
    assert not verify_password("wrong", hashed)


def test_session_token_round_trip(settings):
    token = create_session_token("user-123", settings)
    assert decode_session_token(token, settings) == "user-123"


def test_expired_token_is_rejected(settings):
    settings.session_ttl_days = -1
    token = create_session_token("user-123", settings)
    assert decode_session_token(token, settings) is None


def test_tampered_token_is_rejected(settings):
    token = create_session_token("user-123", settings)
    assert decode_session_token(token + "x", settings) is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_security.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the security helpers**

Use `pwdlib.PasswordHash.recommended()` and `jwt.encode/decode` with `algorithms=["HS256"]`. Catch `jwt.PyJWTError` and return `None`. `set_session_cookie` sets `httponly=True, samesite="lax", secure=settings.app_env == "prod", max_age=settings.session_ttl_days * 86400, path="/"`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_security.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add app/security.py tests/test_security.py
git commit -m "feat: add Argon2 hashing and JWT session helpers"
```

---

## Task 5: Auth Endpoints, Current User, Signup Bonus

**Files:**
- Create: `app/schemas.py`, `app/deps.py`, `app/services/__init__.py`, `app/services/credits.py`, `app/routers/__init__.py`, `app/routers/auth.py`, `tests/test_auth.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `User`, `UserProfile`, `CreditLedger`, `get_session`, security helpers.
- Produces:
  - API schemas: `UserRead { id, email, full_name, avatar_url, created_at }`, `ProfileRead { credit_balance_minutes: float, default_fps, default_enhance_mix, default_silence_pad_ms }`, `SessionUser { user: UserRead, profile: ProfileRead }`, plus `JobRead`, `ArtifactRead`, `LedgerRead { id, job_id, delta_minutes: float, reason, created_at }`, and `ProfileResponse { user, profile, jobs, ledger }` so Task 6 can build the profile payload. Monetary fields are exposed as `float` in API responses while the database keeps `Decimal`.
  - `async def get_current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User` (401 "Not authenticated").
  - `async def get_current_user_optional(...) -> User | None`.
  - `async def add_ledger_entry(session, profile, *, delta: Decimal, reason: str, job_id: str | None = None) -> CreditLedger` — writes one row and applies `delta` to `profile.credit_balance_minutes`.
  - `def reserve_minutes(duration_seconds: float | None) -> Decimal` — `max(1, ceil(duration/60))`.
  - Routes: `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout` (204), `GET /api/auth/me`.

- [ ] **Step 1: Write the failing test**

`tests/test_auth.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_auth.py -v`
Expected: FAIL — routes/module missing (404/import error).

- [ ] **Step 3: Implement auth**

Register: normalize email (`strip().lower()`), reject duplicates with 409, hash password, create `User`, `flush`, create `UserProfile` with `settings.signup_bonus_minutes`, `add_ledger_entry(..., reason="signup_bonus")`, `commit`, set cookie, return 201 `SessionUser`. Login: generic 401 detail `"Invalid email or password"`. `/me`: load profile or 401.

`app/schemas.py` also defines `ProfileResponse` now (used in Task 6) with `user`, `profile`, `jobs: list[JobRead]`, `ledger: list[LedgerRead]`; define `LedgerRead { id, job_id, delta_minutes, reason, created_at }` and forward-declare `JobRead`/`ArtifactRead` in Task 8/9.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_auth.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add app tests/test_auth.py
git commit -m "feat: add register, login, logout, and session endpoint"
```

---

## Task 6: Profile and Preferences Endpoints

**Files:**
- Create: `app/routers/profile.py`, `tests/test_profile.py`
- Modify: `app/main.py`, `app/schemas.py`

**Interfaces:**
- Consumes: `get_current_user`, `ProfileResponse` fields, `UserProfile`, `Job`, `CreditLedger`.
- Produces:
  - `GET /api/profile` → `ProfileResponse` with the 20 newest ledger rows and 10 newest jobs.
  - `PATCH /api/profile` body `ProfileUpdate { full_name?: str, default_fps?: Literal["24","25","29.97","30","60"], default_enhance_mix?: int ge=0 le=100, default_silence_pad_ms?: int ge=0 le=2000 }` → updated `ProfileResponse`.
  - `to_job_read(job, artifacts) -> JobRead` lives in `app/schemas.py`, with an empty artifact list until Task 9 populates it.

- [ ] **Step 1: Write the failing test**

`tests/test_profile.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_profile.py -v`
Expected: FAIL — 404.

- [ ] **Step 3: Implement the profile router**

Merge only provided fields. Return fresh `ProfileResponse` built from user, profile, jobs newest-first limit 10, ledger newest-first limit 20.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_profile.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add app tests/test_profile.py
git commit -m "feat: add profile read and preferences update endpoints"
```

---

## Task 7: Local Object Storage and Upload Endpoints

**Files:**
- Create: `app/storage.py`, `app/routers/uploads.py`, `tests/test_uploads.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `Settings`, `get_current_user`.
- Produces:
  - `AudioMetadata { duration_seconds: float, sample_rate: int, channels: int }`
  - `InvalidToken(Exception)`
  - `ObjectStorage` protocol: `put(key, data, content_type)`, `get(key) -> bytes`, `copy(src, dst)`, `delete(key)`, `exists(key) -> bool`, `size(key) -> int`, `metadata(key) -> AudioMetadata | None`, `signed_upload_url(key, ttl_seconds) -> str`, `signed_download_url(key, filename, ttl_seconds) -> str`, `verify_upload_token(token) -> str`, `verify_download_token(token) -> tuple[str, str]`.
  - `LocalObjectStorage(root: Path, secret_key: str)` implementing all of the above with HMAC-SHA256 tokens; no path traversal (`..` rejected); ffprobe via `subprocess.run` with 10 s timeout, returning `None` on any failure.
  - `POST /api/uploads` (authenticated) body `{filename, size_bytes, content_type}` → 201 `{upload_url, upload_key, expires_at}`; rejects unsupported extension and `size_bytes > settings.max_upload_bytes` (413). The signed PUT and GET token routes authenticate by token alone.
  - `PUT /api/uploads/{token}` stores raw body (403 on invalid/expired/purpose mismatch).
  - `GET /api/uploads/download/{token}` streams the file with `Content-Disposition: attachment; filename="..."` (403 on invalid).
  - `app.state.storage` and `def get_storage(request: Request) -> ObjectStorage` (reads `request.app.state.storage`).

- [ ] **Step 1: Write the failing test**

`tests/test_uploads.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_uploads.py -v`
Expected: FAIL — 404/import error.

- [ ] **Step 3: Implement storage and upload routes**

Token format: `base64url(json({"k": key, "e": epoch, "p": "put"|"get", "f": filename})) + "." + base64url(hmac_sha256(secret, payload))`. Verify with `hmac.compare_digest`, expiry `e >= now`, and purpose equality. Reject keys containing `..`.

Safe filename: keep `[A-Za-z0-9._-]`, otherwise replace with `_`. Upload key: `uploads/{uuid4().hex}/{safe_name}`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_uploads.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add app/storage.py app/routers/uploads.py app/main.py tests/test_uploads.py
git commit -m "feat: add local object storage and signed upload endpoints"
```

---

## Task 8: Job Creation, Credits, and Stage Initialization

**Files:**
- Create: `app/services/stages.py`, `app/services/jobs.py`, `app/services/pipeline.py`, `app/routers/jobs.py`, `tests/test_job_create.py`, `tests/helpers.py`
- Modify: `app/main.py`, `app/schemas.py`

**Interfaces:**
- Consumes: `PipelineConfig`, `StageState`, storage `metadata`, `reserve_minutes`, `add_ledger_entry`, models.
- Produces:
  - `STAGE_ORDER = ["noise_reduction","enhance","separate_music","separate_speakers","transcribe","rough_cut"]`
  - `enabled_stages(config: PipelineConfig) -> list[str]`
  - `initial_stage_states(config: PipelineConfig) -> dict[str, StageState]` (unselected → `skipped`, selected → `pending`, dict in `STAGE_ORDER`)
  - `class PipelineRunner(Protocol): async def spawn(self, job_id: str) -> None`
  - `class NullPipelineRunner: async def spawn(self, job_id: str) -> None: return None`
  - `async def create_job(session, user, storage, runner, settings, data: JobCreate) -> Job` — validates upload key exists, probes metadata, checks balance (402), reserves credits (`job_reserve` negative), writes job with `stage_states`, commits, then `await runner.spawn(job.id)`.
  - `JobCreate { upload_key: str, source_filename: str, fps: FPS, pipeline: PipelineConfig }` where `FPS = Literal["24","25","29.97","30","60"]`.
  - Reuses `JobRead` / `ArtifactRead` defined in Task 5: `JobRead { id, status, source_filename, duration_seconds, sample_rate, fps, pipeline_config, speaker_roles, stage_states, error_code, created_at, started_at, completed_at, artifacts }` and `ArtifactRead { id, kind, label, format, size_bytes, download_url }`.
  - `POST /api/jobs` → 201 `JobRead`; 402 returns a `JSONResponse` with status 402 and top-level body `{"detail": "Insufficient credits", "required_minutes": ..., "available_minutes": ...}`; 404 unknown upload key; 422 invalid pipeline.
  - `app.state.runner` (defaults to `NullPipelineRunner`) and `def get_runner(request: Request) -> PipelineRunner`.
  - Helpers in `tests/helpers.py`: `make_wav(seconds=2, rate=48000) -> bytes` (stdlib `wave`), `async def register(client, email="a@example.com") -> None`, `async def upload(client, data: bytes, filename="clip.wav") -> str` returning `upload_key`.

- [ ] **Step 1: Write the failing test**

`tests/test_job_create.py`:

```python
from decimal import Decimal

from sqlmodel import select

from app.models import CreditLedger, Job
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
        ledger = (await session.exec(select(CreditLedger).where(CreditLedger.reason == "job_reserve"))).one()
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_job_create.py -v`
Expected: FAIL — routes/helpers missing.

- [ ] **Step 3: Implement stage helpers, runner protocol, and job creation**

Use an async transaction: load profile (`session.get`), compare balance, `add_ledger_entry(delta=-minutes, reason="job_reserve", job_id=job.id)`, create job, commit. Return the 402 as a `JSONResponse(status_code=402, content={...})` so `required_minutes` and `available_minutes` are top-level keys. On spawn failure mark failed + refund (best effort).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_job_create.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add app tests/test_job_create.py tests/helpers.py
git commit -m "feat: add job creation with credit reservation and stage state"
```

---

## Task 9: Job List, Detail, Ownership, and Download

**Files:**
- Create: `tests/test_jobs_read.py`
- Modify: `app/routers/jobs.py`, `app/services/jobs.py`, `app/schemas.py`

**Interfaces:**
- Consumes: `JobRead`, `ArtifactRead`, storage signed download URLs.
- Produces:
  - `async def load_job(session, user, job_id) -> Job` raising 404 when absent or owned by someone else.
  - `GET /api/jobs?limit=20&offset=0` → `list[JobRead]` newest first, max limit 100.
  - `GET /api/jobs/{id}` → `JobRead` with artifacts sorted by `created_at`.
  - `GET /api/jobs/{id}/artifacts/{artifact_id}/download` → 302 to `storage.signed_download_url(...)`; 404 when job or artifact is not owned.
  - `to_job_read(job, artifacts) -> JobRead` fills `download_url = f"/api/jobs/{job.id}/artifacts/{artifact.id}/download"`.

- [ ] **Step 1: Write the failing test**

`tests/test_jobs_read.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_jobs_read.py -v`
Expected: FAIL — 404/405.

- [ ] **Step 3: Implement list, detail, and download**

Sort jobs by `created_at.desc()`. Eagerly load artifacts per job with one `select(JobArtifact).where(JobArtifact.job_id.in_(ids))` in the list path to avoid N+1.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_jobs_read.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add app tests/test_jobs_read.py
git commit -m "feat: add job listing, detail ownership, and signed downloads"
```

---

## Task 10: In-Memory Event Broker and SSE Endpoint

**Files:**
- Create: `app/events.py`, `tests/test_events.py`
- Modify: `app/main.py`, `app/routers/jobs.py`

**Interfaces:**
- Consumes: `JobEvent`, `load_job`.
- Produces:
  - `class EventBroker(Protocol): async def publish(self, job_id: str, event: JobEvent) -> None` and `def subscribe(self, job_id: str) -> AsyncIterator[JobEvent]`.
  - `InMemoryEventBroker` with one `asyncio.Queue` per active subscriber and safe unsubscribe.
  - `app.state.broker` and `def get_broker(request: Request) -> EventBroker`.
  - `GET /api/jobs/{id}/events` as `EventSourceResponse`: subscribes first, sends `event: snapshot` with the full `JobRead`; if job is terminal, ends; otherwise streams events with `event: <event.type>`, `data: <json>`, and `ping` every 15 s.

- [ ] **Step 1: Write the failing test**

`tests/test_events.py`:

```python
import asyncio
import json

from parecut_engine.schemas import JobEvent
from tests.helpers import make_wav, register, upload


async def test_sse_sends_snapshot_then_live_event(app, client):
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

    async with client.stream("GET", f"/api/jobs/{job_id}/events") as response:
        assert response.status_code == 200
        lines = response.aiter_lines()

        event_line = await anext(lines)
        while not event_line.startswith("event:"):
            event_line = await anext(lines)
        assert "snapshot" in event_line
        data_line = await anext(lines)
        assert json.loads(data_line.removeprefix("data: "))["id"] == job_id

        await app.state.broker.publish(
            job_id,
            JobEvent(type="stage.progress", job_id=job_id, stage="enhance", percent=50),
        )

        found = False
        for _ in range(20):
            line = await asyncio.wait_for(anext(lines), timeout=2)
            if "stage.progress" in line:
                found = True
                break
        assert found
```

The snapshot must be read before publishing, so the live event is deterministic.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_events.py -v`
Expected: FAIL — route missing.

- [ ] **Step 3: Implement the broker and SSE route**

`subscribe` is an async generator that registers a queue on first iteration and removes it in `finally`. `publish` uses `put_nowait` for every subscriber queue and ignores missing subscribers. Serialize with `JobEvent.model_dump_json()`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_events.py -v`
Expected: PASS (1 passed). If it hangs, the endpoint is not closing when the client disconnects; use `request.is_disconnected` in the stream loop.

- [ ] **Step 5: Commit**

```bash
git add app/events.py app/main.py app/routers/jobs.py tests/test_events.py
git commit -m "feat: add event broker and SSE job progress stream"
```

---

## Task 11: Timecode, Cut Plan, and Transcript Renderers

**Files:**
- Create: `app/renderers.py`, `app/demo_data.py`, `tests/test_renderers.py`

**Interfaces:**
- Consumes: `Transcript`, `TranscriptSegment`, `CutRange`, `SpeakerRole`.
- Produces:
  - `FPS_VALUES = {"24": 24.0, "25": 25.0, "29.97": 30000/1001, "30": 30.0, "60": 60.0}`
  - `fps_value(fps: str) -> float`
  - `frame_number(seconds: float, fps: str) -> int` — `int(seconds * fps_value(fps) + 0.5)` (half-up, no banker's rounding)
  - `format_clock(seconds: float) -> str` — `HH:MM:SS.mmm`
  - `format_smpte(seconds: float, fps: str) -> str` — `HH:MM:SS:FF` using nominal integer FPS (`29.97` → 30) for both fields
  - `build_cut_plan(transcript: Transcript, roles: dict[str, SpeakerRole]) -> list[CutRange]` — gaps of any positive duration become `remove/SILENCE`; `feeder` segments become `remove/FEEDER_PROMPT`; all other speakers become `keep/BEST_TAKE`.
  - `render_transcript(transcript, cut_plan, roles, fps, *, variant: Literal["before","after"], fmt: Literal["md","srt","vtt","json"]) -> str` — before keeps source times; after uses assembled times for SRT/VTT/MD and includes both source and assembled in JSON. Feeder/removed segments are omitted from after. SRT/VTT cue text is prefixed with `[SPEAKER_XX]` so tests and users can tell speakers apart even when lines repeat.
  - `demo_transcript(duration_seconds: float | None) -> Transcript` in `app/demo_data.py`: fixed 7-segment feeder/presenter conversation (two speakers) scaled from a 24.72 s template into the job duration; when duration is `None`, use 24.72. Segments (start, end, speaker, text):
    - 2.5–5.0 `SPEAKER_02` "Today we're going to talk about three-point lighting."
    - 5.0–8.0 `SPEAKER_01` "Today we're gonna— sorry, let me go again."
    - 8.48–11.16 `SPEAKER_01` "Today we're going to talk about three-point lighting."
    - 11.16–15.4 `SPEAKER_02` "The key light is your primary light source on set."
    - 15.4–19.08 `SPEAKER_01` "The key light is the main light source."
    - 19.08–24.72 `SPEAKER_01` "The key light is your primary light source on set."

- [ ] **Step 1: Write the failing test**

`tests/test_renderers.py`:

```python
from app.demo_data import demo_transcript
from app.renderers import (
    FPS_VALUES,
    build_cut_plan,
    format_clock,
    format_smpte,
    frame_number,
    render_transcript,
)


def test_timecode_conversions():
    assert frame_number(1.0, "25") == 25
    assert format_smpte(1.04, "25") == "00:00:01:01"
    assert format_clock(8.48) == "00:00:08.480"
    assert FPS_VALUES["29.97"] > 29.9


def test_before_renderer_keeps_feeder_and_source_time():
    transcript = demo_transcript(24.72)
    roles = {"SPEAKER_01": "presenter", "SPEAKER_02": "feeder"}
    plan = build_cut_plan(transcript, roles)
    srt = render_transcript(
        transcript, plan, roles, "25", variant="before", fmt="srt"
    )
    assert "Today we're going to talk about three-point lighting." in srt
    assert "[SPEAKER_02]" in srt
    assert "00:00:02,500 --> 00:00:05,000" in srt


def test_after_renderer_omits_feeder_and_starts_at_zero():
    transcript = demo_transcript(24.72)
    roles = {"SPEAKER_01": "presenter", "SPEAKER_02": "feeder"}
    plan = build_cut_plan(transcript, roles)
    srt = render_transcript(transcript, plan, roles, "25", variant="after", fmt="srt")
    assert "SPEAKER_02" not in srt
    assert "00:00:00,000 --> " in srt


def test_cut_plan_marks_silence_and_feeder():
    transcript = demo_transcript(24.72)
    plan = build_cut_plan(transcript, {"SPEAKER_01": "presenter", "SPEAKER_02": "feeder"})
    assert any(range_.reason == "SILENCE" for range_ in plan)
    assert any(range_.reason == "FEEDER_PROMPT" for range_ in plan)
    assert any(range_.action == "keep" for range_ in plan)


def test_demo_transcript_scales_to_duration():
    transcript = demo_transcript(12.0)
    assert transcript.segments[-1].end <= 12.0
    assert {segment.speaker for segment in transcript.segments} == {"SPEAKER_01", "SPEAKER_02"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_renderers.py -v`
Expected: FAIL — modules missing.

- [ ] **Step 3: Implement demo data and renderers**

SRT timestamps use `HH:MM:SS,mmm`; VTT use `HH:MM:SS.mmm` and a `WEBVTT` header. Markdown before format: `**[00:00:02.500 – 00:00:05.000] SPEAKER_02 (feeder):** text`. After Markdown includes assembled range only. JSON before is `Transcript.model_dump()`; JSON after is `{"segments": [{..., "source_start", "source_end", "assembled_start", "assembled_end"}], "total_duration": ...}`.

Assembled times are cumulative over kept ranges in source order.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_renderers.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add app/renderers.py app/demo_data.py tests/test_renderers.py
git commit -m "feat: add timecode, cut plan, demo transcript, and transcript renderers"
```

---

## Task 12: `ROUGH-CUT.md` Renderer

**Files:**
- Modify: `app/renderers.py`
- Create: `tests/test_roughcut_md.py`

**Interfaces:**
- Consumes: `CutRange`, `RoughCutMeta`, roles, `format_smpte`, `format_clock`.
- Produces:
  - `render_rough_cut_md(meta: RoughCutMeta, plan: list[CutRange], roles: dict[str, SpeakerRole]) -> str`
  - Output sections exactly: `# PARECUT ROUGH-CUT SPECIFICATION`, `## 1. Source Media & Timeline Metadata`, `## 2. Speaker Map`, `## 3. Machine-Readable Cut List`, `### 3.1 KEEP Ranges`, `### 3.2 REMOVE Ranges`, `## 4. Full Chronological Audit Log`, `## 5. Ready-to-Use Coding Agent Instructions`.
  - Metadata includes filename, duration clock + seconds + total frames, FPS, sample rate, estimated duration after cut and percent removed, recommended audio track `speaker_01_presenter_enhanced.wav`.
  - Tables use columns from spec §5.1 and include both `HH:MM:SS:FF` and seconds/frame columns.
  - New timeline TC in KEEP table is cumulative from 00:00:00:00.

- [ ] **Step 1: Write the failing test**

`tests/test_roughcut_md.py`:

```python
from app.demo_data import demo_transcript
from app.renderers import build_cut_plan, render_rough_cut_md
from parecut_engine.schemas import RoughCutMeta


def _render():
    transcript = demo_transcript(24.72)
    roles = {"SPEAKER_01": "presenter", "SPEAKER_02": "feeder"}
    meta = RoughCutMeta(
        source_filename="A001_C014_interview.mov",
        duration_seconds=24.72,
        fps="25",
        sample_rate=48000,
        estimated_duration_seconds=13.0,
    )
    return render_rough_cut_md(meta, build_cut_plan(transcript, roles), roles)


def test_rough_cut_has_required_sections_and_tables():
    output = _render()
    for heading in [
        "# PARECUT ROUGH-CUT SPECIFICATION",
        "## 1. Source Media & Timeline Metadata",
        "## 2. Speaker Map",
        "### 3.1 `KEEP` Ranges",
        "### 3.2 `REMOVE` Ranges",
        "## 4. Full Chronological Audit Log",
        "## 5. Ready-to-Use Coding Agent Instructions",
    ]:
        assert heading in output


def test_rough_cut_has_timecodes_reasons_and_agent_prompt():
    output = _render()
    assert "00:00:02:13" in output  # 2.5 s @ 25 fps, half-up frame rounding
    assert "FEEDER_PROMPT" in output
    assert "SILENCE" in output
    assert "mediaPool.AppendToTimeline" in output
    assert "A001_C014_interview.mov" in output
    assert "39.3%" in output  # 9.72 s removed of 24.72 s
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_roughcut_md.py -v`
Expected: FAIL — `render_rough_cut_md` missing.

- [ ] **Step 3: Implement the renderer**

Compute `removed = duration - sum(keep durations)`; `percent_removed = removed / duration * 100` formatted to one decimal. Keep rows use `plan` keep ranges in order; REMOVE rows use every remove range. The audit log lists all ranges in order with ✅/❌.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_roughcut_md.py -v`
Expected: PASS (2 passed). Adjust the percent assertion only if arithmetic differs; keep one decimal place.

- [ ] **Step 5: Commit**

```bash
git add app/renderers.py tests/test_roughcut_md.py
git commit -m "feat: render agent-ready ROUGH-CUT.md specification"
```

---

## Task 13: Mock Pipeline Runner and Artifact Writing

**Files:**
- Create: `app/services/roughcut.py`, `tests/test_pipeline.py`
- Modify: `app/services/pipeline.py`, `app/main.py`

**Interfaces:**
- Consumes: `STAGE_ORDER`, `enabled_stages`, `demo_transcript`, renderers, storage, broker, credits, models.
- Produces:
  - `async def write_before_artifacts(session, storage, job, transcript, settings) -> None` — writes canonical `jobs/{job.id}/transcript_raw.json` and registers it as the `transcript_before`/`json` artifact, plus `md`, `srt`, `vtt`; labels `Demo — Transcript (Before Cut)`.
  - `async def write_cut_outputs(session, storage, job, transcript, roles, settings) -> None` — writes `transcript_after.{md,srt,vtt,json}` and `ROUGH-CUT.md`; labels `Demo — Transcript (After Cut)` and `Demo — ROUGH-CUT.md`.
  - `async def regenerate_cut_outputs(session, storage, job, roles, settings) -> None` — loads canonical transcript JSON, deletes existing after/rough-cut artifact rows and files, rewrites them.
  - `MockPipelineRunner(sessionmaker, storage, broker, settings)` implementing `PipelineRunner.spawn` via `asyncio.create_task`, keeping task references on the instance.
  - Stage artifact mapping: `noise_reduction → 01_cleaned.wav (cleaned_audio)`, `enhance → 02_enhanced.wav (enhanced_audio)`, `separate_music → stem_music.wav + stem_dialogue.wav`, `separate_speakers → speaker_01.wav + speaker_02.wav (stem_speaker)`, `transcribe → write_before_artifacts(...)` and `speaker_roles = {SPEAKER_01: presenter, SPEAKER_02: presenter}`, `rough_cut → write_cut_outputs(...)`.
  - Audio artifacts copy `job.source_r2_key` via `storage.copy`; labels start with `Demo — `.
  - Runner sets `job.status`, timestamps, and `stage_states` before each publish; publishes `stage.started`, five `stage.progress` values `0/25/50/75/100`, `stage.completed`, then `job.completed`; on exception sets `failed`, `error_code="mock_pipeline_failed"`, refunds reserve, publishes `job.failed`.
  - `app.state.runner = MockPipelineRunner(...)` in `create_app`.

- [ ] **Step 1: Write the failing test**

`tests/test_pipeline.py`:

```python
import asyncio
from decimal import Decimal

from sqlmodel import select

from app.models import CreditLedger, Job, JobArtifact
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: FAIL — runner not implemented (jobs stay queued).

- [ ] **Step 3: Implement the runner and artifact writer**

Use `await asyncio.sleep(settings.mock_stage_delay_ms / 1000)` between progress ticks. Read the job fresh per stage inside its own session, commit before publishing. `write_before_artifacts` must write the canonical JSON during the `transcribe` stage so `write_cut_outputs` can render from it during `rough_cut`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add app/services/pipeline.py app/services/roughcut.py app/main.py tests/test_pipeline.py
git commit -m "feat: add mock pipeline runner with artifacts and credit settlement"
```

---

## Task 14: Speaker Role Override and Instant Regeneration

**Files:**
- Modify: `app/routers/jobs.py`, `app/services/roughcut.py`
- Create: `tests/test_speakers.py`

**Interfaces:**
- Consumes: `regenerate_cut_outputs`, canonical transcript artifact.
- Produces:
  - `PATCH /api/jobs/{id}/speakers` body `SpeakerRolesUpdate { roles: dict[str, SpeakerRole] }` → `JobRead`.
  - Rejects with 422 when the submitted key set differs from `job.speaker_roles` keys, message `"roles must match detected speakers"`.
  - Applies roles, commits, calls `regenerate_cut_outputs`, returns the refreshed job.
  - Works on completed jobs and on the seeded demo job.

- [ ] **Step 1: Write the failing test**

`tests/test_speakers.py`:

```python
from tests.helpers import make_wav, register, upload
from app.services.pipeline import MockPipelineRunner


async def _completed_job(app, client):
    await register(client)
    key = await upload(client, make_wav(4))
    created = await client.post(
        "/api/jobs",
        json={"upload_key": key, "source_filename": "clip.wav", "fps": "25", "pipeline": {}},
    )
    job_id = created.json()["id"]
    import asyncio

    for _ in range(60):
        body = (await client.get(f"/api/jobs/{job_id}")).json()
        if body["status"] == "completed":
            return body
        await asyncio.sleep(0.05)
    raise AssertionError("job did not complete")


async def _artifact_text(client, job, kind):
    artifact = next(a for a in job["artifacts"] if a["kind"] == kind and a["format"] == "srt")
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
    assert "FEEDER_PROMPT" in (await client.get(md["download_url"], follow_redirects=True)).text


async def test_unknown_speaker_keys_are_rejected(app, client):
    job = await _completed_job(app, client)
    response = await client.patch(
        f"/api/jobs/{job['id']}/speakers",
        json={"roles": {"SPEAKER_99": "feeder"}},
    )
    assert response.status_code == 422
    assert "roles must match detected speakers" in response.json()["detail"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_speakers.py -v`
Expected: FAIL — 405/404.

- [ ] **Step 3: Implement the endpoint and regeneration**

Delete replaced artifacts through `storage.delete` before inserting new rows; keep `transcript_before` untouched. Commit before rendering so storage errors surface as 500 without partially updating roles? Simpler: render first, then commit; either is acceptable, but the test requires consistency after success.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_speakers.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add app/routers/jobs.py app/services/roughcut.py tests/test_speakers.py
git commit -m "feat: regenerate cut outputs when speaker roles change"
```

---

## Task 15: Demo Seed and Startup Reconciliation

**Files:**
- Create: `app/seed.py`, `tests/test_seed.py`
- Modify: `app/main.py` (lifespan)

**Interfaces:**
- Consumes: all models, storage, renderers, `demo_transcript`.
- Produces:
  - `async def seed_demo(sessionmaker, storage, settings) -> None` — idempotent; creates `demo@parecut.app` / `parecut-demo`, profile with 30 minutes and signup ledger, fixed completed job `00000000-0000-4000-8000-000000000001` (duration 20.0 s, fps 25, full pipeline, both speakers presenter), 20 s demo WAV written with stdlib `wave` (48 kHz mono, low-volume sine), audio artifacts, transcript before/after (`Demo — ` labels), and `ROUGH-CUT.md`. Returns immediately if the user exists.
  - `async def reconcile_orphan_jobs(sessionmaker, settings) -> None` — jobs with status `queued` or `running` become `failed`, `error_code="server_restart"`, and their reserve is refunded with reason `job_refund` (skip if a refund row already exists for that job).
  - Lifespan in `create_app`: `seed_demo` when `settings.seed_demo`, then `reconcile_orphan_jobs`.

- [ ] **Step 1: Write the failing test**

`tests/test_seed.py`:

```python
from decimal import Decimal

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from app.config import Settings
from app.db import create_db_and_tables
from app.main import create_app
from app.models import CreditLedger, Job, JobArtifact
from app.seed import reconcile_orphan_jobs


async def test_seed_is_idempotent_and_logs_in(tmp_path):
    settings = Settings(
        app_env="test",
        secret_key="test-secret",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}",
        storage_dir=tmp_path / "storage",
        mock_stage_delay_ms=0,
        seed_demo=True,
    )
    app = create_app(settings)
    await create_db_and_tables(app.state.engine)
    async with LifespanManager(app):
        pass
    async with LifespanManager(app):  # second startup
        pass

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        login = await client.post(
            "/api/auth/login", json={"email": "demo@parecut.app", "password": "parecut-demo"}
        )
        assert login.status_code == 200
        profile = (await client.get("/api/profile")).json()
        assert len(profile["jobs"]) == 1
        assert profile["jobs"][0]["status"] == "completed"
        assert profile["jobs"][0]["artifacts"]

    async with app.state.sessionmaker() as session:
        assert len((await session.exec(select(Job))).all()) == 1
        assert len((await session.exec(select(JobArtifact))).all()) >= 9


async def test_reconcile_marks_running_job_failed_and_refunds(tmp_path):
    settings = Settings(
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}",
        storage_dir=tmp_path / "storage",
        seed_demo=False,
    )
    app = create_app(settings)
    await create_db_and_tables(app.state.engine)
    async with app.state.sessionmaker() as session:
        from app.models import User, UserProfile

        user = User(email="a@example.com", hashed_password="x", full_name="A")
        session.add(user)
        await session.flush()
        session.add(UserProfile(user_id=user.id, credit_balance_minutes=Decimal("10")))
        job = Job(user_id=user.id, status="running", source_filename="x.wav",
                  source_r2_key="uploads/x.wav", duration_seconds=120.0, fps="25")
        session.add(job)
        await session.commit()
        job_id = job.id

    await reconcile_orphan_jobs(app.state.sessionmaker, settings)

    async with app.state.sessionmaker() as session:
        job = await session.get(Job, job_id)
        profile = (await session.exec(select(UserProfile))).one()
        refund = (
            await session.exec(select(CreditLedger).where(CreditLedger.reason == "job_refund"))
        ).one()
        assert job.status == "failed"
        assert job.error_code == "server_restart"
        assert refund.delta_minutes == Decimal("2")
        assert profile.credit_balance_minutes == Decimal("12")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_seed.py -v`
Expected: FAIL — `app.seed` missing.

- [ ] **Step 3: Implement seed and reconciliation**

Build the demo job through the same artifact writer used by the pipeline so its output cannot drift. The demo WAV uses `wave.open(BytesIO(), "wb")` with `setnchannels(1)`, `setsampwidth(2)`, `setframerate(48000)`, and a 220 Hz sine at low amplitude; write bytes via `storage.put`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_seed.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add app/seed.py app/main.py tests/test_seed.py
git commit -m "feat: add idempotent demo seed and orphan job reconciliation"
```

---

## Task 16: Frontend Scaffold, Auth Client, Login, Register

**Files:**
- Create: `web/` (Vite scaffold), `web/src/api/client.ts`, `web/src/api/types.ts`, `web/src/auth/AuthProvider.tsx`, `web/src/pages/Login.tsx`, `web/src/pages/Register.tsx`, `web/src/styles.css`, `web/vite.config.ts`, `web/src/api/client.test.ts`, `web/src/pages/Login.test.tsx`
- Modify: `web/package.json`

**Interfaces:**
- Consumes: backend auth API (`/api/auth/*`).
- Produces:
  - `ApiError extends Error { status: number }`
  - `apiFetch<T>(path: string, init?: RequestInit): Promise<T>` — sets JSON content type when a body is present, `credentials: "include"`, parses `detail` on failure.
  - Types: `SessionUser`, `UserRead`, `ProfileRead`, `JobStatus`, `SpeakerRole`, `StageState`, `PipelineConfig`, `Job`, `Artifact`, `ProfileResponse`.
  - `AuthProvider` exposing `{ me: SessionUser | null, isLoading: boolean }` via `useAuth()`; query key `["me"]`.
  - `Login` and `Register` pages at `/login` and `/register`, redirect to `?next=` or `/`.
  - npm scripts `dev`, `build`, `typecheck` (`tsc --noEmit`), `test` (`vitest run`).

- [ ] **Step 1: Scaffold the frontend and install dependencies**

```bash
cd /home/ahmednabil/Desktop/Station/parecut
npm create vite@latest web -- --template react-ts
cd web
npm install
npm install react-router-dom @tanstack/react-query react-markdown remark-gfm lucide-react clsx @fontsource-variable/inter @fontsource/jetbrains-mono
npm install -D tailwindcss @tailwindcss/vite vitest jsdom @testing-library/react @testing-library/user-event @testing-library/jest-dom
```

Add `"typecheck": "tsc --noEmit"`, `"test": "vitest run"`. Add `test: { environment: "jsdom", setupFiles: "./src/test-setup.ts" }` to `vite.config.ts`, and configure the `/api` proxy to `http://127.0.0.1:8000`. Replace `src/index.css` usage with `src/styles.css` containing `@import "tailwindcss";` and a dark theme token block.

- [ ] **Step 2: Write the failing tests**

`web/src/api/client.test.ts`:

```ts
import { describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch } from "./client";

describe("apiFetch", () => {
  it("throws ApiError with the server detail", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Invalid email or password" }), {
        status: 401,
        headers: { "content-type": "application/json" },
      }),
    ));
    await expect(apiFetch("/api/auth/login")).rejects.toMatchObject({
      status: 401,
      message: "Invalid email or password",
    });
  });
});
```

`web/src/pages/Login.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Login from "./Login";

describe("Login", () => {
  it("shows the server error on bad credentials", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Invalid email or password" }), {
        status: 401,
        headers: { "content-type": "application/json" },
      }),
    ));
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <Login />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await userEvent.type(screen.getByLabelText(/email/i), "a@example.com");
    await userEvent.type(screen.getByLabelText(/password/i), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText("Invalid email or password")).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd web && npm test`
Expected: FAIL — modules missing.

- [ ] **Step 4: Implement the client, provider, and auth pages**

Login form fields must have labels matching `/email/i` and `/password/i`; submit button text `Sign in`. On success: `queryClient.setQueryData(["me"], data)` and navigate. Register mirrors it with name/email/password. Add `useAuth` that reads the `["me"]` query with `retry: false` and treats 401 as unauthenticated.

- [ ] **Step 5: Run the frontend gates**

Run: `cd web && npm test && npm run typecheck && npm run build`
Expected: 2 tests pass; typecheck and build exit 0.

- [ ] **Step 6: Commit**

```bash
git add web
git commit -m "feat(web): scaffold SPA with API client, auth provider, login and register"
```

---

## Task 17: App Shell, Dashboard, and Settings

**Files:**
- Create: `web/src/App.tsx`, `web/src/router.tsx`, `web/src/auth/RequireAuth.tsx`, `web/src/components/AppShell.tsx`, `web/src/components/StatusPill.tsx`, `web/src/pages/Dashboard.tsx`, `web/src/pages/Settings.tsx`, `web/src/lib/format.ts`, `web/src/lib/format.test.ts`
- Modify: `web/src/main.tsx`

**Interfaces:**
- Consumes: `useAuth`, `/api/profile`, `/api/profile` PATCH, `Job` type.
- Produces:
  - Routes: `/login`, `/register`, `/` (Dashboard), `/new` (placeholder page until Task 18), `/jobs/:id` (placeholder until Task 19), `/settings`; unknown paths redirect to `/`.
  - `RequireAuth` redirects unauthenticated users to `/login?next=<path>`.
  - `AppShell` with product mark, nav links (`Dashboard`, `New job`, `Settings`), credit balance, and sign-out button.
  - `formatClock(seconds: number) -> string`, `formatFileSize(bytes: number) -> string`, `formatDuration(seconds: number | null) -> string`.
  - `StatusPill` maps `queued/running/completed/failed` to label + color classes.
  - Dashboard: credit card, recent job rows linking to `/jobs/:id`, empty state.
  - Settings: name, default FPS select, enhance mix 0–100 slider, silence pad number, save mutation, success/error notice.

- [ ] **Step 1: Write the failing test**

`web/src/lib/format.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { formatClock, formatDuration, formatFileSize } from "./format";

describe("format helpers", () => {
  it("formats clock time with milliseconds", () => {
    expect(formatClock(8.48)).toBe("00:00:08.480");
    expect(formatClock(3725.1)).toBe("01:02:05.100");
  });

  it("formats unknown durations and byte sizes", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatFileSize(1536)).toBe("1.5 KB");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd web && npm test -- format`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement shell, router, dashboard, settings**

Use TanStack Query for `/api/profile` (`["profile"]`), invalidate `["profile"]` after PATCH. Sign-out calls `/api/auth/logout`, clears `["me"]`, navigates to `/login`. The shell shows `profile.profile.credit_balance_minutes` with one decimal.

- [ ] **Step 4: Run the gates**

Run: `cd web && npm test && npm run typecheck && npm run build`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web
git commit -m "feat(web): add app shell, dashboard, settings, and formatting helpers"
```

---

## Task 18: New Job Flow — Upload, Pipeline Config, 402 Handling

**Files:**
- Create: `web/src/pages/NewJob.tsx`, `web/src/components/Dropzone.tsx`, `web/src/components/PipelineToggles.tsx`, `web/src/lib/credits.ts`, `web/src/lib/credits.test.ts`, `web/src/lib/audio.ts`
- Modify: `web/src/router.tsx`

**Interfaces:**
- Consumes: `POST /api/uploads`, signed PUT, `POST /api/jobs`, `ApiError`, profile defaults.
- Produces:
  - `estimateCredits(durationSeconds: number | null) -> number` — `Math.max(1, Math.ceil((durationSeconds ?? 0) / 60))`.
  - `validatePipeline(config: PipelineConfig) -> string | null` — returns `"Rough cut needs transcription enabled."` when `rough_cut && !transcribe`.
  - `readAudioDuration(file: File) -> Promise<number | null>` using an object URL and `<audio>` metadata, always revoking the URL.
  - `Dropzone` accepting audio/video extensions, showing filename, size, upload percentage; parent owns the upload.
  - `NewJob` page: upload → pipeline toggles (descriptions from spec), enhance mix slider, FPS select, estimated cost, submit; 402 renders `Insufficient credits: need N, have M.` and keeps form state.
  - After success, navigate to `/jobs/{id}`.

- [ ] **Step 1: Write the failing tests**

`web/src/lib/credits.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { estimateCredits, validatePipeline } from "./credits";

describe("estimateCredits", () => {
  it("rounds up to whole minutes with a one-minute floor", () => {
    expect(estimateCredits(null)).toBe(1);
    expect(estimateCredits(2)).toBe(1);
    expect(estimateCredits(61)).toBe(2);
  });
});

describe("validatePipeline", () => {
  it("rejects rough cut without transcription", () => {
    expect(validatePipeline({ transcribe: false, rough_cut: true } as never))
      .toBe("Rough cut needs transcription enabled.");
    expect(validatePipeline({ transcribe: true, rough_cut: true } as never)).toBeNull();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd web && npm test -- credits`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the upload flow and page**

Upload with `XMLHttpRequest` so `upload.onprogress` is available; resolve with `upload_key`. Upload URL returned by the API is same-origin, so send cookies and `Content-Type` from the file. Disable submit until upload is complete and pipeline is valid. Show file type/size validation before requesting a presign.

- [ ] **Step 4: Run the gates**

Run: `cd web && npm test && npm run typecheck && npm run build`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web
git commit -m "feat(web): add upload and job configuration flow"
```

---

## Task 19: Job Detail — SSE, Stage Timeline, Speaker Roles, Artifact Tabs

**Files:**
- Create: `web/src/pages/JobDetail.tsx`, `web/src/components/StageTimeline.tsx`, `web/src/components/SpeakerRoles.tsx`, `web/src/components/ArtifactTabs.tsx`, `web/src/hooks/useJobEvents.ts`, `web/src/lib/jobEvents.ts`, `web/src/lib/jobEvents.test.ts`
- Modify: `web/src/router.tsx`

**Interfaces:**
- Consumes: `GET /api/jobs/{id}`, SSE `/api/jobs/{id}/events`, `PATCH /speakers`, artifact `download_url`.
- Produces:
  - `applyJobEvent(job: Job, event: JobEvent): Job` — snapshot replaces the job; `stage.started/progress/completed` updates that stage; `job.completed/failed` sets status and timestamps; unknown types return the job unchanged.
  - `useJobEvents(jobId, enabled)` — `EventSource` lifecycle, closes on terminal status and unmount.
  - `StageTimeline` renders `STAGE_ORDER` with pending/running/completed/skipped/failed, percent bar, and timestamps.
  - `SpeakerRoles` renders one select per detected speaker (`Presenter`, `Feeder`, `Co-host`), Save calls PATCH, and shows validation errors inline.
  - `ArtifactTabs` groups artifacts into Audio, Transcript (Before), Transcript (After), `ROUGH-CUT.md`; audio uses `<audio controls>`; Markdown uses `react-markdown` + `remark-gfm`; SRT/VTT/JSON render as preformatted text; every row has a download link; `ROUGH-CUT.md` has a "Copy for coding agent" button that fetches the artifact text and writes it to the clipboard.
  - Detail page shows filename, status, duration, FPS, error code when failed, and keeps polling every 3 s while non-terminal as a fallback to SSE.

- [ ] **Step 1: Write the failing test**

`web/src/lib/jobEvents.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { applyJobEvent } from "./jobEvents";
import type { Job } from "../api/types";

const base = {
  id: "j1",
  status: "running",
  stage_states: {
    transcribe: { status: "pending", percent: 0, started_at: null, completed_at: null },
  },
} as unknown as Job;

describe("applyJobEvent", () => {
  it("updates a stage's percent", () => {
    const next = applyJobEvent(base, {
      type: "stage.progress", job_id: "j1", stage: "transcribe", percent: 75,
    } as never);
    expect(next.stage_states.transcribe.percent).toBe(75);
    expect(next.stage_states.transcribe.status).toBe("running");
  });

  it("marks the job completed and ignores unrelated events", () => {
    const done = applyJobEvent(base, {
      type: "job.completed", job_id: "j1",
    } as never);
    expect(done.status).toBe("completed");
    expect(applyJobEvent(base, { type: "ping", job_id: "j1" } as never)).toBe(base);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd web && npm test -- jobEvents`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the detail page**

Map artifact kinds to tabs; when a kind is absent, show an empty state that says which pipeline step produces it. On PATCH success, replace the `["job", id]` query data with the response. Keep the copy button disabled until the artifact text loads.

- [ ] **Step 4: Run the gates**

Run: `cd web && npm test && npm run typecheck && npm run build`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web
git commit -m "feat(web): add live job detail with stage timeline, speakers, and artifacts"
```

---

## Task 20: Production Serving, README, Full Verification

**Files:**
- Create: `tests/test_spa.py`, `README.md`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `settings.frontend_dist`.
- Produces:
  - SPA mount: `/assets` serves `web/dist/assets`; a catch-all `GET /{path:path}` returns `web/dist/index.html` for non-`api` paths, and JSON 404 for `/api/...`. Missing `index.html` returns a plain 404 with a build hint.
  - README covering: prerequisites, `uv sync`, `npm install`, `alembic upgrade head`, dev commands (two terminals), demo credentials, production build + single-server run, test commands, mock boundaries, and the Phase 1 non-goals.

- [ ] **Step 1: Write the failing test**

`tests/test_spa.py`:

```python
from app.config import Settings
from app.main import create_app


async def test_spa_fallback_serves_index_for_deep_links(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>parecut-shell</body></html>")
    settings = Settings(
        app_env="test",
        secret_key="test-secret",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}",
        storage_dir=tmp_path / "storage",
        frontend_dist=dist,
        seed_demo=False,
    )
    app = create_app(settings)

    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/jobs/abc")
        assert response.status_code == 200
        assert "parecut-shell" in response.text
        assert (await client.get("/api/does-not-exist")).status_code == 404
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_spa.py -v`
Expected: FAIL — deep link returns 404.

- [ ] **Step 3: Implement SPA serving and write the README**

Mount the assets directory only if it exists to keep tests and bare backends working. Register the catch-all after all routers. Exclude paths starting with `api/`.

- [ ] **Step 4: Run the full backend suite**

Run: `uv run pytest -v`
Expected: all tests pass.

- [ ] **Step 5: Run the full frontend suite and build**

```bash
cd web && npm test && npm run typecheck && npm run build
```

Expected: all tests pass; build writes `web/dist`.

- [ ] **Step 6: Manual smoke check**

```bash
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
# second terminal
cd web && npm run dev
```

Verify: sign in as `demo@parecut.app` / `parecut-demo`; open the demo job; change `SPEAKER_02` to Feeder; the after-cut tab and `ROUGH-CUT.md` update without a reload; download an artifact. Then sign up a new account, upload a WAV, run the full pipeline, and watch stages complete live.

- [ ] **Step 7: Commit**

```bash
git add app/main.py tests/test_spa.py README.md
git commit -m "feat: serve the built SPA from FastAPI and document Phase 1"
```

---

## Self-Review Notes

- Every design section maps to a task: scaffold/settings (1), data (2), shared types (3), auth (4–5), profile (6), storage/uploads (7), jobs/credits (8–9), SSE (10), transcripts/cut plan/`ROUGH-CUT.md` (11–12), mock pipeline (13), role override (14), seed/reconciliation (15), UI (16–19), serving/docs (20).
- The five Review Focus failures are tested in: Task 9 (cross-user 404), Task 7 (token forgery/purpose swap), Task 15 (restart refund), Task 14 (role keys/regeneration), Task 8 + 13 (pipeline subsets), Task 8 (402 shortfall).
- Names shared across tasks: `StageState`, `stage_states`, `JobRead`, `download_url`, `write_before_artifacts`, `write_cut_outputs`, `regenerate_cut_outputs`, `MockPipelineRunner`, `reserve_minutes`, `ApiError`.
- Frontend types mirror backend payloads exactly; the backend returns `credit_balance_minutes` as a JSON number and the UI formats it with one decimal.
