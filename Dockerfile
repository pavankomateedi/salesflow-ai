# SalesFlow AI — chat demo image.
# Serves the FastAPI chat UI (salesflow.web). The conversation engine runs fully
# offline (no API key); pricing is grounded from config, policy is retrieval-only.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install the package + web extra first (better layer caching).
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install ".[web]"

# Hosts (Render/Railway/Fly) inject $PORT; default to 8000 locally.
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request as u; u.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/healthz')" || exit 1

CMD ["sh", "-c", "uvicorn salesflow.web:app --host 0.0.0.0 --port ${PORT}"]
