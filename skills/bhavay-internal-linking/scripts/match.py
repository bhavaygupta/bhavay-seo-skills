#!/usr/bin/env python3
"""Match source paragraphs to target pages and propose internal links.

Reads the JSONL from crawl.py, plus optional Search Console CSVs and an optional
keyword metrics CSV. Scores every source paragraph against every target page,
finds exact-match anchors in the paragraph, applies the guardrails and writes a
ranked candidates CSV that build_sheet.py turns into the final sheet.

Similarity backends, tried in this order when --backend auto:
  1. sentence-transformers with BAAI/bge-small-en-v1.5 (pip install sentence-transformers)
  2. Ollama embeddings (nomic-embed-text by default) if a local Ollama answers
  3. TF-IDF cosine with scikit-learn (pip install scikit-learn)
  4. Pure-Python token overlap (idf-weighted cosine), no installs needed

Each backend has its own similarity scale, so each has its own default floor.
Read the similarity distribution in the summary and raise the floor if the set is weak.

Examples:
  python3 match.py --pages pages.jsonl --source-pattern /blog/ --target-pattern "/(product|solutions)/"
  python3 match.py --pages pages.jsonl --targets-file targets.txt \
      --gsc-pages gsc_pages.csv --gsc-queries gsc_page_queries.csv --keywords keywords.csv
  python3 match.py --pages pages.jsonl --backend overlap --floor 0.10 --out candidates.csv
"""

from __future__ import annotations

import argparse
import csv
import heapq
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from urllib.parse import urlparse

DEFAULT_FLOORS = {"sentence-transformers": 0.80, "ollama": 0.70, "tfidf": 0.12, "overlap": 0.10}
DEFAULT_ACRONYMS = "API,SSO,MFA,CRM,ERP,SEO,AEO,GEO,SaaS,HR,AI,ML,BI,PPC,ROI,KPI,SQL,CMS,VPN,IAM,SOC,PAM,DLP,EDR,XDR,SIEM,CSPM"
GENERIC_ANCHORS = {
    "click here", "read more", "learn more", "here", "this", "this page", "this article", "this post",
    "find out more", "more", "website", "link", "our blog", "see more", "more info", "get started",
    "contact us", "sign up", "book a demo", "request a demo", "home", "homepage",
}
STOPWORDS = set("""a about above after again against all am an and any are as at be because been before being
below between both but by can could did do does doing down during each few for from further had has have having
he her here hers herself him himself his how i if in into is it its itself just me more most my myself no nor not
now of off on once only or other our ours ourselves out over own same she should so some such than that the their
theirs them themselves then there these they this those through to too under until up very was we were what when
where which while who whom why will with you your yours yourself yourselves vs versus via per using use used also
get got make makes made best top new guide how what why your 2023 2024 2025 2026 2027""".split())
INTENT_WEIGHTS = {"transactional": 1.0, "commercial": 0.9, "navigational": 0.5, "informational": 0.5}
TYPE_RULES = [
    (r"/blog/", "blog"), (r"/learn/", "learn"), (r"/guides?/", "guide"), (r"/glossary/", "glossary"),
    (r"/(compare|comparison|vs|alternatives?)/|-vs-", "comparison"),
    (r"/(products?|platform|features?)(/|$)", "product"), (r"/solutions?(/|$)", "solution"),
    (r"/pricing", "pricing"), (r"/(case-stud|customers?/)", "case study"), (r"/docs?/", "docs"),
    (r"/(resources?|library)/", "resource"), (r"/integrations?/", "integration"),
]


# --------------------------------------------------------------------------- helpers

def key(url: str) -> str:
    """Join key for URLs: host without www, path without trailing slash, query kept."""
    p = urlparse(url.strip())
    host = p.netloc.lower().split(":")[0].removeprefix("www.")
    path = (p.path or "/").rstrip("/") or "/"
    return host + path + (("?" + p.query) if p.query else "")


def page_type(url: str, custom: list[tuple[re.Pattern, str]]) -> str:
    for rx, name in custom:
        if rx.search(url):
            return name
    path = urlparse(url).path or "/"
    if path in ("", "/"):
        return "home"
    for rx, name in TYPE_RULES:
        if re.search(rx, path, re.I):
            return name
    seg = [s for s in path.split("/") if s]
    return seg[0] if len(seg) > 1 else "page"


def tokens(text: str) -> list[str]:
    out = []
    for t in re.findall(r"[a-z0-9][a-z0-9+#&.-]*", text.lower()):
        t = t.strip(".-")
        if len(t) < 2 or t in STOPWORDS:
            continue
        if len(t) > 4 and t.endswith("ies"):
            t = t[:-3] + "y"
        elif len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.append(t)
    return out


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'“(])", text.strip())
    return [p.strip() for p in parts if p.strip()]


def clean_title(title: str) -> str:
    """Main segment of a title tag, without the brand suffix."""
    parts = re.split("\\s+[|\u2013\u2014\\-:\u00b7]\\s+", title)
    parts = [p.strip() for p in parts if p.strip()]
    return max(parts[:2], key=len) if parts else title.strip()


def read_csv_rows(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def pick(row: dict, *names, default=""):
    low = {k.strip().lower(): v for k, v in row.items() if k}
    for n in names:
        if n in low and low[n] not in (None, ""):
            return low[n]
    return default


def num(v, default=0.0) -> float:
    if v in (None, ""):
        return default
    s = str(v).replace(",", "").strip()
    pct = s.endswith("%")
    try:
        f = float(s.rstrip("%"))
    except ValueError:
        return default
    return f / 100 if pct else f


def expected_ctr(pos: float) -> float:
    """Rough organic CTR curve. Only used to flag below-expected CTR, not as a benchmark."""
    curve = {1: 0.28, 2: 0.15, 3: 0.10, 4: 0.07, 5: 0.05, 6: 0.04, 7: 0.03, 8: 0.025, 9: 0.02, 10: 0.018}
    p = max(1, round(pos))
    return curve.get(p, 0.01 if p <= 20 else 0.005)


def gap_factor(pos: float) -> float:
    if pos <= 0:
        return 0.3
    if pos < 5:
        return 0.4
    if pos <= 20:
        return 1.0
    return max(0.2, 1 - (pos - 20) / 30)


def quantiles(vals: list[float]) -> dict:
    if not vals:
        return {}
    v = sorted(vals)
    q = lambda f: round(v[min(len(v) - 1, int(f * (len(v) - 1) + 0.5))], 4)
    return {"n": len(v), "min": round(v[0], 4), "p25": q(0.25), "median": q(0.5), "p75": q(0.75), "max": round(v[-1], 4)}


# --------------------------------------------------------------------------- backends

def topk_from_rows(rows, k):
    return [heapq.nlargest(k, enumerate(r), key=lambda x: x[1]) for r in rows]


def backend_sentence_transformers(par_texts, tgt_texts, k, model_name):
    from sentence_transformers import SentenceTransformer  # noqa: raises ImportError when missing
    import numpy as np
    model = SentenceTransformer(model_name)
    P = model.encode(par_texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
    T = model.encode(tgt_texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
    return _numpy_topk(np.asarray(P), np.asarray(T), k)


def _numpy_topk(P, T, k, chunk=2000):
    import numpy as np
    out = []
    kk = min(k, T.shape[0])
    for i in range(0, P.shape[0], chunk):
        S = P[i:i + chunk] @ T.T
        S = S.toarray() if hasattr(S, "toarray") else np.asarray(S)
        idx = np.argpartition(-S, kk - 1, axis=1)[:, :kk]
        for r in range(S.shape[0]):
            pairs = sorted(((int(j), float(S[r, j])) for j in idx[r]), key=lambda x: -x[1])
            out.append(pairs)
    return out


def _http_json(url, payload=None, timeout=5):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def ollama_available(base, model):
    try:
        tags = _http_json(base.rstrip("/") + "/api/tags", timeout=2)
    except Exception:
        return False, "no Ollama server answered at " + base
    names = {m.get("name", "") for m in tags.get("models", [])}
    if model in names or f"{model}:latest" in names:
        return True, ""
    return False, f"Ollama is running but {model} is not pulled. Run: ollama pull {model}"


def backend_ollama(par_texts, tgt_texts, k, base, model):
    base = base.rstrip("/")

    def embed(texts):
        vecs = []
        for i in range(0, len(texts), 64):
            batch = texts[i:i + 64]
            try:
                res = _http_json(base + "/api/embed", {"model": model, "input": batch, "keep_alive": "1m"}, timeout=300)
                vecs.extend(res["embeddings"])
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise
                for t in batch:  # older Ollama versions only have /api/embeddings
                    vecs.append(_http_json(base + "/api/embeddings", {"model": model, "prompt": t}, timeout=120)["embedding"])
        return vecs

    P, T = embed(par_texts), embed(tgt_texts)
    try:
        import numpy as np
        P = np.asarray(P, dtype="float32")
        T = np.asarray(T, dtype="float32")
        P /= np.linalg.norm(P, axis=1, keepdims=True) + 1e-9
        T /= np.linalg.norm(T, axis=1, keepdims=True) + 1e-9
        return _numpy_topk(P, T, k)
    except ImportError:
        unit = lambda v: [x / (math.sqrt(sum(y * y for y in v)) or 1) for x in v]
        P, T = [unit(v) for v in P], [unit(v) for v in T]
        return topk_from_rows(([sum(a * b for a, b in zip(p, t)) for t in T] for p in P), k)


def backend_tfidf(par_texts, tgt_texts, k):
    from sklearn.feature_extraction.text import TfidfVectorizer
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True, min_df=1)
    vec.fit(par_texts + tgt_texts)
    P = vec.transform(par_texts)
    T = vec.transform(tgt_texts)  # rows are L2-normalised, so the dot product is cosine
    return _numpy_topk(P, T, k)


def backend_overlap(par_texts, tgt_texts, k):
    """Idf-weighted cosine over token counts with an inverted index. Pure Python."""
    docs = [Counter(tokens(t)) for t in par_texts + tgt_texts]
    df = Counter()
    for d in docs:
        df.update(d.keys())
    n = len(docs)
    idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}

    def weigh(c):
        v = {t: (1 + math.log(f)) * idf[t] for t, f in c.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}

    P = [weigh(c) for c in docs[:len(par_texts)]]
    T = [weigh(c) for c in docs[len(par_texts):]]
    index = defaultdict(list)
    for j, v in enumerate(T):
        for t, w in v.items():
            index[t].append((j, w))
    out = []
    for v in P:
        acc = defaultdict(float)
        for t, w in v.items():
            for j, w2 in index.get(t, ()):
                acc[j] += w * w2
        out.append(heapq.nlargest(k, acc.items(), key=lambda x: x[1]))
    return out


def run_backend(name, par_texts, tgt_texts, k, args):
    order = ["sentence-transformers", "ollama", "tfidf", "overlap"] if name == "auto" else [name]
    for b in order:
        try:
            if b == "sentence-transformers":
                return b, backend_sentence_transformers(par_texts, tgt_texts, k, args.st_model)
            if b == "ollama":
                ok, why = ollama_available(args.ollama_url, args.ollama_model)
                if not ok:
                    raise RuntimeError(why)
                return b, backend_ollama(par_texts, tgt_texts, k, args.ollama_url, args.ollama_model)
            if b == "tfidf":
                return b, backend_tfidf(par_texts, tgt_texts, k)
            return b, backend_overlap(par_texts, tgt_texts, k)
        except Exception as e:  # ImportError, model download failure, no server
            msg = f"{type(e).__name__}: {e}".splitlines()[0][:200]
            if name != "auto":
                sys.exit(f"Backend {b} failed. {msg}")
            print(f"  backend {b} unavailable ({msg}). Trying the next one.", file=sys.stderr)
    sys.exit("No similarity backend worked.")


# --------------------------------------------------------------------------- anchors

class AnchorRules:
    def __init__(self, min_chars, acronyms, brand_terms):
        self.min_chars = min_chars
        self.acronyms = {a.strip().lower() for a in acronyms.split(",") if a.strip()}
        self.brand = {b.strip().lower() for b in brand_terms.split(",") if b.strip()}

    def ok(self, phrase: str) -> bool:
        p = re.sub(r"\s+", " ", phrase.strip().lower())
        if not p or p in GENERIC_ANCHORS or p in self.brand:
            return False
        if len(p) < self.min_chars and p not in self.acronyms:
            return False
        words = re.findall(r"[a-z0-9+#&.-]+", p)
        if not words or all(w in STOPWORDS for w in words):
            return False
        if words[0] in STOPWORDS or words[-1] in STOPWORDS:
            return False
        if re.fullmatch(r"[\d\s.,%-]+", p):
            return False
        return True


def title_ngrams(text: str, nmin=2, nmax=5):
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9+#&'.-]*", text)
    for n in range(min(nmax, len(words)), nmin - 1, -1):
        for i in range(len(words) - n + 1):
            yield " ".join(words[i:i + n])


def target_phrases(target):
    return [x for x in (clean_title(target.get("title", "")), target.get("h1", "")) if x]


def build_anchor_candidates(target, queries, rules, max_queries, shared_ngrams=frozenset()):
    """Ordered list of (phrase, source, weight). Earlier entries win ties.

    Title phrases longer than 8 words are skipped. Title n-grams that appear in the
    title or H1 of more than one target are skipped, because they do not identify
    one page (for example a category phrase every product title shares).
    """
    out, seen = [], set()

    def add(p, src, w):
        p = re.sub(r"\s+", " ", p.strip(" .,:;!?\"'()"))
        lp = p.lower()
        if lp and lp not in seen and rules.ok(p):
            seen.add(lp)
            out.append((p, src, w))

    for q, imp in queries[:max_queries]:
        add(q, "gsc_query", imp)
    for src in target_phrases(target):
        if len(src.split()) <= 8:
            add(src, "title", 0)
    for src in target_phrases(target):
        for g in title_ngrams(src):
            if g.lower() not in shared_ngrams:
                add(g, "title_ngram", 0)
    return out


def find_exact(paragraph: str, cands):
    """Best exact anchor in the paragraph. Queries first, then longest title phrase."""
    best = None
    for phrase, src, w in cands:
        rx = re.compile(r"(?<![\w-])" + re.escape(phrase).replace(r"\ ", r"\s+") + r"(?![\w-])", re.I)
        m = rx.search(paragraph)
        if not m:
            continue
        rank = ({"gsc_query": 3, "title": 2, "title_ngram": 1}[src], w, len(phrase))
        if best is None or rank > best[0]:
            best = (rank, m.group(0), src, w, m.start())
    if best is None:
        return None
    _, text, src, w, pos = best
    return text, src, w, pos


# --------------------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Score paragraph to target relevance and propose internal links.")
    ap.add_argument("--pages", required=True, help="JSONL from crawl.py")
    ap.add_argument("--source-pattern", help="Regex for source pages that will carry links, for example /blog/")
    ap.add_argument("--target-pattern", help="Regex for target pages, for example /(product|solutions)/")
    ap.add_argument("--targets-file", help="File with one target URL per line. Overrides --target-pattern")
    ap.add_argument("--exclude-pattern", help="Regex for source pages to leave alone")
    ap.add_argument("--exclude-file", help="File with one excluded source URL per line")
    ap.add_argument("--gsc-pages", help="CSV with page, clicks, impressions, ctr, position (gsc_pages.py or a GSC export)")
    ap.add_argument("--gsc-queries", help="CSV with page, query, clicks, impressions, ctr, position")
    ap.add_argument("--keywords", help="CSV with keyword, volume, intent, difficulty from any keyword tool")
    ap.add_argument("--backend", default="auto", choices=["auto", "sentence-transformers", "ollama", "tfidf", "overlap"])
    ap.add_argument("--st-model", default="BAAI/bge-small-en-v1.5", help="sentence-transformers model name")
    ap.add_argument("--ollama-model", default="nomic-embed-text", help="Ollama embedding model")
    ap.add_argument("--ollama-url", default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    ap.add_argument("--floor", type=float, help="Similarity floor. Default depends on the backend")
    ap.add_argument("--top-targets", type=int, default=2, help="Best targets kept per paragraph (default 2)")
    ap.add_argument("--max-per-source", type=int, default=2, help="New links per source page (default 2)")
    ap.add_argument("--max-per-target", type=int, default=5, help="New links per target page (default 5)")
    ap.add_argument("--max-anchor-uses", type=int, default=2, help="Times one anchor may be used site-wide (default 2)")
    ap.add_argument("--min-anchor-chars", type=int, default=4, help="Shortest anchor allowed, acronyms excepted")
    ap.add_argument("--acronyms", default=DEFAULT_ACRONYMS, help="Comma list of short anchors that are allowed")
    ap.add_argument("--brand", default="", help="Comma list of brand terms. Brand-only anchors are dropped")
    ap.add_argument("--queries-per-target", type=int, default=25, help="Top GSC queries used per target")
    ap.add_argument("--exact-only", action="store_true", help="Drop topical rows that need a new sentence")
    ap.add_argument("--type-map", action="append", default=[], metavar="REGEX=TYPE",
                    help="Custom page type rule, repeatable, for example '/academy/=learn'")
    ap.add_argument("--out", default="candidates.csv", help="Output CSV (default candidates.csv)")
    args = ap.parse_args(argv)

    custom_types = []
    for rule in args.type_map:
        rx, _, name = rule.rpartition("=")
        custom_types.append((re.compile(rx), name))

    # ---- load crawl
    pages = {}
    unreadable = []
    with open(args.pages, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            url = r.get("final_url") or r["url"]
            if r.get("status") != 200 or r.get("error"):
                unreadable.append({"url": r["url"], "status": r.get("status"), "error": r.get("error", "")})
                continue
            r["_url"] = url
            r["_key"] = key(url)
            pages[r["_key"]] = r
            if r.get("url") and key(r["url"]) not in pages:
                pages[key(r["url"])] = r
    uniq = {id(p): p for p in pages.values()}.values()
    print(f"Loaded {len(uniq)} readable pages, {len(unreadable)} unreadable", file=sys.stderr)

    rx_src = re.compile(args.source_pattern) if args.source_pattern else None
    rx_tgt = re.compile(args.target_pattern) if args.target_pattern else None
    rx_exc = re.compile(args.exclude_pattern) if args.exclude_pattern else None
    excluded = set()
    if args.exclude_file:
        excluded = {key(l) for l in open(args.exclude_file, encoding="utf-8") if l.strip().startswith("http")}

    # ---- GSC
    gsc = {}
    if args.gsc_pages:
        for row in read_csv_rows(args.gsc_pages):
            page = pick(row, "page", "top pages", "url", "address", "landing page")
            if page:
                gsc[key(page)] = {"clicks": num(pick(row, "clicks")), "impressions": num(pick(row, "impressions")),
                                  "ctr": num(pick(row, "ctr")), "position": num(pick(row, "position", "avg. position"))}
    queries = defaultdict(list)
    query_imps = {}
    if args.gsc_queries:
        for row in read_csv_rows(args.gsc_queries):
            page, q = pick(row, "page", "url", "landing page"), pick(row, "query", "top queries", "keyword")
            if page and q:
                imp = num(pick(row, "impressions"))
                queries[key(page)].append((q, imp))
                query_imps[(key(page), q.lower())] = imp
        for k_ in queries:
            queries[k_].sort(key=lambda x: -x[1])

    kw = {}
    if args.keywords:
        for row in read_csv_rows(args.keywords):
            k_ = pick(row, "keyword", "query", "phrase", "anchor").strip().lower()
            if k_:
                kw[k_] = {"volume": num(pick(row, "volume", "search volume", "avg. monthly searches")),
                          "intent": pick(row, "intent", "search intent").lower(),
                          "difficulty": num(pick(row, "difficulty", "kd", "keyword difficulty"), None)}

    # ---- source and target sets
    def is_source(p):
        u = p["_url"]
        if rx_src and not rx_src.search(u):
            return False
        if (rx_exc and rx_exc.search(u)) or p["_key"] in excluded:
            return False
        return bool(p.get("paragraphs")) and p.get("indexable", True)

    sources = [p for p in uniq if is_source(p)]
    if args.targets_file:
        tkeys = [key(l) for l in open(args.targets_file, encoding="utf-8") if l.strip().startswith("http")]
        targets = []
        for tk in dict.fromkeys(tkeys):
            if tk in pages:
                targets.append(pages[tk])
            else:  # target not crawled. Fall back to GSC queries and the URL slug.
                slug = urlparse("https://" + tk).path.strip("/").split("/")[-1].replace("-", " ")
                targets.append({"_url": "https://" + tk, "_key": tk, "title": slug.title(), "h1": "",
                                "meta_description": "", "paragraphs": [], "_uncrawled": True})
    else:
        targets = [p for p in uniq if (not rx_tgt or rx_tgt.search(p["_url"])) and p.get("indexable", True)]
    if not sources or not targets:
        sys.exit(f"Need sources and targets. Found {len(sources)} sources and {len(targets)} targets. "
                 "Check --source-pattern, --target-pattern and the crawl.")
    print(f"{len(sources)} source pages, {len(targets)} target pages", file=sys.stderr)

    # ---- existing in-text links per target, counted across every crawled page
    inlinks = Counter()
    for p in uniq:
        for l in set(key(x) for x in p.get("content_links", [])):
            if l != p["_key"]:
                inlinks[l] += 1

    # ---- texts
    par_index, par_texts = [], []
    for si, s in enumerate(sources):
        for par in s["paragraphs"]:
            par_index.append((si, par["n"], par["text"]))
            par_texts.append(par["text"])
    tgt_texts = []
    for t in targets:
        q = " ; ".join(x[0] for x in queries.get(t["_key"], [])[:10])
        tgt_texts.append(" . ".join(x for x in (t.get("title", ""), t.get("h1", ""), t.get("meta_description", ""), q) if x))

    k = min(len(targets), args.top_targets + 8)  # extra room for self links and existing links
    backend, topk = run_backend(args.backend, par_texts, tgt_texts, k, args)
    floor = args.floor if args.floor is not None else DEFAULT_FLOORS[backend]
    print(f"Backend {backend}, floor {floor}", file=sys.stderr)

    # ---- opportunity per target
    max_imp_log = max((math.log1p(g["impressions"]) for g in gsc.values()), default=0) or 1
    opp = {}
    for t in targets:
        g = gsc.get(t["_key"])
        n_in = inlinks.get(t["_key"], 0)
        if gsc:
            if g:
                boost = 1.2 if g["ctr"] < 0.5 * expected_ctr(g["position"]) else 1.0
                v = math.log1p(g["impressions"]) / max_imp_log * gap_factor(g["position"]) * boost
            else:
                v = 0.05
            if n_in <= 1:
                v *= 1.15
            opp[t["_key"]] = min(v, 1.0)
        else:
            opp[t["_key"]] = 1 / (1 + n_in)  # no GSC data: favour targets with few in-text links

    rules = AnchorRules(args.min_anchor_chars, args.acronyms, args.brand)
    ngram_df = Counter()
    for t in targets:
        ngram_df.update({g.lower() for src in target_phrases(t) for g in title_ngrams(src)})
    shared = frozenset(g for g, n in ngram_df.items() if n > 1)
    anchor_cands = {t["_key"]: build_anchor_candidates(t, queries.get(t["_key"], []), rules,
                                                       args.queries_per_target, shared)
                    for t in targets}
    max_kw_log = max((math.log1p(v["volume"]) for v in kw.values()), default=0) or 1
    max_q_log = max((math.log1p(v) for v in query_imps.values()), default=0) or 1

    def demand(tkey, anchor, src):
        a = anchor.lower()
        if a in kw:
            w = INTENT_WEIGHTS.get(kw[a]["intent"].split(",")[0].strip(), 0.6)
            return math.log1p(kw[a]["volume"]) / max_kw_log * w
        if src == "gsc_query":
            return 0.3 + 0.7 * math.log1p(query_imps.get((tkey, a), 0)) / max_q_log
        return {"title": 0.3, "title_ngram": 0.2}.get(src, 0.15)

    # ---- candidates
    stats = Counter()
    best_sims = []
    cands = []
    for pi, pairs in enumerate(topk):
        si, pno, ptext = par_index[pi]
        s = sources[si]
        linked = {key(x) for x in s.get("content_links", [])}
        if pairs:
            best_sims.append(pairs[0][1])
        kept = 0
        for tj, sim in pairs:
            if kept >= args.top_targets or sim < floor:
                break
            t = targets[tj]
            if t["_key"] == s["_key"] or (s.get("canonical") and key(s["canonical"]) == t["_key"]):
                stats["skipped_self"] += 1
                continue
            if t["_key"] in linked:
                stats["skipped_already_linked"] += 1
                continue
            kept += 1
            hit = find_exact(ptext, anchor_cands[t["_key"]])
            if hit:
                anchor, asrc, _, pos = hit
                find_text = next((x for x in sentences(ptext) if anchor in x), ptext)
                match = "Exact"
            else:
                if args.exact_only:
                    stats["dropped_topical"] += 1
                    continue
                ac = anchor_cands[t["_key"]]
                pref = [a for a in ac if a[1] in ("gsc_query", "title") and len(a[0].split()) <= 6]
                if not pref:
                    stats["no_anchor"] += 1
                    continue
                anchor, asrc = pref[0][0], pref[0][1]
                if asrc == "title":
                    anchor = anchor[0].lower() + anchor[1:] if not anchor[:2].isupper() else anchor
                sents = sentences(ptext)
                find_text = sents[-1] if sents else ptext
                match = "Topical"
            cands.append({"s": s, "t": t, "pno": pno, "ptext": ptext, "sim": sim, "anchor": anchor,
                          "asrc": asrc, "find": find_text, "match": match})

    sims = [c["sim"] for c in cands]
    smin, smax = (min(sims), max(sims)) if sims else (0, 1)
    for c in cands:
        fit = (c["sim"] - floor) / ((smax - floor) or 1) if smax > floor else 1.0
        d = demand(c["t"]["_key"], c["anchor"], c["asrc"])
        o = opp[c["t"]["_key"]]
        c["fit"], c["demand"], c["opp"] = fit, d, o
        c["priority"] = round(100 * (0.4 * o + 0.3 * d + 0.3 * max(0.0, min(fit, 1.0))))

    # ---- guardrails, greedy by priority
    cands.sort(key=lambda c: (-c["priority"], -c["sim"]))
    per_src, per_tgt, anchor_uses, anchor_target = Counter(), Counter(), Counter(), {}
    used_par, used_pair = set(), set()
    chosen = []
    for c in cands:
        sk, tk, a = c["s"]["_key"], c["t"]["_key"], c["anchor"].lower()
        if (sk, c["pno"]) in used_par or (sk, tk) in used_pair:
            stats["dropped_duplicate"] += 1
            continue
        if per_src[sk] >= args.max_per_source:
            stats["dropped_source_cap"] += 1
            continue
        if per_tgt[tk] >= args.max_per_target:
            stats["dropped_target_cap"] += 1
            continue
        if anchor_uses[a] >= args.max_anchor_uses:
            stats["dropped_anchor_cap"] += 1
            continue
        flags = []
        if a in anchor_target and anchor_target[a] != tk:
            flags.append("anchor_conflict")
        anchor_target.setdefault(a, tk)
        used_par.add((sk, c["pno"]))
        used_pair.add((sk, tk))
        per_src[sk] += 1
        per_tgt[tk] += 1
        anchor_uses[a] += 1
        if c["match"] == "Topical":
            flags.append("needs_draft")
        if c["sim"] < floor + 0.02:
            flags.append("near_floor")
        if c["t"].get("_uncrawled"):
            flags.append("target_not_crawled")
        c["flags"] = flags
        chosen.append(c)

    # ---- write
    fields = ["source_url", "source_type", "paragraph_no", "paragraph_text", "find_text", "draft", "anchor",
              "anchor_source", "target_url", "target_title", "target_type", "match", "similarity",
              "anchor_uses", "flag", "priority", "target_inlinks", "impressions", "position", "ctr",
              "keyword_volume", "why"]
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for c in chosen:
            s, t = c["s"], c["t"]
            g = gsc.get(t["_key"], {})
            n_in = inlinks.get(t["_key"], 0)
            vol = kw.get(c["anchor"].lower(), {}).get("volume")
            why = []
            if g:
                why.append(f"Target averages position {g['position']:.1f} on {int(g['impressions']):,} "
                           f"impressions with {g['ctr']:.1%} CTR.")
            why.append(f"It has {n_in} in-text link{'s' if n_in != 1 else ''} from crawled pages today.")
            if vol:
                why.append(f"The anchor has about {int(vol):,} monthly searches.")
            elif c["asrc"] == "gsc_query":
                why.append(f'"{c["anchor"]}" is a query the target already ranks for.')
            else:
                why.append("The anchor comes from the target title.")
            why.append(f"Paragraph similarity {c['sim']:.2f}.")
            w.writerow({
                "source_url": s["_url"], "source_type": page_type(s["_url"], custom_types),
                "paragraph_no": c["pno"], "paragraph_text": c["ptext"], "find_text": c["find"], "draft": "",
                "anchor": c["anchor"], "anchor_source": c["asrc"], "target_url": t["_url"],
                "target_title": t.get("title", ""), "target_type": page_type(t["_url"], custom_types),
                "match": c["match"], "similarity": round(c["sim"], 4),
                "anchor_uses": anchor_uses[c["anchor"].lower()], "flag": ", ".join(c["flags"]),
                "priority": c["priority"], "target_inlinks": n_in,
                "impressions": int(g["impressions"]) if g else "", "position": round(g["position"], 1) if g else "",
                "ctr": round(g["ctr"], 4) if g else "", "keyword_volume": int(vol) if vol else "",
                "why": " ".join(why),
            })

    stem = os.path.splitext(args.out)[0]
    anchors = sorted({c["anchor"] for c in chosen} | {a for cl in anchor_cands.values() for a, s_, _ in cl
                                                      if s_ != "title_ngram"})
    with open(stem + "_anchors.txt", "w", encoding="utf-8") as fh:
        fh.write("\n".join(anchors) + "\n")
    summary = {
        "backend": backend, "floor": floor, "sources": len(sources), "targets": len(targets),
        "paragraphs_scored": len(par_texts), "candidates_above_floor": len(cands), "links_selected": len(chosen),
        "exact": sum(c["match"] == "Exact" for c in chosen), "topical": sum(c["match"] == "Topical" for c in chosen),
        "sources_touched": len({c["s"]["_key"] for c in chosen}), "targets_touched": len({c["t"]["_key"] for c in chosen}),
        "similarity_selected": quantiles([c["sim"] for c in chosen]),
        "similarity_best_per_paragraph": quantiles(best_sims),
        "gsc_loaded": bool(gsc), "queries_loaded": sum(len(v) for v in queries.values()), "keywords_loaded": len(kw),
        "unreadable_pages": unreadable, **{k_: v for k_, v in stats.items()},
    }
    with open(stem + "_summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    print(json.dumps({k_: v for k_, v in summary.items() if k_ != "unreadable_pages"}, indent=2), file=sys.stderr)
    print(f"Wrote {args.out}, {stem}_summary.json and {stem}_anchors.txt", file=sys.stderr)
    if not chosen:
        print("No links passed the guardrails. Lower --floor a little or widen the source and target scope.",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
