# Dockerfile for Fabric API Server
# Headless CLI authentication service

FROM python:3.12-slim AS runtime

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast Python package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install Python dependencies
COPY server/pyproject.toml server/uv.lock server/README.md ./
RUN uv sync --frozen --no-dev

# Copy server source code
COPY server/fabric ./fabric

# Environment variables
ENV PORT=8001
ENV ENVIRONMENT=production
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/api/health || exit 1

# Run with uvicorn
CMD ["uv", "run", "uvicorn", "fabric.main:app", "--host", "0.0.0.0", "--port", "8001"]
