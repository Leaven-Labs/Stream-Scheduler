"""Made-up data to show the windows without any account: used by `app.py --uitest` and tools/screenshots.py."""
from datetime import date, datetime, timedelta

import engine


def easter(year):
    """Easter Sunday of the Western churches (the Gregorian reckoning)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 19 * m) // 433
    month = (h + m - 7 * n + 90) // 25
    return date(year, month, (h + m - 7 * n + 33 * month + 19) % 32)


def lent_midweeks(today):
    """The first and last Wednesday evening of the Lent that is running or comes next: the five
    Wednesdays between Ash Wednesday and Holy Week, which have their own services."""
    for year in (today.year, today.year + 1):
        ash_wednesday = easter(year) - timedelta(days=46)
        first, last = ash_wednesday + timedelta(days=7), ash_wednesday + timedelta(days=35)
        if today <= last:
            return first, last


def fill(store, vault, now=None):
    now = now or datetime.now()
    first_lent, last_lent = lent_midweeks(now.date())
    store.destinations.extend([
        {"id": "demo-yt", "kind": "youtube", "name": "Grace Community Church", "account_id": "UCdemo",
         "client_id": "demo.apps.googleusercontent.com",
         "options": {"privacy": "public", "stream_id": "k", "stream_title": "Default stream key",
                     "made_for_kids": False, "auto_start": True, "auto_stop": True, "latency": "normal",
                     "category": "29", "playlist": "https://www.youtube.com/playlist?list=PLdemo"}},
        {"id": "demo-fb", "kind": "wix", "name": "Website", "account_id": "1",
         "options": {"collection": "Livestream", "item_id": "i1", "item_title": "Sunday stream",
                     "url_field": "videoUrl", "title_field": "title", "publish": False,
                     "page_url": "https://www.example.org/live"}}])
    store.encoders.extend([
        {"id": "demo-obs1", "kind": "obs", "name": "Traditional PC", "host": "127.0.0.1", "port": 4455,
         "local": True, "auth": True},
        {"id": "demo-obs2", "kind": "obs", "name": "Praise & Worship PC", "host": "192.168.1.42", "port": 4455,
         "local": False, "auth": True}])
    store.schedules.extend([
        {"id": "demo-s1", "name": "Sunday Service", "enabled": True, "weekdays": [6], "time": "08:00",
         "lead_days": 1, "create_time": "09:00", "title": "Sunday Service - {date}",
         "description": "Join us live this {weekday} at {time}.", "date_format": "long",
         "destinations": ["demo-yt", "demo-fb"], "overrides": {}, "encoder_id": "demo-obs1", "obs_checks": [55, 20]},
        {"id": "demo-s2", "name": "Lent Evening Prayer", "enabled": True, "weekdays": [2], "time": "19:00",
         "lead_days": 2, "create_time": "12:00", "title": "{series}, week {number} | {month} {day}",
         "series": "Lent", "starts": first_lent.strftime("%Y-%m-%d"),
         "until": last_lent.strftime("%Y-%m-%d"), "privacy": "unlisted",
         "description": "", "date_format": "long", "destinations": ["demo-yt"], "overrides": {}}])
    store.data["notify"] = {"channels": {"pushover": {"on": True},
                                         "email": {"on": True, "host": "smtp.example.org", "port": 587,
                                                   "security": "starttls", "user": "streams@example.org",
                                                   "to": "tech-team@example.org"}},
                            "events": {"summary": True}}
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
            "note": "" if yt else "Wix refused the API key for this site. Check the key and the Site ID."})
    vault.set("demo-yt", "client_secret", "x")
