# A3 Compatibility and Migration Plan

Sprint: `sprint-20260525-tech-hotspot-radar-social-browser-backend-for-x-大咖监控-s02-architecture`

Scope: migration plan only. No runtime migration is executed in this slice.

## 1. Legacy Backend Policy

The X API path is preserved only as an explicit optional backend:

```text
--backend x_api --ack-x-api-cost
```

It must not be selected by `--backend auto`, and it must not bypass `BackendSelector`.

## 2. Three-Phase Migration Ladder

| Phase | Default behavior | X API behavior | Exit criteria |
|---|---|---|---|
| Phase 1 dual-write | Browser backend writes candidate rows; legacy X API can run in parallel for comparison. | Explicit opt-in only. | Dedup compare shows no duplicate downstream semantic/viewpoint rows. |
| Phase 2 browser priority | `auto` selects browser when Browser Agent operator is ready; RSS/manual remain fallback. | Token path allowed only if user selects `x_api`. | Browser smoke works for `--limit-accounts 5`; fallback telemetry is visible. |
| Phase 3 deprecated opt-in | Browser/RSS/manual are the normal path. | X API is deprecated and hidden behind explicit cost acknowledgement. | S05 verifies no X API token is required for default smoke. |

## 3. Rollback Switch

```bash
SOLAR_SOCIAL_BROWSER_BACKEND_DISABLE=1
```

Behavior:

1. `BackendSelector` treats `browser_agent` as unavailable.
2. `auto` proceeds to `rss_public_fallback`, then `manual_curated_import`.
3. Existing browser-collected rows remain readable; no destructive rollback is performed.
4. Status surface must show `browser_backend_disabled_by_env`.

## 4. Degradation Paths

| Failure | Degradation | Data retained | User-visible status |
|---|---|---|---|
| Browser lease unavailable | `browser_agent -> rss_public_fallback` | scan job reason + fallback count | `browser_lease_unavailable` |
| RSS unavailable | `rss_public_fallback -> manual_curated_import` | no-op job + warning | `rss_unavailable_manual_mode` |
| ThunderOMLX socket unavailable | skip semantic extraction; raw post persists | Knowledge raw + `semantic_extract_pending` | `local_semantic_unavailable_raw_only` |

Each degradation is per account or per batch segment; it must not fail the whole 200-account roster.

## 5. Dedup Conflict Resolution

Conflict: legacy X API row and browser row describe the same post but URL formats differ.

Resolution:

1. Normalize canonical URL when possible.
2. Compute sha256 fallback from `author_handle + normalized_text + visible_time`.
3. If canonical URL and sha256 conflict, sha256 identity wins.
4. Store latest canonical URL as metadata and increment `conflict_count`.
5. Suppress duplicate writes to `social_semantic_extracts`, `big_name_viewpoints`, and `propagation_chains`.

## 6. Operational Boundaries

- Do not create a second Browser/Playwright/Chrome system.
- Do not start an extra ThunderOMLX instance.
- Do not make X API a default backend.
- Do not implement anti-bot bypass or login circumvention.
- Do not close the parent epic from this architecture slice.

## 7. Acceptance Map

| Acceptance | Status | Evidence |
|---|---|---|
| A-A3-1 | covered | §2 defines Phase 1 dual-write, Phase 2 browser priority, Phase 3 deprecated opt-in. |
| A-A3-2 | covered | §3 defines `SOLAR_SOCIAL_BROWSER_BACKEND_DISABLE=1`. |
| A-A3-3 | covered | §4 defines lease->rss, rss->manual, ThunderOMLX->raw-only. |
| A-A3-4 | covered | §5 defines legacy X API dedup via sha256 fallback. |
| A-A3-5 | covered | §1 preserves X API token path as explicit optional backend only. |
