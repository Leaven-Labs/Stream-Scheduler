"""Exit 0 when the container's keyring is unlocked and can keep a secret (docker/startapp.sh)."""
import sys

import keyring

try:
    keyring.set_password("Stream Scheduler", "container:check", "ok")
    ok = keyring.get_password("Stream Scheduler", "container:check") == "ok"
    keyring.delete_password("Stream Scheduler", "container:check")
except Exception as exc:  # locked (no one to type the password), or no Secret Service at all
    print(f"keyring: {type(exc).__name__}: {exc}", file=sys.stderr)
    ok = False
sys.exit(0 if ok else 1)
