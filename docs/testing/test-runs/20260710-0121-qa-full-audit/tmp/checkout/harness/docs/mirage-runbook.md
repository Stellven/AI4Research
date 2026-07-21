# Mirage Operator Runbook

**Sprint**: sprint-20260508-mirage-codex-solar-substrate
**Created**: 2026-05-08

---

## 1. What Is Mirage

Mirage is the Solar VFS (Virtual File System) abstraction layer. It provides a unified, bounded read/search surface across Knowledge, QMD/MinerU, Solar state, sprint artifacts, Cortex, and optional Google Drive.

**Canonical entry for all cross-source reads:**
```bash
solar-harness mirage search "<query>" --json
solar-harness mirage exec -- 'cat /knowledge/path.md'
```

## 2. What Goes Through Mirage, What Doesn't

| Layer | Route |
|-------|-------|
| Cross-source search | `solar-harness mirage search` |
| File read via logical mount | `solar-harness mirage exec -- 'cat /mount/path'` |
| Knowledge write | `solar-harness wiki ingest` |
| Sprint mutation | coordinator/evaluator only |
| Config change | `solar-config-ui` (port 8789) |

## 3. Security Boundaries

| Boundary | Enforcement |
|----------|-------------|
| Host absolute paths | Blocked in `mirage exec` (exit 126) |
| `/knowledge` write | Denied (mode: ro) |
| `/sprints` write | Denied (mode: ro) |
| `/solar` write | Denied (mode: ro) |
| `/drive` write | Denied unless `--allow-write-drive` |
| `/raw` write | Allowed (staging area) |
| Credential subpaths | `deny_subpaths` redaction |

## 4. Health Check

```bash
# Quick health
solar-harness mirage doctor --json | python3 -m json.tool

# Check config UI status
curl -fsS http://127.0.0.1:8789/api/status | python3 -c '
import json,sys; d=json.load(sys.stdin); print(json.dumps(d["checks"]["mirage"], indent=2))'

# Run security boundary probes
bash ~/.solar/harness/tests/test-mirage-substrate.sh
```

## 5. Configuration

Config file: `~/.solar/harness/config/mirage.solar.yaml`

```yaml
version: 1
workspace_id: solar-default
mounts:
  - path: /knowledge
    source_type: disk
    root: ~/Knowledge
    mode: ro
  - path: /raw
    source_type: disk
    root: ~/Knowledge/_raw
    mode: rw
  - path: /sprints
    source_type: disk
    root: ~/.solar/harness/sprints
    mode: ro
```

Edit via config UI: `http://127.0.0.1:8789` → Mirage section.

## 6. Troubleshooting

### `host path not allowed` Error

A command tried to use `~/.something` or `/etc/...` or `/Users/...`.

Fix: Use logical mount path instead:
- `~/Knowledge/file.md` → `/knowledge/file.md`
- `~/.solar/harness/sprints/` → `/sprints/`

### Search Returns No Hits

```bash
# Check mounts are ready
solar-harness mirage doctor --json | python3 -c 'import json,sys; d=json.load(sys.stdin); [print(m["path"], m["ready"]) for m in d["mounts"]]'
```

### Drive Mount Failing

Drive mount is optional and off by default. Status `degraded` is expected when no credentials are configured.

To enable: Configure Google credentials path in config UI, then re-probe:
```bash
curl -X POST http://127.0.0.1:8789/api/mirage/reprobe
```

## 7. Rollback

To disable Mirage without affecting other harness features:

```bash
# Set enabled: false in config
curl -X POST http://127.0.0.1:8789/api/config \
  -H 'content-type: application/json' \
  -d '{"config": {"mirage": {"enabled": false}}}'
```

Config backup is at `~/.solar/harness/config/mirage.solar.yaml.bak` (written on every save).
