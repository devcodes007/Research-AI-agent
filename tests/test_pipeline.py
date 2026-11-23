"""Offline end-to-end tests: fake search, fake pages, fake LLM. No network, no keys, no cost."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["ATLAS_DATA"] = tempfile.mkdtemp()

from atlas import audit, llm, reconcile, research, retrieve, schema, seed  # noqa: E402

PAGE = ("To use the Acme API create an API key in Settings. API keys are available on the free plan. "
        "OAuth 2.0 is supported for public apps. Acme offers an official MCP server at https://mcp.acme.com/sse. "
        "Webhooks are supported. Rate limits apply. " * 6)


class FakeSearch:
    name = "fake"

    def search(self, q):
        return [{"title": "Acme docs", "url": "https://docs.acme.com/api", "snippet": ""}]


def fake_fetch(url, refresh=False):
    return {"url": url, "final_url": url, "status": 200, "text": PAGE, "thin": False}


def make_llm(access="free_tier", verdict="build_now", blocker="none"):
    def backend(model, system, user):
        if "adjudicate" in system:
            return json.dumps({"self_serve": {"value": "free_tier", "source": "S1",
                                              "quote": "API keys are available on the free plan", "reason": "stated"}})
        return json.dumps({"description": "Acme CRM", "auth": ["API key", "OAuth2"], "auth_notes": "", "self_serve": access,
                           "gate_detail": "free plan", "api_styles": ["REST"], "api_scope": "contacts", "webhooks": "yes",
                           "sandbox": "unknown", "mcp_status": "official", "mcp_url": "https://mcp.acme.com/sse", "mcp_notes": "",
                           "verdict": verdict, "blocker": blocker, "blocker_detail": "", "confidence": "high",
                           "evidence": [{"source": "S1", "supports": ["auth", "access"], "quote": "API keys are available on the free plan"},
                                        {"source": "S1", "supports": ["mcp"], "quote": "Acme offers an official MCP server"},
                                        {"source": "S1", "supports": ["api"], "quote": "this sentence is invented by the model"}],
                           "uncertainties": []})
    return backend


class Pipeline(unittest.TestCase):
    def setUp(self):
        retrieve.fetch = fake_fetch
        research.collect_sources.__globals__["fetch"] = fake_fetch
        reconcile.fetch = fake_fetch
        research.fetch = fake_fetch
        llm.set_backend(None)
        self.app = {"id": 1, "name": "Acme", "category": "CRM and Sales", "hint": "acme.com", "leads": []}

    def test_seed_is_complete(self):
        apps = seed.build()
        self.assertEqual(len(apps), 100)
        self.assertEqual({a["category"] for a in apps}, set(schema.CATEGORIES))

    def test_quote_grounding_catches_invented_evidence(self):
        llm.set_backend(make_llm())
        rec = research.research_app(self.app, FakeSearch(), "fake/model")
        matches = [e["quote_match"] for e in rec["evidence"]]
        self.assertEqual(matches.count("missing"), 1)
        self.assertIn("exact", matches)
        self.assertEqual(schema.validate(rec), [])

    def test_lint_flags_contradiction(self):
        llm.set_backend(make_llm(access="sales", verdict="build_now"))
        rec = research.research_app(self.app, FakeSearch(), "fake/model")
        self.assertIn("verdict_build_now_but_gated", rec["lint"])

    def test_reconcile_adjudicates_and_applies_rule_fix(self):
        llm.set_backend(make_llm(access="sales", verdict="build_now"))
        base = research.research_app(self.app, FakeSearch(), "m1")
        llm.set_backend(make_llm(access="free_tier", verdict="build_now"))
        blind = research.research_app(self.app, FakeSearch(), "m2", "blind")
        llm.set_backend(make_llm())
        final = reconcile.reconcile_one(base, blind, "m3")
        self.assertEqual(final["self_serve"], "free_tier")           # adjudicated with a verified quote
        self.assertEqual(final["verification"]["status"], "adjudicated")
        self.assertTrue(final["verification"]["disputed"]["self_serve"]["resolved"])

    def test_majority_of_three_overrides_outlier_without_llm(self):
        llm.set_backend(make_llm(access="sales", verdict="needs_outreach", blocker="sales_partnership"))
        base = research.research_app(self.app, FakeSearch(), "m1")
        llm.set_backend(make_llm(access="free_tier"))
        blind = research.research_app(self.app, FakeSearch(), "m2", "blind")
        retry = research.research_app(self.app, FakeSearch(), "m3", "retry")
        llm.set_backend(lambda *a: (_ for _ in ()).throw(AssertionError("adjudicator must not be called")))
        final = reconcile.reconcile_one(base, blind, "m4", retry)
        self.assertEqual(final["self_serve"], "free_tier")
        self.assertEqual(final["verification"]["disputed"]["self_serve"]["resolved_by"], "majority_of_3_with_verified_quote")

    def test_unverified_adjudication_does_not_change_value(self):
        llm.set_backend(make_llm(access="sales", verdict="needs_outreach", blocker="sales_partnership"))
        base = research.research_app(self.app, FakeSearch(), "m1")
        llm.set_backend(make_llm(access="free_tier"))
        blind = research.research_app(self.app, FakeSearch(), "m2", "blind")
        llm.set_backend(lambda m, s, u: json.dumps({"self_serve": {"value": "free_tier", "source": "S1", "quote": "made up words not on page", "reason": "x"}}))
        final = reconcile.reconcile_one(base, blind, "m3")
        self.assertEqual(final["self_serve"], "sales")
        self.assertEqual(final["confidence"], "low")
        self.assertFalse(final["verification"]["disputed"]["self_serve"]["resolved"])

    def test_handoff_mode_writes_prompt_then_ingests_answer_with_grounding(self):
        app = dict(self.app, id=77)
        with self.assertRaises(llm.NeedsAnswer):
            research.research_app(app, FakeSearch(), llm.HANDOFF)
        prompt = llm.handoff_dir() / "primary-077.prompt.md"
        self.assertTrue(prompt.exists())
        self.assertIn("SOURCES:", prompt.read_text(encoding="utf-8"))
        answer = json.loads(make_llm()("m", "s", "u"))
        (llm.handoff_dir() / "primary-077.answer.json").write_text(json.dumps(answer), encoding="utf-8")
        rec = research.research_app(app, FakeSearch(), llm.HANDOFF)
        self.assertEqual(rec["model"], llm.label(llm.HANDOFF))
        self.assertIn("missing", [e["quote_match"] for e in rec["evidence"]])   # invented quote still caught

    def test_catalog_match_and_auth_agreement(self):
        from atlas import catalog
        cat = [{"slug": "hubspot", "name": "HubSpot", "auth_schemes": ["OAUTH2", "API_KEY"], "managed": [], "no_auth": False, "tools_count": 50, "app_url": "https://hubspot.com"},
               {"slug": "zoho", "name": "Zoho CRM", "auth_schemes": ["OAUTH2"], "managed": [], "no_auth": False, "tools_count": 9, "app_url": None}]
        t, how = catalog.match_app({"name": "HubSpot", "hint": "hubspot.com"}, cat)
        self.assertEqual((t["slug"], how), ("hubspot", "slug"))
        self.assertEqual(catalog.match_app({"name": "Zoho CRM", "hint": ""}, cat)[0]["slug"], "zoho")
        self.assertIsNone(catalog.match_app({"name": "Attio", "hint": "attio.com"}, cat)[0])
        self.assertEqual(catalog.agreement(["OAuth2", "API key"], cat[0]), "match")
        self.assertEqual(catalog.agreement(["Basic"], cat[0]), "disagree")
        self.assertEqual(catalog.agreement(["OAuth2"], None), "no_toolkit")

    def test_malformed_json_retries_then_fails_loudly(self):
        llm.set_backend(lambda m, s, u: "not json at all")
        with self.assertRaises(ValueError):
            llm.ask_json("m", "s", "u")

    def test_search_response_harvest_handles_unknown_shapes(self):
        resp = {"data": {"results": [{"title": "A", "link": "https://a.com/x", "snippet": "s"}, {"nested": [{"url": "https://b.com"}]}]}}
        self.assertEqual([h["url"] for h in retrieve.harvest(resp)], ["https://a.com/x", "https://b.com"])

    def test_ssrf_guard(self):
        for bad in ("http://example.com", "https://127.0.0.1/", "https://user:pw@example.com/"):
            with self.assertRaises(ValueError):
                retrieve.public_url(bad)

    def test_audit_scoring_uses_human_truth(self):
        llm.set_backend(make_llm())
        for i in range(1, 4):
            app = dict(self.app, id=i)
            base = research.research_app(app, FakeSearch(), "m1")
            base["self_serve"] = "paid_plan"
            blind = research.research_app(app, FakeSearch(), "m2", "blind")
            final = reconcile.reconcile_one(base, blind, "m3")
            for folder, rec in (("baseline", base), ("verify", blind), ("final", final)):
                (reconcile.sub(folder) / f"{i:03d}.json").write_text(json.dumps(rec), encoding="utf-8")
        audit.prepare(log=lambda *_: None)
        sample = json.loads((reconcile.sub("audit") / "sample.json").read_text())
        ids = sample["random"] + sample["hard"]
        judg = [{"app_id": i, "field": "self_serve", "status": "answered", "correct": "free_tier"} for i in ids]
        path = Path(os.environ["ATLAS_DATA"]) / "h.json"
        path.write_text(json.dumps({"reviewer": "Test", "judgments": judg}))
        s = audit.score(str(path), log=lambda *_: None)
        self.assertEqual(s["overall"]["baseline_accuracy"], 0.0)
        self.assertEqual(s["overall"]["final_accuracy"], 1.0)
        with self.assertRaises(ValueError):
            path.write_text(json.dumps({"reviewer": "", "judgments": []}))
            audit.score(str(path), log=lambda *_: None)


if __name__ == "__main__":
    unittest.main()
