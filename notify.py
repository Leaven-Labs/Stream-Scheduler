"""Messages to you when the app works unattended: by email, Discord, Slack or Pushover.

What can be sent (each can be switched off):
  failed   a stream could not be created, or its start came without it being created
  signin   a saved sign-in stopped working (asked once a day)
  summary  once a week: the streams of the coming seven days and whether each one is in place
  created  a stream was created, with its link
  obs      before a service, OBS is not open or not set to the stream's key (and "ready now" once fixed)

The channels' secrets (webhook addresses, the mail password, Pushover's keys) are in the keychain
under the id "notify"; what is not secret is in config.json under "notify". A message that cannot be
sent never stops the scheduling: the reason is kept and shown on the Alerts page.
"""
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

import engine
import net
import paths
import titles
import vault as vault_module
from vault import NOTIFY

CHANNELS = {"email": "Email", "discord": "Discord", "slack": "Slack", "pushover": "Pushover"}
SECRETS = {"email": ["email_password"], "discord": ["discord_url"], "slack": ["slack_url"],
           "pushover": ["pushover_token", "pushover_user"]}
EVENTS = {"failed": True, "signin": True, "summary": False, "created": False, "obs": True}
HEALTH_EVERY = timedelta(hours=24)


def settings(store):
    """The notification settings, with every key present."""
    cfg = store.data.setdefault("notify", {})
    cfg["events"] = {**EVENTS, **cfg.get("events", {})}
    cfg.setdefault("channels", {})
    cfg.setdefault("summary_day", 5)        # Saturday
    cfg.setdefault("summary_time", "18:00")
    for key in ("last_summary", "last_health", "last_error"):
        cfg.setdefault(key, "")
    cfg.setdefault("sent", [])              # what was reported already, so nothing is reported twice
    cfg.setdefault("health", {})            # destination id -> why its sign-in does not work
    return cfg


def active(store):
    """The channels that are set up and switched on."""
    return [c for c, v in settings(store)["channels"].items() if c in CHANNELS and v.get("on", True)]


# ---- the channels ------------------------------------------------------------------------------

def _webhook(url, body, name):
    if not url.strip().lower().startswith("https://"):
        raise net.ApiError(f"The {name} address must start with https://")
    try:
        net.request("POST", url.strip(), body=body)
    except net.ApiError as exc:
        if exc.status in (401, 403, 404):
            raise net.ApiError(f"{name} no longer accepts this webhook address (deleted?). Set it up again. "
                               f"({exc})", exc.status, exc.reason) from None
        raise


def deliver_mail(config, password, message):
    """Hand a message to the mail server. Tests put their own function in this place."""
    host, port = config["host"].strip(), int(config.get("port") or 587)
    context = net._ssl_context()
    try:
        if config.get("security") == "ssl":
            server = smtplib.SMTP_SSL(host, port, timeout=30, context=context)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.starttls(context=context)   # never send the password over a connection that is not encrypted
        with server:
            if config.get("user"):
                server.login(config["user"].strip(), password)
            server.send_message(message)
    except smtplib.SMTPAuthenticationError:
        raise net.ApiError("The mail server refused the user name or password. Many providers (Gmail, Outlook, "
                           "Yahoo) want an app password here, not your normal one.") from None
    except (smtplib.SMTPException, OSError) as exc:
        raise net.ApiError(f"The email could not be sent ({exc}).") from None


def send_one(channel, config, vault, title, text, url="", urgent=False):
    """Send one message on one channel. Raises ApiError or VaultError."""
    body = text + (f"\n{url}" if url else "")
    if channel == "discord":
        _webhook(vault.get(NOTIFY, "discord_url"), {"content": f"**{title}**\n{body}"[:1900]}, "Discord")
    elif channel == "slack":
        _webhook(vault.get(NOTIFY, "slack_url"), {"text": f"*{title}*\n{body}"}, "Slack")
    elif channel == "pushover":
        form = {"token": vault.get(NOTIFY, "pushover_token"), "user": vault.get(NOTIFY, "pushover_user"),
                "title": title[:250], "message": text[:1024], "priority": "1" if urgent else "0"}
        if url:
            form.update(url=url, url_title="Open")
        try:
            net.request("POST", "https://api.pushover.net/1/messages.json", form=form)
        except net.ApiError as exc:
            if exc.status and exc.status < 500:
                raise net.ApiError(f"Pushover refused the message: {exc} Check the API token and the user key.",
                                   exc.status, exc.reason) from None
            raise
    elif channel == "email":
        message = EmailMessage()
        message["Subject"] = title
        message["From"] = config.get("sender") or config.get("user", "")
        message["To"] = config["to"]
        message.set_content(body + f"\n\n--\nSent by {paths.APP_NAME} on your computer.")
        deliver_mail(config, vault.get(NOTIFY, "email_password") if config.get("user") else "", message)
    else:
        raise net.ApiError(f"Unknown channel: {channel}")


def send(store, vault, title, text, url="", urgent=False):
    """Send a message on every channel that is on. Returns how many took it; failures are remembered."""
    cfg, done, errors = settings(store), 0, []
    for channel in active(store):
        try:
            send_one(channel, cfg["channels"][channel], vault, title, text, url, urgent)
            done += 1
        except (net.ApiError, vault_module.VaultError) as exc:
            errors.append(f"{CHANNELS[channel]}: {exc}")
        except Exception as exc:   # a bug here must never stop the scheduling
            errors.append(f"{CHANNELS[channel]}: unexpected error {type(exc).__name__}: {exc}")
    if errors:
        cfg["last_error"] = f"{datetime.now().strftime('%Y-%m-%dT%H:%M')}  " + "  ".join(errors)
    elif done:
        cfg["last_error"] = ""
    return done


def forget(store, vault, channel):
    """Remove a channel and delete its secrets from the keychain."""
    for name in SECRETS[channel]:
        vault.remove(NOTIFY, name)
    settings(store)["channels"].pop(channel, None)
    store.save()


# ---- what is reported --------------------------------------------------------------------------

def _once(cfg, key):
    """True the first time a key is seen (and remembers it)."""
    if key in cfg["sent"]:
        return False
    cfg["sent"].append(key)
    del cfg["sent"][:-300]
    return True


def _line(store, e):
    when = datetime.fromisoformat(e["when"])
    return f"{e['title']} ({titles.short_day(when, store.settings.get('clock', '12'))}, {e['destination_name']})"


def report_entries(store, vault, entries):
    """Tell about streams that failed (once each) and, when asked, about streams that were created."""
    cfg = settings(store)
    failed = [e for e in entries if e["status"] == "failed" and not e.get("waiting") and not e.get("told")]
    if failed and cfg["events"]["failed"] and active(store):
        text = "\n".join(f"{_line(store, e)}: {e['note']}" for e in failed)
        if send(store, vault, "A stream could not be scheduled", text + "\nThe app tries again every 15 minutes.",
                urgent=True):
            for e in failed:
                e["told"] = True
    made = [e for e in entries if e["status"] == "created" and e["kind"] == "youtube"]
    if made and cfg["events"]["created"] and active(store):
        for e in made:
            send(store, vault, "Stream scheduled", _line(store, e), e.get("url", ""))


def report_missed(store, vault, now):
    """Tell when a stream's start is so near that it will not be created any more."""
    cfg = settings(store)
    if not (cfg["events"]["failed"] and active(store)):
        return
    for item in engine.upcoming(store, now, limit=1000):
        youtube_missing = [d for d, e in item["targets"] if d["kind"] == "youtube"
                           and not (e and e["status"] == "created")]
        if item["skipped"] or not youtube_missing or item["when"] - now >= engine.MIN_AHEAD:
            continue
        if item["create_at"] > now:   # it was never due: someone made the schedule this late
            continue
        key = f"missed:{item['schedule']['id']}:{item['date']}"
        if key not in cfg["sent"] and send(
                store, vault, "A stream was not scheduled in time",
                f"{item['title']} starts {titles.short_day(item['when'], store.settings.get('clock', '12'))} and "
                "is not on YouTube. It is too late for the app to create it: create it in YouTube Studio.",
                urgent=True):
            _once(cfg, key)


def check_health(store, vault, now, force=False):
    """Once a day, ask every destination whether its sign-in still works. A sign-in that stopped
    working is kept in settings(store)["health"] (the app shows it) and reported once."""
    cfg = settings(store)
    if not force and cfg["last_health"] and now - datetime.fromisoformat(cfg["last_health"]) < HEALTH_EVERY:
        return
    reached = False
    for dest in store.destinations:
        if dest["kind"] not in engine.ENABLED or dest["kind"] == "webhook":   # a webhook cannot be asked quietly
            continue
        try:
            engine.test_destination(vault, dest)
            problem = ""
        except vault_module.VaultError as exc:
            problem = str(exc)
        except net.ApiError as exc:
            if not exc.status:   # no connection: says nothing about the sign-in
                continue
            problem = str(exc)
        reached = True
        if not problem:
            cfg["health"].pop(dest["id"], None)
            cfg["sent"] = [k for k in cfg["sent"] if k != f"signin:{dest['id']}"]
            continue
        cfg["health"][dest["id"]] = problem
        if cfg["events"]["signin"] and active(store) and f"signin:{dest['id']}" not in cfg["sent"]:
            if send(store, vault, "A sign-in stopped working",
                    f"{dest['name']}: {problem}\nStreams cannot be scheduled there until this is fixed.", urgent=True):
                _once(cfg, f"signin:{dest['id']}")
    for gone in [i for i in cfg["health"] if not store.destination(i)]:
        del cfg["health"][gone]
    if reached or not store.destinations:
        cfg["last_health"] = now.strftime("%Y-%m-%dT%H:%M:%S")


def summary_text(store, now):
    """The streams of the coming seven days, one per line, with whether each is in place."""
    clock = store.settings.get("clock", "12")
    lines = []
    for item in engine.upcoming(store, now, limit=1000):
        if item["when"] - now > timedelta(days=7):
            break
        day = titles.short_day(item["when"], clock)
        entries = [e for _, e in item["targets"] if e]
        link = next((e["url"] for d, e in item["targets"] if e and d["kind"] == "youtube"
                     and e["status"] == "created"), "")
        failed = next((e for e in entries if e["status"] == "failed" and not e.get("waiting")), None)
        if item["skipped"]:
            lines.append(f"-  {day}  {item['title']}  (skipped)")
        elif failed:
            lines.append(f"FAILED  {day}  {item['title']}: {failed['note']}")
        elif link:
            lines.append(f"OK  {day}  {item['title']}\n    {link}")
        elif not item["targets"]:
            lines.append(f"!  {day}  {item['title']}  (no destination chosen)")
        else:
            lines.append(f"..  {day}  {item['title']}  (will be created {titles.short_day(item['create_at'], clock)})")
    return "\n".join(lines) or "No stream is planned in the next seven days."


def report_summary(store, vault, now):
    """Send the weekly summary when its day and time have come (or passed while the app was not running,
    up to two days ago)."""
    cfg = settings(store)
    if not (cfg["events"]["summary"] and active(store)):
        return
    hour, minute = (int(p) for p in cfg["summary_time"].split(":"))
    slot = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    slot -= timedelta(days=(slot.weekday() - int(cfg["summary_day"])) % 7)
    if slot > now:
        slot -= timedelta(days=7)
    stamp = slot.strftime("%Y-%m-%dT%H:%M")
    if cfg["last_summary"] >= stamp or now - slot > timedelta(days=2):
        return
    text = summary_text(store, now)
    if send(store, vault, "Your streams this week" + (": something needs you" if "FAILED" in text else ""),
            text, urgent="FAILED" in text):
        cfg["last_summary"] = stamp


def report_obs(store, vault, now):
    """Look at OBS before services, at the rounds engine.obs_due() says, and tell when it is not ready;
    at a later round, again if it still is not, or that it is ready now if a problem was fixed."""
    cfg = settings(store)
    clock = store.settings.get("clock", "12")
    for item, encoder, round_ in engine.obs_due(store, now):
        told = engine.obs_state(store).get(engine.obs_key(item), {}).get("told", [])
        result = engine.obs_check(store, vault, item, encoder, now)
        record = engine.obs_record(store, item, result, round_, now)
        store.save()
        if not (cfg["events"]["obs"] and active(store)):
            continue
        minutes = max(1, round((item["when"] - now).total_seconds() / 60))
        start = f"{item['title']} starts in {minutes} minutes ({titles.format_time(item['when'], clock)})"
        if result["problems"]:
            text = f"{start}.\n" + "\n".join(p["text"] for p in result["problems"])
            if send(store, vault, "OBS is still not ready" if told else "OBS is not ready", text, urgent=True):
                record["told"] = [p["code"] for p in result["problems"]]
        elif told:
            if send(store, vault, "OBS is ready now", f"{start}. OBS on {encoder['name']} is ready: the problem "
                                                      "reported earlier is fixed."):
                record["told"] = []


def after(store, vault, entries, now=None):
    """What follows every round of work in the background: report, and look after the sign-ins."""
    now = now or datetime.now()
    for step in (lambda: report_entries(store, vault, entries), lambda: report_missed(store, vault, now),
                 lambda: report_obs(store, vault, now), lambda: check_health(store, vault, now),
                 lambda: report_summary(store, vault, now)):
        try:
            step()
        except Exception as exc:   # reporting must never stop the scheduling
            settings(store)["last_error"] = f"Unexpected error: {type(exc).__name__}: {exc}"
    store.save()
    return entries
