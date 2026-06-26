<#
.SYNOPSIS
    OpenSolar Windows bootstrapper - provisions WSL2 and runs the Linux
    installer inside it with full flag passthrough.

.DESCRIPTION
    Native (non-WSL) Windows is out of scope; WSL2 is the Windows runtime path.
    If WSL2 is absent this self-elevates, installs Ubuntu-24.04, and registers a
    RunOnce continuation - the one documented manual step is the admin approval
    plus the single reboot WSL2 install requires. If WSL2 is present it ensures
    the distro + systemd are ready, then runs the Linux installer inside with
    every forwarded flag, so `--yes` CI/unattended installs behave identically
    to macOS/Linux.

    Phase 0: get-solar.sh ships from the public stable branch and
    -BootstrapUrl defaults to that raw stable URL, so this uses curl|bash by
    default without requiring a GitHub Release asset. Pass -BootstrapUrl '' to
    use the clone-and-exec fallback (RepoUrl), or set -BootstrapUrl to any
    reachable get-solar.sh URL.

.PARAMETER Distro
    WSL distro name. Default Ubuntu-24.04.

.PARAMETER BootstrapUrl
    get-solar.sh URL. Defaults to the public raw stable bootstrap; runs
    `curl -fsSL <url> | bash -s -- <forwarded>`. Pass '' to fall back to the
    clone-and-exec path (RepoUrl).

.PARAMETER RepoUrl
    Git URL cloned inside WSL when -BootstrapUrl is not set.

.PARAMETER ForwardArgs
    Flags passed through verbatim to the Linux install.sh (e.g. --yes
    --components kernel,harness).
#>
[CmdletBinding()]
param(
    [string]$Distro = 'Ubuntu-24.04',
    [string]$BootstrapUrl = 'https://raw.githubusercontent.com/suraj-subrahmanyan/OpenSolar/stable/get-solar.sh',
    [string]$RepoUrl = 'https://github.com/suraj-subrahmanyan/OpenSolar.git',
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ForwardArgs = @()
)

$ErrorActionPreference = 'Stop'

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-WslReady {
    try {
        $null = & wsl.exe --status 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Get-ForwardString {
    $list = @($ForwardArgs)
    $joined = ($list -join ' ')
    # The Windows desktop shell reaches a runtime running in WSL, so the install MUST set up the
    # persistent status-daemon login service (otherwise a backgrounded runtime dies when wsl.exe
    # returns). If the caller didn't pick their own components, install the desktop set.
    if ($joined -notmatch '--components') {
        $list += @('--components', 'kernel,harness,status-daemon')
    }
    if ($joined -notmatch '(^|\s)--yes(\s|$)') {
        $list += '--yes'
    }
    return ($list -join ' ')
}

function Invoke-LinuxInstaller {
    $forwarded = Get-ForwardString
    if ($BootstrapUrl -ne '') {
        $cmd = "curl -fsSL '$BootstrapUrl' | bash -s -- $forwarded"
    } else {
        $cmd = "set -e; tmp=`$(mktemp -d); git clone --depth 1 '$RepoUrl' `"`$tmp/OpenSolar`"; bash `"`$tmp/OpenSolar/install.sh`" $forwarded"
    }
    Write-Host "[solar] running Linux installer inside WSL ($Distro)..."
    & wsl.exe -d $Distro -- bash -lc $cmd
    if ($LASTEXITCODE -ne 0) {
        throw "Linux installer failed inside WSL (exit $LASTEXITCODE)"
    }
}

function Enable-WslSystemd {
    # systemd is required for the daemons component; enable it idempotently.
    $check = & wsl.exe -d $Distro -- bash -lc "grep -q 'systemd=true' /etc/wsl.conf 2>/dev/null && echo ok || echo no"
    if ($check -notmatch 'ok') {
        Write-Host '[solar] enabling systemd in WSL...'
        & wsl.exe -d $Distro -- bash -lc "printf '[boot]\nsystemd=true\n' | sudo tee -a /etc/wsl.conf >/dev/null"
        & wsl.exe --shutdown
    }
}

function Set-WslMirroredNetworking {
    # Mirrored networking (Win11 22H2+) makes host<->WSL localhost bidirectional, so the runtime
    # binds 127.0.0.1 (secure, no LAN exposure) instead of the 0.0.0.0 NAT fallback. Global setting
    # in %UserProfile%\.wslconfig [wsl2]. Conservative + idempotent: never overrides an existing
    # explicit networkingMode (e.g. a Docker Desktop user on 'nat') - the runtime's NAT fallback
    # still works there. Harmlessly ignored on Windows older than 22H2.
    $cfg = Join-Path $env:USERPROFILE '.wslconfig'
    if (-not (Test-Path $cfg)) {
        Set-Content -Path $cfg -Value "[wsl2]`r`nnetworkingMode=mirrored" -Encoding ASCII
        Write-Host '[solar] wrote .wslconfig with mirrored networking (secure localhost path).'
        & wsl.exe --shutdown
        return
    }
    $lines = Get-Content $cfg
    if ($lines -match '^\s*networkingMode\s*=\s*mirrored\s*$') {
        Write-Host '[solar] WSL mirrored networking already set.'
        return
    }
    if ($lines -match '^\s*networkingMode\s*=') {
        Write-Host '[solar] .wslconfig pins a networkingMode already; leaving it (runtime uses the 0.0.0.0 fallback). For the secure loopback path, set networkingMode=mirrored (Win11 22H2+).'
        return
    }
    if ($lines -match '^\s*\[wsl2\]\s*$') {
        $out = foreach ($l in $lines) { $l; if ($l -match '^\s*\[wsl2\]\s*$') { 'networkingMode=mirrored' } }
        Set-Content -Path $cfg -Value $out
    } else {
        Add-Content -Path $cfg -Value "`r`n[wsl2]`r`nnetworkingMode=mirrored"
    }
    Write-Host '[solar] set WSL mirrored networking (.wslconfig); applies after the next wsl --shutdown.'
    & wsl.exe --shutdown
}

function Install-Wsl {
    if (-not (Test-Admin)) {
        Write-Host '[solar] WSL2 install needs administrator rights; re-launching elevated...'
        $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"") + $ForwardArgs
        Start-Process -FilePath 'powershell.exe' -ArgumentList $argList -Verb RunAs
        exit 0
    }
    Write-Host "[solar] installing WSL2 distro $Distro (no launch)..."
    & wsl.exe --install -d $Distro --no-launch
    # Register a RunOnce continuation so this script resumes after the reboot.
    $runOnce = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\RunOnce'
    $resume = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" $(Get-ForwardString)"
    Set-ItemProperty -Path $runOnce -Name 'OpenSolarResume' -Value $resume
    Write-Warning 'WSL2 was installed. A REBOOT is required (the one manual step).'
    Write-Warning 'After reboot, this installer resumes automatically via RunOnce.'
    exit 0
}

# ---- main ----
if (-not (Test-WslReady)) {
    Install-Wsl
} else {
    Enable-WslSystemd
    Set-WslMirroredNetworking
    Invoke-LinuxInstaller
    Write-Host '[solar] Windows (WSL2) install complete.'
}
