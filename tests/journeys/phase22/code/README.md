# Phase 22 Journey Tests

Run all non-live journeys:

```powershell
.venv\Scripts\python.exe -m pytest tests/journeys/phase22/code -m "not live_provider" -vv --basetemp .codex-tmp/pytest-phase22-journeys-repair002 -o cache_dir=.codex-tmp/pytest-cache-phase22-journeys-repair002
```

Run one journey:

```powershell
.venv\Scripts\python.exe -m pytest tests/journeys/phase22/code -k p22_j04 -vv --basetemp .codex-tmp/pytest-phase22-j04-repair002 -o cache_dir=.codex-tmp/pytest-cache-phase22-j04-repair002
```

Run live/network-gated journeys only after explicit authorization and provider setup:

```powershell
$env:PHASE22_ENABLE_LIVE_JOURNEYS="1"
$env:PHASE22_ENABLE_NETWORK_JOURNEYS="1"
.venv\Scripts\python.exe -m pytest tests/journeys/phase22/code -m live_provider -vv --basetemp .codex-tmp/pytest-phase22-journeys-live-repair002 -o cache_dir=.codex-tmp/pytest-cache-phase22-journeys-live-repair002
```

Each test writes a run directory under `outputs/phase22-real-journeys/<run-id>/`
and refreshes `.codex-tmp/phase22-worker-results/journey-code-repair-002/result.json`.
