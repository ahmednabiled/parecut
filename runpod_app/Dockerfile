# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
# Resemble Enhance and pyannote load known checkpoints with older torch.load
# semantics; torch 2.6+ defaults to weights_only=True.
ENV TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
# DeepSpeed is only imported by Resemble Enhance's training module in this image.
ENV DS_BUILD_OPS=0
WORKDIR /worker

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 libgomp1 git \
    && rm -rf /var/lib/apt/lists/*

RUN ffmpeg -hide_banner -loglevel error -f lavfi \
    -i "sine=frequency=440:duration=0.1" -c:a libmp3lame -b:a 192k \
    -y /tmp/mp3_smoke.mp3 \
    && test -s /tmp/mp3_smoke.mp3 \
    && rm -f /tmp/mp3_smoke.mp3

RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cu128 \
    "torch==2.7.1+cu128" "torchaudio==2.7.1+cu128"

RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cu128 \
    "torch==2.7.1+cu128" \
    "torchaudio==2.7.1+cu128" \
    "runpod==2.1.0" \
    "httpx==0.28.1" \
    "pydantic>=2" \
    "numpy<2" \
    "loguru>=0.5" \
    "appdirs>=1.4,<2.0" \
    "requests>=2.27,<3.0" \
    "soundfile==0.14.0" \
    "deepfilterlib==0.5.6" \
    "whisperx==3.3.1" \
    "pyannote.audio==3.3.2" \
    "demucs==4.1.0" \
    "transformers==4.48.3"

# CTranslate2 loads cuBLAS/cuDNN at runtime from the wheels installed by torch.
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.11/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.11/site-packages/nvidia/cudnn/lib:/usr/local/lib/python3.11/site-packages/nvidia/cuda_runtime/lib:/usr/local/lib/python3.11/site-packages/nvidia/cufft/lib:/usr/local/lib/python3.11/site-packages/nvidia/curand/lib:/usr/local/lib/python3.11/site-packages/nvidia/cusolver/lib:/usr/local/lib/python3.11/site-packages/nvidia/cusparse/lib:/usr/local/lib/python3.11/site-packages/nvidia/nccl/lib:/usr/local/lib/python3.11/site-packages/nvidia/nvrtc/lib

RUN python - <<'PY'
import torch

print("torch", torch.__version__, "cuda", torch.version.cuda)
assert torch.version.cuda, "a CUDA torch build is required"
assert "+cu128" in torch.__version__, f"expected a cu128 wheel, got {torch.__version__}"
PY

# DeepFilterNet pins packaging<24, which conflicts with runpod's
# packaging>=26.3. Its runtime code does not use that pin, so skip dependency
# resolution for the pure-Python package and install its runtime deps above.
RUN pip install --no-cache-dir --no-deps "deepfilternet==0.5.6"

# Resemble Enhance is installed without its dependency pins: the package pins
# torch 2.1.1, soundfile 0.12.1, and a full Gradio stack that conflict with the
# worker image. Only the inference modules are used, so install their missing
# runtime dependencies explicitly. pandas, matplotlib, omegaconf, rich, and
# tabulate are already present from the main image stack.
RUN pip install --no-cache-dir --no-deps "resemble-enhance==0.0.1"

# DeepSpeed imports Triton while building metadata, which requires a GPU driver
# the CI runner does not have. Install it with Triton hidden, disable its Triton
# path permanently, then restore the Triton build torch expects.
RUN pip uninstall -y triton \
    && pip install --no-cache-dir --no-deps "deepspeed==0.18.9" \
    && sed -i 's/HAS_TRITON = True/HAS_TRITON = False/' \
        /usr/local/lib/python3.11/site-packages/deepspeed/__init__.py \
    && pip install --no-cache-dir "triton==3.3.1" \
    && pip install --no-cache-dir \
        "hjson" \
        "ninja" \
        "py-cpuinfo" \
        "nvidia-ml-py" \
        "librosa==0.10.1" \
        "resampy==0.4.2"

# DeepSpeed checks whether its CUDA ops can be compiled on import, which needs a
# toolkit this runtime image does not carry. Resemble only imports the training
# classes, so mark the ops unavailable instead of probing for nvcc.
RUN python - <<'PY'
from pathlib import Path

path = Path(
    "/usr/local/lib/python3.11/site-packages/deepspeed/git_version_info.py"
)
source = path.read_text()
needle = (
    "for op_name, builder in ALL_OPS.items():\n"
    "    op_compatible = builder.is_compatible()\n"
    "    compatible_ops[op_name] = op_compatible\n"
    '    compatible_ops["deepspeed_not_implemented"] = False\n'
)
if needle in source:
    path.write_text(
        source.replace(
            needle, 'compatible_ops["deepspeed_not_implemented"] = False\n'
        )
    )
print("patched deepspeed op compatibility check")
PY

RUN python - <<'PY'
import deepspeed
from resemble_enhance.enhancer.inference import enhance  # noqa: F401

print("resemble import ok; deepspeed HAS_TRITON", deepspeed.HAS_TRITON)
assert deepspeed.HAS_TRITON is False
PY

# Bake model weights into the image so workers do not download them on every
# cold start.
RUN python -c "from df.enhance import init_df; init_df(log_file=None)"

RUN python - <<'PY'
from huggingface_hub import snapshot_download

snapshot_download(
    "ResembleAI/resemble-enhance",
    local_dir="/opt/resemble-enhance",
    allow_patterns=["enhancer_stage2/**"],
)
PY

# Smoke-test the Resemble inference path so a broken dependency or checkpoint
# fails the image build instead of the first user job.
RUN python - <<'PY'
import wave
from pathlib import Path

import torchaudio
from resemble_enhance.enhancer.inference import enhance

with wave.open("/tmp/resemble_smoke.wav", "wb") as writer:
    writer.setnchannels(1)
    writer.setsampwidth(2)
    writer.setframerate(44100)
    writer.writeframes(b"\x00\x00" * 4410)

wav, rate = torchaudio.load("/tmp/resemble_smoke.wav")
out, out_rate = enhance(
    dwav=wav.mean(0),
    sr=rate,
    device="cpu",
    nfe=1,
    solver="euler",
    lambd=0.0,
    tau=0.5,
    run_dir=Path("/opt/resemble-enhance/enhancer_stage2"),
)
print("resemble enhance smoke:", tuple(out.shape), out_rate)
Path("/tmp/resemble_smoke.wav").unlink(missing_ok=True)
PY

# Verify the studio finishing and transcription normalization filters are available in this ffmpeg build.
RUN ffmpeg -hide_banner -loglevel error -y -f lavfi -i "sine=frequency=440:duration=1" \
    -af "highpass=f=75:poles=2,agate=threshold=0.01000:ratio=2.00:range=0.25119:attack=10:release=180:knee=3:detection=rms,equalizer=f=120:t=q:w=1:g=2,equalizer=f=320:t=q:w=1:g=-2,equalizer=f=3500:t=q:w=1:g=1.5,deesser=i=0.35:m=0.5:f=0.5,acompressor=threshold=0.126:ratio=2.5:attack=15:release=150:makeup=1:knee=2.5:detection=rms,alimiter=limit=0.891:attack=5:release=50:level=false,loudnorm=I=-16:TP=-1.5:LRA=11" \
    -ar 48000 -ac 1 /tmp/studio_smoke.wav \
    && ffmpeg -hide_banner -loglevel error -y -f lavfi -i "sine=frequency=440:duration=1" \
    -af "dynaudnorm=f=150:g=5:p=0.9:m=15" \
    -ar 16000 -ac 1 /tmp/dynaudnorm_smoke.wav \
    && rm -f /tmp/studio_smoke.wav /tmp/dynaudnorm_smoke.wav

RUN python - <<'PY'
from huggingface_hub import snapshot_download

snapshot_download(
    "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
    allow_patterns=[
        "config.json",
        "preprocessor_config.json",
        "model.bin",
        "tokenizer.json",
        "vocabulary.*",
    ],
    cache_dir="/root/.cache/whisperx",
)

snapshot_download(
    "parseh/whisper-ar-dialectal-ct2",
    local_dir="/opt/whisper-ar-dialectal",
)
PY

RUN python - <<'PY'
from demucs.pretrained import get_model

get_model("htdemucs_ft")
PY

# WhisperX 3.3.1 pins ctranslate2<4.5, but 4.4/4.5 fail on newer glibc with
# "cannot enable executable stack". 4.6.3 works with faster-whisper 1.1.0 and
# ships Blackwell (sm_120) kernels plus CUDA 12.8 runtime support.
RUN pip install --no-cache-dir --no-deps "ctranslate2==4.6.3"
RUN python -c "import ctranslate2, whisperx; print('ctranslate2', ctranslate2.__version__)"
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('/opt/whisper-ar-dialectal', device='cpu', compute_type='int8'); print('Arabic dialect model ready')"

RUN python - <<'PY'
import whisperx

whisperx.load_align_model(language_code="en", device="cpu")
PY

# Nemotron-3-Diarization needs transformers 5.x. Keep it in a venv so the
# main stack keeps its transformers pin, but share the CUDA torch build from
# the system environment instead of installing a second copy.
RUN python -m venv --system-site-packages /opt/nemotron
RUN /opt/nemotron/bin/pip install --no-cache-dir \
    "transformers==5.22.1" \
    "numpy<2" \
    "soundfile==0.14.0" \
    "librosa" \
    "accelerate"
RUN /opt/nemotron/bin/python - <<'PY'
import torch
import transformers

print("nemotron torch", torch.__version__, "transformers", transformers.__version__)
assert torch.version.cuda, "Nemotron must share the CUDA torch build"
assert "+cu128" in torch.__version__, f"expected a cu128 wheel, got {torch.__version__}"
PY
COPY runpod_app/nemotron_diarize.py /opt/nemotron/diarize.py

RUN python - <<'PY'
import wave

with wave.open("/tmp/nemotron_smoke.wav", "wb") as writer:
    writer.setnchannels(1)
    writer.setsampwidth(2)
    writer.setframerate(16000)
    writer.writeframes(b"\x00\x00" * 16000)
PY
RUN /opt/nemotron/bin/python /opt/nemotron/diarize.py \
    /tmp/nemotron_smoke.wav /tmp/nemotron_smoke.json \
    && rm -f /tmp/nemotron_smoke.wav /tmp/nemotron_smoke.json

# Isolated venv for UVR De-Reverb (audio-separator) sharing the CUDA torch build.
RUN python -m venv --system-site-packages /opt/dereverb
RUN /opt/dereverb/bin/pip install --no-cache-dir "audio-separator" "numpy<2"
RUN /opt/dereverb/bin/python - <<'PY'
import torch
from audio_separator.separator import Separator  # noqa: F401

print("dereverb torch", torch.__version__)
assert torch.version.cuda, "De-reverb must share the CUDA torch build"
PY
RUN /opt/dereverb/bin/python - <<'PY'
from audio_separator.separator import Separator

sep = Separator(model_file_dir="/opt/dereverb/models")
sep.load_model("UVR-DeEcho-DeReverb.pth")
print("UVR-DeEcho-DeReverb ready")
PY
COPY runpod_app/dereverb.py /opt/dereverb/dereverb.py
RUN python - <<'PY'
import wave

with wave.open("/tmp/dereverb_smoke.wav", "wb") as writer:
    writer.setnchannels(1)
    writer.setsampwidth(2)
    writer.setframerate(48000)
    writer.writeframes(b"\x00\x00" * 48000)
PY
RUN HF_HUB_OFFLINE=1 /opt/dereverb/bin/python /opt/dereverb/dereverb.py \
    /tmp/dereverb_smoke.wav /tmp/dereverb_smoke_out.wav \
    && test -s /tmp/dereverb_smoke_out.wav \
    && rm -f /tmp/dereverb_smoke.wav /tmp/dereverb_smoke_out.wav

ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1

COPY parecut_engine ./parecut_engine
COPY app/__init__.py ./app/__init__.py
COPY app/demo_data.py ./app/demo_data.py
COPY app/renderers.py ./app/renderers.py
COPY app/services/__init__.py ./app/services/__init__.py
COPY app/services/stages.py ./app/services/stages.py
COPY runpod_app ./runpod_app

CMD ["python", "-u", "-m", "runpod_app.worker"]
