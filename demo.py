"""Made-up data to show the windows without any account: used by `app.py --uitest` and tools/screenshots.py."""
from datetime import datetime, timedelta

import engine


def fill(store, vault):
    store.destinations.extend([
        {"id": "demo-yt", "kind": "youtube", "name": "Grace Community Church", "account_id": "UCdemo",
         "client_id": "demo.apps.googleusercontent.com",
         "options": {"privacy": "public", "stream_id": "k", "stream_title": "Default stream key",
                     "made_for_kids": False, "auto_start": True, "auto_stop": True}},
        {"id": "demo-fb", "kind": "facebook", "name": "Grace Community Church", "account_id": "1",
         "options": {"persistent_key": True}}])
    store.schedules.extend([
        {"id": "demo-s1", "name": "Sunday Service", "enabled": True, "weekdays": [6], "time": "08:00",
         "lead_days": 1, "create_time": "09:00", "title": "Sunday Service - {date}",
         "description": "Join us live this {weekday} at {time}.", "date_format": "long",
         "destinations": ["demo-yt", "demo-fb"], "overrides": {}},
        {"id": "demo-s2", "name": "Midweek Prayer", "enabled": True, "weekdays": [2], "time": "19:00",
         "lead_days": 2, "create_time": "12:00", "title": "Midweek Prayer | {month} {day}",
         "description": "", "date_format": "long", "destinations": ["demo-yt"], "overrides": {}}])
    now = datetime.now()
    items = engine.upcoming(store, now)
    first = next(i for i in items if i["schedule"]["id"] == "demo-s1")
    first["schedule"]["overrides"][items[-1]["date"]] = {"skip": True}
    for dest, _ in first["targets"]:
        yt = dest["kind"] == "youtube"
        store.history.append({
            "id": "h-" + dest["id"], "schedule_id": "demo-s1", "schedule_name": "Sunday Service",
            "date": first["date"], "when": first["when"].strftime("%Y-%m-%dT%H:%M"), "destination_id": dest["id"],
            "destination_name": dest["name"], "kind": dest["kind"], "title": first["title"],
            "at": (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S"), "attempts": 1,
            "status": "created" if yt else "failed", "remote_id": "abc" if yt else "",
            "url": "https://www.youtube.com/watch?v=abc" if yt else "",
            "note": "" if yt else "(#200) The Page access token has expired. Connect the Page again."})
    vault.set("demo-yt", "client_secret", "x")
