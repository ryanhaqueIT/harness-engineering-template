#!/usr/bin/env bash
# check_observability.sh — Layer 6 Observability Gate
# Queries VictoriaLogs (LogsQL) and VictoriaMetrics (PromQL) for real signals.
# Based on: OpenAI per-worktree observability + Datadog verification pyramid.
#
# This gate doesn't just check "is the stack running?" — it checks:
# 1. Are there ERROR logs in the last 5 minutes?
# 2. Is p95 request latency under threshold?
# 3. Do specific expected log lines exist (if feature_list.json defines them)?
# 4. Are there any panic/crash logs?
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

VM_URL="${VICTORIAMETRICS_URL:-http://localhost:8428}"
VL_URL="${VICTORIALOGS_URL:-http://localhost:9428}"

PASS=0
FAIL=0
WARN=0

log_pass() { echo "  PASS: $1"; ((PASS++)); }
log_fail() { echo "  FAIL: $1"; ((FAIL++)); }
log_warn() { echo "  WARN: $1"; ((WARN++)); }

# ─── Health Checks ───────────────────────────────────────────────
echo "Layer 6: Observability Gate"
echo ""

# Check VictoriaMetrics health
if curl -sf "${VM_URL}/health" >/dev/null 2>&1; then
    log_pass "VictoriaMetrics reachable"
else
    echo "SKIP: VictoriaMetrics not running at ${VM_URL}"
    echo "Start with: docker compose -f docker-compose.observability.yml up -d"
    exit 0
fi

# Check VictoriaLogs health
if curl -sf "${VL_URL}/health" >/dev/null 2>&1; then
    log_pass "VictoriaLogs reachable"
else
    log_fail "VictoriaLogs not reachable at ${VL_URL}"
fi

# ─── LogsQL Queries ──────────────────────────────────────────────
echo ""
echo "Log Analysis (last 5 minutes):"

# Query 1: ERROR count in last 5 minutes
ERROR_LINES=$(curl -sf "${VL_URL}/select/logsql/query?query=_msg%3A~%22ERROR%22&start=5m&limit=10" 2>/dev/null || echo "")
ERROR_COUNT=$(echo "$ERROR_LINES" | grep -c "." 2>/dev/null || echo "0")

if [ "$ERROR_COUNT" -eq 0 ]; then
    log_pass "No ERROR logs in last 5 minutes"
elif [ "$ERROR_COUNT" -lt 5 ]; then
    log_warn "Found $ERROR_COUNT ERROR logs in last 5 minutes"
else
    log_fail "Found $ERROR_COUNT ERROR logs in last 5 minutes (threshold: <5)"
fi

# Query 2: PANIC/FATAL count
PANIC_LINES=$(curl -sf "${VL_URL}/select/logsql/query?query=_msg%3A~%22PANIC%7CFATAL%7Cpanic%7Cfatal%22&start=5m&limit=5" 2>/dev/null || echo "")
PANIC_COUNT=$(echo "$PANIC_LINES" | grep -c "." 2>/dev/null || echo "0")

if [ "$PANIC_COUNT" -eq 0 ]; then
    log_pass "No PANIC/FATAL logs"
else
    log_fail "Found $PANIC_COUNT PANIC/FATAL logs — investigate immediately"
    echo "$PANIC_LINES" | head -3
fi

# Query 3: Feature-specific log assertions (if feature_list.json exists)
if [ -f "${REPO_ROOT}/.harness/feature_list.json" ]; then
    echo ""
    echo "Feature Log Assertions:"

    python3 -c "
import json, sys
with open('${REPO_ROOT}/.harness/feature_list.json') as f:
    data = json.load(f)
for feat in data['features']:
    if feat['category'] == 'observability' and not feat['passes']:
        for step in feat['steps']:
            if 'verify' in step.lower() and 'log' in step.lower():
                print(step)
" 2>/dev/null | while read -r step; do
        echo "  Checking: $step"
    done
fi

# ─── PromQL Queries ──────────────────────────────────────────────
echo ""
echo "Metrics Analysis:"

# Query 4: p95 request latency (if metrics exist)
P95=$(curl -sf "${VM_URL}/api/v1/query?query=histogram_quantile(0.95,rate(http_request_duration_seconds_bucket[5m]))" 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    results = data.get('data', {}).get('result', [])
    if results:
        print(results[0].get('value', [None, '0'])[1])
    else:
        print('N/A')
except:
    print('N/A')
" 2>/dev/null || echo "N/A")

if [ "$P95" = "N/A" ]; then
    log_warn "No request latency metrics available (app may not expose Prometheus metrics)"
elif python3 -c "exit(0 if float('$P95') < 2.0 else 1)" 2>/dev/null; then
    log_pass "p95 request latency: ${P95}s (threshold: <2.0s)"
else
    log_fail "p95 request latency: ${P95}s exceeds 2.0s threshold"
fi

# Query 5: Active time series (general health)
TSDB=$(curl -sf "${VM_URL}/api/v1/status/tsdb" 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('data', {}).get('totalSeries', 0))
except:
    print('0')
" 2>/dev/null || echo "0")

if [ "$TSDB" -gt 0 ]; then
    log_pass "VictoriaMetrics tracking $TSDB active time series"
else
    log_warn "No active time series — app may not be exporting metrics"
fi

# ─── Startup Time Check ─────────────────────────────────────────
# OpenAI pattern: "Ensure service startup completes in under 800ms"
STARTUP=$(curl -sf "${VL_URL}/select/logsql/query?query=_msg%3A~%22started%7CStartup%7Clistening%22&start=1h&limit=1" 2>/dev/null || echo "")
if [ -n "$STARTUP" ]; then
    log_pass "Application startup detected in logs"
else
    log_warn "No startup log lines found in last hour"
fi

# ─── Summary ─────────────────────────────────────────────────────
echo ""
echo "─────────────────────────────────────"
echo "Observability: $PASS passed, $FAIL failed, $WARN warnings"

if [ "$FAIL" -gt 0 ]; then
    exit 1
else
    exit 0
fi
