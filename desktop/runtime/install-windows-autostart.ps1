#Requires -Version 5.1
<#
  Register a per-user logon task that brings WSL2 up and prewarms the complete Solar runtime
  at every login. WSL2 does not auto-start until first invoked, so this is the Windows
  half of "the runtime is already running locally" - it pairs with the in-WSL systemd
  user unit + `loginctl enable-linger` (install-linux-service.sh, run inside WSL).
  Idempotent. No admin required (the one-time WSL2 install already happened via install.ps1).
#>
[CmdletBinding()]
param(
  [string]$Distro   = "Ubuntu-24.04",
  [string]$TaskName = "OpenSolar-WSL-Autostart"
)
$ErrorActionPreference = "Stop"

# The VBS launcher (wscript host) lives next to this script - it runs wsl.exe with no console flash.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$vbs  = Join-Path $here "start-solar-wsl.vbs"
if (-not (Test-Path $vbs)) { throw "Missing launcher: $vbs" }

# Idempotent: drop any prior registration first.
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null

$action  = New-ScheduledTaskAction -Execute "wscript.exe" -Argument ("`"$vbs`" `"$Distro`"")
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$trigger.Delay = "PT5S"   # let WSL/networking settle before firing (cold-start can be slow)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
              -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
# "Run only when user is logged on" (Interactive) - NOT session-0, so the user's WSL/systemd
# instance and 127.0.0.1 localhostForwarding are correct. Limited run-level = no admin prompt.
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
  -Settings $settings -Principal $principal `
  -Description "Brings WSL2 up and prewarms the complete Solar runtime at logon." | Out-Null

Write-Host "[install] registered logon task '$TaskName' (distro=$Distro)"
Write-Host "[install] verify:  Get-ScheduledTask -TaskName $TaskName"
Write-Host "[install] action:  wscript start-solar-wsl.vbs -> status-server + harness + coordinator"
