"""Record schema, enums, validation and consistency lint. Pure Python, no dependencies."""

AUTH = ["OAuth2", "API key", "Basic", "Bearer token", "JWT", "HMAC", "Session", "None/local", "Other"]
SELF_SERVE = ["instant", "free_tier", "trial", "paid_plan", "approval", "sales", "unknown"]
SELF_SERVE_HELP = {
    "instant": "A developer can create working credentials on their own, immediately, on a free signup",
    "free_tier": "A free plan is enough for real API use after signup",
    "trial": "Only a time-limited trial gives API access",
    "paid_plan": "A paid plan or paid add-on is required",
    "approval": "App review, developer-token approval, verification or admin approval is required",
    "sales": "Contact sales or a partnership agreement is required",
    "unknown": "Not established from the sources",
}
GATED = {"paid_plan", "approval", "sales"}
API_STYLES = ["REST", "GraphQL", "SDK", "CLI", "SOAP", "RPC", "Other", "None"]
MCP = ["official", "community", "not_found", "unknown"]
VERDICT = ["build_now", "conditional", "needs_outreach", "unclear"]
BLOCKER = ["none", "paid_plan", "approval_review", "sales_partnership", "admin_or_enterprise_only",
           "no_public_api", "local_tool_not_hosted_api", "third_party_wrapper", "ambiguous_product", "other"]
CONFIDENCE = ["high", "medium", "low"]
YESNO = ["yes", "no", "unknown"]
SUPPORTS = ["description", "auth", "access", "api", "mcp", "verdict"]
AUDIT_FIELDS = ["auth", "self_serve", "mcp_status", "verdict"]
MULTI_FIELDS = {"auth", "api_styles"}

ENUMS = {"self_serve": SELF_SERVE, "mcp_status": MCP, "verdict": VERDICT, "blocker": BLOCKER,
         "confidence": CONFIDENCE, "webhooks": YESNO, "sandbox": YESNO}
LISTS = {"auth": AUTH, "api_styles": API_STYLES}

CATEGORIES = ["CRM and Sales", "Support and Helpdesk", "Communications and Messaging",
              "Marketing, Ads, Email and Social", "Ecommerce", "Data, SEO and Scraping",
              "Developer, Infra and Data platforms", "Productivity and Project Management",
              "Finance and Fintech", "AI, Research and Media-native"]

REQUIRED = ["id", "name", "category", "description", "auth", "self_serve", "gate_detail", "api_styles",
            "api_scope", "webhooks", "sandbox", "mcp_status", "mcp_url", "verdict", "blocker",
            "blocker_detail", "confidence", "evidence", "issues", "model", "checked_at"]


def _match(value, allowed):
    """Case/format-insensitive enum coercion. Returns the canonical value or None."""
    if not isinstance(value, str):
        return None
    key = value.strip().lower().replace(" ", "_").replace("-", "_")
    for item in allowed:
        if key == item.lower().replace(" ", "_").replace("-", "_"):
            return item
    return None


def normalize(rec: dict) -> dict:
    """Coerce enum casing and list shapes without inventing information."""
    rec = dict(rec)
    for key, allowed in ENUMS.items():
        if key in rec:
            rec[key] = _match(rec[key], allowed) or rec[key]
    for key, allowed in LISTS.items():
        value = rec.get(key)
        if isinstance(value, str):
            value = [value]
        if isinstance(value, list):
            fixed = []
            for item in value:
                canon = _match(item, allowed)
                if canon is None and key == "auth":
                    canon = "Other"
                if canon and canon not in fixed:
                    fixed.append(canon)
            rec[key] = fixed
    return rec


def validate(rec: dict) -> list:
    """Hard schema errors. A record with errors is never published."""
    errors = []
    for key in REQUIRED:
        if key not in rec:
            errors.append(f"missing:{key}")
    for key, allowed in ENUMS.items():
        if key in rec and rec[key] not in allowed:
            errors.append(f"bad_enum:{key}={rec[key]!r}")
    for key, allowed in LISTS.items():
        values = rec.get(key)
        if not isinstance(values, list) or not values:
            errors.append(f"bad_list:{key}")
        elif any(v not in allowed for v in values):
            errors.append(f"bad_list_value:{key}")
    if rec.get("mcp_url") is not None and not str(rec["mcp_url"]).startswith("https://"):
        errors.append("bad_mcp_url")
    ev = rec.get("evidence")
    if not isinstance(ev, list) or not ev:
        errors.append("no_evidence")
    else:
        for e in ev:
            if not str(e.get("url", "")).startswith("https://"):
                errors.append("bad_evidence_url")
            if not e.get("supports"):
                errors.append("evidence_without_claim")
    return errors


def lint(rec: dict) -> list:
    """Soft consistency checks the agent must resolve or disclose. Not a factual accuracy test."""
    flags = []
    ss, verdict, blocker = rec.get("self_serve"), rec.get("verdict"), rec.get("blocker")
    if verdict == "build_now" and ss in GATED:
        flags.append("verdict_build_now_but_gated")
    if verdict == "needs_outreach" and ss in ("instant", "free_tier"):
        flags.append("verdict_outreach_but_self_serve")
    if verdict == "build_now" and blocker not in (None, "none"):
        flags.append("verdict_build_now_but_blocker")
    if verdict in ("conditional", "needs_outreach") and blocker == "none":
        flags.append("verdict_gated_but_no_blocker")
    if rec.get("mcp_status") in ("official", "community") and not rec.get("mcp_url"):
        flags.append("mcp_claimed_without_url")
    if "HMAC" in (rec.get("auth") or []):
        flags.append("hmac_listed_check_outbound_auth_only")
    if ss == "unknown" and verdict not in ("unclear", None):
        flags.append("unknown_access_but_confident_verdict")
    ev = rec.get("evidence") or []
    for need in ("auth", "access"):
        if not any(need in (e.get("supports") or []) and e.get("quote_match") in ("exact", "fuzzy") for e in ev):
            flags.append(f"ungrounded:{need}")
    return flags


def is_gated(rec: dict) -> bool:
    return rec.get("self_serve") in GATED
