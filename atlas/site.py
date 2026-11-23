"""Build the single self-explanatory page (docs/index.html) plus machine-readable exports for agents."""
import csv
import datetime
import json
import os
from pathlib import Path

from . import patterns as pat
from . import schema
from .config import ROOT, data_dir, env, sub

DOCS = Path(os.environ.get("ATLAS_DOCS", str(ROOT / "docs")))


def process_stats(recs, base):
    n = len(recs)
    ev = [e for r in recs for e in r["evidence"]]
    bev = [e for r in base.values() for e in r["evidence"]]
    ok = lambda es: round(100 * sum(e.get("quote_match") in ("exact", "fuzzy") for e in es) / len(es)) if es else None
    vers = [r.get("verification", {}) for r in recs]
    disputed = [(r["name"], f, d) for r, v in zip(recs, vers) for f, d in v.get("disputed", {}).items()]
    failures = 0
    for p in sub("logs").glob("failures-*.jsonl"):
        failures += len(p.read_text(encoding="utf-8").splitlines())
    return {"apps": n, "evidence_items": len(ev), "quotes_verified_first_pass_pct": ok(bev), "quotes_verified_final_pct": ok(ev),
            "second_pass_completed": sum(v.get("status") in ("agreed", "adjudicated") for v in vers),
            "agreed_without_dispute": sum(v.get("status") == "agreed" for v in vers),
            "apps_with_disputes": sum(v.get("status") == "adjudicated" for v in vers),
            "disputed_fields": len(disputed), "disputes_resolved_with_verified_quote": sum(d["resolved"] for _, _, d in disputed),
            "disputes_unresolved": sum(not d["resolved"] for _, _, d in disputed),
            "changed_by_adjudication": sum(d["changed_from_pass_A"] for _, _, d in disputed),
            "rule_fixes": sum(len(v.get("rule_fixes", [])) for v in vers),
            "low_confidence": [r["name"] for r in recs if r["confidence"] == "low"],
            "unclear": [r["name"] for r in recs if r["verdict"] == "unclear"],
            "research_failures_logged": failures,
            "models": sorted({r["model"] for r in recs} | {r["model"] for r in base.values()})}


def build():
    recs = pat.load_final()
    base = {}
    for p in sub("baseline").glob("*.json"):
        r = json.loads(p.read_text(encoding="utf-8"))
        base[r["id"]] = r
    changes_path = data_dir() / "changes.json"
    audit_path = sub("audit") / "summary.json"
    slim = []
    for r in recs:
        r = {k: v for k, v in r.items() if k not in ("searches", "sources_seen")}
        slim.append(r)
    payload = {"records": slim, "patterns": pat.compute(recs), "process": process_stats(recs, base),
               "changes": json.loads(changes_path.read_text(encoding="utf-8")) if changes_path.exists() else [],
               "audit": json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.exists() else None,
               "repo": env("ATLAS_REPO_URL", ""), "built": datetime.date.today().isoformat(),
               "enums": {"self_serve": schema.SELF_SERVE_HELP}}
    # Human-supported corrections: where the reviewer's documented value differs from the final data.
    # Tagged on the record; the final values and the scored accuracy numbers are NOT changed.
    aud = payload["audit"]
    if aud:
        seen = set()
        by_id = {r["id"]: r for r in slim}
        for e in aud["still_wrong"] + aud["broken_by_verification"]:
            k = (e["id"], e["field"])
            if k in seen or e["id"] not in by_id:
                continue
            seen.add(k)
            by_id[e["id"]].setdefault("human_corrected", {})[e["field"]] = {"final_value": e["final"], "human_value": e["human"], "source_note": e.get("note", "")}
    DOCS.mkdir(exist_ok=True)
    blob = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    (DOCS / "index.html").write_text(TEMPLATE.replace("__DATA__", blob), encoding="utf-8")
    (DOCS / "results.json").write_text(json.dumps(slim, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (DOCS / "patterns.json").write_text(json.dumps(payload["patterns"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with (DOCS / "results.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        cols = ["id", "name", "category", "auth", "self_serve", "api_styles", "mcp_status", "mcp_url", "verdict", "blocker", "confidence", "description", "gate_detail", "api_scope"]
        w.writerow(cols)
        for r in slim:
            w.writerow([";".join(r[c]) if isinstance(r[c], list) else (r[c] or "") for c in cols])
    return f"{DOCS / 'index.html'}  ({len(recs)} apps)"


TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Toolkit Atlas</title><meta name="description" content="100 apps researched by a Composio-powered agent, independently verified, with accuracy measured against a human audit.">
<style>
:root{--bg:#fbfbf8;--card:#fff;--ink:#1b2220;--mut:#5c6965;--line:#dfe3dd;--acc:#0e6b57;--acc2:#b45f06;--bad:#a8362e;--ok:#0e6b57;--chip:#eef1ec}
:root[data-theme=dark]{--bg:#121816;--card:#19211f;--ink:#e9eeeb;--mut:#9aa9a4;--line:#2a3532;--acc:#5ccfb0;--acc2:#f0a24a;--bad:#ff8a80;--ok:#5ccfb0;--chip:#222c29}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#121816;--card:#19211f;--ink:#e9eeeb;--mut:#9aa9a4;--line:#2a3532;--acc:#5ccfb0;--acc2:#f0a24a;--bad:#ff8a80;--ok:#5ccfb0;--chip:#222c29}}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--acc)}.wrap{max-width:1180px;margin:auto;padding:0 20px}header.top{position:sticky;top:0;background:color-mix(in srgb,var(--bg) 92%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--line);z-index:5}
header.top .wrap{display:flex;gap:18px;align-items:center;height:52px;overflow-x:auto;white-space:nowrap}header.top b{letter-spacing:.04em}header.top a{color:var(--mut);text-decoration:none;font-size:14px}header.top a:hover{color:var(--ink)}
.hero{padding:44px 0 8px}.eyebrow{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--acc);font-weight:700}h1{font-size:clamp(30px,5vw,52px);line-height:1.08;letter-spacing:-.03em;margin:10px 0 12px;max-width:900px}
.lede{color:var(--mut);max-width:760px;font-size:18px}.chips{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0}.chip{background:var(--chip);border:1px solid var(--line);border-radius:999px;padding:6px 14px;font-size:14px}.chip b{font-size:16px}
section{padding:36px 0;border-top:1px solid var(--line)}h2{font-size:26px;letter-spacing:-.02em;margin:0 0 6px}.sub{color:var(--mut);margin:0 0 20px;max-width:780px}
.heads{display:grid;gap:10px;margin:0 0 24px;padding:0;list-style:none}.heads li{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--acc);border-radius:8px;padding:12px 16px;font-size:17px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:16px}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px}.card h3{margin:0 0 12px;font-size:15px}
.row{display:grid;grid-template-columns:130px 1fr 46px;gap:10px;align-items:center;font-size:14px;margin:6px 0}.bar{height:12px;background:var(--chip);border-radius:6px;overflow:hidden;display:flex}.bar i{display:block;height:100%}.n{color:var(--mut);text-align:right}
.catrow{display:grid;grid-template-columns:minmax(120px,210px) 1fr 60px;gap:10px;align-items:center;font-size:13.5px;margin:7px 0}.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;color:var(--mut);margin-bottom:8px}.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px}
.c-instant{background:#0e6b57}.c-free_tier{background:#4aa58f}.c-trial{background:#97cdbd}.c-paid_plan{background:#e0a458}.c-approval{background:#c9733a}.c-sales{background:#a8362e}.c-unknown{background:#9aa09d}
.lists{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}.pill{display:inline-block;background:var(--chip);border:1px solid var(--line);border-radius:6px;padding:2px 8px;margin:3px 4px 3px 0;font-size:13px}
.controls{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 12px}input,select,button{font:inherit;font-size:14px;padding:9px 11px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)}input{flex:1;min-width:200px}button{cursor:pointer}button.p{background:var(--acc);color:#fff;border-color:var(--acc)}
.tw{overflow:auto;border:1px solid var(--line);border-radius:12px;background:var(--card);max-height:78vh}table{border-collapse:collapse;width:100%;font-size:14px}th{position:sticky;top:0;background:var(--chip);text-align:left;padding:10px;white-space:nowrap;z-index:1}td{padding:10px;border-top:1px solid var(--line);vertical-align:top}
tr.r{cursor:pointer}tr.r:hover{background:var(--chip)}.tag{display:inline-block;padding:2px 8px;border-radius:5px;font-size:12.5px;font-weight:600;white-space:nowrap}
.v-build_now{background:#d8f0e6;color:#0b5a46}.v-conditional{background:#fdeccf;color:#7a4a05}.v-needs_outreach{background:#f6dad7;color:#8a2a22}.v-unclear{background:#e4e6e3;color:#444}
:root[data-theme=dark] .v-build_now,:root:not([data-theme=light]) .v-build_now{}
tr.d td{background:var(--chip)}.ev{margin:6px 0;padding:6px 10px;border-left:3px solid var(--line);font-size:13.5px}.ev.ok{border-color:var(--ok)}.ev.bad{border-color:var(--bad)}.mut{color:var(--mut)}.small{font-size:13px}
.flow{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:14px 0}.step{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;position:relative}.step b{display:block;font-size:13px;color:var(--acc);letter-spacing:.05em;text-transform:uppercase}.step .who{font-size:12px;color:var(--mut);margin-top:6px}
.acc{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;margin:16px 0}.big{font-size:44px;font-weight:700;letter-spacing:-.03em;line-height:1}.big small{font-size:16px;font-weight:500;color:var(--mut)}
pre{background:var(--chip);border:1px solid var(--line);border-radius:8px;padding:12px;overflow:auto;font-size:13px}code{font-family:ui-monospace,Menlo,Consolas,monospace}
.note{border:1px solid var(--acc2);background:color-mix(in srgb,var(--acc2) 12%,var(--card));border-radius:10px;padding:12px 16px;margin:14px 0}footer{padding:30px 0 60px;color:var(--mut);font-size:14px;border-top:1px solid var(--line)}
@media(max-width:640px){.row{grid-template-columns:96px 1fr 38px}.catrow{grid-template-columns:110px 1fr 46px}td,th{padding:8px}.hide-s{display:none}}
@media print{header.top,.controls{display:none}.tw{max-height:none}}
.small,.small *{overflow-wrap:anywhere}
</style></head><body>
<header class="top"><div class="wrap"><b>TOOLKIT ATLAS</b><a href="#patterns">Patterns</a><a href="#matrix">Findings</a><a href="#agent">The agent</a><a href="#verify">Verification</a><a href="#run">Run it</a><a href="#agents">For agents</a><a href="#" id="theme" style="margin-left:auto">◐ theme</a></div></header>
<main class="wrap">
<div class="hero"><div class="eyebrow">Composio · AI Product Ops case study</div><h1 id="title">Which apps can become agent tools today?</h1>
<p class="lede">100 apps across 10 categories, researched by an agent built on the Composio SDK, checked by independent loops, and scored against a human audit. Evidence for every row; misses shown.</p><div class="chips" id="chips"></div></div>

<section id="patterns"><div class="eyebrow">The headline</div><h2>What the 100 apps tell us</h2><p class="sub">Computed from the data, not written by an LLM. Self-serve means a developer can get working credentials on their own; gated means a paid plan, an approval or review step, or sales is in the way.</p>
<ul class="heads" id="heads"></ul>
<div class="grid"><div class="card"><h3>Authentication methods (apps supporting each)</h3><div id="authbars"></div></div>
<div class="card"><h3>Main blocker among non-green apps</h3><div id="blockbars"></div></div>
<div class="card"><h3>Buildability verdict</h3><div id="verdictbars"></div><p class="small mut" style="margin-top:14px">build now = documented path, no external gate · conditional = plan/admin/config dependency · needs outreach = approval, partner or sales gate</p></div></div>
<div class="card" style="margin-top:16px"><h3>Self-serve vs gated, by category</h3><div class="legend" id="sslegend"></div><div id="catbars"></div></div>
<div class="lists" style="margin-top:16px"><div class="card"><h3>Easy wins: build this week</h3><div id="easy"></div></div><div class="card"><h3>Needs outreach first</h3><div id="outreach" class="small"></div></div></div></section>

<section id="matrix"><div class="eyebrow">The evidence</div><h2>Findings matrix</h2><p class="sub">Click a row for the access detail, quoted evidence (machine-checked against the fetched page) and how each field was verified.</p>
<div class="controls"><input id="q" placeholder="Search apps, auth, blockers…" aria-label="Search"><select id="fc" aria-label="Category"><option value="">All categories</option></select><select id="fv" aria-label="Verdict"><option value="">All verdicts</option><option value="build_now">Build now</option><option value="conditional">Conditional</option><option value="needs_outreach">Needs outreach</option><option value="unclear">Unclear</option></select><select id="fa" aria-label="Access"><option value="">All access</option></select><button id="dl" class="p">Download JSON</button></div>
<p class="mut small" id="count" aria-live="polite"></p><div class="tw"><table><thead><tr><th>#</th><th>App</th><th>Auth</th><th>Self-serve?</th><th class="hide-s">API</th><th class="hide-s">MCP</th><th>Verdict</th><th>Main blocker</th><th class="hide-s">Conf.</th></tr></thead><tbody id="rows"></tbody></table></div></section>

<section id="agent"><div class="eyebrow">The agent</div><h2>How the research was done</h2><p class="sub">Code does retrieval and checking; the LLM only reads and classifies. That keeps cost at $0 on free tiers, works with any model, and stops the model from inventing evidence.</p>
<div class="flow"><div class="step"><b>1 Search</b>3 web-search queries per app (keyless search; Composio's search tools were restricted for the free key).<div class="who">Code</div></div>
<div class="step"><b>2 Fetch</b>Rank official docs first, fetch pages safely, cache them.<div class="who">Code</div></div>
<div class="step"><b>3 Extract</b>An agent reads the pages and returns structured JSON with verbatim quotes (file handoff; any model or LLM API also works).<div class="who">Agent (Claude)</div></div>
<div class="step"><b>4 Ground</b>Every quote is searched for in the cached page. No match, no credit.<div class="who">Code</div></div>
<div class="step"><b>5 Blind recheck</b>Second pass: different queries, separate context, never shown pass 1. Plus Composio's toolkit catalog as an independent auth cross-check.<div class="who">Agent + Composio SDK</div></div>
<div class="step"><b>6 Adjudicate</b>Only disputed fields, with both sides’ evidence; a change needs a verified quote.<div class="who">LLM + Code</div></div>
<div class="step"><b>7 Human audit</b>Unlabelled values judged against the docs; accuracy scored.<div class="who">Human</div></div></div>
<div class="grid"><div class="card"><h3>Where a human was needed</h3><ul id="humans" class="small" style="padding-left:18px;margin:0"></ul></div><div class="card"><h3>What the agent got wrong or could not do</h3><ul id="agentmiss" class="small" style="padding-left:18px;margin:0"></ul></div></div></section>

<section id="verify"><div class="eyebrow">The proof</div><h2>Verification: how accurate is it?</h2><p class="sub" id="vsub"></p><div class="acc" id="accbox"></div><div class="grid"><div class="card"><h3>Automated loops</h3><div id="loops" class="small"></div></div><div class="card"><h3>Human audit: hits and misses</h3><div id="misses" class="small"></div></div></div>
<div class="note small"><b>Honest limits.</b> Docs review is not an authenticated API test. A small sample gives a wide interval. Agent loops can share blind spots; that is why a human judged the sample. “Not found” means not found in what was searched, not proof of absence.</div></section>

<section id="run"><div class="eyebrow">Runnable</div><h2>Run the agent yourself</h2><p class="sub">Free: Composio Hobby plan (no card) and a free LLM key (Gemini, Groq, or local Ollama).</p>
<pre><code>pip install -r requirements.txt
cp .env.example .env        # add COMPOSIO_API_KEY and one LLM key
python -m atlas doctor      # 30-second check of keys, search, LLM
python -m atlas research --ids 1-5    # try 5 apps
python -m atlas research              # all 100, both passes
python -m atlas reconcile &amp;&amp; python -m atlas patterns &amp;&amp; python -m atlas build</code></pre>
<p>Swap models with one line: <code>ATLAS_MODEL=groq/llama-3.3-70b-versatile</code> (or <code>ollama/…</code>, <code>openrouter/…</code>, <code>anthropic/…</code>). The repo also has a GitHub Actions button (manual dispatch) that runs a chosen batch. <span id="repo"></span></p></section>

<section id="agents"><div class="eyebrow">For agents</div><h2>Machine-readable</h2><p class="sub">Same data as the table, no scraping needed.</p>
<p><a href="results.json">results.json</a> (full records with evidence quotes) · <a href="results.csv">results.csv</a> · <a href="patterns.json">patterns.json</a>. Enums: self_serve ∈ instant | free_tier | trial | paid_plan | approval | sales | unknown; verdict ∈ build_now | conditional | needs_outreach | unclear. This page embeds the same JSON in <code>&lt;script id="dataset" type="application/json"&gt;</code>.</p></section>
</main><footer><div class="wrap"><span id="foot"></span></div></footer>
<script id="dataset" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('dataset').textContent),R=D.records,P=D.patterns,X=D.process,A=D.audit;
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),lab=s=>String(s).replace(/_/g,' ');
const safe=u=>/^https:\/\//.test(u)?esc(u):'#';const th=document.documentElement;
try{const t=localStorage.getItem('atlas-theme');if(t)th.dataset.theme=t}catch(e){}
$('#theme').onclick=e=>{e.preventDefault();const t=(th.dataset.theme||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'))==='dark'?'light':'dark';th.dataset.theme=t;try{localStorage.setItem('atlas-theme',t)}catch(e){}};
const n=R.length;
const acc=A?A.overall:null;
$('#chips').innerHTML=[`<span class=chip><b>${n}</b> apps · ${new Set(R.map(r=>r.category)).size} categories</span>`,
`<span class=chip><b>${P.verdict.build_now||0}</b> build-now</span>`,`<span class=chip><b>${P.mcp.official||0}</b> official MCP servers</span>`,P.composio_covered!==undefined&&R.some(r=>r.catalog)?`<span class=chip><b>${P.composio_covered}</b> already in Composio</span>`:'',
acc&&acc.resolved?`<span class=chip>Accuracy on audited sample: <b>${Math.round(acc.baseline_accuracy*100)}% → ${Math.round(acc.final_accuracy*100)}%</b></span>`:`<span class=chip>Human audit: <b>pending</b></span>`,
`<span class=chip>Models: ${esc(X.models.join(', '))}</span>`].join('');
if(n<100)$('#title').insertAdjacentHTML('afterend',`<div class=note><b>Work in progress:</b> ${n} of 100 apps assembled so far.</div>`);
$('#heads').innerHTML=P.headlines.map(h=>`<li>${esc(h)}</li>`).join('');
function bars(el,obj,total,cls){const e=Object.entries(obj).sort((a,b)=>b[1]-a[1]);$(el).innerHTML=e.map(([k,v])=>`<div class=row><span>${esc(lab(k))}</span><div class=bar><i style="width:${100*v/Math.max(total,1)}%;background:${cls||'var(--acc)'}"></i></div><span class=n>${v}</span></div>`).join('')||'<span class=mut>No data yet</span>'}
bars('#authbars',P.auth,n);bars('#blockbars',P.blockers,n,'var(--acc2)');
$('#verdictbars').innerHTML=['build_now','conditional','needs_outreach','unclear'].map(k=>`<div class=row><span>${lab(k)}</span><div class=bar><i class="" style="width:${100*(P.verdict[k]||0)/Math.max(n,1)}%;background:${{build_now:'#0e6b57',conditional:'#e0a458',needs_outreach:'#a8362e',unclear:'#9aa09d'}[k]}"></i></div><span class=n>${P.verdict[k]||0}</span></div>`).join('');
const SS=['instant','free_tier','trial','paid_plan','approval','sales','unknown'];
$('#sslegend').innerHTML=SS.map(k=>`<span title="${esc(D.enums.self_serve[k])}"><i class="c-${k}"></i>${lab(k)}</span>`).join('');
$('#catbars').innerHTML=Object.entries(P.by_category).map(([c,v])=>`<div class=catrow><span>${esc(c)}</span><div class=bar title="${esc(JSON.stringify(v.self_serve))}">${SS.map(k=>`<i class="c-${k}" style="width:${100*(v.self_serve[k]||0)/v.n}%"></i>`).join('')}</div><span class=n>${v.gated}/${v.n} gated</span></div>`).join('');
$('#easy').innerHTML=P.easy_wins.map(a=>`<span class=pill title="${esc(a.category+' · '+a.auth.join(', '))}">${esc(a.name)}</span>`).join('')||'<span class=mut>None yet</span>';
$('#outreach').innerHTML=P.needs_outreach.map(a=>`<div style="margin:6px 0"><b>${esc(a.name)}</b> <span class=mut>— ${esc(lab(a.blocker))}: ${esc(a.detail)}</span></div>`).join('')||'<span class=mut>None</span>';
// matrix
[...new Set(R.map(r=>r.category))].forEach(c=>$('#fc').insertAdjacentHTML('beforeend',`<option>${esc(c)}</option>`));
SS.forEach(k=>$('#fa').insertAdjacentHTML('beforeend',`<option value="${k}">${lab(k)}</option>`));
const open=new Set();
function ver(r){const v=r.verification||{};const parts=[];parts.push(`Second pass: <b>${esc(lab(v.status||'n/a'))}</b>${v.blind_model?' ('+esc(v.blind_model)+')':''}`);
Object.entries(v.disputed||{}).forEach(([f,d])=>parts.push(`Disputed <code>${f}</code>: A=${esc(JSON.stringify(d.pass_A))} vs B=${esc(JSON.stringify(d.pass_B))} → <b>${esc(JSON.stringify(d.final))}</b> ${d.resolved?'(verified quote)':'<span style="color:var(--bad)">(unresolved)</span>'}`));
(v.rule_fixes||[]).forEach(x=>parts.push('Rule fix: '+esc(x.rule)));return parts.join('<br>')}
function render(){const q=$('#q').value.toLowerCase(),c=$('#fc').value,v=$('#fv').value,a=$('#fa').value;
const f=R.filter(r=>(!c||r.category===c)&&(!v||r.verdict===v)&&(!a||r.self_serve===a)&&(!q||JSON.stringify([r.name,r.description,r.auth,r.blocker,r.blocker_detail,r.api_scope]).toLowerCase().includes(q)));
$('#count').textContent=`Showing ${f.length} of ${n} apps`;
$('#rows').innerHTML=f.map(r=>{const o=open.has(r.id);let h=`<tr class=r data-id=${r.id} tabindex=0 aria-expanded=${o}><td class=mut>${r.id}</td><td><b>${esc(r.name)}</b><div class="mut small">${esc(r.description)}</div></td><td>${r.auth.map(esc).join(', ')}</td><td><span title="${esc(D.enums.self_serve[r.self_serve]||'')}">${lab(r.self_serve)}</span></td><td class=hide-s>${r.api_styles.map(esc).join(', ')}</td><td class=hide-s>${lab(r.mcp_status)}</td><td><span class="tag v-${r.verdict}">${lab(r.verdict)}</span></td><td>${esc(lab(r.blocker))}</td><td class=hide-s>${esc(r.confidence)}</td></tr>`;
if(o)h+=`<tr class=d><td></td><td colspan=8>${r.human_corrected?`<p><b>Human audit disagrees with the data below:</b> ${Object.entries(r.human_corrected).map(([f,v])=>esc(f)+': data says '+esc(Array.isArray(v.final_value)?v.final_value.join(', '):String(v.final_value))+', reviewer says '+esc(Array.isArray(v.human_value)?v.human_value.join(', '):String(v.human_value))).join('; ')}</p>`:''}<p><b>Access:</b> ${esc(r.gate_detail)}</p><p><b>API:</b> ${esc(r.api_scope)} ${r.webhooks!=='unknown'?'· webhooks: '+r.webhooks:''} ${r.sandbox!=='unknown'?'· sandbox: '+r.sandbox:''}</p><p><b>MCP:</b> ${esc(r.mcp_notes||lab(r.mcp_status))} ${r.mcp_url?`<a href="${safe(r.mcp_url)}" target=_blank rel=noopener>${esc(r.mcp_url)}</a>`:''}</p><p><b>Blocker:</b> ${esc(r.blocker_detail)}</p>
${r.catalog?`<p><b>Composio catalog:</b> ${r.catalog.toolkit?`toolkit <code>${esc(r.catalog.toolkit)}</code> (${r.catalog.tools_count} tools; auth ${esc((r.catalog.schemes||[]).join(', '))}) · agreement with our auth finding: <b>${esc(lab(r.catalog.auth_agreement))}</b>`:'no toolkit yet'}</p>`:''}
${r.evidence.map(e=>`<div class="ev ${e.quote_match==='missing'?'bad':'ok'}"><a href="${safe(e.url)}" target=_blank rel=noopener>${esc(e.url)}</a> <span class=mut>[${esc((e.supports||[]).join(', '))}]</span><br>“${esc(e.quote)}” <span class=mut>— quote ${e.quote_match==='exact'?'found verbatim':e.quote_match==='fuzzy'?'found (near-verbatim)':'NOT found on page'}</span></div>`).join('')}
<p class=small>${ver(r)}</p>${(r.issues||[]).length?`<p class="small mut"><b>Caveats:</b> ${r.issues.map(esc).join(' · ')}</p>`:''}<p class="small mut">Confidence: ${esc(r.confidence)} · checked ${esc(r.checked_at)} · ${esc(r.model)}</p></td></tr>`;return h}).join('')}
$('#rows').addEventListener('click',e=>{const t=e.target.closest('tr.r');if(!t||e.target.closest('a'))return;const id=+t.dataset.id;open.has(id)?open.delete(id):open.add(id);render()});
$('#rows').addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){const t=e.target.closest('tr.r');if(t){e.preventDefault();t.click()}}});
['#q','#fc','#fv','#fa'].forEach(s=>$(s).addEventListener('input',render));render();
$('#dl').onclick=()=>{const u=URL.createObjectURL(new Blob([JSON.stringify(R,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download='toolkit-atlas.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};
// agent section
const hs=['Created the Composio account and the free LLM key (credentials cannot be automated).'];
hs.push(A?`Judged ${A.received_judgments} field-level answers against vendor documentation (audit by ${esc(A.reviewer)}).`:'Human audit of a sample against vendor documentation: pending.');
if(X.low_confidence.length)hs.push(`Apps still low-confidence after both passes (${X.low_confidence.length}): ${esc(X.low_confidence.join(', '))}. These need a person to open the docs.`);
if(X.unclear.length)hs.push(`Verdict left “unclear” rather than guessed (${X.unclear.length}): ${esc(X.unclear.join(', '))}.`);
$('#humans').innerHTML=hs.map(x=>`<li>${x}</li>`).join('');
const miss=[];if(X.research_failures_logged)miss.push(`${X.research_failures_logged} app runs failed (no usable sources, or model output invalid) and were retried or left missing; nothing was fabricated.`);
if(X.disputes_unresolved)miss.push(`${X.disputes_unresolved} field disagreements between passes could not be settled with a verified quote and are flagged in the matrix.`);
if(A&&A.still_wrong.length)miss.push(`${A.still_wrong.length} audited fields are still wrong in the final data (listed under hits and misses).`);
$('#agentmiss').innerHTML=(miss.length?miss:['See the verification section: misses are listed there once the human audit is complete.']).map(x=>`<li>${x}</li>`).join('');
// verification
$('#vsub').textContent=A?`Same sample, same reviewer: what the first pass got right versus what the final, verified data gets right. ${A.method}`:'The human audit has not been recorded yet, so no accuracy percentage is claimed. The automated loops below are real but are not a substitute for it.';
const pc=x=>x==null?'n/a':Math.round(x*100)+'%',ci=x=>x?` <span class=mut small>(95% CI ${Math.round(x[0]*100)}–${Math.round(x[1]*100)}%)</span>`:'';
$('#accbox').innerHTML=A?[['First pass',A.overall.baseline_accuracy,A.overall.baseline_ci95,A.overall.baseline_correct],['After verification loops',A.overall.final_accuracy,A.overall.final_ci95,A.overall.final_correct]].map(([t,v,c,k])=>`<div class=card><h3>${t}</h3><div class=big>${pc(v)}</div><div class="mut small">${k} of ${A.overall.resolved} resolved fields correct${ci(c)}</div></div>`).join('')+`<div class=card><h3>Breakdown</h3><div class=small>Random sample: ${pc(A.random_sample.baseline_accuracy)} → ${pc(A.random_sample.final_accuracy)} (${A.random_sample.resolved} fields)<br>Hard cases: ${pc(A.hard_cases.baseline_accuracy)} → ${pc(A.hard_cases.final_accuracy)} (${A.hard_cases.resolved} fields)<br>Unsure (excluded): ${A.overall.unsure}</div></div>`:`<div class=card><h3>Accuracy</h3><div class=big>pending</div><div class="mut small">Not claimed until a person has judged the sample.</div></div>`;
const p=x=>x==null?'n/a':x+'%';
$('#loops').innerHTML=`<p><b>1. Quote grounding.</b> ${p(X.quotes_verified_first_pass_pct)} of first-pass evidence quotes were found on the fetched page; ${p(X.quotes_verified_final_pct)} after verification (${X.evidence_items} items).</p>
<p><b>2. Blind second pass.</b> ${X.second_pass_completed} apps got an independent recheck; ${X.agreed_without_dispute} agreed outright, ${X.apps_with_disputes} had at least one disagreement.</p>
<p><b>3. Adjudication.</b> ${X.disputed_fields} disputed fields: ${X.disputes_resolved_with_verified_quote} settled with a verified quote (${X.changed_by_adjudication} changed the first-pass answer), ${X.disputes_unresolved} left flagged.</p>
<p><b>4. Consistency rules.</b> ${X.rule_fixes} verdicts corrected because they contradicted the access finding.</p><p><b>5. Human audit.</b> ${A?'Complete for the sample.':'Pending.'}</p>`;
const row=r=>`<div style="margin:5px 0"><b>${esc(r.name)}</b> · <code>${r.field}</code>: first pass ${esc(JSON.stringify(r.baseline))}, final ${esc(JSON.stringify(r.final))}, human ${esc(JSON.stringify(r.human))}${r.note?' <span class=mut>— '+esc(r.note)+'</span>':''}</div>`;
$('#misses').innerHTML=A?`<p><b>Fixed by the loops (${A.fixed_by_verification.length})</b></p>${A.fixed_by_verification.map(row).join('')||'<span class=mut>none</span>'}<p><b>Made worse (${A.broken_by_verification.length})</b></p>${A.broken_by_verification.map(row).join('')||'<span class=mut>none</span>'}<p><b>Still wrong in the final data (${A.still_wrong.length})</b></p>${A.still_wrong.map(row).join('')||'<span class=mut>none</span>'}`:'<span class=mut>Shown here once the audit is recorded.</span>';
$('#repo').innerHTML=D.repo?`Source: <a href="${safe(D.repo)}">${esc(D.repo)}</a>`:'';
$('#foot').textContent=`Research snapshot ${D.built}. Evidence links are per app. Verdicts are documentation-based assessments, not authenticated integration tests.`;
</script></body></html>"""
