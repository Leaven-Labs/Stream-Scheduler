"""The work: which streams are coming up, and creating the ones whose time has come.

run_due() is called every minute while the app runs (and by `app.py --run` from the system's task
scheduler). It is safe to call again and again: a stream that was created at a destination is
written to the history at once and is never created twice.
"""
from datetime import datetime, timedelta

import facebook
import net
import recurrence
import titles
import vault as vault_module
import youtube
from store import new_id

MIN_AHEAD = timedelta(minutes=12)    # Facebook refuses a start less than 10 minutes away
MAX_AHEAD = timedelta(days=7)        # ... or more than 7 days away
RETRY_AFTER = timedelta(minutes=15)  # wait this long before trying a failed one again
LOOK_AHEAD = timedelta(days=28)


def text_for(store, schedule, when):
    """(title, description, overridden) of the stream at `when`: the schedule's templates with the date
    filled in, unless the user typed other words for this one date."""
    over = schedule.get("overrides", {}).get(recurrence.date_key(when), {})
    clock = store.settings.get("clock", "12")
    fill = lambda text: titles.render(text, when, schedule.get("date_format", "long"), clock)
    title = fill(over["title"] if over.get("title") else schedule.get("title", ""))
    description = fill(over["description"] if "description" in over else schedule.get("description", ""))
    return title, description, bool(over.get("title") or "description" in over)


def upcoming(store, now=None, limit=12):
    """The coming streams of every schedule that is switched on, soonest first."""
    now = now or datetime.now()
    items = []
    for schedule in store.schedules:
        if not schedule.get("enabled", True):
            continue
        for when in recurrence.occurrences(schedule, now, now + LOOK_AHEAD):
            key = recurrence.date_key(when)
            title, description, overridden = text_for(store, schedule, when)
            targets = [(dest, store.entry(schedule["id"], key, dest["id"]))
                       for dest in (store.destination(i) for i in schedule.get("destinations", [])) if dest]
            items.append({"schedule": schedule, "when": when, "date": key, "title": title,
                          "description": description, "overridden": overridden,
                          "skipped": bool(schedule.get("overrides", {}).get(key, {}).get("skip")),
                          "create_at": recurrence.create_at(schedule, when), "targets": targets})
    items.sort(key=lambda item: item["when"])
    return items[:limit]


def create(store, vault, item, dest, now=None):
    """Create one stream at one destination and write the outcome to the history. Returns the entry."""
    now = now or datetime.now()
    schedule, when = item["schedule"], item["when"]
    old = store.entry(schedule["id"], item["date"], dest["id"]) or {}
    entry = {"id": old.get("id") or new_id(), "schedule_id": schedule["id"], "schedule_name": schedule["name"],
             "date": item["date"], "when": when.strftime("%Y-%m-%dT%H:%M"), "destination_id": dest["id"],
             "destination_name": dest["name"], "kind": dest["kind"], "title": item["title"],
             "at": now.strftime("%Y-%m-%dT%H:%M:%S"), "attempts": old.get("attempts", 0) + 1,
             "status": "failed", "remote_id": "", "url": "", "note": ""}
    try:
        found = titles.problems(item["title"], item["description"]) if dest["kind"] == "youtube" else \
            ([] if item["title"].strip() else ["The title is empty."])
        if found:
            raise net.ApiError(" ".join(found))
        if not MIN_AHEAD - timedelta(minutes=2) <= when - now:
            raise net.ApiError("Too late: the stream starts in less than 10 minutes.")
        if dest["kind"] == "facebook" and when - now > MAX_AHEAD:
            raise net.ApiError("Too early: Facebook accepts a stream at most 7 days ahead.")
        start = recurrence.to_utc(when)
        if dest["kind"] == "youtube":
            token = youtube.access_token(dest["client_id"], vault.get(dest["id"], "client_secret"),
                                         vault.get(dest["id"], "refresh_token"))
            made = youtube.create_broadcast(token, item["title"], item["description"], start,
                                            dest.get("options", {}))
        elif dest["kind"] == "facebook":
            made = facebook.create_live(dest["account_id"], vault.get(dest["id"], "page_token"),
                                        item["title"], item["description"], start)
        else:
            raise net.ApiError(f"Unknown kind of destination: {dest['kind']}")
        entry.update(status="created", remote_id=made["id"], url=made["url"], note=made["note"])
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
        if item["skipped"] or item["create_at"] > now or item["when"] - now < MIN_AHEAD:
            continue
        for dest, entry in item["targets"]:
            if entry and entry["status"] == "created":
                continue
            if entry and now - datetime.fromisoformat(entry["at"]) < RETRY_AFTER:
                continue
            done.append(create(store, vault, item, dest, now))
    return done


def create_now(store, vault, item, now=None):
    """The user's "Schedule now": create a coming stream at once at every destination that lacks it."""
    return [create(store, vault, item, dest, now) for dest, entry in item["targets"]
            if not (entry and entry["status"] == "created")]
