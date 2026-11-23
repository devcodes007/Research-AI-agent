"""Human audit: sample selection, a self-contained review page, and honest scoring.

The reviewer sees candidate values WITHOUT labels saying which pass produced them, picks the correct one from the
documentation, and the scorer then measures first-pass vs final accuracy against the human's answers.
"""
import json
import math
from pathlib import Path
import random

from . import schema
from .config import sub

REVIEWER_PAGE = r"""<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Toolkit Atlas · human audit</title><style>
:root{--bg:#fafaf7;--ink:#1c2321;--mut:#5d6a66;--line:#dcdfd8;--acc:#0f6b57;--card:#fff}
@media(prefers-color-scheme:dark){:root{--bg:#141a18;--ink:#e8ece9;--mut:#9aa8a3;--line:#2a3430;--acc:#5fcfb2;--card:#1b2321}}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}main{max-width:900px;margin:auto;padding:20px}
h1{font-size:22px}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:14px 0}
.item{border-top:1px solid var(--line);padding-top:12px;margin-top:12px}label{display:block;margin:4px 0}code{background:rgba(127,127,127,.15);padding:1px 5px;border-radius:4px}
blockquote{margin:6px 0;padding:4px 10px;border-left:3px solid var(--acc);color:var(--mut)}a{color:var(--acc)}
.bar{position:sticky;top:0;background:var(--bg);padding:10px 0;border-bottom:1px solid var(--line);z-index:2}button{font:inherit;padding:8px 14px;border-radius:7px;border:1px solid var(--acc);background:var(--acc);color:#fff;cursor:pointer}
input[type=text],select{font:inherit;padding:6px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink)}.done{opacity:.6}
</style><main><h1>Human audit</h1><p>For each field, open the evidence link(s) (or the vendor docs), then choose the value that the documentation actually supports. Values are unlabelled on purpose. Choose <b>Unsure</b> if you cannot tell; that is reported honestly, not counted as correct. Your answers autosave in this browser.</p>
<div class=bar><input id=who type=text placeholder="Your name" size=24> <span id=prog></span> <button id=exp>Download human-audit.json</button></div><div id=app></div></main>
<script id=data type=application/json>__DATA__</script><script>
const D=JSON.parse(document.getElementById('data').textContent);const K='atlas-audit-v1';let S={};try{S=JSON.parse(localStorage.getItem(K)||'{}')}catch(e){}
const save=()=>{try{localStorage.setItem(K,JSON.stringify(S))}catch(e){}};const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function opt(v){return Array.isArray(v)?v.join(' + '):String(v)}
function render(){let h='';D.items.forEach((app,ai)=>{h+=`<div class=card><b>#${app.id} ${esc(app.name)}</b> <span style="color:var(--mut)">${esc(app.category)}</span><p style="color:var(--mut)">${esc(app.description)}</p>
<details><summary>Evidence the agent gathered (${new Set(app.evidence.map(e=>e.url)).size} sources)</summary>${(()=>{const g={};app.evidence.forEach(e=>{(g[e.url]=g[e.url]||[]).push(e.quote)});return Object.entries(g).map(([u,qs])=>`<blockquote><a href="${esc(u)}" target=_blank rel=noopener>${esc(u)}</a>${qs.map(q=>`<br>${esc(q)}`).join('')}</blockquote>`).join('')})()}</details>`;
app.fields.forEach(f=>{const k=app.id+':'+f.field,s=S[k]||{};h+=`<div class="item ${s.choice?'done':''}"><b><code>${f.field}</code></b> ${f.field=='self_serve'?'<span style="color:var(--mut)">(what must a developer do to get working credentials?)</span>':''}`;
f.options.forEach((o,i)=>{h+=`<label><input type=radio name="${k}" value="o${i}" ${s.choice=='o'+i?'checked':''} onchange="pick('${k}','o${i}',${ai},'${f.field}')"> ${esc(opt(o))}</label>`});
h+=`<label><input type=radio name="${k}" value=other ${s.choice=='other'?'checked':''} onchange="pick('${k}','other',${ai},'${f.field}')"> None of these - the correct value is: ${otherCtl(k,f,s)}</label>
<label><input type=radio name="${k}" value=unsure ${s.choice=='unsure'?'checked':''} onchange="pick('${k}','unsure',${ai},'${f.field}')"> Unsure / docs unclear</label>
<input type=text placeholder="note or URL you checked" value="${esc(s.note||'')}" size=60 oninput="note('${k}',this.value)"></div>`});h+='</div>'});$('#app').innerHTML=h;prog()}
function otherCtl(k,f,s){const vals=D.enums[f.field],multi=D.multi.includes(f.field),cur=s.other||(multi?[]:'');
if(multi)return vals.map(v=>`<label style="display:inline-block;margin-right:8px"><input type=checkbox ${cur.includes(v)?'checked':''} onchange="chk('${k}','${v}',this.checked)"> ${esc(v)}</label>`).join('');
return `<select onchange="setOther('${k}',this.value)"><option value="">choose...</option>${vals.map(v=>`<option ${cur==v?'selected':''}>${esc(v)}</option>`).join('')}</select>`}
function pick(k,c){S[k]=Object.assign(S[k]||{},{choice:c});save();render()}
function setOther(k,v){S[k]=Object.assign(S[k]||{},{other:v});save()}
function chk(k,v,on){const s=S[k]=S[k]||{};s.other=s.other||[];s.other=on?[...new Set([...s.other,v])]:s.other.filter(x=>x!==v);save()}
function note(k,v){S[k]=Object.assign(S[k]||{},{note:v});save()}
function prog(){const total=D.items.reduce((a,x)=>a+x.fields.length,0),done=Object.values(S).filter(s=>s.choice).length;$('#prog').textContent=done+' / '+total+' judged'}
$('#who').value=S._who||'';$('#who').oninput=e=>{S._who=e.target.value;save()};
$('#exp').onclick=()=>{const out={reviewer:$('#who').value.trim(),reviewed_at:new Date().toISOString(),judgments:[]};
D.items.forEach(app=>app.fields.forEach(f=>{const s=S[app.id+':'+f.field];if(!s||!s.choice)return;let j={app_id:app.id,field:f.field,note:s.note||''};
if(s.choice=='unsure')j.status='unsure';else if(s.choice=='other'){j.status='answered';j.correct=s.other}else{j.status='answered';j.correct=f.options[+s.choice.slice(1)]}out.judgments.push(j)}));
const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(out,null,2)],{type:'application/json'}));a.download='human-audit.json';a.click()};
render();</script></html>"""


def _key(value):
    return tuple(sorted(value)) if isinstance(value, list) else value


def pick_sample(base, final, seed=2026, per_category=1, hard=8):
    """Stratified random sample (one per category) plus the hardest cases (most disagreement / lowest confidence)."""
    rnd = random.Random(seed)
    ids = sorted(final)
    by_cat = {}
    for i in ids:
        by_cat.setdefault(final[i]["category"], []).append(i)
    chosen = []
    for cat in sorted(by_cat):
        chosen += rnd.sample(by_cat[cat], min(per_category, len(by_cat[cat])))

    def difficulty(i):
        v = final[i].get("verification", {})
        return (len(v.get("disputed", {})), final[i]["confidence"] == "low", -i)
    rest = sorted((i for i in ids if i not in chosen), key=difficulty, reverse=True)[:hard]
    # 10 random + 8..10 hard. Reported separately so hard cases do not flatter or punish the headline accuracy.
    return {"random": chosen, "hard": rest}


def prepare(log=print):
    base = {json.loads(p.read_text(encoding="utf-8"))["id"]: json.loads(p.read_text(encoding="utf-8")) for p in sub("baseline").glob("*.json")}
    final = {json.loads(p.read_text(encoding="utf-8"))["id"]: json.loads(p.read_text(encoding="utf-8")) for p in sub("final").glob("*.json")}
    sample = pick_sample(base, final)
    items = []
    rnd = random.Random(7)
    for kind in ("random", "hard"):
        for i in sample[kind]:
            f, b = final[i], base.get(i, final[i])
            fields = []
            for field in schema.AUDIT_FIELDS:
                options = []
                for v in (b.get(field), f.get(field)):
                    if _key(v) not in [_key(o) for o in options]:
                        options.append(v)
                rnd.shuffle(options)
                fields.append({"field": field, "options": options})
            items.append({"id": i, "name": f["name"], "category": f["category"], "description": f["description"],
                          "evidence": [{"url": e["url"], "quote": e["quote"]} for e in (f["evidence"] + b["evidence"])][:8], "fields": fields})
    out_dir = sub("audit")
    (out_dir / "sample.json").write_text(json.dumps({"seed": 2026, **sample}, indent=2) + "\n", encoding="utf-8")
    payload = json.dumps({"items": items, "enums": {**{k: v for k, v in schema.ENUMS.items()}, **schema.LISTS},
                          "multi": sorted(schema.MULTI_FIELDS)}, ensure_ascii=False).replace("<", "\\u003c")
    (out_dir / "audit.html").write_text(REVIEWER_PAGE.replace("__DATA__", payload), encoding="utf-8")
    log(f"audit page: {out_dir / 'audit.html'}  ({len(items)} apps, {sum(len(i['fields']) for i in items)} judgments)")
    return sample


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - m) / d, 3), round((c + m) / d, 3)]


def score(path, log=print):
    audit = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not str(audit.get("reviewer", "")).strip():
        raise ValueError("reviewer name is required in the audit file")
    sample = json.loads((sub("audit") / "sample.json").read_text(encoding="utf-8"))
    kinds = {i: "random" for i in sample["random"]} | {i: "hard" for i in sample["hard"]}
    base = {}
    final = {}
    for folder, store in (("baseline", base), ("final", final)):
        for p in sub(folder).glob("*.json"):
            r = json.loads(p.read_text(encoding="utf-8"))
            store[r["id"]] = r
    rows, seen = [], set()
    for j in audit["judgments"]:
        key = (j["app_id"], j["field"])
        if key in seen or j["app_id"] not in kinds or j["field"] not in schema.AUDIT_FIELDS:
            raise ValueError(f"invalid or duplicate judgment {key}")
        seen.add(key)
        row = {"id": j["app_id"], "name": final[j["app_id"]]["name"], "field": j["field"], "kind": kinds[j["app_id"]],
               "baseline": base[j["app_id"]][j["field"]], "final": final[j["app_id"]][j["field"]], "note": j.get("note", ""), "status": j["status"]}
        if j["status"] == "answered":
            row["human"] = j["correct"]
            row["baseline_ok"] = _key(row["baseline"]) == _key(j["correct"])
            row["final_ok"] = _key(row["final"]) == _key(j["correct"])
        rows.append(row)

    def stats(rs):
        resolved = [r for r in rs if r["status"] == "answered"]
        b, f = sum(r["baseline_ok"] for r in resolved), sum(r["final_ok"] for r in resolved)
        return {"judged": len(rs), "unsure": len(rs) - len(resolved), "resolved": len(resolved),
                "baseline_correct": b, "final_correct": f,
                "baseline_accuracy": round(b / len(resolved), 3) if resolved else None,
                "final_accuracy": round(f / len(resolved), 3) if resolved else None,
                "baseline_ci95": wilson(b, len(resolved)), "final_ci95": wilson(f, len(resolved))}
    summary = {"reviewer": audit["reviewer"], "reviewed_at": audit.get("reviewed_at"), "overall": stats(rows),
               "random_sample": stats([r for r in rows if r["kind"] == "random"]),
               "hard_cases": stats([r for r in rows if r["kind"] == "hard"]),
               "by_field": {f: stats([r for r in rows if r["field"] == f]) for f in schema.AUDIT_FIELDS},
               "fixed_by_verification": [r for r in rows if r["status"] == "answered" and not r["baseline_ok"] and r["final_ok"]],
               "broken_by_verification": [r for r in rows if r["status"] == "answered" and r["baseline_ok"] and not r["final_ok"]],
               "still_wrong": [r for r in rows if r["status"] == "answered" and not r["final_ok"]],
               "expected_judgments": (len(sample["random"]) + len(sample["hard"])) * len(schema.AUDIT_FIELDS), "received_judgments": len(rows),
               "method": "Reviewer saw unlabelled candidate values and chose the documented one. random_sample is a seeded stratified "
                         "random draw (1 app per category); hard_cases are the apps with the most pass disagreement. Small sample: see CI."}
    (sub("audit") / "human-audit.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (sub("audit") / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log(json.dumps(summary["overall"], indent=2))
    return summary
