#!/usr/bin/env bash
# =====================================================================
# rag_kro — one-shot local launcher
#
#   ./run.sh            power everything up (infra + dev services + wa gateway)
#   ./run.sh up         same as above
#   ./run.sh build      build all images first
#   ./run.sh logs       follow ALL logs in one terminal
#   ./run.sh ps         show running services
#   ./run.sh down       stop everything
#   ./run.sh restart    stop + start
#
# "Powering everything" = docker compose profiles dev + wa:
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

up() {
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
case "${1:-up}" in
    up)        up; open_log_tabs ;;
    build)     build ;;
    logs)      logs ;;
    ps)        ps ;;
    down)      down ;;
    restart)   down; up; open_log_tabs ;;
    *) echo "usage: $0 {up|build|logs|ps|down|restart}" >&2; exit 1 ;;
esac
