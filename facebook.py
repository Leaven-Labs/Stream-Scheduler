"""Facebook: schedule live videos (as events) on a Page with the Graph API.

The user makes their own Meta app and a short-lived token for it (the wizard explains how). The app
trades that for a long-lived one, asks for the Page's own token, and keeps ONLY the Page token (in
the keychain). The app secret and the user's token are used once and then forgotten.
"""
import json

import net

GRAPH_VERSION = "v26.0"   # Meta retires versions after about two years; raise this with a release
GRAPH = f"https://graph.facebook.com/{GRAPH_VERSION}"
PERMISSIONS = ["pages_show_list", "pages_read_engagement", "pages_manage_posts"]


def pages(app_id, app_secret, user_token):
    """The Pages the token's owner manages: [{"id", "name", "token"}], with long-lived Page tokens.

    A Page token asked for with a long-lived user token does not run out on a timer (it ends when the
    user changes their password, removes the app, or loses their role on the Page)."""
    long_lived = net.request("GET", f"{GRAPH}/oauth/access_token", {
        "grant_type": "fb_exchange_token", "client_id": app_id.strip(), "client_secret": app_secret.strip(),
        "fb_exchange_token": user_token.strip()})["access_token"]
    found, url, params = [], f"{GRAPH}/me/accounts", {"fields": "id,name,access_token", "limit": 100}
    while url:
        answer = net.request("GET", url, params, token=long_lived)
        found += [{"id": p["id"], "name": p["name"], "token": p["access_token"]}
                  for p in answer.get("data", []) if p.get("access_token")]
        url, params = answer.get("paging", {}).get("next"), None
    return found


def page_name(page_id, page_token):
    """Ask for the Page's name: a cheap test that the saved token still works."""
    return net.request("GET", f"{GRAPH}/{page_id}", {"fields": "name"}, token=page_token)["name"]


def create_live(page_id, page_token, title, description, start_utc, persistent_key=False):
    """Schedule a live video on the Page. Returns {"id", "url", "note"}.

    Facebook wants the start between 10 minutes and 7 days from now. With persistent_key, the video is
    then told to use the Page's persistent stream key (the same key every week) instead of a key of
    its own. If Facebook refuses that, the stream still exists and the note says so."""
    # Facebook retired the status SCHEDULED_UNPUBLISHED ("Scheduled Live has been deprecated"). A live
    # video with event_params is created as a scheduled event instead; an event must have a description.
    made = net.request("POST", f"{GRAPH}/{page_id}/live_videos", token=page_token, form={
        "status": "UNPUBLISHED", "title": title, "description": description.strip() or title,
        "event_params": json.dumps({"start_time": int(start_utc.timestamp())})})
    note = ""
    if persistent_key:
        try:
            net.request("POST", f"{GRAPH}/{made['id']}", token=page_token,
                        form={"persistent_stream_key_status": "ENABLE"})
        except net.ApiError as exc:
            note = (f"Created, but Facebook did not switch on the persistent stream key ({exc}). This stream has "
                    "its own key: copy it from the History page, or turn on 'Persistent stream key' for it in "
                    "Facebook's Live Producer.")
    url = f"https://www.facebook.com/events/{made['event_id']}" if made.get("event_id") else ""
    if url:
        return {"id": made["id"], "url": url, "note": note}
    try:
        link = net.request("GET", f"{GRAPH}/{made['id']}", {"fields": "permalink_url"},
                           token=page_token).get("permalink_url", "")
        url = link if link.startswith("http") else ("https://www.facebook.com" + link if link else "")
    except net.ApiError:
        pass  # the stream exists; only its link is unknown
    return {"id": made["id"], "url": url, "note": note}


def stream_address(video_id, page_token):
    """The address with the stream key for the encoder (a secret: shown on request, never saved)."""
    answer = net.request("GET", f"{GRAPH}/{video_id}", {"fields": "secure_stream_url"}, token=page_token)
    return answer.get("secure_stream_url", "")
