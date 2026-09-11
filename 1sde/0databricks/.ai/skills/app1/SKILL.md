---
name: app1
description: "PR, merge, and apply repo 1 (1sde-edgar-01-contracts): put pending work on a branch, open a PR, merge when CI is green, then Liquibase-apply the changelogs to the Databricks workspace. Trigger when the user says app1 or /app1."
---

# app1 — PR + merge + apply for repo 1 (contracts)

`app1` means: take repo 1's pending work through **PR → merge → apply**, in that
order. "Apply" for repo 1 means **Liquibase `update`** against the workspace
(merging to main never applies DDL; only the release-on-tag pipeline and the
local Liquibase toolchain do).

Repo: `D:\1sde\0databricks\1sde-edgar-01-contracts`

## Steps

1. **Sync and assess.** `git fetch` + `git status` + `git log origin/main..HEAD`.
   Parallel sessions are known to work this project — trust the freshly fetched
   state, not memory. Identify pending work: uncommitted changes and/or local
   commits not on origin/main.
2. **PR.** If there is pending work: create a branch, commit it with a message
   explaining why (repo convention: conventional-commit style, body says the
   why), push, `gh pr create`. If the tree is clean and main is pushed, say so
   and go to step 4.
3. **Merge.** Watch CI (`gh pr checks <n> --watch`). Fix real failures on the
   branch (ruff format, etc.) rather than merging red. Then
   `gh pr merge <n> --merge --delete-branch`, and pull main.
4. **Apply.** Use the liquibase skill's script:
   `powershell -NoProfile -File "D:\1sde\0databricks\.ai\skills\liquibase\run.ps1" plan`
   then `... update`, then `... status` to confirm nothing pending. `app1` is
   explicit authorization to apply, but still run `plan` first and stop if the
   plan contains anything destructive or surprising — show it and ask.
5. **Report** what merged, what Liquibase applied (or that it was a no-op), and
   the CI state of main.

## Rules

- Do NOT tag or release (`v*` tags trigger the release pipeline, which also
  runs Liquibase from CI) — tagging is a separate, explicit ask.
- Do not sweep unrelated in-flight work from a parallel session into the PR;
  commit only coherent pending work, and name anything left behind.
- `note.md` is the user's scratch file: include it only if it is the pending
  work itself, otherwise leave it uncommitted.
