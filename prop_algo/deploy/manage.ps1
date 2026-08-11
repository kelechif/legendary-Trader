# One-shot DX helpers for prop_algo local compose (Windows PowerShell).
# Usage (from anywhere):
#   .\prop_algo\deploy\manage.ps1 up
#   .\prop_algo\deploy\manage.ps1 status
#   .\prop_algo\deploy\manage.ps1 smoke
#   .\prop_algo\deploy\manage.ps1 logs [-Tail 200] [service...]
#
# Does not invent product features — wraps existing compose / smoke_test.py only.

[CmdletBinding()]
param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet(
        "up", "up-torch", "up-metrics", "up-all",
        "down", "ps", "status", "smoke", "logs"
    )]
    [string]$Command,

    [Parameter()]
    [int]$Tail = 100,

    # Forwarded to smoke_test.py (avoids PowerShell eating --check-streams).
    [Parameter()]
    [switch]$CheckStreams,

    [Parameter()]
    [switch]$TorchStreams,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ArgsRest
)

$ErrorActionPreference = "Stop"

$DeployDir = $PSScriptRoot
$RepoRoot = (Resolve-Path (Join-Path $DeployDir "..\..")).Path

$Light = @("-f", "docker-compose.yml")
$Torch = @("-f", "docker-compose.yml", "-f", "docker-compose.torch.yml", "--profile", "torch")
$Metrics = @("-f", "docker-compose.yml", "-f", "docker-compose.metrics.yml", "--profile", "metrics")
$All = @(
    "-f", "docker-compose.yml",
    "-f", "docker-compose.torch.yml",
    "-f", "docker-compose.metrics.yml",
    "--profile", "torch",
    "--profile", "metrics"
)

function Invoke-Compose {
    param([string[]]$ComposeArgs)
    Push-Location $DeployDir
    try {
        & docker compose @ComposeArgs
        if ($LASTEXITCODE -ne 0) {
            throw "docker compose failed (exit $LASTEXITCODE)"
        }
    }
    finally {
        Pop-Location
    }
}

switch ($Command) {
    "up" {
        Invoke-Compose (@($Light) + @("up", "-d", "--build"))
    }
    "up-torch" {
        Invoke-Compose (@($Torch) + @("up", "-d", "--build"))
    }
    "up-metrics" {
        Invoke-Compose (@($Metrics) + @("up", "-d", "--build"))
    }
    "up-all" {
        Invoke-Compose (@($All) + @("up", "-d", "--build"))
    }
    "down" {
        # Include overlays so profiled services leave the project cleanly.
        Invoke-Compose (@($All) + @("down"))
    }
    { $_ -in @("ps", "status") } {
        Invoke-Compose (@($All) + @("ps"))
    }
    "smoke" {
        Push-Location $RepoRoot
        try {
            $smoke = Join-Path $RepoRoot "prop_algo\deploy\smoke_test.py"
            $smokeArgs = @()
            if ($CheckStreams) { $smokeArgs += "--check-streams" }
            if ($TorchStreams) { $smokeArgs += "--torch-streams" }
            if ($ArgsRest) { $smokeArgs += $ArgsRest }
            & python $smoke @smokeArgs
            if ($LASTEXITCODE -ne 0) {
                throw "smoke_test.py failed (exit $LASTEXITCODE)"
            }
        }
        finally {
            Pop-Location
        }
    }
    "logs" {
        $logArgs = @("logs", "--tail", "$Tail", "-f") + @($ArgsRest)
        Invoke-Compose (@($All) + $logArgs)
    }
}
