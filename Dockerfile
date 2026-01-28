# Dockerfile for ExtraSuite Server
# Build context: repository root (not server/)
# Skills are bundled as /app/skills.zip for enterprise deployment

FROM python:3.12-slim AS builder

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first for layer caching
COPY server/pyproject.toml server/uv.lock ./

# Create venv and install dependencies (no dev deps)
RUN uv venv /app/.venv && \
    uv sync --frozen --no-dev --no-install-project

# Copy source and install the package
COPY server/src ./src
COPY server/README.md ./
RUN uv sync --frozen --no-dev

# Copy skills folder and create skills.zip (exclude venv, __pycache__, etc.)
COPY server/skills /app/skills-src
RUN apt-get update && apt-get install -y --no-install-recommends zip \
    && cd /app/skills-src \
    && zip -r /app/skills.zip . -x "*/venv/*" -x "*/__pycache__/*" -x "*/.pytest_cache/*" -x "*/.git/*" \
    && rm -rf /app/skills-src \
    && apt-get purge -y zip && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*


# Production stage
FROM python:3.12-slim

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Copy virtual environment, source, and skills.zip from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/skills.zip /app/skills.zip

# Set environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV PORT=8080
ENV ENVIRONMENT=production
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/health || exit 1

# OCI labels for GitHub Container Registry
LABEL org.opencontainers.image.source="https://github.com/think41/extrasuite"
LABEL org.opencontainers.image.description="ExtraSuite Server - OAuth token exchange for CLI tools"
LABEL org.opencontainers.image.licenses="MIT"

CMD ["uvicorn", "extrasuite.server.main:app", "--host", "0.0.0.0", "--port", "8080"]
