"""Wix: show a YouTube stream on a page of a Wix website.

Wix has no API that reaches into a page and edits an element. The supported way is the CMS: the
video player on the page is connected to one item of a collection, and this module writes the
stream's link into that item. Changes to collection content are live at once.

The user makes an API key in their Wix account (the guide explains how); it is kept in the keychain.
Wix wants the key as the whole Authorization header (no "Bearer"), plus the site's id.
"""
import net

API = "https://www.wixapis.com"


def _ask(method, path, api_key, site_id, params=None, body=None):
    try:
        return net.request(method, API + path, params, body=body,
                           headers={"Authorization": api_key.strip(), "wix-site-id": site_id.strip()})
    except net.ApiError as exc:
        if exc.status in (401, 403):
            raise net.ApiError("Wix refused the API key for this site. Check the key, the Site ID, and that the "
                               f"key has the permission this needs. ({exc})", exc.status, exc.reason) from None
        if exc.status == 404:
            raise net.ApiError(f"Wix did not find it: check the collection ID and that the item still exists. ({exc})",
                               exc.status, exc.reason) from None
        raise


def items(api_key, site_id, collection):
    """The items of a collection: [{"id", "data"}] (the first 50)."""
    answer = _ask("POST", "/wix-data/v2/items/query", api_key, site_id,
                  body={"dataCollectionId": collection, "query": {"paging": {"limit": 50}}})
    return [{"id": i.get("id") or i.get("data", {}).get("_id"), "data": i.get("data", {})}
            for i in answer.get("dataItems", [])]


def item(api_key, site_id, collection, item_id):
    answer = _ask("GET", f"/wix-data/v2/items/{item_id}", api_key, site_id, {"dataCollectionId": collection})
    return answer.get("dataItem", {}).get("data", {})


def update(api_key, site_id, collection, item_id, values):
    """Change some fields of one item. Wix replaces the whole item on an update, so the item is read
    first and sent back with the new values in it; its other fields stay as they were."""
    data = {**item(api_key, site_id, collection, item_id), **values, "_id": item_id}
    _ask("PUT", f"/wix-data/v2/items/{item_id}", api_key, site_id,
         body={"dataCollectionId": collection, "dataItem": {"id": item_id, "data": data}})


def publish(api_key, site_id):
    """Publish the site: everything saved in the Wix editor goes live, not only this change."""
    _ask("POST", "/site-publisher/v1/site/publish", api_key, site_id, body={})


def show(dest, api_key, link, title):
    """Put a stream's link (and title) on the website a destination describes. Returns {"id", "url", "note"}."""
    o = dest.get("options", {})
    values = {o["url_field"]: link}
    if o.get("title_field"):
        values[o["title_field"]] = title
    update(api_key, dest["account_id"], o["collection"], o["item_id"], values)
    note = ""
    if o.get("publish"):
        try:
            publish(api_key, dest["account_id"])
        except net.ApiError as exc:
            note = (f"The website shows the new stream, but Wix did not publish the site ({exc}). Collection "
                    "content is live without publishing, so this usually does not matter.")
    return {"id": o["item_id"], "url": o.get("page_url", ""), "note": note}
