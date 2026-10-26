import re
from datetime import date, datetime, timedelta
from pathlib import Path

DEFAULT_WEEKLY_TARGET = 40
DEFAULT_WEEKLY_GOAL = "Standards over everything"
DEFAULT_MARK_GREEN_LABEL = "Green"
DEFAULT_MARK_RED_LABEL = "Red"
DEFAULT_MARK_GOLD_LABEL = "Gold"
DEFAULT_MD_FILENAME = "Habit Tracker.md"
TIME_FORMAT_MINUTES = "minutes"
TIME_FORMAT_CENTI_HOURS = "centi_hours"
WEEK_KEY_RE = re.compile(r"^(\d{4})-W(\d{2})$")
WEEK_HEADING_RE = re.compile(r"^###\s+(\d{4}-W\d{2})\b")


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


def iso_week_key(d):
    iso_year, iso_week, _ = d.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def iso_week_monday(key):
    match = WEEK_KEY_RE.match(str(key or ""))
    if not match:
        raise ValueError(key)
    return date.fromisocalendar(int(match.group(1)), int(match.group(2)), 1)


def iso_week_range_label(key):
    monday = iso_week_monday(key)
    sunday = monday + timedelta(days=6)
    return f"{monday.strftime('%d %b')} – {sunday.strftime('%d %b')}"


def monday_of(d):
    return d - timedelta(days=d.weekday())


def previous_iso_week_key(key):
    return iso_week_key(iso_week_monday(key) - timedelta(days=7))


def _valid_week_key(key):
    match = WEEK_KEY_RE.match(str(key or ""))
    if not match:
        return False
    try:
        date.fromisocalendar(int(match.group(1)), int(match.group(2)), 1)
    except ValueError:
        return False
    return True


def normalise_weekly_goals(goals):
    if not isinstance(goals, dict):
        return {}
    result = {}
    for key, items in goals.items():
        if not _valid_week_key(key):
            continue
        cleaned = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").replace("|", "/").strip()
            if not title:
                continue
            try:
                progress = int(round(float(item.get("progress") or 0)))
            except (TypeError, ValueError):
                progress = 0
            cleaned.append({"title": title, "progress": max(0, min(100, progress))})
        if cleaned:
            result[key] = cleaned
    return result


def merge_weekly_goals(local, remote):
    merged = normalise_weekly_goals(local)
    merged.update(normalise_weekly_goals(remote))
    return merged


def weekly_goals_for_financial_year(goals, fy_start, fy_end):
    result = {}
    for key, items in normalise_weekly_goals(goals).items():
        monday = iso_week_monday(key)
        if fy_start <= monday <= fy_end:
            result[key] = items
    return result


def weekly_goals_before_date(goals, cutoff):
    result = {}
    for key, items in normalise_weekly_goals(goals).items():
        if iso_week_monday(key) < cutoff:
            result[key] = items
    return result


def weekly_goals_on_or_after(goals, cutoff):
    result = {}
    for key, items in normalise_weekly_goals(goals).items():
        if iso_week_monday(key) >= cutoff:
            result[key] = items
    return result


def clamp_craving(value):
    try:
        return max(0, min(10, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0


def mark_fields(value=None):
    value = value or {}
    return {
        "green": bool(value.get("green")),
        "red": bool(value.get("red")),
        "gold": bool(value.get("gold")),
        "green_craving": clamp_craving(value.get("green_craving")),
        "red_craving": clamp_craving(value.get("red_craving")),
        "gold_craving": clamp_craving(value.get("gold_craving")),
    }


def has_mark_data(item):
    return (
        item.get("green")
        or item.get("red")
        or item.get("gold")
        or item.get("green_craving")
        or item.get("red_craving")
        or item.get("gold_craving")
    )


def normalise_entries(entries):
    packed = {}
    for key, value in entries.items():
        if isinstance(value, dict):
            hours = float(value.get("hours") or 0)
            marks = mark_fields(value)
        else:
            hours = float(value or 0)
            marks = mark_fields()
        if hours or has_mark_data(marks):
            packed[key] = {"hours": hours, **marks}
    return packed


def split_entries(entries):
    hours = {}
    marks = {}
    for key, item in normalise_entries(entries).items():
        if item["hours"]:
            hours[key] = item["hours"]
        if has_mark_data(item):
            marks[key] = mark_fields(item)
    return hours, marks


def combine_entries(hours, marks):
    packed = {}
    for key in set(hours) | set(marks):
        amount = float(hours.get(key) or 0)
        mark = mark_fields(marks.get(key))
        if amount or has_mark_data(mark):
            packed[key] = {"hours": amount, **mark}
    return packed


def entries_equal(left, right):
    left = normalise_entries(left)
    right = normalise_entries(right)
    if set(left) != set(right):
        return False
    for key in left:
        if hours_to_minutes(left[key]["hours"]) != hours_to_minutes(right[key]["hours"]):
            return False
        if (
            left[key]["green"] != right[key]["green"]
            or left[key]["red"] != right[key]["red"]
            or left[key]["gold"] != right[key]["gold"]
            or left[key]["green_craving"] != right[key]["green_craving"]
            or left[key]["red_craving"] != right[key]["red_craving"]
            or left[key]["gold_craving"] != right[key]["gold_craving"]
        ):
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
    if _mark_label(left, "mark_gold_label", DEFAULT_MARK_GOLD_LABEL) != _mark_label(
        right, "mark_gold_label", DEFAULT_MARK_GOLD_LABEL
    ):
        return False
    return normalise_weekly_goals(left.get("weekly_goals")) == normalise_weekly_goals(
        right.get("weekly_goals")
    )


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
        elif key in ("weekly_goal", "mark_green_label", "mark_red_label", "mark_gold_label"):
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            settings[key] = value
        elif key == "last_updated":
            settings[key] = value
    return settings, lines[end + 1 :]


def _split_hours_and_goals(body_lines):
    hours_lines = []
    goals_lines = []
    in_goals = False
    for line in body_lines:
        if line.strip().lower() == "## goals":
            in_goals = True
            continue
        if in_goals:
            goals_lines.append(line)
        else:
            hours_lines.append(line)
    return hours_lines, goals_lines


def _parse_goal_row(line):
    line = line.strip()
    if not line.startswith("|"):
        return None
    parts = [part.strip() for part in line.strip("|").split("|")]
    if len(parts) < 2:
        return None
    if parts[0].lower() in {"goal", "date"} or set(parts[0]) <= {"-"}:
        return None
    title = parts[0].replace("|", "/").strip()
    if not title:
        return None
    try:
        progress = int(round(float(str(parts[1]).rstrip("%"))))
    except ValueError:
        return None
    return title, max(0, min(100, progress))


def parse_weekly_goals(body_lines):
    _, goals_lines = _split_hours_and_goals(body_lines)
    goals = {}
    current = None
    for line in goals_lines:
        heading = WEEK_HEADING_RE.match(line.strip())
        if heading:
            current = heading.group(1)
            goals.setdefault(current, [])
            continue
        if current is None:
            continue
        row = _parse_goal_row(line)
        if row is not None:
            title, progress = row
            goals[current].append({"title": title, "progress": progress})
    return normalise_weekly_goals(goals)


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
    gold = _parse_mark(parts[4]) if len(parts) > 4 else False
    green_craving = _parse_craving(parts[5]) if len(parts) > 5 else 0
    red_craving = _parse_craving(parts[6]) if len(parts) > 6 else 0
    gold_craving = _parse_craving(parts[7]) if len(parts) > 7 else 0
    return (
        parts[0],
        raw_value,
        green,
        red,
        gold,
        green_craving,
        red_craving,
        gold_craving,
    )


def _parse_mark(value):
    return value.strip().lower() in {"1", "yes", "true", "x", "y"}


def _parse_craving(value):
    text = str(value).strip()
    if "/" in text:
        text = text.split("/", 1)[0]
    return clamp_craving(text)


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
    settings.setdefault("mark_gold_label", DEFAULT_MARK_GOLD_LABEL)
    settings["weekly_goals"] = parse_weekly_goals(body_lines)

    hours_lines, _ = _split_hours_and_goals(body_lines)
    rows = []
    for line in hours_lines:
        row = _parse_table_row(line)
        if row is not None:
            rows.append(row)

    time_format = _resolve_time_format(
        settings, [raw for _, raw, _, _, _, _, _, _ in rows]
    )
    settings["time_format"] = time_format

    entries = {}
    for (
        day_key,
        raw_value,
        green,
        red,
        gold,
        green_craving,
        red_craving,
        gold_craving,
    ) in rows:
        hours = raw_value_to_hours(raw_value, time_format) if raw_value > 0 else 0
        item = {
            "hours": hours,
            "green": green,
            "red": red,
            "gold": gold,
            "green_craving": green_craving,
            "red_craving": red_craving,
            "gold_craving": gold_craving,
        }
        if hours or has_mark_data(item):
            entries[day_key] = item
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
    gold_label = _mark_label(settings, "mark_gold_label", DEFAULT_MARK_GOLD_LABEL)
    last_updated = format_timestamp(now_timestamp())
    packed = normalise_entries(entries)
    weekly_goals = normalise_weekly_goals(settings.get("weekly_goals"))

    lines = [
        "---",
        f"weekly_target_hours: {weekly_target}",
        f"weekly_goal: {_yaml_quoted(weekly_goal)}",
        f"mark_green_label: {_yaml_quoted(green_label)}",
        f"mark_red_label: {_yaml_quoted(red_label)}",
        f"mark_gold_label: {_yaml_quoted(gold_label)}",
        f"time_format: {TIME_FORMAT_MINUTES}",
        f"last_updated: {_yaml_quoted(last_updated)}",
        "---",
        "",
        "# Habit Tracker",
        "",
        "| Date | Minutes | Green | Red | Gold | Green craving | Red craving | Gold craving |",
        "|------|---------|-------|-----|------|---------------|-------------|--------------|",
    ]
    for day_key in sorted(packed):
        item = packed[day_key]
        minutes = hours_to_minutes(item["hours"])
        if minutes > 0 or has_mark_data(item):
            green = 1 if item["green"] else 0
            red = 1 if item["red"] else 0
            gold = 1 if item["gold"] else 0
            lines.append(
                f"| {day_key} | {minutes} | {green} | {red} | {gold} | "
                f"{item['green_craving']} | {item['red_craving']} | {item['gold_craving']} |"
            )
    lines.append("")

    if weekly_goals:
        lines.append("## Goals")
        lines.append("")
        for week_key in sorted(weekly_goals):
            lines.append(f"### {week_key} ({iso_week_range_label(week_key)})")
            lines.append("")
            lines.append("| Goal | Progress |")
            lines.append("|------|----------|")
            for item in weekly_goals[week_key]:
                lines.append(f"| {item['title']} | {item['progress']} |")
            lines.append("")

    path.write_text("\n".join(lines))
    return last_updated
