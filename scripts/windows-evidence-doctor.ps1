<#
.SYNOPSIS
    Solar Windows/WSL2 evidence doctor - collects the diagnostics that explain a failed or flaky
    first-install ("WSL2 keeps not working"): admin/UAC context, WSL version/state/distros, the
    distro's default user, networking mode, the Solar runtime status inside WSL, and Windows<->WSL
    reachability. READ-ONLY (no changes). Prints a readable report; -Json emits machine-readable;
    -OutFile also saves it. Run it on the affected Windows machine when setup misbehaves, and attach
    the output to a bug report.

.DESCRIPTION
    Implements the "Windows evidence doctor" recommended by the cross-platform verification research
    (docs/insights/2026-06-26_cross-platform-desktop-webapp-verification.md, task 7). Every probe is
    best-effort and independent, so missing pieces are reported rather than aborting.

.PARAMETER Distro
    WSL distro to inspect. Defaults to the first usable registered distro (or
    Ubuntu-24.04). Docker Desktop's internal distros are never Solar targets.

.PARAMETER Json
    Emit the report as JSON instead of text.

.PARAMETER OutFile
    Also write the report to this path.
#>
[CmdletBinding()]
param(
    [string]$Distro = "",
    [switch]$Json,
    [string]$OutFile = ""
)
$ErrorActionPreference = "Continue"

function Test-SolarDistroName {
    param([AllowEmptyString()][string]$Name)
    $value = $Name.Trim()
    return ($value -ne '' -and $value -notmatch '^(?i:docker-desktop(?:-data)?)$')
}

function Get-RegisteredDistro {
    try { $out = & wsl.exe -l -q 2>$null } catch { return @() }
    if ($LASTEXITCODE -ne 0) { return @() }
    return @($out -split "`r?`n" |
        ForEach-Object { ($_ -replace "`0", '').Trim() } |
        Where-Object { Test-SolarDistroName $_ })
}

function Resolve-Distro {
    $list = @(Get-RegisteredDistro | Where-Object { Test-SolarDistroName $_ })
    if ((Test-SolarDistroName $Distro) -and ($list -contains $Distro)) { return $Distro }
    if ($list.Count -gt 0) { return $list[0] }
    return "Ubuntu-24.04"
}

function Invoke-WslText([string]$cmd, [string]$distro) {
    try {
        $r = & wsl.exe -d $distro -- bash -lc $cmd 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Verbose "wsl '$cmd' exited $LASTEXITCODE"
            return ""
        }
        return (($r -join "`n").Trim())
    } catch {
        Write-Verbose "wsl '$cmd' failed: $($_.Exception.Message)"
        return ""
    }
}

function Get-WslStatusServerEvidence([string]$distro) {
    $port = Invoke-WslText "cat `$HOME/.solar/harness/run/status-server.port 2>/dev/null" $distro
    if ($port -notmatch '^\d+$') {
        return [pscustomobject]@{
            PortNumber = ''
            StatusServerPort = '(not running)'
            WslToLoopback = ''
        }
    }

    $health = Invoke-WslText "curl -fsS -m 3 http://127.0.0.1:$port/healthz >/dev/null 2>&1 && echo ok || echo fail" $distro
    if ($health -ne 'ok') {
        return [pscustomobject]@{
            PortNumber = ''
            StatusServerPort = "(not running; stale port file $port)"
            WslToLoopback = 'fail'
        }
    }

    return [pscustomobject]@{
        PortNumber = $port
        StatusServerPort = $port
        WslToLoopback = 'ok'
    }
}

function Get-WslNetworkingMode {
    $cfg = Join-Path $env:USERPROFILE ".wslconfig"
    if (-not (Test-Path $cfg)) { return "nat (default; no .wslconfig)" }
    $m = (Get-Content $cfg | Where-Object { $_ -match '^\s*networkingMode\s*=' } | Select-Object -First 1)
    if ($m) { return ($m -replace '^\s*networkingMode\s*=\s*', '').Trim() }
    return "nat (default; .wslconfig has no networkingMode)"
}

function Test-WinUrl([string]$url) {
    try {
        $resp = Invoke-WebRequest -Uri $url -TimeoutSec 4 -UseBasicParsing -ErrorAction Stop
        return "HTTP $($resp.StatusCode)"
    } catch {
        return "unreachable ($($_.Exception.Message.Split([char]10)[0]))"
    }
}

if ($MyInvocation.InvocationName -ne '.') {
$distro = Resolve-Distro
$r = [ordered]@{}

# --- Windows identity / UAC ---
$idn = [Security.Principal.WindowsIdentity]::GetCurrent()
$pri = New-Object Security.Principal.WindowsPrincipal($idn)
$r["user"] = $idn.Name
$r["is_admin"] = [bool]$pri.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
try {
    $lua = (Get-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System' -Name EnableLUA -ErrorAction Stop).EnableLUA
    $r["uac_enabled"] = ($lua -eq 1)
} catch { $r["uac_enabled"] = "unknown" }

# --- WSL state ---
$r["wsl_version"] = (((& wsl.exe --version 2>$null) -join " ") -replace "`0", "").Trim()
$r["wsl_status"] = (((& wsl.exe --status 2>$null) -join " ") -replace "`0", "").Trim()
$r["distros_registered"] = (Get-RegisteredDistro) -join ", "
$r["distro_inspected"] = $distro
$r["networking_mode"] = Get-WslNetworkingMode

# --- inside the distro ---
$r["distro_user"] = Invoke-WslText "whoami" $distro
$r["wsl_ip"] = Invoke-WslText "hostname -I 2>/dev/null | cut -d' ' -f1" $distro
$r["systemd_enabled"] = Invoke-WslText "grep -q 'systemd=true' /etc/wsl.conf 2>/dev/null && echo yes || echo no" $distro
$prereqMissing = (Invoke-WslText "for b in git python3 pip3 tmux jq curl; do command -v `$b >/dev/null 2>&1 || echo `$b; done" $distro) -replace "`n", " "
$r["prereqs_missing"] = if ($prereqMissing.Trim()) { $prereqMissing.Trim() } else { "(none)" }
$r["solar_runtime_installed"] = Invoke-WslText "test -f `$HOME/.solar/harness/lib/symphony/status-server.py && echo yes || echo no" $distro
$server = Get-WslStatusServerEvidence $distro
$port = $server.PortNumber
$r["status_server_port"] = $server.StatusServerPort
if ($server.WslToLoopback) { $r["wsl_to_loopback"] = $server.WslToLoopback }

# --- reachability (only if the server is up) ---
if ($port -match '^\d+$') {
    $r["windows_to_loopback"] = Test-WinUrl "http://127.0.0.1:$port/healthz"
    if ($r["wsl_ip"]) { $r["windows_to_wsl_ip"] = Test-WinUrl "http://$($r['wsl_ip']):$port/healthz" }
}

# --- output ---
if ($Json) {
    $text = ($r | ConvertTo-Json -Depth 4)
} else {
    $lines = @("=== Solar Windows/WSL2 evidence doctor ===", "time: $((Get-Date).ToString('s'))")
    foreach ($k in $r.Keys) { $lines += ("{0,-24}: {1}" -f $k, $r[$k]) }
    # Quick interpretation to point at the usual culprits.
    $hints = @()
    if ($r["distros_registered"] -eq "") { $hints += "No WSL distro registered - run install.ps1 (it provisions Ubuntu-24.04)." }
    if ($r["solar_runtime_installed"] -eq "no") { $hints += "Solar runtime not installed in WSL - the in-WSL install step didn't complete (check %LOCALAPPDATA%\Solar\setup.log)." }
    if ($r["prereqs_missing"] -ne "(none)") { $hints += "Missing WSL prerequisites: $($r['prereqs_missing']) - install git/python3-pip/python3-venv/tmux/jq." }
    if ($port -match '^\d+$' -and $r["windows_to_loopback"] -notmatch 'HTTP 200' -and $r["wsl_to_loopback"] -eq 'ok') {
        $hints += "Server is up in WSL but Windows can't reach 127.0.0.1 - localhost forwarding broken; set networkingMode=mirrored (Win11 22H2+) or use the WSL IP."
    }
    if ($hints.Count) { $lines += ""; $lines += "--- likely issues ---"; $hints | ForEach-Object { $lines += "* $_" } }
    $text = $lines -join "`n"
}

Write-Output $text
if ($OutFile) {
    try { $text | Out-File -FilePath $OutFile -Encoding UTF8; Write-Output "`n(written to $OutFile)" }
    catch { Write-Verbose "could not write $OutFile : $($_.Exception.Message)" }
}
}
