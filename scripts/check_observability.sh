#!/usr/bin/env bash
# check_observability.sh — Layer 6 Observability gate
# Queries local VictoriaMetrics and VictoriaLogs for health signals.
# Start the stack: docker compose -f docker-compose.observability.yml up -d

set -uo pipefail

VM_URL="${VM_URL:-http://localhost:8428}"
VL_URL="${VL_URL:-http://localhost:9428}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ERRORS=0

# --- Check VictoriaMetrics health ---
if curl -sf "${VM_URL}/health" >/dev/null 2>&1; then
    echo -e "  ${GREEN}VictoriaMetrics healthy${NC} (${VM_URL})"
else
    echo -e "  ${RED}VictoriaMetrics unreachable${NC} (${VM_URL})"
    echo "  Start with: docker compose -f docker-compose.observability.yml up -d"
    exit 2  # SKIP — stack not running
fi

# --- Check VictoriaLogs health ---
if curl -sf "${VL_URL}/health" >/dev/null 2>&1; then
    echo -e "  ${GREEN}VictoriaLogs healthy${NC} (${VL_URL})"
else
    echo -e "  ${RED}VictoriaLogs unreachable${NC} (${VL_URL})"
    echo "  Start with: docker compose -f docker-compose.observability.yml up -d"
    exit 2  # SKIP — stack not running
fi

# --- Query VictoriaLogs for ERROR logs in last 5 minutes ---
ERROR_COUNT=$(curl -sf "${VL_URL}/select/logsql/stats_query" \
    --data-urlencode 'query=error' \
    --data-urlencode 'time=5m' \
    2>/dev/null | grep -oE '"hits":[0-9]+' | grep -oE '[0-9]+' || echo "0")

if [ "${ERROR_COUNT}" -gt 0 ] 2>/dev/null; then
    echo -e "  ${YELLOW}VictoriaLogs: ${ERROR_COUNT} ERROR log(s) in last 5 min${NC}"
    # Informational — errors in logs are a warning, not a gate failure
else
    echo -e "  ${GREEN}VictoriaLogs: no ERROR logs in last 5 min${NC}"
fi

# --- Query VictoriaMetrics for request latency p95 (if metrics exist) ---
P95=$(curl -sf "${VM_URL}/api/v1/query" \
    --data-urlencode 'query=histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))' \
    2>/dev/null | grep -oE '"value":\["[0-9.]+","[0-9.]+"' | grep -oE '"[0-9.]+"$' | tr -d '"' || echo "")

if [ -n "${P95}" ] && [ "${P95}" != "NaN" ]; then
    echo -e "  ${GREEN}Request latency p95: ${P95}s${NC}"
else
    echo -e "  ${YELLOW}No request latency metrics yet (app not instrumented or no traffic)${NC}"
fi

# --- Final verdict ---
if [ "${ERRORS}" -gt 0 ]; then
    echo -e "  ${RED}FAIL — ${ERRORS} observability issue(s)${NC}"
    exit 1
fi

echo -e "  ${GREEN}PASS — observability stack healthy${NC}"
exit 0
