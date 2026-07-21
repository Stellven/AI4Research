# A4 OQ Resolutions: Social Browser Backend for X

Sprint: `sprint-20260525-tech-hotspot-radar-social-browser-backend-for-x-大咖监控-s02-architecture`

Scope: architecture decision table only. No implementation code, no Browser Agent invocation, no extra ThunderOMLX instance.

## Decision Table

| OQ | Decision | Yes/No | Reason | PRD / AC Reference | Owner | Fallback |
|---|---|---:|---|---|---|---|
| OQ-01 lease fail policy | If Browser Agent lease fails because the upstream browser operator is a hard blocker, immediately fall back to `rss_public_fallback`; otherwise retry for 5 minutes with jitter before falling back. | Yes | The PRD requires the sprint to remain blocked until the global Browser Agent operator is ready. Once implementation is allowed, transient lease contention should not fail the whole batch, but an unmet hard blocker must not be hidden by retries. | Hard Dependency / Blocker; Backend order; AC-1, AC-2, AC-5, AC-9 | S03 core runtime | `rss_public_fallback`, then `manual_curated_import` with explicit warning |
| OQ-02 ThunderOMLX reuse | Reuse the existing ThunderOMLX service through its configured local socket/API. Do not start a new ThunderOMLX process for browser-collected posts. | Yes | The PRD explicitly forbids extra ThunderOMLX instances. Semantic extraction is downstream of `social_posts`, so the browser backend only submits normalized posts to the existing local semantic path. | Downstream integration; AC-6, AC-8, AC-10 | S03 core runtime | If local semantic service is unavailable, persist raw posts and enqueue retry with `semantic_extract_pending` |
| OQ-03 premium reasoning trigger | Premium reasoning is triggered only when a tier-1/P0 account post has high entity/link recall or cross-source resonance; do not send raw social streams directly to premium models. | Yes | This matches the HF Paper Insight S02 OQ-03 pattern: use local extraction first, then route high-value packets. It also keeps X/browser collection low-cost and auditable. | Downstream integration; AC-6, AC-8; cross-ref HF Paper Insight S02 OQ-03 | S03/S04 | Keep item as local-only `weak_signal` until GitHub/YouTube/paper evidence raises confidence |
| OQ-04 dedup conflict handling | Dedup priority is canonical post URL first; if URL and sha256 conflict, sha256 wins identity while canonical URL is updated to the latest observed URL. | Yes | URL is more interpretable for humans, but browser-visible URLs can vary by tracking, mobile/desktop form, or redirect. Content hash protects against duplicate semantic extraction and viewpoint inflation. | Deduplication; AC-4 | S03 data/runtime | Store conflict in dedup audit table and suppress downstream duplicate writes |
| OQ-05 Knowledge ingest order | Write Knowledge raw synchronously first; extracted/QMD/graph updates run asynchronously after raw persistence, with retryable failure records. | Yes | This preserves evidence before expensive extraction and follows the HF Paper Insight S02 OQ-05 pattern: raw is the source of truth, derived stores are rebuildable. | Downstream integration; AC-7, AC-8; cross-ref HF Paper Insight S02 OQ-05 | S03/S05 | If extracted/QMD/graph fails, leave raw object plus retry manifest; do not drop collected post |
| OQ-06 `rate_429` backoff scope | Backoff is per account, not global. Global concurrency remains 1 by default, but one account's `rate_429` must not pause the entire 200-account roster. | Yes | PRD requires failed accounts to affect only themselves. Per-account cooldown protects high-value accounts while keeping the collector useful for other handles. | Rate limiting; AC-5 | S03 core runtime | Mark account `cooldown_until`; continue next eligible account; summarize skipped accounts in status |
| OQ-07 screenshot storage | Store screenshot path and DOM hash in Knowledge raw metadata, but do not store image binary in Knowledge raw by default. | Yes | Screenshot is fallback evidence for parse failure, but binary storage would bloat the knowledge store and duplicate browser artifact storage. Path + hash is enough for audit and replay. | Data extraction; WebUI / Status; AC-2, AC-7 | S03/S04 | If screenshot file is missing at review time, keep DOM hash and mark visual evidence unavailable |

## Cross-Epic References

- HF Paper Insight S02 OQ-03 is reused as the premium reasoning routing pattern: local preprocessing builds compact evidence packets before any high-level model call.
- HF Paper Insight S02 OQ-05 is reused as the ingest ordering pattern: raw first, derived stores async and rebuildable.
- YouTube transcript pipeline precedent is reused for low-quality source handling: browser-visible text is not strong evidence until normalized, deduped, and linked to source metadata.

## Residual Risks

- Browser Agent global operator readiness remains a hard blocker for browser backend implementation.
- Browser DOM shape can change; parse failure must degrade to screenshot path + DOM hash without breaking the batch.
- Premium reasoning triggers can over-fire if tier-1 accounts quote the same source; cross-source resonance must dedup propagation chains before escalation.
- Per-account backoff can still starve low-tier accounts if scan windows are too small; S04 status must expose skipped/cooldown counts.

## Implementation Notes

- S03 must encode these decisions in config defaults and runtime guards.
- S04 must surface backend readiness, fallback count, parse failure count, skipped accounts, and semantic pending count.
- S05 must verify no X API token is required, no duplicate Browser/ThunderOMLX process starts, and duplicate posts do not enter downstream semantic tables.
