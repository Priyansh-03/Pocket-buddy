#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$ROOT/apps/api"
WEB_DIR="$ROOT/apps/web"

# ── helpers ─────────────────────────────────────────────────────────────────
log()  { echo "[run.sh] $*"; }
die()  { echo "[run.sh] ERROR: $*" >&2; exit 1; }

cleanup() {
  log "Shutting down..."
  kill "$API_PID" "$WEB_PID" 2>/dev/null || true
  wait "$API_PID" "$WEB_PID" 2>/dev/null || true
}

# ── preflight checks ─────────────────────────────────────────────────────────
command -v python3 >/dev/null 2>&1 || die "python3 not found"
command -v npm     >/dev/null 2>&1 || die "npm not found"

# ── Python venv ──────────────────────────────────────────────────────────────
VENV="$API_DIR/.venv"
if [ ! -d "$VENV" ]; then
  log "Creating Python virtual environment..."
  python3 -m venv "$VENV"
fi

PYTHON="$VENV/bin/python"
PIP="$VENV/bin/pip"

log "Installing/updating API dependencies..."
"$PIP" install -q -r "$API_DIR/requirements.txt"

# ── Node modules ─────────────────────────────────────────────────────────────
if [ ! -d "$WEB_DIR/node_modules" ]; then
  log "Installing web dependencies..."
  npm --prefix "$WEB_DIR" install --silent
fi

# ── DB migrations ─────────────────────────────────────────────────────────────
log "Running Alembic migrations..."
(cd "$API_DIR" && "$VENV/bin/alembic" upgrade head)

# ── Launch API ────────────────────────────────────────────────────────────────
log "Starting API on http://localhost:8000 ..."
(cd "$API_DIR" && "$VENV/bin/uvicorn" app.main:app --reload --host 0.0.0.0 --port 8000) &
API_PID=$!

# ── Launch Web ────────────────────────────────────────────────────────────────
log "Starting web dev server on http://localhost:5173 ..."
npm --prefix "$WEB_DIR" run dev &
WEB_PID=$!

trap cleanup EXIT INT TERM

log "Both services are running. Press Ctrl+C to stop."
wait
