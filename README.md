# Toolkit Atlas

Research pipeline for the Composio AI Product Ops take-home. For 100 apps in 10 categories it finds the auth methods, whether API access is
self-serve or gated, the API surface, any MCP server, a buildability verdict and the evidence. It then verifies itself and publishes one
self-explanatory page (`docs/index.html`, with `results.json`, `results.csv`, `patterns.json` beside it).

**Cost: $0 and no LLM API key.** Needs a free Composio key (for the catalog cross-check and the MCP/session demo). In the original run the "LLM step"
was done by Claude Sonnet 5.5 through Claude Code using file handoff (below). A reviewer can swap in any agent or model.

## How it works
```
search (keyless ddgs) -> fetch + cache pages (local, SSRF-guarded) -> agent writes JSON with verbatim quotes
 -> code checks every quote against the cached page and validates the schema
 -> blind second pass on risky apps -> adjudicate disputed fields -> retry weak apps -> rule checks
 -> Composio catalog cross-check -> human audit -> scoring -> patterns -> page
```
The agent never browses and cannot invent evidence: a quote that is not on the fetched page earns no credit. Patterns and headline numbers are computed in code.

## Reproduce (Python 3.10+)
```
pip install -r requirements.txt
copy .env.example .env                     # (cp on mac/linux); add COMPOSIO_API_KEY only
python -m atlas doctor                     # checks key, search, page fetch, MCP endpoint
python -m atlas research --phase primary   # retrieval + prompts in data/handoff/; answer them (see below), re-run until all 100 done
python -m atlas catalog                    # cross-check against Composio's toolkit catalog
python -m atlas research --phase blind --select uncertain   # independent second pass on risky apps only (31 in our run)
python -m atlas reconcile                  # adjudicate disagreements (answer adjudicate-*.prompt.md, re-run)
python -m atlas retry                      # third pass on still-uncertain apps, then run reconcile again
python -m atlas patterns
python -m atlas audit-prep                 # builds data/audit/audit.html for the human review
python -m atlas audit-score human-audit.json
python -m atlas build                      # writes docs/index.html + results.json/csv
python -m unittest discover -s tests       # offline tests, no keys needed
```
`python -m atlas status` shows progress; re-running skips finished apps (`--force` redoes them).

## Plug in your own agent
`ATLAS_MODEL=handoff` (default in `.env.example`): the pipeline does retrieval and writes `data/handoff/<key>.prompt.md`; any agent or person writes
`<key>.answer.json` next to it; re-run the command and the code grounds every quote and validates the schema. Keys: `primary-NNN`, `blind-NNN`,
`adjudicate-NNN`, `retry-NNN`. For fully automated runs set `ATLAS_MODEL` to any LiteLLM model string (`pip install -r requirements-optional.txt`).
Sources are saved in `data/sources/` so the answerer and the checker see the same pages.

## Composio usage
- **SDK:** `toolkits` list used for the catalog cross-check (`data/catalog_match.json`): match / partial / disagree / no_toolkit per app.
- **MCP / session:** `doctor` requests a session's hosted MCP endpoint (`create(..., mcp=True)`).
- Composio's web-search tools were restricted for our key, so search uses keyless `ddgs` (`ATLAS_SEARCH_BACKEND=ddg`); set it to `composio` if your key allows search.

## Results and honest limits
- **Human audit (18 apps, 72 field judgments, 68 resolved, 4 "unsure" excluded):** first pass 73.5% (95% CI 62-83%), after verification 75.0% (64-84%).
  The intervals overlap: verification did **not** clearly improve overall accuracy. Verdict improved (71% to 82%); auth got worse (67% to 61%).
  The loops fixed 8 fields and broke 7; 17 audited fields are still wrong. Details are on the page and in `data/audit/summary.json`.
- The audit sample is small, and 8 of the 18 apps were deliberately hard cases, so it is not a population estimate. Only 31 apps got a blind second pass; 69 did not.
- Human-supported corrections are tagged `human_corrected` in `results.json` (13 apps). The final values and the scored numbers were not edited.
- Documentation review is not an authenticated API test; "self-serve" and "build-now" are judgments from public docs and can be out of date.
- Where sources did not establish auth or access, the record says `Other` / `unknown` with low confidence instead of guessing.
- The reviewer picked among candidate values shown unlabelled; it was one person.
- Raw per-app data: `data/baseline` (first pass), `data/verify` (blind pass), `data/retry`, `data/final`, `data/changes.json` (key-field changes first pass to final).

`.github/workflows/tests.yml` runs the offline tests on every push.
