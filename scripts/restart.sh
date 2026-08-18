#!/usr/bin/env bash
# Consolidated PM2 / local-dev ops for the jobwright Kanban dashboard.
#
# Usage:
#   ./scripts/restart.sh                      # api + ui (local hot reload)
#   ./scripts/restart.sh --backend-only
#   ./scripts/restart.sh --frontend-only
#   ./scripts/restart.sh --tunnel-only
#   ./scripts/restart.sh --all
#   ./scripts/restart.sh --prod-ui            # pnpm build + restart api + health
#   ./scripts/restart.sh --tmux               # tmux session (no PM2): api --reload + vite
#   ./scripts/restart.sh --status
#   ./scripts/restart.sh start|stop|help
#
# Process names: jobwright-api (:8002), jobwright-ui (Vite :5120), jobwright-tunnel
# Local UI: http://127.0.0.1:5120  (HMR; proxies /api → :8002)
# Prod URL:  http://127.0.0.1:8002 or https://jobwright.parthchandak.info

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$ROOT"

ECOSYSTEM_EXAMPLE="${ROOT}/ecosystem.config.example.js"
ECOSYSTEM_LIVE="${ROOT}/ecosystem.config.js"
TMUX_SESSION="${JOBWRIGHT_TMUX_SESSION:-jobwright-dash}"
API_PORT="${JOBWRIGHT_API_PORT:-8002}"
UI_PORT="${JOBWRIGHT_UI_PORT:-5120}"
DASHBOARD_USER="${JOBWRIGHT_DASHBOARD_USER:-richa}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

ensure_ecosystem() {
  if [[ ! -f "$ECOSYSTEM_LIVE" ]]; then
    echo "==> creating ecosystem.config.js from example"
    cp "$ECOSYSTEM_EXAMPLE" "$ECOSYSTEM_LIVE"
  fi
}

ensure_frontend_deps() {
  if [[ ! -x "$ROOT/frontend/node_modules/.bin/vite" ]]; then
    echo "==> frontend deps (pnpm install)"
    (cd "$ROOT/frontend" && pnpm install)
  fi
}

uvicorn_bin() {
  if [[ -x "$ROOT/.venv/bin/uvicorn" ]]; then
    echo "$ROOT/.venv/bin/uvicorn"
  elif command -v uvicorn >/dev/null 2>&1; then
    command -v uvicorn
  else
    echo "python3 -m uvicorn"
  fi
}

show_help() {
  sed -n '2,18p' "$0"
  echo
  echo "Flags (restart / default):"
  echo "  (default)         restart jobwright-api + jobwright-ui"
  echo "  --backend-only    restart API only (:${API_PORT}, --reload in ecosystem)"
  echo "  --frontend-only   restart Vite only (:${UI_PORT}, HMR)"
  echo "  --tunnel-only     restart cloudflared tunnel only"
  echo "  --all             api + ui + tunnel"
  echo "  --prod-ui         pnpm build + restart api + health check"
  echo "  --tmux            start/attach tmux '${TMUX_SESSION}' (api --reload + vite)"
  echo "  --status          pm2 list (or tmux status if --tmux)"
  echo
  echo "Commands: start | stop | restart | status | help"
  echo "Alias: ./scripts/ops_pm2.sh → this script"
}

pm2_has() {
  local name="$1"
  pm2 describe "$name" >/dev/null 2>&1
}

pm2_start_or_restart() {
  local name="$1"
  ensure_ecosystem
  require_cmd pm2
  # delete+start so ecosystem arg/env changes (e.g. port) take effect
  if pm2_has "$name"; then
    echo "==> pm2 delete ${name} (refresh from ecosystem)"
    pm2 delete "$name" >/dev/null
  fi
  echo "==> pm2 start ${name}"
  pm2 start "$ECOSYSTEM_LIVE" --only "$name"
}

build_frontend() {
  echo "==> frontend build"
  ensure_frontend_deps
  (
    cd frontend
    if command -v pnpm >/dev/null 2>&1; then
      pnpm build
    else
      ./node_modules/.bin/vite build
    fi
  )
}

health_check() {
  require_cmd curl
  echo "==> health check :${API_PORT}"
  curl -sf "http://127.0.0.1:${API_PORT}/api/health"
  echo
}

cmd_tmux() {
  require_cmd tmux
  ensure_frontend_deps

  local UV
  UV="$(uvicorn_bin)"

  if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    echo "==> tmux session '${TMUX_SESSION}' already running"
    echo "    attach: tmux attach -t ${TMUX_SESSION}"
    echo "    kill:   tmux kill-session -t ${TMUX_SESSION}"
    tmux list-windows -t "$TMUX_SESSION"
    return 0
  fi

  echo "==> tmux new-session '${TMUX_SESSION}'"
  echo "    API  :${API_PORT} (--reload)  |  UI :${UI_PORT} (Vite HMR)"
  echo "    Open http://127.0.0.1:${UI_PORT}"

  tmux new-session -d -s "$TMUX_SESSION" -n api \
    "cd '$ROOT' && export JOBWRIGHT_DASHBOARD_USER='$DASHBOARD_USER' PYTHONPATH='$ROOT/src' PORT='$API_PORT' JOBWRIGHT_CORS_ORIGINS='http://127.0.0.1:${UI_PORT},http://localhost:${UI_PORT},http://127.0.0.1:${API_PORT}' && $UV jobwright.web.app:app --host 127.0.0.1 --port ${API_PORT} --reload"

  tmux new-window -t "$TMUX_SESSION" -n ui \
    "cd '$ROOT/frontend' && PORT=${API_PORT} ./node_modules/.bin/vite --port ${UI_PORT} --host 0.0.0.0"

  tmux select-window -t "${TMUX_SESSION}:api"
  echo "==> started. Attach with: tmux attach -t ${TMUX_SESSION}"
}

cmd_tmux_stop() {
  if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    echo "==> tmux kill-session '${TMUX_SESSION}'"
    tmux kill-session -t "$TMUX_SESSION"
  else
    echo "No tmux session '${TMUX_SESSION}'"
  fi
}

cmd_restart() {
  local BACKEND=false
  local FRONTEND=false
  local TUNNEL=false
  local PROD_UI=false
  local ALL=false
  local STATUS_ONLY=false
  local TMUX_MODE=false
  local EXPLICIT=false

  for arg in "$@"; do
    case "${arg}" in
      --backend-only|--backend) BACKEND=true; EXPLICIT=true ;;
      --frontend-only|--frontend) FRONTEND=true; EXPLICIT=true ;;
      --tunnel-only|--tunnel) TUNNEL=true; EXPLICIT=true ;;
      --prod-ui) PROD_UI=true ;;
      --all) ALL=true ;;
      --tmux) TMUX_MODE=true ;;
      --status) STATUS_ONLY=true ;;
      -h|--help)
        show_help
        exit 0
        ;;
      "")
        ;;
      *)
        echo "Unknown option: ${arg}" >&2
        show_help
        exit 1
        ;;
    esac
  done

  if [[ "${TMUX_MODE}" == true ]]; then
    if [[ "${STATUS_ONLY}" == true ]]; then
      tmux list-sessions 2>/dev/null | grep -E "^${TMUX_SESSION}:" || echo "tmux session '${TMUX_SESSION}' not running"
      exit 0
    fi
    cmd_tmux
    exit 0
  fi

  if [[ "${STATUS_ONLY}" == true ]]; then
    require_cmd pm2
    pm2 list
    exit 0
  fi

  require_cmd pm2
  ensure_ecosystem
  ensure_frontend_deps

  if [[ "${ALL}" == true ]]; then
    BACKEND=true
    FRONTEND=true
    TUNNEL=true
    EXPLICIT=true
  fi

  if [[ "${PROD_UI}" == true ]]; then
    if [[ "${EXPLICIT}" == true || "${ALL}" == true ]]; then
      echo "Cannot combine --prod-ui with other restart targets." >&2
      exit 1
    fi
    build_frontend
    BACKEND=true
    EXPLICIT=true
  fi

  if [[ "${EXPLICIT}" == false ]]; then
    BACKEND=true
    FRONTEND=true
  fi

  if [[ "${BACKEND}" == true ]]; then
    pm2_start_or_restart jobwright-api
  fi
  if [[ "${FRONTEND}" == true ]]; then
    pm2_start_or_restart jobwright-ui
  fi
  if [[ "${TUNNEL}" == true ]]; then
    pm2_start_or_restart jobwright-tunnel
  fi

  pm2 list

  if [[ "${PROD_UI}" == true ]]; then
    health_check
  elif [[ "${BACKEND}" == true ]]; then
    sleep 1
    curl -sf "http://127.0.0.1:${API_PORT}/api/health" >/dev/null 2>&1 \
      && echo "==> API healthy on :${API_PORT}" \
      || echo "==> API not ready yet (check: pm2 logs jobwright-api)"
  fi

  if [[ "${FRONTEND}" == true ]]; then
    echo "==> Vite UI: http://127.0.0.1:${UI_PORT}  (HMR; /api → :${API_PORT})"
  fi
}

cmd_start() {
  ensure_ecosystem
  ensure_frontend_deps
  require_cmd pm2
  echo "==> pm2 start ecosystem.config.js"
  pm2 start "$ECOSYSTEM_LIVE"
  pm2 list
  echo "==> Local UI: http://127.0.0.1:${UI_PORT}"
}

cmd_stop() {
  if [[ "${1:-}" == "--tmux" ]]; then
    cmd_tmux_stop
    return
  fi
  require_cmd pm2
  echo "==> pm2 stop jobwright-api jobwright-ui jobwright-tunnel"
  pm2 stop jobwright-api jobwright-ui jobwright-tunnel 2>/dev/null || true
  pm2 list
}

# Dispatch
SUBCOMMAND="restart"
ARGS=()

if [[ $# -gt 0 ]]; then
  case "$1" in
    start|stop|restart|status|help|-h|--help)
      SUBCOMMAND="$1"
      shift
      ARGS=("$@")
      ;;
    --*)
      SUBCOMMAND="restart"
      ARGS=("$@")
      ;;
    *)
      echo "Unknown command: $1" >&2
      show_help
      exit 1
      ;;
  esac
fi

case "$SUBCOMMAND" in
  help|-h|--help) show_help ;;
  status) require_cmd pm2; pm2 list ;;
  start) cmd_start ;;
  stop) cmd_stop "${ARGS[@]}" ;;
  restart)
    if ((${#ARGS[@]} > 0)); then
      cmd_restart "${ARGS[@]}"
    else
      cmd_restart
    fi
    ;;
esac
