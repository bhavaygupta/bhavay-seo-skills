# Script reference

Every script prints its full options with `--help`. This page lists the ones that matter and the file formats passed between steps.

## crawl.py

Polite crawler. Writes `pages.jsonl`.

| Flag | Default | Notes |
|---|---|---|
| `--sitemap URL` | | Sitemap or sitemap index. Gzipped sitemaps work |
| `--urls FILE` | | One URL per line, or a CSV with URLs in the first column |
| `--limit N` | all | Stop after N pages |
| `--include REGEX` | | Only crawl matching URLs |
| `--exclude REGEX` | | Skip matching URLs |
| `--delay SECONDS` | 1.0 | Never below 0.5. A larger robots.txt Crawl-delay wins |
| `--user-agent UA` | skill UA | Identify yourself when crawling a client site |
| `--extractor` | auto | auto, trafilatura or heuristic |
| `--min-par-chars N` | 60 | Shorter text blocks are ignored |

Behavior. Respects robots.txt for the user agent. Backs off on 429 and 503 and honors Retry-After. Skips images, PDFs and other non-HTML files. Marks a page not indexable when it has noindex or a canonical pointing elsewhere.

One line of `pages.jsonl`.

```json
{"url": "https://example.com/blog/a", "status": 200, "final_url": "https://example.com/blog/a",
 "redirected": false, "content_type": "text/html", "title": "...", "h1": "...",
 "canonical": "https://example.com/blog/a", "meta_description": "...", "meta_robots": "",
 "indexable": true, "extractor": "trafilatura", "word_count": 1450,
 "paragraphs": [{"n": 1, "text": "..."}],
 "content_links": ["https://example.com/product/x"],
 "all_internal_links": ["https://example.com/", "https://example.com/pricing"]}
```

`content_links` are links inside the main content. Navigation and footer links are left out, so a nav link to a target does not block an in-text link to it. `all_internal_links` holds every internal href on the page for reference.

## gsc_pages.py

Needs `pip install google-auth requests` and `GOOGLE_APPLICATION_CREDENTIALS`.

| Flag | Default | Notes |
|---|---|---|
| `--site` | required | Exact property string |
| `--months N` | 3 | Complete calendar months |
| `--start`, `--end` | | Override the window, YYYY-MM-DD |
| `--page-regex` | | Server-side page filter |
| `--search-type` | web | web, image, video, news, discover |
| `--skip-queries` | off | Pages table only |
| `--out-prefix` | gsc | Writes `gsc_pages.csv` and `gsc_page_queries.csv` |

## match.py

| Flag | Default | Notes |
|---|---|---|
| `--pages` | required | JSONL from crawl.py |
| `--source-pattern`, `--target-pattern` | all pages | Regex on the URL |
| `--targets-file` | | One target URL per line. Uncrawled targets use the slug and their queries |
| `--exclude-pattern`, `--exclude-file` | | Sources to leave alone |
| `--gsc-pages`, `--gsc-queries` | | CSVs from gsc_pages.py or a Search Console export |
| `--keywords` | | CSV with keyword, volume, intent, difficulty |
| `--backend` | auto | sentence-transformers, ollama, tfidf, overlap |
| `--floor` | per backend | See the table in SKILL.md |
| `--top-targets` | 2 | Targets kept per paragraph |
| `--max-per-source` | 2 | New links per source page |
| `--max-per-target` | 5 | New links per target page |
| `--max-anchor-uses` | 2 | Uses of one anchor across the site |
| `--min-anchor-chars` | 4 | Acronyms in `--acronyms` are allowed below this |
| `--brand` | | Comma list. Brand-only anchors are dropped |
| `--exact-only` | off | No topical rows |
| `--type-map REGEX=TYPE` | | Repeatable page type rules |
| `--out` | candidates.csv | Also writes `_summary.json` and `_anchors.txt` |

Candidates CSV columns. `source_url, source_type, paragraph_no, paragraph_text, find_text, draft, anchor, anchor_source, target_url, target_title, target_type, match, similarity, anchor_uses, flag, priority, target_inlinks, impressions, position, ctr, keyword_volume, why`.

`anchor_source` is gsc_query, title or title_ngram. Fill `draft` for topical rows before building the sheet.

## build_sheet.py

| Flag | Default | Notes |
|---|---|---|
| `--candidates` | candidates.csv | Drafts filled in |
| `--summary` | `<candidates>_summary.json` | Adds the Summary tab |
| `--out` | internal-links.xlsx | `.csv` also works. Falls back to CSV without openpyxl |
| `--batch-size N` | | Numbered batches instead of Quick wins grouping |
| `--drop-flagged` | off | Leave out rows with QA flags other than near_floor |
