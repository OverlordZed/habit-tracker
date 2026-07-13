from datetime import date, datetime
from pathlib import Path

DEFAULT_WEEKLY_TARGET = 40
DEFAULT_WEEKLY_GOAL = "Standards over everything"
DEFAULT_MD_FILENAME = "Habit Tracker.md"
TIME_FORMAT_MINUTES = "minutes"
TIME_FORMAT_CENTI_HOURS = "centi_hours"


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
    merged = dict(local)
    merged.update(remote)
    return merged


def raw_value_to_hours(raw, time_format):
    if time_format == TIME_FORMAT_MINUTES:
        return minutes_to_hours(raw)
    return raw / 100


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
        elif key == "time_format":
            settings[key] = value
        elif key == "weekly_goal":
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            settings[key] = value
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
        raw_value = int(parts[1])
    except ValueError:
        return None
    return parts[0], raw_value


def _resolve_time_format(settings, raw_values):
    time_format = settings.get("time_format")
    if time_format in (TIME_FORMAT_MINUTES, TIME_FORMAT_CENTI_HOURS):
        return time_format
    if raw_values and max(raw_values) >= 1000:
        return TIME_FORMAT_CENTI_HOURS
    return TIME_FORMAT_CENTI_HOURS


def parse_md(path):
    text = Path(path).read_text()
    lines = text.splitlines()
    settings, body_lines = _parse_frontmatter(lines)
    settings.setdefault("weekly_target_hours", DEFAULT_WEEKLY_TARGET)

    rows = []
    for line in body_lines:
        row = _parse_table_row(line)
        if row is not None:
            rows.append(row)

    time_format = _resolve_time_format(settings, [raw for _, raw in rows])
    settings["time_format"] = time_format

    entries = {}
    for day_key, raw_value in rows:
        if raw_value > 0:
            entries[day_key] = raw_value_to_hours(raw_value, time_format)
    return entries, settings


def write_md(path, entries, settings):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    weekly_target = settings.get("weekly_target_hours", DEFAULT_WEEKLY_TARGET)
    weekly_goal = settings.get("weekly_goal", DEFAULT_WEEKLY_GOAL)
    last_updated = datetime.now().replace(microsecond=0).isoformat()

    lines = [
        "---",
        f"weekly_target_hours: {weekly_target}",
        f'weekly_goal: "{weekly_goal.replace(chr(34), chr(92) + chr(34))}"',
        f"time_format: {TIME_FORMAT_MINUTES}",
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
