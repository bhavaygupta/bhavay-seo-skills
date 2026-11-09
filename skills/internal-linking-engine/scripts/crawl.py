#!/usr/bin/env python3
"""Polite site crawler for the internal-linking-engine skill.

Reads a sitemap (sitemap index and .gz supported) or a plain URL list, fetches
each page politely and writes one JSON object per page to a JSONL file.

Per page it records status, final URL, title, H1, canonical, meta description,
robots directives, main-content paragraphs and the internal links found inside
the main content.

Main content comes from trafilatura when it is installed. Otherwise a simple
readability-style heuristic built on BeautifulSoup is used.

Examples:
  python3 crawl.py --sitemap https://example.com/sitemap.xml --out pages.jsonl
  python3 crawl.py --urls urls.txt --limit 200 --delay 2 --out pages.jsonl
  python3 crawl.py --sitemap https://example.com/sitemap.xml --include /blog/ --limit 50
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

try:
    import requests  # optional, urllib is used when missing
except ImportError:  # pragma: no cover
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit(
        "crawl.py needs BeautifulSoup to parse HTML.\n"
        "Install it with:  pip install beautifulsoup4 requests\n"
        "Optional, better main-content extraction:  pip install trafilatura"
    )

try:
    import trafilatura  # optional
except ImportError:
    trafilatura = None

DEFAULT_UA = (
    "InternalLinkingEngine/1.0 (+https://bhavay.com/resources/skills/internal-linking-engine)"
)
BOILERPLATE_TAGS = ["script", "style", "noscript", "template", "svg", "iframe",
                    "nav", "header", "footer", "aside", "form", "button", "dialog"]
BOILERPLATE_HINT = re.compile(
    r"(^|[\s_-])(nav|navbar|menu|header|footer|sidebar|side-bar|breadcrumb|cookie|consent|"
    r"banner|share|social|related|newsletter|subscribe|signup|comment|popup|modal|toc|"
    r"table-of-contents|pagination|author-bio|cta)([\s_-]|$)",
    re.I,
)
SKIP_EXT = re.compile(
    r"\.(pdf|jpe?g|png|gif|webp|svg|avif|ico|mp4|mp3|zip|gz|docx?|xlsx?|pptx?|csv|xml|json|js|css)$",
    re.I,
)


# --------------------------------------------------------------------------- fetch

class Fetcher:
    """Small HTTP helper with a fixed delay between requests and 429 back-off."""

    def __init__(self, user_agent: str, delay: float, timeout: float):
        self.ua = user_agent
        self.delay = delay
        self.timeout = timeout
        self._last = 0.0
        self.session = None
        if requests is not None:
            self.session = requests.Session()
            self.session.headers.update({"User-Agent": user_agent,
                                         "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.5"})

    def _wait(self):
        gap = time.monotonic() - self._last
        if gap < self.delay:
            time.sleep(self.delay - gap)
        self._last = time.monotonic()

    def get(self, url: str, retries: int = 3) -> dict:
        """Return dict with status, final_url, headers (lower-case), content (bytes), error."""
        backoff = max(self.delay, 1.0) * 5
        for attempt in range(retries + 1):
            self._wait()
            try:
                if self.session is not None:
                    r = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                    res = {"status": r.status_code, "final_url": r.url,
                           "headers": {k.lower(): v for k, v in r.headers.items()},
                           "content": r.content, "error": None}
                else:
                    req = urllib.request.Request(url, headers={"User-Agent": self.ua})
                    try:
                        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                            res = {"status": resp.status, "final_url": resp.geturl(),
                                   "headers": {k.lower(): v for k, v in resp.headers.items()},
                                   "content": resp.read(), "error": None}
                    except urllib.error.HTTPError as e:
                        res = {"status": e.code, "final_url": url,
                               "headers": {k.lower(): v for k, v in (e.headers or {}).items()},
                               "content": e.read() if hasattr(e, "read") else b"", "error": None}
            except Exception as e:  # network error, timeout, TLS
                res = {"status": 0, "final_url": url, "headers": {}, "content": b"",
                       "error": f"{type(e).__name__}: {e}"}
            if res["status"] in (429, 503) and attempt < retries:
                wait = res["headers"].get("retry-after", "")
                wait = float(wait) if wait.isdigit() else backoff
                print(f"  {res['status']} on {url}, backing off {wait:.0f}s", file=sys.stderr)
                time.sleep(wait)
                backoff *= 2
                continue
            return res
        return res


# --------------------------------------------------------------------------- robots

class Robots:
    """Caches one robots.txt parser per host. Missing or broken robots.txt means allow."""

    def __init__(self, fetcher: Fetcher):
        self.fetcher = fetcher
        self.cache: dict[str, RobotFileParser | None] = {}

    def parser(self, url: str) -> RobotFileParser | None:
        p = urlparse(url)
        host = f"{p.scheme}://{p.netloc}"
        if host not in self.cache:
            res = self.fetcher.get(host + "/robots.txt", retries=1)
            rp = None
            if res["status"] == 200 and res["content"]:
                rp = RobotFileParser()
                rp.parse(res["content"].decode("utf-8", "replace").splitlines())
            elif res["status"] in (401, 403):
                # Treat an access-denied robots.txt as disallow-all, the conservative reading.
                rp = RobotFileParser()
                rp.parse(["User-agent: *", "Disallow: /"])
            self.cache[host] = rp
        return self.cache[host]

    def allowed(self, url: str) -> bool:
        rp = self.parser(url)
        return True if rp is None else rp.can_fetch(self.fetcher.ua, url)

    def crawl_delay(self, url: str) -> float | None:
        rp = self.parser(url)
        if rp is None:
            return None
        d = rp.crawl_delay(self.fetcher.ua)
        return float(d) if d else None


# --------------------------------------------------------------------------- sitemap

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def read_sitemap(url: str, fetcher: Fetcher, limit: int | None, seen=None) -> list[str]:
    """Return page URLs from a sitemap or sitemap index, depth first, de-duplicated."""
    seen = seen if seen is not None else set()
    if url in seen:
        return []
    seen.add(url)
    res = fetcher.get(url)
    if res["status"] != 200 or not res["content"]:
        print(f"  could not read sitemap {url} (status {res['status']} {res['error'] or ''})",
              file=sys.stderr)
        return []
    data = res["content"]
    if url.endswith(".gz") or data[:2] == b"\x1f\x8b":
        try:
            data = gzip.decompress(data)
        except OSError:
            pass
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        print(f"  sitemap {url} is not valid XML: {e}", file=sys.stderr)
        return []
    urls: list[str] = []
    kind = _local(root.tag)
    for node in root:
        loc = next((c.text.strip() for c in node if _local(c.tag) == "loc" and c.text), None)
        if not loc:
            continue
        if kind == "sitemapindex":
            urls.extend(read_sitemap(loc, fetcher, None if limit is None else limit - len(urls), seen))
        else:
            urls.append(loc)
        if limit is not None and len(urls) >= limit:
            break
    return urls


# --------------------------------------------------------------------------- parsing

def norm_url(u: str) -> str:
    """Normalise a URL for comparison: drop fragment, lower-case host, keep path and query."""
    u, _ = urldefrag(u.strip())
    p = urlparse(u)
    path = p.path or "/"
    return p._replace(scheme=p.scheme.lower(), netloc=p.netloc.lower(), path=path).geturl()


def same_site(host_a: str, host_b: str) -> bool:
    strip = lambda h: h.lower().split(":")[0].removeprefix("www.")
    return strip(host_a) == strip(host_b)


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def is_boilerplate(el) -> bool:
    attrs = getattr(el, "attrs", None)
    if not attrs:
        return False
    ident = " ".join([attrs.get("id") or "", " ".join(attrs.get("class") or []), attrs.get("role") or ""])
    if attrs.get("role") in ("navigation", "banner", "contentinfo", "complementary"):
        return True
    if attrs.get("aria-hidden") == "true":
        return True
    return bool(BOILERPLATE_HINT.search(ident))


def heuristic_main(soup: BeautifulSoup):
    """Pick the main-content node. Prefers <article>/<main>, else the densest <p> parent."""
    body = soup.body or soup
    for tag in body.find_all(BOILERPLATE_TAGS):
        tag.decompose()
    for el in list(body.find_all(True)):
        if getattr(el, "decomposed", False) or el.attrs is None:
            continue
        if el.name not in ("html", "body", "main", "article") and is_boilerplate(el):
            el.decompose()

    for selector in ("article", "main", "[role=main]", "#content", ".post-content",
                     ".entry-content", ".article-body", ".content"):
        node = body.select_one(selector)
        if node and len(clean_text(node.get_text(" "))) > 400:
            return node

    # Readability-style scoring: each paragraph adds its length to its parent and
    # half to its grandparent. The highest scoring container wins.
    scores: dict[int, float] = {}
    nodes: dict[int, object] = {}
    for p in body.find_all("p"):
        text = clean_text(p.get_text(" "))
        if len(text) < 25:
            continue
        score = 1 + text.count(",") + min(len(text) / 100, 3)
        for depth, anc in enumerate([p.parent, p.parent.parent if p.parent else None]):
            if anc is None:
                continue
            scores[id(anc)] = scores.get(id(anc), 0) + score / (1 + depth)
            nodes[id(anc)] = anc
    if scores:
        return nodes[max(scores, key=scores.get)]
    return body


def blocks_from_node(node, min_chars: int) -> list[str]:
    out, seen = [], set()
    for el in node.find_all(["p", "li", "blockquote", "td"]):
        # Skip list items or cells that wrap a paragraph we will read anyway.
        if el.name != "p" and el.find("p"):
            continue
        if el.name in ("li", "td") and el.find_parent("p"):
            continue
        text = clean_text(el.get_text(" "))
        if len(text) >= min_chars and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def links_from_node(node, base: str, site_host: str) -> list[str]:
    links = set()
    for a in node.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absu = norm_url(urljoin(base, href))
        p = urlparse(absu)
        if p.scheme in ("http", "https") and same_site(p.netloc, site_host):
            links.add(absu)
    return sorted(links)


def trafilatura_main(html: str, url: str, min_chars: int, site_host: str):
    """Return (paragraphs, links) from trafilatura XML output, or None on failure."""
    if trafilatura is None:
        return None
    try:
        xml = trafilatura.extract(html, url=url, output_format="xml", include_links=True,
                                  include_comments=False, include_tables=True, favor_precision=True)
    except Exception:
        return None
    if not xml:
        return None
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    paragraphs, links, seen = [], set(), set()
    for el in root.iter():
        name = _local(el.tag)
        if name in ("p", "item", "quote", "cell"):
            text = clean_text("".join(el.itertext()))
            if len(text) >= min_chars and text not in seen:
                seen.add(text)
                paragraphs.append(text)
        if name == "ref" and el.get("target"):
            absu = norm_url(urljoin(url, el.get("target")))
            p = urlparse(absu)
            if p.scheme in ("http", "https") and same_site(p.netloc, site_host):
                links.add(absu)
    if not paragraphs:
        return None
    return paragraphs, sorted(links)


def parse_page(html: str, url: str, extractor: str, min_chars: int) -> dict:
    soup = BeautifulSoup(html, "lxml") if _has_lxml() else BeautifulSoup(html, "html.parser")
    title = clean_text(soup.title.get_text()) if soup.title else ""
    h1 = soup.find("h1")
    canon = soup.find("link", rel=lambda v: v and "canonical" in (v if isinstance(v, list) else [v]))
    desc = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    robots = soup.find("meta", attrs={"name": re.compile("^robots$", re.I)})
    lang = soup.html.get("lang", "") if soup.html else ""
    host = urlparse(url).netloc
    all_links = links_from_node(soup, url, host)

    result = {
        "title": title,
        "h1": clean_text(h1.get_text(" ")) if h1 else "",
        "canonical": norm_url(urljoin(url, canon["href"])) if canon and canon.get("href") else "",
        "meta_description": clean_text(desc.get("content", "")) if desc else "",
        "meta_robots": clean_text(robots.get("content", "")).lower() if robots else "",
        "lang": lang,
        "all_internal_links": all_links,
    }

    # The heuristic node is always computed. Its links are merged with trafilatura's,
    # because trafilatura drops card and button links that still count as "already linked".
    node = heuristic_main(soup)
    heur_links = links_from_node(node, url, host)
    got = None
    if extractor in ("auto", "trafilatura"):
        got = trafilatura_main(html, url, min_chars, host)
        if got:
            result["extractor"] = "trafilatura"
            got = (got[0], sorted(set(got[1]) | set(heur_links)))
    if got is None:
        got = (blocks_from_node(node, min_chars), heur_links)
        result["extractor"] = "heuristic"
    paragraphs, content_links = got
    result["paragraphs"] = [{"n": i + 1, "text": t} for i, t in enumerate(paragraphs)]
    result["content_links"] = content_links
    result["word_count"] = sum(len(t.split()) for t in paragraphs)
    return result


_LXML = None


def _has_lxml() -> bool:
    global _LXML
    if _LXML is None:
        try:
            import lxml  # noqa: F401
            _LXML = True
        except ImportError:
            _LXML = False
    return _LXML


# --------------------------------------------------------------------------- main

def load_url_list(path: str) -> list[str]:
    with open(path, encoding="utf-8") as fh:
        return [ln.strip().split(",")[0] for ln in fh
                if ln.strip() and not ln.startswith("#") and ln.strip().lower().startswith("http")]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Polite crawler that writes page content and in-content links to JSONL.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--sitemap", help="Sitemap or sitemap index URL")
    src.add_argument("--urls", help="Text or CSV file with one URL per line (first column)")
    ap.add_argument("--out", default="pages.jsonl", help="Output JSONL path (default pages.jsonl)")
    ap.add_argument("--limit", type=int, help="Stop after this many URLs")
    ap.add_argument("--include", help="Only crawl URLs matching this regex, for example /blog/|/product/")
    ap.add_argument("--exclude", help="Skip URLs matching this regex")
    ap.add_argument("--delay", type=float, default=1.0, help="Seconds between requests (default 1.0)")
    ap.add_argument("--timeout", type=float, default=20.0, help="Request timeout in seconds")
    ap.add_argument("--user-agent", default=DEFAULT_UA, help="User-Agent header")
    ap.add_argument("--extractor", choices=["auto", "trafilatura", "heuristic"], default="auto",
                    help="Main-content extractor. auto uses trafilatura when installed")
    ap.add_argument("--min-par-chars", type=int, default=60,
                    help="Ignore text blocks shorter than this (default 60)")
    args = ap.parse_args(argv)

    if args.delay < 0.5:
        print("Delay below 0.5s is not polite. Using 0.5s.", file=sys.stderr)
        args.delay = 0.5
    if args.extractor == "trafilatura" and trafilatura is None:
        print("trafilatura is not installed. Falling back to the heuristic extractor.", file=sys.stderr)

    fetcher = Fetcher(args.user_agent, args.delay, args.timeout)
    robots = Robots(fetcher)

    inc = re.compile(args.include) if args.include else None
    exc = re.compile(args.exclude) if args.exclude else None
    # Read more than the limit when filtering, so filters still yield enough URLs.
    read_limit = None if (inc or exc or not args.limit) else args.limit

    if args.sitemap:
        print(f"Reading sitemap {args.sitemap}", file=sys.stderr)
        urls = read_sitemap(args.sitemap, fetcher, read_limit)
    else:
        urls = load_url_list(args.urls)

    picked, seen = [], set()
    for u in urls:
        n = norm_url(u)
        if n in seen or SKIP_EXT.search(urlparse(n).path):
            continue
        if inc and not inc.search(n):
            continue
        if exc and exc.search(n):
            continue
        seen.add(n)
        picked.append(n)
        if args.limit and len(picked) >= args.limit:
            break
    if not picked:
        print("No URLs to crawl. Check the sitemap URL or the include and exclude filters.", file=sys.stderr)
        return 1

    if picked:
        cd = robots.crawl_delay(picked[0])
        if cd and cd > fetcher.delay:
            print(f"robots.txt asks for a {cd}s crawl delay. Using it.", file=sys.stderr)
            fetcher.delay = cd

    print(f"Crawling {len(picked)} URLs at {fetcher.delay}s per request", file=sys.stderr)
    ok = blocked = failed = 0
    with open(args.out, "w", encoding="utf-8") as out:
        for i, url in enumerate(picked, 1):
            rec = {"url": url}
            if not robots.allowed(url):
                rec.update({"status": None, "error": "blocked by robots.txt"})
                blocked += 1
            else:
                res = fetcher.get(url)
                ctype = res["headers"].get("content-type", "")
                rec.update({"status": res["status"], "final_url": norm_url(res["final_url"]),
                            "redirected": norm_url(res["final_url"]) != url,
                            "content_type": ctype.split(";")[0].strip(),
                            "x_robots_tag": res["headers"].get("x-robots-tag", "").lower()})
                if res["error"]:
                    rec["error"] = res["error"]
                    failed += 1
                elif res["status"] == 200 and "html" in ctype.lower():
                    enc = "utf-8"
                    m = re.search(r"charset=([\w-]+)", ctype, re.I)
                    if m:
                        enc = m.group(1)
                    html = res["content"].decode(enc, "replace")
                    try:
                        rec.update(parse_page(html, rec["final_url"], args.extractor, args.min_par_chars))
                        ok += 1
                    except Exception as e:
                        rec["error"] = f"parse failed: {type(e).__name__}: {e}"
                        failed += 1
                else:
                    failed += 1
                robots_flags = rec.get("meta_robots", "") + " " + rec.get("x_robots_tag", "")
                canon = rec.get("canonical") or rec.get("final_url")
                rec["indexable"] = bool(
                    rec.get("status") == 200 and "noindex" not in robots_flags
                    and norm_url(canon or url) == rec.get("final_url"))
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            pars = len(rec.get("paragraphs", []))
            print(f"[{i}/{len(picked)}] {rec.get('status')} {url} paragraphs={pars} "
                  f"content_links={len(rec.get('content_links', []))}", file=sys.stderr)

    print(f"Done. {ok} parsed, {failed} failed or non-HTML, {blocked} blocked by robots.txt. Wrote {args.out}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
