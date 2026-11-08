# AI Stock Sentiment Agent — backend image
# Pinned: Python 3.12. CPU-only torch and HF_HOME=/models are wired for Phase 6;
# torch itself is installed there to keep early images small.

# ---------- stage 1: build & install dependencies ----------
FROM python:3.12-slim AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY backend/pyproject.toml ./
COPY backend/app/ ./app/
RUN pip install --prefix=/install .

# ---------- stage 2: runtime ----------
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/models
RUN useradd --create-home --uid 1000 appuser
WORKDIR /app
COPY --from=builder /install /usr/local
COPY backend/app/ ./app/
COPY backend/alembic.ini ./
RUN mkdir -p /models && chown -R appuser /models
USER appuser
VOLUME ["/models"]
EXPOSE 8000
CMD ["python", "-m", "app.scripts.entrypoint"]
