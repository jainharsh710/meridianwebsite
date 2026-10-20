"""Mechanical checks on a Markdown draft: banned phrases, rhythm, readability, numbers, markers."""
import re
import statistics

BANNED = [
    r"\bdelve", r"\blandscape\b", r"\bnavigat(e|es|ing)\b", r"\bcrucial\b", r"\bpivotal\b", r"\brobust\b",
    r"\bseamless(ly)?\b", r"\bunlock", r"\bempower", r"\belevate", r"\bleverag(e|es|ing)\b(?!d)",
    r"\bgame[- ]changer", r"\btapestry\b", r"\brealm\b", r"\bembark", r"\binvesting journey\b",
    r"\bjourney\b", r"\bmoreover\b", r"\bfurthermore\b", r"(^|[.!?]\s+)Additionally,", r"\bnotably\b",
    r"it'?s important to note", r"it'?s worth noting", r"fast-paced world", r"ever-evolving",
    r"whether you'?re\b.{0,40}\bor\b", r"look no further", r"comprehensive guide", r"\bdive into\b",
    r"let'?s explore", r"in conclusion", r"to sum up", r"at the end of the day", r"the bottom line is",
    r"in this article,? we", r"this article (will|explores|covers)",
]

DISCLAIMER = ("This article is for education only and is not investment, tax or legal advice. "
              "Rules change; check your own situation with a qualified professional.")


def split_front(md):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", md.strip(), re.S)
    if not m:
        return {}, md
    front, body = m.group(1), m.group(2)
    meta = {}
    for line in front.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, body


def prose_only(body):
    lines = []
    for ln in body.splitlines():
        s = ln.strip()
        if s.startswith("|") or s.startswith("#") or not s:
            lines.append("")
            continue
        lines.append(re.sub(r"\[(F|C)\d+\]", "", s))
    return "\n".join(lines)


def sentences(text):
    text = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z₹$\"'(])", text)
    return [p.strip() for p in parts if len(p.strip().split()) >= 2]


def syllables(word):
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups)
    if w.endswith("e") and n > 1 and not w.endswith("le"):
        n -= 1
    return max(1, n)


def flesch(text):
    sents = sentences(text)
    words = re.findall(r"[A-Za-z']+", text)
    if not sents or not words:
        return None
    syl = sum(syllables(w) for w in words)
    return round(206.835 - 1.015 * (len(words) / len(sents)) - 84.6 * (syl / len(words)), 1)


NUM_RE = re.compile(r"(?<![\w.])(?:₹|\$|US\$)?\d[\d,]*(?:\.\d+)?(?:\s?(?:%|lakh|crore|million|billion|bn|k))?", re.I)


def numbers(text):
    clean = re.sub(r"\[(F|C)\d+\]", "", text)
    return [n.strip() for n in NUM_RE.findall(clean)]


def norm_num(n):
    n = n.lower().replace(",", "").replace(" ", "").replace("us$", "$")
    return n


def lint(md):
    meta, body = split_front(md)
    prose = prose_only(body)
    issues = []
    lower = body.lower()
    for pat in BANNED:
        for m in re.finditer(pat, body, re.I | re.M):
            issues.append({"type": "banned", "text": body[max(0, m.start() - 30): m.end() + 30].replace("\n", " ")})
    dashes = body.count("—")
    if dashes > 2:
        issues.append({"type": "em_dashes", "text": f"{dashes} em dashes (max 2)"})
    if "!" in prose:
        issues.append({"type": "exclamation", "text": "exclamation mark found"})
    sents = sentences(prose)
    lengths = [len(s.split()) for s in sents]
    sd = round(statistics.pstdev(lengths), 1) if len(lengths) > 3 else None
    if sd is not None and sd < 6:
        issues.append({"type": "rhythm", "text": f"sentence-length spread {sd} words (want > 6)"})
    for para in [p for p in prose.split("\n") if p.strip()]:
        n = len(sentences(para))
        if n > 3:
            issues.append({"type": "long_paragraph", "text": para[:90] + "..."})
    openers = [s.split()[0].lower() for s in sents if s.split()]
    for i in range(len(openers) - 2):
        if openers[i] == openers[i + 1] == openers[i + 2]:
            issues.append({"type": "repeated_openers", "text": f"three sentences in a row start with '{openers[i]}'"})
    fre = flesch(prose)
    if fre is not None and not (45 <= fre <= 70):
        issues.append({"type": "readability", "text": f"Flesch reading ease {fre} (target 50-65)"})
    bullets = [ln for ln in body.splitlines() if re.match(r"^\s*[-*]\s+\*\*", ln)]
    all_bullets = [ln for ln in body.splitlines() if re.match(r"^\s*[-*]\s+", ln)]
    if len(all_bullets) >= 4 and len(bullets) == len(all_bullets):
        issues.append({"type": "bold_bullets", "text": "every bullet starts with a bold phrase"})
    if DISCLAIMER.lower()[:60] not in lower:
        issues.append({"type": "disclaimer", "text": "standard disclaimer missing"})
    if len(meta.get("title", "")) > 62:
        issues.append({"type": "title_length", "text": f"title is {len(meta.get('title', ''))} characters"})
    words = len(re.findall(r"\w+", prose))
    return {"issues": issues, "stats": {"words": words, "sentence_sd": sd, "flesch": fre,
                                         "em_dashes": dashes, "sentences": len(sents)}}


def mechanical_checks(md, source_pack):
    """Numbers and markers that can't be traced to the source pack."""
    meta, body = split_front(md)
    fact_ids = {f["id"] for f in source_pack.get("facts", [])}
    calc_ids = {c["id"] for c in source_pack.get("calc_outputs", [])}
    unverified = {f["id"] for f in source_pack.get("facts", []) if f.get("status") != "verified"}
    markers = set(re.findall(r"\[((?:F|C)\d+)\]", md))
    unknown = sorted(m for m in markers if m not in fact_ids | calc_ids)
    used_unverified = sorted(m for m in markers if m in unverified)
    corpus = " ".join([f.get("quote", "") + " " + f.get("claim", "") for f in source_pack.get("facts", [])]
                      + [c.get("output", "") for c in source_pack.get("calc_outputs", [])]
                      + [str(source_pack.get("illustrative_household") or "")])
    known = {norm_num(n) for n in numbers(corpus)}
    known_bare = {re.sub(r"[^\d.]", "", k) for k in known}
    unmatched = []
    for n in numbers(body + " " + " ".join(meta.values())):
        k = norm_num(n)
        bare = re.sub(r"[^\d.]", "", k)
        if not bare:
            continue
        try:
            val = float(bare)
        except ValueError:
            continue
        if val <= 31 and "%" not in k and "$" not in k and "₹" not in k:
            continue                      # small counts: "3 steps", "7 days"
        if 1900 <= val <= 2100 and "%" not in k and "$" not in k and "₹" not in k:
            continue                      # years
        if k in known or bare in known_bare:
            continue
        unmatched.append(n)
    return {"unknown_markers": unknown, "unverified_markers_used": used_unverified,
            "unmatched_numbers": sorted(set(unmatched)),
            "disclaimer_present": DISCLAIMER.lower()[:60] in body.lower()}
