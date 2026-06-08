#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_NAME="LOOPER"
# Ports are env-overridable so Control Deck can assign unique ones and run
# multiple projects at once. Defaults preserve standalone behaviour.
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
export BACKEND_PORT FRONTEND_PORT

# Colors
if [[ -t 1 ]]; then
  GREEN='\033[32m'
  BLUE='\033[34m'
  YELLOW='\033[33m'
  RESET='\033[0m'
else
  GREEN=''
  BLUE=''
  YELLOW=''
  RESET=''
fi

log_info() { echo "${BLUE}[run.sh]${RESET} $1"; }
log_success() { echo "${GREEN}[run.sh]${RESET} $1"; }
log_warn() { echo "${YELLOW}[run.sh]${RESET} $1"; }

cleanup() {
  log_warn "Shutting down..."
  kill $BACKEND_PID 2>/dev/null || true
  kill $FRONTEND_PID 2>/dev/null || true
  exit 0
}

trap cleanup SIGINT SIGTERM

cd "$SCRIPT_DIR"

# ============================================================================
# Step 1: Setup Python venv & dependencies
# ============================================================================
log_info "Checking Python environment..."

if [[ ! -d "venv" ]]; then
  log_info "Creating virtual environment..."
  python3 -m venv venv
  source venv/bin/activate
  log_info "Installing Python dependencies..."
  pip install --upgrade pip > /dev/null 2>&1
  pip install -q -r requirements.txt
else
  source venv/bin/activate
fi

log_success "Python environment ready"

# ============================================================================
# Step 2: Start FastAPI backend
# ============================================================================
log_info "Starting FastAPI backend on port $BACKEND_PORT..."
cd "$SCRIPT_DIR"
uvicorn api:app --reload --port $BACKEND_PORT > /tmp/looper_backend.log 2>&1 &
BACKEND_PID=$!
log_success "Backend starting (PID: $BACKEND_PID)"

# Give backend a moment to start
sleep 2

if ! kill -0 $BACKEND_PID 2>/dev/null; then
  log_warn "Backend failed to start. Check /tmp/looper_backend.log:"
  cat /tmp/looper_backend.log
  exit 1
fi

# ============================================================================
# Step 3: Setup & start React frontend
# ============================================================================
log_info "Setting up React frontend..."
cd "$SCRIPT_DIR/frontend"

if [[ ! -d "node_modules" ]]; then
  log_info "Installing npm dependencies (this takes a minute)..."
  npm install --quiet
fi

log_info "Starting React dev server on port $FRONTEND_PORT..."
npm run dev -- --port $FRONTEND_PORT > /tmp/looper_frontend.log 2>&1 &
FRONTEND_PID=$!
log_success "Frontend starting (PID: $FRONTEND_PID)"

# Give frontend a moment to start
sleep 3

# ============================================================================
# Step 4: Display startup info
# ============================================================================
echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                   ✅ LOOPER is running                     ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "  📱 Open your browser:  ${GREEN}http://localhost:$FRONTEND_PORT${RESET}"
echo ""
echo "  📊 API docs:          ${BLUE}http://localhost:$BACKEND_PORT/docs${RESET}"
echo ""
echo "  🔧 Backend:           running on :$BACKEND_PORT (PID: $BACKEND_PID)"
echo "  ⚛️  Frontend:           running on :$FRONTEND_PORT (PID: $FRONTEND_PID)"
echo ""
echo "  📱 Mobile (same WiFi): Run again with ${YELLOW}--host${RESET} flag"
echo ""
echo "  Press Ctrl+C to stop all services"
echo ""

# ============================================================================
# Step 5: Monitor & keep running
# ============================================================================
while true; do
  if ! kill -0 $BACKEND_PID 2>/dev/null; then
    log_warn "Backend crashed (PID: $BACKEND_PID)"
    kill $FRONTEND_PID 2>/dev/null || true
    echo ""
    log_warn "Check /tmp/looper_backend.log for error details"
    exit 1
  fi

  if ! kill -0 $FRONTEND_PID 2>/dev/null; then
    log_warn "Frontend crashed (PID: $FRONTEND_PID)"
    kill $BACKEND_PID 2>/dev/null || true
    echo ""
    log_warn "Check /tmp/looper_frontend.log for error details"
    exit 1
  fi

  sleep 5
done
