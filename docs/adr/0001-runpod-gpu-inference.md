# ADR 0001: RunPod Serverless for GPU inference

- Status: Accepted
- Date: 2026-11-07
- Supersedes: the Modal references in `PARECUT-SRS-v2.0.md`

## Context

Parecut needs on-demand GPU inference for enhancement, separation, diarization, and transcription. The first SRS draft assumed Modal. The deployment target is now RunPod Serverless.

Phase 1 does not contain real GPU code. It uses the `PipelineRunner` seam and a mock runner. This decision changes the future implementation and the architecture documents, not the working Phase 1 shell.

## Decision

Use RunPod Serverless for GPU inference, with FastAPI as the orchestrator and Cloudflare R2 as the artifact store.

## Architecture

### Endpoints

RunPod configures the GPU type per endpoint, so split workers by GPU class:

| Endpoint | GPU | Work |
|---|---|---|
| `parecut-audio` | L4 | enhancement, diarization, transcription, word alignment |
| `parecut-separate` | A10G | music separation, target-speaker extraction |

CPU work (noise reduction, timecodes, rule-based cut planning) stays in FastAPI. LLM take selection can run in FastAPI or a CPU endpoint later.

### Request flow

1. `RunPodPipelineRunner` implements the existing `PipelineRunner` protocol.
2. FastAPI creates short-lived presigned R2 GET and PUT URLs for the job's inputs and outputs.
3. FastAPI calls `POST https://api.runpod.ai/v2/{endpoint_id}/run` with the API key, the input payload, and an optional webhook URL.
4. FastAPI stores `runpod_job_id` on the job and polls `/status/{id}` every 1 to 2 seconds, or receives a signed completion callback from the worker.
5. The runner updates `stage_states` and publishes `JobEvent`s to the existing broker, so the SSE contract and UI do not change.
6. On success FastAPI settles credits. On failure it refunds and marks the job failed.

### Worker contract

- `runpod_app/worker.py` starts with `runpod.serverless.start({"handler": handler})`.
- The handler downloads inputs from presigned R2 URLs, runs the requested `parecut_engine` stages, uploads outputs to presigned R2 URLs, and returns artifact metadata.
- Workers use `runpod.serverless.progress_update` for stage progress. They never connect to Postgres.
- Workers never receive R2 credentials. Only presigned URLs.
- Model weights are baked into the image or mounted read-only from a RunPod network volume. Prefer the image for small hot models and the volume for large shared weights.
- Enable FlashBoot on endpoints. Keep `workersMin = 0` until paid volume justifies a warm worker.

### Security

- `RUNPOD_API_KEY` lives only in the FastAPI environment.
- Endpoint IDs and webhook secrets are configuration, not source.
- If a worker calls back to FastAPI, the callback is HMAC-SHA256 signed by the worker with a shared secret. Do not rely on RunPod to sign application callbacks.
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
- Cold start behavior is controlled per endpoint with FlashBoot and worker warmness.
- Progress is pulled from RunPod status by default; signed worker callbacks are optional.
- The Phase 1 mock runner remains the default until Phase 3.

## Migration steps

1. Benchmark the four audio stages on RunPod with real recordings.
2. Build the two worker images and endpoint configurations.
3. Add `RunPodPipelineRunner` behind the existing protocol.
4. Replace the mock runner in production configuration.
5. Remove the mock runner only after the real pipeline is verified.
