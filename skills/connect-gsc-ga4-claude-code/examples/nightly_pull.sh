#!/usr/bin/env bash
# Nightly Search Console and GA4 pull. Writes dated CSVs to $OUT_DIR.
# Edit the four settings below, then schedule it with cron or launchd.
set -euo pipefail

SCRIPTS="$HOME/.claude/skills/connect-gsc-ga4-claude-code/scripts"   # where this skill lives
OUT_DIR="$HOME/search-data"                                          # where CSVs go
GSC_SITE="sc-domain:example.com"                                     # exact property string
GA4_PROPERTY="123456789"                                             # numeric GA4 property ID

export GOOGLE_APPLICATION_CREDENTIALS="${GOOGLE_APPLICATION_CREDENTIALS:-$HOME/.config/gsc-ga4/key.json}"
PY="${PYTHON:-python3}"

# Search Console data settles after about 3 days, so pull the day 3 days ago.
DAY=$("$PY" -c 'import datetime as d; print(d.date.today() - d.timedelta(days=3))')
YESTERDAY=$("$PY" -c 'import datetime as d; print(d.date.today() - d.timedelta(days=1))')
mkdir -p "$OUT_DIR/gsc" "$OUT_DIR/ga4" "$OUT_DIR/logs"

"$PY" "$SCRIPTS/gsc_query.py" --site "$GSC_SITE" --start "$DAY" --end "$DAY" \
  --dimensions date,query,page --out "$OUT_DIR/gsc/$DAY.csv"

"$PY" "$SCRIPTS/ga4_report.py" --property "$GA4_PROPERTY" --start "$YESTERDAY" --end "$YESTERDAY" \
  --dimensions date,sessionDefaultChannelGroup,landingPagePlusQueryString \
  --metrics sessions,engagedSessions,keyEvents --out "$OUT_DIR/ga4/$YESTERDAY.csv"

echo "$(date) pulled GSC $DAY and GA4 $YESTERDAY"
