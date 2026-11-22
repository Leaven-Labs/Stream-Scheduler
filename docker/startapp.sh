#!/bin/sh
# Starts Stream Scheduler in the container (run by the base image, as the user USER_ID:GROUP_ID).
#
# Everything the app keeps is in /config, the folder mapped to the server:
#   /config/data                      settings, schedules, history (config.json)
#   /config/.local/share/keyrings     the sign-ins, in a GNOME keyring encrypted with KEYRING_PASSWORD
#   /config/.mozilla                  the browser used for sign-ins
set -u

export HOME=/config
export XDG_CONFIG_HOME=/config/.config
export XDG_DATA_HOME=/config/.local/share
export STREAM_SCHEDULER_DATA_DIR=/config/data
export BROWSER=firefox-esr
APP=/opt/stream-scheduler

stop() {
    echo "$1" >&2
    yad --title "Stream Scheduler" --text "$(printf %s "$1" | tr "\n" " ")" --button "Close:0" --center --width 520 --wrap >/dev/null 2>&1
    sleep 30   # the base image starts the app again; don't spin
    exit 1
}

if [ "${1:-}" != "--in-session" ]; then
    if [ -z "${KEYRING_PASSWORD:-}" ]; then
        stop "KEYRING_PASSWORD is not set. Give the container a password of your choice in the variable
KEYRING_PASSWORD: it encrypts the sign-ins (YouTube, Wix, WordPress, alerts) kept in /config. Keep it the
same from then on, or the saved sign-ins cannot be opened."
    fi
    mkdir -p "$STREAM_SCHEDULER_DATA_DIR" "$XDG_DATA_HOME/keyrings" "$XDG_CONFIG_HOME"
    # Only this one copy of the app ever runs in the container, so a lock left behind is a stopped copy's.
    rm -f "$STREAM_SCHEDULER_DATA_DIR/app.lock"
    # A private session bus for the app, the keyring and the browser. It starts without the display, so
    # the keyring can never put up its own password prompt: a wrong password is reported below instead.
    export APP_DISPLAY="${DISPLAY:-:0}"
    exec env -u DISPLAY dbus-run-session -- "$0" --in-session
fi

# Start the keyring and unlock it with the password (the first time, this creates it with that password).
eval "$(printf '%s' "$KEYRING_PASSWORD" | gnome-keyring-daemon --unlock --components=secrets)"
eval "$(gnome-keyring-daemon --start --components=secrets)"
export GNOME_KEYRING_CONTROL
unset KEYRING_PASSWORD
export DISPLAY="$APP_DISPLAY"

if ! timeout 30 /opt/venv/bin/python "$APP/docker/keyring_check.py"; then
    stop "The keyring in /config could not be opened with KEYRING_PASSWORD. Set KEYRING_PASSWORD back to the
password the container had before. (If it is lost: stop the container, delete
/config/.local/share/keyrings, start it again and connect each destination again.)"
fi

cd "$APP"
exec /opt/venv/bin/python app.py
