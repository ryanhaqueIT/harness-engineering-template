#!/usr/bin/env bash
# boot_worktree.sh — Per-worktree app booting (backend + frontend).
#
# Boots both the backend and frontend on dynamically allocated ports,
# writes metadata so other scripts can discover them. Supports multiple
# parallel instances (one per git worktree or directory).
#
# Usage:
#   ./scripts/boot_worktree.sh                   # Boot from current repo
#   ./scripts/boot_worktree.sh /path/to/worktree  # Boot a specific worktree
#   ./scripts/boot_worktree.sh --stop             # Stop this worktree's instances
#   ./scripts/boot_worktree.sh --check            # Health check running instances
#   ./scripts/boot_worktree.sh --status           # Show instance metadata
#
# After booting, metadata is written to:
#   <worktree>/instance-metadata.json
#
# Port allocation: backend 3900-3949, frontend 3950-3999.

set -uo pipefail

# ─── Constants ────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

BACKEND_PORT_MIN=3900
BACKEND_PORT_MAX=3949
FRONTEND_PORT_MIN=3950
FRONTEND_PORT_MAX=3999

HEALTH_TIMEOUT=30
STARTUP_POLL_INTERVAL=1

# ─── Determine worktree root ─────────────────────────────────────────

WORKTREE_PATH=""
ACTION="boot"

for arg in "$@"; do
    case "$arg" in
        --stop)    ACTION="stop" ;;
        --check)   ACTION="check" ;;
        --status)  ACTION="status" ;;
        --help|-h) ACTION="help" ;;
        *)
            if [ -z "$WORKTREE_PATH" ] && [ -d "$arg" ]; then
                WORKTREE_PATH="$arg"
            fi
            ;;
    esac
done

if [ -z "$WORKTREE_PATH" ]; then
    WORKTREE_PATH="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
fi

# Resolve to absolute path
WORKTREE_PATH="$(cd "$WORKTREE_PATH" && pwd)"

BACKEND_DIR="${WORKTREE_PATH}/backend"
FRONTEND_DIR="${WORKTREE_PATH}/frontend"
METADATA_FILE="${WORKTREE_PATH}/instance-metadata.json"
PID_FILE_BACKEND="${WORKTREE_PATH}/.backend.pid"
PID_FILE_FRONTEND="${WORKTREE_PATH}/.frontend.pid"

# ─── Helpers ──────────────────────────────────────────────────────────

find_free_port() {
    local min="$1"
    local max="$2"
    local port
    port=$(python3 -c "
import socket
for p in range($min, $max + 1):
    try:
        s = socket.socket()
        s.bind(('127.0.0.1', p))
        print(p)
        s.close()
        break
    except OSError:
        continue
" 2>/dev/null)
    if [ -n "$port" ]; then
        echo "$port"
        return 0
    fi
    echo ""
    return 1
}

kill_pid_file() {
    local pidfile="$1"
    local label="$2"
    if [ -f "$pidfile" ]; then
        local pid
        pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
            for i in $(seq 1 5); do
                if ! kill -0 "$pid" 2>/dev/null; then break; fi
                sleep 1
            done
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null
            fi
            echo -e "  ${GREEN}Stopped${NC} ${label} (PID ${pid})"
        else
            echo -e "  ${YELLOW}Already stopped${NC} ${label} (PID ${pid} not running)"
        fi
        rm -f "$pidfile"
    else
        echo -e "  ${YELLOW}No PID file${NC} for ${label}"
    fi
}

wait_for_health() {
    local url="$1"
    local timeout="$2"
    for i in $(seq 1 "$timeout"); do
        if curl -sf -o /dev/null "$url" 2>/dev/null; then
            return 0
        fi
        sleep "$STARTUP_POLL_INTERVAL"
    done
    return 1
}

# ─── Help ─────────────────────────────────────────────────────────────

if [ "$ACTION" = "help" ]; then
    echo "boot_worktree.sh — Per-worktree app booting (backend + frontend)"
    echo ""
    echo "Usage:"
    echo "  ./scripts/boot_worktree.sh [path]       Boot backend + frontend"
    echo "  ./scripts/boot_worktree.sh --stop        Stop running instances"
    echo "  ./scripts/boot_worktree.sh --check       Health check instances"
    echo "  ./scripts/boot_worktree.sh --status      Show instance metadata"
    echo ""
    echo "Metadata written to: <worktree>/instance-metadata.json"
    exit 0
fi

# ─── Stop ─────────────────────────────────────────────────────────────

if [ "$ACTION" = "stop" ]; then
    echo -e "${BOLD}Stopping instances for:${NC} ${WORKTREE_PATH}"
    kill_pid_file "$PID_FILE_BACKEND" "Backend"
    kill_pid_file "$PID_FILE_FRONTEND" "Frontend"
    rm -f "$METADATA_FILE"
    echo -e "${GREEN}Cleanup complete${NC}"
    exit 0
fi

# ─── Status ───────────────────────────────────────────────────────────

if [ "$ACTION" = "status" ]; then
    if [ -f "$METADATA_FILE" ]; then
        echo -e "${BOLD}Instance metadata:${NC} ${METADATA_FILE}"
        cat "$METADATA_FILE"
    else
        echo -e "${YELLOW}No instance metadata found at ${METADATA_FILE}${NC}"
        echo "  Run ./scripts/boot_worktree.sh to start instances."
    fi
    exit 0
fi

# ─── Check ────────────────────────────────────────────────────────────

if [ "$ACTION" = "check" ]; then
    if [ ! -f "$METADATA_FILE" ]; then
        echo -e "${RED}No instance metadata found${NC}"
        echo "  Run ./scripts/boot_worktree.sh to start instances."
        exit 1
    fi

    echo -e "${BOLD}Health check for:${NC} ${WORKTREE_PATH}"

    BACKEND_URL=$(python3 -c "import json; print(json.load(open('$METADATA_FILE'))['backend_url'])" 2>/dev/null || echo "")
    FRONTEND_URL=$(python3 -c "import json; print(json.load(open('$METADATA_FILE'))['frontend_url'])" 2>/dev/null || echo "")

    CHECKS_PASSED=0
    CHECKS_FAILED=0

    if [ -n "$BACKEND_URL" ]; then
        if curl -sf -o /dev/null "${BACKEND_URL}/health" 2>/dev/null; then
            echo -e "  ${GREEN}PASS${NC}  Backend healthy at ${BACKEND_URL}"
            ((CHECKS_PASSED++))
        else
            echo -e "  ${RED}FAIL${NC}  Backend unreachable at ${BACKEND_URL}"
            ((CHECKS_FAILED++))
        fi
    fi

    if [ -n "$FRONTEND_URL" ]; then
        if curl -sf -o /dev/null "${FRONTEND_URL}" 2>/dev/null; then
            echo -e "  ${GREEN}PASS${NC}  Frontend healthy at ${FRONTEND_URL}"
            ((CHECKS_PASSED++))
        else
            echo -e "  ${RED}FAIL${NC}  Frontend unreachable at ${FRONTEND_URL}"
            ((CHECKS_FAILED++))
        fi
    fi

    echo ""
    echo "${CHECKS_PASSED} healthy, ${CHECKS_FAILED} unhealthy"

    [ "$CHECKS_FAILED" -gt 0 ] && exit 1
    exit 0
fi

# ─── Boot ─────────────────────────────────────────────────────────────

echo "==========================================="
echo -e " ${BOLD}Worktree Boot${NC}"
echo " Path: ${WORKTREE_PATH}"
echo "==========================================="
echo ""

# Stop any existing instances first
if [ -f "$PID_FILE_BACKEND" ] || [ -f "$PID_FILE_FRONTEND" ]; then
    echo "Stopping previous instances..."
    kill_pid_file "$PID_FILE_BACKEND" "Backend (previous)"
    kill_pid_file "$PID_FILE_FRONTEND" "Frontend (previous)"
    rm -f "$METADATA_FILE"
    echo ""
fi

# ─── Find free ports ─────────────────────────────────────────────────

BACKEND_PORT=$(find_free_port $BACKEND_PORT_MIN $BACKEND_PORT_MAX)
if [ -z "$BACKEND_PORT" ]; then
    echo -e "${RED}ERROR: No free port in range ${BACKEND_PORT_MIN}-${BACKEND_PORT_MAX}${NC}"
    exit 1
fi

FRONTEND_PORT=$(find_free_port $FRONTEND_PORT_MIN $FRONTEND_PORT_MAX)
if [ -z "$FRONTEND_PORT" ]; then
    echo -e "${RED}ERROR: No free port in range ${FRONTEND_PORT_MIN}-${FRONTEND_PORT_MAX}${NC}"
    exit 1
fi

echo -e "  Backend port:  ${CYAN}${BACKEND_PORT}${NC}"
echo -e "  Frontend port: ${CYAN}${FRONTEND_PORT}${NC}"
echo ""

# ─── Boot backend ────────────────────────────────────────────────────

BACKEND_PID=""

if [ -d "$BACKEND_DIR" ]; then
    echo -e "${BOLD}Starting backend...${NC}"
    cd "$BACKEND_DIR"

    # Detect backend type and boot accordingly
    if [ -f "requirements.txt" ] || [ -f "pyproject.toml" ]; then
        # Python backend
        if [ -d ".venv" ]; then
            source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate 2>/dev/null || true
        fi

        # Try common Python web frameworks
        if [ -f "main.py" ]; then
            uvicorn main:app --host 127.0.0.1 --port "$BACKEND_PORT" > /tmp/boot_worktree_backend_${BACKEND_PORT}.log 2>&1 &
        elif [ -f "app.py" ]; then
            uvicorn app:app --host 127.0.0.1 --port "$BACKEND_PORT" > /tmp/boot_worktree_backend_${BACKEND_PORT}.log 2>&1 &
        elif [ -f "manage.py" ]; then
            python manage.py runserver "127.0.0.1:${BACKEND_PORT}" > /tmp/boot_worktree_backend_${BACKEND_PORT}.log 2>&1 &
        else
            echo -e "  ${RED}Cannot detect Python entry point (expected main.py, app.py, or manage.py)${NC}"
            exit 1
        fi
        BACKEND_PID=$!

    elif [ -f "package.json" ]; then
        # Node.js backend
        if grep -q '"dev"' package.json 2>/dev/null; then
            PORT="$BACKEND_PORT" npm run dev > /tmp/boot_worktree_backend_${BACKEND_PORT}.log 2>&1 &
        elif grep -q '"start"' package.json 2>/dev/null; then
            PORT="$BACKEND_PORT" npm start > /tmp/boot_worktree_backend_${BACKEND_PORT}.log 2>&1 &
        else
            echo -e "  ${RED}No dev or start script in backend/package.json${NC}"
            exit 1
        fi
        BACKEND_PID=$!
    fi

    if [ -n "$BACKEND_PID" ]; then
        echo "$BACKEND_PID" > "$PID_FILE_BACKEND"

        if wait_for_health "http://localhost:${BACKEND_PORT}/health" "$HEALTH_TIMEOUT"; then
            echo -e "  ${GREEN}Backend healthy${NC} at http://localhost:${BACKEND_PORT} (PID ${BACKEND_PID})"
        else
            echo -e "  ${RED}Backend failed to start within ${HEALTH_TIMEOUT}s${NC}"
            echo "  Check logs: /tmp/boot_worktree_backend_${BACKEND_PORT}.log"
            kill "$BACKEND_PID" 2>/dev/null
            rm -f "$PID_FILE_BACKEND"
            exit 1
        fi
    fi
else
    echo -e "${YELLOW}No backend/ directory — skipping backend boot${NC}"
fi

# ─── Boot frontend ───────────────────────────────────────────────────

FRONTEND_PID=""

if [ -d "$FRONTEND_DIR" ] && [ -f "$FRONTEND_DIR/package.json" ]; then
    echo -e "${BOLD}Starting frontend...${NC}"
    cd "$FRONTEND_DIR"

    # Detect framework
    if [ -f "next.config.js" ] || [ -f "next.config.ts" ] || [ -f "next.config.mjs" ]; then
        # Next.js
        if [ ! -d ".next" ]; then
            echo "  Building frontend (first run)..."
            npx next build > /tmp/boot_worktree_frontend_build.log 2>&1
            if [ $? -ne 0 ]; then
                echo -e "  ${RED}Frontend build failed${NC}"
                kill_pid_file "$PID_FILE_BACKEND" "Backend"
                exit 1
            fi
        fi
        npx next start -p "$FRONTEND_PORT" > /tmp/boot_worktree_frontend_${FRONTEND_PORT}.log 2>&1 &
        FRONTEND_PID=$!

    elif [ -f "vite.config.ts" ] || [ -f "vite.config.js" ]; then
        # Vite
        npx vite --port "$FRONTEND_PORT" > /tmp/boot_worktree_frontend_${FRONTEND_PORT}.log 2>&1 &
        FRONTEND_PID=$!

    elif grep -q '"dev"' package.json 2>/dev/null; then
        PORT="$FRONTEND_PORT" npm run dev > /tmp/boot_worktree_frontend_${FRONTEND_PORT}.log 2>&1 &
        FRONTEND_PID=$!
    fi

    if [ -n "$FRONTEND_PID" ]; then
        echo "$FRONTEND_PID" > "$PID_FILE_FRONTEND"

        if wait_for_health "http://localhost:${FRONTEND_PORT}" "$HEALTH_TIMEOUT"; then
            echo -e "  ${GREEN}Frontend healthy${NC} at http://localhost:${FRONTEND_PORT} (PID ${FRONTEND_PID})"
        else
            echo -e "  ${RED}Frontend failed to start within ${HEALTH_TIMEOUT}s${NC}"
            echo "  Check logs: /tmp/boot_worktree_frontend_${FRONTEND_PORT}.log"
            kill "$FRONTEND_PID" 2>/dev/null
            rm -f "$PID_FILE_FRONTEND"
            kill_pid_file "$PID_FILE_BACKEND" "Backend"
            exit 1
        fi
    fi
else
    echo -e "${YELLOW}No frontend/ directory — skipping frontend boot${NC}"
fi

# ─── Write metadata ──────────────────────────────────────────────────

BRANCH=$(git -C "$WORKTREE_PATH" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
COMMIT=$(git -C "$WORKTREE_PATH" rev-parse --short HEAD 2>/dev/null || echo "unknown")

cat > "$METADATA_FILE" << EOF
{
    "worktree": "${WORKTREE_PATH}",
    "backend_port": ${BACKEND_PORT:-0},
    "backend_url": "http://localhost:${BACKEND_PORT}",
    "backend_pid": ${BACKEND_PID:-0},
    "frontend_port": ${FRONTEND_PORT:-0},
    "frontend_url": "http://localhost:${FRONTEND_PORT}",
    "frontend_pid": ${FRONTEND_PID:-0},
    "branch": "${BRANCH}",
    "commit": "${COMMIT}",
    "started_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

echo ""
echo "==========================================="
echo -e " ${GREEN}Services running${NC}"
echo ""
if [ -n "$BACKEND_PID" ]; then echo "  Backend:  http://localhost:${BACKEND_PORT}"; fi
if [ -n "$FRONTEND_PID" ]; then echo "  Frontend: http://localhost:${FRONTEND_PORT}"; fi
echo "  Metadata: ${METADATA_FILE}"
echo ""
echo "  Stop:   ./scripts/boot_worktree.sh --stop"
echo "  Check:  ./scripts/boot_worktree.sh --check"
echo "==========================================="
exit 0
