"""When a schedule's streams are, and when each one is to be created on the platforms.

A schedule says: the stream is every week on these weekdays at this time, and it is created
`lead_days` days before, at `create_time`. Example: Sundays at 08:00, created 1 day before at 09:00
(Saturday morning). All times are the computer's local time, without a zone; to_utc() turns one into
the moment the platforms are told.
"""
from datetime import date, datetime, time, timedelta, timezone

MAX_LEAD_DAYS = 6   # Facebook accepts a start at most 7 days ahead


def parse_time(text):
    hour, minute = (int(part) for part in text.split(":"))
    return time(hour, minute)


def date_key(when):
    return when.strftime("%Y-%m-%d")


def occurrences(schedule, after, until):
    """The stream times of a schedule later than `after`, up to `until`, in order."""
    at = parse_time(schedule["time"])
    if schedule.get("once"):   # a single stream on one date; `until` does not hide it
        when = datetime.combine(date.fromisoformat(schedule["once"]), at)
        return [when] if after < when else []
    days = set(schedule.get("weekdays") or [])
    found, day = [], after.date()
    while day <= until.date():
        when = datetime.combine(day, at)
        if day.weekday() in days and after < when <= until:
            found.append(when)
        day += timedelta(days=1)
    return found


def create_at(schedule, when):
    """The moment the stream of `when` is to be created on the platforms."""
    lead = max(1, min(MAX_LEAD_DAYS, int(schedule.get("lead_days", 1))))
    return datetime.combine(when.date() - timedelta(days=lead), parse_time(schedule.get("create_time", "09:00")))


def to_utc(local):
    """A local time without a zone -> the same moment in UTC (the system's zone and summer time apply)."""
    return local.astimezone(timezone.utc)


def describe(schedule, clock="12"):
    """One line for the lists: "Every Sunday at 8:00 AM · created 1 day before at 9:00 AM"."""
    from titles import WEEKDAYS, format_date, format_time
    days = sorted(schedule.get("weekdays") or [])
    lead = int(schedule.get("lead_days", 1))
    made = (f"created {lead} day{'s' if lead != 1 else ''} before at "
            f"{format_time(parse_time(schedule.get('create_time', '09:00')), clock)}")
    if schedule.get("once"):
        day = date.fromisoformat(schedule["once"])
        return f"Once, on {format_date(day, 'weekday')} at {format_time(parse_time(schedule['time']), clock)} · {made}"
    if len(days) == 7:
        names = "day"
    elif not days:
        return "No weekday chosen"
    else:
        names = ", ".join(WEEKDAYS[d] for d in days[:-1]) + (" and " if len(days) > 1 else "") + WEEKDAYS[days[-1]]
    return f"Every {names} at {format_time(parse_time(schedule['time']), clock)} · {made}"
