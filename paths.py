"""Where the app's files live.

- data_dir(): the user's files (config.json: destinations, schedules, history, settings).
  Windows %APPDATA%\\Stream Scheduler, Mac ~/Library/Application Support/Stream Scheduler,
  Linux ~/.config/stream-scheduler ($XDG_CONFIG_HOME if set). STREAM_SCHEDULER_DATA_DIR
  overrides it (for tests, or a portable folder).
Passwords and tokens are NOT in that folder: they are in the system's keychain (see vault.py).
"""
import os
import sys

APP_NAME = "Stream Scheduler"
APP_SLUG = "stream-scheduler"
VERSION = "0.0.5-alpha"
AUTHOR = "Aaron Steger"
COPYRIGHT = f"Copyright (c) 2026 {AUTHOR}"
PUBLISHER = "Leaven Labs"
PUBLISHER_URL = "https://www.leavenlabs.org/"
PROJECT_URL = "https://github.com/Leaven-Labs/Stream-Scheduler"
LICENSE_URL = PROJECT_URL + "/blob/main/LICENSE"


def program_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def data_dir():
    override = os.environ.get("STREAM_SCHEDULER_DATA_DIR")
    if override:
        path = override
    elif sys.platform == "win32":
        path = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME)
    elif sys.platform == "darwin":
        path = os.path.join(os.path.expanduser("~/Library/Application Support"), APP_NAME)
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
        path = os.path.join(base, APP_SLUG)
    os.makedirs(path, exist_ok=True)
    return path
