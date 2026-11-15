#!/usr/bin/env bash
# Run on the Ubuntu VM as its dedicated Docker-enabled deployment user.
set -Eeuo pipefail
umask 077

ROOT=${DAILYCOMMIT_DEPLOY_DIR:-/opt/dailycommit}
SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
IMAGE=${1:?Expected immutable image reference}
COMMIT=${2:?Expected full commit SHA}
[[ "$COMMIT" =~ ^[a-f0-9]{40}$ ]] || { echo 'Invalid commit SHA' >&2; exit 1; }
[[ "$IMAGE" =~ ^ghcr\.io/[a-z0-9._-]+/[a-z0-9._-]+@sha256:[a-f0-9]{64}$ ]] || { echo 'An immutable repository GHCR digest is required' >&2; exit 1; }
[[ -d "$ROOT" && -w "$ROOT" ]] || { echo '/opt/dailycommit must exist and be owned by the deployment user' >&2; exit 1; }
for tool in docker python3 flock install curl; do command -v "$tool" >/dev/null || { echo "Missing VM prerequisite: $tool" >&2; exit 1; }; done
exec 9>"$ROOT/.deploy.lock"
flock -w 1800 9 || { echo 'Another dev deployment still holds the lock' >&2; exit 1; }
docker compose version --short | python3 -c 'import re,sys; m=re.search(r"(\d+)\.(\d+)", sys.stdin.read()); sys.exit(0 if m and tuple(map(int,m.groups())) >= (2,30) else 1)' || {
  echo 'Docker Compose plugin >= 2.30 is required (raw env files and health waits)' >&2; exit 1;
}
docker info >/dev/null
[[ "$(docker info --format '{{.Architecture}}')" == 'x86_64' ]] || { echo 'This dev workflow builds linux/amd64; use an x86_64 Azure VM' >&2; exit 1; }
for file in docker-compose.dev.yml Caddyfile app.env db.env redis.env secret-fingerprints.json .registry-auth.json; do
  [[ -f "$SOURCE/$file" && ! -L "$SOURCE/$file" ]] || { echo 'Deployment bundle is incomplete' >&2; exit 1; }
done
# Do not accidentally rotate the DB/Redis passwords or invalidate every session.
if [[ -f "$ROOT/secret-fingerprints.json" ]] && ! cmp -s "$ROOT/secret-fingerprints.json" "$SOURCE/secret-fingerprints.json"; then
  echo 'Stable credentials changed. Rotation needs an explicit coordinated operation; deployment stopped.' >&2
  exit 1
fi

mkdir -p "$ROOT/backups" "$ROOT/deploy-logs" "$ROOT/deploy/dev"
chmod 700 "$ROOT/backups" "$ROOT/deploy-logs"
export DOCKER_CONFIG
DOCKER_CONFIG=$(mktemp -d "$ROOT/.docker-auth.XXXXXX")
cleanup() {
  rm -f -- "$SOURCE/.registry-auth.json"
  rm -rf -- "$DOCKER_CONFIG"
}
trap cleanup EXIT
# Credentials travel only over SSH, into a private temporary Docker config.
python3 - "$SOURCE/.registry-auth.json" <<'PY'
import json, subprocess, sys
with open(sys.argv[1]) as f:
    auth = json.load(f)
result = subprocess.run(['docker', 'login', 'ghcr.io', '--username', auth['username'], '--password-stdin'], input=auth['token'].encode(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
if result.returncode:
    raise SystemExit('GHCR login failed. Check VM read:packages credentials and package access.')
PY
rm -f -- "$SOURCE/.registry-auth.json"
docker pull "$IMAGE"

# Files are generated from GitHub Secrets; this is not a VM-side git checkout.
for file in docker-compose.dev.yml app.env db.env redis.env secret-fingerprints.json; do
  install -m 600 "$SOURCE/$file" "$ROOT/$file"
done
install -m 644 "$SOURCE/Caddyfile" "$ROOT/Caddyfile"
install -m 600 "$SOURCE/deploy/dev/database.py" "$ROOT/deploy/dev/database.py"
printf 'DAILYCOMMIT_IMAGE=%s\n' "$IMAGE" > "$ROOT/.release.env"
cd "$ROOT"
compose() { docker compose --project-name dailycommit-dev --env-file "$ROOT/.release.env" -f "$ROOT/docker-compose.dev.yml" "$@"; }
compose config --quiet
# Pull/provision-check the proxy before interrupting the running app or changing schema.
compose pull caddy
if ! compose run --rm --no-deps -T caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile; then
  echo 'Caddy configuration is invalid; existing app was not stopped.' >&2
  exit 1
fi
# Stable project and explicit volume names preserve data across every application update.
compose up -d --wait --wait-timeout 180 db redis

database() {
  compose run --rm --no-deps -T --workdir /app/api \
    -v "$ROOT/deploy/dev/database.py:/run/dailycommit-database.py:ro" \
    --entrypoint /app/api/.venv/bin/python app /run/dailycommit-database.py "$1"
}
STATUS_FILE=$(mktemp "$ROOT/.database-state.XXXXXX")
LOG="$ROOT/deploy-logs/${COMMIT}-$(date -u +%Y%m%dT%H%M%SZ).log"
if ! database inspect >"$STATUS_FILE" 2>"$LOG"; then
  rm -f "$STATUS_FILE"
  echo 'Database preflight failed. Check deployment settings and the private VM log.' >&2
  exit 1
fi
STATE=$(python3 - "$STATUS_FILE" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    print(json.load(f)['state'])
PY
)
rm -f "$STATUS_FILE"
# Back up before any schema/app change. Keep the file private and never upload it to Actions.
BACKUP="$ROOT/backups/$(date -u +%Y%m%dT%H%M%SZ)-${COMMIT}.dump"
if ! compose exec -T db pg_dump -U learnhouse -d learnhouse -Fc > "$BACKUP"; then
  echo 'Database backup failed; app was not stopped. Check the private backup/log paths.' >&2
  exit 1
fi
[[ -s "$BACKUP" ]] || { echo 'Empty database backup; stopped' >&2; exit 1; }
chmod 600 "$BACKUP"

case "$STATE" in
  fresh)
    # Native LearnHouse startup creates the schema and first org/admin.
    printf '%s\n' "$IMAGE" > "$ROOT/.bootstrap-pending"
    ;;
  versioned)
    compose stop app
    if ! database upgrade >>"$LOG" 2>&1; then
      echo 'Migration failed; app remains stopped. Do not downgrade blindly. Restore the VM backup through the documented recovery procedure.' >&2
      exit 1
    fi
    ;;
  unversioned)
    # Resume only our own interrupted fresh bootstrap, against exactly the same image.
    if [[ ! -f "$ROOT/.bootstrap-pending" ]] || [[ "$(cat "$ROOT/.bootstrap-pending")" != "$IMAGE" ]]; then
      echo 'Unversioned existing database: establish a verified old-image Alembic baseline before adoption. No automatic stamping performed.' >&2
      exit 1
    fi
    ;;
  *) echo 'Unknown database state; stopped' >&2; exit 1 ;;
esac

# Free a legacy HTTP app's host port 80 before Caddy claims it. Versioned upgrades
# already stopped the app before migration; fresh/resumed boots must also do so.
if [[ "$STATE" != versioned ]]; then
  compose stop app
fi
# Start Caddy BEFORE app readiness: SSR uses its public HTTPS hostname. The proxy
# health check tests only its local admin API, avoiding a circular app dependency.
# Recreate the proxy so updated file bind mounts/config are always picked up;
# certificate/config volumes are retained.
if ! compose up -d --no-deps --pull never --force-recreate --wait --wait-timeout 90 caddy; then
  compose ps
  echo 'Caddy did not start. Database/content/certificate volumes and backup retained.' >&2
  exit 1
fi
# No down, volume deletion, image pruning, or database recreation in this deployment.
if ! compose up -d --no-deps --pull never --wait --wait-timeout 360 app; then
  compose ps
  echo 'New app did not become healthy. Volumes and backup are retained; inspect private VM logs.' >&2
  exit 1
fi
if [[ -f "$ROOT/.bootstrap-pending" ]]; then
  if [[ "$STATE" == versioned ]]; then
    # Recovery after a successful stamp whose marker removal was interrupted.
    database verify >>"$LOG" 2>&1 || { echo 'Interrupted bootstrap version check failed' >&2; exit 1; }
  elif ! database stamp >>"$LOG" 2>&1; then
    echo 'Fresh schema baseline failed; bootstrap marker retained for recovery.' >&2
    exit 1
  fi
  rm -f "$ROOT/.bootstrap-pending"
fi
if ! database verify >>"$LOG" 2>&1; then
  echo 'Migration verification failed. Inspect the private VM log before accepting the release.' >&2
  exit 1
fi
compose exec -T db psql -U learnhouse -d learnhouse -X -v ON_ERROR_STOP=1 -c \
  'SELECT EXISTS (SELECT 1 FROM "user" u JOIN userorganization m ON m.user_id=u.id WHERE m.role_id=1) AS has_admin;' \
  | grep -q ' t' || { echo 'No initial admin exists; inspect native bootstrap before accepting the deployment.' >&2; exit 1; }
# Verify a publicly trusted certificate and hostname through the local proxy.
# --resolve bypasses VM public-IP hairpin routing, NOT TLS verification.
# No --insecure/-k or custom trust store: issuing/renewal must work normally.
https_ready=false
for attempt in $(seq 1 12); do
  if curl --fail --silent --show-error --connect-timeout 5 --max-time 10 \
      --resolve dev.dailycommit.co.za:443:127.0.0.1 \
      https://dev.dailycommit.co.za/api/v1/health >/dev/null 2>&1; then
    https_ready=true
    break
  fi
  sleep 5
done
if [[ "$https_ready" != true ]]; then
  echo 'HTTPS certificate/API check failed; release not accepted. Check DNS, port 80/443 reachability and Caddy logs.' >&2
  exit 1
fi
printf '%s\n' "$IMAGE" > "$ROOT/current-image.txt"
printf '%s\n' "$COMMIT" > "$ROOT/current-commit.txt"
compose ps
echo "DailyCommit dev deployment healthy at commit $COMMIT. Database/content volumes preserved."
