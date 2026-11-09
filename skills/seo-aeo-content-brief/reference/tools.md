# Tool routes for the content brief

The default path is Claude's web search and browsing plus the bundled scripts. Use these routes when the user has the tool.

## SERP and demand

- **SE Ranking first.** Keyword metrics, live SERP, question keywords, related terms, AI search prompts and the pages AI engines cite for them.
- **Semrush or DataForSEO** as a second source or substitute. Use advanced SERP pulls that include the AI Overview block only for priority terms. They cost more.
- **Claude web search.** Search the primary keyword and two or three variants. Record the result URLs in order. Label the set as a web search sample in the evidence appendix, because it is not a ranked Google SERP.
- **Browser tool.** Open the Google results page for the keyword to read People Also Ask and the AI Overview. Open ChatGPT and Perplexity, run the core prompt, and copy the cited URLs. Note the date, because answers change.

## Competitor pages

- **Default.** `scripts/teardown.py --urls serp_urls.txt`. Polite, 1 request per second, robots.txt respected.
- **Screaming Frog MCP.** List-mode crawl of the top 10 and the AI-cited URLs, then a bulk export of page content. Use it when pages need JavaScript rendering. Tool names differ between Screaming Frog MCP servers, so list the tools first.
- **Apify.** Bulk reads where a crawl is blocked. Never trust Apify's RAG browser for anything in the page head. It strips the entire head section.
- **Blocked pages.** Read them in a browser tool, put the headings in a CSV with columns url, level and heading, and pass it with `--headings-csv`.

## Bulk extraction with Ollama

- Use `llama3.2:3b` to pull headings, FAQs, entities and statistics with their source URLs from each competitor page. Cheap, private and repeatable.
- Ask for JSON with fixed keys. Validate it and drop any statistic without a URL.
- Avoid qwen3 for extraction into fixed formats. It leaks reasoning text into the output.

## Clustering with Hugging Face embeddings

- `pip install sentence-transformers`, then `teardown.py --backend sentence-transformers`.
- The script uses `BAAI/bge-small-en-v1.5`. `bge-base-en-v1.5` is slightly better if you adapt the script.
- Default join threshold is 0.78 for embeddings and 0.35 for TF-IDF and token overlap. Raise it when clusters mix ideas. Lower it when the same idea splits across clusters.

## Search Console for refresh mode

- Pull page and query rows for the live URL for the last 3 complete months.
- The `connect-gsc-ga4-claude-code` skill has the setup and `gsc_query.py`. Filter with `--filters "page equals https://example.com/blog/post"`.
