"""Stream Scheduler: schedules your YouTube and Facebook live streams by itself.

  python app.py            the window
  python app.py --tray     start hidden in the tray (used by "Start when I log in")
  python app.py --run      no window: create the streams that are due, print what happened, and exit
                           (for the system's task scheduler / cron). Does nothing while the window runs.
  python app.py --uitest   make every window once, off screen, with made-up data (a self-test)
"""
import os
import sys

import paths


def lock():
    """Only one copy of the app may work at a time, or a stream could be created twice."""
    from PySide6.QtCore import QLockFile
    held = QLockFile(os.path.join(paths.data_dir(), "app.lock"))
    held.setStaleLockTime(0)   # a lock left by a crash is noticed by its dead process, not by its age
    return held if held.tryLock(200) else None


def run_once():
    import engine
    from store import Store
    from vault import Vault
    held = lock()
    if held is None:
        print("Stream Scheduler is already running; it does this work itself.")
        return 0
    entries = engine.run_due(Store(), Vault())
    for e in entries:
        print(f"{e['status']:8} {e['kind']:9} {e['when']}  {e['title']}  {e['note']}")
    if not entries:
        print("Nothing is due.")
    return 1 if any(e["status"] != "created" for e in entries) else 0


def uitest():
    import tempfile
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    with tempfile.TemporaryDirectory() as folder:
        os.environ["STREAM_SCHEDULER_DATA_DIR"] = folder
        import demo
        import ui
        from dialogs import OverrideDialog, ScheduleDialog, YouTubeOptionsDialog
        from mainwindow import MainWindow
        from store import Store
        from vault import MemoryVault
        from wizards import FacebookWizard, WixWizard, YouTubeWizard
        import engine
        for theme in ("light", "dark"):
            store, vault = Store(), MemoryVault()
            store.destinations.clear(), store.schedules.clear(), store.history.clear()
            app = ui.start_app(sys.argv[:1], theme)
            empty = MainWindow(store, vault, background=False)
            for i in range(len(empty.pages)):
                empty.show_page(i)
            demo.fill(store, vault)
            window = MainWindow(store, vault, background=False)
            for i in range(len(window.pages)):
                window.show_page(i)
                window.grab()
            made = [ScheduleDialog(window, store), ScheduleDialog(window, store, store.schedules[0]),
                    OverrideDialog(window, store, engine.upcoming(store)[0]),
                    YouTubeOptionsDialog(window, store.destinations[0])]
            for wizard in (YouTubeWizard(window, store, vault), FacebookWizard(window, store, vault),
                           WixWizard(window, store, vault)):
                for i in range(len(wizard.checks)):
                    wizard.go(i)
                    wizard.grab()
                made.append(wizard)
            for dialog in made:
                dialog.grab()
            app.processEvents()
    import importlib
    backend = {"win32": "Windows", "darwin": "macOS"}.get(sys.platform, "SecretService")
    importlib.import_module("keyring.backends." + backend)   # a built program must carry its keychain
    import truststore  # noqa: F401
    print("uitest ok")
    return 0


def main(argv):
    if "--version" in argv:
        print(paths.VERSION)
        return 0
    if "--run" in argv:
        return run_once()
    if "--uitest" in argv:
        return uitest()
    import ui
    from mainwindow import MainWindow
    from PySide6.QtWidgets import QMessageBox
    from store import Store
    from vault import Vault
    store = Store()
    app = ui.start_app(argv, store.settings["theme"])
    held = lock()
    if held is None:
        QMessageBox.information(None, paths.APP_NAME, "Stream Scheduler is already running. Look for its icon in "
                                                      "the tray (menu bar).")
        return 0
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow(store, Vault())
    if "--tray" not in argv or window.tray is None:
        window.show()
    code = app.exec()
    held.unlock()
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
