#!/usr/bin/env bash
# W14: build, check and compare the Fabric workload package (.nupkg) in one command; uploads nothing.
# Runs in Azure Cloud Shell after `git clone`; needs python3 and git (pytest for the manifest tests).
#   bash tools/workload-package.sh --frontend-app-id <Application (client) ID of the workload app> [--bump patch]
# docs/WORKLOAD-PACKAGE-UPDATES.md says how to run it and what to do with the file.
set -euo pipefail
exec python3 "$(dirname "$0")/workload_package.py" "$@"
