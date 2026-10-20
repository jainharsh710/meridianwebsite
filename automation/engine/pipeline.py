"""The weekly run: learn -> plan -> research -> write -> check -> build. Publishing happens in a later step."""
import html
import json
import math
import random
import re
import time
import uuid
from datetime import date, timedelta

from . import calcs, config, integrations as ext, llm, site, store
from .lint import lint, mechanical_checks, split_front

SEED_PILLARS = {
    "lrs-tcs-schedule-fa": ("P1", True), "cost-of-sending-money-abroad": ("P1", False),
    "open-interactive-brokers-account-india": ("P1", False),
    "how-us-investments-are-taxed-in-india": ("P2", True),
    "us-estate-tax-for-indians": ("P3", True), "is-my-money-safe-at-interactive-brokers": ("P3", False),
    "rupee-is-a-return": ("P4", True),
    "us-etfs-vs-irish-ucits-etfs": ("P5", True), "international-mutual-funds-vs-investing-directly": ("P5", False),
    "gift-city-vs-overseas-account": ("P5", False),
    "how-much-should-be-global": ("P6", True), "sp500-vs-nifty-decade-question": ("P6", False),
}
CTR_BENCH = {1: .28, 2: .15, 3: .10, 4: .07, 5: .05, 6: .04, 7: .03, 8: .025, 9: .02, 10: .018}
PERSPECTIVE_PAGES = ["about.html", "why-global.html", "how-it-works.html", "faq.html", "international-investing.html"]


# ---------------------------------------------------------------- setup + shared context
def ensure_seed():
    if store.load("posts.json") is None:
        posts = []
        for p in site.all_posts_on_disk():
            pillar, corner = SEED_PILLARS.get(p["slug"], ("P6", False))
            posts.append({**{k: p[k] for k in ("slug", "url", "file", "h1", "dek", "category", "read_minutes", "words")},
                          "pillar": pillar, "cornerstone": corner, "primary_keyword": (p["keywords"] or "").split(",")[0].strip(),
                          "keywords": p["keywords"], "format": None, "published": p["date_published"],
                          "modified": p["date_modified"], "origin": "manual", "indexed": None, "indexed_date": None,
                          "refresh_count": 0, "last_changed": p["date_modified"], "reported_t7": True})
        store.save("posts.json", posts)
    if store.load("strategy.json") is None:
        store.save("strategy.json", {
            "pillar_weights": {p: round(1 / 6, 3) for p in config.PILLARS},
            "max_keyword_difficulty": 20,
            "format_rules": {"min_case_study_per_4w": 1, "min_explainer_or_guide_per_4w": 1, "max_news_per_4w": 2},
            "changes": []})
    for name, default in (("topics_ledger.json", []), ("experiments.json", [])):
        if store.load(name) is None:
            store.save(name, default)
    settings = store.load("settings.json") or {}
    if not settings.get("indexnow_key"):
        settings["indexnow_key"] = uuid.uuid4().hex
        store.save("settings.json", settings)
    key = settings["indexnow_key"]
    kf = config.ROOT / f"{key}.txt"
    if not kf.exists():
        kf.write_text(key, encoding="utf-8")
    return settings


def posts_summary(posts):
    return [{"url": p["url"], "title": p["h1"], "pillar": p.get("pillar"), "keyword": p.get("primary_keyword"),
             "format": p.get("format"), "published": p.get("published"), "cornerstone": p.get("cornerstone")}
            for p in posts]


def shared_ctx(run_id, posts):
    bank = store.load("perspectives.json", {"items": []})
    strategy = store.load("strategy.json", {})
    return {"date_ist": config.now_ist().strftime("%A %d %B %Y"), "run_id": run_id,
            "perspectives_json": json.dumps([{k: i[k] for k in ("id", "type", "text")} for i in bank["items"]], ensure_ascii=False),
            "posts_json_summary": json.dumps(posts_summary(posts), ensure_ascii=False),
            "strategy_json": json.dumps({k: strategy.get(k) for k in ("pillar_weights", "max_keyword_difficulty")}
                                        | {"open_experiments": [e for e in store.load("experiments.json", []) if not e.get("verdict")]},
                                        ensure_ascii=False)}


def ensure_perspective_bank(run, ctx):
    if store.load("perspectives.json"):
        return
    pages = [{"url": "/" + p.replace(".html", ""), "text": site.page_plain_text(p)[:12000]}
             for p in PERSPECTIVE_PAGES if (config.ROOT / p).exists()]
    pages += [{"url": f"/insights/{f.stem}", "text": site.page_plain_text(f"insights/{f.name}")[:9000]}
              for f in sorted((config.ROOT / "insights").glob("*.html"))]
    out = llm.call("perspective_bank", "00_perspective_bank.md",
                   {"pages": pages, "existing_bank": [], "mode": "build"}, ctx, max_tokens=12000)
    store.save("perspectives.json", {"items": out.get("items", []), "built": str(date.today())})
    run.write("perspective_bank.json", out)


# ---------------------------------------------------------------- learning: metrics + analyst
def post_metrics(posts, snap, today):
    if not snap or not snap.get("ok"):
        return []
    end = date.fromisoformat(snap["end"])
    w1 = (end - timedelta(days=27), end)
    w0 = (end - timedelta(days=55), end - timedelta(days=28))
    out = []
    for p in posts:
        full = config.SITE + p["url"]
        rows = [r for r in snap.get("page_date", []) if r["keys"][0] in (full, full + "/")]

        def agg(win):
            sel = [r for r in rows if win[0] <= date.fromisoformat(r["keys"][1]) <= win[1]]
            imp = sum(r["impressions"] for r in sel)
            clk = sum(r["clicks"] for r in sel)
            pos = round(sum(r["position"] * r["impressions"] for r in sel) / imp, 1) if imp else None
            return {"impressions": imp, "clicks": clk, "ctr": round(clk / imp, 4) if imp else 0, "position": pos}

        last7 = agg((end - timedelta(days=6), end))
        queries = sorted([r for r in snap.get("page_query", []) if r["keys"][0] in (full, full + "/")],
                         key=lambda r: -r["impressions"])[:10]
        pub = date.fromisoformat(p["published"][:10]) if p.get("published") else None
        age = (today - pub).days if pub else None
        changed = date.fromisoformat(p["last_changed"][:10]) if p.get("last_changed") else pub
        since_change = (today - changed).days if changed else None
        cp = next((c for c in config.CHECKPOINTS if age is not None and c <= age < c + 7), None)
        out.append({"url": p["url"], "title": p["h1"], "pillar": p.get("pillar"), "format": p.get("format"),
                    "words": p.get("words"), "keyword": p.get("primary_keyword"), "age_days": age,
                    "indexed": p.get("indexed"), "indexed_date": p.get("indexed_date"),
                    "metrics_7d": last7, "metrics_28d": agg(w1), "metrics_prev_28d": agg(w0),
                    "top_queries": [{"query": r["keys"][1], "impressions": r["impressions"], "clicks": r["clicks"],
                                     "position": round(r["position"], 1)} for r in queries],
                    "last_changed_days_ago": since_change, "refresh_count": p.get("refresh_count", 0),
                    "checkpoint": cp,
                    "eligible_for_action": bool(cp and (since_change is None or since_change >= 28)
                                                and p.get("refresh_count", 0) < 3 and p.get("origin") != "manual-locked")})
    return out


def site_totals(snap):
    if not snap or not snap.get("ok"):
        return {"available": False}
    end = date.fromisoformat(snap["end"])

    def tot(a, b):
        sel = [r for r in snap.get("page_date", []) if a <= date.fromisoformat(r["keys"][1]) <= b]
        imp = sum(r["impressions"] for r in sel)
        clk = sum(r["clicks"] for r in sel)
        pos = round(sum(r["position"] * r["impressions"] for r in sel) / imp, 1) if imp else None
        return {"impressions": imp, "clicks": clk, "ctr": round(clk / imp, 4) if imp else 0, "position": pos}

    pages = {}
    for r in snap.get("page_query", []):
        pages.setdefault(r["keys"][0], 0)
        pages[r["keys"][0]] += r["impressions"]
    return {"available": True, "data_end": snap["end"],
            "last_7d": tot(end - timedelta(days=6), end), "prev_7d": tot(end - timedelta(days=13), end - timedelta(days=7)),
            "last_28d": tot(end - timedelta(days=27), end), "prev_28d": tot(end - timedelta(days=55), end - timedelta(days=28)),
            "top_pages": sorted(pages.items(), key=lambda kv: -kv[1])[:5],
            "top_queries": [{"query": r["keys"][0], "impressions": r["impressions"], "clicks": r["clicks"],
                             "position": round(r["position"], 1)} for r in sorted(snap.get("query_28d", []), key=lambda r: -r["impressions"])[:10]]}


def cannibalisation(snap):
    if not snap or not snap.get("ok"):
        return []
    by_q = {}
    for r in snap.get("page_query", []):
        if r["impressions"] >= 5:
            by_q.setdefault(r["keys"][1], set()).add(r["keys"][0])
    return [{"query": q, "pages": sorted(p)} for q, p in by_q.items() if len(p) > 1][:20]


# ---------------------------------------------------------------- topic choice
def score(c, rating, strategy, max_kd):
    r, b, a = rating.get("relevance", 0), rating.get("business_value", 0), rating.get("angle_strength", 0)
    vol = c.get("volume_monthly_in") or 10
    kd = c.get("keyword_difficulty")
    kd = 30 if kd is None else kd
    if kd > max_kd or c.get("cannibalisation_risk"):
        return 0.0
    f = 1.3 if c.get("news_hook") else 1.0
    w = strategy["pillar_weights"].get(c.get("pillar"), 0.1) * 6        # 1.0 when weights are equal
    g = 1.5 if c.get("source") == "gsc" else 1.0
    return round(r * b * a * math.log10(vol + 10) * (1 - kd / 100) * f * w * g, 2)


def choose_topics(run, ctx, plan, posts, snap):
    strategy = store.load("strategy.json")
    ledger = store.load("topics_ledger.json", [])
    gsc_q = []
    if snap and snap.get("ok"):
        ranked = {}
        for r in snap.get("page_query", []):
            q = r["keys"][1]
            ranked.setdefault(q, {"query": q, "impressions": 0, "clicks": 0, "best_position": 999, "pages": set()})
            e = ranked[q]
            e["impressions"] += r["impressions"]
            e["clicks"] += r["clicks"]
            e["best_position"] = min(e["best_position"], r["position"])
            e["pages"].add(r["keys"][0])
        gsc_q = [{**{k: v for k, v in e.items() if k != "pages"}, "pages": sorted(e["pages"])[:3],
                  "best_position": round(e["best_position"], 1)}
                 for e in ranked.values() if e["impressions"] >= 5 and 8 <= e["best_position"] <= 50]
        gsc_q = sorted(gsc_q, key=lambda e: -e["impressions"])[:80]
        metrics = ext.keyword_overview([e["query"] for e in gsc_q])
        for e in gsc_q:
            e.update(metrics.get(e["query"], {}))
    kw = ext.keyword_ideas(config.SEED_TERMS)
    trends = ext.trends_rising(["LRS", "TCS", "US stocks", "rupee", "Interactive Brokers"])
    news = ext.news_items()
    run.write("scout_inputs.json", {"gsc_queries": gsc_q, "keyword_data": kw[:300], "trends_rising": trends, "news_items": news})

    payload = {"weekly_plan": plan, "gsc_queries": gsc_q, "keyword_data": kw[:300], "trends_rising": trends, "news_items": news}
    cands = []
    for attempt in range(2):
        out = llm.call("scout", "02_scout.md", payload, ctx, tools={"web_search": 6}, max_tokens=12000)
        cands = out.get("candidates", out if isinstance(out, list) else [])
        off = [c for c in cands if c.get("pillar") not in config.PILLARS]
        if cands and len(off) / len(cands) <= 0.2:
            break
        payload["notes"] = ("Your last list had too many off-niche topics. Use only the subtopics in the topic map "
                            "as seeds and drop anything that does not map to a pillar.")
    cands = [c for c in cands if c.get("pillar") in config.PILLARS]
    run.write("candidates.json", cands)
    if not cands:
        raise RuntimeError("Scout returned no usable candidates")

    recent = [l for l in ledger if l.get("date") and (date.today() - date.fromisoformat(l["date"])).days <= 60][-200:]
    rated = llm.call("strategist", "03_strategist_rate.md",
                     {"candidates": cands, "weekly_plan": plan, "ledger_recent": recent}, ctx, max_tokens=8000)
    rmap = {r["id"]: r for r in rated.get("ratings", [])}
    max_kd = plan.get("max_keyword_difficulty") or strategy.get("max_keyword_difficulty", 20)
    for c in cands:
        c["score"] = score(c, rmap.get(c["id"], {}), strategy, max_kd)
        c["rating"] = rmap.get(c["id"], {})
    ranked = sorted([c for c in cands if c["score"] > 0], key=lambda c: -c["score"])
    if not ranked:
        ranked = sorted(cands, key=lambda c: -(rmap.get(c["id"], {}).get("relevance", 0)))
    run.write("scored.json", ranked)

    recent_formats = [p.get("format") for p in sorted(posts, key=lambda p: p.get("published") or "")[-4:]]
    choice = llm.call("strategist", "03_strategist_choose.md",
                      {"top3": ranked[:3], "weekly_plan": plan, "recent_formats": recent_formats}, ctx, max_tokens=4000)
    run.write("pick.json", choice)
    pick = choice["pick"]
    order = [pick] + [dict(primary_keyword=c["primary_keyword"], secondary_keywords=c.get("secondary_keywords", []),
                           pillar=c["pillar"], format=plan.get("format_preference") or "explainer",
                           working_title=c.get("working_title"), id=c["id"],
                           cornerstone_to_support=config.CORNERSTONES[c["pillar"]],
                           why_this_one="fallback: next-ranked candidate")
                      for c in ranked if c["id"] != pick.get("id")][:config.MAX_TOPIC_FALLBACKS]
    today = str(date.today())
    for u in choice.get("ledger_updates", []):
        c = next((x for x in cands if x["id"] == u.get("id")), {})
        ledger.append({"date": today, "keyword": c.get("primary_keyword"), "pillar": c.get("pillar"),
                       "status": u.get("status", "rejected"), "reason": u.get("reason")})
    store.save("topics_ledger.json", ledger)
    return order


# ---------------------------------------------------------------- research + writing
def brief_for(run, ctx, pick, posts, mode, existing=None):
    s = ext.serp(pick["primary_keyword"]) or {}
    pages = [ext.fetch_page(o["url"], 6000) for o in s.get("organic", [])[:10]]
    targets = [{"url": p["url"], "title": p["h1"], "pillar": p.get("pillar"), "cornerstone": p.get("cornerstone")}
               for p in posts] + site.site_tools()
    payload = {"pick": pick, "serp": s, "pages": pages, "internal_link_targets": targets, "mode": mode}
    if existing:
        payload.update(existing)
    brief = llm.call("serp", "04_serp_brief.md", payload, ctx, max_tokens=8000)
    run.write("serp.json", {"serp": s, "pages": [{k: v for k, v in p.items() if k != "text_excerpt"} for p in pages]})
    run.write("brief.json", brief)
    return brief


def research(run, ctx, pick, brief):
    errors = None
    for attempt in range(2):
        pack = llm.call("researcher", "05_researcher.md",
                        {"brief": {k: brief.get(k) for k in ("data_needed", "calculations_needed", "thesis", "must_cover", "gaps")},
                         "pick": pick, "previous_attempt_errors": errors}, ctx,
                        tools={"web_search": 15, "web_fetch": 20}, max_tokens=16000)
        outs, errs = calcs.run_all(pack.get("calculations"))
        pack["calc_outputs"] = outs
        if not errs:
            break
        errors = errs
    pack["calc_errors"] = errors if errors and errs else []
    run.write("source_pack.json", pack)
    return pack


def style_reference_text():
    page = (config.ROOT / config.STYLE_REFERENCE).read_text(encoding="utf-8")
    return site.strip_tags(site.prose_html(page))


def perspectives_for(ids):
    bank = store.load("perspectives.json", {"items": []})["items"]
    return [i for i in bank if i["id"] in (ids or [])]


def write_and_check(run, ctx, pick, brief, pack, strict, existing_article=None):
    """Writer -> Editor -> reader panel -> gate (with up to 2 revisions). Returns (draft, gate, trail)."""
    persp = perspectives_for(brief.get("perspective_ids"))
    style = style_reference_text()
    base = {"brief": brief, "source_pack": {"facts": [f for f in pack.get("facts", []) if f.get("status") == "verified"],
                                             "calc_outputs": pack.get("calc_outputs", []),
                                             "illustrative_household": pack.get("illustrative_household"),
                                             "counterpoints": pack.get("counterpoints")},
            "pick": pick, "perspectives": persp, "style_reference": style}
    if existing_article:
        base["existing_article"] = existing_article
    draft = llm.call("writer", "06_writer.md", base, ctx, expect_json=False, max_tokens=12000)
    run.write("draft_v1.md", draft)

    report = lint(draft)
    edited = llm.call("editor", "07_editor.md", {"draft": draft, "lint_report": report, "brief": brief}, ctx, max_tokens=14000)
    draft = edited["draft_edited"]
    trail = {"editor_scores": edited.get("scores"), "editor_changes": edited.get("changes"), "cut_percent": edited.get("cut_percent")}
    run.write("draft_v2_edited.md", draft)

    # Blind reader panel against the firm's best human-edited article.
    flip = random.random() < 0.5
    a, b = (draft, style) if flip else (style, draft)
    panel = llm.call("reader_panel", "07b_reader_panel.md", f"ARTICLE A:\n{a}\n\nARTICLE B:\n{b}", ctx, max_tokens=3000)
    mine = "A" if flip else "B"
    lost = panel.get("more_human") != mine or panel.get("teaches_more") != mine
    trail["reader_panel"] = {"draft_won_human": panel.get("more_human") == mine,
                             "draft_won_teaching": panel.get("teaches_more") == mine,
                             "reasons": panel.get(f"reasons_{mine}")}
    if lost:
        fixes = panel.get(f"fixes_for_{mine}")
        edited = llm.call("editor", "07_editor.md", {"draft": draft, "lint_report": lint(draft), "brief": brief,
                                                     "reader_panel_feedback": fixes}, ctx, max_tokens=14000)
        draft = edited["draft_edited"]
        trail["editor_scores_final"] = edited.get("scores")
        trail["editor_changes"] = (trail.get("editor_changes") or []) + (edited.get("changes") or [])
        run.write("draft_v3_panel.md", draft)

    gate = None
    for rnd in range(1, config.MAX_GATE_ROUNDS + 1):
        mech = mechanical_checks(draft, pack)
        mech["lint"] = lint(draft)["issues"]
        refetch = []
        for f in pack.get("facts", []):
            if len(refetch) >= 6:
                break
            if f.get("source_tier") == 1 and re.search(r"limit|rate|threshold|deadline|%|lakh|\$", f.get("claim", ""), re.I):
                txt = ext.page_text(f["url"], 6000)
                if txt:
                    refetch.append({"fact_id": f["id"], "url": f["url"], "live_text": txt})
        gate = llm.call("gate", "08_gate.md", {"draft": draft, "source_pack": pack, "refetched_sources": refetch,
                                               "mechanical_checks": mech, "brief": brief, "perspectives": persp,
                                               "review_round": rnd, "strict_mode": strict}, ctx, max_tokens=8000)
        run.write(f"gate_round{rnd}.json", gate)
        verdict = gate.get("verdict")
        if verdict == "PASS":
            break
        if verdict == "HOLD" or rnd == config.MAX_GATE_ROUNDS:
            gate["verdict"] = "HOLD"
            gate.setdefault("hold_reason", "Issues remained after the final review round.")
            break
        draft = llm.call("writer", "06_writer.md", {**base, "previous_draft": draft, "gate_feedback": gate.get("issues")},
                         ctx, expect_json=False, max_tokens=12000)
        run.write(f"draft_rev{rnd}.md", draft)
    trail["gate_rounds"] = gate.get("review_round", rnd) if gate else 0
    trail["gate_issues_fixed"] = sum(len(json.loads((run.dir / f"gate_round{i}.json").read_text()).get("issues", []))
                                     for i in range(1, rnd))
    return draft, gate, trail


# ---------------------------------------------------------------- build
def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return "-".join(s.split("-")[:7]) or "article"


def build(run, ctx, draft, brief, pick, pack, posts, mode, existing_slug=None, published=None):
    disk_posts = {p["slug"]: p for p in site.all_posts_on_disk()}
    live = []
    for p in posts:
        d = disk_posts.get(p["slug"], {})
        page = (config.ROOT / p["file"]).read_text(encoding="utf-8") if (config.ROOT / p["file"]).exists() else ""
        live.append({"title": p["h1"], "url": p["url"], "keyword": p.get("primary_keyword"), "pillar": p.get("pillar"),
                     "category": p.get("category"), "indexed": p.get("indexed"), "file": p["file"],
                     "linkable_sentences": site.linkable_sentences(page) if mode == "NEW" else []})
    payload = {"draft": draft, "brief": brief, "pick": pick, "live_posts": live, "tools": site.site_tools(),
               "mode": mode, "existing_slug": existing_slug}
    today = str(date.today())
    errors = []
    for attempt in range(2):
        if errors:
            payload["previous_errors"] = errors
        seo = llm.call("builder", "09_builder.md", payload, ctx, max_tokens=6000)
        slug = existing_slug or slugify(seo.get("slug") or brief.get("slug"))
        if mode == "NEW" and (config.ROOT / f"insights/{slug}.html").exists():
            slug = f"{slug}-{date.today().year}"
        page, info = site.build_article(draft_md=draft, seo=seo, facts=pack.get("facts", []),
                                        posts=[disk_posts[p["slug"]] for p in posts if p["slug"] in disk_posts],
                                        published=published or today, modified=today, slug=slug)
        errors = site.validate_page(page)
        if not errors:
            break
    run.write("seo.json", seo)
    if errors:
        return None, {"errors": errors}
    (config.ROOT / f"insights/{slug}.html").write_text(page, encoding="utf-8")
    edited_paths = []
    if mode == "NEW":
        for e in seo.get("inbound_link_edits", [])[:3]:
            if site.apply_inbound_edit(e, slug):
                site.set_modified(e["file"], today)
                edited_paths.append("/" + e["file"].replace(".html", ""))
        meta, _ = split_front(draft)
        site.add_index_card({"url": f"/insights/{slug}", "h1": info["title"], "dek": info["dek"],
                             "category": info["category"], "read_minutes": info["read_minutes"]})
    site.touch_sitemap(edited_paths, today, new_path=f"/insights/{slug}")
    info.update({"slug": slug, "seo": seo, "inbound_links_added": edited_paths})
    return page, info


# ---------------------------------------------------------------- the weekly 'prepare' stage
def prepare(run):
    today = date.today()
    if (config.ROOT / "PAUSE").exists():
        run.set_state(status="PAUSED", publish_ready=False)
        ext.send_email("PAUSED: Meridian content engine", "<p>The PAUSE file is present in the repo, so this "
                       "week's run did nothing. Delete the file to resume.</p>")
        return run.state

    ensure_seed()
    posts = store.load("posts.json")
    ctx = shared_ctx(run.id, posts)
    ensure_perspective_bank(run, ctx)
    ctx = shared_ctx(run.id, posts)

    # 1. Learn
    snap = ext.gsc_snapshot() if config.GSC_SA_JSON else {"ok": False, "error": "GSC not configured"}
    if snap.get("ok"):
        store.save(f"gsc/{today}.json", snap)
    metrics = post_metrics(posts, snap, today)
    totals = site_totals(snap)
    analysis = {"posts": [], "working": [], "not_working": [], "refresh_queue": []}
    if snap.get("ok") and metrics:
        analysis = llm.call("analyst", "11_analyst.md", {
            "posts": metrics, "site_totals": totals, "experiments": store.load("experiments.json", []),
            "strategy": store.load("strategy.json"), "ctr_benchmark": CTR_BENCH, "cannibalisation": cannibalisation(snap),
            "cwv_or_crawl_notes": None}, ctx, max_tokens=10000)
    run.write("analysis.json", analysis)
    actions_done = apply_actions(run, ctx, analysis, metrics, posts)
    posts = store.load("posts.json")

    # 2. Report last week's post (T+7)
    send_results_email(run, ctx, posts, metrics, totals, analysis, actions_done)

    # 3. Plan
    strategy = store.load("strategy.json")
    ledger = store.load("topics_ledger.json", [])
    last_refresh = max([p.get("last_refreshed") or "" for p in posts] or [""]) or None
    plan = llm.call("director", "01_director.md", {
        "analysis": analysis, "strategy": strategy, "ledger_recent": ledger[-60:],
        "site_state": {"indexed_pages": sum(1 for p in posts if p.get("indexed")), "pages_in_sitemap": len(posts),
                       **({"last_28d": totals["last_28d"]} if totals.get("available") else {"gsc": "no data yet"})},
        "recent_formats": [p.get("format") for p in sorted(posts, key=lambda p: p.get("published") or "")[-4:]],
        "last_refresh_date": last_refresh}, ctx, max_tokens=4000)
    run.write("weekly_plan.json", plan)
    apply_strategy_changes(plan)
    ctx = shared_ctx(run.id, posts)

    # 4. Pick, brief, research (with fallbacks)
    mode = "REFRESH" if plan.get("deliverable") == "REFRESH" and plan.get("refresh_target_url") else "NEW"
    existing = None
    if mode == "REFRESH":
        target = next((p for p in posts if p["url"] == plan["refresh_target_url"] or config.SITE + p["url"] == plan["refresh_target_url"]), None)
        if not target:
            mode = "NEW"
        else:
            m = next((x for x in metrics if x["url"] == target["url"]), {})
            picks = [{"id": "refresh", "primary_keyword": (m.get("top_queries") or [{}])[0].get("query") or target.get("primary_keyword"),
                      "secondary_keywords": [q["query"] for q in (m.get("top_queries") or [])[1:6]],
                      "pillar": target.get("pillar"), "format": target.get("format") or "explainer",
                      "working_title": target["h1"], "why_this_one": "Analyst refresh queue",
                      "cornerstone_to_support": config.CORNERSTONES.get(target.get("pillar"))}]
            existing = {"existing_article": site.page_plain_text(target["file"]), "top_queries": m.get("top_queries")}
    if mode == "NEW":
        picks = choose_topics(run, ctx, plan, posts, snap)

    chosen = brief = pack = None
    for pick in picks:
        brief = brief_for(run, ctx, pick, posts, mode, existing)
        if not brief.get("thesis"):
            log_ledger(pick, "dropped", "no thesis found")
            continue
        pack = research(run, ctx, pick, brief)
        if len(pack.get("gaps_unfilled") or []) > 2 or not pack.get("facts"):
            log_ledger(pick, "dropped", "could not source the data")
            continue
        chosen = pick
        break
    if not chosen:
        return hold(run, "No topic this week had both a clear thesis and sourceable data.", None)

    # 5. Write and check
    strict = sum(1 for p in posts if p.get("origin") == "engine") < config.STRICT_WEEKS
    draft, gate, trail = write_and_check(run, ctx, chosen, brief, pack, strict,
                                         existing.get("existing_article") if existing else None)
    run.write("final_draft.md", draft)
    if gate.get("verdict") != "PASS":
        log_ledger(chosen, "held", gate.get("hold_reason"), retry_after=str(today + timedelta(days=14)))
        return hold(run, gate.get("hold_reason") or "The compliance gate did not pass the draft.", gate)

    # 6. Build
    target = next((p for p in posts if mode == "REFRESH" and p["url"] == plan.get("refresh_target_url")), None)
    page, info = build(run, ctx, draft, brief, chosen, pack, posts, mode,
                       existing_slug=target["slug"] if target else None,
                       published=target.get("published") if target else None)
    if page is None:
        return hold(run, f"Page failed validation twice: {info['errors']}", gate)

    record = {"slug": info["slug"], "url": f"/insights/{info['slug']}", "file": f"insights/{info['slug']}.html",
              "h1": info["title"], "dek": info["dek"], "category": info["category"], "read_minutes": info["read_minutes"],
              "words": info["words"], "pillar": chosen.get("pillar"), "cornerstone": False,
              "primary_keyword": chosen.get("primary_keyword"), "keywords": info["seo"].get("keywords"),
              "secondary_keywords": chosen.get("secondary_keywords"), "format": chosen.get("format"),
              "published": target.get("published") if target else str(today), "modified": str(today),
              "origin": "engine", "gate_rounds": trail.get("gate_rounds"), "experiment": (plan.get("experiment") or {}).get("id"),
              "facts_used": info["markers_used"], "links_out": [l["url"] for l in info["internal_links_applied"]],
              "links_in": info["inbound_links_added"], "indexed": None, "indexed_date": None,
              "refresh_count": (target.get("refresh_count", 0) + 1) if target else 0, "last_changed": str(today),
              "last_refreshed": str(today) if target else None, "reported_t7": False, "status": "pending"}
    posts = [p for p in posts if p["slug"] != record["slug"]] + [record]
    store.save("posts.json", posts)
    if plan.get("experiment") and plan["experiment"].get("id"):
        exps = store.load("experiments.json", [])
        if not any(e["id"] == plan["experiment"]["id"] for e in exps):
            exps.append({**plan["experiment"], "start": str(today), "post": record["url"], "verdict": None})
            store.save("experiments.json", exps)
    log_ledger(chosen, "published" if mode == "NEW" else "refreshed", None)
    run.write("trail.json", trail)
    state = run.set_state(status="READY", publish_ready=True, mode=mode, slug=info["slug"], url=info["url"],
                          title=info["title"], words=info["words"], trail=trail, pick=chosen,
                          brief_gaps=[g.get("gap") for g in brief.get("gaps", [])][:3], thesis=brief.get("thesis"),
                          inbound=info["inbound_links_added"], links_out=record["links_out"],
                          cost=llm.summary(), plan=plan)
    run.write("commit_message.txt", f"{'Publish' if mode == 'NEW' else 'Refresh'}: {info['title']}\n\n"
              f"Keyword: {chosen.get('primary_keyword')} | Pillar: {chosen.get('pillar')} | Format: {chosen.get('format')}\n"
              f"Gate rounds: {trail.get('gate_rounds')} | Run cost: ${llm.summary()['total_usd']}\n")
    return state


def log_ledger(pick, status, reason, retry_after=None):
    ledger = store.load("topics_ledger.json", [])
    ledger.append({"date": str(date.today()), "keyword": pick.get("primary_keyword"), "pillar": pick.get("pillar"),
                   "status": status, "reason": reason, "retry_after": retry_after})
    store.save("topics_ledger.json", ledger)


def apply_strategy_changes(plan):
    s = store.load("strategy.json")
    w = s["pillar_weights"]
    for ch in plan.get("strategy_changes") or []:
        field = ch.get("field", "")
        if field.startswith("pillar_weights.") and field.split(".")[1] in w:
            k = field.split(".")[1]
            try:
                to = float(ch.get("to"))
            except (TypeError, ValueError):
                continue
            to = max(0.08, min(w[k] + 0.10, max(w[k] - 0.10, to)))
            s["changes"].append({"date": str(date.today()), "field": field, "from": w[k], "to": round(to, 3), "reason": ch.get("reason")})
            w[k] = round(to, 3)
        elif field == "max_keyword_difficulty":
            try:
                s["max_keyword_difficulty"] = int(max(10, min(60, float(ch.get("to")))))
                s["changes"].append({"date": str(date.today()), **ch})
            except (TypeError, ValueError):
                pass
    total = sum(w.values())
    s["pillar_weights"] = {k: round(v / total, 3) for k, v in w.items()}
    store.save("strategy.json", s)


def apply_actions(run, ctx, analysis, metrics, posts):
    """Run the Analyst's automatic per-post actions (retitle, links). Refreshes go through the Director."""
    done = []
    eligible = {m["url"]: m for m in metrics if m["eligible_for_action"]}
    for a in analysis.get("posts", []):
        url = a.get("url", "").replace(config.SITE, "")
        m = eligible.get(url)
        post = next((p for p in posts if p["url"] == url), None)
        if not m or not post:
            continue
        act = a.get("action")
        try:
            if act == "retitle":
                r = llm.call("retitle", "11b_retitle.md", {
                    "url": url, "current_title_tag": site.read_post(post["file"])["title_tag"],
                    "current_meta_description": site.read_post(post["file"])["meta_description"],
                    "current_h1": post["h1"], "top_queries": m["top_queries"], "diagnosis": a.get("diagnosis"),
                    "change_h1": (m.get("metrics_28d") or {}).get("impressions", 0) < 20}, ctx, max_tokens=1500)
                if r.get("title_tag") and r.get("meta_description"):
                    site.apply_retitle(post["file"], r["title_tag"], r["meta_description"], r.get("h1"))
                    site.set_modified(post["file"], str(date.today()))
                    site.touch_sitemap([url], str(date.today()))
                    post["last_changed"] = str(date.today())
                    done.append({"url": url, "action": "retitle", "detail": r.get("rationale")})
            elif act == "links":
                draft = site.page_plain_text(post["file"])
                seo = llm.call("builder", "09_builder.md", {
                    "draft": draft, "brief": {}, "pick": {"pillar": post.get("pillar")}, "mode": "NEW",
                    "live_posts": [{"title": p["h1"], "url": p["url"], "pillar": p.get("pillar"), "file": p["file"],
                                    "indexed": p.get("indexed"),
                                    "linkable_sentences": site.linkable_sentences((config.ROOT / p["file"]).read_text(encoding="utf-8"))}
                                   for p in posts if p["url"] != url], "tools": []}, ctx, max_tokens=4000)
                added = []
                for e in seo.get("inbound_link_edits", [])[:2]:
                    if site.apply_inbound_edit(e, post["slug"]):
                        site.set_modified(e["file"], str(date.today()))
                        added.append("/" + e["file"].replace(".html", ""))
                if added:
                    site.touch_sitemap(added, str(date.today()))
                    post["last_changed"] = str(date.today())
                    post.setdefault("links_in", []).extend(added)
                    done.append({"url": url, "action": "links", "detail": f"links added from {', '.join(added)}"})
        except Exception as e:  # noqa: BLE001
            done.append({"url": url, "action": act, "detail": f"failed: {e}"})
    store.save("posts.json", posts)
    run.write("actions_done.json", done)
    return done


def hold(run, reason, gate):
    state = run.set_state(status="HOLD", publish_ready=False, reason=reason, cost=llm.summary())
    issues = (gate or {}).get("issues", [])
    rows = "".join(f"<li><b>{html.escape(i.get('severity',''))}</b> {html.escape(i.get('problem',''))}</li>" for i in issues[:10])
    ext.send_email("HOLD: no article this week",
                   f"<p style='font-family:Arial'>The engine stopped before publishing.</p>"
                   f"<p style='font-family:Arial'><b>Reason:</b> {html.escape(reason)}</p>"
                   + (f"<ul style='font-family:Arial'>{rows}</ul>" if rows else "")
                   + "<p style='font-family:Arial'>Next Monday's run continues normally; the topic will be retried in 14 days. "
                     f"Nothing needs your input.</p><p style='font-family:Arial;color:#777'>Run cost: ${llm.summary()['total_usd']}</p>")
    return state


# ---------------------------------------------------------------- emails
def _table(rows, head):
    th = "".join(f"<th style='border:1px solid #ddd;padding:6px;text-align:left'>{h}</th>" for h in head)
    trs = "".join("<tr>" + "".join(f"<td style='border:1px solid #ddd;padding:6px'>{html.escape(str(c))}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table style='border-collapse:collapse;font-family:Arial;font-size:13px'><tr>{th}</tr>{trs}</table>"


def send_results_email(run, ctx, posts, metrics, totals, analysis, actions_done):
    due = [p for p in posts if p.get("origin") == "engine" and not p.get("reported_t7") and p.get("published")
           and (date.today() - date.fromisoformat(p["published"])).days >= 6]
    if not due:
        return
    p = sorted(due, key=lambda x: x["published"])[-1]
    m = next((x for x in metrics if x["url"] == p["url"]), {})
    n_week = sum(1 for x in posts if x.get("origin") == "engine" and x.get("published") and x["published"] <= p["published"])
    data = {"kind": "results", "week_number": n_week, "post": {"title": p["h1"], "url": config.SITE + p["url"],
            "published": p["published"], "indexed": p.get("indexed"), "indexed_date": p.get("indexed_date"),
            "metrics_7d": m.get("metrics_7d"), "first_queries": (m.get("top_queries") or [])[:8],
            "next_checkpoint": str(date.fromisoformat(p["published"]) + timedelta(days=28))},
            "site": totals, "indexed_pages": sum(1 for x in posts if x.get("indexed")), "sitemap_pages": len(posts),
            "working": analysis.get("working"), "not_working": analysis.get("not_working"),
            "actions_taken": actions_done, "strategy_changes": store.load("strategy.json").get("changes", [])[-5:],
            "experiment_verdicts": analysis.get("experiment_verdicts")}
    try:
        out = llm.call("reporter", "12_reporter.md", data, ctx, max_tokens=6000)
        subject, body = out["subject"], out["html"]
    except Exception:  # noqa: BLE001
        subject = f"Week {n_week} results: {p['h1']}"
        body = "<pre style='font-family:monospace'>" + html.escape(json.dumps(data, indent=1)) + "</pre>"
    ext.send_email(subject, body)
    for x in posts:
        if x["slug"] == p["slug"]:
            x["reported_t7"] = True
    store.save("posts.json", posts)
    run.write("results_email.html", body)


def publish_email(state, page_html):
    t = state.get("trail", {})
    pick = state.get("pick", {})
    rp = t.get("reader_panel") or {}
    scores = t.get("editor_scores_final") or t.get("editor_scores") or {}
    cost = state.get("cost", {})
    prose = site.prose_html(page_html)
    url = config.SITE + f"/insights/{state['slug']}"
    parts = [
        f"<p style='font-family:Arial'><b>Live:</b> <a href='{url}'>{url}</a> (confirmed {state.get('live_at','')})</p>",
        f"<p style='font-family:Arial'><b>Why this topic:</b> keyword “{html.escape(pick.get('primary_keyword',''))}”, "
        f"pillar {pick.get('pillar')}, format {pick.get('format')}. {html.escape(pick.get('why_this_one',''))}</p>",
        f"<p style='font-family:Arial'><b>The so-what:</b> {html.escape(state.get('thesis') or '')}</p>",
        "<p style='font-family:Arial'><b>What it adds that the top 10 lack:</b></p><ul style='font-family:Arial'>"
        + "".join(f"<li>{html.escape(g or '')}</li>" for g in state.get("brief_gaps", [])) + "</ul>",
        _table([["Gate rounds", t.get("gate_rounds")], ["Issues fixed by revision", t.get("gate_issues_fixed")],
                ["Editor scores", ", ".join(f"{k} {v}" for k, v in scores.items())],
                ["Blind test vs your estate-tax post", f"more human: {'won' if rp.get('draft_won_human') else 'lost'}; "
                                                         f"teaches more: {'won' if rp.get('draft_won_teaching') else 'lost'}"],
                ["Words", state.get("words")], ["Links out", ", ".join(state.get("links_out") or []) or "none"],
                ["Older posts now linking to it", ", ".join(state.get("inbound") or []) or "none"],
                ["Sitemap / IndexNow submitted", f"{state.get('sitemap_submitted')} / {state.get('indexnow')}"],
                ["Run cost", f"${cost.get('total_usd')}"]], ["Item", "Detail"]),
        "<hr><h2 style='font-family:Arial'>" + html.escape(state["title"]) + "</h2>",
        f"<div style='font-family:Georgia,serif;font-size:15px;line-height:1.55;max-width:680px'>{prose}</div>",
    ]
    subject = ("Published: " if state.get("mode") == "NEW" else "Refreshed: ") + state["title"]
    ext.send_email(subject, "".join(parts), attachments=[(f"{state['slug']}.html", page_html.encode())])


# ---------------------------------------------------------------- post-publish stage
def post_publish(run, wait_seconds=600):
    st = run.state
    if not st.get("publish_ready"):
        return st
    url = config.SITE + f"/insights/{st['slug']}"
    page = (config.ROOT / f"insights/{st['slug']}.html").read_text(encoding="utf-8")
    title_bit = html.escape(st["title"])[:40]
    if config.DRY_RUN:
        st = run.set_state(status="DRY_RUN", live=False, indexnow="skipped (dry run)", sitemap_submitted="skipped (dry run)",
                           live_at="not published (dry run)")
        publish_email(st, page)
        return st
    live = False
    t0 = time.time()
    while time.time() - t0 < wait_seconds:
        code, body = ext.live_status(url)
        if code == 200 and title_bit in body:
            live = True
            break
        time.sleep(30)
    if not live:
        run.set_state(status="FAILED", live=False)
        ext.send_email("FAILED: article did not go live", f"<p style='font-family:Arial'>{html.escape(url)} did not "
                       "return the new page within 10 minutes of the push. The commit is being reverted; next week's run "
                       "continues normally.</p>")
        raise SystemExit(2)
    st = run.set_state(live=True, live_at=config.now_ist().strftime("%d %b %Y %H:%M IST"))
    key = (store.load("settings.json") or {}).get("indexnow_key")
    urls = [url, config.SITE + "/insights", config.SITE + "/sitemap.xml"] + [config.SITE + p for p in st.get("inbound") or []]
    st = run.set_state(indexnow=ext.indexnow(urls, key) if key else False, sitemap_submitted=ext.gsc_submit_sitemap())
    posts = store.load("posts.json")
    for p in posts:
        if p["slug"] == st["slug"]:
            p["status"] = "live"
    store.save("posts.json", posts)
    try:
        ctx = shared_ctx(run.id, posts)
        bank = store.load("perspectives.json", {"items": []})
        new = llm.call("perspective_bank", "00_perspective_bank.md",
                       {"pages": [{"url": f"/insights/{st['slug']}", "text": site.page_plain_text(f"insights/{st['slug']}.html")}],
                        "existing_bank": bank["items"], "mode": "append"}, ctx, max_tokens=3000)
        ids = {i["id"] for i in bank["items"]}
        bank["items"] += [i for i in new.get("items", []) if i.get("id") not in ids]
        store.save("perspectives.json", bank)
    except Exception as e:  # noqa: BLE001
        ext.log(f"perspective append failed: {e}")
    st = run.set_state(status="PUBLISHED", cost=llm.summary() if llm.COST["calls"] else st.get("cost"))
    publish_email(st, page)
    return st


# ---------------------------------------------------------------- daily index monitor
def daily_index():
    posts = store.load("posts.json") or []
    changed = False
    for p in posts:
        if p.get("indexed") or not p.get("published"):
            continue
        age = (date.today() - date.fromisoformat(p["published"][:10])).days
        if age > 45 and p.get("origin") == "manual":
            continue
        res = ext.gsc_inspect(config.SITE + p["url"])
        if not res:
            continue
        p["coverage"] = res.get("coverageState")
        if res.get("verdict") == "PASS":
            p["indexed"] = True
            p["indexed_date"] = str(date.today())
        changed = True
    if changed:
        store.save("posts.json", posts)
    return changed
