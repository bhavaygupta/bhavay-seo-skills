#!/usr/bin/env python3
"""Competitor teardown and coverage map for the bhavay-content-brief skill.

Fetches each ranking or AI-cited URL politely, extracts what a brief needs, then
clusters every H2 and H3 across pages into topics and counts how many pages
cover each topic.

Per page: title, H1, H2 and H3 headings, word count, JSON-LD schema types,
FAQ questions, and statistic sentences with the link nearest to each.

Coverage tiers scale with the number of pages read. With 10 pages they match
the skill: 7 or more pages is must-cover, 3 to 6 is recommended, 1 or 2 is an
optional angle.

Clustering uses sentence-transformers (BAAI/bge-small-en-v1.5) when installed,
otherwise TF-IDF with scikit-learn, otherwise pure-Python token overlap.

Examples:
  python3 teardown.py --urls serp_urls.txt --out-prefix brief/teardown
  python3 teardown.py --urls serp_urls.txt --headings-csv extra_headings.csv --backend overlap
  python3 teardown.py --from-json brief/teardown.json --threshold 0.5   # recluster without refetching

Outputs:
  <prefix>.json          everything extracted per page
  <prefix>_coverage.csv  topic, tier, pages_covering, share, example headings, urls
  <prefix>_stats.csv     statistic sentences with source links, for verification
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

UA = "SEO-AEO-Brief/1.0 (+https://bhavay.com/resources/skills/bhavay-content-brief)"
STOP = set("""a an and are as at be by for from how in into is it its of on or that the this to vs what when where
which who why will with your you our we can do does best top guide 2024 2025 2026 2027""".split())
DEFAULT_THRESHOLDS = {"sentence-transformers": 0.78, "tfidf": 0.35, "overlap": 0.35}
STAT = re.compile(r"(\d[\d,.]*\s?(%|percent|x\b|times|million|billion|thousand|k\b))|(\$\s?\d)|(\b\d{1,3}(,\d{3})+\b)", re.I)
SKIP_HEADINGS = re.compile(r"^(references|external links|see also|notes|further reading|contents|table of contents|"
                           r"related (posts|articles|reading)|share( this)?|comments?|about the author|sources|"
                           r"subscribe|newsletter|you may also like|recent posts|tags|categories)$", re.I)
BOILER = re.compile(r"(nav|menu|footer|header|sidebar|cookie|consent|newsletter|subscribe|related|share|social|comment)", re.I)


def fetch(url: str, timeout: float = 20.0) -> tuple[int, str, str]:
    try:
        import requests
        r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
        return r.status_code, r.url, r.text
    except ImportError:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.geturl(), resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, url, ""
    except Exception as e:
        return 0, url, str(e)


def robots_ok(url: str, cache: dict) -> bool:
    p = urlparse(url)
    host = f"{p.scheme}://{p.netloc}"
    if host not in cache:
        status, _, body = fetch(host + "/robots.txt", 10)
        rp = None
        if status == 200 and body:
            rp = RobotFileParser()
            rp.parse(body.splitlines())
        cache[host] = rp
    rp = cache[host]
    return True if rp is None else rp.can_fetch(UA, url)


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def schema_types(soup) -> tuple[list[str], list[str]]:
    types, faq = [], []

    def walk(node):
        if isinstance(node, list):
            for n in node:
                walk(n)
        elif isinstance(node, dict):
            t = node.get("@type")
            for x in (t if isinstance(t, list) else [t] if t else []):
                types.append(str(x))
                if x == "Question" and node.get("name"):
                    faq.append(clean(str(node["name"])))
            for v in node.values():
                if isinstance(v, (dict, list)):
                    walk(v)

    for tag in soup.find_all("script", type=re.compile("ld\\+json", re.I)):
        try:
            walk(json.loads(tag.string or tag.get_text() or "{}"))
        except ValueError:
            continue
    return sorted(set(types)), faq


def extract(html: str, url: str) -> dict:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    title = clean(soup.title.get_text()) if soup.title else ""
    types, faq = schema_types(soup)
    for t in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form"]):
        t.decompose()
    for el in list(soup.find_all(True)):
        if getattr(el, "decomposed", False) or el.attrs is None:
            continue
        ident = " ".join([el.get("id") or "", " ".join(el.get("class") or [])])
        if el.name not in ("html", "body", "main", "article") and ident and BOILER.search(ident):
            el.decompose()
    main = soup.find("article") or soup.find("main") or soup.body or soup
    h1 = main.find("h1") or soup.find("h1")
    heads = []
    for h in main.find_all(["h2", "h3"]):
        text = re.sub(r"^\s*(\d+[.)]|step \d+[.:]?)\s*", "", clean(h.get_text(" ")), flags=re.I)
        if 3 <= len(text) <= 160 and not SKIP_HEADINGS.match(text):
            heads.append({"level": h.name, "text": text})
    for h in heads:
        if h["text"].endswith("?") and h["text"] not in faq:
            faq.append(h["text"])
    body_text = clean(main.get_text(" "))
    stats = []
    for p in main.find_all(["p", "li", "td"]):
        text = clean(p.get_text(" "))
        if 30 <= len(text) <= 600 and STAT.search(text):
            a = p.find("a", href=True)
            src = urljoin(url, a["href"]) if a else ""
            stats.append({"text": text, "source_link": src})
    return {"url": url, "title": title, "h1": clean(h1.get_text(" ")) if h1 else "", "headings": heads,
            "word_count": len(body_text.split()), "schema_types": types, "faq": faq, "stats": stats[:40]}


# --------------------------------------------------------------------------- clustering

def toks(s: str) -> list[str]:
    out = []
    for t in re.findall(r"[a-z0-9][a-z0-9+#-]*", s.lower()):
        if t in STOP or len(t) < 2:
            continue
        out.append(t[:-1] if len(t) > 3 and t.endswith("s") and not t.endswith("ss") else t)
    return out


def similarity_matrix(texts: list[str], backend: str):
    order = ["sentence-transformers", "tfidf", "overlap"] if backend == "auto" else [backend]
    for b in order:
        try:
            if b == "sentence-transformers":
                from sentence_transformers import SentenceTransformer
                m = SentenceTransformer("BAAI/bge-small-en-v1.5")
                E = m.encode(texts, normalize_embeddings=True, show_progress_bar=False)
                return b, (E @ E.T).tolist()
            if b == "tfidf":
                from sklearn.feature_extraction.text import TfidfVectorizer
                X = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True).fit_transform(texts)
                return b, (X @ X.T).toarray().tolist()
            docs = [Counter(toks(t)) for t in texts]
            df = Counter(k for d in docs for k in d)
            n = len(docs)
            vecs = []
            for d in docs:
                v = {k: (1 + math.log(c)) * (math.log((1 + n) / (1 + df[k])) + 1) for k, c in d.items()}
                norm = math.sqrt(sum(x * x for x in v.values())) or 1
                vecs.append({k: x / norm for k, x in v.items()})
            M = [[sum(w * b2.get(k, 0) for k, w in a.items()) for b2 in vecs] for a in vecs]
            return "overlap", M
        except Exception as e:
            if backend != "auto":
                sys.exit(f"Backend {b} failed. {e}")
            print(f"  backend {b} unavailable ({type(e).__name__}). Trying the next one.", file=sys.stderr)
    sys.exit("No clustering backend worked.")


def cluster(items: list[dict], backend: str, threshold: float | None):
    texts = [i["text"] for i in items]
    used, M = similarity_matrix(texts, backend)
    thr = threshold if threshold is not None else DEFAULT_THRESHOLDS[used]
    clusters: list[list[int]] = []
    # Greedy average-link: a heading joins the cluster it is most similar to on average.
    for i in range(len(items)):
        best, best_s = None, thr
        for ci, members in enumerate(clusters):
            s = sum(M[i][j] for j in members) / len(members)
            if s >= best_s:
                best, best_s = ci, s
        if best is None:
            clusters.append([i])
        else:
            clusters[best].append(i)
    return used, thr, clusters


def tier(n_pages: int, total: int) -> str:
    share = n_pages / total if total else 0
    if share >= 0.7:
        return "must-cover"
    if share >= 0.3:
        return "recommended"
    return "optional angle"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Competitor teardown and heading coverage map.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--urls", help="File with one competitor URL per line, in SERP order")
    src.add_argument("--from-json", help="Recluster a teardown JSON written earlier, without fetching")
    ap.add_argument("--headings-csv", help="Extra headings for pages that block fetching. Columns url, level, heading")
    ap.add_argument("--out-prefix", default="teardown", help="Output prefix (default teardown)")
    ap.add_argument("--delay", type=float, default=1.0, help="Seconds between requests (default 1.0)")
    ap.add_argument("--backend", default="auto", choices=["auto", "sentence-transformers", "tfidf", "overlap"])
    ap.add_argument("--threshold", type=float, help="Similarity needed to join a topic. Default depends on backend")
    args = ap.parse_args(argv)

    if args.from_json:
        pages = json.load(open(args.from_json, encoding="utf-8"))["pages"]
    else:
        try:
            import bs4  # noqa: F401
        except ImportError:
            sys.exit("teardown.py needs BeautifulSoup. Install it with:  pip install beautifulsoup4 requests")
        urls = [l.strip() for l in open(args.urls, encoding="utf-8") if l.strip().startswith("http")]
        pages, cache = [], {}
        for i, u in enumerate(urls, 1):
            if not robots_ok(u, cache):
                print(f"[{i}/{len(urls)}] blocked by robots.txt {u}", file=sys.stderr)
                pages.append({"url": u, "error": "blocked by robots.txt"})
                continue
            status, final, html = fetch(u)
            time.sleep(args.delay)
            if status != 200 or not html:
                print(f"[{i}/{len(urls)}] status {status} {u}", file=sys.stderr)
                pages.append({"url": u, "error": f"status {status}"})
                continue
            rec = extract(html, final)
            rec["serp_position"] = i
            pages.append(rec)
            print(f"[{i}/{len(urls)}] ok {u} headings={len(rec['headings'])} words={rec['word_count']}",
                  file=sys.stderr)

    if args.headings_csv:
        extra = defaultdict(list)
        for row in csv.DictReader(open(args.headings_csv, newline="", encoding="utf-8-sig")):
            extra[row["url"].strip()].append({"level": row.get("level", "h2"), "text": clean(row["heading"])})
        for u, heads in extra.items():
            rec = next((p for p in pages if p["url"] == u), None)
            if rec is None or rec.get("error"):
                pages = [p for p in pages if p["url"] != u]
                pages.append({"url": u, "title": "", "h1": "", "headings": heads, "word_count": None,
                              "schema_types": [], "faq": [h["text"] for h in heads if h["text"].endswith("?")],
                              "stats": [], "note": "headings supplied by hand"})

    read = [p for p in pages if not p.get("error") and p.get("headings")]
    if not read:
        sys.exit("No page could be read. Paste headings into a CSV and pass --headings-csv, or use a browser tool.")

    items = [{"url": p["url"], "level": h["level"], "text": h["text"]} for p in read for h in p["headings"]]
    used, thr, clusters = cluster(items, args.backend, args.threshold)
    rows = []
    for members in clusters:
        urls_ = sorted({items[j]["url"] for j in members})
        heads = [items[j]["text"] for j in members]
        label = Counter(heads).most_common(1)[0][0] if len(set(heads)) < len(heads) else min(heads, key=len)
        rows.append({"topic": label, "tier": tier(len(urls_), len(read)), "pages_covering": len(urls_),
                     "share": round(len(urls_) / len(read), 2), "example_headings": " | ".join(dict.fromkeys(heads))[:500],
                     "urls": " ".join(urls_)})
    rows.sort(key=lambda r: (-r["pages_covering"], r["topic"]))

    with open(args.out_prefix + "_coverage.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    with open(args.out_prefix + "_stats.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["page", "statistic_sentence", "source_link"])
        for p in read:
            for s in p.get("stats", []):
                w.writerow([p["url"], s["text"], s["source_link"]])
    wc = sorted(p["word_count"] for p in read if p.get("word_count"))
    summary = {"pages_listed": len(pages), "pages_read": len(read), "backend": used, "threshold": thr,
               "topics": len(rows), "tiers": dict(Counter(r["tier"] for r in rows)),
               "word_count": {"min": wc[0], "median": wc[len(wc) // 2], "max": wc[-1]} if wc else {},
               "schema_types": dict(Counter(t for p in read for t in p.get("schema_types", [])).most_common()),
               "unreadable": [p["url"] for p in pages if p.get("error")]}
    with open(args.out_prefix + ".json", "w", encoding="utf-8") as fh:
        json.dump({"summary": summary, "pages": pages}, fh, indent=2, ensure_ascii=False)
    print(json.dumps(summary, indent=2), file=sys.stderr)
    print(f"Wrote {args.out_prefix}.json, {args.out_prefix}_coverage.csv and {args.out_prefix}_stats.csv",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
