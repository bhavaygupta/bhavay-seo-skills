# Troubleshooting

The scripts print a plain explanation for each of these. This page covers the cause and the fix.

| Message or symptom | Cause | Fix |
|---|---|---|
| No Google credentials found | `GOOGLE_APPLICATION_CREDENTIALS` is unset and there are no gcloud credentials | Export the variable with the key path, or run `oauth_login.py` |
| Points to a file that does not exist | Wrong path, or `~` inside quotes that was never expanded | Use `$HOME/...` in the export line |
| Is an OAuth client secret, not a credential | The client JSON was used as the credential | Run `oauth_login.py --client-secret` with it, then point the variable at the token file |
| API is not enabled in your Google Cloud project | The API is off in the project that owns the key | Enable it from the link in the message and wait a minute |
| Site list is empty | The credential works but has no Search Console access | Add the service account email as a user on each property |
| `siteUnverifiedUser` in the site list | The account is listed but has no data rights | Ask an owner to add it as Restricted or Full |
| Permission denied on a site | Wrong property string or no user role | Run `test_access.py` and copy the exact string |
| Permission denied on GA4 | The service account is not on the property | Add it as Viewer in Property access management |
| Not a GA4 property ID | A G- measurement ID was used | Use the numeric property ID from Property details |
| Could not get an access token | Key deleted, service account removed, or OAuth token expired | Create a new key, or sign in again. Set the OAuth audience to Internal or publish the app to stop 7-day expiry |
| Insufficient scope | The OAuth consent did not include both scopes | Run `oauth_login.py` again |
| Quota exhausted | Too many requests in the hour or day | Wait, cache results and request fewer rows |
| Network error | A proxy or sandbox blocks Google | Allowlist `googleapis.com` and `oauth2.googleapis.com` |
| Rows look low | Anonymized queries are excluded from query-level rows | Report from page or property totals |
| GA4 warns about thresholding | Small segments are hidden to protect privacy | Widen the date range or remove a dimension |

A permission change can take a few minutes to apply. Rerun `test_access.py` before changing anything else.
