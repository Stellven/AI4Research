param(
    [string]$Distro = "SolarUbuntu",
    [switch]$CleanRestart,
    [string]$AppRelativePath = "desktop\\dist\\win-unpacked\\Solar.exe"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$exePath = Join-Path $repoRoot $AppRelativePath

if (-not (Test-Path $exePath)) {
    throw "未找到 Solar.exe: $exePath"
}

Write-Host "[1/4] 准备本地进程..."
Stop-Process -Name Solar -ErrorAction SilentlyContinue | Out-Null
if ($CleanRestart) {
    Write-Host "执行显式冷启动：关闭 WSL..."
    wsl --shutdown 2>$null
    Start-Sleep -Seconds 2
}

Write-Host "[2/4] 预热完整 WSL 运行时 ($Distro)..."
$prewarm = @'
set -e
mkdir -p ~/.solar/workspace ~/.solar/logs
systemctl --user start solar-status-server.service 2>/dev/null || true
env SOLAR_PRODUCT_MODE=1 SOLAR_PANE_RUNTIME=codex SOLAR_PM_DEFAULT_PROVIDERS=openai SOLAR_MULTI_TASK_DEFAULT_PROVIDERS=openai bash ~/.solar/harness/solar-harness.sh start ~/.solar/workspace --skip-doctor
'@
& wsl.exe -d $Distro -- bash -lc $prewarm
if ($LASTEXITCODE -ne 0) {
    throw "Solar WSL runtime 预热失败（exit=$LASTEXITCODE）"
}
$probe = @'
set -e
tmux has-session -t solar-harness 2>/dev/null
test -s ~/.solar/harness/.coordinator.pid
kill -0 "$(cat ~/.solar/harness/.coordinator.pid)" 2>/dev/null
'@
& wsl.exe -d $Distro -- bash -lc $probe
if ($LASTEXITCODE -ne 0) {
    throw "Solar WSL runtime readiness 失败（exit=$LASTEXITCODE）"
}

Write-Host "[3/4] 启动 Solar GUI..."
$proc = Start-Process -FilePath $exePath -PassThru
Write-Host "Solar 已启动，PID=$($proc.Id)"

try {
    $port = (wsl -d $Distro -e bash -lc "cat ~/.solar/harness/run/status-server.port 2>/dev/null | tr -d '\r' | tr -d '\n'").Trim()
    if ($port -match '^\d+$') {
        Write-Host "status-server 端口: $port"
    } else {
        throw "status-server 端口未写入"
    }
} catch {
    throw "status-server readiness 检查失败：$($_.Exception.Message)"
}

Write-Host "[4/4] 启动完成。"
