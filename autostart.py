"""Start the app when the user logs in (hidden, in the tray), so streams are scheduled without anyone
opening it. Windows: a value under HKCU\\...\\Run. Mac: a LaunchAgent. Linux: an autostart .desktop file.
"""
import os
import sys

import paths

_MAC = os.path.expanduser("~/Library/LaunchAgents/com.leavenlabs.stream-scheduler.plist")
_LINUX = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "autostart",
                      f"{paths.APP_SLUG}.desktop")
_WIN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def command():
    if getattr(sys, "frozen", False):
        return [sys.executable, "--tray"]
    exe = sys.executable
    if sys.platform == "win32" and exe.lower().endswith("python.exe"):  # no console window
        exe = exe[:-len("python.exe")] + "pythonw.exe"
    return [exe, os.path.join(paths.program_dir(), "app.py"), "--tray"]


def set_enabled(on):
    """Switch starting at login on or off. Raises OSError when the system refuses."""
    cmd = command()
    if sys.platform == "win32":
        import subprocess
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if on:
                winreg.SetValueEx(key, paths.APP_NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(cmd))
            else:
                try:
                    winreg.DeleteValue(key, paths.APP_NAME)
                except FileNotFoundError:
                    pass
        return
    path = _MAC if sys.platform == "darwin" else _LINUX
    if not on:
        if os.path.exists(path):
            os.remove(path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if sys.platform == "darwin":
        import plistlib
        with open(path, "wb") as fh:
            plistlib.dump({"Label": "com.leavenlabs.stream-scheduler", "ProgramArguments": cmd,
                           "RunAtLoad": True}, fh)
    else:
        quoted = " ".join('"' + part.replace('"', '\\"') + '"' for part in cmd)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"[Desktop Entry]\nType=Application\nName={paths.APP_NAME}\nExec={quoted}\n"
                     "X-GNOME-Autostart-enabled=true\n")
