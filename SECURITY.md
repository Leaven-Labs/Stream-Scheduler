# Security

## How your accounts are protected

- **No passwords.** You sign in on Google's and Meta's own pages. The app never sees your password.
- **No server in between.** The app talks from your computer straight to `googleapis.com`,
  `accounts.google.com`, `wixapis.com`, and to what you set up yourself: your WordPress site, a
  webhook address, and the services that tell you (your mail server, Discord, Slack, Pushover). All
  of it goes over HTTPS, or an encrypted connection to the mail server, checked against your
  system's trusted certificates. Leaven Labs runs no service for this app and receives nothing.
- **The look for a newer version** asks `api.github.com` for this project's public list of
  releases, once a day, and sends nothing but the app's name and version. It can be switched off in
  Settings. The app never downloads or installs anything by itself.
- **Your own app registration.** You create the Google Cloud project and the Meta app yourself, so
  access is yours to see and to cancel, and nobody else's key can reach your channel or Page.
- **Secrets live in the system keychain**: Windows Credential Manager, the macOS Keychain, or the Linux
  Secret Service. They are encrypted with your login to the computer. If the system has no keychain,
  the app refuses to save a sign-in; it never falls back to a plain file. In the Docker container the
  keychain is a GNOME keyring in the appdata folder, encrypted with the container's `KEYRING_PASSWORD`
  ([docker/README.md](docker/README.md)).
- **The settings file holds no secrets**: `config.json` has names, ids, schedules and history only.
- **The least that works.**
  - YouTube: one permission (`youtube`), the narrowest that can create broadcasts. Kept: the OAuth
    client secret and a refresh token. The sign-in uses PKCE and a one-time `state` value, and listens
    only on `127.0.0.1` while you sign in.
  - Wix: an API key with the Wix Data permission only (and the publishing permission only if you
    switch publishing on). Kept: that API key. The app reads and writes one item of one collection.
  - WordPress: an application password, which cannot log in to the dashboard and can be revoked in
    your profile. Kept: that password. The app reads the list of synced patterns and writes one of
    them. Only `https://` addresses are accepted.
  - Webhooks (a destination's web address, Discord, Slack): the address is the key, so it is kept in
    the keychain like a password, and only `https://` addresses are accepted.
  - Email: the mail account's password (use an app password) is kept in the keychain; the connection
    to the mail server is always encrypted (SSL or STARTTLS).
  - Pushover: the API token and the user key, both kept in the keychain.
  - OBS: the password of its remote control (obs-websocket), kept in the keychain. The app only
    reads from OBS (its version, profiles, scene collections and stream settings); it never starts a
    stream or changes a setting. OBS's remote control is **not encrypted** (`ws://`, port 4455), so it
    is for your own network only: never forward that port on your router, and use a VPN such as
    Tailscale to reach OBS at another site. On this computer, the guide can read the port and password
    from OBS's own settings file, only when you click *Fill in*. To check the key, the app asks YouTube
    for the channel's stream keys (`liveStreams`, `part=cdn`) and OBS for its own; they are compared
    in memory and dropped, never shown, logged or saved. Alerts name a key by its YouTube title only.
- **What an alert says:** the stream's title, time and link, and the reason something failed. It
  goes only to the services you set up on the Alerts page.
- **A backup file holds no secrets**: the same as the settings file, in a place you choose.
  - Facebook (switched off in this version): `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`. Kept: the access token
    of the one Page you choose. The App secret and the user token you paste are used once and dropped.
- **Stream keys are not saved.** A Facebook stream's key is fetched when you ask for it and put on
  the clipboard.
- Tokens are sent in the `Authorization` header or the request body, not in addresses, and error
  messages never include the address that was asked for.
  One exception, which Meta's API requires: the one-time exchange of the pasted token, with the App
  secret, is a query to `graph.facebook.com` over HTTPS.

## What you can do

- Turn on two-factor authentication for the Google and Facebook accounts.
- Use the app on a computer and a user account that you trust; anyone who can log in as you can use
  the saved sign-ins.
- To cancel access: remove the destination in the app (this deletes the sign-in from the computer),
  and revoke it at <https://myaccount.google.com/permissions>, delete the key at
  <https://manage.wix.com/account/api-keys>, or revoke the application password in your WordPress
  profile. Removing OBS on the Destinations page deletes its password from this computer; change the
  password in OBS (Tools → WebSocket Server Settings) to end it there. Removing a way to be told on the
  Alerts page deletes its key from the computer; delete the
  webhook in Discord or Slack, or the token at pushover.net, to end it on their side.
- Never share a client secret, App secret, access token or stream key, and never commit one to git.

## Reporting a problem

Please do not open a public issue for a security problem. Use **Security → Report a vulnerability**
on the GitHub repository (a private report).
