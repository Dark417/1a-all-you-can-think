# Liquibase wrapper for edgar-lakehouse (portable toolchain, no system installs).
# Usage: powershell -NoProfile -File run.ps1 [validate|plan|update|status|history]

param([string]$Action = "validate")

$ErrorActionPreference = "Stop"
$Repo = "D:\1sde\0databricks\1sde-edgar-01-contracts"
$Lb = Join-Path $Repo "tools\liquibase\liquibase.bat"
$Props = Join-Path $Repo "changelog\liquibase.properties"
$PlanOut = Join-Path $Repo "tools\workspace-plan.sql"

if (-not (Test-Path $Lb)) { Write-Error "Liquibase CLI missing at $Lb - see RUNBOOK section B to rebuild tools/"; exit 2 }
$env:JAVA_HOME = Join-Path $Repo "tools\jre"
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"
Set-Location $Repo

function Assert-Credentials {
    if (-not (Test-Path $Props)) { Write-Error "Missing $Props - copy changelog\liquibase.properties.example and fill it in"; exit 2 }
    $content = Get-Content $Props -Raw
    if ($content -match "<PASTE_YOUR_PAT_HERE>" -or $content -match "<PAT>") {
        Write-Error "PAT placeholder still in changelog\liquibase.properties - paste your dapi... token there (file is gitignored)"; exit 2
    }
}

switch ($Action) {
    "validate" {
        & $Lb --changelog-file=changelog/db.changelog-root.yaml --url=offline:databricks validate
        exit $LASTEXITCODE
    }
    "plan" {
        Assert-Credentials
        & $Lb --defaults-file=changelog\liquibase.properties update-sql > $PlanOut
        if ($LASTEXITCODE -ne 0) { Write-Error "update-sql failed"; exit $LASTEXITCODE }
        $creates = (Select-String -Path $PlanOut -Pattern "CREATE TABLE").Count
        Write-Output "Plan written to tools\workspace-plan.sql ($creates CREATE TABLE statements pending)"
        exit 0
    }
    "update" {
        Assert-Credentials
        & $Lb --defaults-file=changelog\liquibase.properties update
        exit $LASTEXITCODE
    }
    "status" {
        Assert-Credentials
        & $Lb --defaults-file=changelog\liquibase.properties status --verbose
        exit $LASTEXITCODE
    }
    "history" {
        Assert-Credentials
        & $Lb --defaults-file=changelog\liquibase.properties history
        exit $LASTEXITCODE
    }
    default {
        Write-Error "Unknown action '$Action'. Valid: validate | plan | update | status | history"; exit 2
    }
}
