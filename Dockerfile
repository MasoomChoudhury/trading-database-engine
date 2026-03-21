# =============================================================================
# Database Engine — Production Docker Image
# Multi-stage: builds dependencies, runs as non-root user
# =============================================================================

# ── Stage 1: Dependency installation ──────────────────────────────────────────
FROM python:3.11-slim AS deps

WORKDIR /deps

# Install compiled dependencies first (faster rebuilds on code-only changes)
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# ── Stage 2: Runtime image ────────────────────────────────────────────────────
FROM python:3.11-slim

# Metadata
LABEL maintainer="Database Engine"
LABEL description="Nifty Market Data Sync Engine + Admin Dashboard"

# Security: run as non-root
RUN groupadd --gid 1000 engine && \
    useradd  --uid 1000 --gid engine --shell /bin/bash engine

WORKDIR /app

# Install runtime-only packages (no compilers needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from deps stage
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin             /usr/local/bin

# Copy application source
COPY --chown=engine:engine . .

# Set Python path so imports like "from fetcher import ..." work
ENV PYTHONPATH=/app

# Switch to non-root user
USER engine

# ── Entrypoint ────────────────────────────────────────────────────────────────
# The CMD is overridden per service in docker-compose.yml
# This default catches SIGTERM for graceful shutdown
ENTRYPOINT ["python3", "-u"]
CMD ["--help"]
