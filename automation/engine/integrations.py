"""External services: Search Console, DataForSEO, news feeds, page fetching, IndexNow, email."""
import base64
import html
import json
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

import requests

from . import config

UA = "Mozilla/5.0 (compatible; MeridianContentBot/1.0; +https://meridiancapital.in)"
LOG = []


def log(msg):
    LOG.append(msg)
    print(msg, flush=True)


# ---------------------------------------------------------------- Search Console
_gsc = None


def gsc_session():
    global _gsc
    if _gsc is None:
        if not config.GSC_SA_JSON:
            return None
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
        info = json.loads(config.GSC_SA_JSON)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/webmasters"])
        _gsc = AuthorizedSession(creds)
    return _gsc


def gsc_query(start, end, dimensions, row_limit=25000, filters=None):
    s = gsc_session()
    if not s:
        return []
    url = f"https://www.googleapis.com/webmasters/v3/sites/{quote(config.GSC_SITE, safe='')}/searchAnalytics/query"
    body = {"startDate": str(start), "endDate": str(end), "dimensions": dimensions, "rowLimit": row_limit}
    if filters:
        body["dimensionFilterGroups"] = [{"filters": filters}]
    r = s.post(url, json=body, timeout=60)
    r.raise_for_status()
    return r.json().get("rows", [])


def gsc_snapshot():
    """90 days of page x query and page x date data. Search Console data lags ~2-3 days."""
    end = date.today() - timedelta(days=2)
    start = end - timedelta(days=89)
    snap = {"end": str(end), "start": str(start)}
    try:
        snap["page_query"] = gsc_query(start, end, ["page", "query"])
        snap["page_date"] = gsc_query(start, end, ["page", "date"])
        snap["query_28d"] = gsc_query(end - timedelta(days=27), end, ["query"], 5000)
        snap["ok"] = True
    except Exception as e:  # noqa: BLE001
        log(f"GSC snapshot failed: {e}")
        snap["ok"] = False
        snap["error"] = str(e)
    return snap


def gsc_submit_sitemap():
    s = gsc_session()
    if not s:
        return False
    feed = quote(config.SITE + "/sitemap.xml", safe="")
    url = f"https://www.googleapis.com/webmasters/v3/sites/{quote(config.GSC_SITE, safe='')}/sitemaps/{feed}"
    r = s.put(url, timeout=60)
    log(f"GSC sitemap submit: HTTP {r.status_code}")
    return r.status_code in (200, 204)


def gsc_inspect(page_url):
    s = gsc_session()
    if not s:
        return None
    r = s.post("https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",
               json={"inspectionUrl": page_url, "siteUrl": config.GSC_SITE}, timeout=60)
    if r.status_code != 200:
        log(f"URL inspection {page_url}: HTTP {r.status_code} {r.text[:200]}")
        return None
    res = r.json().get("inspectionResult", {}).get("indexStatusResult", {})
    return {"verdict": res.get("verdict"), "coverageState": res.get("coverageState"),
            "lastCrawlTime": res.get("lastCrawlTime"), "googleCanonical": res.get("googleCanonical")}


# ---------------------------------------------------------------- DataForSEO
def _d4s(endpoint, payload):
    if not (config.DATAFORSEO_LOGIN and config.DATAFORSEO_PASSWORD):
        return None
    r = requests.post("https://api.dataforseo.com/v3/" + endpoint, json=payload,
                      auth=(config.DATAFORSEO_LOGIN, config.DATAFORSEO_PASSWORD), timeout=120)
    r.raise_for_status()
    data = r.json()
    task = (data.get("tasks") or [{}])[0]
    if task.get("status_code") not in (20000, None):
        log(f"DataForSEO {endpoint}: {task.get('status_code')} {task.get('status_message')}")
        return None
    return task.get("result") or []


def keyword_ideas(seeds, limit=400):
    """Volume, difficulty and intent for keyword ideas around the seed terms (Google India, English)."""
    try:
        res = _d4s("dataforseo_labs/google/keyword_ideas/live",
                   [{"keywords": seeds[:200], "location_code": 2356, "language_code": "en",
                     "limit": limit, "include_serp_info": False,
                     "filters": [["keyword_info.search_volume", ">", 0]],
                     "order_by": ["keyword_info.search_volume,desc"]}])
    except Exception as e:  # noqa: BLE001
        log(f"keyword_ideas failed: {e}")
        return []
    out = []
    for r in res or []:
        for it in r.get("items") or []:
            ki = it.get("keyword_info") or {}
            kp = it.get("keyword_properties") or {}
            si = it.get("search_intent_info") or {}
            trend = ki.get("search_volume_trend") or {}
            out.append({"keyword": it.get("keyword"), "volume": ki.get("search_volume"),
                        "kd": kp.get("keyword_difficulty"), "cpc": ki.get("cpc"),
                        "intent": si.get("main_intent"), "trend_yearly": trend.get("yearly")})
    return out


def keyword_overview(keywords):
    """Exact metrics for specific keywords (used for Search Console queries)."""
    if not keywords:
        return {}
    try:
        res = _d4s("dataforseo_labs/google/keyword_overview/live",
                   [{"keywords": keywords[:700], "location_code": 2356, "language_code": "en"}])
    except Exception as e:  # noqa: BLE001
        log(f"keyword_overview failed: {e}")
        return {}
    out = {}
    for r in res or []:
        for it in r.get("items") or []:
            ki = it.get("keyword_info") or {}
            kp = it.get("keyword_properties") or {}
            out[it.get("keyword")] = {"volume": ki.get("search_volume"), "kd": kp.get("keyword_difficulty")}
    return out


def trends_rising(terms):
    try:
        res = _d4s("keywords_data/google_trends/explore/live",
                   [{"keywords": terms[:5], "location_code": 2356, "time_range": "past_7_days",
                     "type": "web", "item_types": ["google_trends_queries_list"]}])
    except Exception as e:  # noqa: BLE001
        log(f"trends failed: {e}")
        return []
    out = []
    for r in res or []:
        for it in r.get("items") or []:
            data = it.get("data") or {}
            for q in (data.get("rising") or [])[:15]:
                out.append({"query": q.get("query"), "value": q.get("value")})
    return out


def serp(keyword):
    res = _d4s("serp/google/organic/live/advanced",
               [{"keyword": keyword, "location_code": 2356, "language_code": "en", "depth": 10,
                 "device": "mobile"}])
    out = {"organic": [], "people_also_ask": [], "featured_snippet": None, "related_searches": []}
    for r in res or []:
        for it in r.get("items") or []:
            t = it.get("type")
            if t == "organic" and len(out["organic"]) < 10:
                out["organic"].append({"rank": it.get("rank_group"), "url": it.get("url"),
                                       "title": it.get("title"), "description": it.get("description"),
                                       "domain": it.get("domain"), "timestamp": it.get("timestamp")})
            elif t == "people_also_ask":
                for q in it.get("items") or []:
                    out["people_also_ask"].append(q.get("title"))
            elif t == "featured_snippet":
                out["featured_snippet"] = {"url": it.get("url"), "description": it.get("description"),
                                           "title": it.get("title")}
            elif t == "related_searches":
                out["related_searches"].extend(it.get("items") or [])
    return out


# ---------------------------------------------------------------- news + page fetching
def news_items(days=10):
    import feedparser
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    items = []
    for feed in config.NEWS_FEEDS:
        try:
            r = requests.get(feed, headers={"User-Agent": UA}, timeout=30)
            parsed = feedparser.parse(r.content)
        except Exception as e:  # noqa: BLE001
            log(f"feed failed {feed}: {e}")
            continue
        for e in parsed.entries[:60]:
            title = html.unescape(e.get("title", ""))
            summary = re.sub("<[^>]+>", " ", html.unescape(e.get("summary", "")))[:400]
            when = e.get("published_parsed") or e.get("updated_parsed")
            if when:
                dt = datetime(*when[:6], tzinfo=timezone.utc)
                if dt < cutoff:
                    continue
            blob = (title + " " + summary).lower()
            if any(k in blob for k in config.NEWS_KEYWORDS):
                items.append({"title": title, "summary": summary.strip(), "url": e.get("link"),
                              "date": dt.date().isoformat() if when else None, "feed": feed})
    return items[:80]


def fetch_page(url, max_chars=15000):
    """Plain-text extraction of a result page for the SERP analyst."""
    from bs4 import BeautifulSoup
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
            return {"url": url, "error": f"HTTP {r.status_code}"}
        soup = BeautifulSoup(r.text, "html.parser")
        for t in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
            t.decompose()
        title = soup.title.get_text(strip=True) if soup.title else ""
        heads = [f"{h.name}: {h.get_text(' ', strip=True)}" for h in soup.find_all(["h1", "h2", "h3"])][:60]
        body = soup.find("article") or soup.find("main") or soup.body or soup
        text = re.sub(r"\s+", " ", body.get_text(" ", strip=True))
        dates = sorted(set(re.findall(r'"(?:datePublished|dateModified)"\s*:\s*"([^"]+)"', r.text)))
        tables = len(soup.find_all("table"))
        return {"url": url, "title": title, "headings": heads, "word_count": len(text.split()),
                "dates": dates[:4], "tables": tables, "text_excerpt": text[:max_chars]}
    except Exception as e:  # noqa: BLE001
        return {"url": url, "error": str(e)[:200]}


def page_text(url, max_chars=20000):
    p = fetch_page(url, max_chars)
    return p.get("text_excerpt", "") if "error" not in p else ""


def live_status(url):
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"}, timeout=30)
        return r.status_code, r.text
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


# ---------------------------------------------------------------- IndexNow + email
def indexnow(urls, key):
    payload = {"host": config.HOST, "key": key, "keyLocation": f"{config.SITE}/{key}.txt", "urlList": urls}
    try:
        r = requests.post("https://api.indexnow.org/indexnow", json=payload, timeout=30)
        log(f"IndexNow: HTTP {r.status_code} for {len(urls)} URLs")
        return r.status_code in (200, 202)
    except Exception as e:  # noqa: BLE001
        log(f"IndexNow failed: {e}")
        return False


def send_email(subject, html_body, attachments=None):
    """attachments: list of (filename, bytes). Returns True on success."""
    if config.DRY_RUN:
        subject = "[DRY RUN] " + subject
    if not (config.RESEND_API_KEY and config.REPORT_EMAIL):
        log(f"(email not configured) would send: {subject}")
        return False
    body = {"from": config.MAIL_FROM, "to": [e.strip() for e in config.REPORT_EMAIL.split(",")],
            "subject": subject, "html": html_body}
    if attachments:
        body["attachments"] = [{"filename": n, "content": base64.b64encode(b).decode()} for n, b in attachments]
    r = requests.post("https://api.resend.com/emails", json=body,
                      headers={"Authorization": f"Bearer {config.RESEND_API_KEY}"}, timeout=60)
    log(f"Email '{subject}': HTTP {r.status_code}")
    return r.status_code in (200, 201)
