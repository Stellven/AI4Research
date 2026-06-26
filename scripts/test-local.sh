#!/usr/bin/env bash
# test-local.sh — run every gate that is runnable on THIS machine before pushing, so CI
# failures don't bounce back ("stop the back-and-forth"). Pure bash/Node/Python gates run on
# any dev box; the Windows-host gates (install.ps1 parse + PSScriptAnalyzer with the SAME exclude
# set as CI) run automatically when powershell.exe is reachable (a WSL2 session or native Windows).
#
#   bash scripts/test-local.sh            # run all available gates
#
# Each gate prints PASS / FAIL / SKIP; the script exits non-zero if ANY gate failed.
# Mirrors: install-matrix.yml (install.ps1 lint), kernel-gen (check-daemons-render),
# desktop-build.yml (autotest), solar-ci, plus the privacy/whitespace checks.
set -u
repo="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo"
pass=0; fail=0; skip=0

run() { # run <name> <cmd...>   (cmd exit: 0=PASS, 2=SKIP, other=FAIL)
  local name="$1"; shift
  printf '\n--- %s ---\n' "$name"
  "$@"; local rc=$?
  if   [ "$rc" -eq 0 ]; then echo "PASS: $name"; pass=$((pass + 1))
  elif [ "$rc" -eq 2 ]; then echo "SKIP: $name"; skip=$((skip + 1))
  else echo "FAIL: $name (exit $rc)"; fail=$((fail + 1)); fi
}

dashboard_build() {
  [ -d harness/status-server/react-app/node_modules ] || { echo "(npm install in react-app first)"; return 2; }
  ( cd harness/status-server/react-app && npm run typecheck && npm run build >/dev/null )
}

# --- Windows-host gates (only when powershell.exe is reachable) ---
# NOTE: WSL env vars do NOT cross into powershell.exe unless shared via WSLENV — and an empty
# $env:PSFILE makes Invoke-ScriptAnalyzer silently analyze NOTHING (a false pass). Both helpers
# therefore fail hard if PSFILE is missing/unreadable.
ps_parse() {
  powershell.exe -NoProfile -Command 'if(-not $env:PSFILE -or -not (Test-Path $env:PSFILE)){ Write-Host "PSFILE not set/readable"; exit 1 }; $e=$null; [System.Management.Automation.Language.Parser]::ParseFile($env:PSFILE,[ref]$null,[ref]$e); if(@($e).Count){ @($e) | ForEach-Object { Write-Host $_.Message }; exit 1 } else { Write-Host "parse ok" }'
}
ps_lint() {
  powershell.exe -ExecutionPolicy Bypass -NoProfile -Command 'if(-not $env:PSFILE -or -not (Test-Path $env:PSFILE)){ Write-Host "PSFILE not set/readable"; exit 1 }; if(-not (Get-Module -ListAvailable -Name PSScriptAnalyzer)){ Write-Host "PSScriptAnalyzer not installed (Install-Module PSScriptAnalyzer -Scope CurrentUser)"; exit 2 }; Import-Module PSScriptAnalyzer; $x=@("PSAvoidUsingWriteHost","PSUseShouldProcessForStateChangingFunctions","PSReviewUnusedParameter"); $i=Invoke-ScriptAnalyzer -Path $env:PSFILE -Severity Error,Warning -ExcludeRule $x; if($i){ $i | Format-Table RuleName,Line,Message -Auto | Out-String | Write-Host; exit 1 } else { Write-Host "lint clean" }'
}

echo "== Solar local test gate =="
echo "repo: $repo"

run "git diff --check"          git diff --check
run "check-privacy"             bash scripts/check-privacy.sh
run "check-daemons-render"      bash scripts/check-daemons-render.sh
run "check-harness-plumbing"    bash scripts/check-harness-plumbing.sh
run "status-server py_compile"  python3 -m py_compile harness/lib/symphony/status-server.py
run "dashboard typecheck+build" dashboard_build
run "desktop main.js syntax"    node --check desktop/src/main.js
run "desktop autotest"          bash -c 'cd desktop && bash autotest.sh'

if command -v powershell.exe >/dev/null 2>&1; then
  PSFILE="$(wslpath -w "$repo/install.ps1" 2>/dev/null || echo "$repo/install.ps1")"
  export PSFILE
  export WSLENV="${WSLENV:+$WSLENV:}PSFILE"  # WSL env vars only reach powershell.exe via WSLENV
  run "install.ps1 parse (Windows PowerShell)" ps_parse
  run "install.ps1 lint (PSScriptAnalyzer, CI rules)" ps_lint
else
  echo; echo "SKIP: Windows-host install.ps1 parse+lint (no powershell.exe; runs in WSL/Windows)"; skip=$((skip + 1))
fi

echo
echo "================================"
echo "PASS=$pass  FAIL=$fail  SKIP=$skip"
[ "$fail" -eq 0 ] && { echo "LOCAL GATE: GREEN"; exit 0; } || { echo "LOCAL GATE: RED"; exit 1; }
