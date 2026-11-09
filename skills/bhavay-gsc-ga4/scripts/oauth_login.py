#!/usr/bin/env python3
"""One-time OAuth sign-in for people who use OAuth instead of a service account.

Opens a browser, asks for read-only Search Console and Analytics access, and
writes an authorized_user token file. Point GOOGLE_APPLICATION_CREDENTIALS at
that file and every other script in this folder uses it.

Needs:  pip install google-auth-oauthlib

Example:
  python3 oauth_login.py --client-secret ~/.config/gsc-ga4/client_secret.json \
      --token ~/.config/gsc-ga4/token.json
  export GOOGLE_APPLICATION_CREDENTIALS=$HOME/.config/gsc-ga4/token.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gauth import GA4_SCOPE, GSC_SCOPE, die  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Sign in once with OAuth and save a reusable token file.")
    ap.add_argument("--client-secret", required=True, help="OAuth client JSON of type Desktop app")
    ap.add_argument("--token", default=os.path.expanduser("~/.config/gsc-ga4/token.json"),
                    help="Where to write the token (default ~/.config/gsc-ga4/token.json)")
    args = ap.parse_args(argv)

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        die("Missing package. Install it with:\n  pip install google-auth-oauthlib")
    if not os.path.isfile(os.path.expanduser(args.client_secret)):
        die(f"Client secret file not found: {args.client_secret}")

    flow = InstalledAppFlow.from_client_secrets_file(os.path.expanduser(args.client_secret), [GSC_SCOPE, GA4_SCOPE])
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    if not creds.refresh_token:
        die("Google returned no refresh token. Remove the app's access at myaccount.google.com, then run again.")
    info = json.loads(creds.to_json())
    info["type"] = "authorized_user"
    path = os.path.expanduser(args.token)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(info, fh, indent=2)
    os.chmod(path, 0o600)
    print(f"Saved {path}\nNext:\n  export GOOGLE_APPLICATION_CREDENTIALS=\"{path}\"\n  python3 test_access.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
