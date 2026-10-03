# syntax=docker/dockerfile:1
# One image for the whole app (design §1 "Serving", §11): Node builds the SPA, then the
# Python image serves both /api and the built files. Used by compose and by Railway.

FROM node:22.23.3-alpine3.24 AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12.15-slim-trixie AS app
COPY --from=ghcr.io/astral-sh/uv:0.12.22 /uv /bin/uv
# No BuildKit cache mounts: Railway requires a service-specific mount id
# (docs.railway.com/builds/dockerfiles#cache-mounts) and compose uses this same file.
# UV_NO_CACHE keeps uv's download cache out of the image layers instead.
ENV UV_COMPILE_BYTECODE=1 \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /app

# Dependencies first (a layer reused until the lockfile changes), then the project.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY backend/ ./
RUN uv sync --locked --no-dev

COPY --from=frontend /frontend/dist ./app/static

RUN useradd --no-log-init --uid 10001 --no-create-home --shell /usr/sbin/nologin app
USER app

# Railway injects PORT; 8000 is the local default.
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:build_app --factory --host 0.0.0.0 --port \"$PORT\" --no-access-log"]
