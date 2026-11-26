# Troubleshooting

The scripts print a plain explanation for each of these. This page covers the cause and the fix, with a link to the screen where you fix it.

## Quick links

Check the project name in the top bar of Google Cloud Console before changing anything. Most errors come from fixing the right thing in the wrong project.

| Screen | Use it to |
|---|---|
| [Enabled APIs](https://console.cloud.google.com/apis/dashboard) | See which APIs are on in this project |
| [Search Console API](https://console.cloud.google.com/apis/library/searchconsole.googleapis.com) | Enable the Search Console API |
| [Analytics Data API](https://console.cloud.google.com/apis/library/analyticsdata.googleapis.com) | Enable the GA4 Data API |
| [Analytics Admin API](https://console.cloud.google.com/apis/library/analyticsadmin.googleapis.com) | Enable GA4 property listing for `test_access.py` |
| [Service accounts](https://console.cloud.google.com/iam-admin/serviceaccounts) | Find the service account email, create or delete keys |
| [Credentials](https://console.cloud.google.com/apis/credentials) | See every key and OAuth client in the project |
| [OAuth clients](https://console.cloud.google.com/auth/clients) | Download or add an OAuth client secret |
| [OAuth audience](https://console.cloud.google.com/auth/audience) | Switch to Internal, add test users or publish the app |
| [Search Console API quotas](https://console.cloud.google.com/apis/api/searchconsole.googleapis.com/quotas) | Check Search Console request limits |
| [Analytics Data API quotas](https://console.cloud.google.com/apis/api/analyticsdata.googleapis.com/quotas) | Check GA4 Data API request limits |
| [Search Console](https://search.google.com/search-console) | Settings, then Users and permissions, to add a user |
| [Google Analytics](https://analytics.google.com/analytics/web/) | Admin, then Property access management, to add a user |

## Errors and fixes

| Message or symptom | Cause | Fix |
|---|---|---|
| No Google credentials found | `GOOGLE_APPLICATION_CREDENTIALS` is unset and there are no gcloud credentials | Export the variable with the key path, or run `oauth_login.py` |
| Points to a file that does not exist | Wrong path, or `~` inside quotes that was never expanded | Use `$HOME/...` in the export line |
| Is an OAuth client secret, not a credential | The client JSON was used as the credential | Run `oauth_login.py --client-secret` with it, then point the variable at the token file |
| API is not enabled in your Google Cloud project | The API is off in the project that owns the key | Enable the [Search Console API](https://console.cloud.google.com/apis/library/searchconsole.googleapis.com) or [Analytics Data API](https://console.cloud.google.com/apis/library/analyticsdata.googleapis.com) in that project and wait a minute |
| Site list is empty | The credential works but has no Search Console access | In [Search Console](https://search.google.com/search-console), add the service account email under Settings, Users and permissions |
| `siteUnverifiedUser` in the site list | The account is listed but has no data rights | Ask an owner to change it to Restricted or Full in [Search Console](https://search.google.com/search-console) users |
| Permission denied on a site | Wrong property string or no user role | Run `test_access.py` and copy the exact string |
| Permission denied on GA4 | The service account is not on the property | In [Google Analytics](https://analytics.google.com/analytics/web/), add it as Viewer under Admin, Property access management |
| Not a GA4 property ID | A G- measurement ID was used | Use the numeric property ID from Admin, Property details in [Google Analytics](https://analytics.google.com/analytics/web/) |
| Could not get an access token | Key deleted, service account removed, or OAuth token expired | Create a new key in [Service accounts](https://console.cloud.google.com/iam-admin/serviceaccounts), or sign in again. To stop 7-day expiry, set [OAuth audience](https://console.cloud.google.com/auth/audience) to Internal or publish the app |
| Create new key is greyed out | An organization policy blocks service account keys | Ask your admin for an exception on this project, or use OAuth instead |
| Lost the OAuth client file | Newer client secrets can only be downloaded once | In [OAuth clients](https://console.cloud.google.com/auth/clients), open the client, click Add secret and download the new JSON |
| Insufficient scope | The OAuth consent did not include both scopes | Run `oauth_login.py` again |
| Quota exhausted | Too many requests in the hour or day | Wait, cache results and request fewer rows. Limits are on the [Search Console](https://console.cloud.google.com/apis/api/searchconsole.googleapis.com/quotas) and [GA4](https://console.cloud.google.com/apis/api/analyticsdata.googleapis.com/quotas) quota pages |
| Network error | A proxy or sandbox blocks Google | Allowlist `googleapis.com` and `oauth2.googleapis.com` |
| Rows look low | Anonymized queries are excluded from query-level rows | Report from page or property totals |
| GA4 warns about thresholding | Small segments are hidden to protect privacy | Widen the date range or remove a dimension |

A permission change can take a few minutes to apply. Rerun `test_access.py` before changing anything else.
