# GPU Inference and Compressed Audio Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run audio models on the worker GPU and emit MP3 audio artifacts by default, with a per-run lossless option.

**Architecture:** A new `audio_format` pipeline field flows from the inspector through effect creation into `expected_artifacts`, which chooses `.mp3`/`.wav` keys and formats. The worker encodes generated audio at upload with ffmpeg. Separately, the worker image moves to CUDA PyTorch 2.7.1 and each model selects `cuda` per stage, with a `PARECUT_GPU_STAGES` override and CPU fallback.

**Tech Stack:** FastAPI, SQLModel, Pydantic, React/TypeScript, ffmpeg (libmp3lame), PyTorch 2.7.1 cu128, WhisperX, faster-whisper, Demucs, Resemble Enhance, DeepFilterNet, Nemotron diarization, Runpod serverless.

**Spec:** `docs/superpowers/specs/2026-11-16-gpu-inference-and-audio-compression-design.md`

## Global Constraints

- Blackwell GPU (sm_120) requires PyTorch >= 2.7 built with CUDA 12.8.
- Default generated audio format is MP3, constant bitrate 192 kbps, `audio/mpeg`.
- WAV remains selectable per effect run; source uploads are never re-encoded.
- Every model call must fall back to CPU when CUDA is unavailable.
- Keep the existing monochrome UI and the existing editor playback/seek behavior.
- Backend tests run with `uv run pytest -q`; frontend checks run in `web/` with `npm run typecheck`, `npm test`, `npm run build`.

## Review Focus

- An old WAV artifact from a previous run must still play after the change.
- A job created before the field existed (no `audio_format`) must default to MP3, not fail validation.
- An MP3 encode failure must fail the job, never upload WAV bytes under an `.mp3` key.
- The worker must still complete on a host without CUDA.
- A language-picker/lossless toggle combination must send exactly the fields the selected effect supports.

---

### Task 1: Add `audio_format` to the pipeline schema and effect creation

**Files:**
- Modify: `parecut_engine/schemas.py`
- Modify: `app/schemas.py`
- Modify: `app/services/jobs.py`
- Test: `tests/test_schemas.py`
- Test: `tests/test_effect_runs.py`

**Interfaces:**
- Produces: `AudioFormat = Literal["mp3", "wav"]`; `PipelineConfig.audio_format: AudioFormat = "mp3"`; `EffectCreate.audio_format: AudioFormat | None = None`; `effect_config(..., audio_format: AudioFormat | None = None)`.

- [ ] **Step 1: Write failing schema tests**

```python
def test_pipeline_config_defaults_to_mp3():
    assert PipelineConfig().audio_format == "mp3"


def test_pipeline_config_rejects_unknown_audio_format():
    with pytest.raises(ValidationError):
        PipelineConfig(audio_format="flac")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_schemas.py -q`
Expected: FAIL — `audio_format` is not a field.

- [ ] **Step 3: Implement the field and thread it through effect creation**

Add `AudioFormat = Literal["mp3", "wav"]` and the field to `PipelineConfig`. Add the optional field to `EffectCreate`. Add the parameter to `effect_config` and set `values["audio_format"]` when provided. Pass `data.audio_format` in `create_effect_run`.

- [ ] **Step 4: Write the effect-run test**

```python
async def test_enhance_effect_stores_audio_format(app, client):
    created = await _draft_job(client)
    parent = created["job"]
    response = await client.post(
        f"/api/jobs/{parent['id']}/effects",
        json={"effect": "enhance", "audio_format": "wav"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["pipeline_config"]["audio_format"] == "wav"
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_schemas.py tests/test_effect_runs.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add parecut_engine/schemas.py app/schemas.py app/services/jobs.py tests/test_schemas.py tests/test_effect_runs.py
git commit -m "feat(audio): add per-run audio format"
```

---

### Task 2: Make `expected_artifacts` format-aware

**Files:**
- Modify: `app/services/runpod.py`
- Test: `tests/test_runpod_runner.py`

**Interfaces:**
- Consumes: `PipelineConfig.audio_format`.
- Produces: audio artifact dicts whose `key` suffix and `format` match the configured format; `mp3` for `mp3`, `wav` for `wav`.

- [ ] **Step 1: Write failing tests**

```python
def test_expected_artifacts_default_to_mp3():
    config = PipelineConfig(separate_music=True, transcribe=False, rough_cut=False)
    artifacts = expected_artifacts("job-1", config)
    music = next(a for a in artifacts if a["kind"] == "stem_music")
    assert music["key"].endswith(".mp3")
    assert music["format"] == "mp3"


def test_expected_artifacts_honor_wav():
    config = PipelineConfig(
        separate_music=True, transcribe=False, rough_cut=False, audio_format="wav"
    )
    artifacts = expected_artifacts("job-1", config)
    music = next(a for a in artifacts if a["kind"] == "stem_music")
    assert music["key"].endswith(".wav")
    assert music["format"] == "wav"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_runpod_runner.py -q`
Expected: FAIL — keys still end in `.wav`.

- [ ] **Step 3: Implement the suffix swap**

Replace each audio filename's suffix with `config.audio_format` and set `"format": config.audio_format`; apply the same to generated speaker keys. Leave transcript and rough-cut artifacts untouched.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_runpod_runner.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/runpod.py tests/test_runpod_runner.py
git commit -m "feat(audio): choose artifact format from pipeline config"
```

---

### Task 3: Encode audio artifacts in the worker

**Files:**
- Modify: `runpod_app/worker.py`
- Test: `tests/test_worker_stub.py`

**Interfaces:**
- Produces: `AUDIO_ARTIFACT_KINDS: set[str]`; `_encode_audio(content: bytes, workdir: Path, fmt: str, name: str) -> bytes`; `MIME_TYPES["mp3"] == "audio/mpeg"`.

- [ ] **Step 1: Write failing tests**

```python
def test_encode_audio_writes_mp3(tmp_path):
    wav = tmp_path / "tone.wav"
    with wave.open(str(wav), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(8000)
        writer.writeframes(b"\x00\x00" * 8000)
    encoded = _encode_audio(wav.read_bytes(), tmp_path, "mp3", "tone")
    assert encoded[:3] == b"ID3" or encoded[0] == 0xFF


def test_encode_audio_passthrough_wav(tmp_path):
    payload = b"RIFF....WAVE"
    assert _encode_audio(payload, tmp_path, "wav", "tone") == payload
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_worker_stub.py -q`
Expected: FAIL — `_encode_audio` is not defined.

- [ ] **Step 3: Implement `_encode_audio` and call it before upload**

MP3 path: write bytes to `workdir/<name>.src`, run `ffmpeg -i <src> -vn -c:a libmp3lame -b:a 192k <workdir>/<name>.mp3`, return its bytes; raise `RuntimeError` with the stderr tail on failure. In the handler, if the artifact kind is an audio kind and the format is `mp3`, encode before `_upload`; `wav` passes through. Add `"mp3": "audio/mpeg"` to `MIME_TYPES`.

- [ ] **Step 4: Write the handler MIME test**

Build a job whose expected audio artifacts use `format="mp3"` and keys ending `.mp3`, run `handler` with the existing fakes, and assert the uploaded request content type is `audio/mpeg` and the body is not a RIFF WAV.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_worker_stub.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add runpod_app/worker.py tests/test_worker_stub.py
git commit -m "feat(worker): encode audio artifacts to mp3"
```

---

### Task 4: Serve MP3 through the API

**Files:**
- Modify: `app/routers/jobs.py`
- Test: `tests/test_jobs_read.py`

**Interfaces:**
- Produces: `CONTENT_MEDIA_TYPES["mp3"] == "audio/mpeg"`.

- [ ] **Step 1: Write the failing test**

```python
def test_mp3_artifacts_are_served_as_audio_mpeg():
    assert CONTENT_MEDIA_TYPES["mp3"] == "audio/mpeg"
```

- [ ] **Step 2: Run it to confirm failure**

Run: `uv run pytest tests/test_jobs_read.py -q`
Expected: FAIL — `KeyError: 'mp3'`.

- [ ] **Step 3: Add the mapping**

Add `"mp3": "audio/mpeg"` next to `"wav"`. No route changes are needed; range streaming and download already use the artifact format and key.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_jobs_read.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/routers/jobs.py tests/test_jobs_read.py
git commit -m "feat(api): serve mp3 artifacts as audio/mpeg"
```

---

### Task 5: Run models on GPU with a per-stage override

**Files:**
- Modify: `runpod_app/worker.py`
- Modify: `runpod_app/nemotron_diarize.py`
- Modify: `runpod_app/Dockerfile`
- Modify: `.github/workflows/worker-image.yml`
- Test: `tests/test_worker_stub.py`

**Interfaces:**
- Produces: `_gpu_stages() -> set[str] | None`; `_device_for(stage: str) -> str`; `_compute_type_for(stage: str) -> str`.
- Env: `PARECUT_GPU_STAGES` (comma list, `all` default).

- [ ] **Step 1: Write failing tests**

```python
def test_gpu_stages_defaults_to_all(monkeypatch):
    monkeypatch.delenv("PARECUT_GPU_STAGES", raising=False)
    assert _gpu_stages() is None


def test_gpu_stages_reads_csv(monkeypatch):
    monkeypatch.setenv("PARECUT_GPU_STAGES", "enhance,separate_music")
    assert _gpu_stages() == {"enhance", "separate_music"}


def test_device_for_disabled_stage_is_cpu(monkeypatch):
    monkeypatch.setenv("PARECUT_GPU_STAGES", "enhance")
    assert _device_for("separate_music") == "cpu"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_worker_stub.py -q`
Expected: FAIL — helpers are not defined.

- [ ] **Step 3: Implement device helpers and use them**

`_device_for` returns `"cuda"` only when the stage is allowed and `torch.cuda.is_available()`, otherwise `"cpu"`. Use it for WhisperX load, raw faster-whisper load, alignment load and `whisperx.align`, Demucs `apply_model`, and Resemble Enhance. Use `float16` on CUDA and `int8` on CPU for CTranslate2. Log `"<stage> device=<device>"` once per model load. Pass the chosen diarization device to the Nemotron subprocess as `PARECUT_NEMOTRON_DEVICE`; the script moves the model and inputs to it and falls back to CPU on failure.

- [ ] **Step 4: Update the image and workflow**

- Main environment: `torch==2.7.1 torchaudio==2.7.1` from `https://download.pytorch.org/whl/cu128`; remove CPU indexes.
- Nemotron venv: `python -m venv --system-site-packages /opt/nemotron`; install only `transformers==5.22.1`, `numpy<2`, `soundfile`, `librosa`, `accelerate` (do not reinstall torch).
- Export `LD_LIBRARY_PATH` to the torch `nvidia/*/lib` directories so CTranslate2 finds cuDNN/cuBLAS.
- Add a build smoke check printing torch version, CUDA version, and `torch.cuda.get_arch_list()`.
- Add `jlumbroso/free-disk-space@v1.3.1` before the build in the workflow.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_worker_stub.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add runpod_app/worker.py runpod_app/nemotron_diarize.py runpod_app/Dockerfile .github/workflows/worker-image.yml tests/test_worker_stub.py
git commit -m "feat(worker): run audio models on GPU with CPU fallback"
```

---

### Task 6: Add the inspector output control

**Files:**
- Modify: `web/src/api/types.ts`
- Modify: `web/src/lib/effects.ts`
- Modify: `web/src/components/editor/Inspector.tsx`
- Modify: `web/src/pages/JobEditor.tsx`
- Modify: `web/src/components/PipelineToggles.test.tsx`
- Modify: `web/src/lib/credits.test.ts`
- Test: `web/src/components/editor/Inspector.test.tsx`

**Interfaces:**
- Produces: `AudioFormat = "mp3" | "wav"`; `PipelineConfig.audio_format: AudioFormat`; `DEFAULT_AUDIO_FORMAT = "mp3"`; `EffectCreate` payload field `audio_format`.

- [ ] **Step 1: Write the failing component test**

Render `Inspector` with the existing required props, select **Lossless (WAV)**, click **Apply enhancement**, and assert `onApply` received `("enhance", ..., ..., "wav")` (adjust to the actual callback signature after reading the component).

- [ ] **Step 2: Run it to verify failure**

Run: `cd web && npm test -- Inspector`
Expected: FAIL — the control does not exist.

- [ ] **Step 3: Implement the control and payload**

Add a small segmented control labelled **Generated audio** with **Standard (MP3)** and **Lossless (WAV)**. Default to `DEFAULT_AUDIO_FORMAT`; restore the latest run's `pipeline_config.audio_format` when it changes. Pass the value through `onApply` and into the effect mutation payload as `audio_format`. Add the field to the `PipelineConfig` fixtures in `PipelineToggles.test.tsx` and `credits.test.ts`.

- [ ] **Step 4: Run frontend checks**

Run: `cd web && npm run typecheck && npm test && npm run build`
Expected: typecheck clean, all tests pass, build succeeds.

- [ ] **Step 5: Commit**

```bash
git add web/src
git commit -m "feat(editor): choose standard mp3 or lossless wav output"
```

---

### Task 7: Verify, deploy, and document

**Files:**
- Modify: `README.md`
- Modify: `PROGRESS.md`

- [ ] **Step 1: Run the full suites**

Run: `uv run pytest -q` and `cd web && npm run typecheck && npm test && npm run build`.
Expected: all pass.

- [ ] **Step 2: Build and push the worker image**

Push to `dev`, watch `worker-image.yml` succeed, and confirm the `sha-<short>` tag exists.

- [ ] **Step 3: Deploy worker-first**

Create a Runpod release with the new tag while the API is still on WAV, replace outdated workers, and confirm two workers report the new version.

- [ ] **Step 4: Deploy the API/UI and run a live separation**

Run music separation on the demo clip. Confirm:

- worker logs `separate_music device=cuda` and `enhance device=cuda`
- the stem artifacts are `.mp3`/`audio/mpeg` and roughly 10x smaller than the old WAV
- playback starts immediately, seeking is smooth, peaks and download work
- an old WAV artifact from before the change still plays

- [ ] **Step 5: Compare timings**

Record CPU baseline vs GPU for enhance, separation, and transcription on the same clip.

- [ ] **Step 6: Update docs and commit**

Record the release tag, GPU results, MP3 sizes, the `PARECUT_GPU_STAGES` override, and the WAV option in `PROGRESS.md`; update the README feature/limitation list.

```bash
git add README.md PROGRESS.md
git commit -m "docs: record GPU inference and mp3 artifacts"
```
