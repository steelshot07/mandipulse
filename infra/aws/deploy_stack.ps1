# Create or update the MandiPulse ingestion stack in ap-south-1 (Mumbai).
# Usage (from repo root):  .\infra\aws\deploy_stack.ps1 [-AlertEmail you@example.com] [-Profile name]
# Reads DATABASE_URL and DATAGOV_API_KEY from backend\.env and never prints them.
param(
    [string]$AlertEmail = "",
    [string]$Profile = "",
    [string]$CreateGitHubOidcProvider = "true"
)
$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$envFile = Join-Path $root "backend\.env"
if (-not (Test-Path $envFile)) { throw "backend\.env not found" }

$values = @{}
foreach ($line in Get-Content $envFile) {
    if ($line -match '^\s*(DATABASE_URL|DATAGOV_API_KEY)\s*=\s*(.*?)\s*$') {
        $values[$Matches[1]] = $Matches[2].Trim('"').Trim("'")
    }
}
foreach ($key in "DATABASE_URL", "DATAGOV_API_KEY") {
    if (-not $values[$key]) { throw "$key is missing or empty in backend\.env" }
}

$profileArgs = @()
if ($Profile) { $profileArgs = @("--profile", $Profile) }

Write-Host "Deploying stack 'mandipulse-ingest' to ap-south-1 (secrets read from backend\.env, not shown)..."
aws cloudformation deploy @profileArgs `
    --region ap-south-1 `
    --stack-name mandipulse-ingest `
    --template-file (Join-Path $PSScriptRoot "ingest-stack.yaml") `
    --capabilities CAPABILITY_IAM `
    --no-fail-on-empty-changeset `
    --parameter-overrides `
        "DatabaseUrl=$($values['DATABASE_URL'])" `
        "DatagovApiKey=$($values['DATAGOV_API_KEY'])" `
        "AlertEmail=$AlertEmail" `
        "CreateGitHubOidcProvider=$CreateGitHubOidcProvider"
if ($LASTEXITCODE -ne 0) { throw "Stack deploy failed (see the CloudFormation console > Events)" }

Write-Host "`nOutputs (none of these are secret):"
aws cloudformation describe-stacks @profileArgs --region ap-south-1 --stack-name mandipulse-ingest `
    --query "Stacks[0].Outputs[].[OutputKey,OutputValue]" --output table
if ($AlertEmail) { Write-Host "Check $AlertEmail and confirm the AWS SNS subscription to get failure alerts." }
