# ==========================================================
# PepperSign - Process (Flask + DWPose + Whisper + FFmpeg)
#
# Una sola immagine, due varianti scelte con i build-arg:
#   CPU (default): python:3.10-slim + torch CPU + onnxruntime
#   GPU          : nvidia/cuda + torch CUDA + onnxruntime-gpu
#                  (vedi docker-compose.gpu.yml)
# ==========================================================
ARG BASE_IMAGE=python:3.10-slim-bookworm
FROM ${BASE_IMAGE}

ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
ARG ONNXRUNTIME_PACKAGE=onnxruntime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Europe/Rome

# Pacchetti di sistema: ffmpeg (conversioni audio/video), librerie per OpenCV.
# Sull'immagine CUDA (Ubuntu) Python non c'e': lo installo solo se manca.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 ca-certificates \
 && if ! command -v python3 >/dev/null 2>&1; then \
        apt-get install -y --no-install-recommends python3 python3-pip python-is-python3; \
    fi \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 0) pip aggiornato: le versioni vecchie non riconoscono i nomi dei pacchetti
#    sul repository di PyTorch (Jinja2/jinja2, typing_extensions/typing-extensions)
RUN python3 -m pip install --upgrade pip setuptools wheel

# 1) torch dalla variante giusta (CPU o CUDA)
RUN python3 -m pip install torch --index-url ${TORCH_INDEX_URL}

# 2) resto delle dipendenze
COPY requirements.txt .
RUN python3 -m pip install -r requirements.txt

# 2b) easy-dwpose su Linux richiede onnxruntime-gpu==1.16.2, non disponibile.
#     Lo installo senza dipendenze e poi installo le sue dipendenze
#     escluso onnxruntime, che viene messo al passo 3 nella variante giusta (CPU/GPU).
RUN python3 -m pip install --no-deps easy-dwpose \
 && python3 -c "import importlib.metadata as m; print('\n'.join(r for r in (m.requires('easy-dwpose') or []) if 'onnxruntime' not in r))" > /tmp/edw-deps.txt \
 && cat /tmp/edw-deps.txt \
 && python3 -m pip install -r /tmp/edw-deps.txt

# 3) onnxruntime della variante giusta. Rimuovo eventuali versioni installate
#    come dipendenze transitive, altrimenti CPU e GPU andrebbero in conflitto.
RUN python3 -m pip uninstall -y onnxruntime onnxruntime-gpu || true \
 && python3 -m pip install ${ONNXRUNTIME_PACKAGE}

COPY . .

# Percorsi dentro al container (montati come volumi da docker-compose):
#   /data/media        cartella condivisa con la WebApp (scheletri generati)
#   /app/checkpoints   modelli DWPose (.onnx) - easy_dwpose li scarica qui se mancano
#   /app/assets        video sorgente locali (opzionali)
#   /root/.cache       cache HuggingFace/Whisper
ENV PEPPERSIGN_DATA_DIR=/data/media \
    PEPPERSIGN_PORT=5000 \
    FFMPEG_BIN=ffmpeg \
    IMAGEIO_FFMPEG_EXE=/usr/bin/ffmpeg \
    GUNICORN_THREADS=8 \
    GUNICORN_TIMEOUT=900

VOLUME ["/data/media", "/app/checkpoints", "/root/.cache"]
EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=600s --retries=3 \
  CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=4).status == 200 else 1)"

# Un solo worker: i job /try sono tenuti in memoria (app/state.py) e i modelli
# vanno caricati una sola volta. La concorrenza e' data dai thread.
CMD ["sh", "-c", "exec gunicorn --workers 1 --threads ${GUNICORN_THREADS} --timeout ${GUNICORN_TIMEOUT} --bind 0.0.0.0:${PEPPERSIGN_PORT} 'app:create_app()'"]
