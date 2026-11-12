# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
WORKDIR /worker

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 libgomp1 git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
    "torch==2.2.2+cpu" "torchaudio==2.2.2+cpu"

RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
    "torch==2.2.2+cpu" \
    "torchaudio==2.2.2+cpu" \
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
RUN pip install --no-cache-dir \
    "deepspeed==0.12.4" \
    "librosa==0.10.1" \
    "resampy==0.4.2"

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
PY

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
PY

RUN python - <<'PY'
from demucs.pretrained import get_model

get_model("htdemucs_ft")
PY

# WhisperX 3.3.1 pins ctranslate2<4.5, but 4.4/4.5 fail on newer glibc with
# "cannot enable executable stack". 4.6.0 works with faster-whisper 1.1.0.
RUN pip install --no-cache-dir --no-deps "ctranslate2==4.6.0"
RUN python -c "import ctranslate2, whisperx; print('ctranslate2', ctranslate2.__version__)"

RUN python - <<'PY'
import whisperx

whisperx.load_align_model(language_code="en", device="cpu")
PY

# Nemotron-3-Diarization needs torch 2.6+/transformers 5.x. Keep it in a
# separate venv so DeepFilterNet, WhisperX, and Demucs stay on torch 2.2.2.
RUN python -m venv /opt/nemotron
RUN /opt/nemotron/bin/pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
    "torch==2.6.0+cpu" "torchaudio==2.6.0+cpu"
RUN /opt/nemotron/bin/pip install --no-cache-dir \
    "transformers==5.22.1" \
    "numpy<2" \
    "soundfile==0.14.0" \
    "librosa" \
    "accelerate"
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
    /tmp/nemotron_smoke.wav /tmp/nemotron_smoke.json

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
