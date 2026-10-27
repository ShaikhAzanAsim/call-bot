#!/usr/bin/env bash
# Usage: ./scripts/smoke_test.sh https://your-host.example
set -euo pipefail
BASE="${1:-http://127.0.0.1:8000}"
python scripts/smoke_test.py "$BASE"
