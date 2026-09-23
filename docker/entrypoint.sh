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
