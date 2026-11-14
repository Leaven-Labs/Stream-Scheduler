"""Is there a newer version? Asked of GitHub's public list of this project's releases, once a day.

Nothing about you is sent: the request carries only the app's name and version. It can be switched
off in Settings. The app never downloads or installs anything itself; it shows a link to the release.
"""
import re
from datetime import datetime, timedelta

import net
import paths

RELEASES = "https://api.github.com/repos/Leaven-Labs/Stream-Scheduler/releases"
EVERY = timedelta(hours=24)


def number(text):
    """"v0.0.5" or "0.0.5-alpha" -> (0, 0, 5)."""
    found = re.search(r"\d+(?:\.\d+)*", text or "")
    return tuple(int(p) for p in found.group().split(".")) if found else ()


def latest():
    """The newest release: {"version", "url"}, or None. A pre-release counts only while this copy is one."""
    answer = net.request("GET", RELEASES, {"per_page": 10}, headers={"Accept": "application/vnd.github+json"},
                         timeout=15)
    pre = "-" in paths.VERSION
    found = [r for r in answer if isinstance(r, dict) and not r.get("draft") and (pre or not r.get("prerelease"))
             and number(r.get("tag_name"))] if isinstance(answer, list) else []
    if not found:
        return None
    best = max(found, key=lambda r: number(r["tag_name"]))
    return {"version": best["tag_name"].lstrip("v"), "url": best.get("html_url", "")}


def check(store, now=None, force=False):
    """Ask GitHub when a day has passed since the last time (or always, with force). The answer is kept
    in the settings file; no connection changes nothing. Returns available(store)."""
    now = now or datetime.now()
    seen = store.data.setdefault("update", {})
    if not force:
        if not store.settings.get("update_check", True):
            return None
        if seen.get("checked") and now - datetime.fromisoformat(seen["checked"]) < EVERY:
            return available(store)
    try:
        found = latest()
    except net.ApiError:
        if force:
            raise
        return available(store)
    seen.update(checked=now.strftime("%Y-%m-%dT%H:%M:%S"), version=(found or {}).get("version", ""),
                url=(found or {}).get("url", ""))
    store.save()
    return available(store)


def available(store):
    """{"version", "url"} of a release newer than this copy, or None."""
    seen = store.data.get("update") or {}
    if seen.get("version") and number(seen["version"]) > number(paths.VERSION):
        return {"version": seen["version"], "url": seen.get("url", "")}
    return None
