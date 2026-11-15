# GPU inference and compressed audio artifacts

Date: 2026-11-16
Status: approved direction, pending implementation

## Intent

Two problems block the editor: enhancement/separation/transcription run on CPU and
take minutes, and generated audio artifacts are large WAV files that make browser
playback sluggish. Move inference onto the GPU that the Runpod endpoint already
provisions, and make generated audio small enough to stream reliably, with a
lossless escape hatch.

## Goals

- Run Resemble Enhance, Demucs, WhisperX/faster-whisper, alignment, and Nemotron
  diarization on GPU when one is available, with CPU fallback.
- Generate MP3 audio artifacts by default (constant bitrate), so stems and enhanced
  tracks stream and seek without stalling the editor.
- Let the user choose lossless WAV per effect run when they need it.
- Keep every existing artifact (old WAV runs) playable.
- Keep the worker deployable through the existing GitHub Actions image and Runpod
  release flow.

## Non-goals

- True target-speaker separation (MossFormer2) or new separation models.
- Re-encoding historical artifacts.
- GPU-accelerated ffmpeg studio polish.
- New transcription languages.
- Changing source uploads; the original is never re-encoded.

## Constraints

- Endpoint GPU: NVIDIA RTX PRO 6000 Blackwell Server Edition, MIG 1g.24gb,
  compute capability 12.0 (sm_120).
- Blackwell requires PyTorch >= 2.7 built with CUDA 12.8 or newer.
- Worker runs Python 3.11; images are built on a GitHub-hosted amd64 runner.
- GitHub-hosted runners have limited free disk; a CUDA image is roughly 4 GB
  larger than the current CPU image.
- The worker is stateless per request; models are loaded lazily and cached in the
  process.

## Decisions

### GPU runtime

1. Install `torch`/`torchaudio` 2.7.1 from the CUDA 12.8 index in the main
   environment. This is the first release line that ships sm_120 kernels.
2. Create the Nemotron environment with `--system-site-packages` and do not
   reinstall torch there, so the image carries one CUDA torch instead of two.
   The venv installs only its conflicting packages (`transformers` 5.x, `numpy`,
   `soundfile`, `librosa`, `accelerate`).
3. Add a small device helper in the worker:
   `_torch_device()` returns `"cuda"` when `torch.cuda.is_available()`, otherwise
   `"cpu"`; `_compute_type()` returns `"float16"` on CUDA and `"int8"` on CPU.
4. Load WhisperX, the raw faster-whisper model, and alignment models with that
   device/compute type. Demucs `apply_model` receives the device.
5. Resemble Enhance keeps its existing `cuda if available else cpu` selection.
   DeepFilterNet already selects the device internally via `df.modules.get_device()`
   once torch is a CUDA build; no code change is required.
6. The Nemotron diarization script selects CUDA when available and moves the model
   and inputs there, falling back to CPU.
7. Expose the CUDA/cuDNN libraries bundled by the torch wheels to CTranslate2 with
   `LD_LIBRARY_PATH`, because faster-whisper loads cuDNN at runtime.
8. Add a CUDA import smoke check to the image build (torch version, CUDA version,
   arch list) so a broken wheel fails the build rather than a job.
9. Add a disk-cleanup step to the worker-image workflow before the Docker build.
10. Add a per-stage GPU allowlist, `PARECUT_GPU_STAGES` (default: all stages). A
    stage that misbehaves on GPU can be forced to CPU by changing the endpoint
    environment variable and restarting workers, without rebuilding the image.
11. Record the device each stage chose in the worker log (`<stage> device=cuda|cpu`),
    so the first live run proves GPU use and a regression is visible immediately.
12. Treat the Runpod GPU class as a runtime fact, not a build assumption. PyTorch
    2.7.1+cu128 supports Blackwell sm_120 and the older Ampere/Ada cards, so the
    same image works if the endpoint schedules a different worker class. The build
    cannot prove GPU execution (no GPU in CI); the live smoke run does. If the
    endpoint reports an Ampere/Ada worker instead of the PRO 6000 MIG recorded in
    the Runpod console, the image still works; only the expected speed differs.

### Compressed artifacts

10. Add `audio_format: Literal["mp3", "wav"] = "mp3"` to `PipelineConfig`; add the
    same optional field to `EffectCreate`.
11. `expected_artifacts()` uses the selected extension and format for every
    generated audio artifact (`cleaned_audio`, `enhanced_audio`, `stem_music`,
    `stem_dialogue`, `stem_speaker`). Transcript artifacts are unchanged.
12. The worker encodes generated audio at upload time through a new
    `_encode_audio(source_bytes, output_path, fmt)`: WAV passes bytes through; MP3
    runs ffmpeg with `libmp3lame`, constant bitrate 192 kbps, preserving channel
    count (mono voice, stereo stems). Encoding failure fails the job loudly rather
    than silently uploading WAV under an `.mp3` key.
13. Add `mp3` to the worker `MIME_TYPES` and the API `CONTENT_MEDIA_TYPES`, mapping
    to `audio/mpeg`. Peaks, range streaming, and download reuse the existing paths.
14. Expose one output control in the inspector's Effects section: **Standard
    (MP3)** and **Lossless (WAV)**. It defaults to MP3, and the latest effect run's
    choice is restored on reload. The selection is sent with the next effect run.
15. The UI labels the tradeoff: MP3 is small and fast to preview; WAV is lossless
    and larger.

### Deployment

13. Build and push a worker image tagged `sha-<short>`.
14. Roll out in this order:
    1. Deploy the new worker image while the API still requests WAV artifacts. The
       new worker honors the artifact format it receives, so behavior is unchanged
       until the API changes.
    2. Deploy the API and UI (default MP3) and open a fresh editor session.
    3. Run the live verification below.
15. A worker rollback after the API deploy is not safe on its own: an old worker
    would upload WAV bytes under `.mp3` keys. Roll back the API first, or roll back
    both together.
16. Create a new Runpod release pinning that tag, replace outdated workers, and
    keep two workers ready.
17. Record GPU timings and before/after artifact sizes in `PROGRESS.md`.

## Flow

1. The inspector sends `audio_format` with an effect request.
2. `effect_config()` stores it on the child job's `pipeline_config`.
3. `expected_artifacts()` builds `.mp3` keys/formats (or `.wav` when lossless).
4. The worker writes each generated artifact to a temp path, encodes it to the
   requested format, and uploads it with the matching content type.
5. The API returns the artifact `format`, and the content route serves
   `audio/mpeg`; the editor's audio elements stream and seek normally.

## Verification

- Backend: `expected_artifacts` defaults to `.mp3`/`mp3` and honors `wav`; effect
  creation stores `audio_format`; an invalid value is rejected.
- Worker: `_encode_audio` produces a valid MP3 (ffprobe) and the handler uploads
  `audio/mpeg`; CPU fallback still works with fakes; existing WAV artifact tests
  keep passing.
- Frontend: the toggle defaults to MP3, sends `audio_format`, and restores the last
  run's choice; typecheck, Vitest, and production build pass.
- Live: deploy the image, run music separation and enhancement on the demo clip.
  Confirm stem sizes are roughly an order of magnitude smaller, playback and seeking
  are smooth, peaks and download work, and stage timings are materially faster than
  the CPU baseline. Confirm the worker logs `cuda` for each model.
- Confirm an old WAV artifact from an earlier run still plays.

## Risks

- The torch upgrade can break WhisperX 3.3.1, Demucs 4.1.0, pyannote.audio 3.3.2,
  Resemble Enhance, or DeepFilterNet. Mitigation: pin versions, add import and
  device smoke checks, and keep the `PARECUT_GPU_STAGES` CPU override.
- A model may fail specifically on GPU while still working on CPU, most plausibly
  Nemotron through its shared-torch venv. The release is not blocked on that stage:
  remove it from `PARECUT_GPU_STAGES`, document it, and keep it on CPU. Only a
  model that fails on both CPU and GPU blocks the release.
- If `--system-site-packages` cannot satisfy Nemotron, fall back to a dedicated
  venv with its own torch (image grows again) rather than dropping diarization.
- CI disk exhaustion on the larger image. Mitigation: free-disk-space action,
  `--no-cache-dir`, and a single torch install shared by both environments.
- Runpod host driver too old for CUDA 12.8. Mitigation: verify from the first
  worker log; if incompatible, the endpoint must move to a host with a current
  driver.
- MP3 is lossy. Mitigation: WAV remains a per-run option and labels say so.
- First request after cold start is slower while models move to GPU. This already
  happens on CPU; accept it.
