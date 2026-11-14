# Security

## How your accounts are protected

- **No passwords.** You sign in on Google's and Meta's own pages. The app never sees your password.
- **No server in between.** The app talks from your computer straight to `googleapis.com`,
  `accounts.google.com` and `graph.facebook.com`, over HTTPS checked against your system's trusted
  certificates. Leaven Labs runs no service for this app and receives nothing.
- **Your own app registration.** You create the Google Cloud project and the Meta app yourself, so
  access is yours to see and to cancel, and nobody else's key can reach your channel or Page.
- **Secrets live in the system keychain**: Windows Credential Manager, the macOS Keychain, or the Linux
  Secret Service. They are encrypted with your login to the computer. If the system has no keychain,
  the app refuses to save a sign-in; it never falls back to a plain file.
- **The settings file holds no secrets**: `config.json` has names, ids, schedules and history only.
- **The least that works.**
  - YouTube: one permission (`youtube`), the narrowest that can create broadcasts. Kept: the OAuth
    client secret and a refresh token. The sign-in uses PKCE and a one-time `state` value, and listens
    only on `127.0.0.1` while you sign in.
  - Facebook: `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`. Kept: the access token
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
  and revoke it at <https://myaccount.google.com/permissions> or under Facebook → Settings → Business
  integrations.
- Never share a client secret, App secret, access token or stream key, and never commit one to git.

## Reporting a problem

Please do not open a public issue for a security problem. Use **Security → Report a vulnerability**
on the GitHub repository (a private report).
