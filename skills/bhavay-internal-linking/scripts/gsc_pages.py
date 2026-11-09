#!/usr/bin/env python3
"""Pull page and page+query data from the Google Search Console API.

Optional step for the bhavay-internal-linking skill. Writes two CSVs:
  <prefix>_pages.csv          page, clicks, impressions, ctr, position
  <prefix>_page_queries.csv   page, query, clicks, impressions, ctr, position

Default window is the last 3 complete calendar months. Pagination uses
rowLimit 25000 and startRow until the API returns a short page.

Auth: a service account JSON key in GOOGLE_APPLICATION_CREDENTIALS, with the
service account email added as a user on the Search Console property.
Application Default Credentials (gcloud auth application-default login with the
webmasters.readonly scope) also work.

Examples:
  export GOOGLE_APPLICATION_CREDENTIALS=$HOME/.config/gsc-ga4/key.json
  python3 gsc_pages.py --site sc-domain:example.com
  python3 gsc_pages.py --site https://www.example.com/ --page-regex "/(blog|product)/" --out-prefix gsc
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import sys
import time
from urllib.parse import quote

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
API = "https://searchconsole.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"
PAGE_SIZE = 25000


def last_complete_months(n: int, today: dt.date | None = None) -> tuple[str, str]:
    today = today or dt.date.today()
    first_this_month = today.replace(day=1)
    end = first_this_month - dt.timedelta(days=1)
    start = end.replace(day=1)
    for _ in range(n - 1):
        start = (start - dt.timedelta(days=1)).replace(day=1)
    return start.isoformat(), end.isoformat()


def get_session():
    try:
        import google.auth
        from google.auth.exceptions import DefaultCredentialsError
        from google.auth.transport.requests import AuthorizedSession
    except ImportError:
        sys.exit("Missing packages. Install them with:  pip install google-auth requests")

    key = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if key and not os.path.isfile(os.path.expanduser(key)):
        sys.exit(f"GOOGLE_APPLICATION_CREDENTIALS points to a file that does not exist: {key}")
    try:
        creds, _ = google.auth.default(scopes=SCOPES)
    except DefaultCredentialsError:
        sys.exit(
            "No Google credentials found.\n"
            "Set GOOGLE_APPLICATION_CREDENTIALS to the path of a service account JSON key, for example\n"
            "  export GOOGLE_APPLICATION_CREDENTIALS=$HOME/.config/gsc-ga4/key.json\n"
            "Then add the service account email as a user on the Search Console property.\n"
            "Setup guide: https://bhavay.com/resources/skills/bhavay-gsc-ga4"
        )
    return AuthorizedSession(creds), getattr(creds, "service_account_email", None)


def explain_error(resp, site: str, email: str | None) -> str:
    try:
        err = resp.json().get("error", {})
    except ValueError:
        err = {}
    msg = err.get("message", resp.text[:300])
    reasons = " ".join(str(d.get("reason", "")) for d in err.get("details", []) + err.get("errors", []))
    if resp.status_code == 403 and ("SERVICE_DISABLED" in reasons or "has not been used" in msg
                                    or "accessNotConfigured" in reasons):
        return ("The Search Console API is not enabled in this Google Cloud project.\n"
                "Enable it at https://console.cloud.google.com/apis/library/searchconsole.googleapis.com\n"
                f"API said: {msg}")
    if resp.status_code == 403:
        who = email or "the account behind these credentials"
        return (f"Permission denied for {site}.\n"
                f"Add {who} in Search Console, Settings, Users and permissions. Restricted is enough.\n"
                "Also check the property string. sc-domain:example.com and https://www.example.com/ "
                "are different properties.\n"
                f"API said: {msg}")
    if resp.status_code == 400:
        return f"Bad request. Check the dates, the dimensions and the property string.\nAPI said: {msg}"
    if resp.status_code == 401:
        return f"Credentials were rejected. Create a fresh key or sign in again.\nAPI said: {msg}"
    return f"HTTP {resp.status_code}. API said: {msg}"


def query_all(session, site: str, body: dict, email: str | None) -> list[dict]:
    url = API.format(site=quote(site, safe=""))
    rows, start = [], 0
    while True:
        payload = dict(body, rowLimit=PAGE_SIZE, startRow=start)
        for attempt in range(5):
            try:
                resp = session.post(url, json=payload, timeout=120)
            except Exception as e:  # token refresh failure or network error
                if type(e).__name__ == "RefreshError":
                    sys.exit("Could not get an access token. The key may be deleted or revoked, or the service "
                             f"account no longer exists. Create a new key.\nDetail: {e}")
                if attempt == 4:
                    sys.exit(f"Network error calling the Search Console API. Allow googleapis.com and "
                             f"oauth2.googleapis.com.\nDetail: {e}")
                time.sleep(2 ** attempt)
                continue
            if resp.status_code in (429, 500, 502, 503) and attempt < 4:
                wait = 2 ** attempt * 5
                print(f"  HTTP {resp.status_code}, retrying in {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            break
        if resp.status_code != 200:
            sys.exit(explain_error(resp, site, email))
        batch = resp.json().get("rows", [])
        rows.extend(batch)
        print(f"  {body['dimensions']} rows so far: {len(rows)}", file=sys.stderr)
        if len(batch) < PAGE_SIZE:
            return rows
        start += PAGE_SIZE


def write_csv(path: str, dims: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(dims + ["clicks", "impressions", "ctr", "position"])
        for r in rows:
            w.writerow(list(r["keys"]) + [r.get("clicks", 0), r.get("impressions", 0),
                                          round(r.get("ctr", 0.0), 6), round(r.get("position", 0.0), 2)])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pull Search Console page and page+query data to CSV.")
    ap.add_argument("--site", required=True,
                    help="Exact property string, for example sc-domain:example.com or https://www.example.com/")
    ap.add_argument("--months", type=int, default=3, help="Complete calendar months to pull (default 3)")
    ap.add_argument("--start", help="Override start date YYYY-MM-DD")
    ap.add_argument("--end", help="Override end date YYYY-MM-DD")
    ap.add_argument("--search-type", default="web", choices=["web", "image", "video", "news", "discover", "googleNews"])
    ap.add_argument("--page-regex", help="Only keep pages matching this RE2 regex (server side filter)")
    ap.add_argument("--skip-queries", action="store_true", help="Only pull the page table")
    ap.add_argument("--out-prefix", default="gsc", help="Output prefix (default gsc)")
    args = ap.parse_args(argv)

    start, end = last_complete_months(args.months)
    start, end = args.start or start, args.end or end
    session, email = get_session()
    print(f"Property {args.site}, {start} to {end}, type {args.search_type}", file=sys.stderr)

    base = {"startDate": start, "endDate": end, "type": args.search_type, "dataState": "final"}
    if args.page_regex:
        base["dimensionFilterGroups"] = [{"filters": [
            {"dimension": "page", "operator": "includingRegex", "expression": args.page_regex}]}]

    pages = query_all(session, args.site, dict(base, dimensions=["page"]), email)
    write_csv(f"{args.out_prefix}_pages.csv", ["page"], pages)
    print(f"Wrote {args.out_prefix}_pages.csv ({len(pages)} rows)", file=sys.stderr)
    if not pages:
        print("No rows. The property may be new, the filter too narrow, or the dates outside the 16 month window.",
              file=sys.stderr)

    if not args.skip_queries:
        pq = query_all(session, args.site, dict(base, dimensions=["page", "query"]), email)
        write_csv(f"{args.out_prefix}_page_queries.csv", ["page", "query"], pq)
        print(f"Wrote {args.out_prefix}_page_queries.csv ({len(pq)} rows). "
              "Query rows exclude anonymized queries, so they undercount page totals.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
