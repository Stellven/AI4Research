# A2 Data Model Schema: Social Browser Backend for X

Sprint: `sprint-20260525-tech-hotspot-radar-social-browser-backend-for-x-大咖监控-s02-architecture`

Scope: schema and DDL specification only. No migration is executed in this slice.

## 1. `post_record` Contract

| # | Field | Type | Nullable | Source | Notes |
|---:|---|---|---:|---|---|
| 1 | `post_id` | `TEXT` | yes | visible status id | Null when browser cannot infer status id. |
| 2 | `author_handle` | `TEXT` | no | profile handle | Lowercase, no leading `@`. |
| 3 | `text` | `TEXT` | no | DOM text | UTF-8, preserve useful line breaks. |
| 4 | `created_at` | `TEXT` | yes | visible timestamp | ISO UTC when inferable. |
| 5 | `visible_relative_time` | `TEXT` | yes | DOM timestamp | Required when `created_at` is null. |
| 6 | `post_url` | `TEXT` | yes | canonical URL | Preferred dedup input when stable. |
| 7 | `metrics_reply/repost/like/view` | `INTEGER` or `TEXT 'N/A'` | yes | visible metrics | Do not coerce invisible metrics to zero. |
| 8 | `urls` | `JSON` | no | extracted links | Default `[]`; includes GitHub/arXiv/YouTube URLs. |
| 9 | `dom_hash` | `TEXT` | no | sha256 raw DOM | DOM drift and parse audit key. |
| 10 | `screenshot_path` | `TEXT` | yes | screenshot fallback | Non-null when parse failure requires visual evidence. |
| 11 | `collection_backend` | `TEXT` | no | collector | Constant `browser_agent` for this backend. |

Invariant: either `post_url` or `sha256(author_handle + normalized_text + visible_time)` must be available before downstream semantic extraction.

## 2. Dedup Key Generator

```python
def compute_social_post_dedup_key(
    *,
    canonical_post_url: str | None,
    author_handle: str,
    normalized_text: str,
    visible_time: str | None,
) -> tuple[str, str]:
    """Return (dedup_key, strategy).

    strategy is one of:
      - canonical_url
      - content_sha256
    """
```

Decision:

1. If `canonical_post_url` is present and well-formed, use `canonical_url:<url>`.
2. Otherwise use `content_sha256:<sha256(author_handle + normalized_text + visible_time)>`.
3. If URL and sha256 later disagree, sha256 wins identity and the latest canonical URL is stored as metadata.

## 3. DDL Diff

```sql
-- New table: browser/social dedup index.
CREATE TABLE IF NOT EXISTS social_post_dedup_keys (
  key TEXT PRIMARY KEY,
  strategy TEXT NOT NULL CHECK(strategy IN ('canonical_url', 'content_sha256')),
  post_pk INTEGER NOT NULL REFERENCES social_posts(id),
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  canonical_post_url TEXT,
  dom_hash TEXT,
  conflict_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_social_post_dedup_keys_post_pk
  ON social_post_dedup_keys(post_pk);

CREATE INDEX IF NOT EXISTS idx_social_post_dedup_keys_last_seen
  ON social_post_dedup_keys(last_seen_at);
```

```sql
-- Backward-compatible additions to existing social_posts.
ALTER TABLE social_posts ADD COLUMN dom_hash TEXT;
ALTER TABLE social_posts ADD COLUMN screenshot_path TEXT;
ALTER TABLE social_posts ADD COLUMN collection_backend TEXT;
ALTER TABLE social_posts ADD COLUMN dedup_key TEXT REFERENCES social_post_dedup_keys(key);
```

S03 implementation note: if the existing SQLite migration layer does not support repeated `ADD COLUMN`, guard each addition with schema introspection.

## 4. Migration Safety

| Change | Compatibility | Reason |
|---|---|---|
| `dom_hash TEXT NULL` | Safe | Legacy X API rows do not have DOM. |
| `screenshot_path TEXT NULL` | Safe | Only browser parse-fallback rows need screenshots. |
| `collection_backend TEXT NULL` | Safe | Legacy rows can be backfilled as `x_api` later. |
| `dedup_key TEXT NULL` | Safe | Existing rows can be mapped gradually. |
| `social_post_dedup_keys` new table | Safe | No existing reads depend on it. |

No `NOT NULL` should be added directly to existing `social_posts` columns during S03. Runtime validation may require `collection_backend` for new browser rows, but the storage migration must remain backward compatible.

## 5. Legacy X API Compatibility

- Existing X API token path remains optional and must write `collection_backend='x_api'` only when explicitly enabled.
- Legacy rows without `dom_hash` remain valid.
- Dedup compare during migration uses sha256 fallback to avoid URL-format mismatch between API and browser records.

## 6. Acceptance Map

| Acceptance | Status | Evidence |
|---|---|---|
| A-A2-1 | covered | §1 lists all 11 `post_record` fields with type and nullability. |
| A-A2-2 | covered | §2 defines dedup key function and canonical URL vs sha256 priority. |
| A-A2-3 | covered | §3 provides new table and `social_posts` DDL diff. |
| A-A2-4 | covered | §4 explains safe nullable migration and legacy compatibility. |
