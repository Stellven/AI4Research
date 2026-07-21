# ADR-004 — Release Artifact Structure

**Status**: Accepted  
**Date**: 2026-05-09  
**Slice**: S7  
**Authors**: builder_main

---

## Context

Solar Harness v1.0 needs a reproducible, auditable release artifact that:
1. Can be installed on a clean machine
2. Excludes all plaintext secrets
3. Includes a verifiable checksum
4. Links to all ADRs and the CHANGELOG

Prior to this ADR, there was no release artifact structure — all installs were from a live `~/.solar/harness` working tree.

---

## Decision

### Artifact Set

A release consists of exactly three files:

| File | Purpose |
|------|---------|
| `solar-harness-<version>.tar.gz` | All harness code and config |
| `solar-harness-<version>.sha256` | SHA256 checksum of the tarball |
| `MANIFEST-<version>.json` | Structured metadata (version, build_at, file_count, ADRs, guides) |

### Tarball Exclusions

The following are never included in the release tarball:

| Excluded path | Reason |
|---------------|--------|
| `.git/` | Source control metadata, not needed at install time |
| `__pycache__/`, `*.pyc` | Compiled bytecode, platform-specific |
| `venvs/` | Per-machine virtual environments |
| `vendor/` | Third-party code with its own licensing |
| `release/artifacts/` | Prevent self-referential inclusion |
| `run/` | Runtime state (pidfiles, state.db, events.jsonl) |
| `backups/` | Snapshot backups — not part of code distribution |
| `events/` | Runtime event streams such as `events/all.jsonl` |
| `logs/` | Local logs, not source distribution |
| `sessions/` | Runtime session transcripts and QMD search traces |
| `reports/` | Generated local reports, not release source |
| `_extracted_knowledge_fallback/` | Local generated knowledge fallback output |
| `.pytest_cache/` | Local test cache |
| `*.db`, `*.sqlite`, `*.sqlite3` | Runtime databases |
| `*.pid`, `*.lock`, `*.tmp` | Local process/lock/temp files |

### Checksum Algorithm

SHA256 (via `sha256sum` on Linux or `shasum -a 256` on macOS).

The checksum file format follows `sha256sum` convention:
```
<hex_digest>  <filename>
```

### MANIFEST Schema

```json
{
  "version": "1.0.0",
  "build_at": "ISO8601",
  "tarball": "solar-harness-1.0.0.tar.gz",
  "sha256": "<hex>",
  "size_bytes": 123456,
  "file_count": 789,
  "slices_included": ["S0","S1","S2","S3","S4","S5","S6","S7"],
  "adrs": ["ADR-001","ADR-002","ADR-003","ADR-004","ADR-005"],
  "changelog": "release/CHANGELOG.md",
  "upgrade_guide": "docs/upgrade-guide.md",
  "rollback_guide": "docs/rollback-guide.md"
}
```

### Pre-Publish Audit Gates

`release/publish.sh` enforces the following gates before a release can be marked publish-ready:

| Gate | Check |
|------|-------|
| G1 | VERSION is semver (`major.minor.patch`) |
| G2 | Tarball + sha256 + manifest all exist |
| G3 | SHA256 of tarball matches sha256 file |
| G4 | gitleaks scan (or fallback grep) finds 0 secrets |
| G5 | All plugin manifests pass schema validation |
| G6 | All `lib/*.py` files compile cleanly |
| G7 | CHANGELOG.md has an entry for the current version |
| G8 | TVS renderer bridge, Bun runtime, `SOLAR_TVS_ROOT`, and smoke render pass |

Any gate failure (`FAIL`) blocks publication. `WARN` (e.g. gitleaks not installed) is logged but does not block if the fallback passes.

TVS is a release-level dependency because `solar-harness tvs render` is now the
canonical deterministic terminal rendering path for agent-facing output. A
release must fail publication if Bun is unavailable, `SOLAR_TVS_ROOT` does not
point to a TVS checkout containing `index.ts`, the bridge file is missing, or
the smoke render does not produce the expected TVS output.

### Container Validation (D7.2)

The release includes `docker/Dockerfile` + `docker/smoke-test.sh` for clean container round-trip testing. This requires a running Docker daemon. The gate is documented as G2 in the sprint plan. If Docker is unavailable, the gate is recorded as `warn:deferred` and must be completed before the release is marked final.

---

## Alternatives Considered

### A — Single tarball, no MANIFEST

Simpler, but prevents automated audit tooling from knowing which slices and ADRs are included. Rejected.

### B — Container image as primary artifact

Docker image as the release unit. Rejected: requires Docker daemon at build time; impractical for Mac-first users; secrets baked into layers are hard to audit.

### C — Checksumming individual files instead of tarball

Fine-grained, but tarball checksum is the industry standard for distribution. Per-file manifest is additive, not a replacement. Both are implemented: tarball sha256 + per-file exclusion list.

---

## Consequences

- `release/build.sh` must be idempotent (re-run produces identical artifact if source unchanged).
- `VERSION` file at harness root is the authoritative version source.
- `release/publish.sh` is a mandatory pre-release gate, not optional.
- D7.2 (container round-trip) is a hard gate for final publication; it can be deferred with explicit `warn:deferred` documentation.

---

## References

- `release/build.sh`
- `release/publish.sh`
- `release/CHANGELOG.md`
- `docker/Dockerfile`
- `docker/smoke-test.sh`
- `gitleaks.toml`
- ADR-001 (state DB — included in tarball, runtime excluded)
- ADR-003 (plugin sandbox — manifests included in tarball)
