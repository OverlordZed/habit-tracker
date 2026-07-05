#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTOSTART_DIR="$HOME/.config/autostart"
APPLICATIONS_DIR="$HOME/.local/share/applications"
ICONS_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
DESKTOP_DIR="${XDG_DESKTOP_DIR:-$HOME/Desktop}"

chmod +x "$APP_DIR/launch.sh"
chmod +x "$APP_DIR/habit_tracker.py"

if [[ ! -d "$APP_DIR/.venv" ]]; then
    python3 -m venv "$APP_DIR/.venv"
    "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
fi

mkdir -p "$AUTOSTART_DIR" "$APPLICATIONS_DIR" "$ICONS_DIR" "$DESKTOP_DIR"
cp "$APP_DIR/habit-tracker.svg" "$ICONS_DIR/habit-tracker.svg"

DESKTOP_FILE="$APPLICATIONS_DIR/habit-tracker.desktop"
sed "s|APP_DIR|$APP_DIR|g" "$APP_DIR/habit-tracker.desktop" > "$DESKTOP_FILE"
chmod +x "$DESKTOP_FILE"

cp "$DESKTOP_FILE" "$DESKTOP_DIR/habit-tracker.desktop"
chmod +x "$DESKTOP_DIR/habit-tracker.desktop"
if command -v gio >/dev/null 2>&1; then
    gio set "$DESKTOP_DIR/habit-tracker.desktop" metadata::trusted true 2>/dev/null || true
fi

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPLICATIONS_DIR" 2>/dev/null || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

echo "Installed Habit Tracker."
echo "  Start menu: $DESKTOP_FILE"
echo "  Desktop:    $DESKTOP_DIR/habit-tracker.desktop"
echo "  Launch:     $APP_DIR/launch.sh"
