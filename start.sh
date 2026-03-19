#!/bin/bash
# start.sh — starts backend + frontend together
# Usage: ./start.sh

ROOT="$(cd "$(dirname "$0")" && pwd)"

# Kill anything on 8000
if lsof -ti:8000 > /dev/null 2>&1; then
  echo "Killing existing process on port 8000..."
  kill -9 $(lsof -ti:8000) 2>/dev/null
  sleep 1
fi

# Activate venv
source "$ROOT/.venv/bin/activate"

echo "Starting backend on http://127.0.0.1:8000..."
uvicorn api.server:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

# Wait for backend to be ready
echo "Waiting for backend..."
for i in {1..10}; do
  if curl -s http://127.0.0.1:8000/health > /dev/null 2>&1; then
    echo "Backend ready."
    break
  fi
  sleep 1
done

echo "Starting frontend..."
cd "$ROOT/frontend" && npm run dev &
FRONTEND_PID=$!

echo ""
echo "========================================"
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:3000"
echo "  Press Ctrl+C to stop both"
echo "========================================"

# Stop both on Ctrl+C
trap "echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM

wait
