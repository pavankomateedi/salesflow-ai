# SalesFlow AI — full-stack image (React UI + FastAPI backend).
#
# Stage 1 builds the React SPA; stage 2 is the Python runtime that serves both
# the built SPA and the JSON/WebSocket APIs. The conversation engine runs fully
# offline (no key); OPENAI_API_KEY / CARTESIA_API_KEY only upgrade phrasing+voice.

# --- Stage 1: build the React frontend -------------------------------------
FROM node:20-slim AS frontend
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Python runtime -----------------------------------------------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install the package + web extra first (better layer caching).
# Production needs ALL three optional extras:
#   web   -> FastAPI + uvicorn (serves the SPA + APIs)
#   voice -> cartesia + groq (live STT/TTS on /voice)
#   llm   -> openai (natural phrasing, smart extraction, recap review)
# Without these, voice_available() returns True (env var set) but the SDK
# import fails at runtime and the websocket surfaces "SDK not installed".
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install ".[web,voice,llm]"

# Built SPA, served by FastAPI as static files.
COPY --from=frontend /ui/dist ./frontend/dist

# Hosts (Render/Cloud Run/App Runner) inject $PORT; default to 8000 locally.
ENV PORT=8000 \
    SALESFLOW_FRONTEND_DIST=/app/frontend/dist
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request as u; u.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/healthz')" || exit 1

CMD ["sh", "-c", "uvicorn salesflow.web:app --host 0.0.0.0 --port ${PORT}"]
