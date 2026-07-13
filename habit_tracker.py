#!/usr/bin/env python3

import calendar
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from habit_md import (
    DEFAULT_MD_FILENAME,
    DEFAULT_WEEKLY_GOAL,
    display_timestamp,
    entries_equal,
    merge_entries,
    parse_md,
    write_md,
)

DATA_DIR = Path.home() / ".local" / "share" / "habit-tracker"
DATA_FILE = DATA_DIR / "entries.json"
TIMER_FILE = DATA_DIR / "timer.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
CONFIG_FILE = DATA_DIR / "config.json"
ARCHIVES_DIR = DATA_DIR / "archives"
DEFAULT_WEEKLY_TARGET = 40
FINANCIAL_YEAR_START_MONTH = 7
FINANCIAL_YEAR_START_DAY = 1

BG = "#1e1e2e"
SURFACE = "#313244"
SURFACE_ALT = "#45475a"
SURFACE_ACTIVE = "#585b70"
TEXT = "#cdd6f4"
TEXT_DIM = "#6c7086"
TEXT_MUTED = "#a6adc8"
ACCENT = "#89b4fa"
EXPECTED = "#f9e2af"
TIMER_RUNNING = "#a6e3a1"
TIMER_STOP = "#f38ba8"


def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            config = json.load(f)
    else:
        config = {}
    config.setdefault("vault_path", "")
    config.setdefault("md_filename", DEFAULT_MD_FILENAME)
    config.setdefault("last_synced", "")
    return config


def save_config(config):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get_md_path(config):
    vault_path = config.get("vault_path", "").strip()
    if not vault_path:
        return None
    return Path(vault_path) / config.get("md_filename", DEFAULT_MD_FILENAME)


def load_entries_json():
    if DATA_FILE.exists():
        with open(DATA_FILE) as f:
            return json.load(f)
    return {}


def save_entries_json(entries):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(entries, f, indent=2)


def load_legacy_settings():
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE) as f:
            settings = json.load(f)
    else:
        settings = {}
    settings.setdefault("weekly_target_hours", DEFAULT_WEEKLY_TARGET)
    settings.setdefault("weekly_goal", DEFAULT_WEEKLY_GOAL)
    return settings


def load_entries(config=None):
    config = config or load_config()
    md_path = get_md_path(config)
    if md_path and md_path.exists():
        entries, _ = parse_md(md_path)
        return entries
    return load_entries_json()


def load_settings(config=None):
    config = config or load_config()
    settings = {"weekly_target_hours": DEFAULT_WEEKLY_TARGET}
    md_path = get_md_path(config)
    if md_path and md_path.exists():
        _, md_settings = parse_md(md_path)
        settings.update(md_settings)
    else:
        settings.update(load_legacy_settings())
    settings.setdefault("weekly_target_hours", DEFAULT_WEEKLY_TARGET)
    settings.setdefault("weekly_goal", DEFAULT_WEEKLY_GOAL)
    return settings


def persist_data(entries, settings, config=None):
    config = config or load_config()
    save_entries_json(entries)
    md_path = get_md_path(config)
    if md_path:
        last_synced = write_md(md_path, entries, settings)
        config["last_synced"] = last_synced
        save_config(config)
        return last_synced
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(
            {
                "weekly_target_hours": settings["weekly_target_hours"],
                "weekly_goal": settings.get("weekly_goal", DEFAULT_WEEKLY_GOAL),
            },
            f,
            indent=2,
        )
    return ""


def startup_sync(config):
    local_entries = load_entries_json()
    md_path = get_md_path(config)
    last_synced = config.get("last_synced", "")

    if not config.get("vault_path", "").strip():
        return local_entries, load_settings(config), last_synced

    settings = load_legacy_settings()
    if md_path and md_path.exists():
        remote_entries, remote_settings = parse_md(md_path)
        settings.update(remote_settings)
        if entries_equal(local_entries, remote_entries):
            merged = remote_entries
        else:
            merged = merge_entries(local_entries, remote_entries)
        last_synced = write_md(md_path, merged, settings)
        save_entries_json(merged)
        config["last_synced"] = last_synced
        save_config(config)
        return merged, settings, last_synced

    if local_entries:
        last_synced = write_md(md_path, local_entries, settings)
        save_entries_json(local_entries)
        config["last_synced"] = last_synced
        save_config(config)
        return local_entries, settings, last_synced

    last_synced = write_md(md_path, {}, settings)
    config["last_synced"] = last_synced
    save_config(config)
    return {}, settings, last_synced


def save_entries(entries):
    persist_data(entries, load_settings())


def save_settings(settings):
    persist_data(load_entries(), settings)


def date_key(d):
    return d.isoformat()


def financial_year_start(d):
    if d.month >= FINANCIAL_YEAR_START_MONTH:
        return date(d.year, FINANCIAL_YEAR_START_MONTH, FINANCIAL_YEAR_START_DAY)
    return date(d.year - 1, FINANCIAL_YEAR_START_MONTH, FINANCIAL_YEAR_START_DAY)


def financial_year_end(fy_start):
    return date(fy_start.year + 1, FINANCIAL_YEAR_START_MONTH, FINANCIAL_YEAR_START_DAY) - timedelta(
        days=1
    )


def financial_year_label(fy_start):
    return f"{fy_start.year}-{str(fy_start.year + 1)[-2:]}"


def entries_for_financial_year(entries, fy_start):
    fy_end = financial_year_end(fy_start)
    result = {}
    for key, hours in entries.items():
        d = date.fromisoformat(key)
        if fy_start <= d <= fy_end:
            result[key] = hours
    return result


def entries_before_date(entries, cutoff):
    result = {}
    for key, hours in entries.items():
        if date.fromisoformat(key) < cutoff:
            result[key] = hours
    return result


def archive_financial_year(entries, settings, fy_start):
    ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)
    label = financial_year_label(fy_start)
    fy_entries = entries_for_financial_year(entries, fy_start)
    payload = {
        "financial_year": label,
        "period_start": fy_start.isoformat(),
        "period_end": financial_year_end(fy_start).isoformat(),
        "archived_at": datetime.now().replace(microsecond=0).isoformat(),
        "settings": settings,
        "entries": fy_entries,
    }
    json_path = ARCHIVES_DIR / f"fy-{label}.json"
    with open(json_path, "w") as f:
        json.dump(payload, f, indent=2)
    md_path = ARCHIVES_DIR / f"fy-{label}.md"
    write_md(md_path, fy_entries, settings)
    return json_path, md_path


def load_timer_state():
    if TIMER_FILE.exists():
        with open(TIMER_FILE) as f:
            data = json.load(f)
        started_at = datetime.fromisoformat(data["started_at"])
        day = date.fromisoformat(data["day"])
        return started_at, day
    return None, None


def save_timer_state(started_at, day):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(TIMER_FILE, "w") as f:
        json.dump(
            {"started_at": started_at.isoformat(), "day": date_key(day)},
            f,
            indent=2,
        )


def clear_timer_state():
    if TIMER_FILE.exists():
        TIMER_FILE.unlink()


def format_elapsed(seconds):
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def seconds_to_hours(seconds):
    if seconds <= 0:
        return 0
    minutes = round(seconds / 60)
    if minutes == 0:
        minutes = 1
    return minutes / 60


def format_duration(hours):
    total_minutes = round(hours * 60)
    h, m = divmod(total_minutes, 60)
    if h and m:
        return f"{h}h {m}m"
    if h:
        return f"{h}h"
    return f"{m}m"


def add_hours(existing, added):
    total_minutes = round(existing * 60) + round(added * 60)
    return total_minutes / 60


def hours_to_minutes(hours):
    return round(hours * 60)


def year_to_date_total(entries, year):
    total_minutes = 0
    for key, hours in entries.items():
        d = date.fromisoformat(key)
        if d.year == year:
            total_minutes += hours_to_minutes(hours)
    return total_minutes / 60


def total_for_month(entries, year, month):
    total_minutes = 0
    for key, hours in entries.items():
        d = date.fromisoformat(key)
        if d.year == year and d.month == month:
            total_minutes += hours_to_minutes(hours)
    return total_minutes / 60


def total_for_iso_week(entries, day):
    iso_year, iso_week, _ = day.isocalendar()
    total_minutes = 0
    for key, hours in entries.items():
        d = date.fromisoformat(key)
        d_iso_year, d_iso_week, _ = d.isocalendar()
        if d_iso_year == iso_year and d_iso_week == iso_week:
            total_minutes += hours_to_minutes(hours)
    return total_minutes / 60


def aggregate_by_month(entries, year):
    months = {}
    for key, hours in entries.items():
        d = date.fromisoformat(key)
        if d.year != year:
            continue
        months[d.month] = months.get(d.month, 0) + hours_to_minutes(hours)
    return [
        (
            datetime(year, month_num, 1).strftime("%b"),
            months[month_num] / 60,
            month_num,
        )
        for month_num in sorted(months)
    ]


def aggregate_by_week(entries, year):
    weeks = {}
    week_starts = {}
    for key, hours in entries.items():
        d = date.fromisoformat(key)
        if d.year != year:
            continue
        _, iso_week, _ = d.isocalendar()
        weeks[iso_week] = weeks.get(iso_week, 0) + hours_to_minutes(hours)
        if iso_week not in week_starts or d < week_starts[iso_week]:
            week_starts[iso_week] = d
    result = []
    for week_num in sorted(weeks):
        monday = week_starts[week_num] - timedelta(days=week_starts[week_num].weekday())
        label = f"W{week_num}\n{monday.strftime('%d %b')}"
        result.append((label, weeks[week_num] / 60))
    return result


def iso_weeks_in_month(year, month):
    _, days_in_month = calendar.monthrange(year, month)
    weeks = set()
    for day in range(1, days_in_month + 1):
        weeks.add(date(year, month, day).isocalendar()[:2])
    return len(weeks)


def iso_weeks_so_far_in_year(year, up_to):
    weeks = set()
    d = date(year, 1, 1)
    while d <= up_to:
        if d.year == year:
            weeks.add(d.isocalendar()[:2])
        d += timedelta(days=1)
    return len(weeks)


class HoursDialog(QDialog):
    def __init__(self, day_date, current_hours, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hours worked")
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(f"{day_date.strftime('%A %d %B %Y')}\n\nEnter time worked:")
        )

        time_row = QHBoxLayout()
        self.hours_spin = QSpinBox()
        self.hours_spin.setRange(0, 24)
        self.hours_spin.setSuffix(" h")
        time_row.addWidget(self.hours_spin)

        self.minutes_spin = QSpinBox()
        self.minutes_spin.setRange(0, 59)
        self.minutes_spin.setSuffix(" m")
        self.minutes_spin.setSingleStep(1)
        time_row.addWidget(self.minutes_spin)
        layout.addLayout(time_row)

        if current_hours is not None:
            total_minutes = round(float(current_hours) * 60)
            h, m = divmod(total_minutes, 60)
            self.hours_spin.setValue(h)
            self.minutes_spin.setValue(m)

        buttons = QDialogButtonBox()
        clear_btn = buttons.addButton("Clear", QDialogButtonBox.DestructiveRole)
        cancel_btn = buttons.addButton(QDialogButtonBox.Cancel)
        save_btn = buttons.addButton(QDialogButtonBox.Save)
        clear_btn.clicked.connect(self._clear)
        cancel_btn.clicked.connect(self.reject)
        save_btn.clicked.connect(self.accept)
        layout.addWidget(buttons)

        self.cleared = False

    def _clear(self):
        self.cleared = True
        self.accept()

    def result_hours(self):
        if self.cleared:
            return None
        total_minutes = self.hours_spin.value() * 60 + self.minutes_spin.value()
        return total_minutes / 60


class ResetFinancialYearDialog(QDialog):
    def __init__(self, previous_fy_label, current_fy_label, previous_entry_count, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reset for new financial year")
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                f"This will clear all habit data before the start of FY {current_fy_label} "
                f"(1 July {current_fy_label[:4]}).\n\n"
                f"Use this when starting a new financial year. "
                f"This cannot be undone unless you archive first."
            )
        )

        if previous_entry_count:
            archive_text = (
                f"Archive last financial year's data (FY {previous_fy_label}, "
                f"{previous_entry_count} {'entry' if previous_entry_count == 1 else 'entries'})"
            )
        else:
            archive_text = (
                f"Archive last financial year's data (FY {previous_fy_label}, no entries)"
            )

        self.archive_checkbox = QCheckBox(archive_text)
        self.archive_checkbox.setChecked(True)
        layout.addWidget(self.archive_checkbox)

        buttons = QDialogButtonBox()
        reset_btn = buttons.addButton("Reset data", QDialogButtonBox.DestructiveRole)
        cancel_btn = buttons.addButton(QDialogButtonBox.Cancel)
        reset_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def archive_previous_year(self):
        return self.archive_checkbox.isChecked()


class DayButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.day_date = None
        self.setMinimumSize(72, 56)
        self.setFont(QFont("Sans", 10))
        self.setCursor(Qt.PointingHandCursor)


class HabitTracker(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Habit Tracker")
        self.resize(720, 680)
        self.setMinimumSize(600, 560)

        self.config = load_config()
        self.entries, self.settings, self.last_synced = startup_sync(self.config)
        today = date.today()
        self.view_year = today.year
        self.view_month = today.month
        self.selected_date = today
        self.day_buttons = []
        self.timer_started_at = None
        self.timer_day = None
        self.plot_scope = "week"

        self.tick_timer = QTimer(self)
        self.tick_timer.setInterval(1000)
        self.tick_timer.timeout.connect(self._tick_timer)

        self._build_ui()
        self._restore_timer_state()
        self._refresh_calendar()
        self._refresh_plot()
        self._refresh_stats()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        central.setStyleSheet(f"background-color: {BG}; color: {TEXT};")

        root = QVBoxLayout(central)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(8)

        self.goal_banner = QWidget()
        self.goal_banner.setObjectName("goal-banner")
        banner_layout = QVBoxLayout(self.goal_banner)
        banner_layout.setContentsMargins(14, 10, 14, 10)
        banner_layout.setSpacing(4)

        goal_caption = QLabel("Weekly goal")
        goal_caption.setAlignment(Qt.AlignCenter)
        goal_caption.setObjectName("goal-caption")
        banner_layout.addWidget(goal_caption)

        self.weekly_goal_input = QLineEdit()
        self.weekly_goal_input.setObjectName("goal-input")
        self.weekly_goal_input.setAlignment(Qt.AlignCenter)
        self.weekly_goal_input.setFont(QFont("Sans", 14, QFont.Bold))
        self.weekly_goal_input.setPlaceholderText(DEFAULT_WEEKLY_GOAL)
        self.weekly_goal_input.setText(self.settings.get("weekly_goal", DEFAULT_WEEKLY_GOAL))
        self.weekly_goal_input.editingFinished.connect(self._on_weekly_goal_changed)
        banner_layout.addWidget(self.weekly_goal_input)
        root.addWidget(self.goal_banner)

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self.tabs)

        calendar_tab = QWidget()
        calendar_layout = QVBoxLayout(calendar_tab)
        calendar_layout.setContentsMargins(0, 0, 0, 0)
        calendar_layout.setSpacing(8)

        header = QHBoxLayout()
        prev_btn = QPushButton("◀")
        prev_btn.setFixedWidth(40)
        prev_btn.clicked.connect(self._prev_month)
        header.addWidget(prev_btn)

        self.month_label = QLabel()
        self.month_label.setAlignment(Qt.AlignCenter)
        self.month_label.setFont(QFont("Sans", 16, QFont.Bold))
        header.addWidget(self.month_label, stretch=1)

        today_btn = QPushButton("Today")
        today_btn.clicked.connect(self._go_today)
        header.addWidget(today_btn)

        next_btn = QPushButton("▶")
        next_btn.setFixedWidth(40)
        next_btn.clicked.connect(self._next_month)
        header.addWidget(next_btn)
        calendar_layout.addLayout(header)

        weekday_row = QHBoxLayout()
        for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
            label = QLabel(day)
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet(f"color: {TEXT_DIM};")
            weekday_row.addWidget(label, stretch=1)
        calendar_layout.addLayout(weekday_row)

        grid = QGridLayout()
        grid.setSpacing(4)
        for r in range(6):
            row_buttons = []
            for c in range(7):
                btn = DayButton()
                btn.clicked.connect(lambda checked=False, b=btn: self._on_day_click(b))
                grid.addWidget(btn, r, c)
                row_buttons.append(btn)
            self.day_buttons.append(row_buttons)
        calendar_layout.addLayout(grid)

        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(f"color: {TEXT_MUTED};")
        calendar_layout.addWidget(self.status_label)

        timer_row = QHBoxLayout()
        timer_row.setSpacing(8)

        self.timer_label = QLabel("00:00:00")
        self.timer_label.setAlignment(Qt.AlignCenter)
        self.timer_label.setFont(QFont("Monospace", 18, QFont.Bold))
        self.timer_label.setStyleSheet(f"color: {TEXT_MUTED};")
        timer_row.addWidget(self.timer_label, stretch=1)

        self.start_timer_btn = QPushButton("Start timer")
        self.start_timer_btn.clicked.connect(self._start_timer)
        timer_row.addWidget(self.start_timer_btn)

        self.stop_timer_btn = QPushButton("Stop timer")
        self.stop_timer_btn.clicked.connect(self._stop_timer)
        self.stop_timer_btn.setEnabled(False)
        timer_row.addWidget(self.stop_timer_btn)

        calendar_layout.addLayout(timer_row)

        self.plot_tabs = QTabWidget()
        self.plot_tabs.addTab(QWidget(), "Week")
        self.plot_tabs.addTab(QWidget(), "Year to date")
        self.plot_tabs.addTab(QWidget(), "Month")
        self.plot_tabs.setCurrentIndex(0)
        self.plot_tabs.currentChanged.connect(self._on_plot_tab_changed)
        calendar_layout.addWidget(self.plot_tabs)

        self.figure = Figure(figsize=(6, 2.4), dpi=100, facecolor=BG)
        gs = GridSpec(1, 2, figure=self.figure, width_ratios=[4, 1], wspace=0.3)
        self.ax = self.figure.add_subplot(gs[0])
        self.compare_ax = self.figure.add_subplot(gs[1])
        self.canvas = FigureCanvasQTAgg(self.figure)
        calendar_layout.addWidget(self.canvas, stretch=1)

        self.tabs.addTab(calendar_tab, "Calendar")

        stats_tab = QWidget()
        stats_layout = QVBoxLayout(stats_tab)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(8)

        summary_row = QHBoxLayout()
        self.ytd_label = QLabel()
        self.ytd_label.setAlignment(Qt.AlignCenter)
        self.month_total_label = QLabel()
        self.month_total_label.setAlignment(Qt.AlignCenter)
        self.week_total_label = QLabel()
        self.week_total_label.setAlignment(Qt.AlignCenter)
        for label in (self.ytd_label, self.month_total_label, self.week_total_label):
            label.setStyleSheet(f"color: {TEXT_MUTED};")
            summary_row.addWidget(label, stretch=1)
        stats_layout.addLayout(summary_row)

        target_row = QHBoxLayout()
        target_label = QLabel("Weekly target:")
        target_label.setStyleSheet(f"color: {TEXT_MUTED};")
        target_row.addWidget(target_label)
        self.weekly_target_spin = QSpinBox()
        self.weekly_target_spin.setRange(1, 80)
        self.weekly_target_spin.setSuffix(" h")
        self.weekly_target_spin.setValue(self.settings["weekly_target_hours"])
        self.weekly_target_spin.valueChanged.connect(self._on_weekly_target_changed)
        target_row.addWidget(self.weekly_target_spin)
        target_row.addStretch()
        stats_layout.addLayout(target_row)

        sync_label = QLabel("Obsidian vault sync")
        sync_label.setStyleSheet(f"color: {TEXT_MUTED}; font-weight: bold;")
        stats_layout.addWidget(sync_label)

        vault_row = QHBoxLayout()
        vault_row.addWidget(QLabel("Vault path:"))
        self.vault_path_input = QLineEdit()
        self.vault_path_input.setPlaceholderText("/path/to/your/vault")
        self.vault_path_input.setText(self.config.get("vault_path", ""))
        self.vault_path_input.editingFinished.connect(self._on_vault_path_changed)
        vault_row.addWidget(self.vault_path_input, stretch=1)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._browse_vault)
        vault_row.addWidget(browse_btn)
        stats_layout.addLayout(vault_row)

        sync_btn_row = QHBoxLayout()
        import_btn = QPushButton("Import now")
        import_btn.clicked.connect(self._import_now)
        sync_btn_row.addWidget(import_btn)
        export_btn = QPushButton("Export now")
        export_btn.clicked.connect(self._export_now)
        sync_btn_row.addWidget(export_btn)
        sync_btn_row.addStretch()
        stats_layout.addLayout(sync_btn_row)

        self.sync_status_label = QLabel()
        self.sync_status_label.setStyleSheet(f"color: {TEXT_DIM};")
        stats_layout.addWidget(self.sync_status_label)
        self._update_sync_status()

        fy_label = QLabel("Financial year")
        fy_label.setStyleSheet(f"color: {TEXT_MUTED}; font-weight: bold;")
        stats_layout.addWidget(fy_label)

        self.fy_status_label = QLabel()
        self.fy_status_label.setStyleSheet(f"color: {TEXT_DIM};")
        stats_layout.addWidget(self.fy_status_label)
        self._update_financial_year_status()

        reset_fy_row = QHBoxLayout()
        self.reset_fy_btn = QPushButton("Reset for new financial year")
        self.reset_fy_btn.clicked.connect(self._reset_financial_year)
        reset_fy_row.addWidget(self.reset_fy_btn)
        reset_fy_row.addStretch()
        stats_layout.addLayout(reset_fy_row)

        self.month_figure = Figure(figsize=(6, 2.2), dpi=100, facecolor=BG)
        self.month_ax = self.month_figure.add_subplot(111)
        self.month_canvas = FigureCanvasQTAgg(self.month_figure)
        stats_layout.addWidget(self.month_canvas, stretch=1)

        self.week_figure = Figure(figsize=(6, 2.2), dpi=100, facecolor=BG)
        self.week_ax = self.week_figure.add_subplot(111)
        self.week_canvas = FigureCanvasQTAgg(self.week_figure)
        stats_layout.addWidget(self.week_canvas, stretch=1)

        self.tabs.addTab(stats_tab, "Stats")

        self.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {SURFACE};
                color: {TEXT};
                border: none;
                border-radius: 6px;
                padding: 8px 12px;
            }}
            QPushButton:hover {{
                background-color: {SURFACE_ALT};
            }}
            QPushButton#today {{
                background-color: {ACCENT};
                color: {BG};
                font-weight: bold;
            }}
            QPushButton#start-timer {{
                background-color: {TIMER_RUNNING};
                color: {BG};
                font-weight: bold;
            }}
            QPushButton#stop-timer {{
                background-color: {TIMER_STOP};
                color: {BG};
                font-weight: bold;
            }}
            QPushButton#reset-fy {{
                background-color: {TIMER_STOP};
                color: {BG};
                font-weight: bold;
            }}
            QLabel {{
                color: {TEXT};
            }}
            QSpinBox {{
                background-color: {SURFACE};
                color: {TEXT};
                border: 1px solid {SURFACE_ALT};
                padding: 6px;
            }}
            QLineEdit {{
                background-color: {SURFACE};
                color: {TEXT};
                border: 1px solid {SURFACE_ALT};
                padding: 6px;
                border-radius: 4px;
            }}
            QWidget#goal-banner {{
                background-color: {SURFACE_ALT};
                border: 1px solid {ACCENT};
                border-radius: 8px;
            }}
            QLabel#goal-caption {{
                color: {TEXT_DIM};
                font-size: 11px;
            }}
            QLineEdit#goal-input {{
                background-color: transparent;
                border: none;
                color: {TEXT};
                padding: 2px 4px;
            }}
            QTabWidget::pane {{
                border: none;
                background-color: {BG};
            }}
            QTabBar::tab {{
                background-color: {SURFACE};
                color: {TEXT_MUTED};
                padding: 8px 16px;
                border: none;
                margin-right: 4px;
            }}
            QTabBar::tab:selected {{
                background-color: {SURFACE_ALT};
                color: {TEXT};
            }}
            QTabWidget#plot-tabs::pane {{
                border: none;
                padding: 0;
                margin: 0;
            }}
            QTabWidget#plot-tabs QWidget {{
                max-height: 0;
            }}
            """
        )
        self.plot_tabs.setObjectName("plot-tabs")
        today_btn.setObjectName("today")
        self.start_timer_btn.setObjectName("start-timer")
        self.stop_timer_btn.setObjectName("stop-timer")
        self.reset_fy_btn.setObjectName("reset-fy")

    def _update_financial_year_status(self):
        today = date.today()
        current_fy_start = financial_year_start(today)
        current_fy_label = financial_year_label(current_fy_start)
        previous_fy_start = date(current_fy_start.year - 1, FINANCIAL_YEAR_START_MONTH, FINANCIAL_YEAR_START_DAY)
        previous_entries = entries_for_financial_year(self.entries, previous_fy_start)
        current_entries = entries_for_financial_year(self.entries, current_fy_start)
        self.fy_status_label.setText(
            f"Current FY {current_fy_label}: {len(current_entries)} "
            f"{'entry' if len(current_entries) == 1 else 'entries'}  |  "
            f"Previous FY {financial_year_label(previous_fy_start)}: {len(previous_entries)} "
            f"{'entry' if len(previous_entries) == 1 else 'entries'}"
        )

    def _reset_financial_year(self):
        today = date.today()
        current_fy_start = financial_year_start(today)
        current_fy_label = financial_year_label(current_fy_start)
        previous_fy_start = date(
            current_fy_start.year - 1, FINANCIAL_YEAR_START_MONTH, FINANCIAL_YEAR_START_DAY
        )
        previous_fy_label = financial_year_label(previous_fy_start)
        previous_entries = entries_for_financial_year(self.entries, previous_fy_start)
        entries_to_clear = entries_before_date(self.entries, current_fy_start)

        if not entries_to_clear:
            QMessageBox.information(
                self,
                "Nothing to reset",
                f"There is no data before the start of FY {current_fy_label}.",
            )
            return

        dialog = ResetFinancialYearDialog(
            previous_fy_label,
            current_fy_label,
            len(previous_entries),
            self,
        )
        if dialog.exec() != QDialog.Accepted:
            return

        if self.timer_started_at is not None:
            self._stop_timer()

        archive_paths = None
        if dialog.archive_previous_year():
            archive_paths = archive_financial_year(
                self.entries, self.settings, previous_fy_start
            )

        self.entries = {
            key: hours
            for key, hours in self.entries.items()
            if date.fromisoformat(key) >= current_fy_start
        }
        self._persist_data()
        self._refresh_calendar()
        self._refresh_plot()
        self._refresh_stats()
        self._update_financial_year_status()

        cleared_count = len(entries_to_clear)
        message = (
            f"Cleared {cleared_count} "
            f"{'entry' if cleared_count == 1 else 'entries'} before FY {current_fy_label}."
        )
        if archive_paths:
            message += (
                f"\n\nArchived FY {previous_fy_label} to:\n"
                f"{archive_paths[0]}\n{archive_paths[1]}"
            )
        QMessageBox.information(self, "Financial year reset", message)

    def _restore_timer_state(self):
        started_at, day = load_timer_state()
        if started_at is None:
            self._update_timer_ui()
            return

        self.timer_started_at = started_at
        self.timer_day = day
        self.tick_timer.start()
        self._update_timer_ui()

    def _elapsed_seconds(self):
        if self.timer_started_at is None:
            return 0
        return (datetime.now() - self.timer_started_at).total_seconds()

    def _update_timer_ui(self):
        running = self.timer_started_at is not None
        self.start_timer_btn.setEnabled(not running)
        self.stop_timer_btn.setEnabled(running)

        if running:
            self.timer_label.setText(format_elapsed(self._elapsed_seconds()))
            self.timer_label.setStyleSheet(f"color: {TIMER_RUNNING};")
        else:
            self.timer_label.setText("00:00:00")
            self.timer_label.setStyleSheet(f"color: {TEXT_MUTED};")

    def _tick_timer(self):
        self._update_timer_ui()

    def _start_timer(self):
        if self.timer_started_at is not None:
            return

        now = datetime.now()
        self.timer_started_at = now
        self.timer_day = now.date()
        save_timer_state(now, self.timer_day)
        self.tick_timer.start()
        self._update_timer_ui()

    def _stop_timer(self):
        if self.timer_started_at is None or self.timer_day is None:
            return

        elapsed_hours = seconds_to_hours(self._elapsed_seconds())
        if elapsed_hours > 0:
            key = date_key(self.timer_day)
            existing = self.entries.get(key, 0)
            self.entries[key] = add_hours(existing, elapsed_hours)
            self._persist_data()

        self.timer_started_at = None
        self.timer_day = None
        clear_timer_state()
        self.tick_timer.stop()
        self._update_timer_ui()

        today = date.today()
        if self.view_year == today.year and self.view_month == today.month:
            self.selected_date = today
        self._refresh_calendar()
        self._refresh_plot()
        self._refresh_stats()

    def _prev_month(self):
        if self.view_month == 1:
            self.view_month = 12
            self.view_year -= 1
        else:
            self.view_month -= 1
        self._refresh_calendar()
        if self.plot_scope == "month":
            self._refresh_plot()

    def _next_month(self):
        if self.view_month == 12:
            self.view_month = 1
            self.view_year += 1
        else:
            self.view_month += 1
        self._refresh_calendar()
        if self.plot_scope == "month":
            self._refresh_plot()

    def _on_plot_tab_changed(self, index):
        self.plot_scope = ("week", "year", "month")[index]
        self._refresh_plot()

    def _go_today(self):
        today = date.today()
        self.view_year = today.year
        self.view_month = today.month
        self.selected_date = today
        self._refresh_calendar()
        self._refresh_plot()

    def _on_day_click(self, btn):
        if btn.day_date is None:
            return

        self.selected_date = btn.day_date
        key = date_key(btn.day_date)
        current = self.entries.get(key)

        dialog = HoursDialog(btn.day_date, current, self)
        if dialog.exec() != QDialog.Accepted:
            self._refresh_calendar()
            return

        hours = dialog.result_hours()
        if hours is None:
            self.entries.pop(key, None)
        elif hours == 0:
            self.entries.pop(key, None)
        else:
            self.entries[key] = hours

        self._persist_data()
        self._refresh_calendar()
        self._refresh_plot()
        self._refresh_stats()

    def _on_tab_changed(self, index):
        if self.tabs.tabText(index) == "Stats":
            self._refresh_stats()
            self._update_financial_year_status()

    def _on_weekly_target_changed(self, value):
        self.settings["weekly_target_hours"] = value
        self._persist_data()
        self._refresh_plot()
        self._refresh_stats()

    def _on_weekly_goal_changed(self):
        self.settings["weekly_goal"] = self.weekly_goal_input.text().strip()
        self._persist_data()

    def _md_path(self):
        return get_md_path(self.config)

    def _persist_data(self):
        self.last_synced = persist_data(self.entries, self.settings, self.config)
        self._update_sync_status()

    def _update_sync_status(self):
        md_path = self._md_path()
        if not md_path:
            self.sync_status_label.setText("Vault path not set — using local entries.json")
            return

        timestamp = self.last_synced
        if md_path.exists():
            try:
                _, md_settings = parse_md(md_path)
                timestamp = md_settings.get("last_updated", timestamp) or timestamp
            except OSError:
                pass

        if timestamp:
            label = display_timestamp(timestamp)
            self.sync_status_label.setText(f"Last synced: {label}  →  {md_path}")
        else:
            self.sync_status_label.setText(f"Vault file: {md_path}")

    def _save_vault_config(self):
        self.config["vault_path"] = self.vault_path_input.text().strip()
        save_config(self.config)

    def _on_vault_path_changed(self):
        self._save_vault_config()

    def _browse_vault(self):
        current = self.vault_path_input.text().strip()
        start = current if current else str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "Select Obsidian vault", start)
        if not path:
            return
        self.vault_path_input.setText(path)
        self.config["vault_path"] = path
        save_config(self.config)
        self.entries, self.settings, self.last_synced = startup_sync(self.config)
        self.weekly_target_spin.setValue(self.settings["weekly_target_hours"])
        self.weekly_goal_input.setText(self.settings.get("weekly_goal", DEFAULT_WEEKLY_GOAL))
        self._refresh_calendar()
        self._refresh_plot()
        self._refresh_stats()
        self._update_sync_status()

    def _import_now(self):
        md_path = self._md_path()
        if md_path and md_path.exists():
            source = md_path
        else:
            source, _ = QFileDialog.getOpenFileName(
                self,
                "Import habit tracker markdown",
                str(Path.home()),
                "Markdown files (*.md)",
            )
            if not source:
                return
            source = Path(source)

        remote_entries, remote_settings = parse_md(source)
        if entries_equal(self.entries, remote_entries):
            merged = remote_entries
        else:
            merged = merge_entries(self.entries, remote_entries)
        self.entries = merged
        if remote_settings.get("weekly_target_hours"):
            self.settings["weekly_target_hours"] = remote_settings["weekly_target_hours"]
            self.weekly_target_spin.setValue(self.settings["weekly_target_hours"])
        if "weekly_goal" in remote_settings:
            self.settings["weekly_goal"] = remote_settings["weekly_goal"]
            self.weekly_goal_input.setText(self.settings["weekly_goal"])
        self._persist_data()
        self._refresh_calendar()
        self._refresh_plot()
        self._refresh_stats()

    def _export_now(self):
        md_path = self._md_path()
        if md_path:
            target = md_path
        else:
            target, _ = QFileDialog.getSaveFileName(
                self,
                "Export habit tracker markdown",
                str(Path.home() / DEFAULT_MD_FILENAME),
                "Markdown files (*.md)",
            )
            if not target:
                return
            target = Path(target)
        self.last_synced = write_md(target, self.entries, self.settings)
        save_entries_json(self.entries)
        if md_path:
            self.config["last_synced"] = self.last_synced
            save_config(self.config)
        self._update_sync_status()

    def closeEvent(self, event):
        if self._md_path():
            self._persist_data()
        super().closeEvent(event)

    def _weekly_target(self):
        return self.settings["weekly_target_hours"]

    def _style_day_button(self, btn, day_date, day_num, hours, today):
        btn.day_date = day_date
        btn.setText(str(day_num))
        btn.setEnabled(True)

        if hours is not None:
            btn.setText(f"{day_num}\n● {format_duration(hours)}")

        bg = SURFACE
        fg = TEXT
        if day_date == today:
            bg = SURFACE_ALT
        if day_date == self.selected_date:
            bg = SURFACE_ACTIVE

        btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: none;
                border-radius: 6px;
                padding: 4px;
            }}
            QPushButton:hover {{
                background-color: {SURFACE_ACTIVE};
            }}
            """
        )

    def _refresh_calendar(self):
        self.month_label.setText(
            datetime(self.view_year, self.view_month, 1).strftime("%B %Y")
        )

        cal = calendar.Calendar(firstweekday=0)
        weeks = cal.monthdayscalendar(self.view_year, self.view_month)
        today = date.today()

        for r in range(6):
            for c in range(7):
                btn = self.day_buttons[r][c]
                btn.day_date = None
                btn.setText("")
                btn.setEnabled(False)
                btn.setStyleSheet(
                    f"QPushButton {{ background-color: {BG}; border: none; }}"
                )

        for r, week in enumerate(weeks):
            for c, day_num in enumerate(week):
                if day_num == 0:
                    continue
                day_date = date(self.view_year, self.view_month, day_num)
                key = date_key(day_date)
                hours = self.entries.get(key)
                self._style_day_button(
                    self.day_buttons[r][c], day_date, day_num, hours, today
                )

        key = date_key(self.selected_date)
        hours = self.entries.get(key)
        if hours is not None:
            self.status_label.setText(
                f"Selected: {self.selected_date.strftime('%d %b %Y')} — {format_duration(hours)}"
            )
        else:
            self.status_label.setText(
                f"Selected: {self.selected_date.strftime('%d %b %Y')} — no entry"
            )

    def _plot_entries(self):
        today = date.today()
        filtered = []
        if self.plot_scope == "week":
            iso_year, iso_week, _ = today.isocalendar()
        for key in sorted(self.entries.keys()):
            d = date.fromisoformat(key)
            if self.plot_scope == "week":
                d_iso_year, d_iso_week, _ = d.isocalendar()
                if d_iso_year == iso_year and d_iso_week == iso_week:
                    filtered.append((key, self.entries[key]))
            elif self.plot_scope == "year":
                if d.year == today.year:
                    filtered.append((key, self.entries[key]))
            elif d.year == self.view_year and d.month == self.view_month:
                filtered.append((key, self.entries[key]))
        return filtered

    def _plot_title(self):
        if self.plot_scope == "week":
            today = date.today()
            iso_week = today.isocalendar()[1]
            monday = today - timedelta(days=today.weekday())
            sunday = monday + timedelta(days=6)
            return (
                f"Week {iso_week} ({monday.strftime('%d %b')} – {sunday.strftime('%d %b')})"
            )
        if self.plot_scope == "year":
            return f"{date.today().year} year to date"
        return datetime(self.view_year, self.view_month, 1).strftime("%B %Y")

    def _plot_actual_total(self):
        total_minutes = 0
        for _, hours in self._plot_entries():
            total_minutes += hours_to_minutes(hours)
        return total_minutes / 60

    def _plot_expected_total(self):
        weekly_target = self._weekly_target()
        today = date.today()
        if self.plot_scope == "week":
            return weekly_target
        if self.plot_scope == "year":
            return weekly_target * iso_weeks_so_far_in_year(today.year, today)
        return weekly_target * iso_weeks_in_month(self.view_year, self.view_month)

    def _refresh_compare_plot(self):
        self.compare_ax.clear()
        self.compare_ax.set_facecolor("#181825")
        self.compare_ax.set_title("Total", color=TEXT_MUTED, fontsize=9, pad=6)

        actual = self._plot_actual_total()
        expected = self._plot_expected_total()
        labels = ["Actual", "Expected"]
        values = [actual, expected]
        colors = [ACCENT, EXPECTED]
        x = [0, 1]

        bars = self.compare_ax.bar(x, values, color=colors, width=0.55)
        self.compare_ax.set_xticks(x)
        self.compare_ax.set_xticklabels(labels, fontsize=7)
        self.compare_ax.tick_params(colors=TEXT_DIM, labelsize=7)
        ymax = max(values) if values else 1
        if ymax == 0:
            ymax = 1
        self.compare_ax.set_ylim(0, ymax * 1.2)

        for bar, value in zip(bars, values):
            self.compare_ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                format_duration(value),
                ha="center",
                va="bottom",
                fontsize=6,
                color=TEXT_MUTED,
            )

        for spine in self.compare_ax.spines.values():
            spine.set_color(SURFACE_ALT)

    def _refresh_plot(self):
        self.ax.clear()
        self.ax.set_facecolor("#181825")
        self.ax.set_title(self._plot_title(), color=TEXT_MUTED, fontsize=10, pad=8)

        plot_data = self._plot_entries()
        if not plot_data:
            empty_msg = {
                "week": "No data for this week yet",
                "year": "No data for this year yet",
                "month": "No data for this month yet",
            }[self.plot_scope]
            self.ax.text(
                0.5,
                0.5,
                empty_msg,
                ha="center",
                va="center",
                color=TEXT_DIM,
                transform=self.ax.transAxes,
            )
            self.ax.set_xticks([])
            self.ax.set_yticks([])
        else:
            dates = [datetime.strptime(k, "%Y-%m-%d") for k, _ in plot_data]
            values = [v for _, v in plot_data]
            self.ax.bar(dates, values, color=ACCENT, width=0.8)
            self.ax.set_ylabel("Hours", color=TEXT_MUTED, fontsize=9)
            self.ax.tick_params(colors=TEXT_DIM, labelsize=8)
            self.figure.autofmt_xdate(rotation=30, ha="right")
            for spine in self.ax.spines.values():
                spine.set_color(SURFACE_ALT)

        self._refresh_compare_plot()
        self.figure.tight_layout()
        main_pos = self.ax.get_position()
        compare_pos = self.compare_ax.get_position()
        self.compare_ax.set_position(
            [compare_pos.x0, main_pos.y0, compare_pos.width, main_pos.height]
        )
        self.canvas.draw()

    def _draw_stats_bar(
        self, ax, figure, canvas, data, title, expected_values=None, rotate_labels=False
    ):
        ax.clear()
        ax.set_facecolor("#181825")
        ax.set_title(title, color=TEXT_MUTED, fontsize=10, pad=8)

        if not data:
            ax.text(
                0.5,
                0.5,
                "No data for this year yet",
                ha="center",
                va="center",
                color=TEXT_DIM,
                transform=ax.transAxes,
            )
            ax.set_xticks([])
            ax.set_yticks([])
        else:
            if len(data[0]) == 3:
                labels, actual_values, _ = zip(*data)
            else:
                labels, actual_values = zip(*data)
            x = list(range(len(labels)))
            width = 0.38
            actual_bars = ax.bar(
                [i - width / 2 for i in x],
                actual_values,
                width,
                label="Actual",
                color=ACCENT,
            )
            if expected_values is not None:
                ax.bar(
                    [i + width / 2 for i in x],
                    expected_values,
                    width,
                    label="Expected",
                    color=EXPECTED,
                )
            ax.set_ylabel("Hours", color=TEXT_MUTED, fontsize=9)
            ax.set_xticks(x)
            ax.set_xticklabels(labels)
            ax.tick_params(colors=TEXT_DIM, labelsize=7)
            if rotate_labels:
                for label in ax.get_xticklabels():
                    label.set_rotation(45)
                    label.set_ha("right")
            for bar, value in zip(actual_bars, actual_values):
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height(),
                    format_duration(value),
                    ha="center",
                    va="bottom",
                    fontsize=6,
                    color=TEXT_MUTED,
                )
            if expected_values is not None:
                ax.legend(
                    facecolor=SURFACE,
                    edgecolor=SURFACE_ALT,
                    labelcolor=TEXT_MUTED,
                    fontsize=8,
                )
            for spine in ax.spines.values():
                spine.set_color(SURFACE_ALT)

        figure.tight_layout()
        canvas.draw()

    def _refresh_stats(self):
        today = date.today()
        year = today.year
        weekly_target = self._weekly_target()

        ytd = year_to_date_total(self.entries, year)
        month_total = total_for_month(self.entries, year, today.month)
        week_total = total_for_iso_week(self.entries, today)

        ytd_expected = weekly_target * iso_weeks_so_far_in_year(year, today)
        month_expected = weekly_target * iso_weeks_in_month(year, today.month)

        self.ytd_label.setText(
            f"YTD {year}: {format_duration(ytd)} / {format_duration(ytd_expected)}"
        )
        self.month_total_label.setText(
            f"This month: {format_duration(month_total)} / {format_duration(month_expected)}"
        )
        self.week_total_label.setText(
            f"This week: {format_duration(week_total)} / {format_duration(weekly_target)}"
        )

        month_data = aggregate_by_month(self.entries, year)
        week_data = aggregate_by_week(self.entries, year)

        month_expected_values = [
            weekly_target * iso_weeks_in_month(year, month_num)
            for _, _, month_num in month_data
        ]
        week_expected_values = [weekly_target] * len(week_data)

        self._draw_stats_bar(
            self.month_ax,
            self.month_figure,
            self.month_canvas,
            month_data,
            "Monthly totals vs expected",
            expected_values=month_expected_values,
        )
        self._draw_stats_bar(
            self.week_ax,
            self.week_figure,
            self.week_canvas,
            week_data,
            "Weekly totals vs expected",
            expected_values=week_expected_values,
            rotate_labels=True,
        )


def main():
    app = QApplication(sys.argv)
    window = HabitTracker()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
