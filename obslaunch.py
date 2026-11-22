"""Opening OBS Studio on this computer at a set time before a service, so it is ready to be checked.

The app only starts OBS when it is not running. It never closes OBS, never opens a second copy and
never passes --startstreaming: going live stays with a person. OBS is started from its own program
folder (it does not find its files otherwise) with --disable-shutdown-check, so the "Safe Mode?"
question that OBS asks after a crash cannot block a start with nobody at the computer.
"""
import os
import shutil
import subprocess
import sys

WINDOWS_EXE = os.path.join("bin", "64bit", "obs64.exe")
MAC_APP = "/Applications/OBS.app"
FLATPAK = "com.obsproject.Studio"


def _windows_registry():
    """The folder the OBS installer wrote in the registry, or ""."""
    try:
        import winreg
    except ImportError:
        return ""
    for root, view in ((winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
                       (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY), (winreg.HKEY_CURRENT_USER, 0)):
        try:
            with winreg.OpenKey(root, r"SOFTWARE\OBS Studio", 0, winreg.KEY_READ | view) as key:
                folder = winreg.QueryValueEx(key, "")[0]
                if folder:
                    return folder
        except OSError:
            continue
    return ""


def candidates(platform=None, env=None, registry=None):
    """Where OBS may be, most likely first."""
    platform, env = platform or sys.platform, env if env is not None else os.environ
    if platform == "win32":
        folders = [registry if registry is not None else _windows_registry()]
        folders += [os.path.join(env[k], "obs-studio") for k in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)")
                    if env.get(k)]
        folders.append(r"C:\Program Files\obs-studio")
        return [os.path.join(f, WINDOWS_EXE) for f in folders if f]
    if platform == "darwin":
        return [MAC_APP, os.path.expanduser("~/Applications/OBS.app")]
    found = shutil.which("obs")
    return ([found] if found else []) + ["/usr/bin/obs", "/usr/local/bin/obs", "flatpak:" + FLATPAK]


def find(chosen="", exists=os.path.exists, **where):
    """The OBS program: the one the user chose, or the first that is there. "" when none is found."""
    if chosen:
        return chosen if exists(chosen) else ""
    for path in candidates(**where):
        if path.startswith("flatpak:"):
            installed = exists(f"/var/lib/flatpak/app/{FLATPAK}") or exists(
                os.path.expanduser(f"~/.local/share/flatpak/app/{FLATPAK}"))
            if installed and shutil.which("flatpak"):
                return path
        elif exists(path):
            return path
    return ""


def command(program, profile="", collection="", platform=None):
    """(argv, folder to start in) for starting OBS."""
    platform = platform or sys.platform
    extra = ["--disable-shutdown-check"]
    if profile:
        extra += ["--profile", profile]
    if collection:
        extra += ["--collection", collection]
    if program.startswith("flatpak:"):
        return ["flatpak", "run", program.split(":", 1)[1]] + extra, None
    if platform == "darwin" and program.endswith(".app"):
        return ["open", "-a", program, "--args"] + extra, None
    return [program] + extra, os.path.dirname(program) or None


def running(platform=None):
    """Whether OBS is running on this computer (its remote control may be switched off). None when this
    cannot be told."""
    platform = platform or sys.platform
    try:
        if platform == "win32":
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq obs64.exe", "/NH"], capture_output=True,
                                 text=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return "obs64.exe" in out.stdout.lower()
        name = "OBS" if platform == "darwin" else "obs"
        return subprocess.run(["pgrep", "-x", name], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return None


def launch(program, profile="", collection=""):
    """Start OBS, detached from this app (closing the app leaves OBS open). Raises OSError."""
    argv, folder = command(program, profile, collection)
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(argv, cwd=folder, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True, creationflags=flags,
                     start_new_session=sys.platform != "win32")
