#!/bin/sh
# The WebUI's login page is the only way into the app (run by the base image before it starts).
# Without it the container does not start: whoever reaches the WebUI could change or cancel streams.
set -u

missing=""
is-bool-val-true "${WEB_AUTHENTICATION:-0}" || missing="$missing WEB_AUTHENTICATION=1"
is-bool-val-true "${SECURE_CONNECTION:-0}" || missing="$missing SECURE_CONNECTION=1"
is-bool-val-true "${VNC_LOCALHOST_ONLY:-0}" || missing="$missing VNC_LOCALHOST_ONLY=1"
[ -n "${WEB_AUTHENTICATION_USERNAME:-}" ] || missing="$missing WEB_AUTHENTICATION_USERNAME"
[ -n "${WEB_AUTHENTICATION_PASSWORD:-}" ] || missing="$missing WEB_AUTHENTICATION_PASSWORD"

if [ -n "$missing" ]; then
    echo "ERROR: Stream Scheduler opens only behind the WebUI's login page. Set:$missing"
    echo "ERROR: (WEB_AUTHENTICATION_USERNAME and WEB_AUTHENTICATION_PASSWORD are the login page's user name"
    echo "ERROR: and password. See docker/README.md.)"
    exit 1
fi
