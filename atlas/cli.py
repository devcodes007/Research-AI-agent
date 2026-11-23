"""Command line: python -m atlas <command>. See README for the workflow."""
import argparse
import json
import sys

from . import audit, patterns, reconcile, research, retrieve, seed
from .config import env, model_primary, model_verify, sub


def parse_ids(text, apps):
    if not text or text == "all":
        return apps
    ids = set()
    for part in text.split(","):
        if "-" in part:
            a, b = part.split("-")
            ids |= set(range(int(a), int(b) + 1))
        else:
            ids.add(int(part))
    return [a for a in apps if a["id"] in ids]


def cmd_doctor(args):
    """Check keys, Composio search, the LLM and a live page fetch in ~30 seconds."""
    from . import llm
    ok = True

    def fetch_check():
        page = retrieve.fetch("https://developers.fathom.ai/quickstart", refresh=True)
        if page.get("status") != 200 or page["thin"]:
            raise RuntimeError(f"status={page.get('status')} error={page.get('error')} (check internet/proxy)")
        return f"{len(page['text'])} chars"

    def step(name, fn):
        nonlocal ok
        try:
            print(f"[ ok ] {name}: {fn()}")
        except Exception as exc:
            ok = False
            print(f"[FAIL] {name}: {str(exc)[:300]}")
    if env("COMPOSIO_API_KEY"):
        print("[ ok ] COMPOSIO_API_KEY present")
    else:
        ok = False
        print("[FAIL] COMPOSIO_API_KEY missing: add it to .env")
    holder = {}

    def search():
        holder["s"] = retrieve.make_searcher()
        hits = holder["s"].search("Fathom API documentation authentication")
        mode = getattr(holder["s"], "mode", None) or getattr(holder["s"], "working", "n/a")
        extra = f" (session unavailable: {str(holder['s'].session_error)[:90]})" if getattr(holder["s"], "session_error", None) else ""
        return f"{holder['s'].name}/{mode}: {len(hits)} results, first: {hits[0]['url'] if hits else None}{extra}"
    step("web search", search)
    for m in dict.fromkeys([model_primary(), model_verify()]):
        if m == llm.HANDOFF:
            print("[ ok ] LLM: 'handoff' mode (prompts are written to data/handoff/ for an external agent to answer)")
        else:
            step(f"LLM ({m})", lambda m=m: llm.ask_json(m, "Reply with JSON only.", 'Return {"ok": true}'))
    step("page fetch + text extraction", fetch_check)

    def mcp():
        s = holder.get("s")
        if not hasattr(s, "client"):
            return "skipped (not using Composio backend)"
        if getattr(s, "session", None) is None:
            return "skipped: needs a key with session_management write access"
        session = s.client.create(user_id=s.user_id, toolkits=["composio_search"], mcp=True)
        return f"hosted MCP endpoint available: {session.mcp.url}"
    step("Composio MCP endpoint", mcp)
    print("\nAll good." if ok else "\nFix the FAIL lines above (paste them to Claude if stuck).")
    return 0 if ok else 1


def cmd_catalog(args):
    from . import catalog
    m = catalog.run(seed.load())
    for i, v in m.items():
        print(f"{i:3d} {v['app']:<28} -> {v['toolkit'] or '-':<28} ({v['how']}) {v['auth_schemes']}")


def uncertain_ids():
    """Risk-based selection for the independent second pass: weak confidence, lint flags, or disagreement with Composio's catalog."""
    from . import catalog
    cm = catalog.load_matches()
    ids = []
    for p in sorted(sub("baseline").glob("*.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        entry = cm.get(r["id"])
        agree = catalog.agreement(r["auth"], entry if entry and entry.get("toolkit") else None)
        flags = [f for f in r.get("lint", []) if f.startswith("unknown_access")]
        if r["confidence"] == "low" or flags or r["self_serve"] == "unknown" or r["verdict"] == "unclear" or agree == "disagree":
            ids.append(r["id"])
    return ids


def cmd_research(args):
    apps = parse_ids(args.ids, seed.load())
    if args.select == "uncertain":
        keep = set(uncertain_ids())
        apps = [a for a in apps if a["id"] in keep]
        print(f"risk-based selection: {len(apps)} apps need an independent second pass: {[a['id'] for a in apps]}")
    searcher = retrieve.make_searcher()
    phases = ["primary", "blind"] if args.phase == "both" else [args.phase]
    for phase in phases:
        folder = "baseline" if phase == "primary" else "verify"
        model = model_primary() if phase == "primary" else model_verify()
        print(f"== pass '{phase}' with {model} over {len(apps)} apps -> data/{folder}/")
        research.run(apps, searcher, model, phase, folder, force=args.force, workers=args.workers)


def cmd_retry(args):
    """Re-research apps the first reconcile left uncertain (low confidence, unresolved dispute or ungrounded claim)."""
    final = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(sub("final").glob("*.json"))]
    weak = [r["id"] for r in final if r["confidence"] == "low" or any(not d["resolved"] for d in r.get("verification", {}).get("disputed", {}).values())
            or any(f.startswith("ungrounded") for f in r.get("lint", []))]
    apps = [a for a in seed.load() if a["id"] in set(weak)]
    print(f"{len(apps)} uncertain apps -> retry pass: {weak}")
    research.run(apps, retrieve.make_searcher(), model_verify(), "retry", "retry", force=args.force, workers=6)


def cmd_reconcile(args):
    changes = reconcile.run()
    print(f"{len(changes)} key-field changes between first pass and final -> data/changes.json")


def cmd_patterns(args):
    result = patterns.run()
    print("\n".join("- " + h for h in result["headlines"]))


def cmd_audit_prep(args):
    audit.prepare()


def cmd_audit_score(args):
    audit.score(args.file)


def cmd_build(args):
    from . import site
    print(site.build())


def cmd_status(args):
    for folder in ("baseline", "verify", "retry", "final"):
        print(f"{folder:9} {len(list(sub(folder).glob('*.json')))}" + ("/100" if folder != "retry" else ""))
    h = sub("handoff")
    prompts = list(h.glob("*.prompt.md"))
    waiting = [p.name.replace(".prompt.md", "") for p in prompts if not (h / p.name.replace(".prompt.md", ".answer.json")).exists()]
    if prompts:
        print(f"handoff   {len(prompts) - len(waiting)}/{len(prompts)} prompts answered; waiting: {len(waiting)}")
    print("audit summary:", "present" if (sub('audit') / "summary.json").exists() else "pending")


def cmd_seed(args):
    print(seed.write())


def main(argv=None):
    p = argparse.ArgumentParser(prog="atlas", description=__doc__)
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("doctor").set_defaults(fn=cmd_doctor)
    r = s.add_parser("research", help="run the agent (first pass, blind second pass, or both)")
    r.add_argument("--ids", default="all", help="e.g. 1-10,93 or all")
    r.add_argument("--phase", choices=["primary", "blind", "both"], default="both")
    r.add_argument("--force", action="store_true")
    r.add_argument("--select", choices=["all", "uncertain"], default="all", help="uncertain = only apps whose first pass is weak (use with --phase blind)")
    r.add_argument("--workers", type=int, default=6, help="apps researched in parallel")
    r.set_defaults(fn=cmd_research)
    t = s.add_parser("retry", help="third pass on uncertain apps; reconcile then uses majority-of-3")
    t.add_argument("--force", action="store_true")
    t.set_defaults(fn=cmd_retry)
    s.add_parser("catalog", help="match the 100 apps against Composio's toolkit catalog").set_defaults(fn=cmd_catalog)
    s.add_parser("reconcile", help="adjudicate disagreements -> final records").set_defaults(fn=cmd_reconcile)
    s.add_parser("patterns").set_defaults(fn=cmd_patterns)
    s.add_parser("audit-prep", help="build the human review page").set_defaults(fn=cmd_audit_prep)
    a = s.add_parser("audit-score", help="score first pass vs final against human-audit.json")
    a.add_argument("file")
    a.set_defaults(fn=cmd_audit_score)
    s.add_parser("build", help="generate docs/index.html").set_defaults(fn=cmd_build)
    s.add_parser("status").set_defaults(fn=cmd_status)
    s.add_parser("seed").set_defaults(fn=cmd_seed)
    args = p.parse_args(argv)
    sys.exit(args.fn(args) or 0)
