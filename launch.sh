#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$APP_DIR/.venv"

if [[ ! -d "$VENV" ]]; then
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install -q -r "$APP_DIR/requirements.txt"
fi

exec "$VENV/bin/python" "$APP_DIR/habit_tracker.py"
