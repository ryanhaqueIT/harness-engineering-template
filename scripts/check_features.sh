#!/usr/bin/env bash
# check_features.sh — Feature list gate (Layer 7)
# Verifies all features in .harness/feature_list.json pass.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ ! -f "${REPO_ROOT}/.harness/feature_list.json" ]; then
    echo "SKIP: No .harness/feature_list.json found"
    exit 0
fi

python3 "${REPO_ROOT}/scripts/check_features.py" "$@"
