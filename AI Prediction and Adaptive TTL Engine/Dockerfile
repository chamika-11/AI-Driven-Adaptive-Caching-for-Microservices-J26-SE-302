# ─────────────────────────────────────────────────────────────────────────────
# Dockerfile — Component 1: Adaptive TTL Engine
#
# Build:  docker build -t ttl-engine .
# Run:    docker run -p 5001:5001 --env-file .env ttl-engine
# ─────────────────────────────────────────────────────────────────────────────

# ── Base image ────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

# Prevents Python from writing .pyc files and buffers stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ── Install system dependencies ───────────────────────────────────────────────
# libgomp1 is required by LightGBM / some NumPy/SciPy builds
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# ── Install Python dependencies ───────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ── Copy application source ───────────────────────────────────────────────────
COPY src/       ./src/
COPY .env       ./.env

# ── Mount points for models and data ─────────────────────────────────────────
# In production, mount these as volumes so models can be updated without
# rebuilding the image (see docker-compose.yml).
COPY models/    ./models/
COPY data/      ./data/

# ── Expose API port ───────────────────────────────────────────────────────────
EXPOSE 5001

# ── Health check ─────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5001/health')"

# ── Start the production WSGI server ─────────────────────────────────────────
# gunicorn settings:
#   -w 2         → 2 worker processes (tune based on CPU cores)
#   --threads 4  → 4 threads per worker
#   --timeout 120 → allow 120s for model loading on first request
CMD ["gunicorn", \
     "--workers", "2", \
     "--threads", "4", \
     "--timeout", "120", \
     "--bind", "0.0.0.0:5001", \
     "--chdir", "src", \
     "api:app"]
