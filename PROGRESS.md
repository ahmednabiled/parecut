# Parecut Progress and Handoff

Last updated: 2026-11-08

This file is the compact handoff for the project. It records what was built, why, where it lives, and what comes next. A new session should read this file first, then the documents listed under "Source of truth".

## Project

Parecut is an AI audio engineering and rough-cut preparation tool for video editors. It turns a difficult recording into cleaned audio, stems, a speaker-attributed transcript, and a frame-accurate `ROUGH-CUT.md` with keep and remove ranges for Resolve or Premiere.

- Local path: `/home/ahmednabil/Desktop/Station/parecut`
- GitHub: https://github.com/ahmednabiled/parecut (public)
- Active branch: `dev`
- Other branches: `main` (public landing page, README, license), `phase-1-web-shell` (local Phase 1 history)
- License: Apache-2.0 (`LICENSE`, `NOTICE`)
- Remote: `origin` over HTTPS

## Conversation arc

1. The owner supplied a v3.0 SRS for a web-first Parecut.
2. We brainstormed a Phase 1 scope: build the web shell and auth first, leave third-party actions mocked behind interfaces.
3. We wrote a design document and a 20-task implementation plan.
4. We executed Tasks 1 to 17 with TDD, committing per task.
5. We ran the app, then redesigned the UI using the anti-slop rules and Material 3, restricted to black and white.
6. We added the owner's X profile logo and cover, then simplified to the script logo and removed the cover from the UI.
7. We made the repo public, added Apache-2.0 licensing, and added a README to both branches.
8. The owner chose RunPod for GPU inference. We updated the SRS, design, plan, and README, then verified the integration against RunPod's current official docs.

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
- Monochrome Material 3 visual system with Google Sans and the Pare Cut script logo
- Backend tests, frontend tests, typecheck, and production build

Pending:

- Task 18: New job UI (upload, pipeline toggles, FPS, credit estimate, 402 handling)
- Task 19: Job detail UI (SSE timeline, speaker editor, artifact tabs, copy and download)
- Task 20: FastAPI serving the built SPA, README polish, final verification
- Real audio engine and GPU pipeline
- Cloudflare R2, Redis, LLM take selection, Stripe, OAuth, retention

The backend already supports the flows that Tasks 18 and 19 need. The UI routes `/new` and `/jobs/:id` are honest "Coming soon" placeholders.

## Stack

- Python 3.12 via uv
- FastAPI, SQLModel and SQLAlchemy 2, Alembic, aiosqlite
- Argon2 (`pwdlib`), PyJWT, SSE-Starlette
- React 19, Vite, TypeScript, Tailwind v4, TanStack Query, React Router
- Google Sans for text, IBM Plex Mono for timecodes and numeric data
- Planned GPU: RunPod Serverless queue-based endpoints
- Planned storage: Cloudflare R2

## Architecture seams

Phase 1 is built around three protocols so later phases do not rewrite routers or UI:

- `ObjectStorage`: local signed-storage implementation now, R2 later
- `EventBroker`: in-memory SSE broker now, Redis later
- `PipelineRunner`: mock runner now, `RunPodPipelineRunner` later

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
- GPU inference will use RunPod Serverless, not Modal. See `docs/adr/0001-runpod-gpu-inference.md`.
- The repository is public and Apache-2.0 licensed.

## RunPod integration (decided, not implemented)

Architecture:

- `parecut-audio` endpoint, L4: enhancement, diarization, transcription
- `parecut-separate` endpoint, A10G: music separation, target-speaker extraction
- FastAPI orchestrates with `POST /run` and `GET /status/{id}`
- Store `runpod_job_id` on the job
- Poll `/status` for progress and optional completion webhook
- Workers use `runpod.serverless.start`, receive presigned R2 URLs, and never touch Postgres or R2 credentials
- `RunPodPipelineRunner` implements the existing `PipelineRunner` protocol
- `runpod_app/worker.py` is the future worker entrypoint

Important current facts from official docs (verified 2026-11-08):

- Use queue-based endpoints, not load-balancing endpoints
- `/run` is async, returns `IN_QUEUE`; statuses are `IN_QUEUE`, `IN_PROGRESS`, `COMPLETED`, `FAILED`
- `/run` payload limit is 10 MB; pass R2 URLs
- Async results are retained 30 minutes after completion
- Webhook is an optional top-level sibling of `input`
- Webhooks fire only at a terminal state, are unsigned, retry up to 2 times, and must be idempotent
- Verify webhook job id and status with `/status` before changing credits
- `progress_update` is read through `/status` polling
- FlashBoot is on in the console but off by default in REST v2; set `flashBootType = FLASHBOOT`
- Default execution timeout is 600 seconds; raise it for long sources
- Network volumes mount at `/runpod-volume`; `VolumeCache` persists model caches
- `runpod>=2.0` supports Python 3.10 to 3.14

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

- Backend: `uv run pytest -q` -> 42 passed
- Frontend: `cd web && npm test` -> 4 passed
- Typecheck: `cd web && npm run typecheck`
- Build: `cd web && npm run build`

The SSE test uses a finite stream because httpx's ASGITransport buffers the entire response. Live delivery was manually verified in the running app.

## Important files

- `README.md`: project overview and setup
- `PARECUT-SRS-v2.0.md`: SRS v3.1, RunPod architecture
- `docs/adr/0001-runpod-gpu-inference.md`: RunPod decision record and contract
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
- `1c4eb6a`: RunPod architecture
- `0734d68`: RunPod docs verification

The progress file itself adds one more documentation commit after these.

## Next actions in order

1. Task 18: build `/new`.
   - Drag and drop audio or video
   - Presigned upload with progress
   - Pipeline toggles and enhance mix
   - FPS select and credit estimate
   - Inline 402 shortfall handling
2. Task 19: build `/jobs/:id`.
   - SSE stage timeline
   - Speaker role editor with PATCH regeneration
   - Tabs for audio, before transcript, after transcript, and `ROUGH-CUT.md`
   - Download buttons and copy-for-agent
3. Task 20: serve the built SPA from FastAPI, finish README and manual smoke test.
4. Implement the real rough-cut engine (timecodes, rules, LLM take selection).
5. Implement local DSP and audio ingest.
6. Implement RunPod workers and `RunPodPipelineRunner`.
7. Add R2, Redis, Stripe, OAuth, and retention.

## Non-negotiables

- No secrets in the repository. `.env` is ignored.
- Keep the three seams intact when adding R2, Redis, and RunPod.
- Preserve sample-exact audio outputs.
- Keep the UI monochrome. Red is only for errors.
- Keep demo content labeled as demo.
- Keep the license and copyright notices.
