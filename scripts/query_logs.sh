#!/usr/bin/env bash
# query_logs.sh — Query VictoriaLogs via LogsQL
# Usage: query_logs.sh "ERROR" [time_range] [limit]
#   query_logs.sh "ERROR" 5m 10
#   query_logs.sh "container_name:backend" 1h 50
set -euo pipefail

QUERY="${1:?Usage: query_logs.sh QUERY [TIME_RANGE] [LIMIT]}"
TIME="${2:-5m}"
LIMIT="${3:-20}"
VL_URL="${VICTORIALOGS_URL:-http://localhost:9428}"

ENCODED=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$QUERY'))")

curl -sf "${VL_URL}/select/logsql/query?query=${ENCODED}&start=${TIME}&limit=${LIMIT}" 2>/dev/null | python3 -c "
import sys
for line in sys.stdin:
    line = line.strip()
    if line:
        try:
            import json
            obj = json.loads(line)
            ts = obj.get('_time', '')
            msg = obj.get('_msg', obj.get('message', line))
            container = obj.get('container_name', '?')
            print(f'{ts} [{container}] {msg}')
        except:
            print(line)
" || echo "No results or VictoriaLogs not running at ${VL_URL}"
