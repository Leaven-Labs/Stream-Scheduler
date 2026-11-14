"""Make the pictures of the README (docs/*.png) with made-up data, off screen.
Run from the repository: python tools/screenshots.py"""
import os
import sys
import tempfile

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
from wizards import FacebookWizard, YouTubeWizard  # noqa: E402

out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, "docs")
os.makedirs(out, exist_ok=True)
for theme in ("dark", "light"):
    store, vault = Store(), MemoryVault()
    store.destinations.clear(), store.schedules.clear(), store.history.clear()
    app = ui.start_app(sys.argv[:1], theme)
    demo.fill(store, vault)
    window = MainWindow(store, vault, background=False)
    window.resize(1120, 740)
    shots = []
    for i, (name, _, _) in enumerate(window.PAGES):
        window.show_page(i)
        shots.append((name, window))
        app.processEvents()
        window.grab().save(os.path.join(out, f"{name}-{theme}.png"))
    extra = {"schedule": ScheduleDialog(window, store, store.schedules[0])}
    yt, fb = YouTubeWizard(window, store, vault), FacebookWizard(window, store, vault)
    yt.go(2)
    fb.go(3)
    extra.update({"wizard-youtube": yt, "wizard-facebook": fb})
    for name, dialog in extra.items():
        app.processEvents()
        dialog.grab().save(os.path.join(out, f"{name}-{theme}.png"))
print("saved to", out)
