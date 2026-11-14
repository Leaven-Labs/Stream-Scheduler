The fifth alpha of Stream Scheduler: it schedules your YouTube live streams by itself, with the date
of each stream in the title, and shows the coming stream on your Wix website.

> **Alpha.** YouTube scheduling and the Wix website update are confirmed on a real channel and site.
> Changing a stream that already exists on YouTube, and the re-check, are new and not yet confirmed
> there.

## New in 0.0.4

- **A Windows installer.** `Stream-Scheduler-Windows-Setup.exe` replaces the zip. It installs for you
  alone, without an administrator prompt, and can start the app each time you sign in to Windows.
  Later versions update by running the newer Setup.
- **Checks when it starts.** Each time the app starts, also hidden at sign-in, it sees whether every
  scheduled stream is still on YouTube and on the website, creates again what is gone, and creates
  what came due while the computer was off.
- **Start when I log in** in Settings shows what the system really does.

Coming from an unzipped Windows version: run the Setup. It stops the old copy and keeps your
destinations, schedules and sign-ins; afterwards, delete the old unzipped folder yourself. The installer
is new: it passed its automated install, update and uninstall test, and has not yet been used on a
computer with earlier settings, so copy `%APPDATA%\Stream Scheduler` somewhere first.

Updating: download and run the new version (on Windows, the new Setup). Your destinations, schedules and
sign-ins are kept.

## Download

| Your computer | File |
|---|---|
| Windows 10 or 11 (64-bit) | `Stream-Scheduler-Windows-Setup.exe` |
| Mac with Apple silicon (M1 or newer) | `Stream-Scheduler-macOS.zip` |
| Linux, 64-bit (Ubuntu 22.04 or newer) | `Stream-Scheduler-Linux-x86_64.tar.gz` |

**Windows.** Run **Stream-Scheduler-Windows-Setup.exe**. It installs for you alone, without an
administrator prompt, and can start the app each time you sign in to Windows. It isn't code-signed yet,
so if Windows says *"Windows protected your PC"*, click **More info** → **Run anyway**. To update, run
the newer Setup: your destinations, schedules and sign-ins are kept.

**Mac.** Unzip and drag **Stream Scheduler** to **Applications**. It isn't signed with an Apple
developer ID yet, so the first time macOS refuses to open it: click **Done**, open **System Settings →
Privacy & Security**, click **Open Anyway** next to Stream Scheduler and confirm.

**Linux.** Unpack and run `Stream Scheduler/Stream Scheduler`. A keyring (GNOME Keyring or KWallet)
must be running to save sign-ins.

## What it does

- Weekly and one-time schedules, created on YouTube a chosen number of days before
- Titles and descriptions with `{date}`, `{weekday}`, `{month}`, `{day}`, `{year}`, `{time}`
- Change or skip a single stream; check and repair what was scheduled
- YouTube and Wix, each with a step-by-step setup guide
- A persistent YouTube stream key: your encoder keeps the same key every week
- Sign-ins kept in the system keychain
- Tray, start at login, catch-up after the computer was off
