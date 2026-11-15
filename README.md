# Parecut

Parecut is an AI audio engineering and rough-cut preparation tool for video editors.

It takes a difficult recording (single microphone, room noise, an off-camera line feeder) and turns it into:

- cleaned and enhanced audio
- music and per-speaker stems
- a word-level, speaker-attributed transcript
- a frame-accurate `ROUGH-CUT.md` with keep and remove ranges for Resolve or Premiere

## Branches

- `main` contains the coming-soon landing page source (`index.html`).
- `dev` contains the application code and the implementation history.
- This README is shared by both branches.
- The repository is private. The worker image is published privately to
  `ghcr.io/ahmednabiled/parecut-worker`.

## Current status

Phase 1 works end to end: the web shell, R2 storage, and the real Runpod model
pipeline.

Implemented:

- email and password auth with Argon2 and an httpOnly JWT cookie
- profile, credit balance, and preferences
- signed uploads and downloads
- job creation with credit reservation and refunds
- live job progress over SSE
- real noise reduction with DeepFilterNet3
- real music/dialogue separation with Demucs `htdemucs_ft`
- real transcription with WhisperX 3.3.1 `large-v3-turbo` and English word alignment
- mixed-language transcription: choose English/Arabic per run, transcribe once per
  selected language, then merge by script and confidence before speaker assignment
- real enhancement with Resemble Enhance: 44.1 kHz restoration, bandwidth and body
  extension, a wet/dry mix, and GPU inference with CPU fallback
- GPU inference for Resemble Enhance, WhisperX, Demucs, DeepFilterNet, and Nemotron
  diarization, with a `PARECUT_GPU_STAGES` override (`noise_reduction`, `enhance`,
  `separate_music`, `transcribe`; diarization follows `transcribe`/`separate_speakers`)
  for per-stage CPU fallback
- compressed audio artifacts by default: generated audio is MP3 (192 kbps CBR,
  `audio/mpeg`), with a per-run **Lossless (WAV)** option in the inspector
- a configurable studio finishing chain after Resemble: high-pass, body/mud/presence EQ,
  de-esser, compressor, limiter, and loudness normalization in a collapsible panel that
  is collapsed by default and stores its settings on each run
- real diarization with NVIDIA Nemotron-3-Diarization
- per-speaker gated stems
- a speaker-attributed canonical transcript that drives the before/after transcripts
  and `ROUGH-CUT.md`
- speaker-role switching that regenerates the after-cut transcript and `ROUGH-CUT.md`
- a non-destructive timeline editor with synchronized multi-track playback, per-track
  mute, server-generated waveform peaks with low-saturation lane tints, click-and-drag
  scrubbing, caption editing and downloads, and a fixed time ruler and meter rail beside
  the scrolling track list
- on-demand effects that run as child jobs and add muted tracks without touching the
  source: noise reduction, enhancement, music separation, speaker separation, and
  transcribe + rough cut
- deterministic false-start and same-speaker-retake removal
- a seeded demo account and a monochrome Material 3 interface
- a collapsible navigation sidebar on desktop and a drawer on mobile, with the open
  state persisted
- FastAPI serving the built SPA with deep-link fallback in production

Still pending:

- true target-speaker separation; per-speaker stems are gated from diarization turns
- per-segment language identification or a code-switch-aware ASR model; the current
  mixed-language path runs one pass per selected language and merges the results
- language selection/forced language for additional languages beyond English/Arabic
- LLM take selection
- Redis, Stripe billing, OAuth, and retention

The checked-in `.env.example` keeps the no-credentials local/mock path. The active
development `.env` uses R2 + Runpod. The mock runner still exists for tests and for a
plain checkout.

## Editor model

A project starts with an upload at `/new`. The project is a draft: it has the source
track, costs no credits, and produces no artifacts. In `/jobs/:id`, effects are applied
from the inspector. Each effect is a child job (`parent_job_id` + `effect`) that
reserves credits, runs only its own stages, and adds its output as a muted track; the
source is never rewritten.

The Enhance effect runs DeepFilterNet3 and Resemble Enhance. Its Studio polish panel is
collapsed by default; expanding it exposes high-pass, body/mud/presence EQ, de-essing,
compression, limiting, and loudness controls. The panel can be switched off, and the
values are stored on the effect run so the worker applies exactly what was set.

The Transcribe effect has a language picker. Select every language present in the
recording; selecting more than one runs the model once per language and merges the
segments by script and confidence before the cut plan is built.

Source and effect audio stream same-origin with HTTP range support, so the browser can
seek and keep tracks synchronized. Playback and per-track mute use the Web Audio API;
the timeline renders waveform peaks from the source and each effect artifact. The time
ruler and master meter rail are fixed; only the track lanes scroll. The side meters read
the mixed signal. Captions come from the most recent completed
transcription run. Word chunking and text corrections are client-side, and the
corrected SRT downloads from the viewer; the raw VTT and `ROUGH-CUT.md` download from
the inspector.

## Stack

- Backend: FastAPI, SQLModel and SQLAlchemy, Alembic, SQLite by default (Postgres-ready), Argon2, PyJWT, SSE
- Frontend: React, Vite, TypeScript, Tailwind CSS, TanStack Query
- Worker: Python 3.11, DeepFilterNet3, Demucs, WhisperX, NVIDIA Nemotron-3-Diarization.
  Main stack uses CPU torch 2.2.2; Nemotron runs in an isolated torch 2.6/transformers 5.x venv.
- GPU: Runpod Serverless queue endpoint `parecut-audio`
- Storage: Cloudflare R2 for remote workers, local signed storage for development

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

## Production-style run

Build the SPA, then let FastAPI serve it and the API on one port:

```bash
cd web && npm run build && cd ..
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000. Deep links such as `/jobs/<id>` return the SPA, while
unknown `/api/...` routes return JSON 404s. Brand assets are served from the built
`web/dist` directory.

For the real pipeline, set `PARECUT_STORAGE_BACKEND=r2`,
`PARECUT_PIPELINE_RUNNER=runpod`, and the R2/Runpod credentials in `.env`.

## Tests

```bash
uv run pytest -q
cd web && npm test && npm run typecheck && npm run build
```

## Project layout

```text
app/                FastAPI application
parecut_engine/     shared pipeline, transcript, and event schemas
runpod_app/         Runpod worker and Dockerfile
web/                React SPA
alembic/            database migrations
tests/              backend tests
docs/               design and implementation documents
DESIGN.md           visual direction
PARECUT-SRS-v2.0.md product requirements
```

## Roadmap

1. GPU inference for Resemble Enhance, WhisperX, Demucs, and diarization
2. True target-speaker separation
3. LLM take selection on top of the deterministic cut rules
4. Redis, billing, OAuth, and retention
5. A dedicated `parecut-separate` endpoint for heavy separation stages

## License

Apache License 2.0. See `LICENSE` and `NOTICE`.
