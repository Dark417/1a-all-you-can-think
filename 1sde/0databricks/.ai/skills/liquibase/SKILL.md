---
name: liquibase
description: Run Liquibase for the edgar-lakehouse changelogs (validate, plan, update, status, history) via the portable toolchain in 1sde-edgar-01-contracts/tools. Use when the user types /liquibase, or asks to validate changelogs, generate the DDL plan, apply/migrate tables to Databricks, or check migration status.
---

# Liquibase runner for edgar-lakehouse

All actions run through the attached script (PowerShell tool, from any cwd):

```powershell
powershell -NoProfile -File "D:\1sde\0databricks\.ai\skills\liquibase\run.ps1" <action>
```

Actions:

| action | connects to workspace? | what it does |
|---|---|---|
| `validate` | no (offline) | changelog syntax/reference check |
| `plan` | yes | `update-sql` → writes `tools\workspace-plan.sql`, prints CREATE TABLE count |
| `update` | yes | applies pending changesets (creates the tables) |
| `status` | yes | lists pending changesets |
| `history` | yes | lists applied changesets from DATABASECHANGELOG |

## Rules

1. Default action is `validate`. If the user just says `/liquibase`, run `validate`.
2. **Never run `update` without having shown the user a fresh `plan` output in
   this conversation first**, unless the user explicitly says to apply/update
   directly.
3. If the script reports the PAT placeholder is still in
   `changelog/liquibase.properties`, tell the user to paste their `dapi…` token
   into that file (it is gitignored) — do not put the token anywhere else.
4. `update` fails with `Catalog 'edgar' does not exist` if the catalog/schemas
   have not been created yet — that is expected order-of-operations, not a bug.
   Point the user to RUNBOOK §C.4 (create catalog+schemas, or repo 2 Terraform).
5. On any Java/driver error, check `tools/jre` and both jars in
   `tools/liquibase/lib/` exist before diagnosing further (RUNBOOK §B rebuilds
   them).
