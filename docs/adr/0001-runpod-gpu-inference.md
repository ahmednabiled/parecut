# ADR 0001: Runpod Serverless for GPU inference

- Status: Accepted; backend runner and stub worker implemented
- Date: 2026-11-07
- Last verified against Runpod docs: 2026-11-08
- Supersedes: the Modal references in `PARECUT-SRS-v2.0.md`

## Context

Parecut needs on-demand GPU inference for enhancement, separation, diarization, and transcription. The first SRS draft assumed Modal. The deployment target is now Runpod Serverless.

The initial Phase 1 shell used a mock runner. The backend now contains `R2ObjectStorage`, `RunpodPipelineRunner`, and a remote worker contract in `runpod_app/`. The worker still runs a stub pipeline; the real audio models are the next step.

## Decision

Use **Runpod Serverless queue-based endpoints** for GPU inference, with FastAPI as the orchestrator and Cloudflare R2 as the artifact store.

Queue-based endpoints are the correct fit because jobs are long-running and asynchronous. They use handler functions plus `/run`, `/status`, `/stream`, `/cancel`, and `/retry`. Load-balancing endpoints are for real-time HTTP services and would require a different contract.

## Architecture

### Endpoints

Runpod configures the GPU type per endpoint, so split workers by GPU class:

| Endpoint | GPU | Work |
|---|---|---|
| `parecut-audio` | 24 GB `AMPERE_24` (L4/A5000/3090) | enhancement, diarization, transcription, word alignment |
| `parecut-separate` | 24 GB `AMPERE_24` (future) | music separation, target-speaker extraction |

A10G is not listed in the current Serverless GPU catalog, so the 24 GB pool replaces it. CPU work (noise reduction, timecodes, rule-based cut planning) stays in FastAPI. LLM take selection can run in FastAPI or a CPU endpoint later.

Endpoint settings:

- `workers.min = 0` for scale-to-zero.
- `workers.max` sized to expected concurrency.
- `idleTimeout` short enough to release idle workers.
- FlashBoot enabled with `flashboot = FLASHBOOT`. The console default is enabled, but REST v2 defaults FlashBoot to `OFF`, so set it explicitly.
- Execution timeout large enough for a 3-hour source. The console default is 600 seconds; REST v2 endpoint `timeout` defaults to 300000 ms, so set it explicitly.

### Request flow

1. `RunpodPipelineRunner` implements the existing `PipelineRunner` protocol.
2. FastAPI creates short-lived presigned R2 GET and PUT URLs for the job's inputs and outputs.
3. FastAPI calls `POST https://api.runpod.ai/v2/{endpoint_id}/run` with a Bearer API key. The body is `{"input": {...}}`; the optional `webhook` field is a top-level sibling of `input`.
4. FastAPI stores `runpod_job_id` on the job.
5. For progress, FastAPI polls `GET /status/{runpod_job_id}` every 1 to 2 seconds. `runpod.serverless.progress_update` output is available through that status response.
6. Optionally, Runpod posts the terminal job to the `webhook` URL. The receiver verifies the job id and terminal status with `/status` before settling credits. Runpod webhooks are not signed.
7. The runner updates `stage_states` and publishes `JobEvent`s to the existing broker, so the SSE contract and UI do not change.
8. On success FastAPI settles credits. On failure it refunds and marks the job failed.

### Worker contract

- `runpod_app/worker.py` starts with `runpod.serverless.start({"handler": handler})`.
- The handler reads `job["input"]`, downloads inputs from presigned R2 URLs, runs the requested `parecut_engine` stages, uploads outputs to presigned R2 URLs, and returns artifact metadata.
- Workers use `runpod.serverless.progress_update(job, "...")` for stage progress. Progress is read through `/status`; it is not a separate streaming protocol in our backend.
- Progress updates caused the stub worker to hang in Runpod while the handler had already finished. Keep them disabled until they are wrapped with a timeout or replaced with a safer mechanism.
- Workers use `runpod>=2.1,<3` and Python 3.10 to 3.14. Parecut uses Python 3.12.
- Workers never connect to Postgres.
- Workers never receive R2 credentials. Only presigned URLs.

### Operational limits

- `/run` accepts payloads up to 10 MB. Pass R2 URLs, not audio bytes.
- `/run` is asynchronous and returns `IN_QUEUE` immediately.
- `/status` returns `IN_QUEUE`, `IN_PROGRESS`, `COMPLETED`, `FAILED`, `CANCELLED`, or `TIMED_OUT`, plus `delayTime`, `executionTime`, `output`, and progress.
- Asynchronous results are retained for 30 minutes after completion. Keep `/status` as the fallback for settlement if a webhook is missed.
- `/runsync` is not used for audio jobs. It accepts up to 20 MB and its result window is 1 minute by default and 5 minutes maximum.
- Runpod retries a failed webhook up to 2 more times with a 10-second delay. The receiver must be public HTTPS and return 2xx.
- The same completion can arrive more than once. Dedupe on the Runpod job id.
- A failed webhook does not fail the job. The job is still retrievable through `/status`.

### Model stack

- Noise reduction: DeepFilterNet3
- Diarization: NVIDIA Nemotron-3-Diarization (100M parameters, up to 8 speakers, OpenMDW 1.1)
- Transcription and word timing: WhisperX large-v3-turbo
- Music separation: Demucs
- Speech separation, optional: MossFormer2-SS
- Enhancement, optional: Resemble Enhance

Nemotron-3-Diarization replaces pyannote for speaker attribution. It does not separate voices into audio stems; MossFormer2-SS and Demucs still handle separation.

### Model storage

- Small hot models can be baked into the worker image.
- Large shared weights belong on a Runpod network volume mounted at `/runpod-volume`.
- Network volumes pin an endpoint to one data center, which can reduce GPU availability. Attach multiple volumes across data centers only if needed.
- The SDK's `VolumeCache` helper can persist Hugging Face and model caches across workers.
- Global volumes are an alternative for read-heavy weights, but they are beta and GPU-only.

### Security

- `RUNPOD_API_KEY` lives only in the FastAPI environment.
- Endpoint IDs live in configuration, not source.
- Runpod completion webhooks are unsigned. Verify the Runpod job id and status with `/status` before changing credits or job state. Use a secret, non-guessable webhook path and keep the receiver idempotent.
- If strict authenticity is required for progress callbacks, have the worker call a Parecut endpoint with an HMAC-SHA256 signature instead of relying on Runpod webhooks.
- Backend upload/download URLs expire in 15 minutes. Worker presigned URLs use a separate 6-hour TTL (`PARECUT_RUNPOD_URL_TTL_SECONDS`) so long jobs can finish.

### Schema and route changes from the SRS

- `jobs.modal_call_id` becomes `jobs.runpod_job_id`.
- `POST /api/webhooks/modal` becomes `POST /api/webhooks/runpod`.
- `modal_app/` becomes `runpod_app/`.
- `ModalPipelineRunner` becomes `RunpodPipelineRunner`.
- `modal.Volume` becomes a Runpod network volume.
- `@app.cls` / `@app.function` become Runpod serverless handlers.

### Implementation status

- R2 bucket `parecut` and a bucket-scoped token are configured; `R2ObjectStorage` is implemented.
- `RunpodPipelineRunner`, `HttpRunpodClient`, and migration `f34d11320711` are implemented.
- Endpoint `parecut-audio` (`yf16hg8td6au29`) is deployed with a stub worker.
- An end-to-end job produced 15 artifacts in R2, wrote all artifact rows, and downloaded correctly.
- The repository is private. GitHub Actions builds and pushes
  `ghcr.io/ahmednabiled/parecut-worker:dev` privately.
- Runpod pulls it with the `ghcr-parecut` registry credential, backed by a GitHub token
  scoped to `read:packages`.
- The private pull was verified end to end: a fresh worker processed a job and uploaded
  15 artifacts to R2.
- The `dev` tag is mutable; pin `sha-<short>` for production releases.
- The real audio models are still pending.

## Consequences

- No changes to the UI, SSE contract, storage protocol, or credit rules.
- Runpod endpoint configuration and worker images become deployment artifacts.
- Polling is the default progress mechanism. Webhooks are an optional latency optimization, not the source of truth.
- Cold start behavior is controlled per endpoint with FlashBoot and worker warmness.
- Mock and local storage remain the defaults. Set `PARECUT_PIPELINE_RUNNER=runpod` and
  `PARECUT_STORAGE_BACKEND=r2` for remote mode.

## Migration steps

1. Benchmark the audio models on Runpod with real recordings.
2. Build the real worker image and push it to a persistent registry.
3. Create `parecut-separate` for Demucs and MossFormer2-SS.
4. Switch the app to R2 storage and the Runpod runner.
5. Remove the mock runner only after the real pipeline is verified.

## References

- Send requests and webhooks: https://docs.runpod.io/serverless/endpoints/send-requests
- Operation reference (`/run`, `/status`, `/stream`, `/cancel`, `/retry`): https://docs.runpod.io/serverless/endpoints/operation-reference
- Handler functions and progress updates: https://docs.runpod.io/serverless/workers/handler-functions
- Endpoint configuration and FlashBoot: https://docs.runpod.io/serverless/endpoints/endpoint-configurations
- Network volumes: https://docs.runpod.io/storage/network-volumes
- Volume cache: https://docs.runpod.io/serverless/development/volume-cache
- Python SDK: https://docs.runpod.io/sdk/overview
