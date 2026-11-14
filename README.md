<p align="center"><img src="assets/icon.svg" width="96" alt=""></p>
<h1 align="center">Stream Scheduler</h1>
<p align="center">Schedules your weekly live streams on <b>YouTube</b> by itself, with the date of each<br>
stream already in the title, and shows the coming stream on your <b>Wix</b> website.</p>

> **v0.0.4 alpha.** YouTube scheduling and the Wix website update are confirmed on a real channel and
> site. Changing a stream that already exists on YouTube, and the re-check, are new and not yet
> confirmed there. Please report what you find.

![Upcoming streams](docs/upcoming-dark.png)

## What it does

- **Schedules that repeat.** "Every Sunday at 8:00 AM, created the Saturday before at 9:00 AM." Choose
  for each schedule which of your destinations it goes to.
- **Titles that fill in the date.** `Sunday Service - {date}` becomes *Sunday Service - November 15,
  2027* for that Sunday's stream. Also `{weekday}`, `{month}`, `{day}`, `{year}` and `{time}`, in the
  title and the description, with a choice of date formats.
- **One-time streams.** A schedule can also be for a single date, such as Christmas Eve.
- **Change one stream.** Give a single date another title, description or start time, or skip it,
  without touching the schedule. If the stream already exists, it is changed on YouTube and the website.
- **Check and repair.** *Check now* sees whether every scheduled stream is still on YouTube and still
  shown on the website, and puts back what is missing. *Update now* sends one stream again.
- **Your website follows along.** After a stream is created on YouTube, the video player on a page
  of your Wix site is pointed at it.
- **Guided setup.** A step-by-step guide for YouTube and for Wix explains what to click on Google's
  and Wix's pages, and what each step means for your account's safety.
- **Sign-ins kept in the system keychain**, never in a file. See [SECURITY.md](SECURITY.md).
- **Runs quietly.** Stays in the tray, can start at login, and catches up on what it missed while the
  computer was off. Light and dark themes.

| | |
|---|---|
| ![A schedule](docs/schedule-light.png) | ![The Wix guide](docs/wizard-wix-dark.png) |

## Install

Download from the **[Releases](../../releases)** page:

| Your computer | Download |
|---|---|
| Windows 10 or 11 (64-bit) | `Stream-Scheduler-Windows-Setup.exe` |
| Mac with Apple silicon (M1 or newer) | `Stream-Scheduler-macOS.zip` |
| Linux, 64-bit (Ubuntu 22.04 or newer) | `Stream-Scheduler-Linux-x86_64.tar.gz` |

**Windows.** Run **Stream-Scheduler-Windows-Setup.exe**. It installs for you alone, without an
administrator prompt, and can start the app each time you sign in to Windows. It isn't code-signed yet,
so if Windows says *"Windows protected your PC"*, click **More info** → **Run anyway**. To update, run
the newer Setup: your destinations, schedules and sign-ins are kept.

**Mac.** Unzip and drag **Stream Scheduler** to **Applications**. It isn't signed with an Apple
developer ID yet: the first time, click **Done**, open **System Settings → Privacy & Security**, and
click **Open Anyway** next to Stream Scheduler.

**Linux.** Unpack and run `Stream Scheduler/Stream Scheduler`.

Or run it from source with [Python](https://www.python.org/downloads/) 3.10 or newer:

```bash
git clone https://github.com/Leaven-Labs/Stream-Scheduler.git
```

```bash
cd Stream-Scheduler
```

```bash
pip install -r requirements.txt
```

```bash
python app.py
```

Then: **Destinations** → *Add YouTube* and, if you like, *Add Wix website* (10 to 15 minutes each, once), and
**Schedules** → *New schedule*.

## How the automatic part works

The streams are created **by your computer**, at the time the schedule says, through the platforms'
official APIs. There is no server of ours. So the app has to run at that time:

- leave it open, or closed to the tray (the default), and switch on **Settings → Start when I log in**; or
- have your system's task scheduler run the program with `--run` (from source: `python app.py --run`), which creates what is due and exits.

If the computer was off, the app creates the missed streams the next time it runs, as long as the
stream is still more than 10 minutes away. A stream is never created twice.

## Good to know about the platforms

- **YouTube.** You create your own free Google Cloud project (the guide shows how). Set it to *In
  production*, or Google ends the sign-in every 7 days. Choose a stream key in the guide and your
  encoder keeps the same key every week. Live streaming must be enabled on the channel.
- **Wix.** Wix has no way for an outside app to edit an element on a page. The guide has you connect
  the page's YouTube element to a small CMS collection once (Wix's own Video Player cannot show a
  stream that has not started); the app then only changes the link in that
  collection, which is live at once. The schedule must also send to YouTube. Publishing the whole site
  after each update is an option, off by default, because it also publishes any unfinished edits.
- **Facebook is switched off.** Facebook no longer lets an app like this one schedule a live video the
  way its Live Producer does: it refuses the scheduled-live request and the Page's persistent stream
  key. The app could only create an event with a one-off stream key, which does not suit volunteers.
  The code is kept (`facebook.py`) in case Meta opens this up again.

## Where your files are

| | |
|---|---|
| The program (Windows installer) | `%LOCALAPPDATA%\Programs\Stream Scheduler`, replaced by each update |
| Settings, schedules, history | Windows `%APPDATA%\Stream Scheduler` · Mac `~/Library/Application Support/Stream Scheduler` · Linux `~/.config/stream-scheduler` |
| Tokens and client secrets | Windows Credential Manager · macOS Keychain · Linux Secret Service (GNOME Keyring, KWallet) |

## Not in this alpha

Code signing; installers for Mac and Linux; running before anyone has signed in to the computer;
Facebook; thumbnails; deleting a
stream on YouTube from the app; other platforms.

## For developers

Python and Qt (PySide6), standard library for HTTPS.

| File | What it holds |
|---|---|
| `app.py` | the start: the window, `--tray`, `--run`, `--quit`, `--uitest` |
| `tools/build.py`, `tools/installer.iss` | the downloads; the Windows installer (Inno Setup) |
| `engine.py` | which streams are coming, and creating the ones that are due |
| `recurrence.py`, `titles.py` | when streams are; filling `{date}` into titles |
| `youtube.py`, `wix.py`, `net.py` | the platforms' APIs (`facebook.py` is kept but switched off) |
| `vault.py`, `store.py` | secrets in the keychain; everything else in `config.json` |
| `ui.py`, `mainwindow.py`, `dialogs.py`, `wizards.py` | the look, the pages, the dialogs, the setup guides |

```bash
python -m unittest discover tests
```

```bash
python app.py --uitest
```

```bash
python tools/screenshots.py
```

To build the program for your own system (the Release workflow does this for all three and publishes
them):

```bash
pip install -r requirements-build.txt
```

```bash
python tools/build.py
```

## License

MIT, see [LICENSE](LICENSE). YouTube and Facebook are trademarks of their owners; this app is not
affiliated with or endorsed by Google, Meta or Wix.
