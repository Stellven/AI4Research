#Requires -Version 5.1
# Remove the Solar WSL logon-autostart task (parity with the mac/linux uninstallers).
[CmdletBinding()]
param([string]$TaskName = "OpenSolar-WSL-Autostart")
$ErrorActionPreference = "SilentlyContinue"
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "[uninstall] removed logon task '$TaskName' (if present)"
