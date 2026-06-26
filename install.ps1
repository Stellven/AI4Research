<#
.SYNOPSIS
    OpenSolar Windows bootstrapper - provisions WSL2 and runs the Linux
    installer inside it with full flag passthrough.

.DESCRIPTION
    Native (non-WSL) Windows is out of scope; WSL2 is the Windows runtime path.
    If WSL2 is absent this self-elevates, installs Ubuntu-24.04, and registers a
    RunOnce continuation - the one documented manual step is the admin approval
    plus the single reboot WSL2 install requires. If WSL2 is present it ensures
    the distro + systemd are ready, installs the in-WSL prerequisites the Linux
    installer needs (git, python3-venv/pip, tmux, jq), then runs the Linux
    installer inside with every forwarded flag, so `--yes` CI/unattended installs
    behave identically to macOS/Linux.

    Runtime channel: the .exe bundles a version-matched get-solar.sh next to this
    script (electron-builder extraResources). This prefers that bundled script so
    the runtime installed inside WSL is the SAME release as the app. If the bundle
    is missing it falls back to -BootstrapUrl (defaults to the pinned release tag,
    NOT a moving branch), then to a clone-and-exec of -RepoUrl.

    Reliability: every wsl.exe call is exit-code-checked (PowerShell 5.1 does not
    make native-command failures throw even under -ErrorActionPreference Stop), the
    in-WSL pipeline uses `set -o pipefail` so a failed curl/git fails the install
    instead of reporting false success, and the whole run is transcripted to
    %LOCALAPPDATA%\Solar\setup.log so the desktop app can show real progress/errors.
    The RunOnce reboot-continuation runs from a stable %ProgramData%\OpenSolar copy
    (the portable .exe's own resources are an ephemeral temp dir that is gone after
    the reboot).

.PARAMETER Distro
    WSL distro name. Default Ubuntu-24.04. If a different distro is already
    registered, that one is used instead (kept consistent with the desktop app's
    distro detection), so existing WSL users are not forced onto a second distro.

.PARAMETER BootstrapUrl
    Fallback get-solar.sh URL used only when the bundled script is absent. Defaults
    to the pinned release tag. Pass '' to fall back to the clone-and-exec path (RepoUrl).

.PARAMETER RepoUrl
    Git URL cloned inside WSL when -BootstrapUrl is '' and no bundled script exists.

.PARAMETER ForwardArgs
    Flags passed through verbatim to the Linux install.sh (e.g. --yes
    --components kernel,harness).
#>
[CmdletBinding()]
param(
    [string]$Distro = 'Ubuntu-24.04',
    [string]$BootstrapUrl = 'https://raw.githubusercontent.com/suraj-subrahmanyan/OpenSolar/v1.0.0-rc.6/get-solar.sh',
    [string]$RepoUrl = 'https://github.com/suraj-subrahmanyan/OpenSolar.git',
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ForwardArgs = @()
)

$ErrorActionPreference = 'Stop'

$SetupLog = Join-Path $env:LOCALAPPDATA 'Solar\setup.log'

function Start-SetupLog {
    # Best-effort transcript so the desktop app can tail real setup progress/errors.
    try {
        $dir = Split-Path -Parent $SetupLog
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
        Start-Transcript -Path $SetupLog -Append | Out-Null
    } catch {
        Write-Verbose "setup-log transcript unavailable: $($_.Exception.Message)"
    }
}

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# Registered WSL distros (parallel to the desktop app's runtime-detect.js: `wsl -l -q`).
function Get-RegisteredDistro {
    try { $out = & wsl.exe -l -q 2>$null } catch { return @() }
    if ($LASTEXITCODE -ne 0) { return @() }
    return @($out -split "`r?`n" |
        ForEach-Object { ($_ -replace "`0", '').Trim() } |
        Where-Object { $_ })
}

# Use the requested distro if present; else the first registered one (matches the app's
# first-distro pick so detect/install/start/diagnostics all target the SAME distro); else
# the default (nothing registered yet -> we will install it).
function Resolve-Distro {
    $distros = Get-RegisteredDistro
    if ($distros -contains $Distro) { return $Distro }
    if ($distros.Count -gt 0) { return $distros[0] }
    return $Distro
}

# WSL is usable only if `wsl --status` succeeds AND at least one distro is registered.
# (`wsl --status` alone can exit 0 on a box where the stub exists but no distro is installed.)
function Test-WslReady {
    try { $null = & wsl.exe --status 2>$null } catch { return $false }
    if ($LASTEXITCODE -ne 0) { return $false }
    return ((Get-RegisteredDistro).Count -gt 0)
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
    # Fresh WSL Ubuntu lacks tmux/jq/bash>=4; let the installer apt-install them.
    if ($joined -notmatch '--bootstrap-system-deps') {
        $list += '--bootstrap-system-deps'
    }
    return ($list -join ' ')
}

# Fresh Ubuntu-24.04 ships python3.12 but NOT git / python3-pip / python3-venv / tmux / jq.
# get-solar.sh needs git and install.sh needs pip+venv, so install them before the installer runs.
function Install-WslPrerequisite {
    Write-Host '[solar] ensuring WSL prerequisites (git, python3-venv/pip, tmux, jq)...'
    $sh = 'if command -v apt-get >/dev/null 2>&1; then ' +
          'sudo apt-get update && ' +
          'sudo DEBIAN_FRONTEND=noninteractive apt-get install -y ' +
          'git curl ca-certificates python3 python3-venv python3-pip tmux jq; ' +
          'else echo "[solar] non-apt distro; skipping prerequisite install (installer will report any gaps)"; fi'
    & wsl.exe -d $Distro -- bash -lc $sh
    if ($LASTEXITCODE -ne 0) {
        throw "WSL prerequisite install failed (exit $LASTEXITCODE). Open '$Distro' once and run: sudo apt-get install -y git python3-venv python3-pip tmux jq"
    }
}

function Invoke-LinuxInstaller {
    $forwarded = Get-ForwardString
    # Prefer the bundled, version-matched get-solar.sh (same release as this app) over the network.
    $bundled = Join-Path $PSScriptRoot 'get-solar.sh'
    if (Test-Path $bundled) {
        $wp = & wsl.exe -d $Distro -- wslpath -a "$bundled" 2>$null
        if ($LASTEXITCODE -eq 0 -and $wp) {
            $wp = $wp.Trim()
            Write-Host "[solar] running bundled get-solar.sh inside WSL ($Distro): $wp"
            & wsl.exe -d $Distro -- bash -lc "set -o pipefail; bash '$wp' $forwarded"
            if ($LASTEXITCODE -ne 0) { throw "Solar runtime install failed inside WSL (exit $LASTEXITCODE)" }
            return
        }
        Write-Host '[solar] could not map the bundled get-solar.sh into WSL; falling back to network bootstrap.'
    }
    if ($BootstrapUrl -ne '') {
        Write-Host "[solar] bootstrapping the runtime from $BootstrapUrl inside WSL ($Distro)..."
        & wsl.exe -d $Distro -- bash -lc "set -o pipefail; curl -fsSL '$BootstrapUrl' | bash -s -- $forwarded"
    } else {
        $cmd = "set -e -o pipefail; tmp=`$(mktemp -d); git clone --depth 1 '$RepoUrl' `"`$tmp/OpenSolar`"; bash `"`$tmp/OpenSolar/install.sh`" $forwarded"
        Write-Host "[solar] cloning $RepoUrl and running install.sh inside WSL ($Distro)..."
        & wsl.exe -d $Distro -- bash -lc $cmd
    }
    if ($LASTEXITCODE -ne 0) { throw "Linux installer failed inside WSL (exit $LASTEXITCODE)" }
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

# Register the per-user logon task that brings WSL up + starts the status-server at login, so the
# runtime is already running before the desktop app opens. Best-effort; never fails the install.
function Enable-WindowsAutostart {
    $autostart = Join-Path $PSScriptRoot 'runtime\install-windows-autostart.ps1'
    if (-not (Test-Path $autostart)) { return }
    try {
        Write-Host '[solar] registering the WSL logon-autostart task...'
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $autostart -Distro $Distro
    } catch {
        Write-Warning "autostart registration skipped: $($_.Exception.Message)"
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
    if ($LASTEXITCODE -ne 0) {
        throw "wsl --install failed (exit $LASTEXITCODE). Ensure virtualization is enabled in BIOS and Windows is up to date, then re-run."
    }

    # The portable .exe unpacks to an EPHEMERAL temp dir, so a RunOnce that points at
    # $PSCommandPath would be a dead path after the reboot. Persist the scripts to a stable
    # machine-wide location and resume from there.
    $persist = Join-Path $env:ProgramData 'OpenSolar'
    New-Item -ItemType Directory -Force -Path $persist | Out-Null
    Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $persist 'install.ps1') -Force
    $bundled = Join-Path $PSScriptRoot 'get-solar.sh'
    if (Test-Path $bundled) { Copy-Item -LiteralPath $bundled -Destination (Join-Path $persist 'get-solar.sh') -Force }
    $runtimeDir = Join-Path $PSScriptRoot 'runtime'
    if (Test-Path $runtimeDir) { Copy-Item -LiteralPath $runtimeDir -Destination (Join-Path $persist 'runtime') -Recurse -Force }

    $persistPs1 = Join-Path $persist 'install.ps1'
    $runOnce = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\RunOnce'
    $resume = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$persistPs1`" $(Get-ForwardString)"
    Set-ItemProperty -Path $runOnce -Name 'OpenSolarResume' -Value $resume
    Write-Warning 'WSL2 was installed. A REBOOT is required (the one manual step).'
    Write-Warning 'After reboot, this installer resumes automatically via RunOnce.'
    exit 0
}

# ---- main ----
# Guarded so dot-sourcing the script (e.g. Pester: . ./install.ps1) loads the functions WITHOUT
# running the installer. Dot-sourcing sets $MyInvocation.InvocationName to '.'; -File / & runs it.
if ($MyInvocation.InvocationName -ne '.') {
    Start-SetupLog
    try {
        $Distro = Resolve-Distro
        if (-not (Test-WslReady)) {
            Install-Wsl
        } else {
            Install-WslPrerequisite
            Enable-WslSystemd
            Set-WslMirroredNetworking
            Invoke-LinuxInstaller
            Enable-WindowsAutostart
            Write-Host '[solar] Windows (WSL2) install complete.'
        }
    } finally {
        try { Stop-Transcript | Out-Null } catch { Write-Verbose "Stop-Transcript: $($_.Exception.Message)" }
    }
}
