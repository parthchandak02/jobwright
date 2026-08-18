#!/usr/bin/env bash
# Production deploy: build SPA + restart API + health check.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT/scripts/restart.sh" --prod-ui
