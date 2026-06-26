FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Build deps mínimos pra asyncpg, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copia metadata primeiro pra otimizar cache de camadas
COPY pyproject.toml ./
COPY src ./src
RUN pip install -e .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsSL http://localhost:8000/health || exit 1

CMD ["python", "-m", "zoi_agent.main"]
