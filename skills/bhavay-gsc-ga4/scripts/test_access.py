#!/usr/bin/env python3
"""Check which Search Console sites and GA4 properties the credentials can see.

Lists every Search Console property with its permission level and every GA4
property from the Admin API. Optionally runs a one-row test query against one
site and one property, which proves data access end to end.

Examples:
  python3 test_access.py
  python3 test_access.py --site sc-domain:example.com --property 123456789
  python3 test_access.py --skip-ga4
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gauth import GA4_SCOPE, GSC_SCOPE, ApiError, call, session  # noqa: E402

GSC_HINT = ("Add {who} in Search Console, Settings, Users and permissions. Restricted is enough.\n"
            "Check the property string too. sc-domain:example.com and https://www.example.com/ are different.")
GA4_HINT = ("Add {who} in GA4, Admin, Property access management, as Viewer.\n"
            "Use the numeric property ID, not the G- measurement ID.")


def check_gsc(s, site: str | None) -> bool:
    print("\nSearch Console")
    try:
        data = call(s, "GET", "https://searchconsole.googleapis.com/webmasters/v3/sites",
                    "Search Console API", GSC_HINT)
    except ApiError as e:
        print(f"  FAILED\n  {str(e).replace(chr(10), chr(10) + '  ')}")
        return False
    sites = data.get("siteEntry", [])
    if not sites:
        print("  The API works, but these credentials see no Search Console properties.\n"
              f"  Add {s._identity} as a user on each property in Search Console, Settings, Users and permissions.\n"
              "  New users can take a few minutes to appear.")
        return False
    for e in sorted(sites, key=lambda x: x["siteUrl"]):
        note = "  (no data access, verify or ask for a user role)" if e["permissionLevel"] == "siteUnverifiedUser" else ""
        print(f"  {e['permissionLevel']:<20} {e['siteUrl']}{note}")
    if site:
        end = dt.date.today() - dt.timedelta(days=3)
        body = {"startDate": (end - dt.timedelta(days=27)).isoformat(), "endDate": end.isoformat(),
                "dimensions": ["date"], "rowLimit": 1}
        try:
            rows = call(s, "POST", "https://searchconsole.googleapis.com/webmasters/v3/sites/"
                        f"{quote(site, safe='')}/searchAnalytics/query", "Search Console API", GSC_HINT,
                        body=body).get("rows", [])
            print(f"  Test query on {site} OK. {'Data returned.' if rows else 'No rows in the last 28 days.'}")
        except ApiError as e:
            print(f"  Test query on {site} FAILED\n  {str(e).replace(chr(10), chr(10) + '  ')}")
            return False
    return True


def check_ga4(s, prop: str | None) -> bool:
    print("\nGoogle Analytics 4")
    ok = True
    props = []
    token = None
    try:
        while True:
            params = {"pageSize": 200}
            if token:
                params["pageToken"] = token
            data = call(s, "GET", "https://analyticsadmin.googleapis.com/v1beta/accountSummaries",
                        "Google Analytics Admin API", GA4_HINT, params=params)
            for acc in data.get("accountSummaries", []):
                for p in acc.get("propertySummaries", []):
                    props.append((acc.get("displayName", ""), p["property"].split("/")[-1], p.get("displayName", "")))
            token = data.get("nextPageToken")
            if not token:
                break
    except ApiError as e:
        print("  Could not list properties. The Admin API is only used for listing, so reports may still work.\n"
              f"  {str(e).replace(chr(10), chr(10) + '  ')}")
        ok = False
    else:
        if not props:
            print("  The API works, but these credentials see no GA4 properties.\n"
                  f"  Add {s._identity} as Viewer in GA4, Admin, Property access management.")
            ok = False
        for acc, pid, name in sorted(props):
            print(f"  {pid:<12} {name}   (account {acc})")
    if prop:
        pid = prop.split("/")[-1]
        body = {"dateRanges": [{"startDate": "7daysAgo", "endDate": "yesterday"}],
                "metrics": [{"name": "sessions"}], "limit": 1}
        try:
            data = call(s, "POST", f"https://analyticsdata.googleapis.com/v1beta/properties/{pid}:runReport",
                        "Google Analytics Data API", GA4_HINT, body=body)
            rows = data.get("rows", [])
            val = rows[0]["metricValues"][0]["value"] if rows else "0"
            print(f"  Test report on property {pid} OK. Sessions in the last 7 days {val}.")
            ok = True if not props else ok
        except ApiError as e:
            print(f"  Test report on property {pid} FAILED\n  {str(e).replace(chr(10), chr(10) + '  ')}")
            return False
    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="List the GSC sites and GA4 properties these credentials can read.")
    ap.add_argument("--site", help="Also run a test query on this Search Console property")
    ap.add_argument("--property", help="Also run a test report on this GA4 property ID")
    ap.add_argument("--skip-gsc", action="store_true")
    ap.add_argument("--skip-ga4", action="store_true")
    args = ap.parse_args(argv)

    scopes = ([] if args.skip_gsc else [GSC_SCOPE]) + ([] if args.skip_ga4 else [GA4_SCOPE])
    if not scopes:
        ap.error("Nothing to test.")
    s, identity = session(scopes)
    print(f"Credentials identity: {identity}")
    results = []
    if not args.skip_gsc:
        results.append(check_gsc(s, args.site))
    if not args.skip_ga4:
        results.append(check_ga4(s, args.property))
    print("\nAll checks passed." if all(results) else "\nSome checks failed. Read the messages above.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
