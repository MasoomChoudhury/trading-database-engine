#!/bin/bash
# =============================================================================
# Database Engine — Deploy / Restart Script
# =============================================================================
# Use this for quick restarts and updates AFTER initial setup.
# For FIRST-TIME setup, run ./setup.sh instead.
#
# Usage:
#   ./deploy.sh          Deploy (build + start)
#   ./deploy.sh pull     Pull latest git + rebuild + restart
#   ./deploy.sh restart  Restart containers
#   ./deploy.sh logs     Tail logs
#   ./deploy.sh stop     Stop containers
#   ./deploy.sh status   Show container status
# =============================================================================

set -e

COMPOSE_FILE="docker-compose.yml"
PROJECT_NAME="db-engine"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERR]${NC}   $*" >&2; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }

cd "$SCRIPT_DIR"

# ── Routing ───────────────────────────────────────────────────────────────────
case "${1:-deploy}" in
    deploy)
        info "Building and starting services..."
        docker compose -p "$PROJECT_NAME" build
        docker compose -p "$PROJECT_NAME" up -d
        info "Deployment complete. Run '$0 status' to verify."
        ;;

    pull)
        info "Pulling latest code from git..."
        if [ ! -d ".git" ]; then
            error "Not a git repository — cannot pull."
            exit 1
        fi
        BRANCH=$(git branch --show-current 2>/dev/null || echo "main")
        git pull origin "$BRANCH" --ff
        info "Rebuilding and restarting..."
        docker compose -p "$PROJECT_NAME" up -d --build
        success "Updated and restarted."
        ;;

    restart)
        info "Restarting services..."
        docker compose -p "$PROJECT_NAME" restart
        success "Restarted."
        ;;

    restart-engine)
        info "Restarting engine only..."
        docker compose -p "$PROJECT_NAME" restart engine
        success "Engine restarted."
        ;;

    logs)
        shift
        docker compose -p "$PROJECT_NAME" logs -f "$@"
        ;;

    stop|down)
        info "Stopping all services..."
        docker compose -p "$PROJECT_NAME" down
        success "Stopped."
        ;;

    status)
        docker compose -p "$PROJECT_NAME" ps
        echo ""
        ENGINE_HEALTH=$(docker inspect --format='{{.State.Health.Status}}' db_engine 2>/dev/null || echo "N/A")
        info "Engine health: ${ENGINE_HEALTH}"
        ;;

    shell|exec)
        docker compose -p "$PROJECT_NAME" exec engine bash
        ;;

    "")
        echo "Usage: $0 {deploy|pull|restart|restart-engine|logs|stop|status|shell}"
        exit 1
        ;;

    *)
        error "Unknown command: $1"
        echo "Usage: $0 {deploy|pull|restart|restart-engine|logs|stop|status|shell}"
        exit 1
        ;;
esac
