#!/usr/bin/env python3
"""Query the Search Console Search Analytics API and write CSV.

Handles pagination past the 25,000 row page size with startRow.

Filters use "dimension operator expression". Repeat --filters to AND them.
Operators: equals, notEquals, contains, notContains, includingRegex, excludingRegex.

Examples:
  python3 gsc_query.py --site sc-domain:example.com --start 2026-10-01 --end 2026-10-31 \
      --dimensions query,page --out gsc_oct.csv
  python3 gsc_query.py --site https://www.example.com/ --dimensions page \
      --filters "page contains /blog/" --filters "country equals usa" --out blog.csv
  python3 gsc_query.py --site sc-domain:example.com --dimensions date --aggregation byProperty
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import sys
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gauth import GSC_SCOPE, ApiError, call, die, session  # noqa: E402

DIMENSIONS = {"date", "query", "page", "country", "device", "searchAppearance", "hour"}
OPERATORS = {"equals", "notEquals", "contains", "notContains", "includingRegex", "excludingRegex"}
PAGE_SIZE = 25000
HINT = ("Add {who} in Search Console, Settings, Users and permissions. Restricted is enough.\n"
        "Check the property string. sc-domain:example.com and https://www.example.com/ are different properties.\n"
        "Run test_access.py to list the exact strings these credentials can see.")


def last_month() -> tuple[str, str]:
    end = dt.date.today().replace(day=1) - dt.timedelta(days=1)
    return end.replace(day=1).isoformat(), end.isoformat()


def parse_filter(text: str) -> dict:
    parts = text.split(None, 2)
    if len(parts) != 3 or parts[1] not in OPERATORS or parts[0] not in DIMENSIONS:
        die(f"Bad filter '{text}'.\nUse 'dimension operator expression', for example 'page contains /blog/'.\n"
            f"Operators: {', '.join(sorted(OPERATORS))}")
    return {"dimension": parts[0], "operator": parts[1], "expression": parts[2]}


def main(argv=None) -> int:
    d_start, d_end = last_month()
    ap = argparse.ArgumentParser(description="Search Console Search Analytics query to CSV, with pagination.")
    ap.add_argument("--site", required=True, help="sc-domain:example.com or https://www.example.com/")
    ap.add_argument("--start", default=d_start, help=f"YYYY-MM-DD (default {d_start}, start of last month)")
    ap.add_argument("--end", default=d_end, help=f"YYYY-MM-DD (default {d_end}, end of last month)")
    ap.add_argument("--dimensions", default="query,page", help="Comma list (default query,page). "
                    "date, query, page, country, device, searchAppearance, hour")
    ap.add_argument("--filters", action="append", default=[], help="'dimension operator expression'. Repeatable")
    ap.add_argument("--row-limit", type=int, default=0, help="Stop after this many rows (default all)")
    ap.add_argument("--type", default="web", choices=["web", "image", "video", "news", "discover", "googleNews"])
    ap.add_argument("--data-state", default="final", choices=["final", "all", "hourly_all"],
                    help="final excludes the last 2 to 3 days of fresh data (default final)")
    ap.add_argument("--aggregation", default="auto", choices=["auto", "byPage", "byProperty", "byNewsShowcasePanel"])
    ap.add_argument("--out", default="gsc.csv", help="Output CSV (default gsc.csv)")
    args = ap.parse_args(argv)

    dims = [d.strip() for d in args.dimensions.split(",") if d.strip()]
    bad = [d for d in dims if d not in DIMENSIONS]
    if bad:
        die(f"Unknown dimension {bad}. Use {', '.join(sorted(DIMENSIONS))}")
    for d in (args.start, args.end):
        try:
            dt.date.fromisoformat(d)
        except ValueError:
            die(f"Bad date '{d}'. Use YYYY-MM-DD.")

    body = {"startDate": args.start, "endDate": args.end, "dimensions": dims, "type": args.type,
            "dataState": args.data_state, "aggregationType": args.aggregation}
    if args.filters:
        body["dimensionFilterGroups"] = [{"groupType": "and", "filters": [parse_filter(f) for f in args.filters]}]

    s, identity = session([GSC_SCOPE])
    url = ("https://searchconsole.googleapis.com/webmasters/v3/sites/"
           f"{quote(args.site, safe='')}/searchAnalytics/query")
    print(f"{args.site} {args.start} to {args.end} dims={dims} type={args.type}", file=sys.stderr)

    total = 0
    start_row = 0
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(dims + ["clicks", "impressions", "ctr", "position"])
        while True:
            page_size = PAGE_SIZE if not args.row_limit else min(PAGE_SIZE, args.row_limit - total)
            try:
                data = call(s, "POST", url, "Search Console API", HINT,
                            body=dict(body, rowLimit=page_size, startRow=start_row))
            except ApiError as e:
                die(str(e))
            rows = data.get("rows", [])
            for r in rows:
                w.writerow(list(r.get("keys", [])) + [r.get("clicks", 0), r.get("impressions", 0),
                                                      round(r.get("ctr", 0.0), 6), round(r.get("position", 0.0), 2)])
            total += len(rows)
            print(f"  rows {total}", file=sys.stderr)
            if len(rows) < page_size or (args.row_limit and total >= args.row_limit):
                break
            start_row += len(rows)

    print(f"Wrote {total} rows to {args.out}", file=sys.stderr)
    if total == 0:
        print("No rows. Check the dates (data lags 2 to 3 days, history is 16 months), the filters and the property.",
              file=sys.stderr)
    if "query" in dims:
        print("Note. Query rows exclude anonymized queries, so totals here undercount page or property totals.",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
