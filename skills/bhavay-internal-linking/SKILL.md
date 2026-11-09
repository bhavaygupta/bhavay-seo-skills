---
name: bhavay-internal-linking
description: Builds an implementation-ready internal linking sheet for any website. Bundled Python scripts crawl a sitemap politely, pull Google Search Console page and query data, score every source paragraph against target pages with embeddings or TF-IDF, find exact-match anchor text, apply link guardrails and write a prioritized XLSX with the sentence to find, the words to link, the target URL and a reason for every link. Works with Screaming Frog MCP, SE Ranking, Semrush, DataForSEO, Apify, Ollama and Hugging Face models when the user has them. Use when asked for an internal linking tool, internal link suggestions, an internal link audit, internal link opportunities, anchor text ideas, orphan page fixes, which pages should link to a page, link equity to money pages or an internal linking plan for SEO.
license: CC-BY-4.0
---

# Bhavay's Internal Linking Engine

By [Bhavay Gupta](https://bhavay.com), B2B SaaS SEO and AEO consultant. Free to use, share and adapt under CC BY 4.0, with credit to bhavay.com. Docs and updates: https://bhavay.com/resources/skills/bhavay-internal-linking

## Quick start

**Say to Claude.** "Build an internal linking sheet for example.com. Sources are the blog. Targets are the product and solution pages."

**It needs.** Python 3.9 or later and a sitemap URL or a list of URLs. Search Console access is optional and makes the priorities much sharper.

**You get.** `internal-links.xlsx` with one row per link. Each row has the exact sentence to find, the words to link, the target URL, a priority score from 0 to 100 and one line on why the link matters. A Summary tab holds the QA report and the similarity distribution.

**Install.** Put this folder in `~/.claude/skills/bhavay-internal-linking/` for Claude Code, or upload it as a zip under Skills in the Claude app settings. Then run `pip install -r scripts/requirements.txt` once.

Find high-value internal links from source pages to target pages. Push authority and readers toward pages that rank but need help. Never stuff links.

## Inputs

Ask for anything missing. The run cannot start without the first three.

- [ ] **Site.** A sitemap URL, a sitemap index, or a file with one URL per line. A saved crawl export also works (CSV or XLSX with Address, Status Code, Indexability, Title, Meta Description, H1 and Word Count).
- [ ] **Source scope.** Pages that will carry the new links, for example `/blog/` and `/learn/`.
- [ ] **Target scope.** Pages the links point to, for example product, solution, pillar and comparison pages. A regex or a list of URLs.
- [ ] **Search Console property.** Optional. The exact string, such as `sc-domain:example.com` or `https://www.example.com/`. A Pages and Queries export from the Search Console interface also works.
- [ ] **Keyword data.** Optional. Volume and intent for the anchor candidates from any keyword tool.
- [ ] **Exclusions.** Source pages to leave alone, for example pages being redrafted.
- [ ] **Brand terms.** So brand-only anchors are dropped.

## Works with

The bundled scripts are the default. They run on Python alone. Before starting, check which of the tools below the user has. Use the strongest option for each step and tell the user which ones you are using.

| Tool | What it adds |
|---|---|
| Google Search Console API | Real impressions, positions and ranking queries, which drive target priority and the best anchors. |
| Screaming Frog MCP | A full rendered crawl with All Inlinks and page text, for large or JavaScript-heavy sites. |
| SE Ranking, Semrush or DataForSEO | Volume, difficulty and intent for every anchor candidate in one batched call. |
| Apify | Reads pages that block a plain crawler. |
| Hugging Face models via sentence-transformers | `BAAI/bge-small-en-v1.5` or `bge-base-en-v1.5` embeddings, which match by meaning instead of shared words. |
| Ollama | Local embeddings (`nomic-embed-text`) and local drafting of topical sentences with `llama3.2:3b`. |

Tool routes, model notes and memory tips are in [reference/tools.md](reference/tools.md). Every script flag is in [reference/scripts.md](reference/scripts.md).

## Run it

Scripts live in this skill's `scripts/` folder. Run them from a working folder such as `work/` so outputs stay together.

```bash
S=path/to/bhavay-internal-linking/scripts

# 1. Crawl. Polite by default. 1 request per second, robots.txt respected.
python3 $S/crawl.py --sitemap https://example.com/sitemap.xml --out pages.jsonl

# 2. Optional. Search Console pages and page+query data for the last 3 complete months.
python3 $S/gsc_pages.py --site sc-domain:example.com --out-prefix gsc

# 3. Match paragraphs to targets and apply the guardrails.
python3 $S/match.py --pages pages.jsonl \
  --source-pattern "/blog/" --target-pattern "/(product|solutions)/" \
  --gsc-pages gsc_pages.csv --gsc-queries gsc_page_queries.csv \
  --brand "example" --out candidates.csv

# 4. Draft the topical rows into the draft column of candidates.csv. See step 7 below.

# 5. Build the sheet and run QA.
python3 $S/build_sheet.py --candidates candidates.csv --out internal-links.xlsx
```

On the first run of `match.py`, say which similarity backend it picked. It prints the choice.

## Method

### 1. Inventory
- **Default.** `crawl.py` reads the sitemap, follows sitemap indexes and writes one JSON line per page. Each line has status, final URL, title, H1, canonical, meta robots, main-content paragraphs and the internal links inside the main content.
- **Screaming Frog MCP.** Crawl in polite mode and export Internal All, All Inlinks and page text. The full route is in [reference/tools.md](reference/tools.md).
- **Saved export.** Parse the file into a page map keyed by URL. Fetch body text with `crawl.py --urls` if the export has none.
- Keep only indexable HTML pages that return 200. Split them into source and target sets using the scopes. Flag orphans and thin pages. They gain the most from new links.

### 2. Demand from Search Console
Pull the last 3 complete months per page. Clicks, impressions, average position, CTR and the top queries each page ranks for. `gsc_pages.py` does this and paginates past 25,000 rows.
- **Target priority.** High impressions, average position between 5 and 20, and below-expected CTR means the page ranks but needs a push.
- **Anchor harvesting.** A target's real ranking queries become its anchor candidates. They are proven demand and match how Google already reads the page.
- **Orphan detection.** Pages with impressions but almost no editorial inlinks become priority targets.

Without Search Console, `match.py` favors targets with the fewest in-text links and takes anchors from titles and H1s. Say so in the summary.

### 3. Keyword value
`match.py` writes `candidates_anchors.txt`. Send every anchor in that file to the keyword source in one batched call. Get volume, difficulty and intent. Save them as `keywords.csv` with columns keyword, volume, intent and difficulty, then rerun `match.py` with `--keywords keywords.csv`. Commercial and buyer intent rank above generic phrases.

### 4. Source text
Body text comes from the crawl. `crawl.py` uses trafilatura when it is installed and a readability-style fallback otherwise. Both strip navigation, footers, cookie banners and sidebars. Paragraphs are the candidate placements.

### 5. Semantic matching
`match.py` builds a text for every target from its title, H1, meta description and top ranking queries. It scores every source paragraph against every target and keeps the best one or two targets above a similarity floor. Each backend has its own scale.

| Backend | Starting floor |
|---|---|
| sentence-transformers (bge) | 0.80 |
| Ollama embeddings | 0.70 |
| TF-IDF (scikit-learn) | 0.12 |
| Token overlap (pure Python) | 0.10 |

Read the similarity distribution in `candidates_summary.json`. Raise the floor if the set is weak. Lower it a little only when the set is tiny and the rows read well.

### 6. Match type
- **Exact.** The anchor phrase already appears in the paragraph. The instruction is to select those words and link them. No rewriting. `match.py` checks ranking queries first, then the target title and H1, then distinctive phrases from them.
- **Topical.** The phrase is absent. One short sentence is needed. `match.py` proposes the anchor and flags the row `needs_draft`.

### 7. Drafting, topical rows only
Write one short, natural sentence or trailing clause that carries the anchor and fits the paragraph. Put it in the `draft` column of `candidates.csv` with the anchor wrapped in double brackets, for example `[[cloud security posture]]`. Keep it under about 30 words. Strip quotes and stray suffixes. Rewrite or drop anything that reads awkwardly. For local drafting at volume, use `llama3.2:3b` on Ollama and review every line. Use `--exact-only` on `match.py` when the team wants no new copy at all.

### 8. Guardrails
`match.py` applies these. Keep the defaults unless the user asks.
- At most 2 new links per source page (`--max-per-source`).
- A cap per target page so one page does not collect dozens of identical anchors (`--max-per-target`, default 5).
- One anchor phrase used at most twice site-wide (`--max-anchor-uses`).
- One new link per paragraph and one per source and target pair.
- No self-links, including links to the source's own canonical.
- No links that already exist. A target already linked from the source's main content is skipped.
- No generic or brand-only anchors, and nothing under 4 characters except known acronyms such as SSO, MFA or API.
- Never place a link on an excluded page.

If the crawl is more than a day old when the sheet ships, recrawl the source pages with `crawl.py --urls` and rerun `match.py`, so no row proposes a link that now exists.

### 9. QA
`build_sheet.py` checks every row and flags failures. Exactly one bracketed anchor per topical row. Bracketed text matches the anchor column. Exact anchors appear in the sentence. No self-links. No duplicate source and target pairs. No anchor pointing at two different targets. Check by hand that the target title matches the target URL for a sample of rows. Report the similarity distribution so the team can judge the strength of the set.

## Priority score, 0 to 100

Blend three normalized signals.
- **Search opportunity, 40 percent.** Impressions multiplied by a position-gap factor. Higher when the target sits at positions 5 to 20 with weak CTR. A small boost for targets with one in-text link or none.
- **Anchor demand, 30 percent.** Keyword volume weighted by intent. Without keyword data, the anchor's Search Console impressions for that target. Title anchors get a low fixed value.
- **Semantic fit, 30 percent.** Similarity between paragraph and target, scaled from the floor to the best score in the run.

Sort the sheet by this score so the team works the highest-impact links first.

## Output

One xlsx with these columns in this order. `build_sheet.py` writes a CSV with the same columns when openpyxl is missing.

| Column | Contents |
|---|---|
| # | Row number |
| Batch | Quick wins, Exact matches or Needs a sentence. Or numbered batches with `--batch-size` |
| Status | To do |
| Source page | URL to edit |
| Source page type | blog, learn, pillar, product and so on. Custom rules with `--type-map` |
| Paragraph no. | Position of the paragraph on the page |
| Find this text | The exact sentence to search for, quoted verbatim. For topical rows, the last sentence of the paragraph |
| Replacement | Topical rows only. The drafted sentence with the bracketed anchor |
| Anchor text | Exact words to link |
| Link to | Target URL |
| Target page title | Title of the target |
| Target page type | Type of the target |
| How | Plain instruction for the implementer |
| Match | Exact or Topical |
| Similarity | Score from the backend in use |
| Anchor used site-wide | Count, to avoid overuse |
| Flag | For example needs_draft, needs_copy_edit, anchor_conflict or near_floor |
| Priority | 0 to 100 |
| Target in-text links today | Editorial inlinks the target already has from crawled pages |
| Why this link | One line of reasoning |
| Date done, Notes | Blank, for the implementer |

For topical rows, How reads "Add this sentence at the end of the paragraph, link the bracketed words, then delete the brackets".

## Finishing

Report links found, exact versus topical, sources and targets touched, existing links skipped, the backend and floor used, and any pages that could not be read. All of these are in the summary file. Save the xlsx and list a sample of rows for human review before anything ships.

## Troubleshooting

- **Crawl returns few paragraphs.** The site renders content with JavaScript. Use Screaming Frog MCP with rendering on, or Apify.
- **Many pages blocked.** robots.txt disallows them. Do not override it. Ask the site owner for an export instead.
- **Too many weak rows.** Raise `--floor` and tighten `--max-per-target`.
- **Almost no exact matches.** Load Search Console queries. Titles alone rarely appear verbatim in body copy.
- **Drafts empty or full of reasoning text.** The local model is a reasoning model such as qwen3. Switch to `llama3.2:3b`.
- **Machine swaps or stalls.** One heavy model at a time. Run `ollama stop` between steps.
- **Keyword source returns little.** Batch all anchors into one call. Don't re-pull to patch gaps.
- **sentence-transformers is slow on first run.** It downloads the model once, about 130 MB for bge-small.
