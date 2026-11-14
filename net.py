"""One small HTTPS helper for the platforms' APIs (standard library only).

Errors never carry the address that was asked for, because a token can be part of it.
"""
import base64
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

import paths

_context = None


class ApiError(Exception):
    """A platform said no (or could not be reached). `status` is the HTTP status, 0 for no connection;
    `reason` is the platform's short code when it gave one (YouTube: "liveStreamingNotEnabled")."""

    def __init__(self, message, status=0, reason=""):
        super().__init__(message)
        self.status, self.reason = status, reason


def _ssl_context():
    """The system's own list of trusted certificates (truststore) when it is installed."""
    global _context
    if _context is None:
        try:
            import truststore
            _context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except ImportError:
            _context = ssl.create_default_context()
    return _context


def send(method, url, headers, data, timeout):
    """Do the request: (status, bytes). Tests put their own function in this place."""
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise ApiError(f"Could not connect ({reason}). Check the internet connection.") from None


def _error(status, payload):
    reason, message = "", ""
    err = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(err, dict):  # Google's APIs and Facebook
        message = err.get("error_user_msg") or err.get("message") or ""
        errors = err.get("errors") or [{}]
        reason = errors[0].get("reason") or str(err.get("status") or err.get("code") or "")
    elif isinstance(err, str):  # OAuth token answers
        reason, message = err, payload.get("error_description") or err
    elif isinstance(payload, dict) and isinstance(payload.get("message"), str):  # Wix, WordPress, Discord
        message = payload["message"]
        details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
        reason = str(details.get("applicationError", {}).get("code", "") or payload.get("code") or "")
    elif isinstance(payload, dict) and isinstance(payload.get("errors"), list):  # Pushover
        message = " ".join(str(e) for e in payload["errors"])
    return ApiError(message or f"The server answered with error {status}.", status, reason)


def basic(user, password):
    """The Authorization header of a user name with a password (WordPress application passwords)."""
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


def request(method, url, params=None, form=None, body=None, token=None, timeout=30, headers=None, raw=None):
    """Ask and return the JSON answer. `token` goes in the Authorization header (as a Bearer token),
    `form` and `body` (JSON) in the request, never in the address. `headers` adds or replaces headers.
    `raw` is (bytes, content type) for a file, such as a thumbnail."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    headers = {"Accept": "application/json", "User-Agent": f"StreamScheduler/{paths.VERSION}", **(headers or {})}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    elif form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif raw is not None:
        data, headers["Content-Type"] = raw
    status, raw = send(method, url, headers, data, timeout)
    try:
        payload = json.loads(raw) if raw else {}
    except ValueError:
        payload = {}
    if status >= 400:
        raise _error(status, payload)
    return payload
