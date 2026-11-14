"""Titles and descriptions with the stream's date filled in.

A schedule keeps a template such as "Sunday Service - {date}". For the stream of November 15, 2027
that becomes "Sunday Service - November 15, 2027". The names are English and do not depend on the
system's language, so the same schedule gives the same title on every computer.
"""
import re

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# key -> (what the menu shows, how the date is written)
DATE_FORMATS = {
    "long": lambda d: f"{MONTHS[d.month - 1]} {d.day}, {d.year}",
    "weekday": lambda d: f"{WEEKDAYS[d.weekday()]}, {MONTHS[d.month - 1]} {d.day}, {d.year}",
    "short": lambda d: f"{MONTHS[d.month - 1][:3]} {d.day}, {d.year}",
    "dmy": lambda d: f"{d.day} {MONTHS[d.month - 1]} {d.year}",
    "us": lambda d: f"{d.month}/{d.day}/{d.year}",
    "eu": lambda d: f"{d.day:02d}/{d.month:02d}/{d.year}",
    "iso": lambda d: f"{d.year}-{d.month:02d}-{d.day:02d}",
}
VARIABLES = ["date", "weekday", "month", "day", "year", "time"]
TITLE_LIMIT = 100          # YouTube's limit; Facebook allows more
DESCRIPTION_LIMIT = 5000   # YouTube's limit


def format_date(d, date_format="long"):
    return DATE_FORMATS.get(date_format, DATE_FORMATS["long"])(d)


def format_time(t, clock="12"):
    if clock == "24":
        return f"{t.hour:02d}:{t.minute:02d}"
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def render(template, when, date_format="long", clock="12"):
    """Fill {date}, {weekday}, {month}, {day}, {year} and {time}. Anything else in braces stays as typed."""
    values = {"date": format_date(when, date_format), "weekday": WEEKDAYS[when.weekday()],
              "month": MONTHS[when.month - 1], "day": str(when.day), "year": str(when.year),
              "time": format_time(when, clock)}
    return re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1).lower(), m.group(0)), template or "")


def problems(title, description=""):
    """What a platform would refuse, as sentences for the user (an empty list when all is well)."""
    found = []
    if not title.strip():
        found.append("The title is empty.")
    if len(title) > TITLE_LIMIT:
        found.append(f"The title is {len(title)} characters; YouTube allows {TITLE_LIMIT}.")
    if "<" in title or ">" in title or "<" in description or ">" in description:
        found.append("YouTube does not allow the characters < and > in titles and descriptions.")
    if len(description) > DESCRIPTION_LIMIT:
        found.append(f"The description is {len(description)} characters; YouTube allows {DESCRIPTION_LIMIT}.")
    return found
