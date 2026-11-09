"""Shared auth and HTTP helpers for the GSC and GA4 scripts.

Credentials are resolved by google-auth in this order:
  1. GOOGLE_APPLICATION_CREDENTIALS pointing to a service account key or an
     authorized_user token file (oauth_login.py writes one).
  2. Application Default Credentials from `gcloud auth application-default login`.

Only google-auth and requests are needed. The REST endpoints are called directly,
so the heavier Google client libraries are not required.
"""

from __future__ import annotations

import json
import os
import sys
import time

GSC_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
GA4_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
SETUP_URL = "https://bhavay.com/resources/skills/bhavay-gsc-ga4"
ENABLE_URLS = {
    "Search Console API": "https://console.cloud.google.com/apis/library/searchconsole.googleapis.com",
    "Google Analytics Data API": "https://console.cloud.google.com/apis/library/analyticsdata.googleapis.com",
    "Google Analytics Admin API": "https://console.cloud.google.com/apis/library/analyticsadmin.googleapis.com",
}


class ApiError(Exception):
    """Raised with a plain-language explanation of what went wrong."""


def die(msg: str, code: int = 1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def session(scopes: list[str]):
    """Return (AuthorizedSession, identity string). Exits with a clear message on failure."""
    try:
        import google.auth
        from google.auth.exceptions import DefaultCredentialsError, RefreshError
        from google.auth.transport.requests import AuthorizedSession
    except ImportError:
        die("Missing packages. Install them with:\n  pip install google-auth requests")

    key = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if key:
        path = os.path.expanduser(key)
        if not os.path.isfile(path):
            die(f"GOOGLE_APPLICATION_CREDENTIALS points to a file that does not exist.\n  {key}\n"
                "Fix the path or download the JSON key again.")
        try:
            with open(path, encoding="utf-8") as fh:
                info = json.load(fh)
            kind = info.get("type", "")
        except (OSError, ValueError, AttributeError):
            die(f"{key} is not a readable JSON key file.")
        if "installed" in info or "web" in info:
            die(f"{key} is an OAuth client secret, not a credential.\n"
                "Run oauth_login.py --client-secret with it once. It writes a token file.\n"
                "Then point GOOGLE_APPLICATION_CREDENTIALS at that token file.")
        if kind not in ("service_account", "authorized_user", "external_account", "impersonated_service_account"):
            die(f"{key} has type '{kind or 'unknown'}'.\n"
                "If this is an OAuth client secret (type 'installed'), run oauth_login.py with it first.\n"
                "It writes a token file that GOOGLE_APPLICATION_CREDENTIALS can point to.")
    try:
        creds, _ = google.auth.default(scopes=scopes)
    except DefaultCredentialsError:
        die("No Google credentials found.\n"
            "Set GOOGLE_APPLICATION_CREDENTIALS to a service account JSON key, for example\n"
            "  export GOOGLE_APPLICATION_CREDENTIALS=$HOME/.config/gsc-ga4/key.json\n"
            "or sign in with OAuth using scripts/oauth_login.py.\n"
            f"Setup guide: {SETUP_URL}")
    who = getattr(creds, "service_account_email", None)
    identity = who or "the Google account you signed in with"
    s = AuthorizedSession(creds)
    s._identity = identity  # used in error messages
    s._refresh_error = RefreshError
    return s, identity


def _explain(resp, api: str, identity: str, hint: str) -> str:
    try:
        err = resp.json().get("error", {})
    except ValueError:
        err = {}
    if isinstance(err, str):  # token endpoint style
        err = {"message": err}
    msg = err.get("message", resp.text[:300])
    details = json.dumps(err.get("details", [])) + json.dumps(err.get("errors", []))
    code = resp.status_code
    if code == 403 and ("SERVICE_DISABLED" in details or "accessNotConfigured" in details
                        or "has not been used in project" in msg or "is disabled" in msg):
        return (f"The {api} is not enabled in your Google Cloud project.\n"
                f"Enable it here, wait a minute, then retry.\n  {ENABLE_URLS.get(api, 'https://console.cloud.google.com/apis/library')}\n"
                f"API said: {msg}")
    if code == 403 and ("insufficient" in msg.lower() and "scope" in msg.lower()):
        return (f"The credentials do not carry the scope the {api} needs.\n"
                "For OAuth, run oauth_login.py again so the consent covers Search Console and Analytics.\n"
                f"API said: {msg}")
    if code == 403:
        return f"Permission denied by the {api}.\n{hint.format(who=identity)}\nAPI said: {msg}"
    if code == 401:
        return ("The credentials were rejected. The key may be deleted or the OAuth token expired.\n"
                "Create a new key, or run oauth_login.py again. OAuth tokens expire after 7 days while the "
                "consent screen is in Testing mode.\n"
                f"API said: {msg}")
    if code == 404:
        return f"Not found. {hint.format(who=identity)}\nAPI said: {msg}"
    if code == 400:
        return f"Bad request. Check the property, dates, dimensions, metrics and filters.\nAPI said: {msg}"
    if code == 429:
        return f"Quota exhausted for the {api}. Wait and retry, or request fewer rows.\nAPI said: {msg}"
    return f"HTTP {code} from the {api}.\nAPI said: {msg}"


def call(s, method: str, url: str, api: str, hint: str, body: dict | None = None, params: dict | None = None):
    """Make a request with retries on 429 and 5xx. Raises ApiError with an explanation."""
    last = None
    for attempt in range(5):
        try:
            resp = s.request(method, url, json=body, params=params, timeout=120)
        except s._refresh_error as e:
            raise ApiError("Could not get an access token. The key may be revoked or the OAuth token "
                           f"expired. Create a new key or run oauth_login.py again.\nDetail: {e}")
        except Exception as e:  # network
            last = e
            time.sleep(2 ** attempt)
            continue
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < 4:
            wait = 2 ** attempt * 5
            print(f"  HTTP {resp.status_code}, retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
            continue
        if resp.status_code >= 400:
            raise ApiError(_explain(resp, api, s._identity, hint))
        return resp.json() if resp.content else {}
    raise ApiError(f"Network error calling the {api}. Check the connection and any proxy or allowlist.\n"
                   f"Allow googleapis.com and oauth2.googleapis.com.\nDetail: {last}")
