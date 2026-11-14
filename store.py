"""The app's saved data: one JSON file (config.json) with settings, destinations, schedules and history.

No secrets are written here. A destination holds only what is safe to read (its name, the channel or
Page id, the OAuth client id); its tokens are in the system keychain (vault.py), found by its id.
"""
import json
import os
import secrets
import threading

import paths

DEFAULT_SETTINGS = {"theme": "auto", "clock": "12", "tray": True, "autostart": False}
HISTORY_LIMIT = 500


def new_id():
    return secrets.token_hex(6)


class Store:
    def __init__(self, path=None):
        self.path = path or os.path.join(paths.data_dir(), "config.json")
        self.lock = threading.RLock()
        self.data = {}
        self.load()

    def load(self):
        with self.lock:
            try:
                with open(self.path, encoding="utf-8") as fh:
                    data = json.load(fh)
            except FileNotFoundError:
                data = {}
            if not isinstance(data, dict):
                raise ValueError(f"{self.path} is not a settings file")
            data.setdefault("version", 1)
            data["settings"] = {**DEFAULT_SETTINGS, **data.get("settings", {})}
            for key in ("destinations", "schedules", "history"):
                data.setdefault(key, [])
            self.data = data

    def save(self):
        """Write to a new file, then swap it in: a crash never leaves half a file."""
        with self.lock:
            tmp = self.path + ".tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)

    settings = property(lambda self: self.data["settings"])
    destinations = property(lambda self: self.data["destinations"])
    schedules = property(lambda self: self.data["schedules"])
    history = property(lambda self: self.data["history"])

    def destination(self, dest_id):
        return next((d for d in self.destinations if d["id"] == dest_id), None)

    def schedule(self, schedule_id):
        return next((s for s in self.schedules if s["id"] == schedule_id), None)

    def entry(self, schedule_id, date_key, dest_id):
        """The history line of one stream (a schedule's date) at one destination, or None."""
        for e in self.history:
            if (e["schedule_id"], e["date"], e["destination_id"]) == (schedule_id, date_key, dest_id):
                return e
        return None

    def put_entry(self, entry):
        with self.lock:
            old = self.entry(entry["schedule_id"], entry["date"], entry["destination_id"])
            if old is not None:
                self.history.remove(old)
            self.history.insert(0, entry)
            del self.history[HISTORY_LIMIT:]
            self.save()
