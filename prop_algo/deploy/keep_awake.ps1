# Keep the Windows host awake while a long demo run is active.
# Uses SetThreadExecutionState (no permanent power-plan change by default).
#
# Usage (from repo root or prop_algo/deploy):
#   powershell -NoProfile -ExecutionPolicy Bypass -File prop_algo\deploy\keep_awake.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File prop_algo\deploy\keep_awake.ps1 -AwayMode
#   powershell -NoProfile -ExecutionPolicy Bypass -File prop_algo\deploy\keep_awake.ps1 -UsePowerCfg   # optional, temporary
#
# Stop:
#   $pid = Get-Content prop_algo\deploy\logs\keep_awake.pid
#   Stop-Process -Id $pid -Force
#
# Log: prop_algo/deploy/logs/keep_awake.log
# PID: prop_algo/deploy/logs/keep_awake.pid

[CmdletBinding()]
param(
    # Also set ES_AWAYMODE_REQUIRED (useful on some media/PC configs).
    [switch]$AwayMode,

    # Optional: temporarily override AC sleep via powercfg /change. Restored on exit.
    # Prefer the default SetThreadExecutionState path so sleep returns when this script stops.
    [switch]$UsePowerCfg,

    [int]$RefreshSeconds = 60
)

$ErrorActionPreference = "Stop"

$DeployDir = $PSScriptRoot
$LogDir = Join-Path $DeployDir "logs"
$LogFile = Join-Path $LogDir "keep_awake.log"
$PidFile = Join-Path $LogDir "keep_awake.pid"

if (-not (Test-Path -LiteralPath $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

function Write-KeepAwakeLog {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
    Write-Host $line
}

# Win32 SetThreadExecutionState (use Convert — PS parses 0x80000000 as Int32)
$ES_CONTINUOUS = [Convert]::ToUInt32("80000000", 16)
$ES_SYSTEM_REQUIRED = [Convert]::ToUInt32("00000001", 16)
$ES_AWAYMODE_REQUIRED = [Convert]::ToUInt32("00000040", 16)

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class KeepAwakeNative {
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern uint SetThreadExecutionState(uint esFlags);
}
"@

$flags = $ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED
if ($AwayMode) {
    $flags = $flags -bor $ES_AWAYMODE_REQUIRED
}
$flags = [uint32]$flags

$script:PowerCfgChanged = $false
$script:PrevMonitorTimeout = $null
$script:PrevStandbyTimeout = $null
$script:Stopping = $false

function Restore-ExecutionState {
    [void][KeepAwakeNative]::SetThreadExecutionState($ES_CONTINUOUS)
}

function Restore-PowerCfgIfNeeded {
    if (-not $script:PowerCfgChanged) { return }
    try {
        if ($null -ne $script:PrevMonitorTimeout) {
            powercfg /change monitor-timeout-ac $script:PrevMonitorTimeout | Out-Null
        }
        if ($null -ne $script:PrevStandbyTimeout) {
            powercfg /change standby-timeout-ac $script:PrevStandbyTimeout | Out-Null
        }
        Write-KeepAwakeLog "Restored powercfg AC timeouts (monitor=$($script:PrevMonitorTimeout) standby=$($script:PrevStandbyTimeout))"
    }
    catch {
        Write-KeepAwakeLog "WARN: failed to restore powercfg: $_"
    }
    finally {
        $script:PowerCfgChanged = $false
    }
}

function Apply-PowerCfgTemporary {
    # Documented optional path: disable AC sleep/monitor while this process runs.
    # Restore targets are conventional defaults if the prior scheme was not queried.
    $script:PrevMonitorTimeout = 10
    $script:PrevStandbyTimeout = 20
    powercfg /change monitor-timeout-ac 0 | Out-Null
    powercfg /change standby-timeout-ac 0 | Out-Null
    $script:PowerCfgChanged = $true
    Write-KeepAwakeLog "Optional -UsePowerCfg: set monitor-timeout-ac=0 standby-timeout-ac=0 (will restore on exit)"
}

function Invoke-Cleanup {
    if ($script:Stopping) { return }
    $script:Stopping = $true
    Write-KeepAwakeLog "Stopping keep_awake; restoring ES_CONTINUOUS only"
    Restore-ExecutionState
    Restore-PowerCfgIfNeeded
    if (Test-Path -LiteralPath $PidFile) {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    }
    Write-KeepAwakeLog "Exited cleanly (pid was $PID)"
}

# Single-instance guard
if (Test-Path -LiteralPath $PidFile) {
    $existing = (Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
    if ($existing -match '^\d+$') {
        $existingPid = [int]$existing
        $proc = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        if ($null -ne $proc) {
            Write-KeepAwakeLog "Already running as PID $existingPid; exiting"
            exit 0
        }
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

$PID | Set-Content -LiteralPath $PidFile -Encoding ASCII
Write-KeepAwakeLog "Started keep_awake pid=$PID refresh=${RefreshSeconds}s AwayMode=$AwayMode UsePowerCfg=$UsePowerCfg flags=0x$($flags.ToString('X8'))"

try {
    if ($UsePowerCfg) {
        Apply-PowerCfgTemporary
    }

    while ($true) {
        $prev = [KeepAwakeNative]::SetThreadExecutionState($flags)
        if ($prev -eq 0) {
            Write-KeepAwakeLog "WARN: SetThreadExecutionState returned 0 (GetLastError=$([Runtime.InteropServices.Marshal]::GetLastWin32Error()))"
        }
        else {
            Write-KeepAwakeLog "Refreshed execution state (prev=0x$($prev.ToString('X8')))"
        }
        Start-Sleep -Seconds $RefreshSeconds
    }
}
finally {
    Invoke-Cleanup
}
