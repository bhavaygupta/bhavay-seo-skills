# Client library snippets

The bundled scripts call the REST endpoints with `google-auth` and `requests`. Use these snippets when you write your own code with the Google client libraries instead.

```bash
pip install google-api-python-client google-auth google-analytics-data
```

## Search Console

```python
from google.oauth2 import service_account
from googleapiclient.discovery import build

creds = service_account.Credentials.from_service_account_file(
    "/path/to/key.json", scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
gsc = build("searchconsole", "v1", credentials=creds)

print([s["siteUrl"] for s in gsc.sites().list().execute().get("siteEntry", [])])

rows, start = [], 0
while True:
    batch = gsc.searchanalytics().query(siteUrl="sc-domain:example.com", body={
        "startDate": "2026-10-01", "endDate": "2026-10-31",
        "dimensions": ["query", "page"], "rowLimit": 25000, "startRow": start,
    }).execute().get("rows", [])
    rows += batch
    if len(batch) < 25000:
        break
    start += 25000
print(len(rows))
```

## GA4

```python
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Dimension, Metric

client = BetaAnalyticsDataClient()  # reads GOOGLE_APPLICATION_CREDENTIALS
resp = client.run_report(RunReportRequest(
    property="properties/123456789",
    date_ranges=[DateRange(start_date="2026-10-01", end_date="2026-10-31")],
    dimensions=[Dimension(name="sessionDefaultChannelGroup")],
    metrics=[Metric(name="sessions"), Metric(name="keyEvents")],
))
for r in resp.rows:
    print(r.dimension_values[0].value, r.metric_values[0].value)
```

## REST endpoints the scripts use

| Purpose | Method and URL |
|---|---|
| List Search Console sites | `GET https://searchconsole.googleapis.com/webmasters/v3/sites` |
| Search Analytics query | `POST https://searchconsole.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query` |
| List GA4 properties | `GET https://analyticsadmin.googleapis.com/v1beta/accountSummaries` |
| GA4 report | `POST https://analyticsdata.googleapis.com/v1beta/properties/{id}:runReport` |

The site string must be URL-encoded in the path. `sc-domain:example.com` becomes `sc-domain%3Aexample.com`.
