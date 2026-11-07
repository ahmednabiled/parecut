# Parecut v1 — Phase 1: Web Shell + Auth (Design)

Date: 2026-11-06
Status: Approved in conversation; design doc pending builder check + final sign-off
Source spec: `PARECUT-SRS-v2.0.md` (content is v3.0)

## 1. Intent

Parecut's value is the audio-first pipeline and the `ROUGH-CUT.md` deliverable. Before paying for GPUs, storage, and LLM calls, we need the product shell to be real: a person can sign up, land on their dashboard, configure a job, watch it progress, inspect results, switch speaker roles, and download deliverables.

Phase 1 builds that shell end to end, with every third-party dependency replaced by a local implementation behind a stable interface. The UI and API contracts are then frozen against a working app, and later phases swap implementations without rewriting screens.

**Success looks like:** a fresh clone runs with no accounts, no API keys, and no Docker. A new user signs up, uploads a WAV, runs the full pipeline, watches stage progress live, opens the results screen, changes `SPEAKER_02` to Feeder, sees the regenerated after-cut transcript and `ROUGH-CUT.md`, downloads them, and the data is still there after a restart.

## 2. Scope

### In scope

- Repo scaffold, tooling, environment config, run instructions.
- FastAPI app with async SQLModel + Alembic, SQLite by default.
- Email/password auth with httpOnly JWT cookie; signup bonus credits.
- Profile + preferences (name, default FPS, enhance mix, silence pad).
- Local object storage with signed, expiring upload/download URLs.
- Job model, pipeline config validation, credit reserve/settle/refund.
- Mock pipeline runner that simulates selected stages, emits progress events over SSE, and writes artifact rows and files.
- Mock rough-cut regeneration on speaker-role change.
- React SPA: login, register, dashboard, settings, new job, job results.
- Seeded demo user and demo job so the app is explorable immediately.
- Backend test suite; frontend typecheck + production build.
- `docs/` run guide and a short roadmap of later increments.

### Explicit non-goals (Phase 1)

- RunPod, R2/S3, Redis, LLM providers, Stripe, OAuth, email delivery.
- Real DSP, enhancement, separation, diarization, transcription, or cut analysis.
- Email verification, password reset, account deletion.
- Multi-worker deployment, rate limiting, observability stack, retention sweep.
- Native NLE plugins or desktop client.
- `runpod_app/` is not created until there is a RunPod stage to run.

### Anti-goals

- Screens that hardcode data instead of reading the API, or mock artifacts that masquerade as real results. Demo content is labeled as demo.
- Auth shortcuts (client-side-only guards, plaintext passwords, permanent tokens) that would need to be torn out later.
- Building an abstraction per file. Only the three seams that later phases must replace (storage, pipeline runner, event broker) get interfaces.

## 3. Constraints

- Python 3.12 (pinned through `uv`), FastAPI, SQLModel/SQLAlchemy 2, Alembic, Pydantic v2.
- Node 22, React + Vite + TypeScript + Tailwind. Frontend built and served by FastAPI in production; separate dev servers in development with Vite proxying `/api`.
- One repository, one deployable unit.
- No external service required to boot locally. SQLite file + local storage directory.
- Model, file, and API names follow the SRS (`jobs`, `job_artifacts`, `credit_ledger`, `user_profiles`; `SPEAKER_01`; `ROUGH-CUT.md`).

## 4. Decisions Made

These are settled; the builder implements them.

| Area | Decision |
|---|---|
| Auth | Custom email/password. Argon2 hashing (`pwdlib[argon2]`), HS256 JWT in an httpOnly `parecut_session` cookie, `SameSite=Lax`, `Secure` outside dev, 7-day TTL. No refresh-token machinery. |
| CSRF | Relies on `SameSite=Lax`, JSON-only bodies, and same-origin serving. Documented as a Phase 1 tradeoff. |
| Database | `DATABASE_URL` env var; default `sqlite+aiosqlite:///./var/parecut.db`. Postgres works by changing the URL; migrations are vendor-neutral. |
| IDs | UUIDv4 strings for users, jobs, artifacts, ledger rows. |
| JSON columns | Pipeline config, speaker roles, and job progress metadata stored as SQLAlchemy JSON. |
| Uploads | Browser asks for a signed URL, then `PUT`s bytes directly to it. Local backend writes to `var/storage/<key>` and validates the HMAC token and TTL. |
| Job execution | `PipelineRunner` protocol. Phase 1 `MockPipelineRunner` runs as an `asyncio` background task inside the API process. |
| Progress | `EventBroker` protocol with an in-memory implementation. SSE endpoint replays a job snapshot first, then live events, plus a keepalive. |
| Pipeline defaults | Full pipeline on: noise reduction, enhance (mix 0.8), music separation, speaker separation, transcription, rough cut. Rough cut requires transcription; the API validates and the UI disables it otherwise. |
| FPS options | `24`, `25`, `29.97`, `30`, `60`. |
| Credits | Signup bonus 30 minutes. Job reserve = ceiling(duration seconds / 60). Settle on completion (reserve stands), refund on failure/cancel. Numeric minutes stored as `Decimal`. |
| Frontend data | TanStack Query for server state, React Router for routes, Tailwind + small hand-built components, lucide icons, `react-markdown` for Markdown artifacts. No UI kit. |
| Audio playback | Native `<audio>` elements over signed URLs. Waveform player deferred. |
| Styling | Dark, dense, editor-tool aesthetic; one accent color; monospace for timecodes. Desktop-first, usable at 768 px. |
| Demo content | Idempotent startup seed: `demo@parecut.app` / `parecut-demo`, profile, signup ledger entry, one completed job with generated demo audio and canned speaker-attributed transcript. Demo artifacts labeled "Demo" in the UI. |

## 5. Architecture

### 5.1 Layout

```text
parecut/
├── pyproject.toml            # uv project: app + engine + tests
├── alembic.ini
├── alembic/
├── app/
│   ├── main.py               # app factory, routers, SPA static mount
│   ├── config.py             # pydantic-settings
│   ├── db.py                 # async engine + session dependency
│   ├── deps.py               # current_user, services
│   ├── models.py             # SQLModel tables
│   ├── schemas.py            # API request/response models
│   ├── security.py           # hashing, JWT, cookie helpers
│   ├── storage.py            # ObjectStorage protocol + LocalObjectStorage
│   ├── events.py             # EventBroker protocol + InMemoryEventBroker
│   ├── seed.py               # idempotent demo seed + startup reconciliation
│   ├── demo_data.py          # fixed demo transcript, scaled to job duration
│   ├── routers/
│   │   ├── auth.py
│   │   ├── profile.py
│   │   ├── uploads.py
│   │   └── jobs.py
│   ├── services/
│   │   ├── credits.py        # reserve math, ledger writes
│   │   ├── jobs.py           # create/get/list, ownership
│   │   ├── pipeline.py       # PipelineRunner protocol + MockPipelineRunner
│   │   └── roughcut.py       # placeholder regeneration of after-cut + ROUGH-CUT.md
│   └── renderers.py          # markdown/srt/vtt/json from mock transcript
├── parecut_engine/
│   └── schemas.py            # shared Pydantic: PipelineConfig, JobEvent, Transcript, CutPlan, SpeakerRole
├── web/
│   ├── src/
│   │   ├── main.tsx, App.tsx, router.tsx
│   │   ├── api/client.ts, queries.ts
│   │   ├── auth/AuthProvider.tsx, guards.tsx
│   │   ├── components/       # AppShell, Dropzone, PipelineToggles, AudioPlayer, ...
│   │   ├── pages/            # Login, Register, Dashboard, NewJob, JobDetail, Settings
│   │   └── styles.css
│   ├── index.html
│   ├── tailwind.config.ts
│   └── vite.config.ts
├── tests/
├── docs/
├── var/                      # gitignored: db, storage, uploads
└── .env.example
```

### 5.2 Seams for later phases

Three protocols, each with one Phase 1 implementation:

```python
class ObjectStorage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def delete(self, key: str) -> None: ...
    def signed_upload_url(self, key: str, ttl_seconds: int) -> str: ...
    def signed_download_url(self, key: str, filename: str, ttl_seconds: int) -> str: ...

class EventBroker(Protocol):
    async def publish(self, job_id: str, event: JobEvent) -> None: ...
    def subscribe(self, job_id: str) -> AsyncIterator[JobEvent]: ...

class PipelineRunner(Protocol):
    async def spawn(self, job_id: str) -> None: ...
```

Swapping R2 → `R2ObjectStorage`, Redis → `RedisEventBroker`, RunPod → `RunPodPipelineRunner` must not require changes to routers or UI.

### 5.3 Data model

- `users`: id, email (unique, lowercased), hashed_password, full_name, avatar_url (nullable), is_active, created_at.
- `user_profiles`: user_id PK/FK, credit_balance_minutes Decimal(10,2), default_fps, default_enhance_mix int, default_silence_pad_ms int, created_at, updated_at.
- `credit_ledger`: id, user_id, job_id nullable, delta_minutes Decimal, reason enum (`signup_bonus`, `job_reserve`, `job_settle`, `job_refund`), gpu_seconds_internal float nullable, created_at.
- `jobs`: id, user_id, status (`queued`, `running`, `completed`, `failed`; `canceled` is reserved and unused in Phase 1), source_filename, source_r2_key (SRS name; holds local storage key), duration_seconds nullable, sample_rate nullable, fps, pipeline_config JSON, speaker_roles JSON, stage_states JSON, error_code nullable, created_at, started_at, completed_at.
  - `stage_states` is the progress source of truth: ordered map of `stage -> {status: pending|running|completed|skipped|failed, percent: 0-100, started_at, completed_at}`. The runner updates it before publishing an event; `GET /api/jobs/{id}` and the SSE `snapshot` both return it, so a reload or reconnect rebuilds the timeline without replaying every event.
  - Speaker role values are `presenter`, `feeder`, `cohost` (displayed as Presenter/Keep, Feeder/Remove, Co-host/Keep). Roles are `presenter`/`feeder`/`cohost` in JSON keys typed `str`, never free text.
- `job_artifacts`: id, job_id, kind (`cleaned_audio`, `enhanced_audio`, `stem_music`, `stem_dialogue`, `stem_speaker`, `transcript_before`, `transcript_after`, `rough_cut_md`), label, format (`wav`, `md`, `srt`, `vtt`, `json`), r2_key, size_bytes, created_at.

OAuth columns from the SRS are omitted until OAuth exists.

### 5.4 API contract

All routes are `/api/*`, JSON, cookie-authenticated except auth entry points. Errors use `{"detail": "..."}` with 400/401/402/403/404/409/422.

| Method | Path | Behavior |
|---|---|---|
| POST | `/api/auth/register` | Create user + profile + signup bonus atomically; set cookie; return session user. 409 on duplicate email. |
| POST | `/api/auth/login` | Verify credentials; set cookie; return session user. 401 on failure. |
| POST | `/api/auth/logout` | Clear cookie. |
| GET | `/api/auth/me` | Session user + profile. 401 when unauthenticated. |
| GET | `/api/profile` | Profile, balance, 20 most recent credit-ledger entries, and 10 most recent jobs. |
| PATCH | `/api/profile` | Update `full_name`, `default_fps`, `default_enhance_mix` (0–100 int), `default_silence_pad_ms`. |
| POST | `/api/uploads` | Body `{filename, size_bytes, content_type}`. Validates extension/size (≤ 3 h at 48 kHz stereo ≈ 2 GB cap) and returns `{upload_url, upload_key, expires_at}`. |
| PUT | `/api/uploads/{token}` | Receives bytes for the token's key; enforces TTL. |
| POST | `/api/jobs` | Body `{upload_key, source_filename, fps, pipeline}`. Validates config, reads duration via ffprobe (fallback: `null`), reserves credits, creates queued job, spawns runner, returns job. Insufficient balance → 402 with required/available minutes. |
| GET | `/api/jobs` | User's jobs, newest first, cursor-free pagination `limit`/`offset`. |
| GET | `/api/jobs/{id}` | Job + stage snapshot + artifact list + speaker roles. 404 for other users' jobs. |
| GET | `/api/jobs/{id}/events` | SSE. First event `snapshot` carries the full job (including `stage_states`); then `job.status`, `stage.started`, `stage.progress`, `stage.completed`, `job.completed`, `job.failed`; 15 s keepalive. |
| PATCH | `/api/jobs/{id}/speakers` | Replace speaker roles; synchronously regenerate `transcript_after.*` and `rough_cut_md` from the canonical `transcript_before.json`; return updated job. |
| GET | `/api/jobs/{id}/artifacts/{artifact_id}/download` | 302 to signed URL (or direct `FileResponse` locally) with attachment filename. Ownership enforced. |

Pipeline config shape (shared Pydantic model):

```json
{
  "noise_reduction": true,
  "enhance": true,
  "enhance_mix": 0.8,
  "separate_music": true,
  "separate_speakers": true,
  "transcribe": true,
  "rough_cut": true
}
```

Validation: `rough_cut` implies `transcribe`; if transcription is disabled the API rejects rough cut with a 422 and message the UI can show. Speaker separation operates independently on the uploaded audio, so it does not require music separation or transcription.

Credit and duration rules:

- Reserve = `max(1, ceil(duration_seconds / 60))` minutes. When ffprobe cannot read a duration, reserve 1 minute and leave `duration_seconds` null; the upload/ingest phase will replace this heuristic.
- Balance below reserve → 402, no job row, no upload deletion; the UI shows the shortfall and a disabled top-up notice.
- Ledger rows: `signup_bonus` (+30 on registration), `job_reserve` (−N at creation), `job_settle` (delta 0 at completion, as an audit marker), `job_refund` (+N on failure or startup reconciliation). Balance is the sum of deltas and is also denormalized on `user_profiles`.
- Enhance mix has one convention per layer: profile and UI use integer 0–100 (SRS default 80); job pipeline config uses float 0.0–1.0 (SRS default 0.8). Conversion happens once when `/api/jobs` maps profile defaults into the config.

Speaker-role defaults: whenever the mock pipeline produces speakers, `SPEAKER_01` starts as `presenter` and every other detected speaker starts as `presenter` too, so the role editor has a visible effect when the user marks one `feeder`. The demo seed uses the same defaults and the demo transcript labels them as demo data.

### 5.5 Mock pipeline behavior

- Runs only the selected stages, ~1.5 s per stage (`MOCK_STAGE_DELAY_MS`, default 1500; tests set 0).
- Emits realistic progress (0, 25, 50, 75, 100) per stage and writes `job.status`.
- Audio artifacts copy the uploaded file to a new key (so players work with real audio).
- Transcript and rough-cut artifacts are generated from a fixed demo transcript, scaled/snapped to the uploaded duration and chosen FPS. They are clearly labeled "Demo transcript".
- `transcript_before.*` renders all segments with source timecodes. `transcript_after.*` renders only kept segments with source timecodes and assembled timecodes. `ROUGH-CUT.md` includes metadata, speaker map, KEEP/REMOVE tables, chronological audit log, and the coding-agent instruction block — the same skeleton as SRS §5.1.
- `transcript_before.json` is the canonical machine-readable transcript for the job. The renderer treats it as input and derives every other transcript format plus the cut plan; the seeded demo job ships the same file. This is the seam the real Stage 5 planner plugs into.
- `PATCH speakers` reads `transcript_before.json`, applies roles, re-renders after-cut and `ROUGH-CUT.md` in-process; replaced artifact rows point to newly written keys.
- Failure path: if the job row disappears or storage fails, mark `failed`, write `error_code`, refund credits.
- Startup reconciliation: any job left `queued` or `running` from a previous process is marked `failed` with `error_code = server_restart` and its reserve refunded. This keeps the in-process runner honest across `--reload` and restarts.

### 5.6 Frontend

Routes and behavior:

- `/login`, `/register`: email/password forms, inline validation, server error display, redirect to `/` or `?next=`.
- `/`: credit balance, quick "New job" CTA, recent jobs with status pills and stage progress, settings link.
- `/new`: drag-and-drop (click-to-browse fallback), file type/size hints, upload progress, pipeline checkboxes with descriptions, enhance mix slider (0–100), FPS select, estimated credit cost, submit disabled until upload completes. A 402 shows the shortfall inline and keeps the form state; the top-up action is visibly disabled in Phase 1.
- `/jobs/:id`: header with filename, status, duration, FPS; stage timeline with live SSE updates; speaker role editor; tabs for Audio, Transcript (Before), Transcript (After), `ROUGH-CUT.md`; each artifact row has a download button; `ROUGH-CUT.md` tab has "Copy for coding agent" plus rendered Markdown.
- `/settings`: profile fields and defaults.
- Auth guard redirects to login and preserves intended path.
- SSE reconnects with backoff; when the job is terminal the page stops streaming and shows the results.

State: TanStack Query keys `me`, `profile`, `jobs`, `job(id)`; mutations invalidate the relevant keys. Downloads use normal links so the browser handles them.

### 5.7 Seed data

On startup when `SEED_DEMO=true` (default in dev): create the demo user if absent, a completed job with full-pipeline config, audio artifacts backed by a generated 20 s low-volume tone (stdlib `wave`, no external binary, clearly demo), before/after transcripts in four formats, and `ROUGH-CUT.md`. Seeding is idempotent by fixed job UUID.

## 6. Functional Requirements Covered

- FR-AUTH-01 (signup, login, logout, profile management).
- FR-UPL-01 partial: upload UX and storage mechanics; real 3-hour processing arrives with the GPU phase.
- FR-PIP-01: selection UI and validation; execution is mocked.
- FR-AUD-01 partial: preview of uploaded and generated audio artifacts; real enhanced stems arrive later.
- FR-CUT-01 partial: artifact structure, formats, and UI; content is demo until the engine lands.
- FR-CUT-02: role switching and instant regeneration of after-cut + `ROUGH-CUT.md`, implemented synchronously (mock renderer now, real planner later).

## 7. Definition of Done

1. `uv sync` and `npm install` succeed from a clean checkout.
2. `uv run alembic upgrade head` creates the schema on SQLite.
3. `uv run uvicorn app.main:app --reload` boots with no external services.
4. Seeded demo login works; a brand-new signup also works and starts with 30 credits.
5. Upload → configure → run → progress via SSE → results works for any subset of stages, including "transcription only" and "rough cut disabled".
6. Speaker role change regenerates after-cut artifacts and `ROUGH-CUT.md` without a page reload or job re-run.
7. All artifacts download with correct filenames and content types; unauthorized users get 404.
8. Credits reserve, settle, and refund correctly; ledger rows appear in the profile API response and are asserted in tests.
9. `uv run pytest` passes; `npm run typecheck` and `npm run build` pass; FastAPI serves the built SPA with deep-link fallback.
10. `README.md` documents setup, demo credentials, and the known mock boundaries.

## 8. Later Increments (roadmap only, not planned here)

1. **Rough-cut engine (no third-party):** real timecode conversion for all FPS values, transcript schema + alignment ingestion, rule pass, before/after renderers, and `ROUGH-CUT.md` from real transcripts.
2. **Local audio ingest + Stage 1 DSP (local libraries):** ffmpeg/ffprobe metadata, WAV normalization, high-pass, notch, spectral gate, loudness normalization, sample-exact output.
3. **RunPod GPU stages:** enhancement, music/speaker separation, transcription; real `PipelineRunner`, HMAC callback, Redis broker, artifact retention.
4. **R2 storage:** presigned browser uploads/downloads, lifecycle rules.
5. **LLM take selection:** provider abstraction, retake grouping, best-take scoring, cost controls.
6. **Commercial surface:** Stripe top-ups, OAuth, email flows, rate limits, observability, retention sweep.

## 9. Left to the Builder

- Exact component styling, spacing, and copy within the chosen aesthetic.
- Choice of minor libraries not listed (form helpers, toast, etc.) that do not change contracts.
- Alembic revision granularity and test fixtures.
- Demo audio synthesis details and demo transcript content.
- Whether to add a minimal Vitest smoke test; not required for Phase 1 done.
