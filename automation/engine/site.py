"""Read and write the static site: existing posts, new article pages, the Insights index and the sitemap.

New pages are built from a live article used as the shell, so header, footer, CSS and analytics stay
identical to the rest of the site. Only the <head> SEO fields and the <main> block are generated.
"""
import html
import json
import re
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

import markdown as md_lib

from . import config
from .lint import split_front

AUTHORS = "Harsh Jain &amp; Harsh Bothra"


# ---------------------------------------------------------------- reading existing pages
def strip_tags(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def _ld(page):
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}


def _graph_nodes(ld):
    if "@graph" in ld:
        return ld["@graph"]
    return [ld] if ld else []


def article_node(page):
    for n in _graph_nodes(_ld(page)):
        t = n.get("@type")
        if t == "Article" or (isinstance(t, list) and "Article" in t):
            return n
    return {}


def prose_html(page):
    m = re.search(r'<article class="prose">(.*?)</article>', page, re.S)
    return m.group(1) if m else ""


def linkable_sentences(page, limit=40):
    """Sentences from plain paragraphs (no inline tags), safe targets for adding a link."""
    out = []
    for p in re.findall(r"<p>(.*?)</p>", prose_html(page), re.S):
        if "<" in p:
            continue
        text = html.unescape(p).strip()
        for s in re.split(r"(?<=[.!?])\s+", text):
            if 8 <= len(s.split()) <= 45:
                out.append(s)
    return out[:limit]


def read_post(rel):
    page = (config.ROOT / rel).read_text(encoding="utf-8")
    slug = Path(rel).stem
    art = article_node(page)
    h1 = re.search(r"<h1>(.*?)</h1>", page, re.S)
    lede = re.search(r'<p class="lede">(.*?)</p>', page, re.S)
    crumb = re.search(r'<p class="eyebrow crumb">(.*?)</p>', page, re.S)
    mins = re.search(r"(\d+) min read", page)
    title_tag = re.search(r"<title>(.*?)</title>", page, re.S)
    desc = re.search(r'<meta name="description" content="([^"]*)"', page)
    body_text = strip_tags(prose_html(page))
    return {
        "slug": slug, "file": rel, "url": f"/insights/{slug}",
        "h1": strip_tags(h1.group(1)) if h1 else slug,
        "dek": strip_tags(lede.group(1)) if lede else "",
        "category": strip_tags(crumb.group(1)).split("/")[-1].strip() if crumb else "",
        "read_minutes": int(mins.group(1)) if mins else None,
        "title_tag": html.unescape(title_tag.group(1)) if title_tag else "",
        "meta_description": html.unescape(desc.group(1)) if desc else "",
        "date_published": art.get("datePublished"), "date_modified": art.get("dateModified"),
        "keywords": art.get("keywords", ""), "words": len(body_text.split()),
        "body_excerpt": body_text[:1500],
    }


def all_posts_on_disk():
    return [read_post(f"insights/{p.name}") for p in sorted((config.ROOT / "insights").glob("*.html"))]


def site_tools():
    out = []
    for p in sorted((config.ROOT / "tools").glob("*.html")):
        page = p.read_text(encoding="utf-8")
        h1 = re.search(r"<h1>(.*?)</h1>", page, re.S)
        out.append({"url": f"/tools/{p.stem}", "title": strip_tags(h1.group(1)) if h1 else p.stem})
    return out


def page_plain_text(rel):
    page = (config.ROOT / rel).read_text(encoding="utf-8")
    m = re.search(r"<main[^>]*>(.*?)</main>", page, re.S)
    return strip_tags(m.group(1) if m else page)


# ---------------------------------------------------------------- markdown to article HTML
MARK = re.compile(r"\s?\[((?:F|C)\d+)\]")


def _wrap_tables(h):
    return re.sub(r"<table>(.*?)</table>", r'<div class="table-wrap"><table>\1</table></div>', h, flags=re.S)


def _link_phrases(body_html, links):
    """Wrap the first plain-text occurrence of each phrase (in a <p> or <li>) with a link."""
    applied = []
    for ln in links or []:
        phrase, url = (ln.get("phrase") or "").strip(), ln.get("url", "")
        if not phrase or not url.startswith("/"):
            continue
        esc = html.escape(phrase, quote=False)
        for m in re.finditer(re.escape(esc), body_html):
            before = body_html[:m.start()]
            last_open = re.findall(r"<(/?)(\w+)[^>]*>", before)
            stack = []
            for closing, tag in last_open:
                if closing:
                    if stack and stack[-1] == tag:
                        stack.pop()
                else:
                    stack.append(tag)
            if stack and stack[-1] in ("p", "li", "strong", "em", "b") and not ({"a", "h2", "h3", "td", "th"} & set(stack)):
                body_html = body_html[:m.start()] + f'<a href="{html.escape(url)}">{esc}</a>' + body_html[m.end():]
                applied.append(ln)
                break
    return body_html, applied


def render_body(md_body, facts, links):
    order = []
    for m in MARK.finditer(md_body):
        if m.group(1) not in order:
            order.append(m.group(1))
    text = MARK.sub("", md_body)
    h = md_lib.markdown(text, extensions=["tables", "sane_lists"])
    h = _wrap_tables(h)
    h, applied = _link_phrases(h, links)
    fact_by_id = {f["id"]: f for f in facts}
    src_items, seen = [], set()
    for fid in order:
        f = fact_by_id.get(fid)
        if not f or f.get("url") in seen:
            continue
        seen.add(f.get("url"))
        label = f"{f.get('publisher') or ''}: {f.get('page_title') or f.get('claim', '')[:70]}".strip(": ")
        src_items.append(f'<li><a href="{html.escape(f["url"])}" target="_blank" rel="noopener">{html.escape(label)}</a></li>')
    sources = ""
    if src_items:
        sources = '<h2>Sources</h2><ul class="sources-list">' + "".join(src_items) + "</ul>"
        if any(x.startswith("C") for x in order):
            sources += "<p>Worked examples are Meridian Capital calculations using the sources above.</p>"
    return h, sources, applied, order


def faq_pairs(md_body):
    m = re.search(r"^##\s+Questions readers ask\s*$(.*?)(?=^##\s|\Z)", md_body, re.M | re.S)
    if not m:
        return []
    pairs = []
    for q, a in re.findall(r"^###\s+(.+?)\s*$\n(.*?)(?=^###\s|\Z)", m.group(1), re.M | re.S):
        ans = MARK.sub("", a).strip()
        ans = re.sub(r"\s+", " ", ans)
        if ans:
            pairs.append((MARK.sub("", q).strip(), strip_tags(md_lib.markdown(ans))))
    return pairs


def _month(d):
    return date.fromisoformat(d).strftime("%B %Y")


def keyfigs_html(meta):
    try:
        figs = json.loads(meta.get("keyfigs", "[]"))
    except json.JSONDecodeError:
        return ""
    cells = "".join(f'<div><b>{html.escape(str(f.get("value","")))}</b><span>{html.escape(str(f.get("label","")))}</span></div>'
                    for f in figs[:3] if f.get("value"))
    return f'<div class="keyfigs">{cells}</div>' if cells else ""


def post_card(p):
    return (f'<a class="post" href="{p["url"]}"><span class="n">{html.escape(p.get("category") or "")}</span>'
            f'<div><h3>{html.escape(p["h1"])}</h3><p>{html.escape(p.get("dek") or "")}</p></div>'
            f'<span class="meta">{p.get("read_minutes") or 5} min read</span></a>')


def build_article(*, draft_md, seo, facts, posts, published, modified, slug):
    """Return (page_html, info). posts = list of read_post dicts for Keep reading."""
    meta, body = split_front(draft_md)
    url = f"{config.SITE}/insights/{slug}"
    title = meta.get("title", "").strip()
    dek = meta.get("dek", "").strip()
    category = meta.get("category", "Insights").strip()
    words = len(re.findall(r"\w+", MARK.sub("", body)))
    minutes = max(3, round(words / 230))
    body_html, sources_html, applied, order = render_body(body, facts, seo.get("internal_links"))
    faqs = faq_pairs(body)

    shell_path = config.ROOT / config.STYLE_REFERENCE
    shell = shell_path.read_text(encoding="utf-8")
    head, rest = shell.split("</head>", 1)
    old_url = re.search(r'<link rel="canonical" href="([^"]+)"', head).group(1)
    head = head.replace(old_url, url)
    t_tag = html.escape(seo["title_tag"], quote=True)
    d_tag = html.escape(seo["meta_description"], quote=True)
    head = re.sub(r"<title>.*?</title>", f"<title>{t_tag}</title>", head, flags=re.S)
    for pat in (r'(<meta name="description" content=")[^"]*(")', r'(<meta property="og:description" content=")[^"]*(")',
                r'(<meta name="twitter:description" content=")[^"]*(")'):
        head = re.sub(pat, lambda m: m.group(1) + d_tag + m.group(2), head)
    for pat in (r'(<meta property="og:title" content=")[^"]*(")', r'(<meta name="twitter:title" content=")[^"]*(")'):
        head = re.sub(pat, lambda m: m.group(1) + t_tag + m.group(2), head)
    head = re.sub(r'(<meta property="article:published_time" content=")[^"]*(")', lambda m: m.group(1) + published + m.group(2), head)
    head = re.sub(r'(<meta property="article:modified_time" content=")[^"]*(")', lambda m: m.group(1) + modified + m.group(2), head)

    shared_nodes = [n for n in _graph_nodes(_ld(shell))
                    if n.get("@type") in ("Person",) or (isinstance(n.get("@type"), list) and "Organization" in n["@type"])
                    or n.get("@type") == "Organization"]
    graph = [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": config.SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": "Insights", "item": config.SITE + "/insights"},
            {"@type": "ListItem", "position": 3, "name": title.rstrip("."), "item": url}]},
        {"@type": "Article", "@id": url + "#article", "headline": title, "description": seo["meta_description"],
         "mainEntityOfPage": url, "image": config.SITE + "/assets/og-image.jpg", "datePublished": published,
         "dateModified": modified, "author": [{"@id": config.SITE + "/about#harsh-jain"}, {"@id": config.SITE + "/about#harsh-bothra"}],
         "publisher": {"@id": config.SITE + "/#organization"}, "inLanguage": "en-IN", "articleSection": category,
         "keywords": seo.get("keywords", ""), "wordCount": words},
    ] + shared_nodes
    if faqs:
        graph.append({"@type": "FAQPage", "@id": url + "#faq", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs]})
    ld = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False)
    head = re.sub(r'<script type="application/ld\+json">.*?</script>', lambda m: f'<script type="application/ld+json">{ld}</script>', head, flags=re.S)

    keep = [p for p in posts if p["url"] in (seo.get("keep_reading") or []) and p["slug"] != slug][:3]
    if len(keep) < 3:
        keep += [p for p in posts if p not in keep and p["slug"] != slug][: 3 - len(keep)]
    cta = seo.get("tool_cta") or {}
    cta_html = (f'<a class="more" href="{html.escape(cta["url"])}">{html.escape(cta.get("label") or "Try the tool →")}</a>'
                if cta.get("url") else "")
    main = (
        '<main id="top">\n'
        f'<section class="ph article-head"><div class="wrap"><p class="eyebrow crumb"><a href="/">Home</a> / <a href="/insights">Insights</a> / {html.escape(category)}</p>'
        f'<h1>{html.escape(title)}</h1><p class="lede">{html.escape(dek)}</p>'
        f'<p class="meta">By {AUTHORS} · {_month(published)} · {minutes} min read</p>{keyfigs_html(meta)}</div></section>\n'
        '<section class="band band-paper" style="padding-top:clamp(56px,8vw,100px)"><div class="wrap"><article class="prose">\n'
        f'{body_html}\n{sources_html}</article>\n'
        f'<div class="article-end">{cta_html}<a class="btn" href="/contact">Let’s talk <span class="arr">→</span></a></div></div></section>\n'
        '<section class="band"><div class="wrap"><h2 style="font-size:clamp(32px,4vw,56px)">Keep reading.</h2><div class="posts">'
        + "".join(post_card(p) for p in keep) + '</div></div></section>\n</main>'
    )
    rest = re.sub(r'<main id="top">.*?</main>', lambda m: main, rest, flags=re.S)
    page = head + "</head>" + rest
    info = {"title": title, "dek": dek, "category": category, "read_minutes": minutes, "words": words,
            "faq_count": len(faqs), "internal_links_applied": applied, "markers_used": order, "url": url}
    return page, info


# ---------------------------------------------------------------- index, sitemap, edits
def add_index_card(card_post):
    p = config.ROOT / "insights.html"
    s = p.read_text(encoding="utf-8")
    if f'href="{card_post["url"]}"' in s:
        return False
    anchor = '<div class="posts" style="margin-top:0">'
    if anchor not in s:
        raise RuntimeError("Insights index layout changed: card anchor not found")
    s = s.replace(anchor, anchor + post_card(card_post), 1)
    p.write_text(s, encoding="utf-8")
    return True


def touch_sitemap(paths_modified, today, new_path=None):
    p = config.ROOT / "sitemap.xml"
    s = p.read_text(encoding="utf-8")
    if new_path and f"<loc>{config.SITE}{new_path}</loc>" not in s:
        line = (f"  <url><loc>{config.SITE}{new_path}</loc><lastmod>{today}</lastmod>"
                f"<changefreq>monthly</changefreq><priority>0.7</priority></url>\n")
        marker = f"<loc>{config.SITE}/insights</loc>"
        i = s.find(marker)
        if i >= 0:
            j = s.find("</url>", i) + len("</url>\n")
            s = s[:j] + line + s[j:]
        else:
            s = s.replace("</urlset>", line + "</urlset>")
    for path in set(paths_modified) | ({new_path} if new_path else set()) | {"/insights"}:
        loc = f"<loc>{config.SITE}{path}</loc><lastmod>"
        s = re.sub(re.escape(loc) + r"[^<]*", loc + today, s)
    p.write_text(s, encoding="utf-8")


def set_modified(rel, today):
    p = config.ROOT / rel
    s = p.read_text(encoding="utf-8")
    s = re.sub(r'(<meta property="article:modified_time" content=")[^"]*(")', lambda m: m.group(1) + today + m.group(2), s)
    s = re.sub(r'("dateModified":\s*")[^"]*(")', lambda m: m.group(1) + today + m.group(2), s)
    p.write_text(s, encoding="utf-8")


def apply_inbound_edit(edit, new_slug):
    """Add one link from an existing post to the new one. Returns True if applied."""
    rel = edit.get("file", "")
    if not re.fullmatch(r"insights/[a-z0-9-]+\.html", rel) or not (config.ROOT / rel).exists():
        return False
    find, repl = edit.get("find", ""), edit.get("replace", "").replace("NEW-SLUG", new_slug)
    am = re.fullmatch(r'(.*?)<a href="(/insights/[a-z0-9-]+)">(.+?)</a>(.*)', repl, re.S)
    if not am or am.group(2) != f"/insights/{new_slug}":
        return False
    if am.group(1) + am.group(3) + am.group(4) != find:
        return False                                   # the edit changed more than the link
    p = config.ROOT / rel
    page = p.read_text(encoding="utf-8")
    prose = prose_html(page)
    for para in re.findall(r"<p>(.*?)</p>", prose, re.S):
        if "<" in para:
            continue
        plain = html.unescape(para)
        if plain.count(find) != 1:
            continue
        pre, post = plain.split(find)
        new_para = (html.escape(pre, quote=False) + html.escape(am.group(1), quote=False)
                    + f'<a href="/insights/{new_slug}">{html.escape(am.group(3), quote=False)}</a>'
                    + html.escape(am.group(4), quote=False) + html.escape(post, quote=False))
        new_prose = prose.replace(f"<p>{para}</p>", f"<p>{new_para}</p>", 1)
        page = page.replace(prose, new_prose, 1)
        p.write_text(page, encoding="utf-8")
        return True
    return False


def apply_retitle(rel, title_tag, meta_description, h1=None):
    p = config.ROOT / rel
    s = p.read_text(encoding="utf-8")
    t, d = html.escape(title_tag, quote=True), html.escape(meta_description, quote=True)
    s = re.sub(r"<title>.*?</title>", f"<title>{t}</title>", s, flags=re.S)
    for pat in (r'(<meta name="description" content=")[^"]*(")', r'(<meta property="og:description" content=")[^"]*(")',
                r'(<meta name="twitter:description" content=")[^"]*(")'):
        s = re.sub(pat, lambda m: m.group(1) + d + m.group(2), s)
    for pat in (r'(<meta property="og:title" content=")[^"]*(")', r'(<meta name="twitter:title" content=")[^"]*(")'):
        s = re.sub(pat, lambda m: m.group(1) + t + m.group(2), s)
    s = re.sub(r'("@type": "Article".*?"description": ")[^"]*(")', lambda m: m.group(1) + d.replace('"', "") + m.group(2), s, count=1, flags=re.S)
    if h1:
        s = re.sub(r"<h1>.*?</h1>", f"<h1>{html.escape(h1)}</h1>", s, count=1, flags=re.S)
        s = re.sub(r'("@type": "Article".*?"headline": ")[^"]*(")', lambda m: m.group(1) + h1.replace('"', "") + m.group(2), s, count=1, flags=re.S)
    p.write_text(s, encoding="utf-8")


# ---------------------------------------------------------------- validation
class _Checker(HTMLParser):
    def __init__(self):
        super().__init__()
        self.h1 = 0
        self.hrefs = []
        self.canonical = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "h1":
            self.h1 += 1
        if tag == "a" and a.get("href"):
            self.hrefs.append(a["href"])
        if tag == "link" and a.get("rel") == "canonical":
            self.canonical = True


def resolve_internal(href):
    path = href.split("#")[0].split("?")[0]
    if not path.startswith("/") or path.startswith("//"):
        return True
    if path == "/":
        return (config.ROOT / "index.html").exists()
    rel = path.lstrip("/")
    cands = [config.ROOT / rel, config.ROOT / (rel + ".html"), config.ROOT / rel / "index.html"]
    if any(c.exists() for c in cands):
        return True
    redirects = (config.ROOT / "_redirects").read_text(encoding="utf-8") if (config.ROOT / "_redirects").exists() else ""
    return any(line.split()[0] == path for line in redirects.splitlines() if line.strip())


def validate_page(page_html):
    errors = []
    c = _Checker()
    try:
        c.feed(page_html)
    except Exception as e:  # noqa: BLE001
        errors.append(f"HTML parse error: {e}")
    if c.h1 != 1:
        errors.append(f"{c.h1} H1 elements (need exactly 1)")
    if not c.canonical:
        errors.append("canonical link missing")
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', page_html, re.S)
    try:
        ld = json.loads(m.group(1)) if m else None
        types = {n.get("@type") if isinstance(n.get("@type"), str) else "Org" for n in ld["@graph"]}
        for need in ("Article", "BreadcrumbList"):
            if need not in types:
                errors.append(f"schema missing {need}")
    except Exception as e:  # noqa: BLE001
        errors.append(f"JSON-LD invalid: {e}")
    bad = [h for h in c.hrefs if not resolve_internal(h)]
    if bad:
        errors.append(f"broken internal links: {bad}")
    if len(page_html.encode()) > 300_000:
        errors.append("page over 300 KB")
    title = re.search(r"<title>(.*?)</title>", page_html, re.S)
    if not title or len(html.unescape(title.group(1))) > 65:
        errors.append("title tag missing or over 65 characters")
    desc = re.search(r'<meta name="description" content="([^"]*)"', page_html)
    if not desc or not (110 <= len(html.unescape(desc.group(1))) <= 165):
        errors.append("meta description missing or outside 110-165 characters")
    return errors
