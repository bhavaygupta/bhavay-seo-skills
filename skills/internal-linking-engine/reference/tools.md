# Tool routes for the internal linking engine

The bundled scripts cover every step. Use the routes below when the user has the tool and it does the step better.

## Screaming Frog MCP

Best for large sites, JavaScript-rendered pages and sites where a full inlinks map matters.

- Crawl in polite mode. Single thread, at least 1000 ms delay, back off on 429.
- The tool names below come from one Screaming Frog MCP server. Other servers name the same steps differently. List the server's tools first.
- Run `sf_crawl` and poll `sf_crawl_progress`.
- Export Internal All with `sf_export_seo_element_urls`, All Inlinks with `sf_generate_bulk_export`, and page text with `sf_bulk_export_page_content`.
- Read NDJSON with `sf_read_text_file` at 500 rows or fewer per call.
- Close the Screaming Frog desktop app before loading a saved crawl with `sf_load_crawl`, or the database locks.
- To reuse the bundled matcher, convert the export into the `pages.jsonl` format in [scripts.md](scripts.md). Keep `content_links` to in-content links only, taken from All Inlinks where the link position is Content.

## Search Console

- `scripts/gsc_pages.py` calls the Search Console API with a service account. Setup steps are in the `connect-gsc-ga4-claude-code` skill.
- No API access is fine. Export Pages and Queries from the Search Console Performance report. `match.py --gsc-pages` reads the Pages export as is. The interface export has no page and query pairs, so anchors fall back to titles.

## Keyword tools

- SE Ranking, Semrush or DataForSEO. Send every line of `candidates_anchors.txt` in one batched keyword-metrics call. Ask for volume, difficulty and intent for the user's market.
- Save as `keywords.csv` with columns `keyword, volume, intent, difficulty`. Intent values are transactional, commercial, navigational or informational.
- Do not re-pull to patch gaps. Missing volume means low demand for scoring purposes.

## Apify

- Use a website content crawler actor when a site blocks plain requests or needs a real browser.
- Never trust Apify's RAG browser for anything in the page head. It strips the entire head section, so titles and canonicals come back empty. Take those from the sitemap crawl.

## Hugging Face embeddings

- `pip install sentence-transformers`, then `match.py --backend sentence-transformers`.
- Default model `BAAI/bge-small-en-v1.5`. Use `--st-model BAAI/bge-base-en-v1.5` for a little more accuracy. `BAAI/bge-m3` handles non-English sites.
- The first run downloads the model. Later runs work offline with `HF_HUB_OFFLINE=1`.

## Ollama

- Embeddings. `ollama pull nomic-embed-text`, then `match.py --backend ollama`. Set `--ollama-url` or `OLLAMA_HOST` if Ollama runs elsewhere.
- Drafting topical rows. Use `llama3.2:3b`. Avoid qwen3 for drafting, it leaks reasoning text into the output.
- Prompt shape that works. Give the paragraph, the anchor and the target title. Ask for one sentence under 30 words that would follow the paragraph naturally and contains the anchor exactly once in double brackets. Ask for the sentence only.
- Length-check every draft. Strip quotes and prefixes such as "Here is the sentence". Drop anything that repeats the paragraph.

## Small machines

- On an 8 GB machine load one heavy model at a time.
- Run embeddings and drafting as separate steps.
- Set Ollama `keep_alive` to `1m` and run `ollama stop` between heavy steps.
- The TF-IDF and token-overlap backends need almost no memory and suit very large sites.
