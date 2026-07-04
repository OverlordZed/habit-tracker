#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTOSTART_DIR="$HOME/.config/autostart"
APPLICATIONS_DIR="$HOME/.local/share/applications"

chmod +x "$APP_DIR/launch.sh"
chmod +x "$APP_DIR/habit_tracker.py"

if ! python3 -m venv "$APP_DIR/.venv" 2>/dev/null; then
    python3 -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

mkdir -p "$AUTOSTART_DIR" "$APPLICATIONS_DIR"
cp "$APP_DIR/habit-tracker.desktop" "$AUTOSTART_DIR/habit-tracker.desktop"
cp "$APP_DIR/habit-tracker.desktop" "$APPLICATIONS_DIR/habit-tracker.desktop"

echo "Installed. Habit Tracker will start on login."
echo "Launch now: $APP_DIR/launch.sh"
