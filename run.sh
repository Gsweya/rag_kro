#!/usr/bin/env bash
# =====================================================================
# rag_kro — one-shot local launcher
#
#   ./run.sh                 power everything up via Docker
#   ./run.sh up              same as above
#   ./run.sh build           build all images first
#   ./run.sh logs            follow ALL logs in one terminal
#   ./run.sh ps              show running services
#   ./run.sh down            stop everything
#   ./run.sh restart         stop + start
#
#   ./run.sh --local         power everything up WITHOUT Docker for the
#   ./run.sh --local setup     rag_kro services: core infra (postgres, redis,
#   ./run.sh --local ps        qdrant, minio) still runs in Docker, but api/
#   ./run.sh --local down      rag/ingestion/worker run from a conda env and
#                              web/wa-gateway run via npm. Service-to-service
#                              URLs are rewritten to localhost host ports.
#
# "Powering everything" (docker) = docker compose profiles dev + wa:
#   postgres, redis, qdrant, minio        (core infra, always on)
#   api, rag, ingestion, worker, web      (rag_kro services)
#   wa-gateway                            (WhatsApp bridge)
#
# Each service that deserves attention gets its OWN gnome-terminal tab
# tailing its logs, so you can watch/manage them side by side:
#   api | rag | ingestion | worker | web | wa-gateway
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")"

COMPOSE="docker compose"
PROFILES="--profile dev --profile wa"
LOCAL=0
CONDA_ENV="${RAGKRO_CONDA_ENV:-ragkro}"
CONDA_BIN="$(type -P conda || echo conda)"

# services that get a dedicated terminal tab
TAB_SERVICES=(api rag ingestion worker web wa-gateway)

# ---------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------
have_gnome_terminal() {
    command -v gnome-terminal >/dev/null 2>&1
}

open_tab() {
    local title="$1"; shift
    gnome-terminal --tab --title="$title" -- bash -c "$*; exec bash"
}

# ---------------------------------------------------------------------
# local (no-docker) mode
# ---------------------------------------------------------------------
# infra ports as published to the host (see docker-compose.yml)
LOCAL_POSTGRES_PORT=5433
LOCAL_REDIS_PORT=6379
LOCAL_QDRANT_PORT=6333
LOCAL_MINIO_PORT=9000

# env vars that must point at localhost when the services run on the host
# (docker names like "postgres" only resolve inside the compose network).
# Written inline into each tab's command — tab shells are fresh bash.
LOCAL_ENV_EXPORTS="export POSTGRES_HOST=localhost
export POSTGRES_PORT=$LOCAL_POSTGRES_PORT
export DATABASE_URL=postgresql+psycopg://\${POSTGRES_USER:-rag_kro}:\${POSTGRES_PASSWORD}@localhost:$LOCAL_POSTGRES_PORT/\${POSTGRES_DB:-rag_kro}
export REDIS_HOST=localhost
export REDIS_PORT=$LOCAL_REDIS_PORT
export REDIS_URL=redis://localhost:$LOCAL_REDIS_PORT/0
export CELERY_BROKER_URL=redis://localhost:$LOCAL_REDIS_PORT/1
export CELERY_RESULT_BACKEND=redis://localhost:$LOCAL_REDIS_PORT/2
export QDRANT_HOST=localhost
export QDRANT_PORT=$LOCAL_QDRANT_PORT
export QDRANT_URL=http://localhost:$LOCAL_QDRANT_PORT
export MINIO_HOST=localhost
export MINIO_PORT=$LOCAL_MINIO_PORT
export MINIO_ENDPOINT=http://localhost:$LOCAL_MINIO_PORT
export INGESTION_API_URL=http://localhost:8001
export RAG_API_URL=http://localhost:8002
export WA_API_CALLBACK_URL=http://localhost:8000/webhook/message
export IG_API_CALLBACK_URL=http://localhost:8000/webhook/message
export API_INTERNAL_URL=http://localhost:8000
export WA_GATEWAY_INTERNAL_URL=http://localhost:8100
export RAG_INTERNAL_URL=http://localhost:8002
export INGESTION_INTERNAL_URL=http://localhost:8001"

# run one command inside the conda env with the host-local env applied
local_service_cmd() {
    local cmd="$1"
    echo "set -a; source .env; set +a; eval \"$LOCAL_ENV_EXPORTS\"; $cmd"
}

local_setup() {
    echo "==> local mode: setting up conda env '$CONDA_ENV' + node deps ..."
    if ! "$CONDA_BIN" env list | grep -qE "^\s*$CONDA_ENV\s"; then
        echo "==> creating conda env '$CONDA_ENV' (python 3.12) ..."
        "$CONDA_BIN" create -y -n "$CONDA_ENV" python=3.12
    fi
    echo "==> installing shared package + python deps ..."
    "$CONDA_BIN" run --no-capture-output -n "$CONDA_ENV" pip install --retries 10 --default-timeout=120 \
        -e packages/python/rag_kro_shared
    "$CONDA_BIN" run --no-capture-output -n "$CONDA_ENV" pip install --retries 10 --default-timeout=120 \
        -r services/api/requirements.txt \
        -r services/rag/requirements.txt \
        -r services/ingestion/requirements.txt \
        -r services/worker/requirements.txt
    echo "==> reusing pre-downloaded torch wheels (no re-download) ..."
    if ls infra/docker/python-base/wheels/*.whl >/dev/null 2>&1; then
        "$CONDA_BIN" run --no-capture-output -n "$CONDA_ENV" pip install --retries 10 --default-timeout=120 \
            infra/docker/python-base/wheels/*.whl || echo "  (wheel install skipped — will resolve from network)"
    fi
    echo "==> installing web (next) + wa-gateway (node) deps ..."
    (cd services/web && [ -d node_modules ] || npm install --no-audit --no-fund)
    (cd services/wa-gateway && [ -d node_modules ] || npm install --no-audit --no-fund)
}

local_up() {
    if ! "$CONDA_BIN" env list | grep -qE "^\s*$CONDA_ENV\s"; then
        echo "==> conda env '$CONDA_ENV' not found — running setup first ..."
        local_setup
    fi
    echo "==> starting core infra (postgres, redis, qdrant, minio) in Docker ..."
    $COMPOSE up -d postgres redis qdrant minio
    echo "==> waiting for postgres to be healthy ..."
    for _ in $(seq 1 60); do
        if docker exec rag_kro_postgres pg_isready -U "${POSTGRES_USER:-rag_kro}" -d "${POSTGRES_DB:-rag_kro}" >/dev/null 2>&1; then
            echo "==> postgres is up"
            break
        fi
        sleep 2
    done
    echo "==> opening a terminal tab per service (running natively) ..."
    open_tab "ragkro:api"       "$(local_service_cmd "cd services/api && $CONDA_BIN run --no-capture-output -n $CONDA_ENV uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload")"
    open_tab "ragkro:rag"       "$(local_service_cmd "cd services/rag && $CONDA_BIN run --no-capture-output -n $CONDA_ENV uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload")"
    open_tab "ragkro:ingestion" "$(local_service_cmd "cd services/ingestion && $CONDA_BIN run --no-capture-output -n $CONDA_ENV uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload")"
    open_tab "ragkro:worker"    "$(local_service_cmd "cd services/worker && $CONDA_BIN run --no-capture-output -n $CONDA_ENV celery -A app.celery_app.app worker -B -l info -Q default")"
    open_tab "ragkro:web"       "$(local_service_cmd "cd services/web && npm run dev")"
    open_tab "ragkro:wa-gateway" "$(local_service_cmd "cd services/wa-gateway && npm run dev")"
    echo
    echo "==> everything is running (local mode):"
    echo "    dashboard : http://localhost:3000"
    echo "    api       : http://localhost:8000  (/docs)"
    echo "    minio     : http://localhost:9001"
    echo "    (postgres on host port $LOCAL_POSTGRES_PORT)"
    echo
}

local_ps() {
    echo "==> infra (docker):"
    $COMPOSE ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
    echo
    echo "==> local (host) processes:"
    pgrep -af "uvicorn|celery|next dev|wa-gateway|src/index.js" || echo "    (none running)"
}

up() {
    if [ -z "$(ls infra/docker/python-base/wheels/*.whl 2>/dev/null)" ]; then
        echo "==> fetching heavy ML wheels (torch ~526MB, resumable) ..."
        echo "    re-run this script any time; it continues where it left off."
        bash infra/docker/python-base/fetch-wheels.sh
    fi
    echo "==> building shared ML base image (torch, downloaded once) ..."
    $COMPOSE $PROFILES build python-base
    echo "==> building + starting all services (dev + wa) ..."
    $COMPOSE $PROFILES up -d --build
    echo "==> waiting for api to be reachable ..."
    for _ in $(seq 1 60); do
        if curl -sf -o /dev/null http://localhost:8000/health; then
            echo "==> api is up"
            break
        fi
        sleep 2
    done
    echo
    echo "==> everything is running:"
    $COMPOSE $PROFILES ps --format "table {{.Service}}\t{{.Status}}\t{{.Ports}}"
    echo
    echo "    dashboard : http://localhost:3000"
    echo "    api       : http://localhost:8000  (/docs)"
    echo "    minio     : http://localhost:9001"
    echo
}

open_log_tabs() {
    if ! have_gnome_terminal; then
        echo "gnome-terminal not found — skipping per-service tabs."
        echo "run:  $COMPOSE $PROFILES logs -f"
        return 0
    fi
    echo "==> opening a terminal tab per service (logs follow) ..."
    for svc in "${TAB_SERVICES[@]}"; do
        open_tab "ragkro:$svc" "$COMPOSE logs -f $svc"
    done
}

build() {
    echo "==> building all images ..."
    $COMPOSE $PROFILES build
}

logs() {
    $COMPOSE $PROFILES logs -f --tail=100
}

ps() {
    $COMPOSE $PROFILES ps --format "table {{.Service}}\t{{.Status}}\t{{.Ports}}"
}

down() {
    $COMPOSE $PROFILES down
}

# ---------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------
# --local flag may come before or replace the subcommand
if [ "${1:-}" = "--local" ]; then
    LOCAL=1
    shift
fi
case "${1:-up}" in
    up)
        if [ "$LOCAL" = 1 ]; then local_up; else up; open_log_tabs; fi
        ;;
    build)
        if [ "$LOCAL" = 1 ]; then echo "build has no effect in local mode (run 'setup')" >&2; exit 1; fi
        build
        ;;
    setup)
        [ "$LOCAL" = 1 ] || { echo "setup is only meaningful with --local" >&2; exit 1; }
        local_setup
        ;;
    logs)
        [ "$LOCAL" = 1 ] && { echo "use the per-service tabs for logs in local mode" >&2; exit 1; }
        logs
        ;;
    ps)
        if [ "$LOCAL" = 1 ]; then local_ps; else ps; fi
        ;;
    down)
        if [ "$LOCAL" = 1 ]; then $COMPOSE down; else down; fi
        ;;
    restart)
        if [ "$LOCAL" = 1 ]; then $COMPOSE down; local_up; else down; up; open_log_tabs; fi
        ;;
    *) echo "usage: $0 [--local] {up|build|setup|logs|ps|down|restart}" >&2; exit 1 ;;
esac
