#!/usr/bin/env python3
"""Open the AWS console in a browser using the current SSO session.

No password, no MFA prompt: it exchanges the temporary credentials the CLI
already holds for a console sign-in token via AWS's federation endpoint, then
opens the resulting URL. The MFA you did at `aws sso login` is the only one --
and if the portal session duration is set long (Identity Center -> Settings ->
Authentication), that login itself is rare.

    python scripts/aws-console.py                     # default profile edgar-sso
    python scripts/aws-console.py --profile other
    python scripts/aws-console.py --service s3        # land on a service page
    python scripts/aws-console.py --print             # print the URL, do not open

Credentials never touch disk and the console session lasts 12 hours, matching
the permission set. The URL embeds a one-time sign-in token: treat it like a
password and do not paste it anywhere.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.parse
import urllib.request
import webbrowser

FEDERATION = "https://signin.aws.amazon.com/federation"
CONSOLE = "https://console.aws.amazon.com/"


def credentials(profile: str) -> dict[str, str]:
    """Temporary credentials for a profile, refreshing the SSO login if needed."""
    cmd = ["aws", "configure", "export-credentials", "--profile", profile, "--format", "process"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # Almost always an expired SSO session; re-login and try once more.
        print(f"credentials unavailable, running: aws sso login --profile {profile}", file=sys.stderr)
        if subprocess.run(["aws", "sso", "login", "--profile", profile]).returncode != 0:
            sys.exit("aws sso login failed")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            sys.exit(proc.stderr.strip() or "could not export credentials")

    c = json.loads(proc.stdout)
    if not c.get("SessionToken"):
        sys.exit(
            "this profile has long-lived credentials, not temporary ones.\n"
            "The federation endpoint only accepts temporary credentials, which is\n"
            "the point: use an SSO profile."
        )
    return c


def signin_token(c: dict[str, str]) -> str:
    session = json.dumps(
        {
            "sessionId": c["AccessKeyId"],
            "sessionKey": c["SecretAccessKey"],
            "sessionToken": c["SessionToken"],
        }
    )
    # 43200s = 12h, matching the EdgarAdmin permission set. The endpoint caps at
    # the life of the underlying credentials, so asking for more is harmless.
    url = f"{FEDERATION}?{urllib.parse.urlencode({'Action': 'getSigninToken', 'SessionDuration': 43200, 'Session': session})}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return str(json.loads(r.read())["SigninToken"])
    except urllib.error.HTTPError as e:  # noqa: PERF203 - the message matters here
        sys.exit(f"federation endpoint rejected the credentials: {e.code} {e.read().decode()[:200]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", default="edgar-sso")
    ap.add_argument("--service", default=None, help="console service to land on, e.g. s3, ecs")
    ap.add_argument("--region", default=None, help="console region (defaults to the profile's)")
    ap.add_argument("--print", dest="print_only", action="store_true")
    args = ap.parse_args()

    c = credentials(args.profile)
    region = args.region or c.get("Region") or "us-east-2"

    destination = CONSOLE
    if args.service:
        destination = f"https://{region}.console.aws.amazon.com/{args.service}/home?region={region}"

    login = f"{FEDERATION}?" + urllib.parse.urlencode(
        {
            "Action": "login",
            "Issuer": "edgar-lakehouse-local",
            "Destination": destination,
            "SigninToken": signin_token(c),
        }
    )

    if args.print_only:
        print(login)
        return
    print(f"opening the console as {args.profile} ({region})")
    webbrowser.open(login)


if __name__ == "__main__":
    main()
