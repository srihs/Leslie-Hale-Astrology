# syntax=docker/dockerfile:1
#
# Multi-stage build: build tooling (compiler, headers) never reaches the
# runtime image, and test tooling (pytest & co, see the "dev" stage) never
# reaches it either. Runs as a non-root "app" user. One process per
# container — this image runs gunicorn only; nothing here also runs cron
# or a worker.
#
# Stages: builder -> builder-dev -> runtime-base -> {dev, runtime}.
# "runtime" is last in the file, so it is the default with no --target —
# that is what a bare production `docker build .` gets. "dev" is what
# docker-compose.yml builds locally (target: dev) and carries the pinned
# pytest/pytest-django/factory_boy/freezegun group from pyproject.toml's
# [project.optional-dependencies].dev.
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
# builder-dev — adds pinned test tooling (pytest, pytest-django, factory_boy,
# freezegun) on top of the same venv, for the "dev" stage only. This stage
# is never referenced by the production build, so none of it reaches the
# runtime image.
# ---------------------------------------------------------------------------

FROM builder AS builder-dev

RUN pip install --no-cache-dir .[dev]


# ---------------------------------------------------------------------------
# runtime-base — shared OS packages, non-root user, workdir. No venv and no
# application code yet: "runtime" and "dev" below each copy their own venv
# onto this so neither stage's COPY --from runs against files already
# chowned to the non-root user (that would fail without --chown gymnastics).
# ---------------------------------------------------------------------------

FROM python:3.12.7-slim-bookworm AS runtime-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

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

WORKDIR /app


# ---------------------------------------------------------------------------
# dev stage — everything "runtime" has, plus the pinned test tooling from
# builder-dev. This is what docker-compose.yml builds locally (target: dev)
# so the suite runs in-container without ad-hoc `pip install`. It is NOT
# the default target — see "runtime" below, which is.
# ---------------------------------------------------------------------------

FROM runtime-base AS dev

ENV DJANGO_SETTINGS_MODULE=config.settings.dev

COPY --from=builder-dev /opt/venv /opt/venv

# tests/browser/ (Playwright + real Chromium) — installed here, at build
# time, in the "dev" stage only. Decided deliberately, not defaulted:
#
#   `playwright install --with-deps chromium` needs apt (for the ~40
#   shared libraries Chromium needs: libnss3, libatk-bridge2.0-0, libgbm1,
#   fonts, ...), and apt needs root. This container's own USER is "app" by
#   the time anyone would `docker compose exec` into it, and there is no
#   sudo in this image — a "run it manually once you need it" step would
#   actually mean "docker compose exec -u root ... && chown ... every time
#   the container is recreated", which is exactly the setup ritual a
#   developer forgets, and it would have to be repeated after every
#   `docker compose up --build` since nothing outside the image persists
#   across a rebuild. Baking it into the image at build time, where root
#   is already the active user for the apt-requiring builder stages
#   anyway, is the only version of this that isn't a trap.
#
#   The size cost is real and paid only here: roughly 400-600MB added to
#   the "dev" stage alone (Chromium itself is ~150-300MB; the apt
#   libraries and fonts make up the rest) — see the build-time size
#   comparison in the deployment notes. It does not touch "runtime" below,
#   which copies from "builder", never "builder-dev", and never runs this
#   block.
#
# PLAYWRIGHT_BROWSERS_PATH points outside any per-user home directory
# specifically so the browsers land somewhere the non-root "app" user can
# still read after USER switches below — the `playwright install` default
# ($HOME/.cache/ms-playwright, i.e. /root/.cache/ms-playwright while this
# RUN is still root) is unreadable by "app" once the image drops
# privileges, which is the exact failure this project's test-engineer hit
# installing by hand into the running container. Verified as the "app"
# user, not assumed — see the deployment notes.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN mkdir -p /ms-playwright \
    && playwright install --with-deps chromium \
    && chown -R app:app /ms-playwright

# Application code, owned by app:app. Build-context is trimmed by
# .dockerignore (.git, .venv, __pycache__, versions/, media, secrets).
COPY --chown=app:app . .

RUN mkdir -p /app/staticfiles /app/media \
    && chown -R app:app /app/staticfiles /app/media \
    && chmod +x /app/docker/entrypoint.sh

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz/', timeout=3)" || exit 1

ENTRYPOINT ["/app/docker/entrypoint.sh"]

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]


# ---------------------------------------------------------------------------
# runtime stage (production default: this is the LAST stage in the file, so
# a plain `docker build .` / `docker build --target runtime .` with no
# --target lands here) — no compiler, no build headers, no pip cache, and
# no test framework: it copies the venv from "builder", never "builder-dev".
# ---------------------------------------------------------------------------

FROM runtime-base AS runtime

ENV DJANGO_SETTINGS_MODULE=config.settings.prod

COPY --from=builder /opt/venv /opt/venv

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
