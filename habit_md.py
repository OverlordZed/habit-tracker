from datetime import date, datetime
from pathlib import Path

DEFAULT_WEEKLY_TARGET = 40
DEFAULT_WEEKLY_GOAL = "Standards over everything"
DEFAULT_MARK_GREEN_LABEL = "Green"
DEFAULT_MARK_RED_LABEL = "Red"
DEFAULT_MD_FILENAME = "Habit Tracker.md"
TIME_FORMAT_MINUTES = "minutes"
TIME_FORMAT_CENTI_HOURS = "centi_hours"


def hours_to_minutes(hours):
    return round(hours * 60)


def minutes_to_hours(minutes):
    return minutes / 60


def now_timestamp():
    return datetime.now().astimezone().replace(microsecond=0)


def format_timestamp(dt):
    return dt.isoformat(timespec="seconds")


def parse_timestamp(value):
    cleaned = value.strip().strip('"').strip("'")
    if " " in cleaned and "T" not in cleaned:
        cleaned = cleaned.replace(" ", "T", 1)
    return datetime.fromisoformat(cleaned)


def display_timestamp(value):
    if not value:
        return ""
    try:
        dt = parse_timestamp(value).astimezone()
        tz = dt.strftime("%z")
        if tz:
            tz = f" UTC{tz[:3]}:{tz[3:]}"
        return dt.strftime("%d %b %Y %H:%M:%S") + tz
    except ValueError:
        return value


def _yaml_quoted(value):
    return '"' + str(value).replace('"', '\\"') + '"'


def _mark_label(settings, key, default):
    value = str(settings.get(key, default) or "").strip()
    return value or default


def normalise_entries(entries):
    packed = {}
    for key, value in entries.items():
        if isinstance(value, dict):
            hours = float(value.get("hours") or 0)
            green = bool(value.get("green"))
            red = bool(value.get("red"))
        else:
            hours = float(value or 0)
            green = False
            red = False
        if hours or green or red:
            packed[key] = {"hours": hours, "green": green, "red": red}
    return packed


def split_entries(entries):
    hours = {}
    marks = {}
    for key, item in normalise_entries(entries).items():
        if item["hours"]:
            hours[key] = item["hours"]
        if item["green"] or item["red"]:
            marks[key] = {"green": item["green"], "red": item["red"]}
    return hours, marks


def combine_entries(hours, marks):
    packed = {}
    for key in set(hours) | set(marks):
        amount = float(hours.get(key) or 0)
        mark = marks.get(key) or {}
        green = bool(mark.get("green"))
        red = bool(mark.get("red"))
        if amount or green or red:
            packed[key] = {"hours": amount, "green": green, "red": red}
    return packed


def entries_equal(left, right):
    left = normalise_entries(left)
    right = normalise_entries(right)
    if set(left) != set(right):
        return False
    for key in left:
        if hours_to_minutes(left[key]["hours"]) != hours_to_minutes(right[key]["hours"]):
            return False
        if left[key]["green"] != right[key]["green"] or left[key]["red"] != right[key]["red"]:
            return False
    return True


def settings_equal_for_md(left, right):
    if left.get("weekly_target_hours", DEFAULT_WEEKLY_TARGET) != right.get(
        "weekly_target_hours", DEFAULT_WEEKLY_TARGET
    ):
        return False
    if _mark_label(left, "mark_green_label", DEFAULT_MARK_GREEN_LABEL) != _mark_label(
        right, "mark_green_label", DEFAULT_MARK_GREEN_LABEL
    ):
        return False
    if _mark_label(left, "mark_red_label", DEFAULT_MARK_RED_LABEL) != _mark_label(
        right, "mark_red_label", DEFAULT_MARK_RED_LABEL
    ):
        return False
    return True


def md_unchanged(path, entries, settings):
    path = Path(path)
    if not path.exists():
        return False
    existing_entries, existing_settings = parse_md(path)
    return entries_equal(entries, existing_entries) and settings_equal_for_md(
        settings, existing_settings
    )


def merge_entries(local, remote):
    merged = normalise_entries(local)
    merged.update(normalise_entries(remote))
    return merged


def raw_value_to_hours(raw, time_format):
    if time_format == TIME_FORMAT_MINUTES:
        return minutes_to_hours(raw)
    return raw / 100


def _clean_yaml_value(value):
    return value.strip().strip('"').strip("'")


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
        value = _clean_yaml_value(value)
        if key == "weekly_target_hours":
            settings[key] = int(float(value))
        elif key == "time_format":
            settings[key] = value
        elif key in ("weekly_goal", "mark_green_label", "mark_red_label"):
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
    green = _parse_mark(parts[2]) if len(parts) > 2 else False
    red = _parse_mark(parts[3]) if len(parts) > 3 else False
    return parts[0], raw_value, green, red


def _parse_mark(value):
    return value.strip().lower() in {"1", "yes", "true", "x", "y"}


def _resolve_time_format(settings, raw_values):
    time_format = settings.get("time_format")
    if time_format in (TIME_FORMAT_MINUTES, TIME_FORMAT_CENTI_HOURS):
        return time_format
    if raw_values and max(raw_values) >= 1000:
        return TIME_FORMAT_CENTI_HOURS
    return TIME_FORMAT_MINUTES


def parse_md(path):
    text = Path(path).read_text()
    lines = text.splitlines()
    settings, body_lines = _parse_frontmatter(lines)
    settings.setdefault("weekly_target_hours", DEFAULT_WEEKLY_TARGET)
    settings.setdefault("mark_green_label", DEFAULT_MARK_GREEN_LABEL)
    settings.setdefault("mark_red_label", DEFAULT_MARK_RED_LABEL)

    rows = []
    for line in body_lines:
        row = _parse_table_row(line)
        if row is not None:
            rows.append(row)

    time_format = _resolve_time_format(settings, [raw for _, raw, _, _ in rows])
    settings["time_format"] = time_format

    entries = {}
    for day_key, raw_value, green, red in rows:
        hours = raw_value_to_hours(raw_value, time_format) if raw_value > 0 else 0
        if hours or green or red:
            entries[day_key] = {"hours": hours, "green": green, "red": red}
    return entries, settings


def write_md(path, entries, settings):
    path = Path(path)
    if md_unchanged(path, entries, settings):
        _, existing_settings = parse_md(path)
        return existing_settings.get("last_updated", "")

    path.parent.mkdir(parents=True, exist_ok=True)

    weekly_target = settings.get("weekly_target_hours", DEFAULT_WEEKLY_TARGET)
    weekly_goal = settings.get("weekly_goal", DEFAULT_WEEKLY_GOAL)
    green_label = _mark_label(settings, "mark_green_label", DEFAULT_MARK_GREEN_LABEL)
    red_label = _mark_label(settings, "mark_red_label", DEFAULT_MARK_RED_LABEL)
    last_updated = format_timestamp(now_timestamp())
    packed = normalise_entries(entries)

    lines = [
        "---",
        f"weekly_target_hours: {weekly_target}",
        f"weekly_goal: {_yaml_quoted(weekly_goal)}",
        f"mark_green_label: {_yaml_quoted(green_label)}",
        f"mark_red_label: {_yaml_quoted(red_label)}",
        f"time_format: {TIME_FORMAT_MINUTES}",
        f"last_updated: {_yaml_quoted(last_updated)}",
        "---",
        "",
        "# Habit Tracker",
        "",
        "| Date | Minutes | Green | Red |",
        "|------|---------|-------|-----|",
    ]
    for day_key in sorted(packed):
        item = packed[day_key]
        minutes = hours_to_minutes(item["hours"])
        if minutes > 0 or item["green"] or item["red"]:
            green = 1 if item["green"] else 0
            red = 1 if item["red"] else 0
            lines.append(f"| {day_key} | {minutes} | {green} | {red} |")
    lines.append("")

    path.write_text("\n".join(lines))
    return last_updated
