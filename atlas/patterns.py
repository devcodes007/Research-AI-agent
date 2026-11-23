"""Pattern analysis. Deterministic: every headline sentence is computed from the data, never written by an LLM."""
import json
from collections import Counter

from . import schema
from .config import sub


def load_final():
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(sub("final").glob("*.json"))]


def pct(n, d):
    return round(100 * n / d) if d else 0


def compute(recs):
    n = len(recs)
    cats = sorted({r["category"] for r in recs})
    auth = Counter(a for r in recs for a in set(r["auth"]))
    auth_primary = Counter()
    for r in recs:
        order = [a for a in ["OAuth2", "API key", "Bearer token", "Basic", "JWT", "Session", "HMAC", "Other", "None/local"] if a in r["auth"]]
        auth_primary[order[0] if order else "Other"] += 1
    ss = Counter(r["self_serve"] for r in recs)
    gated = sum(1 for r in recs if schema.is_gated(r))
    by_cat = {}
    for c in cats:
        rs = [r for r in recs if r["category"] == c]
        by_cat[c] = {"n": len(rs), "self_serve": dict(Counter(r["self_serve"] for r in rs)),
                     "gated": sum(1 for r in rs if schema.is_gated(r)), "verdict": dict(Counter(r["verdict"] for r in rs)),
                     "mcp": dict(Counter(r["mcp_status"] for r in rs)),
                     "api_key_share": pct(sum(1 for r in rs if "API key" in r["auth"]), len(rs)),
                     "oauth_share": pct(sum(1 for r in rs if "OAuth2" in r["auth"]), len(rs))}
    blockers = Counter(r["blocker"] for r in recs if r["blocker"] != "none")
    verdict = Counter(r["verdict"] for r in recs)
    mcp = Counter(r["mcp_status"] for r in recs)
    easy = [{"id": r["id"], "name": r["name"], "category": r["category"], "auth": r["auth"], "mcp": r["mcp_status"]}
            for r in recs if r["verdict"] == "build_now"]
    outreach = [{"id": r["id"], "name": r["name"], "category": r["category"], "blocker": r["blocker"], "detail": r["blocker_detail"]}
                for r in recs if r["verdict"] == "needs_outreach"]
    unclear = [{"id": r["id"], "name": r["name"]} for r in recs if r["verdict"] == "unclear"]
    combo = Counter((r["auth"][0] if r["auth"] else "?", r["self_serve"]) for r in recs)

    def rank(key, reverse=True):
        return sorted(by_cat.items(), key=lambda kv: (kv[1][key] / kv[1]["n"], kv[0]), reverse=reverse)

    def open_n(c):
        return sum(v for k, v in c["self_serve"].items() if k in ("instant", "free_tier", "trial"))
    most_open = max(by_cat.items(), key=lambda kv: (open_n(kv[1]) / kv[1]["n"], kv[0]), default=None)
    most_gated = max(by_cat.items(), key=lambda kv: kv[1]["gated"] / kv[1]["n"], default=None)
    named = [(k, v) for k, v in blockers.most_common() if k != "other"]
    top_auth, top_block = (auth.most_common(1) or [(None, 0)])[0], (named or [(None, 0)])[0]
    runner = [(k, v) for k, v in auth.most_common() if k != top_auth[0]][:1] or [(None, 0)]
    unknown_n = ss.get("unknown", 0)
    open_total = n - gated - unknown_n
    heads = []
    if n:
        heads.append(f"{top_auth[0]} is the most common auth method: {top_auth[1]} of {n} apps ({pct(top_auth[1], n)}%) support it. "
                     f"{runner[0][0]} follows with {runner[0][1]}.")
        heads.append(f"{open_total} of {n} apps ({pct(open_total, n)}%) are self-serve (instant, free tier or trial); "
                     f"{gated} ({pct(gated, n)}%) are gated by a paid plan, an approval or review step, or sales; "
                     f"for {unknown_n} ({pct(unknown_n, n)}%) the sources did not establish how access works.")
        if most_open and most_gated:
            heads.append(f"Most open category: {most_open[0]} ({open_n(most_open[1])}/{most_open[1]['n']} self-serve). "
                         f"Most gated: {most_gated[0]} ({most_gated[1]['gated']}/{most_gated[1]['n']} gated).")
        if top_block[0]:
            heads.append(f"The most common named blocker is '{top_block[0].replace('_', ' ')}' ({top_block[1]} apps; {blockers.get('other', 0)} more are tagged 'other').")
        heads.append(f"{verdict.get('build_now', 0)} apps can be built into an agent toolkit today with no external gate; "
                     f"{verdict.get('conditional', 0)} are conditional; {verdict.get('needs_outreach', 0)} need outreach; "
                     f"{verdict.get('unclear', 0)} remain unclear after verification.")
        heads.append(f"Official MCP servers exist for {mcp.get('official', 0)} apps; {mcp.get('community', 0)} have community-only MCP.")
    cov = [r for r in recs if (r.get("catalog") or {}).get("toolkit")]
    covered_ids = {r["id"] for r in cov}
    new_wins = [r["name"] for r in recs if r["verdict"] == "build_now" and r["id"] not in covered_ids and r.get("catalog") is not None]
    if recs and any("catalog" in r for r in recs):
        heads.append(f"Composio already ships a toolkit for {len(cov)} of {n} apps; {len(new_wins)} build-now apps have no Composio toolkit yet (the most actionable gaps).")
        agree = Counter((r.get("catalog") or {}).get("auth_agreement") for r in cov)
        heads.append(f"Where a toolkit exists, its auth schemes fully match our finding for {agree.get('match', 0)} of {len(cov)} apps (independent cross-check).")
    return {"composio_covered": len(cov), "composio_gaps_build_now": new_wins, "n": n, "auth": dict(auth), "auth_primary": dict(auth_primary), "self_serve": dict(ss), "gated": gated,
            "by_category": by_cat, "blockers": dict(blockers), "verdict": dict(verdict), "mcp": dict(mcp),
            "easy_wins": easy, "needs_outreach": outreach, "unclear": unclear, "headlines": heads,
            "auth_x_access": {f"{a} | {s}": c for (a, s), c in combo.most_common()}}


def run():
    result = compute(load_final())
    path = sub("final").parent / "patterns.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result
