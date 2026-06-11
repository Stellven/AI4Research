<#
.SYNOPSIS
    OpenSolar Windows bootstrapper — provisions WSL2 and runs the Linux
    installer inside it with full flag passthrough.

.DESCRIPTION
    Native (non-WSL) Windows is out of scope; WSL2 is the Windows runtime path.
    If WSL2 is absent this self-elevates, installs Ubuntu-24.04, and registers a
    RunOnce continuation — the one documented manual step is the admin approval
    plus the single reboot WSL2 install requires. If WSL2 is present it ensures
    the distro + systemd are ready, then runs the Linux installer inside with
    every forwarded flag, so `--yes` CI/unattended installs behave identically
    to macOS/Linux.

    NOTE (P4 swap): get-solar.sh does not exist until the P4 release cut. Until
    then this clones the repo inside WSL and execs install.sh. Set
    -BootstrapUrl to a get-solar.sh URL once published to switch to curl|bash.

.PARAMETER Distro
    WSL distro name. Default Ubuntu-24.04.

.PARAMETER BootstrapUrl
    Optional get-solar.sh URL (P4+). When set, runs `curl -fsSL <url> | bash -s
    -- <forwarded>` instead of the clone-and-exec path.

.PARAMETER RepoUrl
    Git URL cloned inside WSL when -BootstrapUrl is not set.

.PARAMETER ForwardArgs
    Flags passed through verbatim to the Linux install.sh (e.g. --yes
    --components kernel,harness).
#>
[CmdletBinding()]
param(
    [string]$Distro = 'Ubuntu-24.04',
    [string]$BootstrapUrl = '',
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
    if ($ForwardArgs.Count -eq 0) { return '' }
    return ($ForwardArgs -join ' ')
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
    Invoke-LinuxInstaller
    Write-Host '[solar] Windows (WSL2) install complete.'
}
