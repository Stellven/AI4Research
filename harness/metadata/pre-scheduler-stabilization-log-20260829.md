# Pre-Scheduler Stabilization Log — 2026-08-29

Scope: the locked runtime at `D:\demo only version\harness`, from GUI intake through successful Planner completion. Rapid mode is used for every retest. Scheduler and later-stage defects are report-only.

| # | Stage | Symptom | Root cause | Fix | Verification |
|---|---|---|---|---|---|
| 1 | GUI health | Concurrent `/api/sprints` polling timed out and made intake unreliable. | Every request rebuilt the expensive sprint index independently. | Added a short-lived, stale-while-refresh single-flight cache around the sprint index. | Focused regression: 5 passed. Live cold burst: 8/8 HTTP 200 in about 1.39 s. Git `87d497984`. |
| 2 | Intent Compiler workspace | GUI intake launched compiler artifacts under `/home/james/.solar/harness/intents` instead of the selected runtime. | `intent_gateway.py` defaulted intent and sprint directories to `Path.home()` and ignored `HARNESS_DIR`. | Derive default intent and sprint directories from the portable runtime root, with explicit directory environment variables still taking precedence. | Portable-path probe passed; 36 runtime Intent/typed-Planner regressions passed. Exact-prompt retest pending. |
