"""End-to-end offline test: runs the whole weekly pipeline on a COPY of the site with simulated
AI replies and APIs. Nothing is sent, pushed or published.

    python automation/tests/offline_test.py
"""
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[2]
TMP = Path(tempfile.mkdtemp(prefix="meridian-offline-"))
shutil.copytree(SRC, TMP / "site", ignore=shutil.ignore_patterns(".git", "runs", "gsc", "__pycache__"))
sys.path.insert(0, str(TMP / "site"))
os.environ["CALC_SANDBOX"] = "off"

from automation.engine import config, integrations as ext, llm, pipeline, store  # noqa: E402

SENT = []
GATE_CALLS = {"n": 0}

DRAFT = """---
title: TCS is a loan to the taxman, not a cost.
dek: What 20% TCS really costs a ₹15 lakh remittance, and how to get it back sooner.
category: Rules
keyfigs: [{"value":"20%","label":"TCS above ₹10 lakh a year","ref":"F1"},{"value":"₹1,00,000","label":"TCS on a ₹15 lakh remittance","ref":"C1"},{"value":"$250,000","label":"LRS limit per person per year","ref":"F2"}]
---
Illustrative example: Neha, 38, in Pune, wants to move ₹15 lakh to her global account this year. Her bank will collect 20% TCS on everything above ₹10 lakh [F1]. That money is not lost. It is parked with the government until she files her return, and that wait is the real cost.

Our view is simple: TCS is a timing problem, not a tax problem. Treat it as a short loan to the government and plan the cash flow around it.

## How TCS works on an LRS remittance

TCS applies to remittances under the Liberalised Remittance Scheme above ₹10 lakh in a financial year, at 20% for investment [F1]. Each resident can remit up to $250,000 a year under LRS [F2]. The bank deducts it at the time of the transfer and deposits it against your PAN.

## What it costs Neha

[C1]
| Remittance | TCS collected | Months until refund | Interest lost at 7% |
| --- | --- | --- | --- |
| ₹15,00,000 | ₹1,00,000 | 14 | ₹8,167 |

The interest lost is the only true cost, and it shrinks if Neha adjusts her advance tax for the year. Combine the 20% rate [F1] with the $250,000 ceiling [F2] and a family that splits remittances across two members can halve the amount that ever attracts TCS.

## Questions readers ask

### Is TCS an extra tax on investing abroad?
No. It is an advance collection that counts towards your income tax for the year [F1]. You claim it in your return.

### Can I reduce TCS legally?
Yes, by keeping each person's remittances within the ₹10 lakh threshold [F1].

This article is for education only and is not investment, tax or legal advice. Rules change; check your own situation with a qualified professional.
"""


def mock(agent, system, user):
    if agent == "perspective_bank":
        return json.dumps({"items": [{"id": "V01", "type": "view", "text": "The rupee's fall is a return, too.", "source": "/insights/rupee-is-a-return"},
                                     {"id": "V02", "type": "view", "text": "TCS is not a cost; it is credited against your tax.", "source": "/insights/cost-of-sending-money-abroad"}]})
    if agent == "director":
        return json.dumps({"phase": "SANDBOX", "phase_evidence": "no data yet", "deliverable": "NEW", "refresh_target_url": None,
                           "pillar_priority": ["P1"], "format_preference": "case_study", "max_keyword_difficulty": 25,
                           "news_hook_allowed": False, "strategy_changes": [{"field": "pillar_weights.P1", "from": 0.167, "to": 0.4, "reason": "test clamp"}],
                           "experiment": None, "notes_for_scout": "TCS questions"})
    if agent == "scout":
        return json.dumps({"candidates": [
            {"id": "c01", "working_title": "TCS refund timing", "pillar": "P1", "primary_keyword": "tcs on foreign remittance refund",
             "secondary_keywords": ["tcs refund"], "source": "keyword_tool", "volume_monthly_in": 880, "keyword_difficulty": 12,
             "trend": "stable", "search_intent": "informational", "news_hook": None, "why_meridian_wins": "cash-flow maths", "cannibalisation_risk": False},
            {"id": "c02", "working_title": "Cricket", "pillar": "P9", "primary_keyword": "ipl", "volume_monthly_in": 100000, "keyword_difficulty": 90},
            {"id": "c03", "working_title": "Schedule FA penalty", "pillar": "P2", "primary_keyword": "schedule fa penalty",
             "secondary_keywords": [], "source": "keyword_tool", "volume_monthly_in": 320, "keyword_difficulty": 8,
             "trend": "stable", "search_intent": "informational", "news_hook": None, "why_meridian_wins": "worked penalty", "cannibalisation_risk": False}]})
    if agent == "strategist" and "Rate each candidate" in system:
        return json.dumps({"ratings": [{"id": "c01", "relevance": 5, "business_value": 5, "angle_strength": 4, "reasons": ""},
                                       {"id": "c03", "relevance": 4, "business_value": 3, "angle_strength": 4, "reasons": ""}]})
    if agent == "strategist":
        return json.dumps({"pick": {"id": "c01", "primary_keyword": "tcs on foreign remittance refund", "secondary_keywords": ["tcs refund"],
                                    "pillar": "P1", "format": "case_study", "working_title": "TCS refund timing",
                                    "why_this_one": "highest score", "cornerstone_to_support": "/insights/lrs-tcs-schedule-fa"},
                           "ledger_updates": [{"id": "c03", "status": "deferred", "reason": "next week"}]})
    if agent == "serp":
        return json.dumps({"intent": {"primary": "informational"}, "snippet_target": {"question": "Is TCS refundable?"},
                           "must_cover": ["rate", "threshold"], "gaps": [{"gap": "No rupee cost of the wait", "evidence": "", "how_we_fill_it": "calc"},
                                                                         {"gap": "No family split", "evidence": "", "how_we_fill_it": ""},
                                                                         {"gap": "Outdated thresholds", "evidence": "", "how_we_fill_it": ""}],
                           "unique_asset": "interest-lost table", "thesis": "TCS is a loan to the government; its cost is the interest you lose.",
                           "perspective_ids": ["V02"], "outline": [], "faq": [], "data_needed": [], "calculations_needed": [{"name": "interest lost"}],
                           "internal_links": [], "tool_cta": "/tools/tcs-calculator", "target_words": 1400,
                           "title_options": ["TCS is a loan to the taxman, not a cost."], "slug": "tcs-refund-cost-lrs"})
    if agent == "researcher":
        return json.dumps({"facts": [
            {"id": "F1", "claim": "TCS of 20% applies above ₹10 lakh for investment remittances", "quote": "20% on amount exceeding ₹10 lakh",
             "url": "https://incometaxindia.gov.in/tcs", "publisher": "Income Tax Department", "page_title": "TCS rates", "source_tier": 1, "status": "verified"},
            {"id": "F2", "claim": "LRS limit is $250,000 per financial year", "quote": "USD 2,50,000 per financial year",
             "url": "https://rbi.org.in/lrs-faq", "publisher": "RBI", "page_title": "LRS FAQs", "source_tier": 1, "status": "verified"}],
            "calculations": [{"name": "interest lost", "python": "r=1500000;t=0.2*(r-1000000);i=t*0.07*14/12\nprint('| Remittance | TCS collected | Months until refund | Interest lost at 7% |')\nprint('| --- | --- | --- | --- |')\nprint(f'| ₹15,00,000 | ₹{t:,.0f} | 14 | ₹{i:,.0f} |')",
                              "fact_inputs": ["F1"]}],
            "illustrative_household": {"name": "Neha", "age": 38, "city": "Pune", "illustrative": True, "rate": "7%"},
            "counterpoints": [], "gaps_unfilled": []})
    if agent == "writer":
        return DRAFT
    if agent == "editor":
        return json.dumps({"draft_edited": DRAFT, "cut_percent": 11, "scores": {"specificity": 9, "clarity": 9, "originality": 8,
                           "rhythm": 8, "trustworthiness": 9, "insight": 8}, "changes": ["tightened opening"]})
    if agent == "reader_panel":
        mine_is_a = "Neha" in user.split("ARTICLE B:")[0]
        return json.dumps({"more_human": "A" if mine_is_a else "B", "teaches_more": "B" if mine_is_a else "A",
                           "reasons_A": [], "reasons_B": [], "fixes_for_A": ["add a sharper close"], "fixes_for_B": ["add a sharper close"]})
    if agent == "gate":
        GATE_CALLS["n"] += 1
        if GATE_CALLS["n"] == 1:
            return json.dumps({"review_round": 1, "verdict": "REVISE", "issues": [{"severity": "MAJOR", "quote": "x", "rule": "A1", "problem": "overstated", "fix": "soften"}], "verified_claims": 5})
        return json.dumps({"review_round": 2, "verdict": "PASS", "issues": [], "verified_claims": 7})
    if agent == "builder":
        data = json.loads(user)
        corner = next(p for p in data["live_posts"] if p["url"] == "/insights/lrs-tcs-schedule-fa")
        sent = corner["linkable_sentences"][0]
        words = sent.split()
        anchor = " ".join(words[1:4])
        return json.dumps({"title_tag": "TCS on foreign remittance: refund and real cost",
                           "meta_description": "TCS on a foreign remittance is refundable. See what 20% TCS really costs a ₹15 lakh LRS transfer in lost interest, and how to get it back sooner.",
                           "slug": "tcs-refund-cost-lrs",
                           "internal_links": [{"phrase": "Liberalised Remittance Scheme", "url": "/insights/lrs-tcs-schedule-fa"},
                                              {"phrase": "global account", "url": "/how-it-works"}],
                           "inbound_link_edits": [{"file": corner["file"], "find": sent,
                                                   "replace": sent.replace(anchor, f'<a href="/insights/NEW-SLUG">{anchor}</a>', 1)}],
                           "keep_reading": ["/insights/lrs-tcs-schedule-fa", "/insights/cost-of-sending-money-abroad"],
                           "keywords": "TCS on foreign remittance, TCS refund, LRS TCS", "tool_cta": {"url": "/tools/tcs-calculator", "label": "Run the TCS calculator →"}})
    raise AssertionError(f"unexpected agent {agent}")


def run():
    llm.MOCK = mock
    ext.serp = lambda kw: {"organic": [{"url": "https://example.com/a", "title": "A"}], "people_also_ask": ["Is TCS refundable?"]}
    ext.fetch_page = lambda url, n=6000: {"url": url, "title": "A", "headings": [], "word_count": 1200, "text_excerpt": "x"}
    ext.keyword_ideas = lambda seeds, limit=400: [{"keyword": "tcs on foreign remittance refund", "volume": 880, "kd": 12}]
    ext.trends_rising = lambda t: []
    ext.news_items = lambda days=10: []
    ext.page_text = lambda url, n=6000: "20% on amount exceeding ₹10 lakh"
    ext.send_email = lambda s, h, attachments=None: SENT.append((s, len(h), [a[0] for a in attachments or []])) or True
    ext.indexnow = lambda urls, key: True
    ext.gsc_submit_sitemap = lambda: True

    run = store.Run("test-run")
    state = pipeline.prepare(run)
    assert state["status"] == "READY", state
    slug = state["slug"]
    page_path = config.ROOT / f"insights/{slug}.html"
    page = page_path.read_text(encoding="utf-8")
    ext.live_status = lambda url: (200, page)
    st2 = pipeline.post_publish(run, wait_seconds=5)

    # ---- assertions
    from automation.engine import site
    errs = site.validate_page(page)
    assert not errs, errs
    assert "[F1]" not in page and "[C1]" not in page, "markers leaked into page"
    assert '<div class="table-wrap"><table>' in page
    assert '"@type": "FAQPage"' in page and '"@type": "Article"' in page
    assert 'href="/insights/lrs-tcs-schedule-fa">Liberalised Remittance Scheme</a>' in page, "internal link not applied"
    assert "Income Tax Department: TCS rates" in page, "sources list missing"
    idx = (config.ROOT / "insights.html").read_text(encoding="utf-8")
    assert idx.find(f'href="/insights/{slug}"') < idx.find('href="/insights/how-us-investments-are-taxed-in-india"'), "card not first"
    sm = (config.ROOT / "sitemap.xml").read_text(encoding="utf-8")
    assert f"/insights/{slug}</loc>" in sm
    corner = (config.ROOT / "insights/lrs-tcs-schedule-fa.html").read_text(encoding="utf-8")
    assert f'href="/insights/{slug}"' in corner, "inbound link not added to cornerstone"
    strategy = store.load("strategy.json")
    assert abs(sum(strategy["pillar_weights"].values()) - 1) < 0.01
    assert GATE_CALLS["n"] == 2, "gate loop did not revise once then pass"
    posts = store.load("posts.json")
    rec = next(p for p in posts if p["slug"] == slug)
    assert rec["status"] == "live" and rec["origin"] == "engine"
    assert st2["status"] == "PUBLISHED"
    assert any(s.startswith("Published:") for s, _, _ in SENT), SENT
    assert (config.ROOT / f"{store.load('settings.json')['indexnow_key']}.txt").exists()
    print("ALL CHECKS PASSED")
    print("slug:", slug, "| emails:", SENT)
    print("trail:", json.dumps(state["trail"], ensure_ascii=False)[:400])
    print("output copy:", TMP / "site")


if __name__ == "__main__":
    run()
