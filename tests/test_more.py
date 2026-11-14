"""Tests of series, the extra YouTube settings, cancelling, other websites, notifications, the update
check and backups. Run: python -m unittest discover tests"""
import json
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import engine
import net
import notify
import paths
import recurrence
import titles
import updates
import webhook
import wordpress
import youtube
from store import Store

import test_core as core

SAT = datetime(2027, 11, 13, 9, 0)   # the Sunday stream of November 14 is created now


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def calls(test, part, method=""):
    return [c for c in test.net.calls if part in c["url"] and method in ("", c["method"])]


class SeriesTest(unittest.TestCase):
    LENT = dict(core.sunday_schedule(), weekdays=[2], time="19:00", starts="2027-02-10", until="2027-03-24")

    def test_a_series_starts_and_ends(self):
        found = recurrence.occurrences(self.LENT, datetime(2027, 1, 1), datetime(2027, 12, 31))
        self.assertEqual((len(found), found[0], found[-1]),
                         (7, datetime(2027, 2, 10, 19, 0), datetime(2027, 3, 24, 19, 0)))
        self.assertFalse(recurrence.ended(self.LENT, datetime(2027, 3, 24, 18, 0)))
        self.assertTrue(recurrence.ended(self.LENT, datetime(2027, 3, 24, 19, 1)))
        self.assertFalse(recurrence.ended(core.sunday_schedule(), datetime(2030, 1, 1)))
        self.assertIn("from Feb 10, 2027 until Mar 24, 2027", recurrence.describe(self.LENT))

    def test_number_counts_from_the_first_date(self):
        self.assertEqual(recurrence.number(self.LENT, datetime(2027, 2, 10, 19, 0)), 1)
        self.assertEqual(recurrence.number(self.LENT, datetime(2027, 2, 24, 19, 0)), 3)
        self.assertIsNone(recurrence.number(core.sunday_schedule(), datetime(2027, 11, 14)))

    def test_series_note_and_number_in_a_title(self):
        when = datetime(2027, 2, 17, 19, 0)
        more = {"series": "Lent", "note": "", "number": 2}
        self.assertEqual(titles.render("{series}, week {number} ({nth}) {note}", when, more=more),
                         "Lent, week 2 (2nd) ")
        self.assertEqual(titles.render("{nth} of {number}", when), "{nth} of {number}")   # nothing to count from
        self.assertEqual([titles.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22)],
                         ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd"])


class YouTubeFieldsTest(core.Base):
    def setUp(self):
        super().setUp()
        self.store.schedules[0]["destinations"] = ["yt"]
        self.picture = os.path.join(self.dir.name, "thumb.png")
        with open(self.picture, "wb") as fh:
            fh.write(b"\x89PNG-not-really")
        self.net.routes = [("/videos?", 200, {}), ("playlistItems", 200, {}), ("thumbnails/set", 200, {})] + core.OK_ROUTES

    def test_latency_category_playlist_and_thumbnail(self):
        self.store.destinations[0]["options"].update(latency="low", category="29",
                                                     playlist="https://www.youtube.com/playlist?list=PLabc_1-2")
        self.store.schedules[0].update(thumbnail=self.picture, privacy="public", series="Advent",
                                       title="{series}: {date} {note}")
        done = engine.run_due(self.store, self.vault, SAT)
        self.assertEqual((done[0]["status"], done[0]["note"], done[0]["title"]),
                         ("created", "", "Advent: November 14, 2027"))
        made = json.loads(calls(self, "liveBroadcasts?", "POST")[0]["data"])
        self.assertEqual((made["contentDetails"]["latencyPreference"], made["status"]["privacyStatus"]),
                         ("low", "public"))   # the schedule's "public" wins over the channel's "unlisted"
        video = json.loads(calls(self, "/videos?", "PUT")[0]["data"])
        self.assertEqual(video, {"id": "yt123", "snippet": {"title": "Advent: November 14, 2027",
                                                            "description": "Join us on Sunday.", "categoryId": "29"}})
        listed = json.loads(calls(self, "playlistItems", "POST")[0]["data"])
        self.assertEqual(listed["snippet"], {"playlistId": "PLabc_1-2",
                                             "resourceId": {"kind": "youtube#video", "videoId": "yt123"}})
        thumb = calls(self, "upload/youtube/v3/thumbnails/set", "POST")[0]
        self.assertEqual((thumb["data"], thumb["headers"]["Content-Type"]), (b"\x89PNG-not-really", "image/png"))
        self.assertIn("videoId=yt123", thumb["url"])

    def test_nothing_extra_is_asked_when_nothing_extra_is_set(self):
        engine.run_due(self.store, self.vault, SAT)
        self.assertEqual([c for c in self.net.calls if any(p in c["url"] for p in
                                                           ("/videos?", "playlistItems", "thumbnails"))], [])
        self.assertNotIn("latencyPreference", calls(self, "liveBroadcasts?", "POST")[0]["data"].decode())

    def test_a_refused_extra_is_a_note_and_the_stream_still_exists(self):
        self.store.schedules[0].update(thumbnail=self.picture, playlist="PLx")
        self.net.routes = [("thumbnails/set", 403, {"error": {"message": "Forbidden"}}),
                           ("playlistItems", 404, {"error": {"message": "Playlist not found"}})] + core.OK_ROUTES
        done = engine.run_due(self.store, self.vault, SAT)
        self.assertEqual(done[0]["status"], "created")
        self.assertIn("youtube.com/verify", done[0]["note"])
        self.assertIn("Not added to the playlist", done[0]["note"])

    def test_a_thumbnail_that_is_gone_or_too_large(self):
        self.assertIn("JPG or PNG", youtube.thumbnail_problem("picture.gif"))
        self.assertIn("not there", youtube.thumbnail_problem(os.path.join(self.dir.name, "none.jpg")))
        with open(self.picture, "wb") as fh:
            fh.write(b"x" * (youtube.THUMBNAIL_LIMIT + 1))
        self.assertIn("2 MB", youtube.thumbnail_problem(self.picture))
        self.store.schedules[0]["thumbnail"] = self.picture
        done = engine.run_due(self.store, self.vault, SAT)
        self.assertEqual(done[0]["status"], "created")
        self.assertIn("2 MB", done[0]["note"])
        self.assertEqual(calls(self, "thumbnails"), [])

    def test_one_stream_can_have_its_own_thumbnail_and_note(self):
        self.store.schedules[0].update(title="Service {note}", overrides={"2027-11-14": {
            "note": "with baptism", "thumbnail": self.picture}})
        item = engine.find(self.store, "s1", "2027-11-14", SAT)
        self.assertEqual((item["title"], item["thumbnail"], item["overridden"]),
                         ("Service with baptism", self.picture, True))

    def test_playlist_links(self):
        self.assertEqual(youtube.playlist_id("https://youtube.com/playlist?list=PL9-x_Y&si=abc"), "PL9-x_Y")
        self.assertEqual(youtube.playlist_id(" PL9-x_Y "), "PL9-x_Y")
        self.assertEqual(youtube.playlist_id("not a link"), "")

    def test_cancel_deletes_on_youtube_and_skips_the_date(self):
        engine.run_due(self.store, self.vault, SAT)
        item = engine.find(self.store, "s1", "2027-11-14", SAT)
        self.assertEqual(engine.cancel(self.store, self.vault, item, SAT), [])
        deleted = calls(self, "liveBroadcasts", "DELETE")[0]
        self.assertIn("id=yt123", deleted["url"])
        self.assertEqual(self.store.history[0]["status"], "deleted")
        self.assertTrue(engine.find(self.store, "s1", "2027-11-14", SAT)["skipped"])
        self.assertEqual(engine.run_due(self.store, self.vault, SAT), [])
        del self.store.schedules[0]["overrides"]["2027-11-14"]   # "Restore": it is created again at once
        self.assertEqual(engine.run_due(self.store, self.vault, SAT)[0]["status"], "created")

    def test_a_cancel_that_youtube_refuses_changes_nothing(self):
        engine.run_due(self.store, self.vault, SAT)
        self.net.routes = [("DELETE liveBroadcasts", 403, {"error": {"message": "Forbidden"}})] + core.OK_ROUTES
        problems = engine.cancel(self.store, self.vault, engine.find(self.store, "s1", "2027-11-14", SAT), SAT)
        self.assertEqual(len(problems), 1)
        self.assertEqual(self.store.history[0]["status"], "created")
        self.assertFalse(engine.find(self.store, "s1", "2027-11-14", SAT)["skipped"])

    def test_preview_sends_nothing(self):
        self.store.schedules[0].update(playlist="PLx", title="A < B")
        streams = engine.preview(self.store, self.store.schedules[0], 2, SAT)
        self.assertEqual([s["when"] for s in streams], [datetime(2027, 11, 14, 8, 0), datetime(2027, 11, 21, 8, 0)])
        lines = dict(streams[0]["destinations"][0]["lines"])
        self.assertEqual((lines["Who can watch"], lines["Playlist"], lines["Stream key"]),
                         ("Unlisted", "PLx", "chosen in YouTube Studio"))
        self.assertIn("< and >", streams[0]["problems"][0])
        self.assertEqual(self.net.calls, [])


class WebsitesTest(core.Base):
    def setUp(self):
        super().setUp()
        self.store.destinations.extend([
            {"id": "wp", "kind": "wordpress", "name": "Our site", "account_id": "https://example.org/blog",
             "options": {"user": "editor", "pattern_id": 42, "pattern_title": "Livestream", "show_title": True,
                         "page_url": "https://example.org/live"}},
            {"id": "hook", "kind": "webhook", "name": "Zapier", "account_id": "", "options": {}}])
        self.vault.set("wp", "app_password", "abcd efgh")
        self.vault.set("hook", "url", "https://hooks.example.com/catch/SECRET-HOOK")
        self.store.schedules[0]["destinations"] = ["hook", "wp", "yt"]
        self.net.routes = [("hooks.example.com", 200, {}),
                           ("rest_route=/wp/v2/blocks/42", 200, {"id": 42, "content": {"raw": "old"}})] + core.OK_ROUTES

    def test_wordpress_and_the_webhook_follow_youtube(self):
        done = engine.run_due(self.store, self.vault, SAT)
        self.assertEqual([(e["kind"], e["status"]) for e in done],
                         [("youtube", "created"), ("webhook", "created"), ("wordpress", "created")])
        post = calls(self, "rest_route=/wp/v2/blocks/42", "POST")[0]
        self.assertTrue(post["url"].startswith("https://example.org/blog/?rest_route="))
        self.assertEqual(post["headers"]["Authorization"], net.basic("editor", "abcd efgh"))
        content = json.loads(post["data"])["content"]
        self.assertIn('"url":"https://www.youtube.com/watch?v=yt123"', content)
        self.assertIn("<h2 class=\"wp-block-heading\">Sunday Service - November 14, 2027</h2>", content)
        sent = json.loads(calls(self, "hooks.example.com")[0]["data"])
        self.assertEqual((sent["event"], sent["url"], sent["video_id"], sent["start_local"], sent["schedule"]),
                         ("stream.scheduled", "https://www.youtube.com/watch?v=yt123", "yt123", "2027-11-14T08:00",
                          "Sunday Service"))
        self.assertNotIn("SECRET-HOOK", read(self.store.path))

    def test_websites_wait_for_youtube_without_counting_as_a_failure_to_report(self):
        self.net.routes = [("liveBroadcasts", 500, {})] + self.net.routes
        done = engine.run_due(self.store, self.vault, SAT)
        self.assertEqual([bool(e.get("waiting")) for e in done], [False, True, True])

    def test_check_puts_back_a_pattern_someone_changed(self):
        engine.run_due(self.store, self.vault, SAT)
        self.assertEqual(engine.verify(self.store, self.vault, SAT), 1)   # the pattern holds "old"
        again = engine.run_due(self.store, self.vault, SAT)
        self.assertEqual([(e["kind"], e["status"]) for e in again], [("wordpress", "created")])

    def test_only_https_addresses(self):
        self.assertEqual(wordpress.site_address("example.org/blog/"), "https://example.org/blog")
        for bad in ("http://example.org", "", "ftp://x"):
            with self.assertRaises(net.ApiError):
                wordpress.site_address(bad)
        with self.assertRaises(net.ApiError):
            webhook.address("http://hooks.example.com/x")

    def test_a_site_that_is_not_wordpress_and_a_refused_password(self):
        self.net.routes = [("rest_route=/wp/v2/blocks", 200, {})]
        with self.assertRaisesRegex(net.ApiError, "did not answer like a WordPress"):
            wordpress.patterns("https://example.org", "u", "p")
        self.net.routes = [("rest_route", 401, {"code": "rest_forbidden", "message": "Sorry."})]
        with self.assertRaisesRegex(net.ApiError, "application password"):
            wordpress.patterns("https://example.org", "u", "p")

    def test_patterns_list_and_destination_test(self):
        self.net.routes = [("rest_route=/wp/v2/blocks/42", 200, {"id": 42, "content": {"raw": "x"}}),
                           ("rest_route=/wp/v2/blocks", 200, [{"id": 42, "title": {"raw": "Livestream"}}]),
                           ("hooks.example.com", 200, {})]
        self.assertEqual(wordpress.patterns("example.org", "u", "p"), [{"id": 42, "title": "Livestream"}])
        self.assertIn("Livestream", engine.test_destination(self.vault, self.store.destination("wp")))
        engine.test_destination(self.vault, self.store.destination("hook"))
        self.assertEqual(json.loads(calls(self, "hooks.example.com")[0]["data"])["event"], "test")


class NotifyTest(core.Base):
    def setUp(self):
        super().setUp()
        self.store.schedules[0]["destinations"] = ["yt"]
        cfg = notify.settings(self.store)
        cfg["channels"] = {"discord": {"on": True}, "slack": {"on": True}, "pushover": {"on": True},
                           "email": {"on": True, "host": "smtp.example.org", "port": 587, "security": "starttls",
                                     "user": "me@example.org", "to": "team@example.org"}}
        for name, value in (("discord_url", "https://discord.com/api/webhooks/1/SECRET-D"),
                            ("slack_url", "https://hooks.slack.com/services/SECRET-S"),
                            ("pushover_token", "SECRET-PT"), ("pushover_user", "SECRET-PU"),
                            ("email_password", "SECRET-MAIL")):
            self.vault.set(notify.NOTIFY, name, value)
        self.mails = []
        real = notify.deliver_mail
        notify.deliver_mail = lambda config, password, message: self.mails.append((password, message))
        self.addCleanup(setattr, notify, "deliver_mail", real)
        self.extra = [("discord.com", 204, {}), ("hooks.slack.com", 200, {}), ("api.pushover.net", 200, {"status": 1})]
        self.net.routes = self.extra + core.OK_ROUTES
        cfg["last_health"] = SAT.strftime("%Y-%m-%dT%H:%M:%S")   # not due in these tests unless said

    def sent(self, part):
        return calls(self, part)

    def test_a_failure_is_reported_once_on_every_channel(self):
        self.net.routes = self.extra + [("liveBroadcasts", 403, {"error": {"message": "Quota exceeded"}})] + core.OK_ROUTES
        notify.after(self.store, self.vault, engine.run_due(self.store, self.vault, SAT), SAT)
        self.assertIn("Quota exceeded", json.loads(self.sent("discord.com")[0]["data"])["content"])
        self.assertIn("Sunday Service - November 14, 2027", json.loads(self.sent("hooks.slack.com")[0]["data"])["text"])
        push = self.sent("api.pushover.net")[0]["data"].decode()
        self.assertIn("token=SECRET-PT", push)
        self.assertIn("priority=1", push)
        self.assertEqual(self.mails[0][0], "SECRET-MAIL")
        self.assertEqual((self.mails[0][1]["To"], self.mails[0][1]["Subject"]),
                         ("team@example.org", "A stream could not be scheduled"))
        later = datetime(2027, 11, 13, 9, 20)   # the retry fails again: nobody is told twice
        notify.after(self.store, self.vault, engine.run_due(self.store, self.vault, later), later)
        self.assertEqual((len(self.sent("discord.com")), len(self.mails)), (1, 1))
        self.net.routes = self.extra + core.OK_ROUTES   # it works; a later failure would be reported again
        done = engine.run_due(self.store, self.vault, datetime(2027, 11, 13, 9, 40))
        self.assertNotIn("told", done[0])

    def test_no_secret_of_a_channel_is_in_the_settings_file(self):
        notify.send(self.store, self.vault, "T", "text")
        self.store.save()
        saved = read(self.store.path)
        for secret in ("SECRET-D", "SECRET-S", "SECRET-PT", "SECRET-PU", "SECRET-MAIL"):
            self.assertNotIn(secret, saved)

    def test_created_is_only_told_when_asked(self):
        notify.after(self.store, self.vault, engine.run_due(self.store, self.vault, SAT), SAT)
        self.assertEqual(self.sent("discord.com"), [])
        notify.settings(self.store)["events"]["created"] = True
        self.store.history.clear()
        notify.after(self.store, self.vault, engine.run_due(self.store, self.vault, SAT), SAT)
        self.assertIn("watch?v=yt123", json.loads(self.sent("discord.com")[0]["data"])["content"])

    def test_one_channel_failing_does_not_stop_the_others(self):
        self.net.routes = [("discord.com", 404, {"message": "Unknown Webhook", "code": 10015})] + self.net.routes
        self.assertEqual(notify.send(self.store, self.vault, "T", "text"), 3)
        self.assertIn("Discord", notify.settings(self.store)["last_error"])
        notify.settings(self.store)["channels"]["discord"]["on"] = False
        self.assertEqual(notify.send(self.store, self.vault, "T", "text"), 3)
        self.assertEqual(notify.settings(self.store)["last_error"], "")

    def test_a_stream_that_was_never_created_is_reported_when_it_is_too_late(self):
        late = datetime(2027, 11, 14, 7, 55)   # the computer was off since Saturday
        self.assertEqual(engine.run_due(self.store, self.vault, late), [])
        notify.after(self.store, self.vault, [], late)
        notify.after(self.store, self.vault, [], datetime(2027, 11, 14, 7, 56))
        self.assertEqual(len(self.sent("discord.com")), 1)
        self.assertIn("YouTube Studio", json.loads(self.sent("discord.com")[0]["data"])["content"])

    def test_weekly_summary_once_at_its_time(self):
        cfg = notify.settings(self.store)
        cfg["events"]["summary"] = True
        cfg.update(summary_day=5, summary_time="18:00")
        engine.run_due(self.store, self.vault, SAT)
        notify.after(self.store, self.vault, [], datetime(2027, 11, 13, 17, 59))
        self.assertEqual(self.sent("discord.com"), [])
        notify.after(self.store, self.vault, [], datetime(2027, 11, 13, 18, 0))
        notify.after(self.store, self.vault, [], datetime(2027, 11, 13, 18, 1))
        text = json.loads(self.sent("discord.com")[0]["data"])["content"]
        self.assertEqual(len(self.sent("discord.com")), 1)
        self.assertIn("OK  Sun, Nov 14 at 8:00 AM  Sunday Service - November 14, 2027", text)
        self.assertIn("watch?v=yt123", text)
        self.assertNotIn("November 21", text)   # more than seven days away
        self.assertIn("will be created", notify.summary_text(self.store, datetime(2027, 11, 15, 10, 0)))
        cfg["last_summary"] = ""   # the app was closed for five days: no stale summary
        notify.after(self.store, self.vault, [], datetime(2027, 11, 18, 18, 0))
        self.assertEqual(len(self.sent("discord.com")), 1)

    def test_a_sign_in_that_stopped_working_is_found_and_reported_once(self):
        cfg = notify.settings(self.store)
        cfg["last_health"] = ""
        self.net.routes = self.extra + [("oauth2.googleapis.com/token", 400, {"error": "invalid_grant"})]
        notify.after(self.store, self.vault, [], SAT)
        self.assertIn("Reconnect", cfg["health"]["yt"])
        self.assertIn("Our channel", json.loads(self.sent("discord.com")[0]["data"])["content"])
        notify.check_health(self.store, self.vault, datetime(2027, 11, 14, 10, 0))
        self.assertEqual(len(self.sent("discord.com")), 1)
        self.net.routes = self.extra + [("channels", 200, {"items": [{"id": "UC1", "snippet": {"title": "C"}}]})] + core.OK_ROUTES
        notify.check_health(self.store, self.vault, datetime(2027, 11, 15, 11, 0))
        self.assertEqual(cfg["health"], {})

    def test_no_connection_says_nothing_about_a_sign_in(self):
        cfg = notify.settings(self.store)
        cfg["last_health"] = ""

        def offline(*a):
            raise net.ApiError("Could not connect")
        net.send = offline
        notify.check_health(self.store, self.vault, SAT)
        self.assertEqual((cfg["health"], cfg["last_health"]), ({}, ""))

    def test_forget_deletes_the_secrets(self):
        notify.forget(self.store, self.vault, "pushover")
        self.assertFalse(self.vault.has(notify.NOTIFY, "pushover_token"))
        self.assertNotIn("pushover", notify.active(self.store))


class UpdatesTest(core.Base):
    def setUp(self):
        super().setUp()
        version = paths.VERSION
        paths.VERSION = "0.0.4-alpha"
        self.addCleanup(setattr, paths, "VERSION", version)
        self.releases = [{"tag_name": "v0.0.4", "prerelease": True, "html_url": "https://example/4"},
                         {"tag_name": "v0.0.10", "prerelease": True, "html_url": "https://example/10"},
                         {"tag_name": "v0.0.11", "draft": True, "prerelease": True, "html_url": "x"}]
        self.net.routes = [("api.github.com", 200, self.releases)]

    def test_a_newer_release_is_found_once_a_day(self):
        now = datetime(2027, 11, 13, 9, 0)
        self.assertEqual(updates.check(self.store, now), {"version": "0.0.10", "url": "https://example/10"})
        updates.check(self.store, datetime(2027, 11, 13, 20, 0))
        self.assertEqual(len(self.net.calls), 1)
        updates.check(self.store, datetime(2027, 11, 14, 9, 1))
        self.assertEqual(len(self.net.calls), 2)
        self.assertNotIn("Authorization", self.net.calls[0]["headers"])

    def test_nothing_newer_switched_off_and_offline(self):
        self.releases[:] = self.releases[:1]
        self.assertIsNone(updates.check(self.store))
        self.store.settings["update_check"] = False
        self.store.data["update"] = {}
        updates.check(self.store)
        self.assertEqual(len(self.net.calls), 1)
        self.net.routes = []
        net.send = lambda *a: (_ for _ in ()).throw(net.ApiError("Could not connect"))
        self.store.settings["update_check"] = True
        self.assertIsNone(updates.check(self.store))

    def test_a_finished_version_ignores_pre_releases(self):
        paths.VERSION = "1.0.0"
        self.releases.append({"tag_name": "v1.1.0-beta", "prerelease": True, "html_url": "b"})
        self.assertIsNone(updates.check(self.store))
        self.assertEqual(updates.number("v1.2.3-alpha"), (1, 2, 3))


class BackupTest(core.Base):
    def test_backup_and_restore(self):
        path = os.path.join(self.dir.name, "backup.json")
        self.store.backup(path)
        self.assertNotIn("SECRET", read(path))
        other = Store(os.path.join(self.dir.name, "other.json"))
        other.restore(path)
        self.assertEqual((other.schedules, other.destinations), (self.store.schedules, self.store.destinations))
        self.assertEqual(Store(other.path).schedules[0]["name"], "Sunday Service")

    def test_a_file_that_is_not_a_backup_changes_nothing(self):
        for text in ("not json", "[]", '{"backup_of": "Stream Scheduler", "data": {"schedules": 5}}', '{"data": {}}'):
            path = os.path.join(self.dir.name, "bad.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            with self.assertRaises(ValueError):
                self.store.restore(path)
        self.assertEqual(len(self.store.schedules), 1)

    def test_a_reconnected_destination_keeps_its_id(self):
        self.vault.set("new", "client_secret", "S2")
        self.vault.set("new", "refresh_token", "R2")
        self.vault.move("youtube", "new", "yt")
        self.assertEqual((self.vault.get("yt", "refresh_token"), self.vault.has("new", "refresh_token")), ("R2", False))


if __name__ == "__main__":
    unittest.main()
