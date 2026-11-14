"""The smaller windows: a schedule, the words of one single stream, and a YouTube channel's options."""
from datetime import datetime

from PySide6.QtCore import Qt, QTime
from PySide6.QtWidgets import (QComboBox, QDialog, QGridLayout, QHBoxLayout, QLineEdit, QPlainTextEdit, QSpinBox,
                               QTimeEdit, QVBoxLayout, QWidget)

import engine
import recurrence
import titles
import ui
from store import new_id
from wizards import YouTubeOptions

KIND_NAMES = {"youtube": "YouTube", "facebook": "Facebook", "wix": "Website"}


def time_edit(text, clock):
    edit = QTimeEdit(QTime.fromString(text, "HH:mm"))
    edit.setDisplayFormat("HH:mm" if clock == "24" else "h:mm AP")
    edit.setFixedWidth(110)
    pad(edit)
    return edit


def pad(spin):
    """Room at the left of a time or number field's text (the style sheet cannot reach it)."""
    inner = spin.findChild(QLineEdit)
    if inner:
        inner.setTextMargins(8, 0, 0, 0)


def variable_row(target):
    """Buttons that put {date} and the others where the cursor is in `target`."""
    row = QHBoxLayout()
    row.setSpacing(6)
    row.addWidget(ui.label("Insert:", "small"))
    for name in titles.VARIABLES:
        row.addWidget(ui.button("{" + name + "}", "var", lambda _=False, n=name: (
            target.insert("{" + n + "}") if isinstance(target, QLineEdit) else target.insertPlainText("{" + n + "}"),
            target.setFocus())))
    row.addStretch(1)
    return row


def bottom_bar(dialog, ok_text, on_ok):
    bar = QHBoxLayout()
    dialog.error = ui.label("", "error", wrap=True)
    bar.addWidget(dialog.error, 1)
    bar.addWidget(ui.button("Cancel", clicked=dialog.reject))
    bar.addWidget(ui.button(ok_text, "primary", on_ok))
    return bar


class ScheduleDialog(QDialog):
    """Make or change a schedule. After accept(), `schedule` is the result (not yet saved)."""

    def __init__(self, parent, store, schedule=None):
        super().__init__(parent)
        self.store = store
        self.clock = store.settings.get("clock", "12")
        self.schedule = dict(schedule) if schedule else {
            "id": new_id(), "name": "", "enabled": True, "weekdays": [6], "time": "08:00", "lead_days": 1,
            "create_time": "09:00", "title": "Sunday Service - {date}", "description": "", "date_format": "long",
            "destinations": [d["id"] for d in store.destinations if d["kind"] in engine.ENABLED], "overrides": {}}
        s = self.schedule
        self.setWindowTitle("Edit schedule" if schedule else "New schedule")
        self.resize(720, 700)
        col = QVBoxLayout(self)
        col.setContentsMargins(26, 22, 26, 18)
        col.setSpacing(10)
        col.addWidget(ui.label(self.windowTitle(), "pagetitle"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)
        col.addLayout(grid)

        self.name = QLineEdit(s["name"])
        self.name.setPlaceholderText("For your own lists, e.g. Sunday Service")
        self.days = []
        days = QHBoxLayout()
        days.setSpacing(6)
        for i, day in enumerate(titles.WEEKDAYS):
            b = ui.button(day[:3], "pick")
            b.setCheckable(True)
            b.setChecked(i in s["weekdays"])
            days.addWidget(b)
            self.days.append(b)
        days.addStretch(1)
        self.time = time_edit(s["time"], self.clock)
        self.lead = QSpinBox()
        self.lead.setRange(1, recurrence.MAX_LEAD_DAYS)
        self.lead.setValue(int(s["lead_days"]))
        self.lead.setFixedWidth(56)
        pad(self.lead)
        self.create_time = time_edit(s["create_time"], self.clock)
        made = QHBoxLayout()
        made.setSpacing(8)
        for w in (self.lead, ui.label("day(s) before, at"), self.create_time):
            made.addWidget(w)
        made.addStretch(1)
        self.title = QLineEdit(s["title"])
        self.date_format = QComboBox()
        sample = datetime(2027, 11, 15)
        for key in titles.DATE_FORMATS:
            self.date_format.addItem(titles.format_date(sample, key), key)
        self.date_format.setCurrentIndex(max(0, self.date_format.findData(s["date_format"])))
        self.description = QPlainTextEdit(s["description"])
        self.description.setPlaceholderText("Shown under the video. The same {names} work here.")
        self.description.setFixedHeight(84)
        self.dests = {}
        dest_row = QHBoxLayout()
        dest_row.setSpacing(6)
        for d in store.destinations:
            if d["kind"] not in engine.ENABLED:
                continue
            b = ui.button(f"{KIND_NAMES[d['kind']]} · {d['name']}", "pick")
            b.setCheckable(True)
            b.setChecked(d["id"] in s["destinations"])
            dest_row.addWidget(b)
            self.dests[d["id"]] = b
        if not self.dests:
            dest_row.addWidget(ui.label("None connected yet. You can save the schedule and add them on the "
                                        "Destinations page.", "sub", wrap=True), 1)
        else:
            dest_row.addStretch(1)

        title_box = QVBoxLayout()
        title_box.setSpacing(5)
        title_box.addWidget(self.title)
        title_box.addLayout(variable_row(self.title))
        rows = [("Name", self.name), ("Stream days", days), ("Stream time", self.time),
                ("Create it", made), ("Title", title_box), ("Date written as", self.date_format),
                ("Description", self.description), ("Send to", dest_row)]
        for i, (text, thing) in enumerate(rows):
            grid.addWidget(ui.label(text, "strong"), i, 0, Qt.AlignTop)
            if isinstance(thing, QWidget):
                grid.addWidget(thing, i, 1, Qt.AlignLeft if thing in (self.time, self.date_format) else Qt.Alignment())
            else:
                grid.addLayout(thing, i, 1)

        preview = ui.card()
        box = QVBoxLayout(preview)
        box.setContentsMargins(16, 12, 16, 12)
        box.setSpacing(3)
        box.addWidget(ui.label("PREVIEW OF THE NEXT STREAM", "caps"))
        self.preview_title = ui.label("", "big", wrap=True)
        self.preview_when = ui.label("", "sub", wrap=True)
        box.addWidget(self.preview_title)
        box.addWidget(self.preview_when)
        col.addWidget(preview)
        col.addStretch(1)
        col.addLayout(bottom_bar(self, "Save", self.save))

        for b in self.days:
            b.toggled.connect(self.update_preview)
        for signal in (self.title.textChanged, self.time.timeChanged, self.create_time.timeChanged,
                       self.lead.valueChanged, self.date_format.currentIndexChanged):
            signal.connect(self.update_preview)
        self.update_preview()

    def value(self):
        s = dict(self.schedule)
        s.update(name=self.name.text().strip(), weekdays=[i for i, b in enumerate(self.days) if b.isChecked()],
                 time=self.time.time().toString("HH:mm"), lead_days=self.lead.value(),
                 create_time=self.create_time.time().toString("HH:mm"), title=self.title.text().strip(),
                 date_format=self.date_format.currentData(), description=self.description.toPlainText().strip(),
                 destinations=[i for i, b in self.dests.items() if b.isChecked()])
        return s

    def update_preview(self, *_):
        s = self.value()
        now = datetime.now()
        coming = recurrence.occurrences(s, now, now.replace(year=now.year + 1)) if s["weekdays"] else []
        if not coming:
            self.preview_title.setText("Choose at least one stream day")
            self.preview_when.setText("")
            return
        when = coming[0]
        made = recurrence.create_at(s, when)
        self.preview_title.setText(titles.render(s["title"], when, s["date_format"], self.clock) or "(no title)")
        self.preview_when.setText(
            f"Goes live {titles.format_date(when, 'weekday')} at {titles.format_time(when, self.clock)}  ·  "
            f"created on {titles.format_date(made, 'weekday')} at {titles.format_time(made, self.clock)}")

    def save(self):
        s = self.value()
        now = datetime.now()
        sample = titles.render(s["title"], now.replace(month=9, day=30), "weekday")  # about the longest date
        found = titles.problems(sample, s["description"])
        if not s["name"]:
            found.insert(0, "Give the schedule a name.")
        if not s["weekdays"]:
            found.insert(0, "Choose at least one stream day.")
        if found:
            self.error.setText(found[0])
            return
        self.schedule = s
        self.accept()


class OverrideDialog(QDialog):
    """Other words for one single stream. After accept(), `result` is the override: {} to go back to
    the schedule's own text, or {"title", "description"}."""

    def __init__(self, parent, store, item):
        super().__init__(parent)
        self.item = item
        schedule = item["schedule"]
        over = schedule.get("overrides", {}).get(item["date"], {})
        self.result = dict(over)
        self.setWindowTitle("Edit this stream")
        self.resize(620, 430)
        col = QVBoxLayout(self)
        col.setContentsMargins(26, 22, 26, 18)
        col.setSpacing(10)
        col.addWidget(ui.label("Edit this stream only", "pagetitle"))
        col.addWidget(ui.label(
            f"{schedule['name']} · {titles.format_date(item['when'], 'weekday')}. The other streams of the "
            "schedule keep the schedule's own title and description.", "sub", wrap=True))
        self.title = QLineEdit(over.get("title") or schedule.get("title", ""))
        self.description = QPlainTextEdit(over["description"] if "description" in over
                                          else schedule.get("description", ""))
        col.addWidget(ui.label("Title", "strong"))
        col.addWidget(self.title)
        col.addLayout(variable_row(self.title))
        col.addWidget(ui.label("Description", "strong"))
        col.addWidget(self.description, 1)
        bar = bottom_bar(self, "Save for this stream", self.save)
        if over.get("title") or "description" in over:
            bar.insertWidget(0, ui.button("Use the schedule's text again", clicked=self.reset))
        col.addLayout(bar)

    def reset(self):
        self.result = {k: v for k, v in self.result.items() if k == "skip"}
        self.accept()

    def save(self):
        title, description = self.title.text().strip(), self.description.toPlainText().strip()
        found = titles.problems(titles.render(title, self.item["when"]), description)
        if found:
            self.error.setText(found[0])
            return
        schedule = self.item["schedule"]
        if (title, description) == (schedule.get("title", ""), schedule.get("description", "")):
            return self.reset()   # nothing differs from the schedule
        self.result.update(title=title, description=description)
        self.accept()


class YouTubeOptionsDialog(QDialog):
    def __init__(self, parent, dest):
        super().__init__(parent)
        self.setWindowTitle("YouTube options")
        self.resize(560, 360)
        col = QVBoxLayout(self)
        col.setContentsMargins(26, 22, 26, 18)
        col.setSpacing(12)
        col.addWidget(ui.label(dest["name"], "pagetitle"))
        col.addWidget(ui.label("Used for every stream this app creates on the channel.", "sub"))
        self.options = YouTubeOptions(dest.get("options", {}))
        col.addWidget(self.options)
        col.addStretch(1)
        col.addLayout(bottom_bar(self, "Save", self.accept))
