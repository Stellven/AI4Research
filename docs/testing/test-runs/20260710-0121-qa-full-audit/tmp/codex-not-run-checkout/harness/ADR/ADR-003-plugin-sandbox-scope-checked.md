# ADR-003: Plugin Sandbox Strategy — Scope-Checked Start

**Date**: 2026-05-09
**Status**: Accepted
**Deciders**: Solar Product Platform S4 builder
**Sprint**: sprint-20260509-solar-product-platform (S4 Extension Framework)

## Context

Solar Harness needs an extension framework that allows third-party integrations (Obsidian, QMD, MinerU, Mirage, Mermaid, etc.) to be managed declaratively. The key risks are:

1. **Scope creep**: A plugin writes to paths it was never supposed to touch, corrupting user data or other plugins' state.
2. **False-ok status**: Plugins that are stubs or broken report as healthy, hiding real integration gaps.
3. **Uncontrolled activation**: Enabling a plugin should be explicit; new plugins must not auto-activate on installation.

## Decision

We adopt a **scope-checked manifest** approach as the first sandbox tier. This is intentionally minimal ("scope-checked start") rather than a full container/VM sandbox, which would add too much complexity for the current phase.

### Manifest-First Design

Every plugin declares itself in `plugins/<id>/manifest.yaml` with:
- **`write_scope`**: explicit list of paths the plugin may write to (relative to HARNESS_DIR or absolute)
- **`read_scope`**: paths it reads from (informational, not enforced at this tier)
- **`capabilities`**: tokens it provides (registered in state DB via `capability_registry.py`)
- **`integration_level`**: one of `dead_end / basic_usable / default_usable / closed_loop`
- **`status`**: `enabled / disabled / candidate` — default for new plugins is **`candidate`**

### Scope Enforcement

`plugin_loader.py::cmd_check_scope()` implements the guard:

```python
def _check_scope(plugin, target_path) -> bool:
    # expand write_scope entries relative to HARNESS_DIR
    # return True if target_path starts with any scope entry
    # /tmp/solar-* always allowed (temp output)
```

On violation:
1. Return `allowed=False`
2. Emit `plugin.scope_violation` event to `events.jsonl`
3. Caller **must not proceed** with the write

This is enforced at the `check-scope` CLI level; host-level filesystem isolation is deferred to a future ADR.

### Four-Level Integration Classification

| Level | Meaning |
|-------|---------|
| `dead_end` | Plugin present but no live connection; stub only |
| `basic_usable` | Can perform core action; no bidirectional feedback |
| `default_usable` | Default workflow works; edge cases need manual steps |
| `closed_loop` | Fully automated, self-healing, event-driven |

`solar-harness integrations plugins --json` exposes this per-plugin and aggregated.

### Capability Registry

Capabilities from all enabled plugins are synced to `plugin_capabilities` table in `run/state.db` via `capability_registry.py sync`. This allows:
- `autopilot.py` to discover what is available before dispatching
- `evolution_engine.py` (S5) to score capability coverage
- `solar-harness integrations capabilities` to inspect live state

### Status Lifecycle

```
new plugin → candidate (default, never auto-enabled)
    ↓ solar-harness integrations install <id>
  enabled
    ↓ solar-harness integrations disable <id>
  disabled
```

## Alternatives Considered

| Option | Rejected Reason |
|--------|----------------|
| Full container sandbox per plugin | Too heavy; most Solar plugins are thin wrappers, not arbitrary code |
| Symlink-based scope enforcement | Symlink following defeats path prefix checks; avoided |
| No scope checking | Would allow accidental overwrites; unacceptable for production data |
| Capability-only model (no manifest) | Harder to audit; manifest provides single source of truth |

## Consequences

**Positive**:
- Simple to implement and audit (YAML + path prefix check)
- Scope violations are logged, not silently ignored
- Capability registry enables autopilot-aware dispatching (S5 dependency)
- Four-level status prevents false-ok (plugins start at `dead_end` if unconfigured)

**Negative / Deferred**:
- No kernel-level isolation; a misbehaving plugin could still bypass scope via subprocess
- `read_scope` is informational only at this tier — enforcement would require inotify/fanotify (future work)
- Scope checking requires explicit `check-scope` call by the plugin host; automatic enforcement on every `open()` is out of scope

## Future Work

- ADR-004: Move to cgroups-based resource limits for MinerU/heavy plugins
- ADR-007: fsevents-based read scope monitoring (macOS FSEvents / Linux inotify)
- Consider `pledge()`-style syscall restriction for high-risk plugins in later tiers
