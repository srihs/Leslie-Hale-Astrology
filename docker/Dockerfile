# syntax=docker/dockerfile:1
#
# Multi-stage build: build tooling (compiler, headers) never reaches the
# runtime image. Runs as a non-root "app" user. One process per container —
# this image runs gunicorn only; nothing here also runs cron or a worker.
#
# Base image pin: exact tag below. A digest pin (python:3.12.7-slim-bookworm
# @sha256:...) is stronger still and is the intended end state, but this
# scaffold was built offline and cannot safely fabricate a digest — resolve
# and pin the real one (`docker pull python:3.12.7-slim-bookworm && docker
# inspect --format '{{index .RepoDigests 0}}' python:3.12.7-slim-bookworm`)
# before the first production build. See final report for this assumption.

FROM python:3.12.7-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# build-essential + libpq-dev cover the rare case a dependency has no
# prebuilt wheel for the target platform; psycopg[binary] normally makes
# libpq-dev unnecessary but keeping it here costs nothing in a stage that
# is discarded before the runtime image is assembled.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY pyproject.toml ./
RUN pip install --no-cache-dir .


# ---------------------------------------------------------------------------
# Runtime stage — no compiler, no build headers, no pip cache.
# ---------------------------------------------------------------------------

FROM python:3.12.7-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    DJANGO_SETTINGS_MODULE=config.settings.prod

# libpq5 is the runtime client library psycopg needs even with the
# [binary] wheel on some base images; curl is intentionally NOT installed —
# the healthcheck below uses Python, already present, instead of pulling in
# another package.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system app \
    && adduser --system --ingroup app --home /app --no-create-home app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# Application code, owned by app:app. Build-context is trimmed by
# .dockerignore (.git, .venv, __pycache__, versions/, media, secrets).
COPY --chown=app:app . .

# staticfiles/ is generated at container start (see entrypoint.sh);
# media/ is expected to be a mounted volume, not image content — both
# directories still need to exist with the right owner before the first
# write.
RUN mkdir -p /app/staticfiles /app/media \
    && chown -R app:app /app/staticfiles /app/media \
    && chmod +x /app/docker/entrypoint.sh

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz/', timeout=3)" || exit 1

ENTRYPOINT ["/app/docker/entrypoint.sh"]

# Workers default to 3; override via WEB_CONCURRENCY at run time using
# `--workers ${WEB_CONCURRENCY}` is not available in exec-form CMD, so the
# worker count is fixed here — docker-compose.yml overrides the full
# command for local dev (runserver, with autoreload) instead.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
