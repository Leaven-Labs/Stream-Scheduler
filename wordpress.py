"""WordPress: show a YouTube stream on a page of a WordPress website.

The page holds a synced pattern (a reusable block) and this module replaces that pattern's content
with a YouTube embed of the coming stream. A synced pattern shows the same content wherever it is
placed, and nothing else on the page is touched.

The user makes an application password in their WordPress profile (the guide explains how); it is
kept in the keychain. WordPress has these since version 5.6 and gives them only over HTTPS.
"""
import html
import urllib.parse

import net


def site_address(text):
    """A site's address as typed -> "https://example.org" (with its folder, without a trailing slash).
    Raises ApiError for an address that is not HTTPS: the password would travel in the open."""
    text = (text or "").strip().rstrip("/")
    if text and "://" not in text:
        text = "https://" + text
    parts = urllib.parse.urlparse(text)
    if parts.scheme != "https" or not parts.netloc:
        raise net.ApiError("Enter the website's address, starting with https://")
    return f"https://{parts.netloc}{parts.path}".rstrip("/")


def _ask(method, site, path, user, password, params=None, body=None):
    # ?rest_route= reaches the REST API whatever the site's permalink setting is
    url = site_address(site) + "/?rest_route=" + path
    try:
        return net.request(method, url, params, body=body,
                           headers={"Authorization": net.basic(user.strip(), password.strip())})
    except net.ApiError as exc:
        if exc.status in (401, 403):
            raise net.ApiError("WordPress refused the user name or the application password, or this user may "
                               f"not edit patterns. ({exc})", exc.status, exc.reason) from None
        if exc.status == 404:
            raise net.ApiError("WordPress did not find it: check the website's address, and that the pattern "
                               f"still exists. ({exc})", exc.status, exc.reason) from None
        raise


def patterns(site, user, password):
    """The site's synced patterns: [{"id", "title"}] (the first 100)."""
    answer = _ask("GET", site, "/wp/v2/blocks", user, password, {"per_page": 100, "context": "edit"})
    if not isinstance(answer, list):
        raise net.ApiError("This address did not answer like a WordPress website. Check the address.")
    return [{"id": b["id"], "title": (b.get("title") or {}).get("raw") or f"Pattern {b['id']}"} for b in answer]


def content(site, user, password, pattern_id):
    """What a pattern holds now, as WordPress stores it."""
    answer = _ask("GET", site, f"/wp/v2/blocks/{pattern_id}", user, password, {"context": "edit"})
    return ((answer.get("content") or {}).get("raw") or "") if isinstance(answer, dict) else ""


def embed(link, title=""):
    """The blocks the pattern gets: WordPress's own YouTube embed, with the title above it when asked."""
    safe = html.escape(link, quote=True)
    heading = (f'<!-- wp:heading -->\n<h2 class="wp-block-heading">{html.escape(title)}</h2>\n'
               '<!-- /wp:heading -->\n\n') if title else ""
    return (heading + '<!-- wp:embed {"url":"' + safe + '","type":"video","providerNameSlug":"youtube",'
            '"responsive":true,"className":"wp-embed-aspect-16-9 wp-has-aspect-ratio"} -->\n'
            '<figure class="wp-block-embed is-type-video is-provider-youtube wp-block-embed-youtube '
            'wp-embed-aspect-16-9 wp-has-aspect-ratio"><div class="wp-block-embed__wrapper">\n'
            + safe + '\n</div></figure>\n<!-- /wp:embed -->')


def show(dest, password, link, title):
    """Put a stream on the website a destination describes. Returns {"id", "url", "note"}."""
    o = dest.get("options", {})
    _ask("POST", dest["account_id"], f"/wp/v2/blocks/{o['pattern_id']}", o["user"], password,
         body={"content": embed(link, title if o.get("show_title") else "")})
    return {"id": str(o["pattern_id"]), "url": o.get("page_url", ""), "note": ""}


def shows(dest, password, link):
    """Whether the website still shows this stream."""
    o = dest.get("options", {})
    return html.escape(link, quote=True) in content(dest["account_id"], o["user"], password, o["pattern_id"])
