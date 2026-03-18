#!/usr/bin/env bash
# query_metrics.sh — Query VictoriaMetrics via PromQL
# Usage: query_metrics.sh "up"
#   query_metrics.sh "rate(http_requests_total[5m])"
#   query_metrics.sh "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))"
set -euo pipefail

QUERY="${1:?Usage: query_metrics.sh PROMQL_QUERY}"
VM_URL="${VICTORIAMETRICS_URL:-http://localhost:8428}"

ENCODED=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$QUERY'))")

curl -sf "${VM_URL}/api/v1/query?query=${ENCODED}" 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    status = data.get('status', 'error')
    if status != 'success':
        print(f'Query failed: {data.get(\"error\", \"unknown\")}')
        sys.exit(1)
    results = data.get('data', {}).get('result', [])
    if not results:
        print('No data')
    else:
        for r in results:
            metric = r.get('metric', {})
            value = r.get('value', [None, 'N/A'])[1]
            labels = ', '.join(f'{k}={v}' for k, v in metric.items())
            print(f'{labels or \"scalar\"}: {value}')
except Exception as e:
    print(f'Error: {e}')
" || echo "VictoriaMetrics not running at ${VM_URL}"
