#!/usr/bin/env python3
"""Run a GA4 Data API report and write CSV.

Paginates with limit and offset until every row is fetched. Warns when GA4
reports thresholding, sampling or an "(other)" row, because those change how far
the numbers can be trusted.

Filters use "dimension match_type value". Repeat --filter to AND them.
Match types: exact, contains, begins_with, ends_with, full_regexp, partial_regexp.
Prefix the match type with not_ to exclude, for example "country not_exact India".

Dates take YYYY-MM-DD or GA4 relative values such as yesterday, today or 28daysAgo.

Examples:
  python3 ga4_report.py --property 123456789 --start 2026-10-01 --end 2026-10-31 \
      --dimensions sessionDefaultChannelGroup --metrics sessions,keyEvents --out channels.csv
  python3 ga4_report.py --property 123456789 --dimensions landingPagePlusQueryString \
      --metrics sessions,engagedSessions,keyEvents \
      --filter "sessionDefaultChannelGroup exact Organic Search" --out organic_landing.csv
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gauth import GA4_SCOPE, ApiError, call, die, session  # noqa: E402

MATCH = {"exact": "EXACT", "contains": "CONTAINS", "begins_with": "BEGINS_WITH", "ends_with": "ENDS_WITH",
         "full_regexp": "FULL_REGEXP", "partial_regexp": "PARTIAL_REGEXP"}
PAGE_SIZE = 100000
HINT = ("Add {who} in GA4, Admin, Property access management, as Viewer.\n"
        "Use the numeric property ID, not the G- measurement ID. Run test_access.py to list the IDs you can read.")


def last_month() -> tuple[str, str]:
    end = dt.date.today().replace(day=1) - dt.timedelta(days=1)
    return end.replace(day=1).isoformat(), end.isoformat()


def check_date(d: str) -> str:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}|today|yesterday|\d+daysAgo", d):
        return d
    die(f"Bad date '{d}'. Use YYYY-MM-DD, today, yesterday or NdaysAgo.")


def parse_filter(text: str) -> dict:
    parts = text.split(None, 2)
    if len(parts) != 3:
        die(f"Bad filter '{text}'. Use 'dimension match_type value', for example "
            "'sessionDefaultChannelGroup exact Organic Search'.")
    dim, mt, value = parts
    neg = mt.startswith("not_")
    mt = mt.removeprefix("not_")
    if mt not in MATCH:
        die(f"Bad match type '{parts[1]}'. Use {', '.join(MATCH)} or not_ plus one of them.")
    f = {"filter": {"fieldName": dim, "stringFilter": {"matchType": MATCH[mt], "value": value}}}
    return {"notExpression": f} if neg else f


def main(argv=None) -> int:
    d_start, d_end = last_month()
    ap = argparse.ArgumentParser(description="GA4 Data API runReport to CSV, with pagination.")
    ap.add_argument("--property", required=True, help="Numeric GA4 property ID, for example 123456789")
    ap.add_argument("--start", default=d_start, help=f"Start date (default {d_start}, start of last month)")
    ap.add_argument("--end", default=d_end, help=f"End date (default {d_end}, end of last month)")
    ap.add_argument("--dimensions", default="date", help="Comma list (default date). Up to 9")
    ap.add_argument("--metrics", default="sessions", help="Comma list (default sessions). Up to 10")
    ap.add_argument("--filter", action="append", default=[], help="'dimension match_type value'. Repeatable")
    ap.add_argument("--limit", type=int, default=0, help="Stop after this many rows (default all)")
    ap.add_argument("--out", default="ga4.csv", help="Output CSV (default ga4.csv)")
    args = ap.parse_args(argv)

    pid = args.property.split("/")[-1].strip()
    if pid.upper().startswith("G-") or not pid.isdigit():
        die(f"'{args.property}' is not a GA4 property ID. Use the numeric ID from GA4, Admin, Property details. "
            "A G- value is a measurement ID.")
    dims = [d.strip() for d in args.dimensions.split(",") if d.strip()]
    mets = [m.strip() for m in args.metrics.split(",") if m.strip()]
    if not mets:
        die("At least one metric is required.")

    body = {"dateRanges": [{"startDate": check_date(args.start), "endDate": check_date(args.end)}],
            "dimensions": [{"name": d} for d in dims], "metrics": [{"name": m} for m in mets]}
    if args.filter:
        exprs = [parse_filter(f) for f in args.filter]
        body["dimensionFilter"] = exprs[0] if len(exprs) == 1 else {"andGroup": {"expressions": exprs}}

    s, identity = session([GA4_SCOPE])
    url = f"https://analyticsdata.googleapis.com/v1beta/properties/{pid}:runReport"
    print(f"Property {pid} {args.start} to {args.end} dims={dims} metrics={mets}", file=sys.stderr)

    total, offset, row_count, meta = 0, 0, None, {}
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(dims + mets)
        while True:
            size = PAGE_SIZE if not args.limit else min(PAGE_SIZE, args.limit - total)
            try:
                data = call(s, "POST", url, "Google Analytics Data API", HINT,
                            body=dict(body, limit=size, offset=offset))
            except ApiError as e:
                die(str(e))
            rows = data.get("rows", [])
            row_count = data.get("rowCount", row_count or 0)
            meta = data.get("metadata", meta)
            for r in rows:
                w.writerow([v.get("value", "") for v in r.get("dimensionValues", [])] +
                           [v.get("value", "") for v in r.get("metricValues", [])])
            total += len(rows)
            offset += len(rows)
            print(f"  rows {total} of {row_count}", file=sys.stderr)
            if not rows or total >= (row_count or 0) or (args.limit and total >= args.limit):
                break

    print(f"Wrote {total} rows to {args.out}", file=sys.stderr)
    if meta.get("subjectToThresholding"):
        print("Warning. GA4 applied thresholding to this report. Small rows may be hidden.", file=sys.stderr)
    if meta.get("samplingMetadatas"):
        print("Warning. This report is sampled. Treat small segments with care.", file=sys.stderr)
    if meta.get("dataLossFromOtherRow"):
        print("Warning. Some rows were grouped into (other). Narrow the dimensions or the date range.",
              file=sys.stderr)
    if total == 0:
        print("No rows. Check the dates, the filters and that the property collects data.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
