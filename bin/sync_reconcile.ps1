[CmdletBinding()]
param(
    [string]$PythonExecutable = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$entryScript = Join-Path $PSScriptRoot "run_mt5_sync.ps1"
if (-not (Test-Path -LiteralPath $entryScript)) {
    throw "Sync entry script not found: $entryScript"
}

& $entryScript -Command run -Profile reconcile -PythonExecutable $PythonExecutable
if ($LASTEXITCODE -is [int]) {
    exit $LASTEXITCODE
}
exit 0
