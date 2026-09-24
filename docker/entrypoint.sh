#!/usr/bin/env sh
# Entrypoint for the web container. One process per container: this script
# prepares the process (wait for the database, optionally migrate, always
# collect static) and then execs the CMD (gunicorn) as PID 1 — it does not
# stay running itself, and it never also runs cron or a worker alongside
# gunicorn.
set -eu

echo "entrypoint: waiting for the database to accept connections..."
python - <<'PYEOF'
import os
import sys
import time

import psycopg

database_url = os.environ["DATABASE_URL"]
deadline = time.monotonic() + 30
last_error = None

while time.monotonic() < deadline:
    try:
        with psycopg.connect(database_url, connect_timeout=3):
            print("entrypoint: database is accepting connections.")
            sys.exit(0)
    except psycopg.OperationalError as exc:
        last_error = exc
        time.sleep(1)

print(f"entrypoint: database never became ready: {last_error}", file=sys.stderr)
sys.exit(1)
PYEOF

# Migrations are a deliberate, explicit step — not an implicit side effect
# of every container starting. In docker-compose (single web instance) it
# defaults on for convenience. In a multi-replica production deploy, run
# migrations once (RUN_MIGRATIONS=true against a single one-off container
# or deploy job) before rolling out replicas with RUN_MIGRATIONS unset.
if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    echo "entrypoint: RUN_MIGRATIONS=true, applying migrations..."
    python manage.py migrate --noinput

    # The rate-limit cache table (CACHES in config/settings/base.py, finding
    # 1 in reviews/2026-09-22-final-security-review.md) is schema, same as a
    # migration — created here, once, deliberately, not on every container
    # start. createcachetable is safe to run against a table that already
    # exists: it checks connection.introspection.table_names() first and
    # returns without error (verified against django==5.1's own
    # createcachetable command source), so re-running this step on a later
    # one-off deploy is a no-op, not a failure.
    echo "entrypoint: ensuring the rate-limit cache table exists..."
    python manage.py createcachetable

    # Wagtail's own Site record (wagtail_sites) is schema data, same as the
    # cache table above — set once, deliberately, not implicitly on every
    # container start. Wagtail's initial migration leaves it at
    # hostname="localhost", port=80. Page.full_url / .get_url() resolve
    # against this record when no request is available (e.g. the RSS feed,
    # apps/blog/feeds.py), so left unset in production every such link
    # would silently read "http://localhost/...". Only runs when
    # WAGTAIL_SITE_HOSTNAME is actually set (see .env.example) — blank
    # means "leave Wagtail's Site record alone", which is correct for
    # local dev.
    if [ -n "${WAGTAIL_SITE_HOSTNAME:-}" ]; then
        echo "entrypoint: syncing Wagtail's default Site record to ${WAGTAIL_SITE_HOSTNAME}:${WAGTAIL_SITE_PORT:-443}..."
        python manage.py shell <<'PYEOF'
import os

from wagtail.models import Site

hostname = os.environ["WAGTAIL_SITE_HOSTNAME"]
port = int(os.environ.get("WAGTAIL_SITE_PORT", "443"))

site = Site.objects.filter(is_default_site=True).first()
if site is None:
    print("entrypoint: WARNING - no default Wagtail Site found; skipping.")
elif site.hostname != hostname or site.port != port:
    site.hostname = hostname
    site.port = port
    site.save()
    print(f"entrypoint: Wagtail Site updated -> {hostname}:{port}")
else:
    print(f"entrypoint: Wagtail Site already set to {hostname}:{port}")
PYEOF
    else
        echo "entrypoint: WAGTAIL_SITE_HOSTNAME not set, leaving Wagtail's Site record unchanged."
    fi
else
    echo "entrypoint: RUN_MIGRATIONS is not true, skipping migrations."
fi

# collectstatic is idempotent and container-local (whitenoise serves from
# this container's own STATIC_ROOT), so it is safe to run on every start
# regardless of replica count.
echo "entrypoint: collecting static files..."
python manage.py collectstatic --noinput

echo "entrypoint: handing off to: $*"
exec "$@"
