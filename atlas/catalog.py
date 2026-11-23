"""Composio toolkit catalog as an independent cross-check.

Composio already publishes toolkits (and the auth schemes they implement) for many apps. That is a second, machine-readable
source for the `auth` claim, and it tells us which apps are already covered. A disagreement is a review flag, not proof:
the catalog lists what Composio implemented, not everything the vendor supports.
"""
import difflib
import json
import re

from .config import data_dir, env

SCHEME_MAP = {"OAUTH2": "OAuth2", "OAUTH1": "Other", "OAUTH": "OAuth2", "API_KEY": "API key", "BASIC": "Basic", "BEARER_TOKEN": "Bearer token",
              "JWT": "JWT", "BASIC_WITH_JWT": "Basic", "NO_AUTH": "None/local", "SERVICE_ACCOUNT": "Other",
              "GOOGLE_SERVICE_ACCOUNT": "Other", "DCR_OAUTH": "OAuth2", "SNOWFLAKE": "Other", "BILLCOM_AUTH": "Other", "CALCOM_AUTH": "Other"}
# Where Composio's toolkit slug differs from the app's common name.
ALIASES = {"Zoho CRM": ["zoho", "zohocrm", "zoho_crm"], "Google Ads": ["googleads", "google_ads"], "Meta Ads": ["metaads", "meta_ads", "facebook"],
           "LinkedIn Ads": ["linkedin_ads", "linkedin"], "Lark (Larksuite)": ["lark", "larksuite"], "WhatsApp Business": ["whatsapp"],
           "Threads (Meta)": ["threads"], "Salesforce Commerce Cloud": ["salesforce_commerce_cloud"], "Magento (Adobe Commerce)": ["magento", "adobe_commerce"],
           "Amazon Selling Partner": ["amazon_selling_partner", "amazon_sp", "amazon"], "MongoDB Atlas": ["mongodb_atlas", "mongodb", "mongodbatlas"],
           "Monday.com": ["monday", "monday_com"], "Help Scout": ["helpscout", "help_scout"], "Otter AI": ["otter", "otter_ai"],
           "YouTube Transcript": ["youtube_transcript", "youtube"], "Mermaid CLI": ["mermaid"], "NotebookLM": ["notebooklm"], "Bright Data": ["brightdata", "bright_data"],
           "SE Ranking": ["seranking", "se_ranking"], "Binance": ["binance"], "Paygent Connect": ["paygent"], "GoHighLevel": ["highlevel", "gohighlevel"],
           "Waterfall.io": ["waterfall", "waterfall_io"], "Twenty": ["twenty", "twenty_crm"], "Devin": ["devin"], "higgsfield": ["higgsfield"], "Plain": ["plain"], "Close": ["close", "close_crm"]}


def _n(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def fetch_all():
    from composio import Composio
    client = Composio(api_key=env("COMPOSIO_API_KEY"))
    items, cursor = [], None
    while True:
        page = client.toolkits.list(limit=500, cursor=cursor, sort_by="alphabetically") if cursor else client.toolkits.list(limit=500, sort_by="alphabetically")
        for t in page.items:
            meta = t.meta
            items.append({"slug": t.slug, "name": t.name, "auth_schemes": t.auth_schemes or [], "managed": t.composio_managed_auth_schemes or [],
                          "no_auth": bool(t.no_auth), "tools_count": int(meta.tools_count), "app_url": meta.app_url,
                          "categories": [c.name for c in meta.categories], "type": getattr(t, "toolkit_type", None)})
        cursor = page.next_cursor
        if not cursor or not page.items:
            break
    return items


def match_app(app, catalog):
    """Returns (toolkit|None, how). Conservative: ambiguous names become 'none' rather than a wrong match."""
    by_slug = {_n(t["slug"]): t for t in catalog}
    by_name = {_n(t["name"]): t for t in catalog}
    keys = [_n(app["name"])] + [_n(a) for a in ALIASES.get(app["name"], [])]
    base = re.sub(r"\(.*?\)", "", app["name"]).strip()
    keys.append(_n(base))
    for k in keys:
        if k in by_slug:
            return by_slug[k], "slug"
        if k in by_name:
            return by_name[k], "name"
    host = re.search(r"([a-z0-9-]+)\.(?:com|io|dev|ai|app|org|net|co)", app.get("hint", "").lower())
    if host:
        for t in catalog:
            if t.get("app_url") and host.group(0) in t["app_url"].lower() and _n(t["name"])[:4] == _n(app["name"])[:4]:
                return t, "url"
    close = difflib.get_close_matches(_n(app["name"]), list(by_name), n=1, cutoff=0.92)
    return (by_name[close[0]], "fuzzy") if close else (None, "none")


def mapped(schemes):
    return sorted({SCHEME_MAP.get(s.upper(), "Other") for s in schemes})


def agreement(our_auth, entry):
    if entry is None:
        return "no_toolkit"
    theirs, ours = set(mapped(entry["auth_schemes"] or (["NO_AUTH"] if entry["no_auth"] else []))), set(our_auth)
    ours_cmp = ours - {"HMAC", "Session", "Other"}
    theirs_cmp = theirs - {"Other"}
    if not theirs_cmp or not ours_cmp:
        return "inconclusive"
    if ours_cmp == theirs_cmp:
        return "match"
    return "partial" if ours_cmp & theirs_cmp else "disagree"


def run(apps, log=print):
    catalog = fetch_all()
    (data_dir() / "composio_catalog.json").write_text(json.dumps(catalog, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    matches = {}
    for app in apps:
        t, how = match_app(app, catalog)
        matches[app["id"]] = {"app": app["name"], "toolkit": t["slug"] if t else None, "how": how,
                              "auth_schemes": t["auth_schemes"] if t else [], "no_auth": t["no_auth"] if t else None,
                              "tools_count": t["tools_count"] if t else 0, "name": t["name"] if t else None}
    (data_dir() / "catalog_match.json").write_text(json.dumps(matches, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    have = sum(1 for m in matches.values() if m["toolkit"])
    log(f"Composio catalog: {len(catalog)} toolkits; {have} of {len(apps)} apps matched (fuzzy/url matches should be eyeballed)")
    return matches


def load_matches():
    path = data_dir() / "catalog_match.json"
    return {int(k): v for k, v in json.loads(path.read_text(encoding="utf-8")).items()} if path.exists() else {}
