The fourth alpha of Stream Scheduler: it schedules your YouTube live streams by itself, with the date
of each stream in the title, and shows the coming stream on your Wix website.

> **Alpha.** YouTube scheduling and the Wix website update are confirmed on a real channel and site.
> Changing a stream that already exists on YouTube, and the re-check, are new and not yet confirmed
> there.

## New in 0.0.3

- **Check now also re-checks.** It sees whether every scheduled stream is still on YouTube and still
  shown on the website, creates again what was deleted, and gives the website the new link.
- **Update now** on a scheduled stream sends its title, description and time again.
- **Edit one stream, also after it was scheduled,** including its start time (8:15 to 8:30 for one
  Sunday). A stream that exists is changed in place on YouTube and keeps its link.
- **One-time streams:** a schedule can be for a single date.
- **Wix guide corrected:** use Wix's YouTube element, not its Video Player; set the dataset to Read;
  the steps match what the Wix dashboard shows.

Updating: download, unzip and run the new version. Your destinations, schedules and sign-ins are kept.

## Download

| Your computer | File |
|---|---|
| Windows 10 or 11 (64-bit) | `Stream-Scheduler-Windows.zip` |
| Mac with Apple silicon (M1 or newer) | `Stream-Scheduler-macOS.zip` |
| Linux, 64-bit (Ubuntu 22.04 or newer) | `Stream-Scheduler-Linux-x86_64.tar.gz` |

**Windows.** Unzip, open the folder, run **Stream Scheduler.exe**. It isn't code-signed yet, so if
Windows says *"Windows protected your PC"*, click **More info** → **Run anyway**.

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
