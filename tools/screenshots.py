"""Make the pictures of the README and the website with made-up data, off screen.
Run from the repository: python tools/screenshots.py [folder]

The pictures are taken as if it were TODAY, a Sunday in Lent, so that the made-up Lent series is under
way and the dates agree with the church year whenever the script is run.
"""
import os
import sys
import tempfile
from datetime import datetime

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, root)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["STREAM_SCHEDULER_DATA_DIR"] = tempfile.mkdtemp()

import demo  # noqa: E402
import ui  # noqa: E402
from dialogs import ScheduleDialog  # noqa: E402
from mainwindow import MainWindow  # noqa: E402
from store import Store  # noqa: E402
from vault import MemoryVault  # noqa: E402
from wizards import WixWizard, YouTubeWizard  # noqa: E402
from PySide6.QtCore import QDate  # noqa: E402

TODAY = datetime(2027, 2, 28, 14, 46)   # the second Sunday in Lent (Easter 2027 is March 28)


class _Now(datetime):
    @classmethod
    def now(cls, tz=None):
        return TODAY


class _Today(QDate):
    @staticmethod
    def currentDate():
        return QDate(TODAY.year, TODAY.month, TODAY.day)


for module in list(sys.modules.values()):   # the app's own modules ask these for the time
    if os.path.dirname(getattr(module, "__file__", None) or "") == root:
        if getattr(module, "datetime", None) is datetime:
            module.datetime = _Now
        if getattr(module, "QDate", None) is QDate:
            module.QDate = _Today

out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, "docs")
os.makedirs(out, exist_ok=True)
for theme in ("dark", "light"):
    store, vault = Store(), MemoryVault()
    store.destinations.clear(), store.schedules.clear(), store.history.clear()
    app = ui.start_app(sys.argv[:1], theme)
    demo.fill(store, vault, TODAY)
    window = MainWindow(store, vault, background=False)
    window.resize(1120, 740)
    shots = []
    for i, (name, _, _) in enumerate(window.PAGES):
        window.show_page(i)
        shots.append((name, window))
        app.processEvents()
        window.grab().save(os.path.join(out, f"{name}-{theme}.png"))
    extra = {"schedule": ScheduleDialog(window, store, store.schedules[0])}
    yt, wx = YouTubeWizard(window, store, vault), WixWizard(window, store, vault)
    yt.go(3)
    extra.update({"wizard-youtube": yt})
    for step in range(len(wx.checks)):
        wx.go(step)
        app.processEvents()
        wx.grab().save(os.path.join(out, f"wizard-wix-{step + 1}-{theme}.png"))
    for name, dialog in extra.items():
        app.processEvents()
        dialog.grab().save(os.path.join(out, f"{name}-{theme}.png"))
print("saved to", out)
