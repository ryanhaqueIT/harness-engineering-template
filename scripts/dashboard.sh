#!/usr/bin/env bash
# dashboard.sh — Launch the Harness DAG Dashboard
# Usage: bash scripts/dashboard.sh
#
# Opens an Airflow-inspired DAG visualization in your browser.
# Run validate.sh in another terminal to see gates light up in real-time.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HARNESS_DIR="${REPO_ROOT}/.harness"
PORT="${HARNESS_PORT:-8099}"
PID_FILE="${HARNESS_DIR}/dashboard.pid"

# Kill existing server if running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null || echo "")
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        kill "$OLD_PID" 2>/dev/null || true
        sleep 0.5
    fi
    rm -f "$PID_FILE"
fi

# Generate dashboard HTML
echo "Generating dashboard..."
python3 "${SCRIPT_DIR}/harness_dashboard.py"

# Start HTTP server in background
cd "$HARNESS_DIR"
python3 -m http.server "$PORT" &>/dev/null &
SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"

# Open browser (cross-platform)
URL="http://localhost:${PORT}/dashboard.html"
if command -v start &>/dev/null; then
    start "$URL"
elif command -v open &>/dev/null; then
    open "$URL"
elif command -v xdg-open &>/dev/null; then
    xdg-open "$URL"
else
    echo "Open $URL in your browser"
fi

echo ""
echo "════════════════════════════════════════════════════"
echo " Harness Dashboard running at $URL"
echo " PID: $SERVER_PID"
echo "════════════════════════════════════════════════════"
echo ""
echo " Now run in another terminal:"
echo "   bash scripts/validate.sh"
echo ""
echo " Watch the gates light up in real-time!"
echo ""
echo " To stop: kill $SERVER_PID"
echo "════════════════════════════════════════════════════"

# Wait for server (so Ctrl+C stops it)
wait "$SERVER_PID" 2>/dev/null || true
