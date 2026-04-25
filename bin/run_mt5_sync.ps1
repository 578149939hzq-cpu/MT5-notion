[CmdletBinding()]
param(
    [ValidateSet("run", "health-check")]
    [string]$Command = "run",

    [ValidateSet("incremental", "reconcile")]
    [string]$Profile = "incremental",

    [string]$PythonExecutable = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-PythonInvocation {
    param(
        [string]$ConfiguredExecutable
    )

    if ($ConfiguredExecutable) {
        return @{
            Command = $ConfiguredExecutable
            PrefixArgs = @()
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{
            Command = $python.Source
            PrefixArgs = @()
        }
    }

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        return @{
            Command = $pyLauncher.Source
            PrefixArgs = @("-3")
        }
    }

    throw "Python executable not found. Install Python, add it to PATH, or pass -PythonExecutable."
}

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$runnerScript = Join-Path $repoRoot "tools\sync_job_runner.py"

if (-not (Test-Path -LiteralPath $runnerScript)) {
    throw "Runner script not found: $runnerScript"
}

$pythonInvocation = Resolve-PythonInvocation -ConfiguredExecutable $PythonExecutable
$arguments = @()
$arguments += $pythonInvocation.PrefixArgs
$arguments += $runnerScript
$arguments += $Command
$arguments += "--profile"
$arguments += $Profile

Push-Location $repoRoot
try {
    & $pythonInvocation.Command @arguments
    if ($LASTEXITCODE -is [int]) {
        exit $LASTEXITCODE
    }
    exit 0
}
finally {
    Pop-Location
}
