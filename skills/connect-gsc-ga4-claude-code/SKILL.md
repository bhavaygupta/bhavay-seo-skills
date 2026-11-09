---
name: connect-gsc-ga4-claude-code
description: Connects Google Search Console and Google Analytics 4 to Claude Code through the official Google Search Console API and GA4 Data API, with no MCP server or extra connector. Covers the Google Cloud project, service account versus OAuth, granting property access, credential handling, bundled Python scripts that test access and pull Search Console and GA4 reports to CSV with pagination, the data limits that trip people up, and scheduled pulls with cron or launchd. Use when asked to connect, set up or troubleshoot GSC or GA4 access in Claude Code, to pull Search Console or GA4 data with Python, to fix a 403 error or an empty site list, to automate a nightly SEO data export, or before any skill that needs Search Console or GA4 data.
license: CC-BY-4.0
---

# Connect GSC and GA4 to Claude Code

By [Bhavay Gupta](https://bhavay.com), B2B SaaS SEO and AEO consultant. Free to use, share and adapt under CC BY 4.0, with credit to bhavay.com. Docs and updates: https://bhavay.com/resources/skills/connect-gsc-ga4-claude-code

## Quick start

**Say to Claude.** "Connect my Search Console and GA4 to Claude Code" or "Why does my Search Console API call return 403".

**It needs.** Python 3.9 or later, a Google account with access to the Search Console property and the GA4 property, and about 15 minutes for the Google Cloud steps.

**You get.** A working credential, a list of every site and property it can read, and three scripts that pull Search Console and GA4 data to CSV. Optional nightly scheduling with cron or launchd.

**Install.** Put this folder in `~/.claude/skills/connect-gsc-ga4-claude-code/` for Claude Code, or upload it as a zip under Skills in the Claude app settings. Then run `pip install -r scripts/requirements.txt` once.

Claude Code can call the Search Console API and the GA4 Data API directly with a small Python toolkit. For scheduled reporting and analysis this beats a connector. It is simpler, deterministic and version-controlled. Python does the pulls and the arithmetic. Claude reads the output and writes the analysis.

## Inputs

- [ ] **Google Cloud access.** Permission to create a project, or an existing project to use.
- [ ] **Auth choice.** Service account or OAuth. Section 1 helps pick.
- [ ] **Search Console property string.** For example `sc-domain:example.com` or `https://www.example.com/`. `test_access.py` lists the exact strings.
- [ ] **GA4 property ID.** The numeric ID from GA4, Admin, Property details. Not the G- measurement ID.
- [ ] **Property admin.** Someone who can add a user to each property, if the credential is a service account.

## Works with

The bundled scripts are the default. They need only `google-auth` and `requests` and call the REST endpoints directly. Check what the user already has and say which route you are using.

| Option | What it adds |
|---|---|
| gcloud CLI | `gcloud auth application-default login` gives credentials without a key file. The scripts pick them up automatically. |
| Google client libraries | `google-api-python-client` and `google-analytics-data` for people writing their own code. Snippets are in [reference/api-snippets.md](reference/api-snippets.md). |
| Claude Code scheduled routines | Pulls plus written analysis on a schedule. See section 9. |
| MCP servers | Google publishes a read-only [Google Analytics MCP server](https://developers.google.com/analytics/devguides/MCP). No official Google Search Console MCP server was found when this skill was written. Third-party MCP servers exist. This skill uses the official APIs directly, so there is nothing extra to run. |

## 1. Choose the auth model

| | Service account | OAuth (desktop app) |
|---|---|---|
| Best for | Scheduled, unattended pulls | When every property is already shared with one Google account |
| Access | Add the service account email to each property | Sign in once as the account that already has access |
| Browser step | None | One-time consent, then a stored refresh token |
| Watch out for | Every property owner must add the email | Refresh tokens expire after 7 days if the consent screen stays in External Testing mode |

If all your Search Console and GA4 access sits on one Google account, OAuth avoids asking every property owner to add a new user. For unattended jobs across many properties, use a service account.

## 2. Google Cloud setup

1. Create a project in Google Cloud Console. Creating projects inside a Workspace organization needs the Project Creator role. If you get a permission error, that's the role to ask your admin for.
2. Enable **Google Search Console API** and **Google Analytics Data API**. Add the **Google Analytics Admin API** if you want to list GA4 properties automatically. `test_access.py` uses it.
3. Create credentials.
   - Service account. IAM and Admin, Service Accounts, create, then Keys, add key, JSON.
   - OAuth. Google Auth Platform, create an OAuth client of type Desktop app. If the project lives in a Workspace organization, set the audience to Internal to avoid test-user caps and 7-day token expiry.
4. These APIs are free within quotas. The Custom Search JSON API is a different, billable product. Don't enable it by accident.

## 3. Grant property access

- **Search Console.** Settings, Users and permissions, add the service account email. Restricted is enough for reading data.
- **GA4.** Admin, Property access management, add the service account email as Viewer.

OAuth users skip this step when their own account already has access.

## 4. Credentials, never in the repo

Service account.

```bash
mkdir -p ~/.config/gsc-ga4 && mv ~/Downloads/key.json ~/.config/gsc-ga4/key.json
chmod 600 ~/.config/gsc-ga4/key.json
echo 'export GOOGLE_APPLICATION_CREDENTIALS="$HOME/.config/gsc-ga4/key.json"' >> ~/.zshrc
```

OAuth. Save the client JSON as `~/.config/gsc-ga4/client_secret.json`, then sign in once.

```bash
pip install google-auth-oauthlib
python3 scripts/oauth_login.py --client-secret ~/.config/gsc-ga4/client_secret.json
echo 'export GOOGLE_APPLICATION_CREDENTIALS="$HOME/.config/gsc-ga4/token.json"' >> ~/.zshrc
```

Add `*.json` key paths and any `token.json` to `.gitignore`. In cloud or scheduled runs, store the key as a secret environment variable, not a file in the repo.

## 5. Install and test

```bash
pip install -r scripts/requirements.txt
python3 scripts/test_access.py
python3 scripts/test_access.py --site sc-domain:example.com --property 123456789
```

The first command lists every Search Console property with its permission level and every GA4 property the credential can see. The second also runs a tiny query against one site and one property, which proves data access end to end. It exits with code 1 when any check fails.

If the site list is empty, the account has no Search Console access yet. If GA4 returns 403, the service account isn't on the property. The full error guide is in [reference/troubleshooting.md](reference/troubleshooting.md).

## 6. Pull data

Search Console. Any dimensions, any filters, every row.

```bash
python3 scripts/gsc_query.py --site sc-domain:example.com \
  --start 2026-10-01 --end 2026-10-31 --dimensions query,page \
  --filters "page contains /blog/" --out gsc_oct.csv
```

- Dimensions are date, query, page, country, device, searchAppearance and hour.
- Filter operators are equals, notEquals, contains, notContains, includingRegex and excludingRegex. Repeat `--filters` to combine them.
- Pages of 25,000 rows are fetched with `startRow` until the data runs out. `--row-limit` stops early.
- Dates default to last calendar month. `--data-state final` is the default.

GA4. Any dimensions and metrics, every row.

```bash
python3 scripts/ga4_report.py --property 123456789 \
  --start 2026-10-01 --end 2026-10-31 \
  --dimensions sessionDefaultChannelGroup,landingPagePlusQueryString \
  --metrics sessions,engagedSessions,keyEvents \
  --filter "sessionDefaultChannelGroup exact Organic Search" --out ga4_oct.csv
```

- Filter match types are exact, contains, begins_with, ends_with, full_regexp and partial_regexp. Prefix with `not_` to exclude.
- Dates take YYYY-MM-DD or GA4 values such as `yesterday` and `28daysAgo`.
- The script warns when GA4 applies thresholding, sampling or an (other) row.

Run any script with `--help` for every flag.

## 7. Tell Claude Code how to use it

Add a short section to the project's `CLAUDE.md`.

```markdown
## Search data
- GSC and GA4 pulls use the scripts in the connect-gsc-ga4-claude-code skill. Run the scripts. Never recompute their numbers by hand.
- Use complete date windows only. Weeks run Monday to Sunday. Never use rolling "last 7 days" presets.
- Split brand and non-brand with the regex in `toolkit/brand_regex.txt`. Confirm it before reporting.
- Write outputs to `data/` as CSV or JSON, then analyze.
```

## 8. Limits that trip people up

**Search Console**
- Data lags 2 to 3 days. Final data settles after about 3 days.
- 16 months of history. Store your own copies if you need longer.
- 25,000 rows per request. Paginate with `startRow`. The script does this.
- Query-level data excludes anonymized queries, so query totals undercount page totals. Report from page or property totals when the number matters.
- `sc-domain:` properties and URL-prefix properties are different strings. Use the exact one the account has.
- The URL Inspection API allows about 2,000 inspections a day per property.

**GA4**
- Quotas are tokens per property per hour and per day. Batch requests and cache results.
- Key events replaced conversions. Check which events are marked as key events before reporting on them.
- Thresholding and sampling can apply on small segments. Note it when a number looks off.

## 9. Run it on a schedule

- Deterministic pulls only, such as a nightly export, fit cron, launchd or GitHub Actions. `examples/nightly_pull.sh` pulls one day of Search Console data from 3 days ago and yesterday's GA4 data into dated CSVs. Edit the four settings at the top.
- **cron.** `examples/crontab.txt` has a ready line. Use absolute paths, because cron runs with a minimal environment.
- **launchd on macOS.** `examples/com.example.gsc-ga4-pull.plist` runs the same script daily and catches up after the Mac wakes. Steps are in the file.
- Pulls plus written analysis fit a Claude Code scheduled routine. Allowlist `googleapis.com` and `oauth2.googleapis.com`, store the key as a secret, and write results to an external destination like Sheets or a database. Each run is stateless.

## 10. Before trusting any number

- Confirm the property string and date range in the output. Every script prints both.
- Compare one figure against the Search Console or GA4 interface.
- If GA4 and Search Console disagree sharply, check tracking before calling it a traffic change.
