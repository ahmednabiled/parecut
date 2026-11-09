# Parecut Progress and Handoff

Last updated: 2026-11-09

This file is the compact handoff for the project. It records what was built, why, where it lives, and what comes next. A new session should read this file first, then the documents listed under "Source of truth".

## Project

Parecut is an AI audio engineering and rough-cut preparation tool for video editors. It turns a difficult recording into cleaned audio, stems, a speaker-attributed transcript, and a frame-accurate `ROUGH-CUT.md` with keep and remove ranges for Resolve or Premiere.

- Local path: `/home/ahmednabil/Desktop/Station/parecut`
- GitHub: https://github.com/ahmednabiled/parecut (private)
- Active branch: `dev`
- Other branches: `main` (landing page source, README, license), `phase-1-web-shell` (local Phase 1 history)
- License: Apache-2.0 (`LICENSE`, `NOTICE`)
- Remote: `origin` over SSH
- Worker image: `ghcr.io/ahmednabiled/parecut-worker:dev` (private GHCR)

## Conversation arc

1. The owner supplied a v3.0 SRS for a web-first Parecut.
2. We brainstormed a Phase 1 scope: build the web shell and auth first, leave third-party actions mocked behind interfaces.
3. We wrote a design document and a 20-task implementation plan.
4. We executed Tasks 1 to 17 with TDD, committing per task.
5. We ran the app, then redesigned the UI using the anti-slop rules and Material 3, restricted to black and white.
6. We added the owner's X profile logo and cover, then simplified to the script logo and removed the cover from the UI.
7. We made the repo public, added Apache-2.0 licensing, and added a README to both branches.
8. The owner chose Runpod for GPU inference. We updated the SRS, design, plan, and README, then verified the integration against Runpod's current official docs.

## Current status

Phase 1 is partially shipped.

Complete:

- FastAPI backend with async SQLModel, Alembic, SQLite by default
- Email and password auth with Argon2 and an httpOnly JWT cookie
- Profile, credit balance, and preferences
- Signed local uploads and downloads with HMAC tokens
- Job creation with credit reservation, settlement, refunds, and startup reconciliation
- In-memory event broker and SSE job progress
- Mock pipeline that writes artifacts and stage states
- Timecode, cut plan, before and after transcript renderers
- `ROUGH-CUT.md` renderer
- Speaker-role override that regenerates after-cut outputs
- Idempotent demo seed and demo account
- React shell with login, register, dashboard, and settings
- New job flow at `/new`: drag-and-drop upload with XHR progress, pipeline toggles,
  enhancement mix, FPS select, live credit estimate, and inline 402 shortfall handling
- Job detail at `/jobs/:id`: live SSE stage timeline with polling fallback, speaker-role
  editor with PATCH regeneration, audio players, before/after transcripts, rendered
  `ROUGH-CUT.md`, downloads, and copy-for-coding-agent
- Monochrome Material 3 visual system with Google Sans and the Pare Cut script logo
- Backend tests, frontend tests, typecheck, and production build
- Cloudflare R2 storage adapter behind `ObjectStorage`, verified with real put/get/delete
- Runpod queue endpoint `parecut-audio` with a remote stub worker
- `RunpodPipelineRunner`, `HttpRunpodClient`, and `jobs.runpod_job_id`
- End-to-end R2 + Runpod job: 15 artifacts, downloads, and `ROUGH-CUT.md`

Pending:

- Task 20: FastAPI serving the built SPA, README polish, final verification
- Real audio models in the worker (the current worker is a contract stub)
- Pin the worker image to a `sha-<short>` tag for production releases
- `parecut-separate` endpoint
- R2 bucket CORS for browser uploads
- Redis, LLM take selection, Stripe, OAuth, retention

Both `/new` and `/jobs/:id` are live. The new job page uploads immediately on file selection, keeps the returned `upload_key` across a 402 retry, and navigates to the job detail route after creation. The job detail page streams stage events over SSE, keeps a 3-second polling fallback, rebuilds from the saved snapshot after a reload, and regenerates after-cut artifacts synchronously when speaker roles change.

## Stack

- Python 3.12 via uv
- FastAPI, SQLModel and SQLAlchemy 2, Alembic, aiosqlite
- Argon2 (`pwdlib`), PyJWT, SSE-Starlette
- React 19, Vite, TypeScript, Tailwind v4, TanStack Query, React Router
- Google Sans for text, IBM Plex Mono for timecodes and numeric data
- GPU: Runpod Serverless queue-based endpoints
- Storage: Cloudflare R2 for remote workers, local signed storage for development

## Architecture seams

Phase 1 is built around three protocols so later phases do not rewrite routers or UI:

- `ObjectStorage`: local signed storage and Cloudflare R2 adapters; select with `PARECUT_STORAGE_BACKEND`
- `EventBroker`: in-memory SSE broker now, Redis later
- `PipelineRunner`: mock runner and `RunpodPipelineRunner`; select with `PARECUT_PIPELINE_RUNNER`

Job progress is stored in `jobs.stage_states`, so reloads and SSE reconnects rebuild the timeline.

## Key decisions

- Phase 1 uses SQLite by default through `PARECUT_DATABASE_URL`; Postgres works by changing the URL.
- Auth is custom, not FastAPI Users. Argon2 plus an httpOnly `parecut_session` JWT cookie.
- Credits are Decimal minutes. Signup bonus is 30 minutes. Reserve is `max(1, ceil(duration / 60))`.
- The mock pipeline copies the uploaded audio and writes demo transcript artifacts. It is labeled as demo content and is not real audio analysis.
- `transcript_before.json` is the canonical transcript. Speaker-role changes re-render after-cut and `ROUGH-CUT.md` from it.
- Orphaned queued or running jobs are failed and refunded at startup.
- The UI is monochrome Material 3. No gradients, glass, glow, or amber accent. Error red is the only semantic color.
- The auth page uses the script `Pare Cut` logo alone. The app sidebar uses the same logo alone. The P mark is only the favicon.
- The cover image is retained at `web/public/brand/cover.webp` but is not currently placed in the interface.
- GPU inference will use Runpod Serverless, not Modal. See `docs/adr/0001-runpod-gpu-inference.md`.
- The repository is public and Apache-2.0 licensed.

## Runpod integration (backend and stub worker in place)

Implemented:

- R2 bucket `parecut` in Western Europe; token `parecut-backend` scoped to that bucket
- R2 credentials live only in `.env`; S3 put/get/delete verified
- `R2ObjectStorage` behind `ObjectStorage`
- `RunpodPipelineRunner` and `HttpRunpodClient` behind `PipelineRunner`
- `jobs.runpod_job_id` added by migration `f34d11320711`
- `runpod_app/worker.py` stub and `runpod_app/Dockerfile`
- `parecut-audio` endpoint `yf16hg8td6au29`, queue-based, 24 GB AMPERE_24 (L4/A5000/3090),
  0-2 workers, 10s idle timeout, 4h execution timeout, FlashBoot on
- End-to-end test: the runner submitted a job, the worker uploaded 15 artifacts to R2,
  the backend wrote all artifact rows, downloads matched the source, and credits settled

Worker image:

- GitHub Actions workflow `.github/workflows/worker-image.yml` builds `runpod_app/Dockerfile`
  on pushes to `dev`.
- The image is pushed privately to `ghcr.io/ahmednabiled/parecut-worker:dev` and
  `ghcr.io/ahmednabiled/parecut-worker:sha-<short>`.
- The repository is private, so Runpod uses the `ghcr-parecut` registry credential with a
  GitHub PAT scoped to `read:packages`.
- The endpoint now runs `ghcr.io/ahmednabiled/parecut-worker:dev`.
- The private pull was verified end to end: a fresh worker pulled the private image,
  processed a job, and uploaded 15 artifacts to R2.
- The `dev` tag is mutable; pin `sha-<short>` for production releases.

Current worker:

- The worker is a contract stub: it copies the source for audio artifacts and renders a
  demo transcript and `ROUGH-CUT.md`. It does not run the real models yet.
- Worker progress updates caused the stub to hang in Runpod. They are disabled by default;
  set `PARECUT_WORKER_PROGRESS=1` only after implementing them with a timeout or a safer
  progress mechanism.
- The first private GHCR cold start was about 66 seconds, mostly image pull. FlashBoot,
  a pinned image, or a network volume for model caches will reduce this later.

Architecture:

- `parecut-audio` endpoint, 24 GB pool: enhancement, diarization, transcription
- `parecut-separate` endpoint, future: music separation, target-speaker extraction
- FastAPI orchestrates with `POST /run` and `GET /status/{id}`
- Store `runpod_job_id` on the job
- Poll `/status` for progress and optional completion webhook
- Workers use `runpod.serverless.start`, receive presigned R2 URLs, and never touch Postgres or R2 credentials
- `RunpodPipelineRunner` implements the existing `PipelineRunner` protocol

Model stack:

- Noise reduction: DeepFilterNet3
- Diarization: NVIDIA Nemotron-3-Diarization (100M, up to 8 speakers, OpenMDW 1.1)
- Transcription: WhisperX large-v3-turbo
- Music separation: Demucs
- Speech separation, optional: MossFormer2-SS
- Enhancement, optional: Resemble Enhance

Important current facts from official docs (verified 2026-11-08):

- Use queue-based endpoints, not load-balancing endpoints
- `/run` is async, returns `IN_QUEUE`; terminal statuses are `COMPLETED`, `FAILED`, `CANCELLED`, `TIMED_OUT`
- `/run` payload limit is 10 MB; pass R2 URLs
- Async results are retained 30 minutes after completion
- Webhook is an optional top-level sibling of `input`
- Webhooks fire at a terminal state, are unsigned, retry up to 2 times, and must be idempotent
- Verify webhook job id and status with `/status` before changing credits
- `progress_update` is read through `/status` polling
- FlashBoot is on in the console but off by default in REST v2; set `flashboot = FLASHBOOT`
- REST v2 endpoint `timeout` defaults to 300000 ms; set it explicitly for long sources
- Network volumes mount at `/runpod-volume`; `VolumeCache` persists model caches
- Use `runpod>=2.1,<3`; Python 3.10 to 3.14 is supported

Official docs:

- https://docs.runpod.io/serverless/endpoints/send-requests
- https://docs.runpod.io/serverless/endpoints/operation-reference
- https://docs.runpod.io/serverless/workers/handler-functions
- https://docs.runpod.io/serverless/endpoints/endpoint-configurations
- https://docs.runpod.io/storage/network-volumes
- https://docs.runpod.io/serverless/development/volume-cache
- https://docs.runpod.io/sdk/overview

## Current runtime

At the time of writing:

- API: http://localhost:8000, health returns 200
- Web: http://localhost:5173, returns 200
- LAN: http://192.168.1.53:5173
- Demo login: `demo@parecut.app` / `parecut-demo`
- The backend seeds one demo user and one completed demo job with 15 artifacts

Servers are development processes and may be stopped. Restart them with the commands below.

## Run locally

Prerequisites: Python 3.12, uv, Node 22, ffmpeg.

Backend:

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

Frontend, second terminal:

```bash
cd web
npm install
npm run dev
```

Open http://localhost:5173.

Default local data:

- Database: `var/parecut.db`
- Storage: `var/storage/`
- Env prefix: `PARECUT_`; see `.env.example`

## Verification

- Backend: `uv run pytest -q` -> 54 passed
- Frontend: `cd web && npm test` -> 19 passed
- Typecheck: `cd web && npm run typecheck`
- Build: `cd web && npm run build` (one chunk-size warning from react-markdown)

The SSE test uses a finite stream because httpx's ASGITransport buffers the entire response. Live delivery was manually verified in the running app.

Task 18 was smoke-tested in Chrome: login, upload `demo_interview.wav`, see the
20s duration and 1-minute estimate, create the job, and watch it complete with 15
artifacts. Unsupported file types and the transcription/rough-cut dependency were
verified in the browser as well.

Task 19 was smoke-tested in the browser against a completed job and a fresh running
job. The fresh job updated from `Running` through each stage to `Completed` with 15
artifacts. Changing `SPEAKER_02` to Feeder regenerated the after-cut transcript and
`ROUGH-CUT.md` without a reload; the speaker map changed to `REMOVE ALL`, the after
transcript contained only `SPEAKER_01`, the copy button reported `Copied`, and the
download endpoint returned the Markdown specification with a 200.

## Important files

- `README.md`: project overview and setup
- `PARECUT-SRS-v2.0.md`: SRS v3.1, Runpod architecture
- `docs/adr/0001-runpod-gpu-inference.md`: Runpod decision record and contract
- `docs/superpowers/specs/2026-11-06-parecut-v1-web-shell-design.md`: Phase 1 design
- `docs/superpowers/plans/2026-11-06-parecut-phase-1-web-shell.md`: 20-task Phase 1 plan
- `DESIGN.md`: monochrome Material 3 direction and brand asset rules
- `app/`: FastAPI backend
- `parecut_engine/`: shared pipeline, transcript, and event schemas
- `web/`: React SPA
- `tests/`: backend tests
- `web/public/brand/`: Pare Cut logo, cover, favicon

## Repository history landmarks

- `0d2dae9`: SRS, design, and plan
- `bc9623c`: project scaffold and test harness
- `9318004`: database models and migration
- `1d82dbf`: frontend scaffold and auth pages
- `dc577b4`: app shell, dashboard, settings
- `960f316`: monochrome Material 3 redesign
- `6964bca`: profile logo and cover
- `89b7df4`: script logo on auth pages
- `d46bd9d`: Apache-2.0 license
- `6c92f9c`: project README
- `1c4eb6a`: Runpod architecture
- `0734d68`: Runpod docs verification
- `259eb66`: Task 18 new job flow
- `9f65b91`: Task 19 live job detail

The progress file itself adds one more documentation commit after these.

## Next actions in order

1. Replace the stub worker with the real model pipeline.
   - DeepFilterNet3 for noise reduction
   - Nemotron-3-Diarization for speaker attribution
   - WhisperX large-v3-turbo for transcription and word timing
   - Demucs for music separation
   - MossFormer2-SS and Resemble Enhance as optional stages
   - Generate real before/after transcripts and `ROUGH-CUT.md`
2. Push the worker image to a persistent registry, deploy it to `parecut-audio`, and create
   `parecut-separate`.
3. Add R2 bucket CORS for browser uploads, then switch the app to
   `PARECUT_STORAGE_BACKEND=r2` and `PARECUT_PIPELINE_RUNNER=runpod`.
4. Task 20: serve the built SPA from FastAPI, finish README and manual smoke test.
5. Implement the real rough-cut engine (timecodes, rules, LLM take selection).
6. Add Redis, Stripe, OAuth, and retention.

## Non-negotiables

- No secrets in the repository. `.env` is ignored.
- Keep the three seams intact when adding R2, Redis, and Runpod.
- Preserve sample-exact audio outputs.
- Keep the UI monochrome. Red is only for errors.
- Keep demo content labeled as demo.
- Keep the license and copyright notices.
