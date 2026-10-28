#!/usr/bin/env bash
# A short usage report (last 7 and 30 days) from Log Analytics. Reads only; see docs/USAGE.md.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 deploy/usage_report.py "$@"
