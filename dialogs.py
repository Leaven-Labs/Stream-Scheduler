"""The smaller windows: a schedule, the words of one single stream, a preview of what would be sent,
a YouTube channel's options, and the About box."""
import os
from datetime import datetime, timedelta

from PySide6.QtCore import QDate, Qt, QTime
from PySide6.QtWidgets import (QComboBox, QDateEdit, QDialog, QFileDialog, QGridLayout, QHBoxLayout, QLineEdit,
                               QPlainTextEdit, QScrollArea, QSpinBox, QTimeEdit, QVBoxLayout, QWidget)

import engine
import paths
import recurrence
import titles
import ui
import youtube
from store import new_id
from wizards import YouTubeOptions

KIND_NAMES = {"youtube": "YouTube", "facebook": "Facebook", "wix": "Website", "wordpress": "WordPress",
              "webhook": "Webhook"}


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
    tips = {"series": "The series' name, from the schedule", "note": "A note typed for one single stream (Edit, "
            "on the Upcoming page)", "number": "Which stream of the series it is: 2. Needs a first date.",
            "nth": "The same as a word: 2nd. Needs a first date."}
    both = QVBoxLayout()
    both.setSpacing(5)
    for lead, names in (("Insert:", titles.VARIABLES), ("Series:", titles.MORE_VARIABLES)):
        row = QHBoxLayout()
        row.setSpacing(6)
        head = ui.label(lead, "small")
        head.setFixedWidth(44)
        row.addWidget(head)
        for name in names:
            row.addWidget(ui.button("{" + name + "}", "var", lambda _=False, n=name: (
                target.insert("{" + n + "}") if isinstance(target, QLineEdit) else target.insertPlainText("{" + n + "}"),
                target.setFocus()), tips.get(name, "")))
        row.addStretch(1)
        both.addLayout(row)
    return both


class OptionalDate(QWidget):
    """A switch, a few words and a date: the date counts only while the switch is on."""

    def __init__(self, text, value, default):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.switch = ui.Switch(bool(value))
        self.date = QDateEdit(QDate.fromString(value, "yyyy-MM-dd") if value else default)
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("ddd, MMM d, yyyy")
        self.date.setMinimumWidth(170)
        self.date.setEnabled(bool(value))
        pad(self.date)
        self.switch.toggled.connect(self.date.setEnabled)
        row.addWidget(self.switch)
        row.addWidget(ui.label(text))
        row.addWidget(self.date)
        row.addStretch(1)

    def value(self):
        return self.date.date().toString("yyyy-MM-dd") if self.switch.isChecked() else ""


class ThumbnailPicker(QWidget):
    """Choose a picture file for the thumbnail, or none. `path` is the choice ("" for none)."""

    def __init__(self, path, none_text="None: YouTube's own picture"):
        super().__init__()
        self.path, self.none_text = path or "", none_text
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.name = ui.label("", "sub")
        self.clear_button = ui.button("Remove", "mini", lambda: self.set(""))
        row.addWidget(ui.button("Choose a picture ...", "mini", self.choose,
                                "JPG or PNG, at most 2 MB. YouTube suggests 1280 × 720."))
        row.addWidget(self.clear_button)
        row.addWidget(self.name, 1)
        self.set(self.path)

    def set(self, path):
        self.path = path
        problem = youtube.thumbnail_problem(path) if path else ""
        self.name.setObjectName("error" if problem else "sub")
        ui.set_prop(self.name, "x", 1)
        self.name.setText(problem or os.path.basename(path) or self.none_text)
        self.name.setToolTip(path)
        self.clear_button.setVisible(bool(path))

    def choose(self):
        path, _ = QFileDialog.getOpenFileName(self, "Thumbnail", os.path.dirname(self.path),
                                              "Pictures (*.jpg *.jpeg *.png)")
        if path:
            self.set(path)


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
        self.resize(780, 760)
        col = QVBoxLayout(self)
        col.setContentsMargins(26, 22, 18, 18)
        col.setSpacing(10)
        col.addWidget(ui.label(self.windowTitle(), "pagetitle"))
        body = QWidget()
        body.setObjectName("scrollbody")
        grid = QGridLayout(body)
        grid.setContentsMargins(0, 0, 12, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        col.addWidget(scroll, 1)

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
        days_box = QWidget()
        days_box.setLayout(days)
        days.setContentsMargins(0, 0, 0, 0)
        self.repeat = ui.Segments([("weekly", "Every week"), ("once", "One time")], "once" if s.get("once") else "weekly")
        self.date = QDateEdit(QDate.fromString(s["once"], "yyyy-MM-dd") if s.get("once")
                              else QDate.currentDate().addDays(7))
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dddd, MMMM d, yyyy")
        self.date.setMinimumWidth(250)
        pad(self.date)
        when_box = QVBoxLayout()
        when_box.setSpacing(8)
        when_box.addWidget(self.repeat, 0, Qt.AlignLeft)
        when_box.addWidget(days_box)
        when_box.addWidget(self.date, 0, Qt.AlignLeft)
        self.starts = OptionalDate("First stream on or after", s.get("starts", ""), QDate.currentDate())
        self.until = OptionalDate("Last stream on or before", s.get("until", ""), QDate.currentDate().addDays(42))
        for w in (self.starts, self.until):
            w.setToolTip("For a series with a beginning and an end, such as Lent. Off: no limit.")
            when_box.addWidget(w)
            w.switch.toggled.connect(lambda *_: self.update_preview())
            w.date.dateChanged.connect(lambda *_: self.update_preview())

        def show_kind(*_):
            once = self.repeat.buttons["once"].isChecked()
            days_box.setVisible(not once)
            self.starts.setVisible(not once)
            self.until.setVisible(not once)
            self.date.setVisible(once)
            self.update_preview()
        self.repeat.changed.connect(show_kind)
        self.date.dateChanged.connect(lambda *_: self.update_preview())
        self.show_kind = show_kind
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
        self.series = QLineEdit(s.get("series", ""))
        self.series.setPlaceholderText("Optional, e.g. Lent 2027. Written where the title or description says {series}.")
        self.thumbnail = ThumbnailPicker(s.get("thumbnail", ""))
        self.privacy = QComboBox()
        for key, text in (("", "As the channel is set"), ("public", "Public: everyone"),
                          ("unlisted", "Unlisted: only with the link"), ("private", "Private: only you")):
            self.privacy.addItem(text, key)
        self.privacy.setCurrentIndex(max(0, self.privacy.findData(s.get("privacy", ""))))
        self.playlist = QLineEdit(s.get("playlist", ""))
        self.playlist.setPlaceholderText("Optional: paste a playlist's link. Empty: as the channel is set.")
        tube = QVBoxLayout()
        tube.setSpacing(6)
        tube.addWidget(self.privacy, 0, Qt.AlignLeft)
        tube.addWidget(self.playlist)
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

        self.encoder = QComboBox()
        self.encoder.addItem("Don't check OBS", "")
        for e in store.encoders:
            self.encoder.addItem(e["name"], e["id"])
        self.encoder.setCurrentIndex(max(0, self.encoder.findData(s.get("encoder_id", ""))))
        rounds = (engine.obs_rounds(s) + [0])[:2] if s.get("obs_checks") else list(engine.OBS_CHECKS)
        self.obs_first, self.obs_second = QSpinBox(), QSpinBox()
        for spin, value in ((self.obs_first, rounds[0]), (self.obs_second, rounds[1])):
            spin.setRange(0, 600)
            spin.setValue(value)
            spin.setFixedWidth(64)
            pad(spin)
        self.obs_second.setSpecialValueText("off")
        self.obs_first.setRange(1, 600)
        obs_box = QVBoxLayout()
        obs_box.setSpacing(6)
        obs_box.addWidget(self.encoder, 0, Qt.AlignLeft)
        self.obs_when = QWidget()
        when_row = QHBoxLayout(self.obs_when)
        when_row.setContentsMargins(0, 0, 0, 0)
        when_row.setSpacing(8)
        for w in (ui.label("Check"), self.obs_first, ui.label("and"), self.obs_second,
                  ui.label("minutes before the start")):
            when_row.addWidget(w)
        when_row.addStretch(1)
        obs_box.addWidget(self.obs_when)
        obs_box.addWidget(ui.label("Is OBS open, and set to the stream key of this schedule's YouTube stream? You "
                                   "are told on the Alerts page's channels if not. The app never changes OBS."
                                   if store.encoders else "To check OBS before each stream, add OBS on the "
                                   "Destinations page.", "small", wrap=True))
        self.encoder.currentIndexChanged.connect(lambda *_: self.obs_when.setVisible(bool(self.encoder.currentData())))
        self.obs_when.setVisible(bool(self.encoder.currentData()))
        self.encoder.setEnabled(bool(store.encoders))

        title_box = QVBoxLayout()
        title_box.setSpacing(5)
        title_box.addWidget(self.title)
        title_box.addLayout(variable_row(self.title))
        rows = [("Name", self.name), ("Repeats", when_box), ("Stream time", self.time),
                ("Create it", made), ("Title", title_box), ("Date written as", self.date_format),
                ("Series", self.series), ("Description", self.description), ("Thumbnail", self.thumbnail),
                ("On YouTube", tube), ("Send to", dest_row), ("OBS", obs_box)]
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
        bar = bottom_bar(self, "Save", self.save)
        bar.insertWidget(0, ui.button("Preview what is sent", clicked=self.show_preview,
                                      tip="Everything the platforms would be told for the next streams. "
                                          "Nothing is sent."))
        col.addLayout(bar)

        for b in self.days:
            b.toggled.connect(self.update_preview)
        for signal in (self.title.textChanged, self.time.timeChanged, self.create_time.timeChanged,
                       self.lead.valueChanged, self.date_format.currentIndexChanged, self.series.textChanged):
            signal.connect(self.update_preview)
        self.show_kind()

    def value(self):
        s = dict(self.schedule)
        s.update(name=self.name.text().strip(), weekdays=[i for i, b in enumerate(self.days) if b.isChecked()],
                 time=self.time.time().toString("HH:mm"), lead_days=self.lead.value(),
                 create_time=self.create_time.time().toString("HH:mm"), title=self.title.text().strip(),
                 date_format=self.date_format.currentData(), description=self.description.toPlainText().strip(),
                 destinations=[i for i, b in self.dests.items() if b.isChecked()],
                 series=self.series.text().strip(), thumbnail=self.thumbnail.path,
                 privacy=self.privacy.currentData(), playlist=self.playlist.text().strip(),
                 starts=self.starts.value(), until=self.until.value())
        s.pop("once", None)
        s.pop("encoder_id", None)
        s.pop("obs_checks", None)
        if self.encoder.currentData():
            s["encoder_id"] = self.encoder.currentData()
            s["obs_checks"] = [m for m in (self.obs_first.value(), self.obs_second.value()) if m]
        if self.repeat.buttons["once"].isChecked():
            s["once"] = self.date.date().toString("yyyy-MM-dd")
            s.update(starts="", until="")
        return s

    def show_preview(self):
        PreviewDialog(self, self.store, self.value()).exec()

    def update_preview(self, *_):
        s = self.value()
        now = datetime.now()
        coming = recurrence.occurrences(s, now, now + timedelta(days=366)) if s["weekdays"] or s.get("once") else []
        if not coming:
            self.preview_title.setText("That date and time have passed" if s.get("once")
                                       else "No stream is left between the first and the last date"
                                       if s["weekdays"] else "Choose at least one stream day")
            self.preview_when.setText("")
            return
        when = coming[0]
        made = recurrence.create_at(s, when)
        self.preview_title.setText(engine.text_for(self.store, s, when)[0] or "(no title)")
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
        if not s["weekdays"] and not s.get("once"):
            found.insert(0, "Choose at least one stream day.")
        if s.get("once") and not recurrence.occurrences(s, now, now):
            found.insert(0, "That date and time have passed. Choose a later one.")
        if s.get("starts") and s.get("until") and s["until"] < s["starts"]:
            found.insert(0, "The last date is before the first date.")
        if s.get("playlist") and not youtube.playlist_id(s["playlist"]):
            found.append("The playlist is not understood. Paste the playlist's link from YouTube, or leave it empty.")
        if s.get("thumbnail") and youtube.thumbnail_problem(s["thumbnail"]):
            found.append(youtube.thumbnail_problem(s["thumbnail"]))
        if found:
            self.error.setText(found[0])
            return
        self.schedule = s
        self.accept()


class OverrideDialog(QDialog):
    """Other words, or another time, for one single stream. After accept(), `result` is the override:
    {} to go back to the schedule's own, or some of {"title", "description", "time"}."""

    def __init__(self, parent, store, item):
        super().__init__(parent)
        self.item = item
        schedule = item["schedule"]
        over = schedule.get("overrides", {}).get(item["date"], {})
        self.result = dict(over)
        self.setWindowTitle("Edit this stream")
        self.resize(660, 640)
        self.clock = store.settings.get("clock", "12")
        self.exists = any(e and e["status"] == "created" for _, e in item["targets"])
        col = QVBoxLayout(self)
        col.setContentsMargins(26, 22, 26, 18)
        col.setSpacing(10)
        col.addWidget(ui.label("Edit this stream only", "pagetitle"))
        col.addWidget(ui.label(
            f"{schedule['name']} · {titles.format_date(item['when'], 'weekday')}. The other streams of the "
            "schedule keep the schedule's own title, description and time."
            + (" This stream already exists: saving changes it on YouTube and on the website."
               if self.exists else ""), "sub", wrap=True))
        self.time = time_edit(over.get("time") or schedule["time"], self.clock)
        time_row = QHBoxLayout()
        time_row.addWidget(ui.label("Starts at", "strong"))
        time_row.addWidget(self.time)
        time_row.addStretch(1)
        col.addLayout(time_row)
        self.title = QLineEdit(over.get("title") or schedule.get("title", ""))
        self.description = QPlainTextEdit(over["description"] if "description" in over
                                          else schedule.get("description", ""))
        col.addWidget(ui.label("Title", "strong"))
        col.addWidget(self.title)
        col.addLayout(variable_row(self.title))
        col.addWidget(ui.label("Description", "strong"))
        col.addWidget(self.description, 1)
        self.note = QLineEdit(over.get("note", ""))
        self.note.setPlaceholderText("Optional, e.g. with baptism. Written where the title or description says {note}.")
        col.addWidget(ui.label("Note for this date", "strong"))
        col.addWidget(self.note)
        self.thumbnail = ThumbnailPicker(over.get("thumbnail", ""), "The schedule's own")
        col.addWidget(ui.label("Thumbnail for this stream", "strong"))
        col.addWidget(self.thumbnail)
        bar = bottom_bar(self, "Save for this stream", self.save)
        if any(over.get(k) for k in ("title", "time", "note", "thumbnail")) or "description" in over:
            bar.insertWidget(0, ui.button("Use the schedule's own again", clicked=self.reset))
        col.addLayout(bar)

    def reset(self):
        self.result = {k: v for k, v in self.result.items() if k == "skip"}
        self.accept()

    def save(self):
        title, description = self.title.text().strip(), self.description.toPlainText().strip()
        found = titles.problems(titles.render(title, self.item["when"]), description)
        if self.thumbnail.path and youtube.thumbnail_problem(self.thumbnail.path):
            found.append(youtube.thumbnail_problem(self.thumbnail.path))
        if found:
            self.error.setText(found[0])
            return
        schedule = self.item["schedule"]
        at = self.time.time().toString("HH:mm")
        when = datetime.combine(self.item["when"].date(), recurrence.parse_time(at))
        if when - datetime.now() < engine.MIN_AHEAD:
            self.error.setText("That time is less than 12 minutes away, or has passed.")
            return
        self.result = {k: v for k, v in self.result.items() if k == "skip"}
        if (title, description) != (schedule.get("title", ""), schedule.get("description", "")):
            self.result.update(title=title, description=description)
        if at != schedule["time"]:
            self.result["time"] = at
        if self.note.text().strip():
            self.result["note"] = self.note.text().strip()
        if self.thumbnail.path:
            self.result["thumbnail"] = self.thumbnail.path
        self.accept()


class PreviewDialog(QDialog):
    """What a schedule would send for its next streams. Nothing is sent."""

    def __init__(self, parent, store, schedule):
        super().__init__(parent)
        self.setWindowTitle("Preview")
        self.resize(700, 680)
        clock = store.settings.get("clock", "12")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 22, 18, 18)
        outer.setSpacing(10)
        outer.addWidget(ui.label("What would be sent", "pagetitle"))
        outer.addWidget(ui.label("Nothing is sent now. These are the next streams of this schedule as the "
                                 "platforms would be told, with what you have filled in so far.", "sub", wrap=True))
        body = QWidget()
        body.setObjectName("scrollbody")
        col = QVBoxLayout(body)
        col.setContentsMargins(0, 0, 12, 0)
        col.setSpacing(12)
        streams = engine.preview(store, schedule, 3) if schedule.get("weekdays") or schedule.get("once") else []
        if not streams:
            col.addWidget(ui.label("This schedule has no coming stream: choose its days and dates first.", "sub",
                                   wrap=True))
        for stream in streams:
            card = ui.card()
            box = QVBoxLayout(card)
            box.setContentsMargins(16, 12, 16, 14)
            box.setSpacing(5)
            box.addWidget(ui.label(titles.format_date(stream["when"], "weekday").upper() + "  ·  "
                                   + titles.format_time(stream["when"], clock), "caps"))
            box.addWidget(ui.label(stream["title"] or "(no title)", "big", wrap=True))
            box.addWidget(ui.label(f"{len(stream['title'])} of {titles.TITLE_LIMIT} characters  ·  created "
                                   f"{titles.short_day(stream['create_at'], clock)}", "small"))
            for problem in stream["problems"]:
                box.addWidget(ui.label("✗  " + problem, "error", wrap=True))
            words = ui.label(stream["description"] or "(no description)", "sub", wrap=True)
            words.setTextFormat(Qt.PlainText)
            box.addWidget(words)
            if not stream["destinations"]:
                box.addWidget(ui.label("No destination is chosen: nothing would be created.", "error", wrap=True))
            for dest in stream["destinations"]:
                box.addSpacing(4)
                box.addWidget(ui.rule())
                box.addWidget(ui.label(f"{KIND_NAMES[dest['kind']]} · {dest['name']}", "strong"))
                lines = QGridLayout()
                lines.setHorizontalSpacing(14)
                lines.setVerticalSpacing(3)
                lines.setColumnStretch(1, 1)
                for i, (name, value) in enumerate(dest["lines"]):
                    lines.addWidget(ui.label(name, "small"), i, 0, Qt.AlignTop)
                    lines.addWidget(ui.label(str(value), wrap=True), i, 1)
                box.addLayout(lines)
            col.addWidget(card)
        col.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        bar = QHBoxLayout()
        bar.addStretch(1)
        bar.addWidget(ui.button("Close", "primary", self.accept))
        outer.addLayout(bar)


class YouTubeOptionsDialog(QDialog):
    def __init__(self, parent, dest):
        super().__init__(parent)
        self.setWindowTitle("YouTube options")
        self.resize(600, 600)
        col = QVBoxLayout(self)
        col.setContentsMargins(26, 22, 26, 18)
        col.setSpacing(12)
        col.addWidget(ui.label(dest["name"], "pagetitle"))
        col.addWidget(ui.label("Used for every stream this app creates on the channel.", "sub"))
        self.options = YouTubeOptions(dest.get("options", {}))
        col.addWidget(self.options)
        col.addStretch(1)
        col.addLayout(bottom_bar(self, "Save", self.save))

    def save(self):
        problem = self.options.problem()
        if problem:
            self.error.setText(problem)
        else:
            self.accept()


class AboutDialog(QDialog):
    """Who made the app, who publishes it, which version this is, and its license."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(f"About {paths.APP_NAME}")
        self.setMinimumWidth(460)
        col = QVBoxLayout(self)
        col.setContentsMargins(26, 22, 26, 18)
        col.setSpacing(12)
        head = QHBoxLayout()
        head.setSpacing(14)
        head.addWidget(ui.Logo(48))
        names = QVBoxLayout()
        names.setSpacing(2)
        names.addWidget(ui.label(paths.APP_NAME, "pagetitle"))
        names.addWidget(ui.label(f"Version {paths.VERSION}", "sub"))
        head.addLayout(names, 1)
        col.addLayout(head)
        col.addWidget(ui.rule())
        facts = QGridLayout()
        facts.setHorizontalSpacing(18)
        facts.setVerticalSpacing(8)
        facts.setColumnStretch(1, 1)
        for row, (name, html) in enumerate([
                ("Author", paths.AUTHOR),
                ("Publisher", f"<a href='{paths.PUBLISHER_URL}'>{paths.PUBLISHER}</a>"),
                ("Version", paths.VERSION),
                ("License", f"<a href='{paths.LICENSE_URL}'>MIT License</a>"),
                ("Project", f"<a href='{paths.PROJECT_URL}'>{paths.PROJECT_URL.split('//')[1]}</a>")]):
            facts.addWidget(ui.label(name, "sub"), row, 0, Qt.AlignTop)
            facts.addWidget(ui.rich(html), row, 1)
        col.addLayout(facts)
        col.addWidget(ui.rule())
        col.addWidget(ui.label(
            f"{paths.COPYRIGHT}. Free software: anyone may use, copy, change and share it, as long as the "
            "copyright notice and license are kept with it. It comes without warranty of any kind.", "small", wrap=True))
        col.addWidget(ui.label(
            "YouTube and Facebook are trademarks of their owners; this app is not affiliated with or endorsed by "
            "Google, Meta or Wix.", "small", wrap=True))
        col.addWidget(ui.label(
            "The headings are set in Fraunces, by The Fraunces Project Authors, under the SIL Open Font License.",
            "small", wrap=True))
        bar = QHBoxLayout()
        bar.addStretch(1)
        bar.addWidget(ui.button("Close", "primary", self.accept))
        col.addLayout(bar)
