The second alpha of Stream Scheduler: it schedules your weekly YouTube and Facebook live streams by
itself, with the date of each stream in the title.

> **Alpha.** YouTube scheduling has been confirmed on a real channel. The new Facebook request was
> confirmed by hand on a real Page, but not yet from inside the app.

## New in 0.0.1

- **Facebook scheduling fixed.** Facebook refused the old request ("Scheduled Live has been
  deprecated"). Streams are now created as scheduled events, and History links to the event.
- **YouTube guide:** separate steps for the sign-in screen, the Branding page (what Google needs before
  the app can be published) and publishing.
- **Facebook guide:** Next on the Connect step looks for your Pages; help for when the token lists no
  Page (choose the Page, or add `business_management` for a Page in a business portfolio).

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
- YouTube and Facebook Pages, each with a step-by-step setup guide
- Persistent stream keys (YouTube: a reusable key; Facebook: the Page's persistent key)
- Sign-ins kept in the system keychain
- Tray, start at login, catch-up after the computer was off
