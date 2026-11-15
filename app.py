"""Stream Scheduler: schedules your YouTube and Facebook live streams by itself.

  python app.py            the window
  python app.py --tray     start hidden in the tray (used by "Start when I log in")
  python app.py --run      no window: create the streams that are due, print what happened, and exit
                           (for the system's task scheduler / cron). Does nothing while the window runs.
  python app.py --quit     ask the copy that is running to stop, and wait until it has (used by the installer)
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


def control_name():
    """The name of the running copy's private line (one per user: it comes from the data folder)."""
    import hashlib
    return "stream-scheduler-" + hashlib.sha256(paths.data_dir().encode()).hexdigest()[:16]


def listen(window):
    """Let `--quit` stop this copy properly (an installer must not replace files that are in use)."""
    from PySide6.QtNetwork import QLocalServer
    server = QLocalServer(window)
    server.setSocketOptions(QLocalServer.UserAccessOption)
    QLocalServer.removeServer(control_name())   # we hold the lock, so a name left behind is a crashed copy's

    def connected():
        line = server.nextPendingConnection()
        line.readyRead.connect(lambda: window.quit() if bytes(line.readAll()).startswith(b"quit") else None)
    server.newConnection.connect(connected)
    server.listen(control_name())


def quit_running():
    """Ask the running copy to stop and wait until it has. 0 when no copy is left running."""
    import time
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtNetwork import QLocalSocket
    app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])  # noqa: F841
    line = QLocalSocket()
    line.connectToServer(control_name())
    if line.waitForConnected(2000):
        line.write(b"quit")
        line.waitForBytesWritten(2000)
        line.disconnectFromServer()
    for _ in range(50):
        held = lock()
        if held is not None:
            held.unlock()
            return 0
        time.sleep(0.2)
    return 1


def run_once():
    import engine
    from store import Store
    from vault import Vault
    held = lock()
    if held is None:
        print("Stream Scheduler is already running; it does this work itself.")
        return 0
    import notify
    store, vault = Store(), Vault()
    entries = notify.after(store, vault, engine.run_due(store, vault))
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
        from dialogs import AboutDialog, OverrideDialog, PreviewDialog, ScheduleDialog, YouTubeOptionsDialog
        from mainwindow import MainWindow
        from store import Store
        from vault import MemoryVault
        from wizards import (NOTIFY_WIZARDS, FacebookWizard, WebhookWizard, WixWizard, WordPressWizard,
                             YouTubeWizard)
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
                    YouTubeOptionsDialog(window, store.destinations[0]),
                    PreviewDialog(window, store, store.schedules[0]), AboutDialog(window)]
            for wizard in [YouTubeWizard(window, store, vault), FacebookWizard(window, store, vault),
                           WixWizard(window, store, vault), WordPressWizard(window, store, vault),
                           WebhookWizard(window, store, vault)] + [w(window, store, vault)
                                                                   for w in NOTIFY_WIZARDS.values()]:
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
    from PySide6 import QtNetwork  # noqa: F401 (the line that --quit uses)
    print("uitest ok")
    return 0


def main(argv):
    if "--version" in argv:
        print(paths.VERSION)
        return 0
    if "--quit" in argv:
        return quit_running()
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
    listen(window)
    if "--tray" not in argv or window.tray is None:
        window.show()
    code = app.exec()
    held.unlock()
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
