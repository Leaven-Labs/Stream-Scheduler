"""The work: which streams are coming up, and creating the ones whose time has come.

run_due() is called every minute while the app runs (and by `app.py --run` from the system's task
scheduler). It is safe to call again and again: a stream that was created at a destination is
written to the history at once and is never created twice.
"""
from datetime import datetime, time, timedelta

import facebook
import net
import recurrence
import titles
import vault as vault_module
import webhook
import wix
import wordpress
import youtube
from store import new_id

MIN_AHEAD = timedelta(minutes=12)    # Facebook refuses a start less than 10 minutes away
MAX_AHEAD = timedelta(days=7)        # ... or more than 7 days away
RETRY_AFTER = timedelta(minutes=15)  # wait this long before trying a failed one again
LOOK_AHEAD = timedelta(days=28)
# The kinds of destination in use. Facebook is switched off: it no longer lets an app like this one
# schedule a live video with the Page's persistent stream key. Its code (facebook.py) is kept.
# Websites show the link of the schedule's YouTube stream, so they come after YouTube and wait for it.
WEB = {"wix", "wordpress", "webhook"}
ENABLED = {"youtube"} | WEB


class Waiting(net.ApiError):
    """Not a failure yet: a website waits for the YouTube stream whose link it shows."""


def text_for(store, schedule, when):
    """(title, description, overridden) of the stream at `when`: the schedule's templates with the date
    filled in, unless the user typed other words for this one date."""
    over = schedule.get("overrides", {}).get(recurrence.date_key(when), {})
    clock = store.settings.get("clock", "12")
    more = {"series": schedule.get("series", ""), "note": over.get("note", ""),
            "number": recurrence.number(schedule, when)}
    fill = lambda text: titles.render(text, when, schedule.get("date_format", "long"), clock, more)
    title = " ".join(fill(over["title"] if over.get("title") else schedule.get("title", "")).split())
    description = fill(over["description"] if "description" in over else schedule.get("description", "")).strip()
    return title, description, bool(over.get("title") or "description" in over or over.get("time")
                                    or over.get("note") or over.get("thumbnail"))


def upcoming(store, now=None, limit=12):
    """The coming streams of every schedule that is switched on, soonest first."""
    now = now or datetime.now()
    items = []
    for schedule in store.schedules:
        if not schedule.get("enabled", True):
            continue
        today = datetime.combine(now.date(), time.min) - timedelta(seconds=1)
        for when in recurrence.occurrences(schedule, today, now + LOOK_AHEAD):
            key = recurrence.date_key(when)
            other = schedule.get("overrides", {}).get(key, {}).get("time")
            if other:   # this one stream was moved to another time of its day
                when = datetime.combine(when.date(), recurrence.parse_time(other))
            if when <= now:
                continue
            title, description, overridden = text_for(store, schedule, when)
            targets = [(dest, store.entry(schedule["id"], key, dest["id"]))
                       for dest in (store.destination(i) for i in schedule.get("destinations", []))
                       if dest and dest["kind"] in ENABLED]
            targets.sort(key=lambda t: t[0]["kind"] != "youtube")  # YouTube first: a website shows its link
            items.append({"schedule": schedule, "when": when, "date": key, "title": title,
                          "description": description, "overridden": overridden,
                          "thumbnail": schedule.get("overrides", {}).get(key, {}).get("thumbnail")
                          or schedule.get("thumbnail", ""),
                          "skipped": bool(schedule.get("overrides", {}).get(key, {}).get("skip")),
                          "create_at": recurrence.create_at(schedule, when), "targets": targets})
    items.sort(key=lambda item: item["when"])
    return items[:limit]


OLD = "2000-01-01T00:00:00"   # an entry's time that lets it be tried again at once


def redo(entry, why):
    """Mark something that was done as to be done again (it is gone, or what it shows has changed)."""
    entry.update(status="failed", note=why, redo=True, at=OLD)


def youtube_options(schedule, dest, thumbnail=""):
    """How a schedule's stream is made on a channel: the channel's own options, with what the schedule
    says otherwise (who can watch, the playlist) and the stream's thumbnail."""
    options = dict(dest.get("options", {}))
    for key in ("privacy", "playlist"):
        if schedule.get(key):
            options[key] = schedule[key]
    options["thumbnail"] = thumbnail
    return options


def show_on(dest, vault, link, item, start):
    """Put a YouTube stream's link on a website. Returns {"id", "url", "note"}."""
    if dest["kind"] == "wix":
        return wix.show(dest, vault.get(dest["id"], "api_key"), link, item["title"])
    if dest["kind"] == "wordpress":
        return wordpress.show(dest, vault.get(dest["id"], "app_password"), link, item["title"])
    webhook.send(vault.get(dest["id"], "url"), webhook.payload(
        item["title"], item["description"], link, start, item["when"], item["schedule"]["name"]))
    return {"id": "", "url": "", "note": ""}


def create(store, vault, item, dest, now=None, update=False):
    """Create one stream at one destination and write the outcome to the history. Returns the entry.

    With update, a stream that already exists is changed in place (title, description, time) and
    keeps its link; without it, an existing stream is never touched."""
    now = now or datetime.now()
    schedule, when = item["schedule"], item["when"]
    old = store.entry(schedule["id"], item["date"], dest["id"]) or {}
    entry = {"id": old.get("id") or new_id(), "schedule_id": schedule["id"], "schedule_name": schedule["name"],
             "date": item["date"], "when": when.strftime("%Y-%m-%dT%H:%M"), "destination_id": dest["id"],
             "destination_name": dest["name"], "kind": dest["kind"], "title": item["title"],
             "at": now.strftime("%Y-%m-%dT%H:%M:%S"), "attempts": old.get("attempts", 0) + 1,
             "status": "failed", "remote_id": "", "url": "", "note": ""}
    for key in ("redo", "told"):   # redo stays until it works; told: the failure was already reported
        if old.get(key):
            entry[key] = True
    try:
        found = titles.problems(item["title"], item["description"]) if dest["kind"] == "youtube" else \
            ([] if item["title"].strip() else ["The title is empty."])
        if found:
            raise net.ApiError(" ".join(found))
        if dest["kind"] not in WEB and not MIN_AHEAD - timedelta(minutes=2) <= when - now:
            raise net.ApiError("Too late: the stream starts in less than 10 minutes.")
        if dest["kind"] == "facebook" and when - now > MAX_AHEAD:
            raise net.ApiError("Too early: Facebook accepts a stream at most 7 days ahead.")
        start = recurrence.to_utc(when)
        if dest["kind"] == "youtube":
            token = youtube.access_token(dest["client_id"], vault.get(dest["id"], "client_secret"),
                                         vault.get(dest["id"], "refresh_token"))
            options = youtube_options(schedule, dest, item.get("thumbnail", ""))
            exists = update and old.get("status") == "created" and youtube.broadcast(token, old["remote_id"])
            if exists:
                note = youtube.update_broadcast(token, old["remote_id"], item["title"], item["description"],
                                                start, options)
                made = {"id": old["remote_id"], "url": old["url"], "note": note}
            else:
                made = youtube.create_broadcast(token, item["title"], item["description"], start, options)
        elif dest["kind"] == "facebook":
            made = facebook.create_live(dest["account_id"], vault.get(dest["id"], "page_token"),
                                        item["title"], item["description"], start,
                                        dest.get("options", {}).get("persistent_key", False))
        elif dest["kind"] in WEB:
            link = next((e["url"] for d, e in ((d, store.entry(schedule["id"], item["date"], d["id"]))
                                               for d, _ in item["targets"] if d["kind"] == "youtube")
                         if e and e["status"] == "created" and e.get("url")), "")
            if not link:
                raise Waiting("Waiting for this schedule's YouTube stream: the website shows its link. "
                              "(The schedule must also send to a YouTube channel.)")
            made = show_on(dest, vault, link, item, start)
        else:
            raise net.ApiError(f"Unknown kind of destination: {dest['kind']}")
        entry.update(status="created", remote_id=made["id"], url=made["url"], note=made["note"])
        for key in ("redo", "told"):
            entry.pop(key, None)
        if dest["kind"] == "youtube" and old.get("url") and old["url"] != made["url"]:
            for other, _ in item["targets"]:   # a new stream has a new link: websites must follow
                shown = store.entry(schedule["id"], item["date"], other["id"])
                if other["kind"] in WEB and shown and shown["status"] == "created":
                    redo(shown, "The YouTube stream was created again; the website gets the new link.")
    except Waiting as exc:
        entry.update(note=str(exc), waiting=True)
    except (net.ApiError, vault_module.VaultError) as exc:
        entry["note"] = str(exc)
    except Exception as exc:  # a bug must not stop the other destinations
        entry["note"] = f"Unexpected error: {type(exc).__name__}: {exc}"
    store.put_entry(entry)
    return entry


def run_due(store, vault, now=None):
    """Create every stream whose time has come and that is not there yet. Returns the new history entries."""
    now = now or datetime.now()
    done = []
    for item in upcoming(store, now, limit=1000):
        if item["skipped"]:
            continue
        for dest, _ in item["targets"]:
            entry = store.entry(item["schedule"]["id"], item["date"], dest["id"])  # fresh: redo() may have marked it
            again = bool(entry and entry.get("redo"))
            if not again and item["create_at"] > now:
                continue
            if item["when"] - now < MIN_AHEAD and dest["kind"] not in WEB:
                continue
            if entry and entry["status"] == "created":
                continue
            if entry and now - datetime.fromisoformat(entry["at"]) < RETRY_AFTER:
                continue
            done.append(create(store, vault, item, dest, now))
    return done


def verify(store, vault, now=None):
    """Look at every coming stream that was created and see whether it is still there: the broadcast on
    YouTube, and its link on the website. What is gone is marked to be done again. Returns how many."""
    now = now or datetime.now()
    gone = 0
    for item in upcoming(store, now, limit=1000):
        link = ""
        for dest, _ in item["targets"]:
            entry = store.entry(item["schedule"]["id"], item["date"], dest["id"])
            if not entry or entry["status"] != "created":
                continue
            try:
                if dest["kind"] == "youtube":
                    token = youtube.access_token(dest["client_id"], vault.get(dest["id"], "client_secret"),
                                                 vault.get(dest["id"], "refresh_token"))
                    if youtube.broadcast(token, entry["remote_id"]):
                        link = link or entry["url"]
                    else:
                        redo(entry, "This stream was no longer on YouTube (deleted?). It is created again.")
                        gone += 1
                elif dest["kind"] == "wix":
                    o = dest["options"]
                    shown = wix.item(vault.get(dest["id"], "api_key"), dest["account_id"], o["collection"],
                                     o["item_id"]).get(o["url_field"])
                    if shown != link:
                        redo(entry, "The website no longer showed this stream. It is updated again.")
                        gone += 1
                elif dest["kind"] == "wordpress":
                    if link and not wordpress.shows(dest, vault.get(dest["id"], "app_password"), link):
                        redo(entry, "The website no longer showed this stream. It is updated again.")
                        gone += 1
            except (net.ApiError, vault_module.VaultError) as exc:
                entry["note"] = f"Could not be checked: {exc}"
    store.save()
    return gone


def check(store, vault, now=None):
    """The "Check now" button: verify what was created, then create what is due or was found missing."""
    verify(store, vault, now)
    return run_due(store, vault, now)


def create_now(store, vault, item, now=None):
    """The user's "Schedule now": create a coming stream at once at every destination that lacks it."""
    done = []
    for dest, _ in item["targets"]:
        entry = store.entry(item["schedule"]["id"], item["date"], dest["id"])
        if not (entry and entry["status"] == "created"):
            done.append(create(store, vault, item, dest, now))
    return done


def sync(store, vault, item, now=None):
    """The user's "Update now", and what follows an edit of a scheduled stream: send the title,
    description and time again to every destination, and create whatever is missing."""
    return [create(store, vault, item, dest, now, update=True) for dest, _ in item["targets"]]


def find(store, schedule_id, date_key, now=None):
    """The coming stream of a schedule on a date, as upcoming() describes it now (or None)."""
    return next((i for i in upcoming(store, now, limit=1000)
                 if i["schedule"]["id"] == schedule_id and i["date"] == date_key), None)


def cancel(store, vault, item, now=None):
    """The user's "Cancel": delete a coming stream from YouTube and skip its date, so it is not created
    again. Returns sentences about what could not be deleted (an empty list when all went well)."""
    problems = []
    schedule = item["schedule"]
    for dest, _ in item["targets"]:
        entry = store.entry(schedule["id"], item["date"], dest["id"])
        if not entry or entry["status"] != "created":
            continue
        if dest["kind"] == "youtube":
            try:
                token = youtube.access_token(dest["client_id"], vault.get(dest["id"], "client_secret"),
                                             vault.get(dest["id"], "refresh_token"))
                youtube.delete_broadcast(token, entry["remote_id"])
            except (net.ApiError, vault_module.VaultError) as exc:
                entry["note"] = f"Could not be deleted on YouTube: {exc}"
                problems.append(f"{dest['name']}: {exc}")
                continue
            entry.update(status="deleted", note="Deleted on YouTube from this app.", at=OLD, url="")
        else:   # a website keeps showing what it showed; there is nothing of its own to delete
            entry.update(status="deleted", at=OLD,
                         note="The stream was cancelled. The website shows it until the next stream is created.")
    if not problems:
        schedule.setdefault("overrides", {}).setdefault(item["date"], {})["skip"] = True
    store.save()
    return problems


def created_of(store, schedule, now=None):
    """The coming streams of a schedule that exist on a platform (to offer deleting them with the schedule)."""
    return [i for i in upcoming(store, now, limit=1000) if i["schedule"]["id"] == schedule["id"]
            and any(e and e["status"] == "created" and d["kind"] == "youtube" for d, e in i["targets"])]


def test_destination(vault, dest):
    """Ask a platform whether the saved sign-in still works. Returns a few words about what answered."""
    o = dest.get("options", {})
    if dest["kind"] == "youtube":
        token = youtube.access_token(dest["client_id"], vault.get(dest["id"], "client_secret"),
                                     vault.get(dest["id"], "refresh_token"))
        return youtube.channel(token)["title"]
    if dest["kind"] == "wix":
        data = wix.item(vault.get(dest["id"], "api_key"), dest["account_id"], o["collection"], o["item_id"])
        return f"{dest['name']}: {data.get('title') or o['item_id']}"
    if dest["kind"] == "wordpress":
        wordpress.content(dest["account_id"], o["user"], vault.get(dest["id"], "app_password"), o["pattern_id"])
        return f"{dest['name']}: {o.get('pattern_title') or o['pattern_id']}"
    if dest["kind"] == "webhook":
        now = datetime.now()
        webhook.send(vault.get(dest["id"], "url"), webhook.payload(
            "Test from Stream Scheduler", "", "https://www.youtube.com/watch?v=test", recurrence.to_utc(now), now,
            "Test", test=True))
        return f"{dest['name']} (a test message was sent)"
    raise net.ApiError("This kind of destination cannot be tested.")


def preview(store, schedule, count=3, now=None):
    """What a schedule would send for its next streams, without sending anything: for each stream its
    time, title, description and what a platform would refuse, and for each destination the settings
    that go with it, as (name, value) lines. `schedule` need not be saved yet."""
    now = now or datetime.now()
    clock = store.settings.get("clock", "12")
    streams = []
    for when in recurrence.occurrences(schedule, now, now + timedelta(days=366))[:count]:
        title, description, _ = text_for(store, schedule, when)
        dests = [d for d in (store.destination(i) for i in schedule.get("destinations", []))
                 if d and d["kind"] in ENABLED]
        dests.sort(key=lambda d: d["kind"] != "youtube")
        problems = titles.problems(title, description) if any(d["kind"] == "youtube" for d in dests) else \
            ([] if title else ["The title is empty."])
        if dests and not any(d["kind"] == "youtube" for d in dests):
            problems.append("No YouTube channel is chosen: a website shows the YouTube stream's link.")
        shown = []
        for dest in dests:
            o = dest.get("options", {})
            if dest["kind"] == "youtube":
                o = youtube_options(schedule, dest, schedule.get("thumbnail", ""))
                lines = [("Who can watch", o.get("privacy", "public").capitalize()),
                         ("Starts (UTC, as YouTube is told)", recurrence.to_utc(when).strftime("%Y-%m-%d %H:%M")),
                         ("Stream key", o.get("stream_title") or "chosen in YouTube Studio"),
                         ("Made for kids", "Yes" if o.get("made_for_kids") else "No"),
                         ("Starts and stops by itself", "Yes" if o.get("auto_start", True) else "No"),
                         ("Delay", dict(youtube.LATENCY).get(o.get("latency") or "normal", "Normal").split(":")[0]),
                         ("Category", dict(youtube.CATEGORIES).get(str(o.get("category") or ""), "YouTube's own choice")),
                         ("Playlist", youtube.playlist_id(o.get("playlist", "")) or
                          ("Not understood: paste the playlist's link" if o.get("playlist") else "None")),
                         ("Thumbnail", o["thumbnail"] or "YouTube's own picture")]
                if o["thumbnail"] and youtube.thumbnail_problem(o["thumbnail"]):
                    problems.append(youtube.thumbnail_problem(o["thumbnail"]))
            elif dest["kind"] == "wix":
                lines = [("Gets", "the YouTube stream's link" + (" and the title" if o.get("title_field") else "")),
                         ("Where", f"collection {o.get('collection')}, item “{o.get('item_title')}”")]
            elif dest["kind"] == "wordpress":
                lines = [("Gets", "the YouTube stream, as an embedded video" + (" under its title" if o.get("show_title") else "")),
                         ("Where", f"the pattern “{o.get('pattern_title')}” on {dest.get('account_id')}")]
            else:
                lines = [("Gets", "the title, description, start time and the YouTube link, as JSON")]
            shown.append({"name": dest["name"], "kind": dest["kind"], "lines": lines})
        streams.append({"when": when, "create_at": recurrence.create_at(schedule, when), "title": title,
                        "description": description, "problems": problems, "destinations": shown,
                        "clock": clock})
    return streams
