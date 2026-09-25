#!/usr/bin/env bash
# Post-deploy media verification — run on the deploy host after any deploy
# or nginx change that touches media. Checks the four things that have
# separately produced a media 404 on this project's real deploys, in
# under a minute:
#   1. The filesystem permission chain nginx needs (see
#      deploy/nginx/leslie.conf.example's "Directory permissions" section
#      for why `test -r` on the directory alone is not this check).
#   2. The container's actual media uid:gid against the host directory's
#      owner (see docker-compose.prod.yml's "Media" section).
#   3. Which host directory is actually bind-mounted to /app/media in the
#      running container, against what .env's MEDIA_DIR says it should be
#      (dev and prod put media in different places — see
#      docker-compose.yml's "media:" volume comment).
#   4. A real media URL over HTTPS, expecting 200.
#
# Run from the repo root, with .env present and docker-compose.prod.yml
# already up:
#   ./deploy/verify-media.sh
#
# Optional: pass a media path (relative to MEDIA_DIR) to test a specific
# file instead of the first one this script finds:
#   ./deploy/verify-media.sh original_images/leslie.jpg
#
# Exits non-zero on the first failing check, so this doubles as a
# deploy-gate, not just a manual troubleshooting aid.

set -euo pipefail

COMPOSE="docker compose -f docker-compose.prod.yml"

if [ ! -f .env ]; then
    echo "verify-media: no .env in $(pwd) — run this from the repo root on the deploy host." >&2
    exit 1
fi

MEDIA_DIR_RAW=$(grep -E '^MEDIA_DIR=' .env | head -n1 | cut -d= -f2-)
MEDIA_DIR_RAW=${MEDIA_DIR_RAW:-./data/media}
MEDIA_DIR=$(cd "$MEDIA_DIR_RAW" 2>/dev/null && pwd || true)
if [ -z "$MEDIA_DIR" ]; then
    echo "verify-media: MEDIA_DIR ($MEDIA_DIR_RAW) does not exist on this host." >&2
    exit 1
fi

DOMAIN=$(grep -E '^DJANGO_ALLOWED_HOSTS=' .env | head -n1 | cut -d= -f2- | cut -d, -f1)

if [ -n "${1:-}" ]; then
    SAMPLE="$MEDIA_DIR/$1"
else
    SAMPLE=$(find "$MEDIA_DIR" -type f 2>/dev/null | head -n1 || true)
fi
if [ -z "$SAMPLE" ] || [ ! -f "$SAMPLE" ]; then
    echo "verify-media: no file found under $MEDIA_DIR to test — pass a relative path explicitly." >&2
    exit 1
fi

echo "== 1. Permission chain (namei) =============================="
echo "Sample file: $SAMPLE"
namei -l "$SAMPLE"
echo
echo -n "www-data can read this file directly (not just list the directory): "
if sudo -u www-data test -r "$SAMPLE"; then
    echo "OK"
else
    echo "FAIL"
    echo "www-data cannot read $SAMPLE — check the namei output above for a" >&2
    echo "directory missing the execute (x) bit for 'other'." >&2
    exit 1
fi

echo
echo "== 2. Container media uid:gid vs host directory owner ======="
CONTAINER_UID=$($COMPOSE exec -T web id -u)
CONTAINER_GID=$($COMPOSE exec -T web id -g)
HOST_UID=$(stat -c '%u' "$MEDIA_DIR")
HOST_GID=$(stat -c '%g' "$MEDIA_DIR")
echo "Container app user:      ${CONTAINER_UID}:${CONTAINER_GID}"
echo "Host $MEDIA_DIR owner: ${HOST_UID}:${HOST_GID}"
if [ "$CONTAINER_UID" != "$HOST_UID" ] || [ "$CONTAINER_GID" != "$HOST_GID" ]; then
    echo "FAIL — mismatch. New uploads through Wagtail will fail to write with"
    echo "no visible error. Fix:"
    echo "  sudo chown -R ${CONTAINER_UID}:${CONTAINER_GID} \"$MEDIA_DIR\""
    exit 1
fi
echo "OK"

echo
echo "== 3. Which host directory is actually mounted at /app/media ="
CONTAINER_ID=$($COMPOSE ps -q web)
if [ -z "$CONTAINER_ID" ]; then
    echo "verify-media: web container is not running (docker compose -f docker-compose.prod.yml up -d)." >&2
    exit 1
fi
MOUNT_SRC=$(docker inspect "$CONTAINER_ID" --format '{{range .Mounts}}{{if eq .Destination "/app/media"}}{{.Source}}{{end}}{{end}}')
echo "Container's /app/media is bind-mounted from: $MOUNT_SRC"
echo ".env's MEDIA_DIR resolves to:                 $MEDIA_DIR"
if [ "$MOUNT_SRC" != "$MEDIA_DIR" ]; then
    echo "FAIL — the running container is not serving the media directory this"
    echo "host's .env describes. Common cause: the dev stack (docker-compose.yml,"
    echo "named volume, not a host bind mount — see its own comment) is running"
    echo "instead of, or as well as, docker-compose.prod.yml. Check with:"
    echo "  docker compose ls"
    exit 1
fi
echo "OK"

echo
echo "== 4. Fetch a real media URL over HTTPS ======================"
if [ -z "$DOMAIN" ]; then
    echo "verify-media: DJANGO_ALLOWED_HOSTS not set in .env — cannot build a URL to fetch." >&2
    exit 1
fi
RELATIVE_PATH=${SAMPLE#"$MEDIA_DIR"/}
URL="https://${DOMAIN}/media/${RELATIVE_PATH}"
echo "GET $URL"
STATUS=$(curl -s -o /dev/null -w '%{http_code}' "$URL")
echo "HTTP $STATUS"
if [ "$STATUS" != "200" ]; then
    echo "FAIL — expected 200. See deploy/nginx/leslie.conf.example's media"
    echo "section: this is a 404 whether the cause is the permission chain,"
    echo "an alias/MEDIA_DIR path mismatch, or a missing trailing slash on"
    echo "either — checks 1-3 above should already have ruled out the first."
    exit 1
fi
echo "OK — media is actually being served."

echo
echo "All checks passed."
