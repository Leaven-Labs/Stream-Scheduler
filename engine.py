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
import wix
import youtube
from store import new_id

MIN_AHEAD = timedelta(minutes=12)    # Facebook refuses a start less than 10 minutes away
MAX_AHEAD = timedelta(days=7)        # ... or more than 7 days away
RETRY_AFTER = timedelta(minutes=15)  # wait this long before trying a failed one again
LOOK_AHEAD = timedelta(days=28)
# The kinds of destination in use. Facebook is switched off: it no longer lets an app like this one
# schedule a live video with the Page's persistent stream key. Its code (facebook.py) is kept.
ENABLED = {"youtube", "wix"}


def text_for(store, schedule, when):
    """(title, description, overridden) of the stream at `when`: the schedule's templates with the date
    filled in, unless the user typed other words for this one date."""
    over = schedule.get("overrides", {}).get(recurrence.date_key(when), {})
    clock = store.settings.get("clock", "12")
    fill = lambda text: titles.render(text, when, schedule.get("date_format", "long"), clock)
    title = fill(over["title"] if over.get("title") else schedule.get("title", ""))
    description = fill(over["description"] if "description" in over else schedule.get("description", ""))
    return title, description, bool(over.get("title") or "description" in over or over.get("time"))


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
                          "skipped": bool(schedule.get("overrides", {}).get(key, {}).get("skip")),
                          "create_at": recurrence.create_at(schedule, when), "targets": targets})
    items.sort(key=lambda item: item["when"])
    return items[:limit]


OLD = "2000-01-01T00:00:00"   # an entry's time that lets it be tried again at once


def redo(entry, why):
    """Mark something that was done as to be done again (it is gone, or what it shows has changed)."""
    entry.update(status="failed", note=why, redo=True, at=OLD)


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
    if old.get("redo"):
        entry["redo"] = True   # stays until it works
    try:
        found = titles.problems(item["title"], item["description"]) if dest["kind"] == "youtube" else \
            ([] if item["title"].strip() else ["The title is empty."])
        if found:
            raise net.ApiError(" ".join(found))
        if dest["kind"] != "wix" and not MIN_AHEAD - timedelta(minutes=2) <= when - now:
            raise net.ApiError("Too late: the stream starts in less than 10 minutes.")
        if dest["kind"] == "facebook" and when - now > MAX_AHEAD:
            raise net.ApiError("Too early: Facebook accepts a stream at most 7 days ahead.")
        start = recurrence.to_utc(when)
        if dest["kind"] == "youtube":
            token = youtube.access_token(dest["client_id"], vault.get(dest["id"], "client_secret"),
                                         vault.get(dest["id"], "refresh_token"))
            exists = update and old.get("status") == "created" and youtube.broadcast(token, old["remote_id"])
            if exists:
                youtube.update_broadcast(token, old["remote_id"], item["title"], item["description"], start)
                made = {"id": old["remote_id"], "url": old["url"], "note": old.get("note", "")}
            else:
                made = youtube.create_broadcast(token, item["title"], item["description"], start,
                                                dest.get("options", {}))
        elif dest["kind"] == "facebook":
            made = facebook.create_live(dest["account_id"], vault.get(dest["id"], "page_token"),
                                        item["title"], item["description"], start,
                                        dest.get("options", {}).get("persistent_key", False))
        elif dest["kind"] == "wix":
            link = next((e["url"] for d, e in ((d, store.entry(schedule["id"], item["date"], d["id"]))
                                               for d, _ in item["targets"] if d["kind"] == "youtube")
                         if e and e["status"] == "created" and e.get("url")), "")
            if not link:
                raise net.ApiError("Waiting for this schedule's YouTube stream: the website shows its link. "
                                   "(The schedule must also send to a YouTube channel.)")
            made = wix.show(dest, vault.get(dest["id"], "api_key"), link, item["title"])
        else:
            raise net.ApiError(f"Unknown kind of destination: {dest['kind']}")
        entry.update(status="created", remote_id=made["id"], url=made["url"], note=made["note"])
        entry.pop("redo", None)
        if dest["kind"] == "youtube" and old.get("url") and old["url"] != made["url"]:
            for other, _ in item["targets"]:   # a new stream has a new link: websites must follow
                shown = store.entry(schedule["id"], item["date"], other["id"])
                if other["kind"] == "wix" and shown and shown["status"] == "created":
                    redo(shown, "The YouTube stream was created again; the website gets the new link.")
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
            if item["when"] - now < MIN_AHEAD and dest["kind"] != "wix":
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
