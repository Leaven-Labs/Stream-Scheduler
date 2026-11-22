"""Tests of the OBS connection (obs.py) against a small fake OBS on this computer, which speaks real
WebSocket and obs-websocket 5 over a real socket. Run: python -m unittest discover tests"""
import base64
import hashlib
import json
import os
import socket
import struct
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

import engine
import notify
import obs
import obslaunch
from store import Store
from vault import MemoryVault

import test_core as core

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class FakeObs:
    """One OBS on a free port of this computer. `password` None means no password is asked for.
    `mode`: "ok", "silent" (says nothing after the handshake, like OBS before 28), "http" (not OBS)."""

    def __init__(self, password="secret pw", mode="ok", stream=None):
        self.password, self.mode = password, mode
        self.stream = stream or {"streamServiceType": "rtmp_common",
                                 "streamServiceSettings": {"service": "YouTube - RTMPS",
                                                           "server": "rtmps://a.rtmps.youtube.com:443/live2",
                                                           "key": "abcd-1234"}}
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(5)
        self.port = self.server.getsockname()[1]
        self.requests = []
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def stop(self):
        self.server.close()

    def serve(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            try:
                self.talk(conn)
            except OSError:
                pass
            finally:
                conn.close()

    def talk(self, conn):
        conn.settimeout(5)
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = conn.recv(4096)
            if not chunk:
                return
            head += chunk
        if self.mode == "http":
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nhi")
            return
        lines = head.decode().split("\r\n")
        fields = {k.lower(): v.strip() for k, _, v in (l.partition(":") for l in lines[1:] if l)}
        accept = base64.b64encode(hashlib.sha1((fields["sec-websocket-key"] + GUID).encode()).digest()).decode()
        conn.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      f"Sec-WebSocket-Accept: {accept}\r\nSec-WebSocket-Protocol: obswebsocket.json\r\n\r\n").encode())
        if self.mode == "silent":
            conn.recv(4096)   # waits until the client gives up
            return
        hello = {"obsWebSocketVersion": "5.5.4", "rpcVersion": 1}
        if self.password is not None:
            hello["authentication"] = {"challenge": "c2hhbGxlbmdl", "salt": "c2FsdA=="}
        self.send(conn, {"op": 0, "d": hello})
        identify = self.receive(conn)
        if identify is None:   # the app gave up (no password to give) and closed
            return
        if self.password is not None and identify["d"].get("authentication") != self.expected():
            conn.sendall(bytes([0x88, 2]) + struct.pack(">H", 4009))
            return
        self.send(conn, {"op": 2, "d": {"negotiatedRpcVersion": 1}})
        answers = {"GetVersion": {"obsVersion": "31.0.2", "obsWebSocketVersion": "5.5.4"},
                   "GetProfileList": {"currentProfileName": "Sunday", "profiles": ["Sunday", "Youth"]},
                   "GetSceneCollectionList": {"currentSceneCollectionName": "Main",
                                              "sceneCollections": ["Main", "Christmas"]},
                   "GetStreamServiceSettings": self.stream}
        while True:
            try:
                message = self.receive(conn)
            except ConnectionError:
                return
            if message is None:
                return
            d = message["d"]
            self.requests.append(d["requestType"])
            self.send(conn, {"op": 5, "d": {"eventType": "Noise", "eventData": {}}})   # an event in between
            known = d["requestType"] in answers
            self.send(conn, {"op": 7, "d": {"requestType": d["requestType"], "requestId": d["requestId"],
                                            "requestStatus": {"result": known, "code": 100 if known else 204},
                                            "responseData": answers.get(d["requestType"], {})}})

    def expected(self):
        """obs-websocket 5's documented sign-in, worked out here on its own (not with obs.py)."""
        step = hashlib.sha256((self.password + "c2FsdA==").encode()).digest()
        return base64.b64encode(hashlib.sha256(base64.b64encode(step) + b"c2hhbGxlbmdl").digest()).decode()

    @staticmethod
    def send(conn, message):
        data = json.dumps(message).encode()
        if len(data) < 126:
            head = bytes([0x81, len(data)])
        else:
            head = bytes([0x81, 126]) + struct.pack(">H", len(data))
        conn.sendall(head + data)

    @staticmethod
    def receive(conn):
        def read(n):
            data = b""
            while len(data) < n:
                chunk = conn.recv(n - len(data))
                if not chunk:
                    raise ConnectionError
                data += chunk
            return data
        first, second = read(2)
        length = second & 0x7F
        if length == 126:
            length = struct.unpack(">H", read(2))[0]
        assert second & 0x80, "a client must mask"
        mask = read(4)
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(read(length)))
        if first & 0x0F == 0x8:
            return None
        return json.loads(payload)


class ObsTest(unittest.TestCase):
    def fake(self, **kw):
        f = FakeObs(**kw)
        self.addCleanup(f.stop)
        return f

    def test_info_with_password(self):
        f = self.fake()
        found = obs.info("127.0.0.1", f.port, "secret pw")
        self.assertEqual((found["version"], found["profile"], found["collection"]), ("31.0.2", "Sunday", "Main"))
        self.assertEqual(found["profiles"], ["Sunday", "Youth"])
        self.assertEqual(obs.describe(found), "OBS 31.0.2  ·  profile “Sunday”  ·  scene collection “Main”")

    def test_no_password_asked(self):
        f = self.fake(password=None)
        self.assertEqual(obs.info("127.0.0.1", f.port)["version"], "31.0.2")

    def test_wrong_and_missing_password(self):
        f = self.fake()
        with self.assertRaises(obs.ObsError) as wrong:
            obs.info("127.0.0.1", f.port, "nope")
        self.assertEqual(wrong.exception.reason, "password")
        self.assertIn("refused the password", str(wrong.exception))
        with self.assertRaises(obs.ObsError) as missing:
            obs.info("127.0.0.1", f.port, "")
        self.assertEqual(missing.exception.reason, "password")

    def test_obs_closed(self):
        free = socket.socket()
        free.bind(("127.0.0.1", 0))
        port = free.getsockname()[1]
        free.close()
        with self.assertRaises(obs.ObsError) as caught:
            obs.info("127.0.0.1", port, "x")
        self.assertEqual(caught.exception.reason, "closed")
        self.assertIn("OBS isn't open on this computer", str(caught.exception))

    def test_not_obs_and_old_obs(self):
        with self.assertRaises(obs.ObsError) as http:
            obs.info("127.0.0.1", self.fake(mode="http").port, "x")
        self.assertEqual(http.exception.reason, "not_obs")
        f = self.fake(mode="silent")
        with self.assertRaises(obs.ObsError) as old:
            obs.Connection("127.0.0.1", f.port, "x", timeout=0.5)
        self.assertEqual(old.exception.reason, "old")

    def test_stream_settings_and_unknown_request(self):
        f = self.fake()
        s = obs.stream_settings("127.0.0.1", f.port, "secret pw")
        self.assertEqual((s["type"], s["key"], s["service"]), ("rtmp_common", "abcd-1234", "YouTube - RTMPS"))
        with obs.connect("127.0.0.1", f.port, "secret pw") as c:
            with self.assertRaises(obs.ObsError) as caught:
                c.request("StartStream")   # the fake does not know it; the app never sends it anyway
        self.assertEqual(caught.exception.reason, "request")

    def test_address(self):
        self.assertEqual(obs.address("192.168.1.20"), ("192.168.1.20", 4455))
        self.assertEqual(obs.address(" ws://streaming-pc:4460/ "), ("streaming-pc", 4460))
        for bad in ("", "pc:port", "pc:70000", "my pc", "a/b"):
            with self.assertRaises(obs.ObsError, msg=bad):
                obs.address(bad)

    def test_local_settings_new_and_old_obs(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(obs.local_settings([folder]))
            with open(os.path.join(folder, "global.ini"), "w", encoding="utf-8") as fh:
                fh.write("[General]\nName=x\n\n[OBSWebSocket]\nServerEnabled=true\nServerPort=4456\n"
                         "AuthRequired=true\nServerPassword=old pw\n")
            self.assertEqual(obs.local_settings([folder]),
                             {"enabled": True, "port": 4456, "auth": True, "password": "old pw"})
            os.makedirs(os.path.join(folder, "plugin_config", "obs-websocket"))
            with open(os.path.join(folder, "plugin_config", "obs-websocket", "config.json"), "w") as fh:
                json.dump({"server_enabled": False, "server_port": 4455, "auth_required": True,
                           "server_password": "new pw"}, fh)
            self.assertEqual(obs.local_settings([folder]),
                             {"enabled": False, "port": 4455, "auth": True, "password": "new pw"})

    def test_encoders_are_saved_and_tested(self):
        f = self.fake()
        with tempfile.TemporaryDirectory() as folder:
            store, vault = Store(os.path.join(folder, "config.json")), MemoryVault()
            store.encoders.append({"id": "e1", "kind": "obs", "name": "P&W PC", "host": "127.0.0.1",
                                   "port": f.port, "local": False, "auth": True})
            vault.set("e1", "password", "secret pw")
            store.save()
            again = Store(store.path)
            self.assertEqual(again.encoder("e1")["name"], "P&W PC")
            self.assertIn("OBS 31.0.2", engine.test_encoder(vault, again.encoder("e1")))
            vault.forget("e1", "obs")
            self.assertEqual(vault.items, {})
        with tempfile.TemporaryDirectory() as folder:   # a settings file from before encoders
            path = os.path.join(folder, "config.json")
            with open(path, "w") as fh:
                json.dump({"destinations": [], "schedules": [], "history": []}, fh)
            self.assertEqual(Store(path).encoders, [])


SAT = datetime(2027, 11, 13, 9, 0)       # the Sunday stream of November 14, 8:00, is created now
KEYS = {"items": [{"id": "key1", "snippet": {"title": "Main sanctuary"}, "cdn": {"ingestionInfo": {"streamName": "abcd-1234"}}},
                  {"id": "key2", "snippet": {"title": "Backup"}, "cdn": {"ingestionInfo": {"streamName": "zzzz-9999"}}}]}
YT = [("GET liveBroadcasts", 200, {"items": [{"id": "yt123", "snippet": {}, "contentDetails": {"boundStreamId": "key1"}}]}),
      ("GET liveStreams", 200, KEYS)] + core.OK_ROUTES


def at(hour, minute):
    return datetime(2027, 11, 14, hour, minute)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class ObsBase(core.Base):
    def setUp(self):
        super().setUp()
        self.net.routes = YT
        self.store.schedules[0].update(destinations=["yt"], encoder_id="e1")
        self.encoder = {"id": "e1", "kind": "obs", "name": "P&W PC", "host": "127.0.0.1", "port": free_port(),
                        "local": False, "auth": True}
        self.store.encoders.append(self.encoder)
        self.vault.set("e1", "password", "secret pw")

    def obs_up(self, key="abcd-1234", service="YouTube - RTMPS"):
        f = FakeObs(stream={"streamServiceType": "rtmp_common",
                            "streamServiceSettings": {"service": service, "server": "auto", "key": key}})
        self.addCleanup(f.stop)
        self.encoder["port"] = f.port
        return f

    def item(self, now):
        return engine.upcoming(self.store, now)[0]


class ObsCheckTest(ObsBase):
    def test_rounds_come_once_each(self):
        due = lambda now: [(i["date"], r) for i, _, r in engine.obs_due(self.store, now)]
        self.assertEqual(due(at(7, 0)), [])
        self.assertEqual(due(at(7, 5)), [("2027-11-14", 0)])
        engine.obs_record(self.store, self.item(at(7, 5)), {"at": "x", "ok": True, "problems": [], "notes": []}, 0)
        self.assertEqual(due(at(7, 10)), [])
        self.assertEqual(due(at(7, 40)), [("2027-11-14", 1)])
        self.assertEqual(due(at(8, 0)), [])                     # it has started: no more checks
        self.store.data["obs"] = {}
        self.assertEqual(due(at(7, 45)), [("2027-11-14", 1)])   # the computer woke late: only the latest round
        self.store.schedules[0]["obs_checks"] = [90]
        self.assertEqual(due(at(6, 35)), [("2027-11-14", 0)])
        self.store.schedules[0].pop("encoder_id")
        self.assertEqual(due(at(7, 45)), [])

    def test_key_matches(self):
        self.obs_up()
        engine.run_due(self.store, self.vault, SAT)
        result = engine.obs_check(self.store, self.vault, self.item(at(7, 5)), self.encoder, at(7, 5))
        self.assertEqual((result["ok"], result["problems"], result["notes"]), (True, [], []))
        self.assertEqual(engine.obs_summary(result), "Ready.")

    def test_wrong_key_is_named_and_never_shown(self):
        self.obs_up(key="zzzz-9999")
        engine.run_due(self.store, self.vault, SAT)
        result = engine.obs_check(self.store, self.vault, self.item(at(7, 5)), self.encoder, at(7, 5))
        self.assertEqual([p["code"] for p in result["problems"]], ["key"])
        text = result["problems"][0]["text"]
        self.assertIn("“Backup”", text)
        self.assertIn("“Main sanctuary”", text)
        self.assertNotIn("zzzz", json.dumps(result) + json.dumps(self.store.data))
        self.assertNotIn("abcd", json.dumps(result) + json.dumps(self.store.data))
        self.obs_up(key="other-key")
        result = engine.obs_check(self.store, self.vault, self.item(at(7, 5)), self.encoder, at(7, 5))
        self.assertIn("a stream key that is not on this channel", result["problems"][0]["text"])
        self.obs_up(key="other-key", service="Twitch")
        result = engine.obs_check(self.store, self.vault, self.item(at(7, 5)), self.encoder, at(7, 5))
        self.assertIn("a service other than YouTube", result["problems"][0]["text"])

    def test_obs_signed_in_to_youtube_and_no_broadcast_yet(self):
        self.obs_up(key="")
        result = engine.obs_check(self.store, self.vault, self.item(at(7, 5)), self.encoder, at(7, 5))
        self.assertTrue(result["ok"])
        self.assertIn("once the YouTube stream exists", result["notes"][0])
        engine.run_due(self.store, self.vault, SAT)
        result = engine.obs_check(self.store, self.vault, self.item(at(7, 5)), self.encoder, at(7, 5))
        self.assertTrue(result["ok"])
        self.assertIn("Connect account", result["notes"][0])

    def test_obs_closed_and_wrong_password(self):
        result = engine.obs_check(self.store, self.vault, self.item(at(7, 5)), self.encoder, at(7, 5))
        self.assertEqual([p["code"] for p in result["problems"]], ["closed"])
        self.assertIn("OBS isn't open on P&W PC", result["problems"][0]["text"])
        self.obs_up()
        self.vault.set("e1", "password", "wrong")
        result = engine.obs_check(self.store, self.vault, self.item(at(7, 5)), self.encoder, at(7, 5))
        self.assertEqual([p["code"] for p in result["problems"]], ["password"])

    def test_check_now_records_without_alerts(self):
        self.obs_up()
        done = engine.obs_check_now(self.store, self.vault, at(6, 0))
        self.assertEqual(len(done), 1)
        saved = Store(self.store.path).data["obs"]["s1|2027-11-14"]
        self.assertEqual((saved["ok"], saved["round"]), (True, -1))   # the automatic rounds still come
        self.assertEqual(engine.obs_check_now(self.store, self.vault, at(4, 0)), [])   # more than 3 hours ahead


class ObsAlertTest(ObsBase):
    def setUp(self):
        super().setUp()
        cfg = notify.settings(self.store)
        cfg["channels"] = {"discord": {"on": True}}
        cfg["last_health"] = at(7, 0).strftime("%Y-%m-%dT%H:%M:%S")
        self.vault.set(notify.NOTIFY, "discord_url", "https://discord.com/api/webhooks/1/SECRET-D")
        self.net.routes = [("discord.com", 204, {})] + YT
        engine.run_due(self.store, self.vault, SAT)

    def told(self):
        return [json.loads(c["data"])["content"] for c in self.net.calls if "discord.com" in c["url"]]

    def test_not_ready_then_ready(self):
        notify.after(self.store, self.vault, [], at(7, 5))
        self.assertEqual(len(self.told()), 1)
        self.assertIn("OBS is not ready", self.told()[0])
        self.assertIn("starts in 55 minutes", self.told()[0])
        self.assertIn("OBS isn't open on P&W PC", self.told()[0])
        notify.after(self.store, self.vault, [], at(7, 10))
        self.assertEqual(len(self.told()), 1)                   # nothing more until the next round
        self.obs_up()
        notify.after(self.store, self.vault, [], at(7, 40))
        self.assertEqual(len(self.told()), 2)
        self.assertIn("OBS is ready now", self.told()[1])
        notify.after(self.store, self.vault, [], at(7, 50))
        self.assertEqual(len(self.told()), 2)

    def test_still_not_ready(self):
        notify.after(self.store, self.vault, [], at(7, 5))
        notify.after(self.store, self.vault, [], at(7, 40))
        self.assertEqual(len(self.told()), 2)
        self.assertIn("OBS is still not ready", self.told()[1])

    def test_ready_is_silent_and_the_alert_can_be_switched_off(self):
        self.obs_up()
        notify.after(self.store, self.vault, [], at(7, 5))
        self.assertEqual(self.told(), [])
        self.encoder["port"] = free_port()
        notify.settings(self.store)["events"]["obs"] = False
        notify.after(self.store, self.vault, [], at(7, 40))
        self.assertEqual(self.told(), [])
        self.assertFalse(self.store.data["obs"]["s1|2027-11-14"]["ok"])   # still shown in the app


class ObsLaunchTest(unittest.TestCase):
    def test_finds_obs_on_windows(self):
        env = {"ProgramFiles": r"D:\Apps"}
        there = {os.path.join(r"D:\Apps", "obs-studio", obslaunch.WINDOWS_EXE)}
        self.assertEqual(obslaunch.find(exists=there.__contains__, platform="win32", env=env, registry=""),
                         os.path.join(r"D:\Apps", "obs-studio", obslaunch.WINDOWS_EXE))
        from_registry = os.path.join(r"E:\OBS", obslaunch.WINDOWS_EXE)
        self.assertEqual(obslaunch.find(exists=lambda p: True, platform="win32", env=env, registry=r"E:\OBS"),
                         from_registry)
        self.assertEqual(obslaunch.find(exists=lambda p: False, platform="win32", env=env, registry=""), "")
        self.assertEqual(obslaunch.find("C:/mine/obs64.exe", exists=lambda p: True), "C:/mine/obs64.exe")
        self.assertEqual(obslaunch.find("C:/gone/obs64.exe", exists=lambda p: False), "")

    def test_command_never_goes_live(self):
        argv, folder = obslaunch.command("/opt/obs/bin/64bit/obs64.exe", "Sunday", "Main", platform="win32")
        self.assertEqual(argv, ["/opt/obs/bin/64bit/obs64.exe", "--disable-shutdown-check", "--profile", "Sunday",
                                "--collection", "Main"])
        self.assertEqual(folder, "/opt/obs/bin/64bit")   # OBS must start in its own folder
        self.assertEqual(obslaunch.command("/Applications/OBS.app", platform="darwin")[0],
                         ["open", "-a", "/Applications/OBS.app", "--args", "--disable-shutdown-check"])
        self.assertEqual(obslaunch.command("flatpak:com.obsproject.Studio", platform="linux")[0][:3],
                         ["flatpak", "run", "com.obsproject.Studio"])
        for platform in ("win32", "darwin", "linux"):
            self.assertNotIn("--startstreaming", obslaunch.command("obs", "p", "c", platform=platform)[0])


class ObsOpenTest(ObsBase):
    def setUp(self):
        super().setUp()
        self.encoder["local"] = True
        self.store.schedules[0].update(obs_profile="Sunday", obs_collection="Main")
        self.launched, self.is_running = [], False
        for name, fake in (("launch", lambda *a: self.launched.append(a)),
                           ("running", lambda: self.is_running),
                           ("find", lambda chosen="": chosen or "C:/obs/bin/64bit/obs64.exe")):
            real = getattr(obslaunch, name)
            setattr(obslaunch, name, fake)
            self.addCleanup(setattr, obslaunch, name, real)

    def test_opened_once_an_hour_before(self):
        self.assertEqual(engine.open_obs(self.store, self.vault, at(6, 55)), [])
        done = engine.open_obs(self.store, self.vault, at(7, 0))
        self.assertEqual(self.launched, [("C:/obs/bin/64bit/obs64.exe", "Sunday", "Main")])
        self.assertEqual(done[0]["result"], "opened")
        self.assertEqual(engine.open_obs(self.store, self.vault, at(7, 1)), [])   # never a second time
        self.assertEqual(len(self.launched), 1)
        # the check keeps what happened, and says it when OBS still does not answer
        result = engine.obs_check(self.store, self.vault, self.item(at(7, 5)), self.encoder, at(7, 5))
        record = engine.obs_record(self.store, self.item(at(7, 5)), result, 0, at(7, 5))
        self.assertEqual(record["opened"]["result"], "opened")
        self.assertIn("opened OBS at 7:00 AM, but it does not answer", result["problems"][0]["text"])

    def test_not_opened_when_running_off_or_elsewhere(self):
        self.is_running = True
        self.assertEqual(engine.open_obs(self.store, self.vault, at(7, 0))[0]["result"], "running")
        self.store.data["obs"] = {}
        self.is_running = False
        self.store.schedules[0]["obs_open"] = 0
        self.assertEqual(engine.open_obs(self.store, self.vault, at(7, 30)), [])
        self.store.schedules[0]["obs_open"] = 60
        self.encoder["local"] = False   # OBS on another computer is never opened from here
        self.assertEqual(engine.open_obs(self.store, self.vault, at(7, 30)), [])
        self.assertEqual(self.launched, [])

    def test_not_found_is_said(self):
        obslaunch.find = lambda chosen="": ""
        done = engine.open_obs(self.store, self.vault, at(7, 0))
        self.assertEqual(done[0]["result"], "failed")
        result = engine.obs_check(self.store, self.vault, self.item(at(7, 5)), self.encoder, at(7, 5))
        self.assertIn("OBS was not found on this computer", result["problems"][0]["text"])


if __name__ == "__main__":
    unittest.main()
