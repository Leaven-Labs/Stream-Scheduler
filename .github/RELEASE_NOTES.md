The eighth alpha of Stream Scheduler: it schedules your YouTube live streams by itself, with the date
of each stream in the title, shows the coming stream on your website, and tells you when one needs you.

> **Alpha.** YouTube scheduling and the Wix website update are confirmed on a real channel and site.
> Everything under "New in 0.0.5" that talks to another service passed its automated tests but is
> **not yet confirmed on real accounts**. Try each one once before relying on it.

## New in 0.0.7

- **The look of the website, in the app.** Its gradient of indigo, violet and coral is on a line along
  the top of the window, the main buttons, the switches, the date leaves and the page titles, and the
  headings are in the website's typeface. Where things are and what they do has not changed.
- **A soft glow** under the main buttons and under the next stream on the Upcoming page.
- **Small animations.** A page fades in and a band of light crosses its title; the menu's marker and
  the switches slide; a ring spreads from the green light while auto-scheduling is on; and a light
  runs along the top line while the app is working, so you can see that it is busy.
- **Settings → Animations** switches them off for a still window. Nothing moves while the window is
  closed to the tray.

The new look passed the automated tests but is **not yet seen on a real Windows PC or Mac**. Please
report anything that looks wrong or feels slow.

## New in 0.0.6

- **A new icon.** The calendar now has two arrows going round its dot, for a stream that comes round
  by itself. It is in the window, the tray, the taskbar and your applications menu, with a simpler
  drawing at the small sizes. Nothing else about the app has changed.
- **Leaven Labs has a home page:** [www.leavenlabs.org](https://www.leavenlabs.org). The About
  window and the README point there now.

## New in 0.0.5

- **Alerts.** A new page sets up email, Discord, Slack and Pushover, each with a step-by-step guide
  and a test message. You are told when a stream could not be scheduled (or its start came without
  it), when a sign-in stopped working (asked once a day), and, if you like, in a weekly summary and
  for every new stream with its link.
- **Series with a first and a last date,** such as Wednesdays in Lent. `{series}`, `{number}`,
  `{nth}` and `{note}` join the names you can use in titles and descriptions.
- **Thumbnails:** one per schedule, and another for a single stream when you want.
- **More YouTube settings:** playlist, category and delay for a channel; who can watch and the
  playlist for a schedule.
- **Cancel** deletes a scheduled stream from YouTube and skips its date. Deleting a schedule offers
  to delete its coming streams too.
- **Preview what is sent,** in the schedule window: the next streams with every setting, and what
  YouTube would refuse. Nothing is sent.
- **More websites:** a guide for WordPress, and a web address (webhook) for Zapier, Make and others.
- **Reconnect** gives a destination a new sign-in without losing its schedules.
- **Backup and restore** in Settings: everything but the sign-ins, in one file.
- **A notice when a newer version is out.** Once a day the app asks GitHub for this project's
  releases; it can be switched off in Settings.

Updating: download and run the new version (on Windows, the new Setup). Your destinations, schedules and
sign-ins are kept. To be safe, copy the settings folder first (`%APPDATA%\Stream Scheduler` on Windows);
since 0.0.5, **Settings → Save a backup** does that for you.

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

- Weekly schedules, series with an end date and one-time streams, created on YouTube a chosen number
  of days before
- Titles and descriptions with `{date}`, `{weekday}`, `{month}`, `{day}`, `{year}`, `{time}`, `{series}`,
  `{number}`, `{nth}`, `{note}`
- Thumbnails, playlists, category, delay and who can watch
- Change, skip or cancel a single stream; check and repair what was scheduled; preview before sending
- Alerts by email, Discord, Slack and Pushover
- YouTube, Wix, WordPress and webhooks, each with a step-by-step setup guide
- A persistent YouTube stream key: your encoder keeps the same key every week
- Sign-ins kept in the system keychain
- Tray, start at login, catch-up after the computer was off, backup and restore, a notice of new versions
