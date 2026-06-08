#!/usr/bin/env bash
# Start LOOPER: FastAPI backend + React frontend with one command.
#   ./run.sh
# Open the app at http://localhost:5173 (NOT :8000 — that's the data API).
# Press Ctrl+C to stop both.
set -e
cd "$(dirname "$0")"

# Use the Python venv if it exists
[ -d venv ] && source venv/bin/activate

# Make sure backend deps are installed
if ! python -c "import fastapi, uvicorn" 2>/dev/null; then
  echo "Installing Python deps…"
  pip install -q -r requirements.txt
fi

# Start the backend; stop it automatically when this script exits
uvicorn api:app --port 8000 > /tmp/looper_api.log 2>&1 &
API_PID=$!
trap "kill $API_PID 2>/dev/null" EXIT

# Wait until the backend is actually answering before opening the app
echo "Starting backend…"
for i in $(seq 1 40); do
  if curl -s http://localhost:8000/api/config >/dev/null 2>&1; then
    echo "Backend ready on http://localhost:8000"
    break
  fi
  if ! kill -0 "$API_PID" 2>/dev/null; then
    echo "Backend failed to start. Last log lines:"; tail -n 20 /tmp/looper_api.log; exit 1
  fi
  sleep 0.5
done

# Start the frontend (installs packages the first time) and open the browser
cd frontend
[ -d node_modules ] || npm install
npm run dev -- --open
