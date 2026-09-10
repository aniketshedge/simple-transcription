# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS frontend
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.11.32 AS uv
FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    DATA_DIR=/data MODEL_DIR=/models FRONTEND_DIR=/app/frontend/dist \
    HF_HOME=/models/huggingface TORCH_HOME=/models/torch XDG_CACHE_HOME=/models/cache \
    NLTK_DATA=/app/nltk_data HF_HUB_DISABLE_TELEMETRY=1 PYANNOTE_METRICS_ENABLED=0 \
    DO_NOT_TRACK=1 TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=3 MKL_NUM_THREADS=3
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_CACHE_DIR=/root/.cache/uv uv sync --locked --no-dev --no-install-project
RUN python -m nltk.downloader -d /app/nltk_data punkt_tab
COPY backend/ ./backend/
COPY --from=frontend /ui/dist ./frontend/dist
RUN mkdir -p /data /models && chown -R app:app /data /models
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
