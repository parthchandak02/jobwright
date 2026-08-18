#!/usr/bin/env bash
# Alias for scripts/restart.sh (litreview-style name).
exec "$(cd "$(dirname "$0")" && pwd)/restart.sh" "$@"
