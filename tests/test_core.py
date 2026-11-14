"""Tests of everything but the windows. Run: python -m unittest discover tests"""
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import engine
import facebook
import net
import recurrence
import titles
import youtube
from store import Store
from vault import MemoryVault, Vault, VaultError


class FakeNet:
    """Stands in for net.send: records every request and answers from a list of (address part, status, json)."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, method, url, headers, data, timeout):
        self.calls.append({"method": method, "url": url, "headers": headers, "data": data})
        for part, status, payload in self.routes:
            if part in url:
                return status, json.dumps(payload).encode()
        raise AssertionError("unexpected request: " + url)


OK_ROUTES = [
    ("oauth2.googleapis.com/token", 200, {"access_token": "ya29.access"}),
    ("liveBroadcasts/bind", 200, {"id": "yt123"}),
    ("liveBroadcasts", 200, {"id": "yt123"}),
    ("/live_videos", 200, {"id": "fb456"}),
    ("fb456", 200, {"permalink_url": "/page/videos/fb456"}),
]


def sunday_schedule(**more):
    return {"id": "s1", "name": "Sunday Service", "enabled": True, "weekdays": [6], "time": "08:00",
            "lead_days": 1, "create_time": "09:00", "title": "Sunday Service - {date}",
            "description": "Join us on {weekday}.", "date_format": "long", "destinations": ["yt", "fb"],
            "overrides": {}, **more}


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.store = Store(os.path.join(self.dir.name, "config.json"))
        self.store.destinations.extend([
            {"id": "yt", "kind": "youtube", "name": "Our channel", "account_id": "UC1", "client_id": "cid",
             "options": {"privacy": "unlisted", "stream_id": "key1"}},
            {"id": "fb", "kind": "facebook", "name": "Our Page", "account_id": "999", "options": {}}])
        self.store.schedules.append(sunday_schedule())
        self.vault = MemoryVault()
        self.vault.set("yt", "client_secret", "SECRET-CLIENT")
        self.vault.set("yt", "refresh_token", "SECRET-REFRESH")
        self.vault.set("fb", "page_token", "SECRET-PAGE")
        self.net = FakeNet(OK_ROUTES)
        enabled = engine.ENABLED   # the Facebook code is kept and tested, though the app has it switched off
        engine.ENABLED = {"youtube", "facebook", "wix"}
        self.addCleanup(setattr, engine, "ENABLED", enabled)
        real = net.send
        net.send = self.net
        self.addCleanup(setattr, net, "send", real)


class TitlesTest(unittest.TestCase):
    def test_the_users_example(self):
        when = datetime(2027, 11, 15, 8, 0)
        self.assertEqual(titles.render("Service - {date}", when), "Service - November 15, 2027")
        self.assertEqual(titles.render("{weekday} {month} {day} {year} {time}", when), "Monday November 15 2027 8:00 AM")
        self.assertEqual(titles.render("{date}", when, "iso"), "2027-11-15")
        self.assertEqual(titles.render("{date}", when, "eu"), "15/11/2027")
        self.assertEqual(titles.render("{time}", datetime(2027, 1, 1, 18, 5), clock="24"), "18:05")
        self.assertEqual(titles.render("{time}", datetime(2027, 1, 1, 0, 5)), "12:05 AM")

    def test_unknown_names_stay(self):
        self.assertEqual(titles.render("{Date} {speaker} {}", datetime(2027, 1, 3)), "January 3, 2027 {speaker} {}")

    def test_problems(self):
        self.assertEqual(titles.problems("Fine", "Also fine"), [])
        self.assertEqual(len(titles.problems("x" * 101)), 1)
        self.assertEqual(len(titles.problems("a <b>")), 1)
        self.assertEqual(len(titles.problems("  ")), 1)


class RecurrenceTest(unittest.TestCase):
    def test_every_sunday_created_on_saturday(self):
        s = sunday_schedule()
        found = recurrence.occurrences(s, datetime(2027, 11, 8, 12, 0), datetime(2027, 11, 30))
        self.assertEqual(found, [datetime(2027, 11, 14, 8), datetime(2027, 11, 21, 8), datetime(2027, 11, 28, 8)])
        self.assertEqual(recurrence.create_at(s, found[0]), datetime(2027, 11, 13, 9, 0))
        self.assertEqual(recurrence.create_at(s, found[0]).weekday(), 5)

    def test_the_same_day_counts_only_before_the_time(self):
        s = sunday_schedule()
        self.assertEqual(len(recurrence.occurrences(s, datetime(2027, 11, 14, 7, 59), datetime(2027, 11, 14, 23))), 1)
        self.assertEqual(len(recurrence.occurrences(s, datetime(2027, 11, 14, 8, 0), datetime(2027, 11, 14, 23))), 0)

    def test_lead_is_kept_within_facebooks_week(self):
        self.assertEqual(recurrence.create_at(sunday_schedule(lead_days=30), datetime(2027, 11, 14, 8)).day, 8)

    def test_describe(self):
        self.assertEqual(recurrence.describe(sunday_schedule()),
                         "Every Sunday at 8:00 AM · created 1 day before at 9:00 AM")
        self.assertIn("Wednesday and Sunday", recurrence.describe(sunday_schedule(weekdays=[2, 6])))

    def test_to_utc_is_the_same_moment(self):
        local = datetime(2027, 11, 14, 8, 0)
        self.assertEqual(recurrence.to_utc(local).timestamp(), local.timestamp())
        self.assertEqual(recurrence.to_utc(local).tzinfo, timezone.utc)


class EngineTest(Base):
    def test_nothing_before_saturday_morning(self):
        self.assertEqual(engine.run_due(self.store, self.vault, datetime(2027, 11, 13, 8, 59)), [])
        self.assertEqual(self.net.calls, [])

    def test_saturday_creates_both_once(self):
        now = datetime(2027, 11, 13, 9, 0)
        done = engine.run_due(self.store, self.vault, now)
        self.assertEqual([(e["kind"], e["status"], e["title"]) for e in done], [
            ("youtube", "created", "Sunday Service - November 14, 2027"),
            ("facebook", "created", "Sunday Service - November 14, 2027")])
        self.assertEqual(done[0]["url"], "https://www.youtube.com/watch?v=yt123")
        self.assertEqual(done[1]["url"], "https://www.facebook.com/page/videos/fb456")
        calls = len(self.net.calls)
        self.assertEqual(engine.run_due(self.store, self.vault, datetime(2027, 11, 13, 9, 1)), [])
        self.assertEqual(engine.run_due(Store(self.store.path), self.vault, datetime(2027, 11, 13, 23, 0)), [])
        self.assertEqual(len(self.net.calls), calls)  # also after the app starts again: no second stream

    def test_what_the_platforms_are_sent(self):
        engine.run_due(self.store, self.vault, datetime(2027, 11, 13, 9, 0))
        by = lambda part: next(c for c in self.net.calls if part in c["url"])
        start = recurrence.to_utc(datetime(2027, 11, 14, 8, 0))
        insert = by("liveBroadcasts?")
        body = json.loads(insert["data"])
        self.assertEqual(body["snippet"], {"title": "Sunday Service - November 14, 2027",
                                           "description": "Join us on Sunday.",
                                           "scheduledStartTime": start.strftime("%Y-%m-%dT%H:%M:%SZ")})
        self.assertEqual(body["status"], {"privacyStatus": "unlisted", "selfDeclaredMadeForKids": False})
        self.assertEqual(insert["headers"]["Authorization"], "Bearer ya29.access")
        self.assertIn("streamId=key1", by("liveBroadcasts/bind")["url"])
        live = by("/999/live_videos")
        form = dict(urllib.parse.parse_qsl(live["data"].decode()))
        self.assertEqual(form["status"], "UNPUBLISHED")
        self.assertEqual(form["description"], "Join us on Sunday.")
        self.assertEqual(json.loads(form["event_params"]), {"start_time": int(start.timestamp())})
        self.assertEqual(live["headers"]["Authorization"], "Bearer SECRET-PAGE")

    def test_no_secret_in_an_address_or_in_the_file(self):
        engine.run_due(self.store, self.vault, datetime(2027, 11, 13, 9, 0))
        for call in self.net.calls:
            self.assertNotIn("SECRET", call["url"])
            self.assertNotIn("ya29", call["url"])
        with open(self.store.path, encoding="utf-8") as fh:
            saved = fh.read()
        self.assertNotIn("SECRET", saved)
        self.assertNotIn("ya29", saved)

    def test_catches_up_when_the_app_was_closed(self):
        done = engine.run_due(self.store, self.vault, datetime(2027, 11, 14, 7, 0))  # Sunday, an hour before
        self.assertEqual([e["status"] for e in done], ["created", "created"])

    def test_too_late_is_left_alone(self):
        self.assertEqual(engine.run_due(self.store, self.vault, datetime(2027, 11, 14, 7, 55)), [])

    def test_one_fails_the_other_goes_on_and_is_retried_later(self):
        self.net.routes = [("/live_videos", 400, {"error": {"message": "(#200) Permissions error", "code": 200}})] \
            + OK_ROUTES
        done = engine.run_due(self.store, self.vault, datetime(2027, 11, 13, 9, 0))
        self.assertEqual([e["status"] for e in done], ["created", "failed"])
        self.assertIn("Permissions error", done[1]["note"])
        self.assertEqual(engine.run_due(self.store, self.vault, datetime(2027, 11, 13, 9, 5)), [])
        self.net.routes = OK_ROUTES
        again = engine.run_due(self.store, self.vault, datetime(2027, 11, 13, 9, 16))
        self.assertEqual([(e["kind"], e["status"], e["attempts"]) for e in again], [("facebook", "created", 2)])
        self.assertEqual(len(self.store.history), 2)

    def test_override_and_skip(self):
        s = self.store.schedules[0]
        s["overrides"]["2027-11-14"] = {"title": "Harvest Festival ({date})", "description": ""}
        s["overrides"]["2027-11-21"] = {"skip": True}
        items = engine.upcoming(self.store, datetime(2027, 11, 13, 9, 0))
        self.assertEqual((items[0]["title"], items[0]["description"], items[0]["overridden"]),
                         ("Harvest Festival (November 14, 2027)", "", True))
        self.assertTrue(items[1]["skipped"])
        self.assertEqual((items[2]["title"], items[2]["overridden"]), ("Sunday Service - November 28, 2027", False))
        self.assertEqual(engine.run_due(self.store, self.vault, datetime(2027, 11, 20, 12, 0)), [])

    def test_chosen_destinations_only_and_disabled(self):
        self.store.schedules[0]["destinations"] = ["fb", "gone"]
        done = engine.run_due(self.store, self.vault, datetime(2027, 11, 13, 9, 0))
        self.assertEqual([e["kind"] for e in done], ["facebook"])
        self.store.schedules[0]["enabled"] = False
        self.assertEqual(engine.upcoming(self.store, datetime(2027, 11, 15)), [])

    def test_schedule_now_respects_facebooks_week(self):
        item = engine.upcoming(self.store, datetime(2027, 11, 1, 12, 0))[1]  # Sunday the 14th, 13 days ahead
        done = engine.create_now(self.store, self.vault, item, datetime(2027, 11, 1, 12, 0))
        self.assertEqual([e["status"] for e in done], ["created", "failed"])
        self.assertIn("7 days", done[1]["note"])

    def test_missing_secret_and_revoked_sign_in(self):
        self.vault.forget("fb", "facebook")
        self.net.routes = [("oauth2.googleapis.com/token", 400, {"error": "invalid_grant",
                                                                 "error_description": "Token has been expired"})]
        done = engine.run_due(self.store, self.vault, datetime(2027, 11, 13, 9, 0))
        self.assertIn("connect it again", done[0]["note"])
        self.assertIn("7 days", done[0]["note"])
        self.assertIn("missing from the keychain", done[1]["note"])

    def test_facebook_event_link_and_description_is_never_empty(self):
        self.net.routes = [("/live_videos", 200, {"id": "fb456", "event_id": "777"})] + OK_ROUTES
        self.store.schedules[0].update(destinations=["fb"], description="")
        done = engine.run_due(self.store, self.vault, datetime(2027, 11, 13, 9, 0))
        self.assertEqual(done[0]["url"], "https://www.facebook.com/events/777")
        form = dict(urllib.parse.parse_qsl(self.net.calls[0]["data"].decode()))
        self.assertEqual(form["description"], "Sunday Service - November 14, 2027")

    def test_facebook_persistent_key(self):
        self.store.destination("fb")["options"] = {"persistent_key": True}
        self.store.schedules[0]["destinations"] = ["fb"]
        done = engine.run_due(self.store, self.vault, datetime(2027, 11, 13, 9, 0))
        call = next(c for c in self.net.calls if c["url"].endswith("/fb456") and c["method"] == "POST")
        self.assertEqual(call["data"], b"persistent_stream_key_status=ENABLE")
        self.assertEqual((done[0]["status"], done[0]["note"]), ("created", ""))

    def test_facebook_persistent_key_refused_still_creates(self):
        self.store.destination("fb")["options"] = {"persistent_key": True}
        self.store.schedules[0]["destinations"] = ["fb"]
        real = self.net

        def refuse(method, url, headers, data, timeout):
            if method == "POST" and url.endswith("/fb456"):
                return 400, b'{"error": {"message": "(#100) Invalid parameter"}}'
            return real(method, url, headers, data, timeout)
        net.send = refuse
        done = engine.run_due(self.store, self.vault, datetime(2027, 11, 13, 9, 0))
        self.assertEqual(done[0]["status"], "created")
        self.assertIn("did not switch on the persistent stream key", done[0]["note"])

    def test_youtube_live_not_enabled(self):
        self.net.routes = [("liveBroadcasts", 403, {"error": {"message": "x", "errors": [
            {"reason": "liveStreamingNotEnabled"}]}})] + OK_ROUTES
        done = engine.run_due(self.store, self.vault, datetime(2027, 11, 13, 9, 0))
        self.assertIn("youtube.com/features", done[0]["note"])


class WixTest(Base):
    def setUp(self):
        super().setUp()
        self.store.destinations.append(
            {"id": "wx", "kind": "wix", "name": "Website", "account_id": "SITE-1",
             "options": {"collection": "Livestream", "item_id": "item-9", "url_field": "videoUrl",
                         "title_field": "title", "publish": False, "page_url": "https://example.org/live"}})
        self.vault.set("wx", "api_key", "SECRET-WIX")
        self.store.schedules[0]["destinations"] = ["wx", "yt"]   # the website is listed first on purpose
        self.net.routes = [
            ("site-publisher", 200, {}),
            ("wix-data/v2/items/item-9", 200, {"dataItem": {"id": "item-9", "data": {
                "_id": "item-9", "title": "Old", "videoUrl": "https://old", "notes": "keep me"}}})] + OK_ROUTES

    def test_the_website_gets_the_youtube_link_after_youtube(self):
        done = engine.run_due(self.store, self.vault, datetime(2027, 11, 13, 9, 0))
        self.assertEqual([(e["kind"], e["status"]) for e in done], [("youtube", "created"), ("wix", "created")])
        self.assertEqual(done[1]["url"], "https://example.org/live")
        put = next(c for c in self.net.calls if c["method"] == "PUT")
        self.assertEqual((put["headers"]["Authorization"], put["headers"]["wix-site-id"]), ("SECRET-WIX", "SITE-1"))
        self.assertEqual(json.loads(put["data"]), {"dataCollectionId": "Livestream", "dataItem": {
            "id": "item-9", "data": {"_id": "item-9", "title": "Sunday Service - November 14, 2027",
                                     "videoUrl": "https://www.youtube.com/watch?v=yt123", "notes": "keep me"}}})
        self.assertFalse(any("site-publisher" in c["url"] for c in self.net.calls))
        self.assertEqual(engine.run_due(self.store, self.vault, datetime(2027, 11, 13, 9, 30)), [])

    def test_waits_when_youtube_failed_and_follows_when_it_works(self):
        ok = self.net.routes
        self.net.routes = [("liveBroadcasts", 500, {"error": {"message": "Backend error"}})] + ok
        done = engine.run_due(self.store, self.vault, datetime(2027, 11, 13, 9, 0))
        self.assertEqual([(e["kind"], e["status"]) for e in done], [("youtube", "failed"), ("wix", "failed")])
        self.assertIn("Waiting for this schedule's YouTube stream", done[1]["note"])
        self.assertFalse(any(c["method"] == "PUT" for c in self.net.calls))
        self.net.routes = ok
        again = engine.run_due(self.store, self.vault, datetime(2027, 11, 13, 9, 20))
        self.assertEqual([(e["kind"], e["status"]) for e in again], [("youtube", "created"), ("wix", "created")])

    def test_publish_when_asked_and_a_refused_publish_is_only_a_note(self):
        self.store.destination("wx")["options"]["publish"] = True
        done = engine.run_due(self.store, self.vault, datetime(2027, 11, 13, 9, 0))
        self.assertTrue(any("site-publisher/v1/site/publish" in c["url"] for c in self.net.calls))
        self.assertEqual((done[1]["status"], done[1]["note"]), ("created", ""))
        self.store.history.clear()
        self.net.routes = [("site-publisher", 403, {"message": "Permission denied"})] + self.net.routes
        done = engine.run_due(self.store, self.vault, datetime(2027, 11, 13, 9, 0))
        self.assertEqual(done[1]["status"], "created")
        self.assertIn("did not publish the site", done[1]["note"])

    def test_title_field_is_optional_and_a_bad_key_is_explained(self):
        self.store.destination("wx")["options"]["title_field"] = ""
        engine.run_due(self.store, self.vault, datetime(2027, 11, 13, 9, 0))
        put = next(c for c in self.net.calls if c["method"] == "PUT")
        self.assertEqual(json.loads(put["data"])["dataItem"]["data"]["title"], "Old")
        self.store.history.clear()
        self.net.routes = [("wix-data", 403, {"message": "Forbidden"})] + self.net.routes
        done = engine.run_due(self.store, self.vault, datetime(2027, 11, 13, 9, 0))
        self.assertIn("Wix refused the API key", done[1]["note"])
        self.assertNotIn("SECRET", done[1]["note"])

    def test_facebook_is_skipped_while_it_is_switched_off(self):
        engine.ENABLED = {"youtube", "wix"}
        self.store.schedules[0]["destinations"] = ["fb", "yt"]
        done = engine.run_due(self.store, self.vault, datetime(2027, 11, 13, 9, 0))
        self.assertEqual([e["kind"] for e in done], ["youtube"])

    def test_items_list(self):
        import wix
        self.net.routes = [("items/query", 200, {"dataItems": [{"id": "a", "data": {"_id": "a", "title": "Sunday"}}]})]
        self.assertEqual(wix.items("k", "s", "Livestream"), [{"id": "a", "data": {"_id": "a", "title": "Sunday"}}])
        self.assertEqual(json.loads(self.net.calls[0]["data"])["dataCollectionId"], "Livestream")


class PlatformTest(Base):
    def test_facebook_pages_keeps_the_exchange_out_of_sight(self):
        self.net.routes = [
            ("oauth/access_token", 200, {"access_token": "LONG"}),
            ("me/accounts", 200, {"data": [{"id": "1", "name": "A", "access_token": "PA"}, {"id": "2", "name": "B"}]})]
        self.assertEqual(facebook.pages("app", "sec", " short "), [{"id": "1", "name": "A", "token": "PA"}])
        self.assertIn("fb_exchange_token=short", self.net.calls[0]["url"])
        self.assertEqual(self.net.calls[1]["headers"]["Authorization"], "Bearer LONG")

    def test_youtube_streams_and_channel(self):
        self.net.routes = [
            ("liveStreams", 200, {"items": [{"id": "a", "snippet": {"title": "Default"},
                                             "contentDetails": {"isReusable": True}},
                                            {"id": "b", "snippet": {"title": "Once"},
                                             "contentDetails": {"isReusable": False}}]}),
            ("channels", 200, {"items": []})]
        self.assertEqual(youtube.streams("t"), [{"id": "a", "title": "Default"}])
        with self.assertRaises(net.ApiError):
            youtube.channel("t")

    def test_sign_in_round_trip(self):
        self.net.routes = [("oauth2.googleapis.com/token", 200, {"access_token": "A", "refresh_token": "R"})]
        signin = youtube.SignIn("cid", "csecret")
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(signin.start()).query))
        self.assertEqual((query["code_challenge_method"], query["access_type"]), ("S256", "offline"))
        self.assertTrue(query["redirect_uri"].startswith("http://127.0.0.1:"))
        result = {}
        thread = threading.Thread(target=lambda: result.update(signin.wait(10)))
        thread.start()
        with self.assertRaises(Exception):  # a wrong state is not an answer... it is refused below
            urllib.request.urlopen(query["redirect_uri"] + "/favicon.ico", timeout=5)
        urllib.request.urlopen(f"{query['redirect_uri']}/?state={query['state']}&code=THECODE", timeout=5).read()
        thread.join(10)
        self.assertEqual(result["refresh_token"], "R")
        form = dict(urllib.parse.parse_qsl(self.net.calls[0]["data"].decode()))
        self.assertEqual((form["code"], form["code_verifier"]), ("THECODE", signin.verifier))

    def test_sign_in_refuses_a_forged_state(self):
        signin = youtube.SignIn("cid", "csecret")
        redirect = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(signin.start()).query))["redirect_uri"]
        errors = []

        def wait():
            try:
                signin.wait(10)
            except net.ApiError as exc:
                errors.append(str(exc))
        thread = threading.Thread(target=wait)
        thread.start()
        urllib.request.urlopen(f"{redirect}/?state=forged&code=EVIL", timeout=5).read()
        thread.join(10)
        self.assertEqual(len(errors), 1)
        self.assertEqual(self.net.calls, [])  # the forged code was never sent to Google


class VaultTest(unittest.TestCase):
    def test_refuses_a_plain_text_or_missing_keychain(self):
        import keyring
        from keyring.backends import fail
        old = keyring.get_keyring()
        self.addCleanup(keyring.set_keyring, old)
        keyring.set_keyring(fail.Keyring())
        self.assertTrue(Vault().available())
        with self.assertRaises(VaultError):
            Vault().set("d", "page_token", "x")


if __name__ == "__main__":
    unittest.main()
