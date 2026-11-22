"""The work: which streams are coming up, and creating the ones whose time has come.

run_due() is called every minute while the app runs (and by `app.py --run` from the system's task
scheduler). It is safe to call again and again: a stream that was created at a destination is
written to the history at once and is never created twice.
"""
from datetime import datetime, time, timedelta

import facebook
import net
import obs
import obslaunch
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


AUTO = ("auto_start", "auto_stop")   # YouTube's enableAutoStart and enableAutoStop


def youtube_auto(options):
    """(auto_start, auto_stop) of a channel's options. Both on when never set (YouTube's own default)."""
    return tuple(bool(options.get(key, True)) for key in AUTO)


def youtube_options(schedule, dest, thumbnail=""):
    """How a schedule's stream is made on a channel: the channel's own options, with what the schedule
    says otherwise (who can watch, the playlist, starting and ending with OBS) and the stream's
    thumbnail. A schedule that never set auto_start or auto_stop follows the channel as it is now."""
    options = dict(dest.get("options", {}))
    for key in ("privacy", "playlist"):
        if schedule.get(key):
            options[key] = schedule[key]
    for key in AUTO:
        if schedule.get(key) is not None:
            options[key] = bool(schedule[key])
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
    """The "Check now" button: verify what was created, then create what is due or was found missing,
    then look at OBS for the streams of the next three hours."""
    verify(store, vault, now)
    done = run_due(store, vault, now)
    obs_check_now(store, vault, now)
    return done


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


def encoder_password(vault, encoder):
    """The OBS password of an encoder ("" when its OBS asks for none)."""
    return vault.get(encoder["id"], "password") if encoder.get("auth", True) else ""


def test_encoder(vault, encoder):
    """Connect to an encoder's OBS. Returns a line about it: its version, profile and scene collection."""
    return obs.describe(obs.info(encoder["host"], encoder["port"], encoder_password(vault, encoder)))


# ---- OBS before a service ------------------------------------------------------------------------
# A schedule can name an encoder (OBS on this or another computer). Before each of its streams the app
# looks at OBS twice, by default 55 and 20 minutes before the start: is OBS open, and does it stream to
# the key the YouTube broadcast is bound to? It only looks; what to do about it stays with a person.

OBS_CHECKS = (55, 20)          # minutes before the start
OBS_OPEN = 60                  # OBS on this computer is opened this long before the start (0: not opened)
OBS_MANUAL = timedelta(hours=3)  # "Check now" also looks at OBS for the streams of the next three hours


def obs_rounds(schedule):
    """The minutes before the start at which a schedule's OBS is looked at, earliest first."""
    found = []
    for m in schedule.get("obs_checks") or OBS_CHECKS:
        try:
            if int(m) > 0 and int(m) not in found:
                found.append(int(m))
        except (TypeError, ValueError):
            continue
    return sorted(found, reverse=True)


def obs_state(store):
    """What was found at each stream's checks, by "<schedule id>|<date>"."""
    return store.data.setdefault("obs", {})


def obs_key(item):
    return f"{item['schedule']['id']}|{item['date']}"


def obs_due(store, now=None):
    """[(item, encoder, round)] of the streams whose OBS is to be looked at now. Each round is done once;
    when the computer was off at an earlier round's time, only the latest round that has come is done."""
    now = now or datetime.now()
    due = []
    for item in upcoming(store, now, limit=1000):
        encoder = store.encoder(item["schedule"].get("encoder_id"))
        if not encoder or item["skipped"]:
            continue
        rounds = obs_rounds(item["schedule"])
        come = [i for i, m in enumerate(rounds) if now >= item["when"] - timedelta(minutes=m)]
        if not come:
            continue
        done = obs_state(store).get(obs_key(item), {}).get("round", -1)
        if come[-1] > done:
            due.append((item, encoder, come[-1]))
    return due


def obs_first_check(item):
    """When the first look at OBS is, for a stream whose schedule names an encoder."""
    rounds = obs_rounds(item["schedule"])
    return item["when"] - timedelta(minutes=rounds[0]) if rounds else None


def _key_name(keys, key):
    found = next((k for k in keys if k["key"] and k["key"] == key), None)
    return f"the stream key “{found['title']}”" if found else "a stream key that is not on this channel"


def obs_check(store, vault, item, encoder, now=None):
    """Look at OBS for one stream. Returns {"at", "ok", "problems": [{"code", "text"}], "notes": [...]}.
    Codes: closed, unreachable, password, old, not_obs (check 1); key (check 2). OBS's stream key is
    compared here and dropped."""
    now = now or datetime.now()
    result = {"at": now.strftime("%Y-%m-%dT%H:%M:%S"), "encoder": encoder["name"], "problems": [], "notes": []}
    where = encoder["name"]
    try:
        with obs.connect(encoder["host"], encoder["port"], encoder_password(vault, encoder)) as c:
            c.request("GetVersion")
            answer = c.request("GetStreamServiceSettings")
    except obs.ObsError as exc:
        code = exc.reason if exc.reason in ("closed", "unreachable", "password", "old", "not_obs") else "closed"
        text = {"closed": f"OBS isn't open on {where}, or its WebSocket server is switched off.",
                "unreachable": f"{where} could not be reached on the network. Is it switched on?"}.get(code, str(exc))
        opened = obs_state(store).get(obs_key(item), {}).get("opened", {})
        if code == "closed" and opened.get("result") == "failed":
            text += " " + opened["text"]
        elif code == "closed" and opened.get("result") == "opened":
            text += (f" {opened['text'][:-1]}, but it does not answer: it may be waiting at a question on the "
                     "screen, or its WebSocket server is switched off.")
        result["problems"].append({"code": code, "text": text})
        result["ok"] = False
        return result
    except vault_module.VaultError as exc:
        result["problems"].append({"code": "password", "text": f"The OBS password of {where} is missing: {exc}"})
        result["ok"] = False
        return result
    settings = answer.get("streamServiceSettings") or {}
    obs_key_now = settings.get("key", "")
    service = f"{settings.get('service', '')} {settings.get('server', '')}".lower()
    broadcasts = [(d, e) for d, e in item["targets"] if d["kind"] == "youtube" and e and e["status"] == "created"
                  and e.get("remote_id")]
    if not broadcasts:
        result["notes"].append("The stream key is checked once the YouTube stream exists.")
    expected, named = [], ""
    for dest, entry in broadcasts:
        try:
            token = youtube.access_token(dest["client_id"], vault.get(dest["id"], "client_secret"),
                                         vault.get(dest["id"], "refresh_token"))
            bound = youtube.bound_stream_id(token, entry["remote_id"])
            if not bound:
                result["notes"].append(f"{dest['name']}: the YouTube stream is not bound to a stream key yet.")
                continue
            keys = youtube.stream_keys(token)
        except (net.ApiError, vault_module.VaultError) as exc:
            result["notes"].append(f"The stream key could not be checked: YouTube did not answer ({exc}).")
            continue
        mine = next((k for k in keys if k["id"] == bound), None)
        if not (mine and mine["key"]):
            result["notes"].append(f"{dest['name']}: the stream key of the YouTube stream was not found.")
        else:
            expected.append(mine)
            named = named or (_key_name(keys, obs_key_now) if obs_key_now else "")
    if expected:
        if not obs_key_now:
            if "youtube" in service:
                result["notes"].append("OBS uses its own YouTube sign-in (Connect account) instead of a stream key, "
                                       "so the key could not be checked.")
            else:
                result["problems"].append({"code": "key", "text": f"OBS on {where} has no stream key set."})
        elif not any(k["key"] == obs_key_now for k in expected):
            target = named if "youtube" in service or not service.strip() else "a service other than YouTube"
            want = " or ".join(f"“{k['title']}”" for k in expected)
            result["problems"].append({"code": "key", "text": f"OBS on {where} is set to {target}, but "
                                       f"{item['schedule']['name']} is bound to the stream key {want}."})
    result["ok"] = not result["problems"]
    return result


def obs_open_minutes(schedule):
    """How long before the start OBS is opened; 0 when it is not."""
    try:
        return max(0, int(schedule.get("obs_open", OBS_OPEN)))
    except (TypeError, ValueError):
        return OBS_OPEN


def obs_open_due(store, now=None):
    """[(item, encoder)] of the streams whose OBS on this computer is to be opened now (once each)."""
    now = now or datetime.now()
    due = []
    for item in upcoming(store, now, limit=1000):
        encoder = store.encoder(item["schedule"].get("encoder_id"))
        minutes = obs_open_minutes(item["schedule"])
        if (encoder and encoder.get("local") and minutes and not item["skipped"]
                and now >= item["when"] - timedelta(minutes=minutes)
                and "opened" not in obs_state(store).get(obs_key(item), {})):
            due.append((item, encoder))
    return due


def open_obs(store, vault, now=None):
    """Open OBS on this computer for the streams that are due, unless it is open already. Records what
    happened for each stream ("opened", "running" or "failed", with a sentence). Returns the records."""
    now = now or datetime.now()
    done = []
    for item, encoder in obs_open_due(store, now):
        clock = store.settings.get("clock", "12")
        record = {"at": now.strftime("%Y-%m-%dT%H:%M:%S")}
        open_already = obslaunch.running()
        if open_already is None:   # cannot tell from the process list: ask OBS itself
            try:
                obs.connect(encoder["host"], encoder["port"], encoder_password(vault, encoder), timeout=3).close()
                open_already = True
            except obs.ObsError as exc:
                open_already = exc.reason != "closed"
            except vault_module.VaultError:
                open_already = False
        if open_already:
            record.update(result="running", text="OBS was open already.")
        else:
            program = obslaunch.find(encoder.get("program", ""))
            schedule = item["schedule"]
            if not program:
                record.update(result="failed", text="The app could not open it: OBS was not found on this computer. "
                                                    "Choose the OBS program with Change on the Destinations page.")
            else:
                try:
                    obslaunch.launch(program, schedule.get("obs_profile", ""), schedule.get("obs_collection", ""))
                    record.update(result="opened", text=f"The app opened OBS at {titles.format_time(now, clock)}.")
                except OSError as exc:
                    record.update(result="failed", text=f"The app could not open OBS ({exc.strerror or exc}).")
        obs_state(store).setdefault(obs_key(item), {"round": -1, "told": []})["opened"] = record
        done.append(record)
    if done:
        store.save()
    return done


def obs_summary(result):
    """One line about a check, for the Upcoming page."""
    if result["problems"]:
        return " ".join(p["text"] for p in result["problems"])
    return "Ready." + "".join(f" {n}" for n in result["notes"])


def obs_record(store, item, result, round_=None, now=None):
    """Keep what a check found (and which round it was), and forget the checks of past days."""
    state = obs_state(store)
    old = state.get(obs_key(item), {})
    state[obs_key(item)] = {**result, "round": old.get("round", -1) if round_ is None else round_,
                            "told": old.get("told", [])}
    if "opened" in old:
        state[obs_key(item)]["opened"] = old["opened"]
    cutoff = ((now or datetime.now()) - timedelta(days=2)).strftime("%Y-%m-%d")
    for key in [k for k in state if k.split("|")[-1] < cutoff]:
        del state[key]
    return state[obs_key(item)]


def obs_check_now(store, vault, now=None, item=None):
    """The user's look at OBS (a stream's "Check OBS", or Check now): every stream with an encoder in the
    next three hours, or the one given. Records what was found; sends no alert. Returns the results."""
    now = now or datetime.now()
    items = [item] if item else [i for i in upcoming(store, now, limit=1000) if i["when"] - now <= OBS_MANUAL]
    done = []
    for i in items:
        encoder = store.encoder(i["schedule"].get("encoder_id"))
        if encoder and not i["skipped"]:
            done.append(obs_record(store, i, obs_check(store, vault, i, encoder, now), now=now))
    store.save()
    return done


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
                         ("Starts when OBS connects", "Yes" if o.get("auto_start", True) else "No"),
                         ("Ends when OBS stops", "Yes" if o.get("auto_stop", True) else "No"),
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
