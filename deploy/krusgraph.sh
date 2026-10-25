#!/usr/bin/env bash
# Reuse the existing app. The helper reads the secret without echoing it.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 deploy/azure_containerapp.py "$@"
