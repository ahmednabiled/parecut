# ADR 0001: RunPod Serverless for GPU inference

- Status: Accepted
- Date: 2026-11-07
- Last verified against RunPod docs: 2026-11-08
- Supersedes: the Modal references in `PARECUT-SRS-v2.0.md`

## Context

Parecut needs on-demand GPU inference for enhancement, separation, diarization, and transcription. The first SRS draft assumed Modal. The deployment target is now RunPod Serverless.

Phase 1 does not contain real GPU code. It uses the `PipelineRunner` seam and a mock runner. This decision changes the future implementation and the architecture documents, not the working Phase 1 shell.

## Decision

Use **RunPod Serverless queue-based endpoints** for GPU inference, with FastAPI as the orchestrator and Cloudflare R2 as the artifact store.

Queue-based endpoints are the correct fit because jobs are long-running and asynchronous. They use handler functions plus `/run`, `/status`, `/stream`, `/cancel`, and `/retry`. Load-balancing endpoints are for real-time HTTP services and would require a different contract.

## Architecture

### Endpoints

RunPod configures the GPU type per endpoint, so split workers by GPU class:

| Endpoint | GPU | Work |
|---|---|---|
| `parecut-audio` | L4 | enhancement, diarization, transcription, word alignment |
| `parecut-separate` | A10G | music separation, target-speaker extraction |

CPU work (noise reduction, timecodes, rule-based cut planning) stays in FastAPI. LLM take selection can run in FastAPI or a CPU endpoint later.

Endpoint settings:

- `workersMin = 0` for scale-to-zero.
- `workersMax` sized to expected concurrency.
- `idleTimeout` short enough to release idle workers.
- FlashBoot enabled with `flashBootType = FLASHBOOT`. The console default is enabled, but REST v2 defaults FlashBoot to off, so set it explicitly.
- Execution timeout large enough for a 3-hour source (the service default is 600 seconds, so this must be raised).

### Request flow

1. `RunPodPipelineRunner` implements the existing `PipelineRunner` protocol.
2. FastAPI creates short-lived presigned R2 GET and PUT URLs for the job's inputs and outputs.
3. FastAPI calls `POST https://api.runpod.ai/v2/{endpoint_id}/run` with a Bearer API key. The body is `{"input": {...}}`; the optional `webhook` field is a top-level sibling of `input`.
4. FastAPI stores `runpod_job_id` on the job.
5. For progress, FastAPI polls `GET /status/{runpod_job_id}` every 1 to 2 seconds. `runpod.serverless.progress_update` output is available through that status response.
6. Optionally, RunPod posts the terminal job to the `webhook` URL. The receiver verifies the job id and terminal status with `/status` before settling credits. RunPod webhooks are not signed.
7. The runner updates `stage_states` and publishes `JobEvent`s to the existing broker, so the SSE contract and UI do not change.
8. On success FastAPI settles credits. On failure it refunds and marks the job failed.

### Worker contract

- `runpod_app/worker.py` starts with `runpod.serverless.start({"handler": handler})`.
- The handler reads `job["input"]`, downloads inputs from presigned R2 URLs, runs the requested `parecut_engine` stages, uploads outputs to presigned R2 URLs, and returns artifact metadata.
- Workers use `runpod.serverless.progress_update(job, "...")` for stage progress. Progress is read through `/status`; it is not a separate streaming protocol in our backend.
- Workers use `runpod>=2.0` and Python 3.10 to 3.14. Parecut uses Python 3.12.
- Workers never connect to Postgres.
- Workers never receive R2 credentials. Only presigned URLs.

### Operational limits

- `/run` accepts payloads up to 10 MB. Pass R2 URLs, not audio bytes.
- `/run` is asynchronous and returns `IN_QUEUE` immediately.
- `/status` returns `IN_QUEUE`, `IN_PROGRESS`, `COMPLETED`, or `FAILED`, plus `delayTime`, `executionTime`, `output`, and progress.
- Asynchronous results are retained for 30 minutes after completion. Keep `/status` as the fallback for settlement if a webhook is missed.
- `/runsync` is not used for audio jobs. Its result window is 1 minute by default and 5 minutes maximum.
- RunPod retries a failed webhook up to 2 more times with a 10-second delay. The receiver must be public HTTPS and return 2xx.
- The same completion can arrive more than once. Dedupe on the RunPod job id.
- A failed webhook does not fail the job. The job is still retrievable through `/status`.

### Model storage

- Small hot models can be baked into the worker image.
- Large shared weights belong on a RunPod network volume mounted at `/runpod-volume`.
- Network volumes pin an endpoint to one data center, which can reduce GPU availability. Attach multiple volumes across data centers only if needed.
- The SDK's `VolumeCache` helper can persist Hugging Face and model caches across workers.
- Global volumes are an alternative for read-heavy weights, but they are beta and GPU-only.

### Security

- `RUNPOD_API_KEY` lives only in the FastAPI environment.
- Endpoint IDs live in configuration, not source.
- RunPod completion webhooks are unsigned. Verify the RunPod job id and status with `/status` before changing credits or job state. Use a secret, non-guessable webhook path and keep the receiver idempotent.
- If strict authenticity is required for progress callbacks, have the worker call a Parecut endpoint with an HMAC-SHA256 signature instead of relying on RunPod webhooks.
- All R2 URLs expire in 15 minutes or less.

### Schema and route changes from the SRS

- `jobs.modal_call_id` becomes `jobs.runpod_job_id`.
- `POST /api/webhooks/modal` becomes `POST /api/webhooks/runpod`.
- `modal_app/` becomes `runpod_app/`.
- `ModalPipelineRunner` becomes `RunPodPipelineRunner`.
- `modal.Volume` becomes a RunPod network volume.
- `@app.cls` / `@app.function` become RunPod serverless handlers.

## Consequences

- No changes to the UI, SSE contract, storage protocol, or credit rules.
- RunPod endpoint configuration and worker images become deployment artifacts.
- Polling is the default progress mechanism. Webhooks are an optional latency optimization, not the source of truth.
- Cold start behavior is controlled per endpoint with FlashBoot and worker warmness.
- The Phase 1 mock runner remains the default until Phase 3.

## Migration steps

1. Benchmark the four audio stages on RunPod with real recordings.
2. Build the two worker images and endpoint configurations.
3. Add `RunPodPipelineRunner` behind the existing protocol.
4. Replace the mock runner in production configuration.
5. Remove the mock runner only after the real pipeline is verified.

## References

- Send requests and webhooks: https://docs.runpod.io/serverless/endpoints/send-requests
- Operation reference (`/run`, `/status`, `/stream`, `/cancel`, `/retry`): https://docs.runpod.io/serverless/endpoints/operation-reference
- Handler functions and progress updates: https://docs.runpod.io/serverless/workers/handler-functions
- Endpoint configuration and FlashBoot: https://docs.runpod.io/serverless/endpoints/endpoint-configurations
- Network volumes: https://docs.runpod.io/storage/network-volumes
- Volume cache: https://docs.runpod.io/serverless/development/volume-cache
- Python SDK: https://docs.runpod.io/sdk/overview
