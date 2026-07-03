[CmdletBinding()]
param(
    [switch]$Fix
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [string]$Exe,

        [Parameter(Mandatory = $true)]
        [string[]]$Args
    )

    Write-Host ""
    Write-Host "==> $Name"
    & $Exe @Args
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
Push-Location $repoRoot
try {
    Invoke-Step -Name "Ruff lint" -Exe "python" -Args @("-m", "ruff", "check", ".")
    if ($Fix) {
        Invoke-Step -Name "Ruff format" -Exe "python" -Args @("-m", "ruff", "format", ".")
    } else {
        Invoke-Step -Name "Ruff format check" -Exe "python" -Args @("-m", "ruff", "format", "--check", ".")
    }
} finally {
    Pop-Location
}
