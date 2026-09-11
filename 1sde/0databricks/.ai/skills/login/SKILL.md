---
name: login
description: Sign in to AWS for this project and open the console in a browser, already authenticated. Use when the user says "login", "log in", "sign in", "login demo", "open the console", or "open AWS" — anything asking to get into the AWS account. Not for creating demo material; that is the create-demo skill.
---

# login — get into the AWS demo account

One command: refresh the SSO session if needed, then open the AWS console in a
browser already signed in. No password page, no MFA prompt.

```bash
python D:/1sde/0databricks/scripts/aws-console.py
```

That is the whole thing. It exchanges the temporary credentials the CLI holds
for a console sign-in token via AWS's federation endpoint, and runs
`aws sso login --profile edgar-sso` first if the session has expired.

## Variants

| Ask | Command |
|---|---|
| open the console | `python scripts/aws-console.py` |
| land on a service | `python scripts/aws-console.py --service s3` (or `ecs`, `ecr`, `secretsmanager`, `ssm`, `cloudwatch`) |
| CLI only, no browser | `aws sso login --profile edgar-sso` |
| just print the URL | `python scripts/aws-console.py --print` |
| which identity am I? | `aws sts get-caller-identity --profile edgar-sso` |

## What it signs in as

Account **806168459926** (the project account, named "demo"), role
`EdgarAdmin`, via the SSO user in the management account's IAM Identity Center.
The session lasts 12 hours. There is no assignment on the management account,
so this grants nothing outside the project account — that is deliberate.

## Rules

1. **Report the identity after signing in.** Run
   `aws sts get-caller-identity --profile edgar-sso` and state the account and
   role. "Signed in" without saying *as what* is how work lands in the wrong
   account.
2. **Never print the generated URL into chat.** It embeds a live sign-in token
   and is equivalent to a password. `--print` exists for debugging; use it only
   when the user asks, and say what it is.
3. **Do not fall back to the old `edgar` profile** (long-lived key, no MFA) when
   SSO fails. Fix the SSO path or report the failure — silently reverting to the
   credential this setup exists to retire defeats the point.
4. If `aws sso login` opens a device-authorisation page and the user must
   approve it, say so rather than appearing to hang.
5. Prefix any AWS work in the same turn with `--profile edgar-sso`, or export
   `AWS_PROFILE=edgar-sso`, so it does not silently run as the default profile
   (which is the management account).

## When it fails

| Symptom | Cause | Fix |
|---|---|---|
| `credentials unavailable` then a login prompt | SSO session expired | expected — let it re-login |
| federation endpoint rejects the credentials | profile has long-lived keys, not temporary ones | use `edgar-sso`, not `edgar` or `default` |
| browser opens to a sign-in page instead of the console | the sign-in token expired before it was used | re-run; the token is one-shot and short-lived |
| MFA prompted every time | portal session duration is short | Identity Center → Settings → Authentication → raise session duration, and set MFA to "only when sign-in context changes" |
