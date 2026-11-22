# Stream Scheduler in Docker (Unraid and other home servers)

The container runs the same app as the desktop version, all the time, on your server, so no computer
has to be left on. You use the app's window in a web browser: **https://&lt;server&gt;:5800**, behind a login page.

> **Alpha, and new.** The container has been built and tested, but not yet used with a real YouTube
> channel from a server. Please report what you find.

## Unraid

1. Download the template into Unraid's template folder (in the Unraid terminal):

   ```bash
   wget -O /boot/config/plugins/dockerMan/templates-user/my-stream-scheduler.xml https://raw.githubusercontent.com/Leaven-Labs/Stream-Scheduler/main/docker/unraid/stream-scheduler.xml
   ```

2. **Docker → Add Container**, choose **stream-scheduler** under *Template*.
3. Fill in **Keyring password** (see below), a **Web login user name** and **Web login password**,
   check **Appdata**, and click **Apply**.
4. Click the container's icon → **WebUI**. The certificate is self-signed, so the browser warns the
   first time: accept it, then sign in.

Unraid passes your time zone (`TZ`) to the container by itself.

## Docker Compose or `docker run`

```bash
KEYRING_PASSWORD=choose-one WEB_USER=me WEB_PASSWORD=choose-another TZ=America/Chicago docker compose up -d
```

```bash
docker run -d --name stream-scheduler --restart unless-stopped -p 5800:5800 --shm-size 1g \
  -v /path/to/appdata:/config -e KEYRING_PASSWORD=choose-one -e TZ=America/Chicago \
  -e WEB_AUTHENTICATION_USERNAME=me -e WEB_AUTHENTICATION_PASSWORD=choose-another \
  ghcr.io/leaven-labs/stream-scheduler:latest
```

To build the image yourself: `docker build -t stream-scheduler .` in the repository.

## Settings

| Variable | |
|---|---|
| `KEYRING_PASSWORD` | **Required.** Encrypts the sign-ins (see below). Choose one and keep it. |
| `TZ` | Your time zone, such as `America/Chicago`. Schedules use it: "Sunday at 8:00 AM" is 8:00 AM there. |
| `USER_ID`, `GROUP_ID` | Who owns the files in `/config` (Unraid: 99 and 100). |
| `WEB_AUTHENTICATION_USERNAME`, `WEB_AUTHENTICATION_PASSWORD` | **Required.** The user name and password for the login page before the WebUI opens. |
| `DARK_MODE` | `1` for a dark frame around the app (the app's own theme is in its Settings). |

The container is built on [jlesage/baseimage-gui](https://github.com/jlesage/docker-baseimage-gui), so
its other settings work too.

**Whoever signs in to the WebUI can use the app**, and so change or cancel your streams, so the login
page is the only way in. The WebUI is always https with a login page (the certificate is self-signed;
`http://` addresses are sent on to `https://`), and the VNC server that the WebUI uses inside the
container listens only there: there is no port 5900. Without a user name and password, or with
`WEB_AUTHENTICATION`, `SECURE_CONNECTION` or `VNC_LOCALHOST_ONLY` switched off, the container stops
at once and its log says what to set. Keep port 5800 on your home network and reach it from outside only through a
VPN (Unraid's WireGuard, Tailscale), rather than by opening the port on your router.

## The sign-ins and `KEYRING_PASSWORD`

On a computer, the app keeps its sign-ins (the YouTube token, the Wix key, the WordPress password, the
alert passwords) in the system's keychain. In the container that is a GNOME keyring in
`/config/.local/share/keyrings`, encrypted with `KEYRING_PASSWORD`, so a copy of the appdata folder
without the password does not give the sign-ins away.

- Keep the password the same. With another one the app does not start and says so in the WebUI. Put
  the old password back, or, if it is lost, stop the container, delete
  `/config/.local/share/keyrings`, start it and **Reconnect** each destination and alert.
- The password is in the container's settings, so anyone who can see those (an Unraid admin) can
  open the sign-ins. That is the price of a server that starts by itself.

## Using it

Everything works as on a computer. Some things are different:

- **Signing in.** The guides open web pages (Google Cloud, YouTube's sign-in, Wix) in a browser
  **inside the container**, shown in the same WebUI. Google's sign-in has to come back to the app on
  `127.0.0.1`, which is why the browser runs in there. Copy and paste between your computer and the
  container through the clipboard panel at the side of the WebUI.
- **No tray, and no "Start when I log in".** The container starts the app when it starts, and again
  if it stops. Closing the window restarts it. The *Keep running in the tray* and *Start when I log
  in* switches in Settings do nothing here.
- **Backups** (Settings → Save a backup) are saved inside the container: choose a folder under
  `/config` and you find the file in your appdata folder. A backup of the appdata folder itself is a
  backup of everything, sign-ins included (still encrypted).
- **Alerts** come from the server, so the weekly summary now tells you whether the *server* is up.

## Files in `/config`

| | |
|---|---|
| `data/config.json` | destinations, schedules, history, settings |
| `.local/share/keyrings/` | the sign-ins, encrypted with `KEYRING_PASSWORD` |
| `.mozilla/` | the browser used for signing in |
| `log/` | the container's logs |
