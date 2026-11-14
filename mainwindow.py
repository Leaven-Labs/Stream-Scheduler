"""The main window: a menu at the left and five pages (Upcoming, Schedules, Destinations, History, Settings).

While the window lives (also hidden in the tray) it asks engine.run_due() once a minute to create
the streams whose time has come.
"""
import os
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFrame, QHBoxLayout, QHeaderView, QMainWindow, QMenu,
                               QScrollArea, QStackedWidget, QSystemTrayIcon, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

import autostart
import engine
import facebook
import paths
import recurrence
import titles
import ui
import youtube
from dialogs import KIND_NAMES, OverrideDialog, ScheduleDialog, YouTubeOptionsDialog
from wizards import FacebookWizard, YouTubeWizard

CHECK_EVERY_MS = 60_000


def short_day(when, clock):
    """"Sat, Nov 13 at 9:00 AM"."""
    return f"{when.strftime('%a')}, {titles.MONTHS[when.month - 1][:3]} {when.day} at {titles.format_time(when, clock)}"


class Page(QWidget):
    """A page: a title, a line under it, buttons at the right, and a scrolling column of cards."""

    def __init__(self, window, title, sub):
        super().__init__()
        self.window_, self.store, self.vault = window, window.store, window.vault
        outer = QVBoxLayout(self)
        outer.setContentsMargins(30, 26, 30, 0)
        outer.setSpacing(16)
        head = QHBoxLayout()
        words = QVBoxLayout()
        words.setSpacing(3)
        words.addWidget(ui.label(title, "pagetitle"))
        words.addWidget(ui.label(sub, "sub", wrap=True))
        head.addLayout(words, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        head.addLayout(self.actions)
        outer.addLayout(head)
        body = QWidget()
        body.setObjectName("scrollbody")
        self.col = QVBoxLayout(body)
        self.col.setContentsMargins(0, 0, 8, 24)
        self.col.setSpacing(12)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

    clock = property(lambda self: self.store.settings.get("clock", "12"))

    def refresh(self):
        ui.clear(self.col)
        self.fill()
        self.col.addStretch(1)

    def empty(self, heading, text, button=None):
        card = ui.card()
        box = QVBoxLayout(card)
        box.setContentsMargins(26, 30, 26, 30)
        box.setSpacing(8)
        box.addWidget(ui.label(heading, "heading"), 0, Qt.AlignHCenter)
        lab = ui.label(text, "sub", wrap=True)
        lab.setAlignment(Qt.AlignHCenter)
        box.addWidget(lab)
        if button:
            box.addSpacing(6)
            box.addWidget(button, 0, Qt.AlignHCenter)
        self.col.addWidget(card)


class UpcomingPage(Page):
    def __init__(self, window):
        super().__init__(window, "Upcoming streams",
                         "What your schedules will create next. Each stream is created on its platforms by itself.")
        self.check_button = ui.button("Check now", clicked=window.check,
                                      tip="Create every stream whose time has come")
        self.actions.addWidget(self.check_button)

    def fill(self):
        problem = self.vault.available()
        if problem:
            self.col.addWidget(ui.callout("No safe place for sign-ins", problem, "warn", "warn"))
        if not self.store.destinations or not self.store.schedules:
            first = not self.store.destinations
            self.empty("Two steps to your first automatic stream" if first else "Now create a schedule",
                       "1. Connect YouTube or a Facebook Page.   2. Create a schedule, for example every Sunday "
                       "at 8:00 AM.\nFrom then on the streams appear on your platforms by themselves."
                       if first else "Say when you stream and what the title is. The app does the rest.",
                       ui.button("Connect a destination" if first else "New schedule", "primary",
                                 lambda: self.window_.show_page(2 if first else 1)))
            return
        items = engine.upcoming(self.store, limit=10)
        if not items:
            self.empty("Nothing coming up", "Every schedule is switched off.")
        for item in items:
            self.col.addWidget(self.stream_card(item))

    def stream_card(self, item):
        now = datetime.now()
        skipped = item["skipped"]
        card = ui.card("off" if skipped else "")
        row = QHBoxLayout(card)
        row.setContentsMargins(16, 14, 16, 14)
        row.setSpacing(16)
        row.addWidget(ui.DateBlock(item["when"], dim=skipped), 0, Qt.AlignTop)
        mid = QVBoxLayout()
        mid.setSpacing(5)
        title = ui.label(item["title"] or "(no title)", "big", wrap=True)
        mid.addWidget(title)
        missing = [d for d, e in item["targets"] if not (e and e["status"] == "created")]
        if skipped:
            state = "Skipped: will not be created"
        elif not item["targets"]:
            state = "No destination chosen"
        elif not missing:
            state = "Scheduled everywhere"
        elif item["create_at"] <= now:
            state = "Due now"
        else:
            state = f"Will be created {short_day(item['create_at'], self.clock)}"
        edited = "  ·  Edited for this date" if item["overridden"] else ""
        mid.addWidget(ui.label(f"{item['schedule']['name']}  ·  {titles.format_time(item['when'], self.clock)}"
                               f"  ·  {state}{edited}", "sub", wrap=True))
        chips = QHBoxLayout()
        chips.setSpacing(6)
        for dest, entry in item["targets"]:
            name = KIND_NAMES[dest["kind"]]
            if skipped:
                chips.addWidget(ui.chip(name))
            elif entry and entry["status"] == "created":
                url = entry.get("url")
                chips.addWidget(ui.chip(f"✓  {name} · Scheduled", "ok", "Open it in the browser" if url else "",
                                        (lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u))) if url else None))
            elif entry:
                chips.addWidget(ui.chip(f"{name} · Failed", "no", entry.get("note", "")))
            else:
                chips.addWidget(ui.chip(f"{name} · Planned"))
        chips.addStretch(1)
        mid.addLayout(chips)
        for dest, entry in item["targets"]:
            if entry and not skipped and (entry["status"] == "failed" or entry.get("note")):
                mid.addWidget(ui.label(f"{KIND_NAMES[dest['kind']]}: {entry['note']}",
                                       "error" if entry["status"] == "failed" else "small", wrap=True))
        row.addLayout(mid, 1)
        buttons = QVBoxLayout()
        buttons.setSpacing(6)
        if not skipped:
            if missing:
                buttons.addWidget(ui.button("Schedule now", "mini", lambda: self.schedule_now(item),
                                            "Create it on the platforms right away"))
                buttons.addWidget(ui.button("Edit", "mini", lambda: self.edit(item),
                                            "Another title or description for this one stream"))
        if missing or skipped or not item["targets"]:
            buttons.addWidget(ui.button("Restore" if skipped else "Skip", "mini", lambda: self.skip(item, not skipped)))
        buttons.addStretch(1)
        row.addLayout(buttons)
        return card

    def override(self, item):
        return item["schedule"].setdefault("overrides", {}).setdefault(item["date"], {})

    def edit(self, item):
        dialog = OverrideDialog(self, self.store, item)
        if dialog.exec():
            overrides = item["schedule"].setdefault("overrides", {})
            if dialog.result:
                overrides[item["date"]] = dialog.result
            else:
                overrides.pop(item["date"], None)
            self.store.save()
            self.refresh()

    def skip(self, item, on):
        over = self.override(item)
        over["skip"] = on
        if not on:
            del over["skip"]
            if not over:
                del item["schedule"]["overrides"][item["date"]]
        self.store.save()
        self.refresh()

    def schedule_now(self, item):
        if not ui.ask(self, "Schedule now", f"Create “{item['title']}” on the platforms now?"):
            return
        self.window_.work(lambda: engine.create_now(self.store, self.vault, item))


class SchedulesPage(Page):
    def __init__(self, window):
        super().__init__(window, "Schedules", "A schedule repeats every week and remembers the title and description.")
        self.actions.addWidget(ui.button("New schedule", "primary", lambda: self.edit(None)))

    def fill(self):
        if not self.store.schedules:
            self.empty("No schedule yet", "Example: every Sunday at 8:00 AM, created the Saturday before, titled "
                       "“Sunday Service - {date}”.", ui.button("New schedule", "primary", lambda: self.edit(None)))
        for s in self.store.schedules:
            card = ui.card()
            row = QHBoxLayout(card)
            row.setContentsMargins(18, 14, 16, 14)
            row.setSpacing(14)
            mid = QVBoxLayout()
            mid.setSpacing(5)
            mid.addWidget(ui.label(s["name"], "big"))
            mid.addWidget(ui.label(recurrence.describe(s, self.clock), "sub", wrap=True))
            template = ui.label(s["title"], wrap=True)
            template.setFont(ui.fixed_font(10))
            mid.addWidget(template)
            chips = QHBoxLayout()
            chips.setSpacing(6)
            dests = [d for d in (self.store.destination(i) for i in s["destinations"]) if d]
            for d in dests:
                chips.addWidget(ui.chip(f"{KIND_NAMES[d['kind']]} · {d['name']}"))
            if not dests:
                chips.addWidget(ui.chip("No destination chosen", "warn"))
            chips.addStretch(1)
            mid.addLayout(chips)
            row.addLayout(mid, 1)
            switch = ui.Switch(s.get("enabled", True))
            switch.setToolTip("Switch the schedule on or off")
            switch.toggled.connect(lambda on, s=s: self.enable(s, on))
            row.addWidget(switch, 0, Qt.AlignTop)
            row.addWidget(ui.button("Edit", "mini", lambda _=False, s=s: self.edit(s)), 0, Qt.AlignTop)
            delete = ui.button("Delete", "mini", lambda _=False, s=s: self.delete(s))
            row.addWidget(delete, 0, Qt.AlignTop)
            self.col.addWidget(card)

    def enable(self, schedule, on):
        schedule["enabled"] = on
        self.store.save()
        self.window_.side_status()

    def edit(self, schedule):
        dialog = ScheduleDialog(self, self.store, schedule)
        if dialog.exec():
            if schedule:
                self.store.schedules[self.store.schedules.index(schedule)] = dialog.schedule
            else:
                self.store.schedules.append(dialog.schedule)
            self.store.save()
            self.refresh()
            self.window_.side_status()

    def delete(self, schedule):
        if ui.ask(self, "Delete schedule", f"Delete “{schedule['name']}”? Streams it already created stay "
                                           "on the platforms."):
            self.store.schedules.remove(schedule)
            self.store.save()
            self.refresh()
            self.window_.side_status()


class DestinationsPage(Page):
    def __init__(self, window):
        super().__init__(window, "Destinations", "Where your streams are scheduled. A guide takes you through each step.")
        self.actions.addWidget(ui.button("Add YouTube", "primary", lambda: self.add(YouTubeWizard)))
        self.actions.addWidget(ui.button("Add Facebook Page", "primary", lambda: self.add(FacebookWizard)))
        self.results = {}

    def fill(self):
        if not self.store.destinations:
            self.empty("Nothing connected yet", "Add a YouTube channel or a Facebook Page. You can add several of each.")
        for d in self.store.destinations:
            card = ui.card()
            row = QHBoxLayout(card)
            row.setContentsMargins(18, 14, 16, 14)
            row.setSpacing(14)
            row.addWidget(ui.Icon(d["kind"], 34), 0, Qt.AlignTop)
            mid = QVBoxLayout()
            mid.setSpacing(4)
            mid.addWidget(ui.label(d["name"], "big"))
            if d["kind"] == "youtube":
                o = d.get("options", {})
                detail = (f"YouTube channel  ·  {o.get('privacy', 'public').capitalize()}  ·  "
                          f"Stream key: {o.get('stream_title') or 'chosen in YouTube Studio'}")
            else:
                detail = "Facebook Page  ·  each stream gets its own stream key (see History)"
            mid.addWidget(ui.label(detail, "sub", wrap=True))
            kind, text = self.results.get(d["id"], ("small", f"Sign-in kept in {self.vault.where()}"))
            mid.addWidget(ui.label(text, kind, wrap=True))
            row.addLayout(mid, 1)
            row.addWidget(ui.button("Test", "mini", lambda _=False, d=d: self.test(d),
                                    "Ask the platform whether the saved sign-in still works"), 0, Qt.AlignTop)
            if d["kind"] == "youtube":
                row.addWidget(ui.button("Options", "mini", lambda _=False, d=d: self.options(d)), 0, Qt.AlignTop)
            row.addWidget(ui.button("Remove", "mini", lambda _=False, d=d: self.remove(d)), 0, Qt.AlignTop)
            self.col.addWidget(card)
        self.col.addWidget(ui.callout(
            "Where your sign-ins are kept",
            f"Tokens and client secrets are stored in <b>{self.vault.where()}</b>, encrypted with your login to this "
            "computer. They are never written to the app's settings file, and they are sent only to Google and "
            "Meta. Removing a destination deletes its sign-in from this computer."))

    def add(self, wizard_class):
        wizard = wizard_class(self, self.store, self.vault)
        if wizard.exec():
            self.refresh()
            if self.store.schedules and ui.ask(self, "Add to schedules",
                                               f"Send every existing schedule to “{wizard.destination['name']}” too?"):
                for s in self.store.schedules:
                    s["destinations"].append(wizard.destination["id"])
                self.store.save()

    def options(self, dest):
        dialog = YouTubeOptionsDialog(self, dest)
        if dialog.exec():
            dest["options"] = dialog.options.value()
            self.store.save()
            self.refresh()

    def test(self, dest):
        self.results[dest["id"]] = ("small", "Testing ...")
        self.refresh()

        def work():
            if dest["kind"] == "youtube":
                token = youtube.access_token(dest["client_id"], self.vault.get(dest["id"], "client_secret"),
                                             self.vault.get(dest["id"], "refresh_token"))
                return youtube.channel(token)["title"]
            return facebook.page_name(dest["account_id"], self.vault.get(dest["id"], "page_token"))

        def done(name, error):
            self.results[dest["id"]] = ("error", str(error)) if error else ("good", f"✓  Works: connected to “{name}”")
            self.refresh()
        ui.run_async(work, done)

    def remove(self, dest):
        if not ui.ask(self, "Remove destination", f"Remove “{dest['name']}” and delete its sign-in from this "
                                                  "computer? Streams already created stay on the platform."):
            return
        self.vault.forget(dest["id"], dest["kind"])
        self.store.destinations.remove(dest)
        for s in self.store.schedules:
            if dest["id"] in s["destinations"]:
                s["destinations"].remove(dest["id"])
        self.store.save()
        self.refresh()


class HistoryPage(Page):
    COLUMNS = ["Stream", "Destination", "Title", "Result", "Created"]

    def __init__(self, window):
        super().__init__(window, "History", "Every stream the app created, or tried to create.")
        self.open_button = ui.button("Open", clicked=self.open)
        self.copy_button = ui.button("Copy link", clicked=self.copy)
        self.key_button = ui.button("Copy Facebook stream key", clicked=self.key,
                                    tip="The address and key for your encoder. Fetched now; never saved.")
        for b in (self.open_button, self.copy_button, self.key_button):
            self.actions.addWidget(b)
        self.table = None

    def fill(self):
        if not self.store.history:
            self.table = None
            self.empty("Nothing yet", "Created streams are listed here, with a link to each.")
            self.selected()
            return
        t = self.table = QTableWidget(len(self.store.history), len(self.COLUMNS))
        t.setHorizontalHeaderLabels(self.COLUMNS)
        t.verticalHeader().hide()
        t.setShowGrid(False)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.verticalHeader().setDefaultSectionSize(40)
        t.horizontalHeader().setHighlightSections(False)
        t.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        for row, e in enumerate(self.store.history):
            when, at = datetime.fromisoformat(e["when"]), datetime.fromisoformat(e["at"])
            ok = e["status"] == "created"
            cells = [short_day(when, self.clock), f"{KIND_NAMES.get(e['kind'], e['kind'])} · {e['destination_name']}",
                     e["title"], "✓ Scheduled" if ok else "Failed", short_day(at, self.clock)]
            for column, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                cell.setToolTip(e.get("note") or text if column == 3 else text)
                if column == 3:
                    cell.setForeground(QColor(ui.colors["ok" if ok else "no"]))
                t.setItem(row, column, cell)
        header = t.horizontalHeader()
        for column, mode in enumerate([QHeaderView.ResizeToContents, QHeaderView.Stretch, QHeaderView.Stretch,
                                       QHeaderView.ResizeToContents, QHeaderView.ResizeToContents]):
            header.setSectionResizeMode(column, mode)
        t.setMinimumHeight(min(560, 46 + 40 * len(self.store.history)))
        t.itemSelectionChanged.connect(self.selected)
        self.col.addWidget(t)
        self.note = ui.label("", "sub", wrap=True)
        self.col.addWidget(self.note)
        t.selectRow(0)

    def entry(self):
        if self.table is None or not self.table.selectionModel().selectedRows():
            return None
        return self.store.history[self.table.selectionModel().selectedRows()[0].row()]

    def selected(self):
        e = self.entry()
        if self.table is not None:
            self.note.setObjectName("error" if e and e["status"] != "created" else "sub")
            ui.set_prop(self.note, "x", 1)
            self.note.setText((e.get("note") or f"Attempts: {e.get('attempts', 1)}") if e else "")
        self.open_button.setEnabled(bool(e and e.get("url")))
        self.copy_button.setEnabled(bool(e and e.get("url")))
        self.key_button.setEnabled(bool(e and e["kind"] == "facebook" and e.get("remote_id")))

    def open(self):
        QDesktopServices.openUrl(QUrl(self.entry()["url"]))

    def copy(self):
        QGuiApplication.clipboard().setText(self.entry()["url"])

    def key(self):
        e = self.entry()

        def done(address, error):
            if error or not address:
                ui.tell(self, "Stream key", str(error) if error else "Facebook gave no stream address for this video.")
                return
            QGuiApplication.clipboard().setText(address)
            ui.tell(self, "Stream key", "The stream address (with its key) is on the clipboard. Paste it into your "
                                        "encoder.\n\nTreat it like a password: anyone who has it can stream to "
                                        "your Page.")
        ui.run_async(lambda: facebook.stream_address(e["remote_id"], self.vault.get(e["destination_id"], "page_token")),
                     done)


class SettingsPage(Page):
    def __init__(self, window):
        super().__init__(window, "Settings", f"{paths.APP_NAME} {paths.VERSION}")

    def fill(self):
        s = self.store.settings
        theme = ui.Segments([("auto", "Auto"), ("light", "Light"), ("dark", "Dark")], s["theme"])
        theme.changed.connect(lambda key: self.window_.set_theme(key))
        clock = ui.Segments([("12", "8:00 AM"), ("24", "08:00")], s["clock"])
        clock.changed.connect(lambda key: self.set("clock", key))
        tray = ui.Switch(s["tray"])
        tray.toggled.connect(lambda on: self.set("tray", on))
        auto = ui.Switch(s["autostart"])
        auto.toggled.connect(self.set_autostart)
        folder = ui.button("Open folder", clicked=lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(paths.data_dir())))
        self.section("Look", [("Theme", "Auto follows your system.", theme),
                              ("Times", "How times are shown, and written by {time}.", clock)])
        self.section("Running in the background", [
            ("Keep running when the window is closed",
             "The app stays in the tray (menu bar) so streams are still scheduled.", tray),
            ("Start when I log in", "Starts hidden in the tray. Without this, open the app before a stream is due; "
                                    "it catches up on what it missed.", auto)])
        self.section("Your data", [
            ("Settings and history", f"{paths.data_dir()}\nNo passwords or tokens are in this folder.", folder),
            ("Sign-ins", f"Kept in {self.vault.where()}. Remove a destination to delete its sign-in.", None)])
        self.col.addWidget(ui.callout(
            "The computer must be on", "Streams are created by this computer at the time you chose. If it is "
            "asleep or off at that time, the app creates them as soon as it runs again, as long as the stream is "
            "still more than 10 minutes away.", icon="upcoming"))

    def section(self, title, rows):
        self.col.addWidget(ui.label(title.upper(), "caps"))
        card = ui.card()
        box = QVBoxLayout(card)
        box.setContentsMargins(18, 6, 18, 6)
        box.setSpacing(0)
        for i, (name, hint, widget) in enumerate(rows):
            if i:
                box.addWidget(ui.rule())
            row = QHBoxLayout()
            row.setContentsMargins(0, 11, 0, 11)
            words = QVBoxLayout()
            words.setSpacing(2)
            words.addWidget(ui.label(name, "strong"))
            words.addWidget(ui.label(hint, "small", wrap=True))
            row.addLayout(words, 1)
            if widget:
                row.addWidget(widget, 0, Qt.AlignVCenter)
            box.addLayout(row)
        self.col.addWidget(card)

    def set(self, key, value):
        self.store.settings[key] = value
        self.store.save()

    def set_autostart(self, on):
        try:
            autostart.set_enabled(on)
        except OSError as exc:
            ui.tell(self, "Start at login", f"The system refused: {exc}")
            self.refresh()
            return
        self.set("autostart", on)


class MainWindow(QMainWindow):
    PAGES = [("upcoming", "Upcoming", UpcomingPage), ("schedules", "Schedules", SchedulesPage),
             ("destinations", "Destinations", DestinationsPage), ("history", "History", HistoryPage),
             ("settings", "Settings", SettingsPage)]

    def __init__(self, store, vault, background=True):
        super().__init__()
        self.store, self.vault = store, vault
        self.busy = False
        self.last_check = None
        self.quitting = False
        self.told_tray = False
        self.setWindowTitle(paths.APP_NAME)
        self.resize(1120, 740)
        self.setMinimumSize(900, 600)
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        side = QFrame()
        side.setObjectName("side")
        side.setFixedWidth(224)
        col = QVBoxLayout(side)
        col.setContentsMargins(14, 20, 14, 16)
        col.setSpacing(4)
        brand = QHBoxLayout()
        brand.setContentsMargins(6, 0, 0, 14)
        brand.setSpacing(10)
        brand.addWidget(ui.Logo(34))
        brand.addWidget(ui.label(paths.APP_NAME, "appname"), 1)
        col.addLayout(brand)
        self.stack = QStackedWidget()
        self.nav, self.pages = [], []
        for index, (icon, name, page_class) in enumerate(self.PAGES):
            b = ui.NavButton(icon, name)
            b.clicked.connect(lambda _=False, i=index: self.show_page(i))
            col.addWidget(b)
            self.nav.append(b)
            page = page_class(self)
            self.pages.append(page)
            self.stack.addWidget(page)
        col.addStretch(1)
        status = QHBoxLayout()
        status.setContentsMargins(8, 0, 0, 0)
        status.setSpacing(8)
        self.dot = ui.Dot()
        self.status = ui.label("", "small", wrap=True)
        status.addWidget(self.dot, 0, Qt.AlignTop)
        status.addWidget(self.status, 1)
        col.addLayout(status)
        row.addWidget(side)
        row.addWidget(self.stack, 1)

        self.tray = None
        if background and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(ui.app_icon(), self)
            self.tray.setToolTip(paths.APP_NAME)
            menu = QMenu()
            menu.addAction("Open Stream Scheduler", self.open_window)
            menu.addAction("Check now", self.check)
            menu.addSeparator()
            menu.addAction("Quit", self.quit)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda why: self.open_window() if why == QSystemTrayIcon.Trigger else None)
            self.tray.show()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check)
        if background:
            self.timer.start(CHECK_EVERY_MS)
            QTimer.singleShot(1500, self.check)   # catch up on what was missed while the app was closed
        self.show_page(0)

    def show_page(self, index):
        self.nav[index].setChecked(True)
        self.stack.setCurrentIndex(index)
        self.pages[index].refresh()
        self.side_status()

    def refresh(self):
        self.pages[self.stack.currentIndex()].refresh()
        self.side_status()

    def side_status(self):
        active = [s for s in self.store.schedules if s.get("enabled", True)]
        on = bool(active and self.store.destinations)
        self.dot.color = "ok" if on else "off"
        self.dot.update()
        if self.busy:
            text = "Working ..."
        elif not on:
            text = "Not scheduling yet"
        else:
            clock = self.store.settings.get("clock", "12")
            checked = f"\nLast check {titles.format_time(self.last_check, clock)}" if self.last_check else ""
            text = f"Auto-scheduling is on{checked}"
        self.status.setText(text)

    def set_theme(self, theme):
        self.store.settings["theme"] = theme
        self.store.save()
        ui.apply_theme(QApplication.instance(), theme)
        self.refresh()

    # ---- the work ----
    def check(self):
        self.work(lambda: engine.run_due(self.store, self.vault))

    def work(self, fn):
        """Run engine work off the window's thread, one at a time, then show what happened."""
        if self.busy:
            return
        self.busy = True
        self.pages[0].check_button.setEnabled(False)
        self.side_status()
        ui.run_async(fn, self.worked)

    def worked(self, entries, error):
        self.busy = False
        self.last_check = datetime.now()
        self.pages[0].check_button.setEnabled(True)
        self.refresh()
        entries = entries or []
        made = [e for e in entries if e["status"] == "created"]
        failed = [e for e in entries if e["status"] != "created"]
        if self.tray and (made or failed or error):
            if failed or error:
                first = failed[0] if failed else None
                self.tray.showMessage("A stream could not be scheduled",
                                      f"{first['title']} ({first['destination_name']}): {first['note']}" if first
                                      else str(error), QSystemTrayIcon.Warning)
            else:
                self.tray.showMessage("Stream scheduled", f"{made[0]['title']} is scheduled on " + " and ".join(
                    sorted({KIND_NAMES.get(e['kind'], e['kind']) for e in made})) + ".", QSystemTrayIcon.Information)

    # ---- window and tray ----
    def open_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.refresh()

    def quit(self):
        self.quitting = True
        QApplication.instance().quit()

    def closeEvent(self, event):
        if self.tray and self.store.settings.get("tray", True) and not self.quitting:
            event.ignore()
            self.hide()
            if not self.told_tray:
                self.told_tray = True
                self.tray.showMessage(paths.APP_NAME, "Still running here, so your streams are scheduled on time. "
                                                      "Right-click the icon to quit.", QSystemTrayIcon.Information)
        else:
            event.accept()
            self.quit()
