---
name: bhavay-content-brief
description: Generates an SEO and AEO content brief for a target keyword or an existing URL that needs a refresh. Builds the brief from the live SERP, the AI answers in ChatGPT, Perplexity and Google AI Overviews, competitor teardowns, a coverage map of competitor headings and Search Console data. Ships a fill-in content brief template, a complete sample brief, a teardown script that extracts competitor headings, FAQs, schema and statistics and clusters them into must-cover topics, and a brief linter. Runs on Claude's own web search and browsing, and works with SE Ranking, Semrush, DataForSEO, Screaming Frog MCP, Apify, Ollama and Hugging Face embeddings when the user has them. Use when asked for a content brief, a content brief template, an SEO brief, an AEO or GEO brief, a writer brief, a refresh brief, a content outline, SERP analysis for a keyword, or a brief for a page that should rank in Google and get cited by AI engines.
license: CC-BY-4.0
---

# Bhavay's SEO and AEO Content Brief

By [Bhavay Gupta](https://bhavay.com), B2B SaaS SEO and AEO consultant. Free to use, share and adapt under CC BY 4.0, with credit to bhavay.com. Docs and updates: https://bhavay.com/resources/skills/bhavay-content-brief

## Quick start

**Say to Claude.** "Write a content brief for 'expense management software comparison' for the US market" or "Write a refresh brief for https://example.com/blog/post".

**It needs.** A keyword or a URL, and the market. A client context file makes the brief specific to the brand. Python 3.9 or later runs the teardown and the linter.

**You get.** One Markdown brief named `<keyword> - brief` that follows [templates/brief-template.md](templates/brief-template.md). It has the target, the page type and angle, a full outline with an instruction under every heading, must-cover topics, entities, sourced facts, FAQ, AEO rules, schema, links, a word count range and an evidence appendix. See [examples/sample-brief.md](examples/sample-brief.md) for a finished one.

**Install.** Put this folder in `~/.claude/skills/bhavay-content-brief/` for Claude Code, or upload it as a zip under Skills in the Claude app settings. Then run `pip install beautifulsoup4 requests` once.

Turn a target keyword, or an existing URL that needs a refresh, into a brief a writer can execute without guessing. The brief carries instructions and evidence. It never contains drafted paragraphs. Writing the article is the writer's job.

## Inputs

- [ ] **Target.** The keyword, or the URL to refresh.
- [ ] **Market and language.** For example US English.
- [ ] **Client context file.** ICP, product names, claims allowed and forbidden, competitors never to link, tone notes and banned phrases. Every brief for an account reads this file. Without it briefs come out generic, so say so in the brief metadata.
- [ ] **Search Console property.** Refresh mode only.
- [ ] **Own-site crawl or sitemap.** For internal link targets.

## Works with

The default path needs nothing beyond Claude and Python. Claude's own web search and browsing gather the SERP and the AI answers. The bundled scripts do the teardown, the coverage map and the linter. Before starting, check which of the tools below the user has. Use the strongest option for each step and tell the user which ones you are using.

| Tool | What it adds |
|---|---|
| SE Ranking | Keyword metrics, the live SERP, question keywords, related terms, AI search prompts and the pages AI engines cite. |
| Semrush or DataForSEO | A second source or a substitute for keyword and SERP data, including the AI Overview block on advanced SERP pulls. |
| Google Search Console | The queries a live page already ranks for, which drive refresh mode. |
| Screaming Frog MCP | A list-mode crawl of competitor pages with rendering, when plain fetches fail. |
| Apify | Bulk reads of pages that block crawlers. |
| Ollama | Cheap, private bulk extraction of headings, FAQs, entities and statistics with `llama3.2:3b`. |
| Hugging Face embeddings | `BAAI/bge-small-en-v1.5` or `bge-base-en-v1.5` through sentence-transformers, for tighter topic clusters. |

Routes and settings for each tool are in [reference/tools.md](reference/tools.md).

## Run it

```bash
S=path/to/bhavay-content-brief/scripts

# After collecting the top 10 and the AI-cited URLs into serp_urls.txt, in SERP order.
python3 $S/teardown.py --urls serp_urls.txt --out-prefix teardown

# After writing the brief.
python3 $S/lint_brief.py "<keyword> - brief.md" --banned banned_phrases.txt
```

`teardown.py` writes `teardown.json` with every page's headings, word count, schema types, FAQ questions and statistic sentences. It also writes `teardown_coverage.csv` with topics tiered as must-cover, recommended or optional angle, and `teardown_stats.csv` with statistics and the links next to them. Pages that block the fetch are listed as unreadable. Read those with a browser tool, put their headings in a CSV with columns url, level and heading, and rerun with `--headings-csv`.

## Method

### 1. SERP and demand
Pull the top 10 organic results, People Also Ask, the AI Overview if present, keyword volume, difficulty, intent, question keywords and related terms. For GEO, pull the prompts around the topic and the pages AI engines cite for them. Run the core prompt in ChatGPT and Perplexity and note which sources they cite.

**Without an SEO API.** Use Claude's web search for the primary keyword and two or three close variants. Treat the combined results as the SERP sample and say so in the evidence appendix. With a browser tool, open the Google results page to read People Also Ask and any AI Overview, and open ChatGPT and Perplexity to run the core prompt and record the cited sources. Without a browser tool, search the core prompt as a question and note the pages that answer it. Write volume and difficulty as "not available". Never estimate them. In refresh mode, Search Console impressions stand in for volume.

Reserve advanced SERP pulls that include the AI Overview block for priority terms. They cost more.

### 2. Intent check
Classify the page type the SERP rewards. Guide, listicle, comparison, landing page, tool or glossary. If the SERP rewards a format the brand can't credibly produce, say so and stop. A brief for the wrong format wastes a writer's week.

### 3. Competitor teardown
For each ranking and AI-cited page extract H1 to H3 headings, word count, FAQ questions, schema types, named entities, and every statistic with its source URL. `teardown.py` covers all of these except entities. Pull entities from the headings and the AI answers, or with Ollama at volume. Never trust Apify's RAG browser for anything in the page head. It strips the entire head section.

### 4. Coverage map
Cluster every competitor heading into topics. `teardown.py` does this.
- A topic covered by 7 or more of 10 pages is a **must-cover** section.
- A topic covered by 3 to 6 pages is **recommended**.
- A topic covered by 1 or 2 pages is an **optional angle**, and often the differentiator.

The thresholds scale when fewer than 10 pages were read. Skim the clusters before using them. Merge near-duplicates and split any cluster that mixes two ideas. Tune with `--threshold`.

### 5. Refresh mode, existing URLs only
Crawl the live page and pull its Search Console queries for the last 3 complete months. Queries the page ranks for but never addresses become new sections. Cap the word count target at 1.4 times the live word count. Beyond that the page loses its intent. The `bhavay-gsc-ga4` skill has a query script for this.

### 6. AEO requirements
For every H2, specify the question it answers and require an answer-first opening of one or two sentences that stands alone if quoted. List the facts and statistics the section must include, each with a source URL, so the page earns citations. Check `teardown_stats.csv` for numbers competitors cite, then trace each one to its primary source before it goes in the brief.

### 7. Internal links
Propose 3 to 6 internal link targets from the brand's own crawl with suggested anchors. The `bhavay-internal-linking` skill does this at scale.

### 8. Assemble the brief
Fill [templates/brief-template.md](templates/brief-template.md). Keep every section. Delete the guidance lines.

| Section | Contents |
|---|---|
| Brief metadata | Mode, brand, date sampled, data sources, client context file |
| Target | Primary keyword, secondary keywords, market, volume, difficulty, intent, core AI prompt |
| Page type and angle | The format the SERP rewards and the angle that beats it |
| Title and meta | Title tag direction and meta description direction, not final copy |
| Outline | H2 and H3 structure, with an instruction under every heading |
| Must-cover topics | From the coverage map, with how many competitors cover each |
| Entities | Terms and concepts the page must mention |
| Facts and statistics | Each with its source URL |
| FAQ | Questions from PAA and the prompt research |
| AEO rules | Answer-first openings, extractable definitions, the questions each H2 answers |
| Schema | Recommended types for the page |
| Links | Internal targets with anchors, external sources allowed |
| Word count | A range justified by the SERP, capped at 1.4x live in refresh mode |
| Do not | Claims the brand forbids, competitors never to link |
| Evidence appendix | Every URL reviewed and every data source used |

Claude writes the brief from the structured data. It does not recompute numbers.

### 9. Linter pass
Run `lint_brief.py` on the finished brief. It flags drafted paragraphs, time or effort estimates, statistics with no source URL on the line, banned phrases from the client context file, dashes used as punctuation and unfilled placeholders. Fix every hit. Then read the brief once more and confirm every statistic has a source URL.

## Output

One document per brief, named `<keyword> - brief`. End it with the evidence appendix listing the URLs reviewed and the data sources used, so a reviewer can verify any line. Tell the user which tools fed the brief and which steps ran on the default path.
