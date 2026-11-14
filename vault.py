"""Where tokens and client secrets are kept: the operating system's own keychain.

Windows: Credential Manager. Mac: Keychain. Linux: the Secret Service (GNOME Keyring, KWallet).
These encrypt with the user's login, so another user of the computer, or someone who copies the
app's settings folder, cannot read them. If the system has no keychain the app refuses to save a
secret; it never falls back to a plain file.

One entry per secret: service "Stream Scheduler", name "<destination id>:<what>".
"""
import paths

SERVICE = paths.APP_NAME
SECRETS = {"youtube": ["client_secret", "refresh_token"], "facebook": ["page_token"], "wix": ["api_key"],
           "wordpress": ["app_password"], "webhook": ["url"]}
NOTIFY = "notify"   # the id under which the notification channels' secrets are kept (notify.py)


class VaultError(Exception):
    pass


class Vault:
    """The system keychain, through the `keyring` library."""

    def _keyring(self):
        try:
            import keyring
            from keyring.backends import fail
        except ImportError:
            raise VaultError("The 'keyring' library is not installed.") from None
        backend = keyring.get_keyring()
        name = f"{type(backend).__module__}.{type(backend).__name__}".lower()
        # only a real, encrypted system keychain will do: no "fail" backend and no plain-text file
        if isinstance(backend, fail.Keyring) or "plaintext" in name or "null" in name:
            raise VaultError("This computer has no keychain to keep passwords in. On Linux, install and unlock "
                             "GNOME Keyring or KWallet (the Secret Service), then try again.")
        return keyring

    def available(self):
        try:
            self._keyring()
            return ""
        except VaultError as exc:
            return str(exc)

    def where(self):
        import sys
        return {"win32": "Windows Credential Manager", "darwin": "the macOS Keychain"}.get(
            sys.platform, "the system keyring (Secret Service)")

    def set(self, dest_id, name, value):
        try:
            self._keyring().set_password(SERVICE, f"{dest_id}:{name}", value)
        except VaultError:
            raise
        except Exception as exc:
            raise VaultError(f"The keychain refused to save the secret ({type(exc).__name__}).") from None

    def get(self, dest_id, name):
        try:
            value = self._keyring().get_password(SERVICE, f"{dest_id}:{name}")
        except VaultError:
            raise
        except Exception as exc:
            raise VaultError(f"The keychain could not be read ({type(exc).__name__}). Is it unlocked?") from None
        if not value:
            raise VaultError("The saved sign-in for this destination is missing from the keychain. "
                             "Use Reconnect on the Destinations page.")
        return value

    def has(self, dest_id, name):
        try:
            self.get(dest_id, name)
            return True
        except VaultError:
            return False

    def remove(self, dest_id, name):
        """Delete one secret. Nothing happens when it was never saved."""
        try:
            self._keyring().delete_password(SERVICE, f"{dest_id}:{name}")
        except Exception:
            pass  # was never saved, or the keychain is gone: nothing left to delete

    def forget(self, dest_id, kind):
        """Delete every secret of a destination (when it is removed)."""
        for name in SECRETS.get(kind, []):
            self.remove(dest_id, name)

    def move(self, kind, from_id, to_id):
        """Give the secrets of one destination to another id (a destination that was connected again)."""
        for name in SECRETS.get(kind, []):
            self.set(to_id, name, self.get(from_id, name))
        self.forget(from_id, kind)


class MemoryVault(Vault):
    """Keeps secrets in memory only (tests and --uitest)."""

    def __init__(self):
        self.items = {}

    def available(self):
        return ""

    def set(self, dest_id, name, value):
        self.items[f"{dest_id}:{name}"] = value

    def get(self, dest_id, name):
        if f"{dest_id}:{name}" not in self.items:
            raise VaultError("The saved sign-in for this destination is missing from the keychain. "
                             "Use Reconnect on the Destinations page.")
        return self.items[f"{dest_id}:{name}"]

    def remove(self, dest_id, name):
        self.items.pop(f"{dest_id}:{name}", None)
