"""Windows only: a streaming PC that runs with nobody at it ("Unattended PC" in Settings).

Three things, each switched on separately and all off by default:

- Lock right after it starts. A Task Scheduler task, "At log on" for this account, runs the app with
  --lock-after-boot. That only locks when Windows has been running for less than two minutes, so the
  automatic sign-in at boot is locked and a person who signs in later is not. Windows cannot tell an
  automatic sign-in from a person's in any other way.
- Wake before streams. One Task Scheduler task with "Wake the computer to run this task", its times
  rewritten when the coming streams change: a few minutes before a stream is created, and before OBS
  is opened or first checked. It wakes from sleep or hibernation, not from a full shut-down.
- Automatic sign-in. The same as Sysinternals Autologon and Windows' own netplwiz: AutoAdminLogon,
  DefaultUserName and DefaultDomainName under Winlogon, and the password as the protected LSA secret
  "DefaultPassword", never as plain text in the registry. Writing them needs administrator rights, so
  that part runs in a separate, elevated copy of the app (--elevated), which asks for the password
  itself: the password is never put on a command line. It checks the password with Windows first and
  refuses an account that is an administrator.

Everything that touches Windows is behind a function, so the rest can be tested on any system.
"""
import ctypes
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from xml.sax.saxutils import escape

import paths

TASK_FOLDER = "\\Stream Scheduler\\"
LOCK_TASK = TASK_FOLDER + "Lock after start"
WAKE_TASK = TASK_FOLDER + "Wake before streams"
LOCK_WITHIN = timedelta(minutes=2)     # a sign-in this soon after Windows started is the automatic one
WAKE_EARLY = timedelta(minutes=5)
WAKE_AHEAD = timedelta(days=14)
WAKE_MAX = 24                          # times in the wake task at once
WINLOGON = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
PASSWORDLESS = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\PasswordLess\Device"

# what an elevated copy's exit code means
DONE, CANCELLED, REFUSED_ADMIN, FAILED = 0, 10, 12, 13


class WinSetupError(Exception):
    pass


def supported():
    return sys.platform == "win32"


def program(*args):
    """The command that starts this app with `args` (no console window)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        exe = exe[:-len("python.exe")] + "pythonw.exe"
    return [exe, os.path.join(paths.program_dir(), "app.py"), *args]


def current_account():
    """(domain, user) of whoever runs the app."""
    return os.environ.get("USERDOMAIN", ""), os.environ.get("USERNAME", "")


def account_name(domain, user):
    return f"{domain}\\{user}" if domain else user


# ---- Task Scheduler ---------------------------------------------------------------------------

def _exec_xml(argv):
    command = subprocess.list2cmdline(argv[:1])
    arguments = subprocess.list2cmdline(argv[1:])
    return (f"<Exec><Command>{escape(command)}</Command>"
            + (f"<Arguments>{escape(arguments)}</Arguments>" if arguments else "") + "</Exec>")


def task_xml(account, triggers, argv, wake=False, description=""):
    """A Task Scheduler task (its XML) that runs `argv` as `account`, only while it is signed in."""
    return ("<?xml version=\"1.0\" encoding=\"UTF-16\"?>\n"
            "<Task version=\"1.2\" xmlns=\"http://schemas.microsoft.com/windows/2004/02/mit/task\">"
            f"<RegistrationInfo><Author>{escape(paths.APP_NAME)}</Author>"
            f"<Description>{escape(description)}</Description></RegistrationInfo>"
            f"<Triggers>{triggers}</Triggers>"
            f"<Principals><Principal id=\"Author\"><UserId>{escape(account)}</UserId>"
            "<LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>"
            "<Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>"
            "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>"
            "<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>"
            "<StartWhenAvailable>true</StartWhenAvailable>"
            f"<WakeToRun>{'true' if wake else 'false'}</WakeToRun>"
            "<ExecutionTimeLimit>PT10M</ExecutionTimeLimit><Priority>5</Priority></Settings>"
            f"<Actions Context=\"Author\">{_exec_xml(argv)}</Actions></Task>")


def lock_task_xml(account):
    return task_xml(account, f"<LogonTrigger><UserId>{escape(account)}</UserId></LogonTrigger>",
                    program("--lock-after-boot"),
                    description="Locks this computer right after it signs in by itself at start-up "
                                "(Stream Scheduler, Settings → Unattended PC).")


def wake_task_xml(account, times):
    triggers = "".join(f"<TimeTrigger><StartBoundary>{t.strftime('%Y-%m-%dT%H:%M:%S')}</StartBoundary>"
                       "</TimeTrigger>" for t in times)
    return task_xml(account, triggers, program("--run"), wake=True,
                    description="Wakes this computer from sleep before a stream is created and before OBS is "
                                "opened or checked (Stream Scheduler, Settings → Unattended PC).")


def _run(argv, timeout=30):
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, creationflags=flags)
    except (OSError, subprocess.SubprocessError) as exc:
        raise WinSetupError(str(exc)) from None


def create_task(name, xml):
    """Make or replace a task. Raises WinSetupError (with Windows' words) when it is refused."""
    folder = tempfile.mkdtemp()
    path = os.path.join(folder, "task.xml")
    try:
        with open(path, "w", encoding="utf-16") as fh:
            fh.write(xml)
        done = _run(["schtasks", "/Create", "/TN", name, "/XML", path, "/F"])
    finally:
        try:
            os.remove(path)
            os.rmdir(folder)
        except OSError:
            pass
    if done.returncode:
        raise WinSetupError((done.stderr or done.stdout).strip() or "Task Scheduler refused the task.")


def delete_task(name):
    _run(["schtasks", "/Delete", "/TN", name, "/F"])   # one that is not there is fine


def task_exists(name):
    try:
        return _run(["schtasks", "/Query", "/TN", name]).returncode == 0
    except WinSetupError:
        return False


# ---- lock after start ------------------------------------------------------------------------

def uptime():
    ticks = ctypes.windll.kernel32.GetTickCount64
    ticks.restype = ctypes.c_ulonglong
    return timedelta(milliseconds=ticks())


def lock_now():
    if not ctypes.windll.user32.LockWorkStation():
        raise WinSetupError("Windows did not lock.")


def lock_after_boot(up=None, lock=None):
    """--lock-after-boot: lock when Windows started less than two minutes ago. True when it locked."""
    up = uptime() if up is None else up
    if up >= LOCK_WITHIN:
        return False
    (lock or lock_now)()
    return True


def set_lock_task(on, account=None, elevate=None):
    """Make or remove the lock task. When Windows wants administrator rights to make it, ask for them
    once (`elevate` is run_elevated). Raises WinSetupError."""
    account = account or account_name(*current_account())
    if not on:
        delete_task(LOCK_TASK)
        return
    try:
        create_task(LOCK_TASK, lock_task_xml(account))
    except WinSetupError:
        code = (elevate or run_elevated)(["lock-task", "--account", account])
        if code != DONE:
            raise WinSetupError("The lock was not set up: administrator approval was not given."
                                if code == CANCELLED else "The lock could not be set up.") from None


# ---- wake before streams ---------------------------------------------------------------------

def wake_times(store, now=None):
    """When to wake the computer: a few minutes before each coming stream is created, and before its OBS
    is opened or first checked. Soonest first, at most WAKE_MAX, within two weeks."""
    import engine
    now = now or datetime.now()
    times = set()
    for item in engine.upcoming(store, now, limit=1000):
        if item["skipped"] or item["when"] - now > WAKE_AHEAD:
            continue
        moments = [item["create_at"]]
        encoder = store.encoder(item["schedule"].get("encoder_id"))
        if encoder:
            first = engine.obs_first_check(item)
            if first:
                moments.append(first)
            minutes = engine.obs_open_minutes(item["schedule"])
            if encoder.get("local") and minutes:
                moments.append(item["when"] - timedelta(minutes=minutes))
        for moment in moments:
            wake = (moment - WAKE_EARLY).replace(second=0, microsecond=0)
            if wake > now:
                times.add(wake)
    return sorted(times)[:WAKE_MAX]


def sync_wake(store, now=None, create=None, delete=None):
    """Keep the wake task in step with the coming streams (called after each round of work). Rewrites it
    only when the times change. Returns an error sentence, or ""."""
    s = store.settings
    written = s.get("wake_written", None)
    if not s.get("wake_before_stream"):
        if written is not None:
            (delete or delete_task)(WAKE_TASK)
            s.pop("wake_written", None)
            store.save()
        return ""
    times = [t.strftime("%Y-%m-%dT%H:%M") for t in wake_times(store, now)]
    if times == written:
        return ""
    try:
        (create or create_task)(WAKE_TASK, wake_task_xml(account_name(*current_account()),
                                                         [datetime.fromisoformat(t) for t in times]))
    except WinSetupError as exc:
        s["wake_error"] = str(exc)
        store.save()
        return str(exc)
    s["wake_written"] = times
    s.pop("wake_error", None)
    store.save()
    return ""


def wake_timers_allowed():
    """Whether the power plan lets tasks wake the computer (on mains power): True, False, or None when
    unknown. Read from powercfg; the setting's id is fixed (RTCWAKE)."""
    done = _run(["powercfg", "/query", "SCHEME_CURRENT", "SUB_SLEEP", "BD3B718A-0680-4D9D-8AB2-E1D2B4AC806D"])
    if done.returncode:
        return None
    for line in done.stdout.splitlines():
        if "AC" in line and "0x" in line:   # "Current AC Power Setting Index: 0x00000001"
            return int(line.rsplit("0x", 1)[1].strip(), 16) != 0
    return None


# ---- automatic sign-in -----------------------------------------------------------------------

def autologon_state():
    """{"on", "user", "domain"} as Windows has it now (readable without administrator rights)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, WINLOGON, 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            def value(name):
                try:
                    return str(winreg.QueryValueEx(key, name)[0])
                except OSError:
                    return ""
            return {"on": value("AutoAdminLogon").strip() == "1", "user": value("DefaultUserName"),
                    "domain": value("DefaultDomainName")}
    except (ImportError, OSError):
        return {"on": False, "user": "", "domain": ""}


def autologon_is_mine():
    state = autologon_state()
    domain, user = current_account()
    return state["on"] and state["user"].lower() == user.lower() and (
        not state["domain"] or state["domain"].lower() == domain.lower())


def hello_only():
    """Whether Windows 11's "only allow Windows Hello sign-in for Microsoft accounts" is on (it blocks
    automatic sign-in for those accounts)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, PASSWORDLESS, 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            return int(winreg.QueryValueEx(key, "DevicePasswordLessBuildVersion")[0]) == 2
    except (ImportError, OSError, ValueError):
        return False


def is_admin_account(domain, user):
    """Whether the account is in the local Administrators group (directly or through another group)."""
    from ctypes import wintypes
    netapi, advapi = ctypes.windll.netapi32, ctypes.windll.advapi32
    sid = ctypes.c_void_p()
    if not advapi.ConvertStringSidToSidW("S-1-5-32-544", ctypes.byref(sid)):
        raise WinSetupError("Windows could not name its Administrators group.")
    name, name_len = ctypes.create_unicode_buffer(256), wintypes.DWORD(256)
    dom, dom_len, use = ctypes.create_unicode_buffer(256), wintypes.DWORD(256), wintypes.DWORD()
    ok = advapi.LookupAccountSidW(None, sid, name, ctypes.byref(name_len), dom, ctypes.byref(dom_len),
                                  ctypes.byref(use))
    ctypes.windll.kernel32.LocalFree(sid)
    if not ok:
        raise WinSetupError("Windows could not name its Administrators group.")
    buf, read, total = ctypes.c_void_p(), wintypes.DWORD(), wintypes.DWORD()
    status = netapi.NetUserGetLocalGroups(None, account_name(domain, user), 0, 1, ctypes.byref(buf),
                                          wintypes.DWORD(0xFFFFFFFF), ctypes.byref(read), ctypes.byref(total))
    if status:
        raise WinSetupError(f"Windows could not list the account's groups (error {status}).")
    try:
        groups = ctypes.cast(buf, ctypes.POINTER(ctypes.c_wchar_p))
        return any((groups[i] or "").lower() == name.value.lower() for i in range(read.value))
    finally:
        netapi.NetApiBufferFree(buf)


def check_password(domain, user, password):
    """"" when Windows accepts the password for the account, else why not."""
    from ctypes import wintypes
    token = wintypes.HANDLE()
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    ok = advapi.LogonUserW(user, domain or ".", password, 2, 0, ctypes.byref(token))  # 2: interactive
    if ok:
        ctypes.windll.kernel32.CloseHandle(token)
        return ""
    error = ctypes.get_last_error()
    if error == 1326:
        return "Windows did not accept this password for the account."
    if error == 1327:
        return "Windows refused: the account has a restriction (a blank password, or sign-in hours)."
    return f"Windows could not check the password (error {error})."


class _LsaString(ctypes.Structure):
    _fields_ = [("Length", ctypes.c_ushort), ("MaximumLength", ctypes.c_ushort), ("Buffer", ctypes.c_wchar_p)]


def _lsa_string(text):
    s = _LsaString()
    s.Buffer = text
    s.Length = len(text) * 2
    s.MaximumLength = s.Length + 2
    return s


def _store_lsa_secret(name, value):
    """Store (or with None, delete) an LSA secret. Needs administrator rights."""

    class Attributes(ctypes.Structure):
        _fields_ = [("Length", ctypes.c_ulong), ("RootDirectory", ctypes.c_void_p), ("ObjectName", ctypes.c_void_p),
                    ("Attributes", ctypes.c_ulong), ("SecurityDescriptor", ctypes.c_void_p),
                    ("SecurityQualityOfService", ctypes.c_void_p)]
    advapi = ctypes.windll.advapi32
    attributes, handle = Attributes(), ctypes.c_void_p()
    attributes.Length = ctypes.sizeof(Attributes)
    status = advapi.LsaOpenPolicy(None, ctypes.byref(attributes), 0x20 | 0x01, ctypes.byref(handle))  # CREATE_SECRET
    if status:
        raise WinSetupError(f"Windows refused to open its secret store (error {advapi.LsaNtStatusToWinError(status)}).")
    try:
        key = _lsa_string(name)
        data = _lsa_string(value) if value is not None else None
        status = advapi.LsaStorePrivateData(handle, ctypes.byref(key), ctypes.byref(data) if data else None)
        if status and value is not None:
            raise WinSetupError(f"Windows refused to keep the password (error {advapi.LsaNtStatusToWinError(status)}).")
    finally:
        advapi.LsaClose(handle)


def set_autologon(domain, user, password):
    """Switch automatic sign-in on for the account (administrator rights)."""
    import winreg
    _store_lsa_secret("DefaultPassword", password)
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, WINLOGON, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as key:
        winreg.SetValueEx(key, "DefaultUserName", 0, winreg.REG_SZ, user)
        winreg.SetValueEx(key, "DefaultDomainName", 0, winreg.REG_SZ, domain)
        winreg.SetValueEx(key, "AutoAdminLogon", 0, winreg.REG_SZ, "1")
        for gone in ("DefaultPassword", "AutoLogonCount"):   # a plain-text password, or a limit on the count
            try:
                winreg.DeleteValue(key, gone)
            except OSError:
                pass


def clear_autologon():
    """Switch automatic sign-in off and delete the stored password (administrator rights)."""
    import winreg
    _store_lsa_secret("DefaultPassword", None)
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, WINLOGON, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as key:
        winreg.SetValueEx(key, "AutoAdminLogon", 0, winreg.REG_SZ, "0")
        try:
            winreg.DeleteValue(key, "DefaultPassword")
        except OSError:
            pass


# ---- the elevated copy ------------------------------------------------------------------------

def run_elevated(args):
    """Run this app as administrator with `--elevated *args` and wait. Its exit code (DONE, REFUSED_ADMIN,
    FAILED ...), or CANCELLED when the administrator approval was not given."""
    from ctypes import wintypes

    class Info(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
                    ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
                    ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
                    ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
                    ("dwHotKey", wintypes.DWORD), ("hIcon", wintypes.HANDLE), ("hProcess", wintypes.HANDLE)]
    argv = program("--elevated", *args)
    info = Info()
    info.cbSize = ctypes.sizeof(Info)
    info.fMask = 0x40   # SEE_MASK_NOCLOSEPROCESS: keep the process, to wait for it
    info.lpVerb, info.lpFile = "runas", argv[0]
    info.lpParameters = subprocess.list2cmdline(argv[1:])
    info.nShow = 1
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
        return CANCELLED   # the approval was refused or closed
    kernel = ctypes.windll.kernel32
    process = wintypes.HANDLE(info.hProcess)   # a pointer-sized handle: never passed as a plain int
    kernel.WaitForSingleObject(process, wintypes.DWORD(0xFFFFFFFF))
    code = wintypes.DWORD()
    kernel.GetExitCodeProcess(process, ctypes.byref(code))
    kernel.CloseHandle(process)
    return code.value


def elevated_main(argv):
    """`app.py --elevated <what> ...`, run as administrator by run_elevated(). Returns its exit code.

    autologon-on --domain D --user U   asks for U's password in its own window, checks it, refuses an
                                       administrator account, then switches automatic sign-in on
    autologon-off                      switches it off and deletes the stored password
    lock-task --account A              makes the lock task for account A"""
    def arg(name):
        return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else ""
    what = arg("--elevated")
    try:
        if what == "autologon-off":
            clear_autologon()
            return DONE
        if what == "lock-task":
            create_task(LOCK_TASK, lock_task_xml(arg("--account")))
            return DONE
        if what == "autologon-on":
            domain, user = arg("--domain"), arg("--user")
            if is_admin_account(domain, user):
                _message("Automatic sign-in", f"{account_name(domain, user)} is an administrator account. Automatic "
                         "sign-in is only for a standard account made for streaming. Nothing was changed.")
                return REFUSED_ADMIN
            password = _ask_password(domain, user)
            if password is None:
                return CANCELLED
            set_autologon(domain, user, password)
            return DONE
    except (OSError, WinSetupError) as exc:
        _message("Automatic sign-in", f"Nothing more was changed: {exc}")
        return FAILED
    return FAILED


def _message(title, text):
    from PySide6.QtWidgets import QApplication, QMessageBox
    QApplication.instance() or QApplication([])
    QMessageBox.warning(None, title, text)


def _ask_password(domain, user):
    """The account's password, asked in a small window of this elevated copy and checked with Windows
    until it is right. None when cancelled."""
    from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit
    QApplication.instance() or QApplication([])
    note = ""
    while True:
        password, ok = QInputDialog.getText(
            None, "Automatic sign-in", f"{note}Type the Windows password of {account_name(domain, user)}.\n"
            "Windows keeps it as a protected secret; it is not written to any file.", QLineEdit.Password)
        if not ok:
            return None
        problem = check_password(domain, user, password)
        if not problem:
            return password
        note = problem + "\n\n"
