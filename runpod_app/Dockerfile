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

# Bake model weights into the image so workers do not download them on every
# cold start.
RUN python -c "from df.enhance import init_df; init_df(log_file=None)"

RUN python - <<'PY'
import whisperx

whisperx.load_model(
    "large-v3-turbo",
    device="cpu",
    compute_type="int8",
    download_root="/root/.cache/whisperx",
)
PY

RUN python - <<'PY'
from demucs.pretrained import get_model

get_model("htdemucs_ft")
PY

RUN --mount=type=secret,id=HF_TOKEN HF_TOKEN=$(cat /run/secrets/HF_TOKEN) python - <<'PY'
import os

from pyannote.audio import Pipeline

Pipeline.from_pretrained(
    "pyannote/speaker-diarization-3.1",
    use_auth_token=os.environ["HF_TOKEN"],
)
PY

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
