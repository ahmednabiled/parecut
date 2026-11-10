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
- Runpod queue endpoint `parecut-audio` with a full model worker
- `RunpodPipelineRunner`, `HttpRunpodClient`, and `jobs.runpod_job_id`
- End-to-end R2 + Runpod job: artifacts, downloads, and `ROUGH-CUT.md`
- Local `.env` switched to `r2` + `runpod`; UI-created jobs have real `runpod_job_id`s
- Real noise reduction: `cleaned_audio` is DeepFilterNet3 output (48 kHz mono)
- Real separation: `stem_music` and `stem_dialogue` come from Demucs `htdemucs_ft`;
  per-speaker stems are gated from the diarization turns
- Real transcription: WhisperX `large-v3-turbo` with word alignment
- Real diarization: pyannote `speaker-diarization-3.1` with
  `segmentation-3.0` and `wespeaker-voxceleb-resnet34-LM`, baked into the image
- Speaker-attributed transcript fed into the before/after renderers and `ROUGH-CUT.md`
- Endpoint release #13 pinned to `ghcr.io/ahmednabiled/parecut-worker:sha-c12bc4e`
- R2 browser uploads proxied through FastAPI, with worker artifact uploads still using
  direct presigned R2 URLs; text artifacts served same-origin for previews and copy
- Deterministic cut rules for restart false starts and same-speaker retakes; the
  after-cut transcript and `ROUGH-CUT.md` now differ from the before transcript even
  when every speaker is a presenter
- Speaker-role regeneration uses the real canonical transcript and keeps real artifact
  labels; mock/demo jobs still get `Demo —` labels

Pending:

- Task 20: FastAPI serving the built SPA, README polish, final verification
- Resemble Enhance for the enhancement stage; `enhanced_audio` currently reuses the
  DeepFilterNet3 output and is labeled `Denoised Audio (Enhancement pending)`
- True target-speaker separation; per-speaker stems are currently gated by diarization
  turns, and MossFormer2-SS remains optional
- LLM take selection on top of the deterministic false-start/retake rules
- `parecut-separate` endpoint
- Optional R2 bucket CORS if direct browser uploads replace the FastAPI proxy
- Redis, Stripe, OAuth, retention

Both `/new` and `/jobs/:id` are live. The new job page uploads immediately on file selection, keeps the returned `upload_key` across a 402 retry, and navigates to the job detail route after creation. The job detail page streams stage events over SSE, keeps a 3-second polling fallback, rebuilds from the saved snapshot after a reload, and regenerates after-cut artifacts synchronously when speaker roles change.

The local `.env` now selects the real R2 + Runpod path. Browser uploads go to FastAPI and are written to R2 server-side, so they do not depend on R2 CORS. The worker still receives direct presigned R2 URLs for its outputs, and text artifacts are served by FastAPI so Markdown previews and copy work without cross-origin reads.

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
- GPU inference uses Runpod Serverless, not Modal. See `docs/adr/0001-runpod-gpu-inference.md`.
- The active local `.env` uses `PARECUT_STORAGE_BACKEND=r2` and `PARECUT_PIPELINE_RUNNER=runpod`.
  `.env.example` keeps the local/mock defaults for a no-credentials checkout.
- Browser uploads are proxied through FastAPI for R2 because the bucket token cannot manage
  CORS. The `ObjectStorage` seam has separate `signed_upload_url` (browser) and
  `signed_direct_upload_url` (worker outputs) methods.
- The repository is public and Apache-2.0 licensed.

## Runpod integration (backend and full model worker in place)

Implemented:

- R2 bucket `parecut` in Western Europe; token `parecut-backend` scoped to that bucket
- R2 credentials live only in `.env`; S3 put/get/delete verified
- `R2ObjectStorage` behind `ObjectStorage`
- `RunpodPipelineRunner` and `HttpRunpodClient` behind `PipelineRunner`
- `jobs.runpod_job_id` added by migration `f34d11320711`
- `runpod_app/worker.py` with DeepFilterNet3 denoising, WhisperX transcription and
  alignment, pyannote diarization, Demucs separation, and gated speaker stems
- `runpod_app/Dockerfile` with the full worker image
- `parecut-audio` endpoint `yf16hg8td6au29`, queue-based, 24 GB AMPERE_24 (L4/A5000/3090),
  0-2 workers, 10s idle timeout, 4h execution timeout, FlashBoot on
- End-to-end test: the runner submitted a job, the worker uploaded 15 artifacts to R2,
  the backend wrote all artifact rows, downloads matched the source, and credits settled
- Active runtime test after wiring: the UI upload was proxied to R2, `POST /api/jobs`
  submitted to `parecut-audio` (`runpod_job_id` recorded), the worker ran and the job
  completed in about 27 seconds with 15 artifacts
- After release #6, a noisy speech job completed with `Denoised Audio (DeepFilterNet3)`
- After release #13, a two-voice sample produced two speakers, four aligned transcript
  segments, Demucs music/dialogue stems, two gated speaker stems, and real before/after
  transcripts and `ROUGH-CUT.md`

Worker image:

- GitHub Actions workflow `.github/workflows/worker-image.yml` builds `runpod_app/Dockerfile`
  on pushes to `dev`.
- The image is pushed privately to `ghcr.io/ahmednabiled/parecut-worker:dev` and
  `ghcr.io/ahmednabiled/parecut-worker:sha-<short>`.
- The repository is private, so Runpod uses the `ghcr-parecut` registry credential with a
  GitHub PAT scoped to `read:packages`.
- Endpoint release #13 runs `ghcr.io/ahmednabiled/parecut-worker:sha-c12bc4e`.
- The private pull was verified end to end: a fresh worker pulled the private image,
  processed jobs, and uploaded artifacts to R2.
- The image bakes DeepFilterNet3, WhisperX `large-v3-turbo`, the English alignment
  model, Demucs `htdemucs_ft`, and the pyannote diarization models.
- The gated pyannote terms were accepted on the `ahmednabiled` Hugging Face account.
  The build uses the `HF_TOKEN` GitHub Actions secret through a BuildKit secret; the
  token is not persisted in the image.
- Use a new `sha-<short>` release for each worker change. The `dev` tag is mutable, so
  the endpoint is pinned to an immutable tag.

Current worker:

- Noise reduction: `ffmpeg` converts the source to 48 kHz mono, DeepFilterNet3 denoises
  it, and the result is uploaded as `cleaned_audio`.
- Separation: Demucs `htdemucs_ft` produces `stem_music` and `stem_dialogue`.
  Per-speaker stems are gated from the pyannote turns, up to eight speakers.
- Transcription: WhisperX 3.3.1 `large-v3-turbo` with the English alignment model.
  Aligned words are assigned to speakers and merged into readable segments.
- Diarization: pyannote `speaker-diarization-3.1` with `segmentation-3.0` and
  `wespeaker-voxceleb-resnet34-LM`. If the model fails, the worker logs the error and
  falls back to one speaker instead of failing the whole job.
- Cut outputs: the real speaker-attributed transcript is the canonical
  `transcript_before.json`; `build_cut_plan`, the before/after renderers, and
  `ROUGH-CUT.md` use it. `PATCH /speakers` regenerates from the real transcript.
- Enhancement: `enhanced_audio` reuses the denoised WAV and is labeled
  `Denoised Audio (Enhancement pending)`. Resemble Enhance is not installed.
- The image uses Python 3.11 because `deepfilterlib` has no Python 3.12 wheel.
  It installs `ffmpeg`, `git`, `libsndfile1`, CPU torch/torchaudio 2.2.2, `soundfile`,
  `whisperx==3.3.1`, `pyannote.audio==3.3.2`, `demucs==4.1.0`, and
  `transformers==4.48.3`.
- CTranslate2 is overridden to 4.6.0 after the WhisperX install: 4.4/4.5 fail on newer
  glibc with "cannot enable executable stack", while 4.6 works with faster-whisper 1.1.0.
- DeepFilterNet is installed with `--no-deps` because its `packaging<24` pin conflicts
  with `runpod`'s `packaging>=26.3`.
- All model weights are baked into the image. Runtime uses `HF_HUB_OFFLINE=1` and
  `TRANSFORMERS_OFFLINE=1`.
- Inference is CPU-only in the current worker. Short clips take roughly 1-2 minutes;
  long recordings will be slower until the image is moved to CUDA torch.
- Worker progress updates still cause problems in Runpod. They are disabled by default;
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

Model stack currently deployed:

- Noise reduction: DeepFilterNet3
- Diarization: pyannote `speaker-diarization-3.1` with `segmentation-3.0` and
  `wespeaker-voxceleb-resnet34-LM`
- Transcription: WhisperX 3.3.1 `large-v3-turbo` with English word alignment
- Music separation: Demucs `htdemucs_ft`
- Speaker stems: diarization-gated audio (not true target-speaker extraction)
- Enhancement: DeepFilterNet3 output as a placeholder; Resemble Enhance pending
- Optional future: MossFormer2-SS and Resemble Enhance

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
- The active local `.env` uses R2 storage and the Runpod runner
- The API was restarted with `--reload` after the Runpod wiring change

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
- Local storage fallback: `var/storage/`
- Env prefix: `PARECUT_`; see `.env.example`
- The active `.env` uses `PARECUT_STORAGE_BACKEND=r2` and `PARECUT_PIPELINE_RUNNER=runpod`;
  `.env.example` keeps the local/mock defaults for a plain checkout

## Verification

- Backend: `uv run pytest -q` -> 63 passed
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

The Runpod runtime was verified after switching `.env` to R2 + Runpod. A UI job was
submitted with a real `runpod_job_id`, Runpod showed it in queue and then running, the
backend recorded completion about 27 seconds later, and 15 artifacts were written to
R2. The job detail page showed `Stub — ...` labels, the text previews and copy worked
through the same-origin endpoint, and an audio artifact loaded with duration 20s.

The DeepFilterNet3 path was verified with a noisy speech sample on endpoint release #6.
The job completed with `Denoised Audio (DeepFilterNet3)` and 15 artifacts. The downloaded
cleaned WAV had a different SHA-256 from the source, was 48 kHz mono, and the trailing
noise floor dropped from -41.9 dB mean / -30.5 dB max to -65.9 dB mean / -47.7 dB max
(about 24 dB of noise reduction). The UI, audio players, and downloads all worked.

The deterministic cut rules were verified by regenerating that Runpod job's outputs
through `PATCH /speakers` with both speakers still presenters. The before-cut SRT kept
"Today we're gonna— sorry, let me go again."; the after-cut SRT dropped it; and
`ROUGH-CUT.md` listed it as a `FALSE_START` in the remove table and audit log.

The full model stack was verified on release #13 with a two-voice test clip:

- pyannote found `SPEAKER_00` and `SPEAKER_01`.
- WhisperX produced four aligned, speaker-attributed segments.
- Demucs produced real music and dialogue stems.
- The worker produced two gated speaker stems.
- The before transcript contained all four segments; `PATCH /speakers` with
  `SPEAKER_01=feeder` removed its two lines from the after transcript and changed the
  `ROUGH-CUT.md` speaker map to `REMOVE ALL`.

A 33s WhatsApp OGG voice note also completed with real transcription, denoising, and
Demucs stems. It ran on the pre-#13 worker and used the one-speaker fallback; jobs on
release #13 use the aligned, diarized path.

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
- `b78fb0e`: R2 upload proxy and same-origin text artifacts
- `4148666`: test isolation for local/mock fixtures
- `4144194`: false-start and retake cut rules
- `a732a2e`: DeepFilterNet3 worker denoising
- `0d037d0`: install git for DeepFilterNet logging
- `37696ea`: install soundfile backend for torchaudio
- `63eddcb`: full-stack worker models
- `3cc10b3`: CTranslate2 4.6 for newer glibc
- `4a5daf2`: bake all pyannote diarization models
- `c12bc4e`: word alignment and speaker-split transcript
- `e660ac9`: correct real vs demo labels after role regeneration

The progress file itself adds one more documentation commit after these.

## Next actions in order

1. Add Resemble Enhance for the enhancement stage. `enhanced_audio` currently reuses
   the DeepFilterNet3 output and is labeled `Denoised Audio (Enhancement pending)`.
2. Replace the gated per-speaker stems with true target-speaker extraction
   (MossFormer2-SS) if the product needs overlapping-speech separation.
3. Add LLM take selection on top of the deterministic rule pass. The current rules
   remove silence, feeder lines, restart false starts, and same-speaker retakes.
4. Task 20: serve the built SPA from FastAPI, finish README and manual smoke test.
5. Create `parecut-separate`; publish a new `sha-<short>` worker release for each change.
6. Optional: add R2 CORS if direct browser uploads should replace the FastAPI proxy.
7. Consider CUDA torch for faster inference; the current worker is CPU-only.
8. Add Redis, Stripe, OAuth, and retention.

## Non-negotiables

- No secrets in the repository. `.env` is ignored.
- Keep the three seams intact when adding R2, Redis, and Runpod.
- Preserve sample-exact audio outputs.
- Keep the UI monochrome. Red is only for errors.
- Keep demo content labeled as demo.
- Keep the license and copyright notices.
