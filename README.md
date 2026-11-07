# Parecut

Parecut is an AI audio engineering and rough-cut preparation tool for video editors.

It takes a difficult recording (single microphone, room noise, an off-camera line feeder) and turns it into:

- cleaned and enhanced audio
- music and per-speaker stems
- a word-level, speaker-attributed transcript
- a frame-accurate `ROUGH-CUT.md` with keep and remove ranges for Resolve or Premiere

## Branches

- `main` contains the public coming-soon landing page (`index.html`).
- `dev` contains the application code and the implementation history.
- This README is shared by both branches.

## Current status

Phase 1: the web shell works end to end.

Implemented:

- email and password auth with Argon2 and an httpOnly JWT cookie
- profile, credit balance, and preferences
- signed local uploads and downloads
- job creation with credit reservation and refunds
- live job progress over SSE
- a mock pipeline that produces demo stems and transcripts
- speaker-role switching that regenerates the after-cut transcript and `ROUGH-CUT.md`
- a seeded demo account and a monochrome Material 3 interface

Not wired yet:

- real noise reduction, enhancement, separation, diarization, or transcription
- RunPod GPU workers, Cloudflare R2, Redis, or LLM take selection
- Stripe billing and OAuth

The mock pipeline copies the uploaded audio and generates demo transcript artifacts. It exercises the product flow. It does not perform real audio analysis.

## Stack

- Backend: FastAPI, SQLModel and SQLAlchemy, Alembic, SQLite by default (Postgres-ready), Argon2, PyJWT, SSE
- Frontend: React, Vite, TypeScript, Tailwind CSS, TanStack Query
- Planned GPU: RunPod Serverless with Whisper, Demucs, pyannote, and a target-speaker model

## Run locally

The commands below apply to `dev`.

Prerequisites: Python 3.12, uv, Node 22, and ffmpeg.

Start the backend:

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

Start the frontend in a second terminal:

```bash
cd web
npm install
npm run dev
```

Open http://localhost:5173.

The backend seeds a demo account on first start when `PARECUT_SEED_DEMO=true` (the default).

Demo login:

- Email: `demo@parecut.app`
- Password: `parecut-demo`

Local data is written to `var/parecut.db` and `var/storage/`.

## Tests

```bash
uv run pytest -q
cd web && npm test && npm run typecheck && npm run build
```

## Project layout

```text
app/                FastAPI application
parecut_engine/     shared pipeline, transcript, and event schemas
web/                React SPA
alembic/            database migrations
tests/              backend tests
docs/               design and implementation documents
DESIGN.md           visual direction
PARECUT-SRS-v2.0.md product requirements
```

## Roadmap

1. Real rough-cut engine: timecodes, rule pass, before and after transcripts, `ROUGH-CUT.md`
2. Local audio ingest and DSP
3. RunPod GPU stages: enhancement, separation, transcription
4. R2 storage and signed uploads
5. LLM take selection
6. Billing, OAuth, and retention

## License

Apache License 2.0. See `LICENSE` and `NOTICE`.
