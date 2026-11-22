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

import engine
import obs
from store import Store
from vault import MemoryVault

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


if __name__ == "__main__":
    unittest.main()
