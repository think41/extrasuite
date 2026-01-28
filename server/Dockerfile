# Dockerfile for ExtraSuite Server
# Multi-stage build for minimal production image

FROM python:3.12-slim AS builder

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Create venv and install dependencies (no dev deps)
RUN uv venv /app/.venv && \
    uv sync --frozen --no-dev --no-install-project

# Copy source and install the package
COPY src ./src
COPY README.md ./
RUN uv sync --frozen --no-dev


# Production stage
FROM python:3.12-slim

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Copy virtual environment and source from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

# Copy skills folder (copied into build context by cloudbuild.yaml)
COPY skills /app/skills

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

CMD ["uvicorn", "extrasuite.server.main:app", "--host", "0.0.0.0", "--port", "8080"]
