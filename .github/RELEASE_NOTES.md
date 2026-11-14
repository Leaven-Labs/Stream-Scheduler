The third alpha of Stream Scheduler: it schedules your weekly YouTube live streams by itself, with the
date of each stream in the title, and shows the coming stream on your Wix website.

> **Alpha.** YouTube scheduling is confirmed on a real channel. The Wix website update is new and has
> not yet been tried against a real Wix site.

## New in 0.0.2

- **Wix websites.** After a schedule creates its YouTube stream, the app points the video player on a
  page of your Wix site at it (through a CMS collection the guide helps you set up). Publishing the
  site afterwards is an option.
- **Facebook is switched off.** Facebook no longer lets an app schedule a live video with a Page's
  persistent stream key. Schedules skip a Facebook destination; you can remove it.

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

- Weekly schedules, created on the platforms a chosen number of days before
- Titles and descriptions with `{date}`, `{weekday}`, `{month}`, `{day}`, `{year}`, `{time}`
- Override or skip a single stream
- YouTube and Wix, each with a step-by-step setup guide
- A persistent YouTube stream key: your encoder keeps the same key every week
- Sign-ins kept in the system keychain
- Tray, start at login, catch-up after the computer was off
