"""A web address that is told about each new stream (a "webhook").

For websites and services this app has no guide for: an automation service (Zapier, Make, IFTTT) or a
script of your own receives the stream's details and does what it likes with them, such as updating a
Squarespace page. The address often carries a key, so it is kept in the keychain like a password.
"""
import urllib.parse

import net
import paths


def address(text):
    """The address as typed, or ApiError when it is not HTTPS (the stream's details would travel in the open)."""
    text = (text or "").strip()
    parts = urllib.parse.urlparse(text)
    if parts.scheme != "https" or not parts.netloc:
        raise net.ApiError("Enter the web address, starting with https://")
    return text


def payload(title, description, link, start_utc, start_local, schedule_name, test=False):
    """What is sent, as JSON. `start` is the moment in UTC; `start_local` is the computer's own time."""
    return {"event": "test" if test else "stream.scheduled", "app": paths.APP_NAME, "title": title,
            "description": description, "url": link, "video_id": link.rpartition("v=")[2] if "v=" in link else "",
            "start": start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), "start_local": start_local.strftime("%Y-%m-%dT%H:%M"),
            "schedule": schedule_name}


def send(url, data):
    try:
        net.request("POST", address(url), body=data)
    except net.ApiError as exc:
        if exc.status:
            raise net.ApiError(f"The web address answered with an error ({exc}).", exc.status, exc.reason) from None
        raise
