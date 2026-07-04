from datetime import date, datetime
from pathlib import Path

DEFAULT_WEEKLY_TARGET = 40
DEFAULT_MD_FILENAME = "Habit Tracker.md"


def hours_to_minutes(hours):
    return round(hours * 60)


def minutes_to_hours(minutes):
    return minutes / 60


def entries_equal(left, right):
    if set(left) != set(right):
        return False
    for key in left:
        if hours_to_minutes(left[key]) != hours_to_minutes(right.get(key, 0)):
            return False
    return True


def merge_entries(local, remote):
    merged = {}
    all_dates = set(local) | set(remote)
    for key in all_dates:
        total_minutes = 0
        if key in local:
            total_minutes += hours_to_minutes(local[key])
        if key in remote:
            total_minutes += hours_to_minutes(remote[key])
        if total_minutes > 0:
            merged[key] = minutes_to_hours(total_minutes)
    return merged


def _parse_frontmatter(lines):
    settings = {}
    if not lines or lines[0].strip() != "---":
        return settings, lines
    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break
    if end is None:
        return settings, lines
    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key == "weekly_target_hours":
            settings[key] = int(float(value))
        elif key == "last_updated":
            settings[key] = value
    return settings, lines[end + 1 :]


def _parse_table_row(line):
    line = line.strip()
    if not line.startswith("|"):
        return None
    parts = [part.strip() for part in line.strip("|").split("|")]
    if len(parts) < 2:
        return None
    if parts[0].lower() == "date" or set(parts[0]) == {"-"}:
        return None
    try:
        date.fromisoformat(parts[0])
        minutes = int(parts[1])
    except ValueError:
        return None
    return parts[0], minutes


def parse_md(path):
    text = Path(path).read_text()
    lines = text.splitlines()
    settings, body_lines = _parse_frontmatter(lines)
    settings.setdefault("weekly_target_hours", DEFAULT_WEEKLY_TARGET)

    entries = {}
    for line in body_lines:
        row = _parse_table_row(line)
        if row is None:
            continue
        day_key, minutes = row
        if minutes > 0:
            entries[day_key] = minutes_to_hours(minutes)
    return entries, settings


def write_md(path, entries, settings):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    weekly_target = settings.get("weekly_target_hours", DEFAULT_WEEKLY_TARGET)
    last_updated = datetime.now().replace(microsecond=0).isoformat()

    lines = [
        "---",
        f"weekly_target_hours: {weekly_target}",
        f"last_updated: {last_updated}",
        "---",
        "",
        "# Habit Tracker",
        "",
        "| Date | Minutes |",
        "|------|---------|",
    ]
    for day_key in sorted(entries):
        minutes = hours_to_minutes(entries[day_key])
        if minutes > 0:
            lines.append(f"| {day_key} | {minutes} |")
    lines.append("")

    path.write_text("\n".join(lines))
    return last_updated
