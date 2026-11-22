"""OBS Studio: a small client for its built-in remote control (obs-websocket 5, in OBS 28 and newer).

Standard library only. OBS speaks plain WebSocket (ws://, not encrypted) on the local network, so this
is a minimal WebSocket client: the opening handshake, masked text frames out, and frames in. On top of
it, obs-websocket's own steps: Hello, Identify (with the password hashed as OBS asks), Identified, then
requests and their answers.

The app only READS from OBS (its version, profiles, scene collections, stream settings). It never
starts or stops a stream, switches a scene or changes a setting. The stream key that OBS returns is a
secret: it is compared and forgotten, never shown, logged or saved.
"""
import base64
import configparser
import hashlib
import json
import os
import secrets
import socket
import struct
import sys

import net

DEFAULT_PORT = 4455
LOCAL = "127.0.0.1"
_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"   # fixed by the WebSocket standard (RFC 6455)


class ObsError(net.ApiError):
    """OBS could not be reached or said no. `reason` is a short code: "closed", "unreachable",
    "password", "old", "not_obs" or "request"."""


def address(text):
    """(host, port) from what the user typed: "192.168.1.20", "streaming-pc" or "192.168.1.20:4455".
    Raises ObsError for something that is not an address."""
    text = (text or "").strip()
    for prefix in ("ws://", "wss://"):
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
    text = text.rstrip("/")
    host, port = text, DEFAULT_PORT
    if text.count(":") == 1:
        host, _, number = text.partition(":")
        if not number.isdigit() or not 0 < int(number) < 65536:
            raise ObsError("The port after the colon must be a number, such as 4455.", reason="address")
        port = int(number)
    if not host or any(c.isspace() or c in "/\\@?#" for c in host):
        raise ObsError("Type the other computer's name or its address on the network, such as 192.168.1.20.",
                       reason="address")
    return host, port


def _where(host):
    return "this computer" if host in (LOCAL, "localhost", "::1") else host


# ---- the WebSocket part ---------------------------------------------------------------------

class _Socket:
    """One WebSocket connection: text messages in and out. Tests put their own class in this place."""

    def __init__(self, host, port, timeout):
        self.where = _where(host)
        try:
            self.sock = socket.create_connection((host, port), timeout=timeout)
        except ConnectionRefusedError:
            raise ObsError(f"OBS isn't open on {self.where}, or its WebSocket server is switched off "
                           "(in OBS: Tools → WebSocket Server Settings).", reason="closed") from None
        except socket.timeout:
            raise ObsError(f"{self.where} did not answer on port {port}. Is it switched on and on this "
                           "network? Its firewall may also be blocking OBS.", reason="unreachable") from None
        except OSError as exc:
            raise ObsError(f"{self.where} could not be reached ({exc.strerror or exc}).",
                           reason="unreachable") from None
        self.buffer = b""
        try:
            self._handshake(host, port)
        except BaseException:
            self.close()
            raise

    def _read(self, count):
        while len(self.buffer) < count:
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout:
                raise ObsError(f"OBS on {self.where} stopped answering.", reason="unreachable") from None
            except OSError as exc:
                raise ObsError(f"The connection to OBS on {self.where} was lost ({exc.strerror or exc}).",
                               reason="unreachable") from None
            if not chunk:
                raise ObsError(f"OBS on {self.where} closed the connection.", reason="closed")
            self.buffer += chunk
        data, self.buffer = self.buffer[:count], self.buffer[count:]
        return data

    def _handshake(self, host, port):
        key = base64.b64encode(secrets.token_bytes(16)).decode()
        host_header = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
        self.sock.sendall((f"GET / HTTP/1.1\r\nHost: {host_header}\r\nUpgrade: websocket\r\n"
                           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
                           "Sec-WebSocket-Protocol: obswebsocket.json\r\n\r\n").encode())
        not_obs = ObsError(f"Something other than OBS answered on {self.where}, port {port}.", reason="not_obs")
        head = b""
        while not head.endswith(b"\r\n\r\n"):   # byte by byte: what follows the head stays in the buffer
            if len(head) > 16384:
                raise not_obs
            head += self._read(1)
        lines = head.decode("latin-1").split("\r\n")
        if " 101 " not in lines[0] + " ":
            raise not_obs
        fields = {k.strip().lower(): v.strip() for k, _, v in (line.partition(":") for line in lines[1:] if line)}
        expected = base64.b64encode(hashlib.sha1((key + _GUID).encode()).digest()).decode()
        if fields.get("sec-websocket-accept") != expected:
            raise not_obs

    def send(self, text):
        payload = text.encode()
        head = bytes([0x81])   # a whole text message
        if len(payload) < 126:
            head += bytes([0x80 | len(payload)])
        elif len(payload) < 65536:
            head += bytes([0x80 | 126]) + struct.pack(">H", len(payload))
        else:
            head += bytes([0x80 | 127]) + struct.pack(">Q", len(payload))
        mask = secrets.token_bytes(4)   # a client must mask what it sends
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        try:
            self.sock.sendall(head + mask + masked)
        except OSError as exc:
            raise ObsError(f"The connection to OBS on {self.where} was lost ({exc.strerror or exc}).",
                           reason="unreachable") from None

    def _frame(self):
        first, second = self._read(2)
        fin, opcode = bool(first & 0x80), first & 0x0F
        length = second & 0x7F
        if length == 126:
            length = struct.unpack(">H", self._read(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self._read(8))[0]
        mask = self._read(4) if second & 0x80 else None
        payload = self._read(length)
        if mask:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return fin, opcode, payload

    def receive(self):
        """The next text message. Answers pings; turns OBS's closing codes into ObsError."""
        parts = []
        while True:
            fin, opcode, payload = self._frame()
            if opcode == 0x8:   # close
                code = struct.unpack(">H", payload[:2])[0] if len(payload) >= 2 else 0
                raise _closed(code, payload[2:].decode(errors="replace"), self.where)
            if opcode == 0x9:   # ping
                self._control(0xA, payload)
                continue
            if opcode == 0xA:   # pong
                continue
            parts.append(payload)
            if fin:
                return b"".join(parts).decode()

    def _control(self, opcode, payload):
        mask = secrets.token_bytes(4)
        try:
            self.sock.sendall(bytes([0x80 | opcode, 0x80 | len(payload)]) + mask
                              + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))
        except OSError:
            pass

    def close(self):
        try:
            self._control(0x8, struct.pack(">H", 1000))
            self.sock.close()
        except OSError:
            pass


def _closed(code, text, where):
    if code == 4009:
        return ObsError(f"OBS on {where} refused the password. Copy it again from OBS (Tools → WebSocket "
                        "Server Settings → Show Connect Info).", reason="password")
    if code == 4010:
        return ObsError(f"OBS on {where} is too old or too new for this app. Update OBS and Stream "
                        "Scheduler.", reason="old")
    return ObsError(f"OBS on {where} closed the connection{f' ({text})' if text else ''}.", reason="closed")


# ---- obs-websocket ----------------------------------------------------------------------------

def auth_string(password, salt, challenge):
    """obs-websocket 5's answer to its challenge: base64(sha256(base64(sha256(password + salt)) + challenge))."""
    secret = base64.b64encode(hashlib.sha256((password + salt).encode()).digest()).decode()
    return base64.b64encode(hashlib.sha256((secret + challenge).encode()).digest()).decode()


class Connection:
    """A signed-in connection to OBS. Use as `with obs.connect(host, port, password) as c: c.request(...)`."""

    socket_class = _Socket   # tests put a fake OBS here

    def __init__(self, host, port=DEFAULT_PORT, password="", timeout=5):
        self.where = _where(host)
        self.ws = self.socket_class(host, port, timeout)
        self.count = 0
        try:
            self._identify(password)
        except BaseException:
            self.ws.close()
            raise

    def _message(self):
        try:
            message = json.loads(self.ws.receive())
        except ValueError:
            raise ObsError(f"OBS on {self.where} sent something this app does not understand.",
                           reason="not_obs") from None
        if not isinstance(message, dict) or "op" not in message:
            raise ObsError(f"OBS on {self.where} sent something this app does not understand.", reason="not_obs")
        return message

    def _identify(self, password):
        try:
            hello = self._message()
        except ObsError as exc:
            if exc.reason == "unreachable":   # nothing came: obs-websocket 4 (before OBS 28) says nothing first
                raise ObsError(f"OBS on {self.where} did not greet this app. It needs OBS 28 or newer.",
                               reason="old") from None
            raise
        if hello.get("op") != 0:
            raise ObsError(f"OBS on {self.where} sent something this app does not understand.", reason="not_obs")
        data = hello.get("d") or {}
        identify = {"rpcVersion": 1, "eventSubscriptions": 0}
        challenge = data.get("authentication")
        if challenge:
            if not password:
                raise ObsError(f"OBS on {self.where} asks for a password. Copy it from OBS (Tools → WebSocket "
                               "Server Settings → Show Connect Info).", reason="password")
            identify["authentication"] = auth_string(password, challenge["salt"], challenge["challenge"])
        self.ws.send(json.dumps({"op": 1, "d": identify}))
        while True:
            message = self._message()
            if message["op"] == 2:
                return

    def request(self, kind, data=None):
        """Ask OBS for one thing; its responseData (a dict)."""
        self.count += 1
        rid = f"ss-{self.count}"
        body = {"requestType": kind, "requestId": rid}
        if data:
            body["requestData"] = data
        self.ws.send(json.dumps({"op": 6, "d": body}))
        while True:
            message = self._message()
            d = message.get("d") or {}
            if message["op"] == 7 and d.get("requestId") == rid:
                status = d.get("requestStatus") or {}
                if not status.get("result"):
                    raise ObsError(f"OBS on {self.where} could not answer {kind}"
                                   f"{': ' + status['comment'] if status.get('comment') else ''}.", reason="request")
                return d.get("responseData") or {}

    def close(self):
        self.ws.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def connect(host, port=DEFAULT_PORT, password="", timeout=5):
    return Connection(host, port, password, timeout)


def info(host, port=DEFAULT_PORT, password=""):
    """What the guide and the Test button show: {"version", "profile", "profiles", "collection", "collections"}."""
    with connect(host, port, password) as c:
        version = c.request("GetVersion")
        profiles = c.request("GetProfileList")
        collections = c.request("GetSceneCollectionList")
    return {"version": version.get("obsVersion", ""), "profile": profiles.get("currentProfileName", ""),
            "profiles": list(profiles.get("profiles") or []),
            "collection": collections.get("currentSceneCollectionName", ""),
            "collections": list(collections.get("sceneCollections") or [])}


def stream_settings(host, port=DEFAULT_PORT, password=""):
    """Where OBS streams to: {"type", "server", "key", "service"}. The key is a secret: compare it and drop it."""
    with connect(host, port, password) as c:
        answer = c.request("GetStreamServiceSettings")
    s = answer.get("streamServiceSettings") or {}
    return {"type": answer.get("streamServiceType", ""), "server": s.get("server", ""), "key": s.get("key", ""),
            "service": s.get("service", "")}


def describe(found):
    """One line about a connected OBS, for the guide and the Destinations page."""
    words = [f"OBS {found['version']}" if found.get("version") else "OBS"]
    if found.get("profile"):
        words.append(f"profile “{found['profile']}”")
    if found.get("collection"):
        words.append(f"scene collection “{found['collection']}”")
    return "  ·  ".join(words)


# ---- OBS's own settings on this computer ----------------------------------------------------

def config_dirs():
    """Where OBS keeps its settings on this computer, most likely first."""
    if sys.platform == "win32":
        return [os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "obs-studio")]
    if sys.platform == "darwin":
        return [os.path.expanduser("~/Library/Application Support/obs-studio")]
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return [os.path.join(base, "obs-studio"),
            os.path.expanduser("~/.var/app/com.obsproject.Studio/config/obs-studio")]   # the Flatpak


def local_settings(dirs=None):
    """OBS's remote-control settings on this computer: {"enabled", "port", "auth", "password"}, or None
    when OBS (28 or newer) has not been set up here. Read only when the user asks for it in the guide."""
    for folder in dirs or config_dirs():
        path = os.path.join(folder, "plugin_config", "obs-websocket", "config.json")
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            data = None
        if isinstance(data, dict):
            return {"enabled": bool(data.get("server_enabled", False)),
                    "port": int(data.get("server_port") or DEFAULT_PORT),
                    "auth": bool(data.get("auth_required", True)), "password": str(data.get("server_password") or "")}
        # OBS 28 and 29 kept them in global.ini, section [OBSWebSocket]
        ini = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            with open(os.path.join(folder, "global.ini"), encoding="utf-8-sig") as fh:
                ini.read_file(fh)
        except (OSError, configparser.Error):
            continue
        if ini.has_section("OBSWebSocket"):
            s = ini["OBSWebSocket"]
            yes = lambda key, default: s.get(key, default).strip().lower() == "true"
            port = s.get("ServerPort", str(DEFAULT_PORT)).strip()
            return {"enabled": yes("ServerEnabled", "false"),
                    "port": int(port) if port.isdigit() else DEFAULT_PORT,
                    "auth": yes("AuthRequired", "true"), "password": s.get("ServerPassword", "")}
    return None
