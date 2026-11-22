# Stream Scheduler in a container: the app's window is shown in a web browser (https, port 5800, behind a login page), for a home
# server such as Unraid. See docker/README.md.
#
#   docker build -t stream-scheduler .
#   docker run -d -p 5800:5800 -v /path/to/appdata:/config -e KEYRING_PASSWORD=... -e TZ=America/Chicago \
#     -e WEB_AUTHENTICATION_USERNAME=... -e WEB_AUTHENTICATION_PASSWORD=... stream-scheduler
#
# The base image runs the X display, the web page that shows it, and restarts the app if it stops.
FROM jlesage/baseimage-gui:debian-12-v4.14.0

# Python, Qt's system libraries, the Secret Service (GNOME Keyring) for the sign-ins, and Firefox for
# the sign-ins and setup guides that open a web page (Google's sign-in comes back to 127.0.0.1, so the
# browser has to run in the container too).
RUN add-pkg \
        python3 python3-venv \
        libegl1 libgl1 libxkbcommon0 libxkbcommon-x11-0 libfontconfig1 libdbus-1-3 \
        libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
        libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libxcb-xfixes0 \
        gnome-keyring dbus \
        firefox-esr xdg-utils \
        fonts-dejavu-core ca-certificates tzdata

COPY requirements.txt /opt/stream-scheduler/requirements.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r /opt/stream-scheduler/requirements.txt

COPY . /opt/stream-scheduler/
RUN chmod 755 /opt/stream-scheduler/docker/startapp.sh \
    && ln -s /opt/stream-scheduler/docker/startapp.sh /startapp.sh \
    && install -m 755 /opt/stream-scheduler/docker/require-web-login.sh /etc/cont-init.d/05-require-web-login.sh \
    && APP_ICON_URL=file:///opt/stream-scheduler/assets/logo-120.png \
    && (install_app_icon.sh "$APP_ICON_URL" || true)

RUN set-cont-env APP_NAME "Stream Scheduler" \
    && set-cont-env APP_VERSION "$(cd /opt/stream-scheduler && /opt/venv/bin/python -c 'import paths; print(paths.VERSION)')"

# The app runs all the time in the container and is started again if it stops. The WebUI's login page,
# over https, is the only way in: the VNC server behind the WebUI listens inside the container only (no
# port 5900 from outside). docker/require-web-login.sh stops the container if any of this is switched off.
ENV KEEP_APP_RUNNING=1 \
    VNC_LOCALHOST_ONLY=1 \
    SECURE_CONNECTION=1 \
    WEB_AUTHENTICATION=1

LABEL org.opencontainers.image.title="Stream Scheduler" \
      org.opencontainers.image.description="Schedules weekly live streams on YouTube, in a container with a web view" \
      org.opencontainers.image.source="https://github.com/Leaven-Labs/Stream-Scheduler" \
      org.opencontainers.image.licenses="MIT"
