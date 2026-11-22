"""YouTube: sign in with Google (OAuth 2.0 for desktop apps, with PKCE) and schedule live broadcasts.

The user makes their own OAuth client in Google Cloud (the wizard explains how), so the app talks
to Google directly with the user's own quota and nothing passes through anyone else's server.
Kept in the keychain: the client secret and the refresh token. The short-lived access token is
only held in memory.
"""
import base64
import hashlib
import http.server
import os
import secrets
import time
import urllib.parse

import net

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/youtube/v3"
SCOPE = "https://www.googleapis.com/auth/youtube"   # the narrowest scope that can create broadcasts
UPLOAD = "https://www.googleapis.com/upload/youtube/v3"
PRIVACY = ["public", "unlisted", "private"]
LATENCY = [("normal", "Normal: best quality"), ("low", "Low: a few seconds behind"),
           ("ultraLow", "Ultra low: for talking with viewers")]
# YouTube's video categories (their ids are the same everywhere). "" leaves YouTube's own choice.
CATEGORIES = [("", "YouTube's own choice"), ("29", "Nonprofits & Activism"), ("22", "People & Blogs"),
              ("27", "Education"), ("10", "Music"), ("24", "Entertainment"), ("25", "News & Politics"),
              ("17", "Sports"), ("28", "Science & Technology"), ("26", "Howto & Style"), ("20", "Gaming"),
              ("1", "Film & Animation"), ("23", "Comedy"), ("19", "Travel & Events"), ("15", "Pets & Animals"),
              ("2", "Autos & Vehicles")]
THUMBNAIL_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
THUMBNAIL_LIMIT = 2 * 1024 * 1024   # YouTube's limit for a thumbnail file

_DONE_PAGE = """<!doctype html><meta charset="utf-8"><title>Stream Scheduler</title>
<body style="font-family:system-ui,sans-serif;background:#0f1117;color:#eceef5;text-align:center;padding-top:18vh">
<h2>%s</h2><p style="color:#9299ad">You can close this tab and go back to Stream Scheduler.</p></body>"""


class SignIn:
    """One sign-in in the browser. start() gives the address to open; wait() returns the tokens.

    Google sends the browser back to a web server this class runs on 127.0.0.1 for the length of the
    sign-in (only this computer can reach it). `state` proves the answer belongs to our question, and
    the PKCE verifier proves to Google that the one who asks for the tokens started the sign-in."""

    def __init__(self, client_id, client_secret):
        self.client_id, self.client_secret = client_id.strip(), client_secret.strip()
        self.state = secrets.token_urlsafe(24)
        self.verifier = secrets.token_urlsafe(64)
        self.answer = None
        self.cancelled = False
        self.server = None

    def start(self):
        signin = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                if "state" not in query:  # a favicon request, or a stranger
                    self.send_error(404)
                    return
                good = secrets.compare_digest(query["state"][0], signin.state)
                signin.answer = {k: v[0] for k, v in query.items()} if good else {"error": "state"}
                page = _DONE_PAGE % ("Signed in" if good and "code" in query else "Sign-in did not finish")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(page.encode())

            def log_message(self, *args):  # nothing on the console: the address holds the code
                pass

        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.server.timeout = 0.5
        self.redirect = f"http://127.0.0.1:{self.server.server_address[1]}"
        challenge = base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode()).digest()).rstrip(b"=").decode()
        return AUTH_URL + "?" + urllib.parse.urlencode({
            "client_id": self.client_id, "redirect_uri": self.redirect, "response_type": "code",
            "scope": SCOPE, "state": self.state, "code_challenge": challenge, "code_challenge_method": "S256",
            "access_type": "offline", "prompt": "consent"})  # offline + consent: Google gives a refresh token

    def cancel(self):
        self.cancelled = True

    def wait(self, timeout=300):
        """Block until the browser comes back. Returns {"refresh_token", "access_token"}."""
        deadline = time.monotonic() + timeout
        try:
            while self.answer is None:
                if self.cancelled:
                    raise net.ApiError("The sign-in was cancelled.")
                if time.monotonic() > deadline:
                    raise net.ApiError("No answer from the browser after 5 minutes. Please try again.")
                self.server.handle_request()
        finally:
            self.server.server_close()
        if "code" not in self.answer:
            why = self.answer.get("error", "")
            raise net.ApiError("Access was not allowed in the browser." if why == "access_denied"
                               else f"The sign-in did not finish ({why}).")
        tokens = net.request("POST", TOKEN_URL, form={
            "client_id": self.client_id, "client_secret": self.client_secret, "code": self.answer["code"],
            "code_verifier": self.verifier, "grant_type": "authorization_code", "redirect_uri": self.redirect})
        if not tokens.get("refresh_token"):
            raise net.ApiError("Google did not give a long-term sign-in. Please try again.")
        return tokens


def access_token(client_id, client_secret, refresh_token):
    """A fresh access token (good for about an hour) from the saved refresh token."""
    try:
        answer = net.request("POST", TOKEN_URL, form={
            "client_id": client_id, "client_secret": client_secret, "refresh_token": refresh_token,
            "grant_type": "refresh_token"})
    except net.ApiError as exc:
        if exc.reason == "invalid_grant":
            raise net.ApiError(
                "Google no longer accepts the saved sign-in. It was revoked, or the Google Cloud app is still in "
                "'Testing' (those sign-ins end after 7 days). Use Reconnect on the Destinations page.",
                exc.status, exc.reason) from None
        raise
    return answer["access_token"]


def channel(token):
    """The signed-in channel: {"id", "title"}."""
    items = net.request("GET", f"{API}/channels", {"part": "snippet", "mine": "true"}, token=token).get("items")
    if not items:
        raise net.ApiError("This Google account has no YouTube channel. Create one on youtube.com first.")
    return {"id": items[0]["id"], "title": items[0]["snippet"]["title"]}


def streams(token):
    """The channel's reusable stream keys: [{"id", "title"}]. A broadcast bound to one of them goes
    live when the encoder sends to that key, so the key in OBS (or the encoder) never changes."""
    answer = net.request("GET", f"{API}/liveStreams",
                         {"part": "snippet,contentDetails", "mine": "true", "maxResults": 50}, token=token)
    return [{"id": s["id"], "title": s["snippet"]["title"]} for s in answer.get("items", [])
            if s.get("contentDetails", {}).get("isReusable", True)]


def stream_keys(token):
    """The channel's stream keys with their secret part: [{"id", "title", "key"}]. Only for comparing
    with the key in OBS: a key is never shown, logged or saved."""
    found, params = [], {"part": "snippet,cdn", "mine": "true", "maxResults": 50}
    while True:
        answer = net.request("GET", f"{API}/liveStreams", params, token=token)
        found += [{"id": s["id"], "title": s.get("snippet", {}).get("title", ""),
                   "key": s.get("cdn", {}).get("ingestionInfo", {}).get("streamName", "")}
                  for s in answer.get("items", [])]
        if not answer.get("nextPageToken"):
            return found
        params = {**params, "pageToken": answer["nextPageToken"]}


def bound_stream_id(token, broadcast_id):
    """The id of the stream key a broadcast is bound to ("" when none), or None when the broadcast is gone."""
    b = broadcast(token, broadcast_id)
    return None if b is None else b.get("contentDetails", {}).get("boundStreamId", "")


def create_broadcast(token, title, description, start_utc, options):
    """Schedule a broadcast. Returns {"id", "url", "note"}; note says what could not be done."""
    body = {
        "snippet": {"title": title, "description": description,
                    "scheduledStartTime": start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")},
        "status": {"privacyStatus": options.get("privacy", "public"),
                   "selfDeclaredMadeForKids": bool(options.get("made_for_kids", False))},
        "contentDetails": {"enableAutoStart": bool(options.get("auto_start", True)),
                           "enableAutoStop": bool(options.get("auto_stop", True))},
    }
    if options.get("latency") in ("low", "ultraLow"):   # "normal" is what YouTube does when nothing is said
        body["contentDetails"]["latencyPreference"] = options["latency"]
    try:
        made = net.request("POST", f"{API}/liveBroadcasts", {"part": "snippet,status,contentDetails"},
                           body=body, token=token)
    except net.ApiError as exc:
        if exc.reason in ("liveStreamingNotEnabled", "insufficientLivePermissions"):
            raise net.ApiError("Live streaming is not switched on for this YouTube channel. Enable it at "
                               "youtube.com/features (the first time takes up to 24 hours).",
                               exc.status, exc.reason) from None
        raise
    note = ""
    if options.get("stream_id"):
        try:
            net.request("POST", f"{API}/liveBroadcasts/bind",
                        {"id": made["id"], "part": "id,contentDetails", "streamId": options["stream_id"]},
                        token=token)
        except net.ApiError as exc:
            note = f"Created, but the stream key could not be attached ({exc}). Choose it in YouTube Studio."
    notes = [note] + dress(token, made["id"], title, description, options)
    if playlist_id(options.get("playlist", "")):
        try:
            net.request("POST", f"{API}/playlistItems", {"part": "snippet"}, token=token, body={"snippet": {
                "playlistId": playlist_id(options["playlist"]),
                "resourceId": {"kind": "youtube#video", "videoId": made["id"]}}})
        except net.ApiError as exc:
            notes.append(f"Not added to the playlist ({exc}). Check the playlist's link, and that it belongs "
                         "to this channel.")
    return {"id": made["id"], "url": f"https://www.youtube.com/watch?v={made['id']}",
            "note": " ".join(n for n in notes if n)}


def playlist_id(text):
    """The id in a playlist's link (youtube.com/playlist?list=PL...), or the id itself when that was typed."""
    text = (text or "").strip()
    if "list=" in text:
        text = urllib.parse.parse_qs(urllib.parse.urlparse(text).query).get("list", [""])[0]
    return text if text and all(c.isalnum() or c in "-_" for c in text) else ""


def thumbnail_problem(path):
    """Why a file cannot be a thumbnail, as a sentence ("" when it can)."""
    if os.path.splitext(path)[1].lower() not in THUMBNAIL_TYPES:
        return "A thumbnail must be a JPG or PNG picture."
    if not os.path.isfile(path):
        return f"The thumbnail picture is not there any more: {path}"
    if os.path.getsize(path) > THUMBNAIL_LIMIT:
        return "The thumbnail picture is larger than 2 MB, the most YouTube accepts."
    return ""


def dress(token, video_id, title, description, options):
    """What a broadcast gets after it exists: its category and its thumbnail. Returns notes about what
    could not be done; neither stops the stream from being scheduled."""
    notes = []
    if options.get("category"):
        try:   # the category belongs to the video; YouTube wants the title sent along with it
            net.request("PUT", f"{API}/videos", {"part": "snippet"}, token=token, body={
                "id": video_id, "snippet": {"title": title, "description": description,
                                            "categoryId": str(options["category"])}})
        except net.ApiError as exc:
            notes.append(f"The category could not be set ({exc}).")
    path = options.get("thumbnail")
    if path:
        problem = thumbnail_problem(path)
        try:
            if problem:
                raise net.ApiError(problem)
            with open(path, "rb") as fh:
                data = fh.read()
            net.request("POST", f"{UPLOAD}/thumbnails/set", {"videoId": video_id, "uploadType": "media"},
                        token=token, timeout=90,
                        raw=(data, THUMBNAIL_TYPES[os.path.splitext(path)[1].lower()]))
        except OSError as exc:
            notes.append(f"The thumbnail could not be read ({exc}).")
        except net.ApiError as exc:
            hint = (" YouTube allows custom thumbnails once the channel is verified by phone: "
                    "youtube.com/verify") if exc.status == 403 else ""
            notes.append(f"The thumbnail could not be set ({exc}).{hint}")
    return notes


def broadcast(token, broadcast_id):
    """A broadcast of the channel by its id, or None when it is not there (deleted on YouTube)."""
    items = net.request("GET", f"{API}/liveBroadcasts", {"part": "snippet,status,contentDetails", "id": broadcast_id},
                        token=token).get("items")
    return items[0] if items else None


def update_broadcast(token, broadcast_id, title, description, start_utc, options=None):
    """Change a broadcast that has not started yet: its title, description, start time and who can watch,
    and send its category and thumbnail again. Returns a note about what could not be done."""
    options = options or {}
    body = {"id": broadcast_id, "snippet": {"title": title, "description": description,
                                            "scheduledStartTime": start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")}}
    if options.get("privacy") in PRIVACY:
        body["status"] = {"privacyStatus": options["privacy"]}
    net.request("PUT", f"{API}/liveBroadcasts", {"part": ",".join(k for k in body if k != "id")}, token=token,
                body=body)
    return " ".join(dress(token, broadcast_id, title, description, options))


def delete_broadcast(token, broadcast_id):
    """Delete a broadcast from the channel. One that is gone already counts as deleted."""
    try:
        net.request("DELETE", f"{API}/liveBroadcasts", {"id": broadcast_id}, token=token)
    except net.ApiError as exc:
        if exc.status != 404:
            raise
