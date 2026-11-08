FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /worker

RUN pip install --no-cache-dir "runpod==2.1.0" "httpx==0.28.1"

COPY parecut_engine ./parecut_engine
COPY app/__init__.py ./app/__init__.py
COPY app/demo_data.py ./app/demo_data.py
COPY app/renderers.py ./app/renderers.py
COPY app/services/__init__.py ./app/services/__init__.py
COPY app/services/stages.py ./app/services/stages.py
COPY runpod_app ./runpod_app

CMD ["python", "-u", "-m", "runpod_app.worker"]
