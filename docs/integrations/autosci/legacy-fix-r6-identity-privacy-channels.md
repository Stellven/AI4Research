# Legacy Fix R6 Identity, Privacy, and Channels

Baseline: `6a96d40153b919d97a2018c8267d7796d5e3e1d5`

Branch/worktree: `codex/legacy-fix-r6-identity` at `.legacy-fix-worktrees/r6-identity`

## Product Boundary Decision

OpenSolar still does not have a hosted Solar product-account identity backend. The Account Registration L2 must not be marked resolved from this repair: external Codex/Claude provider auth, local install config, and the new local-only identity store are not verified Solar cloud accounts.

This repair implements a local-only identity/privacy control surface for Solar-owned local data:

- `solar identity register --local-only`
- `solar identity login`
- `solar identity session`
- `solar identity logout`
- `solar identity profile get|set`
- `solar privacy export|redact|delete`
- `solar channel status|route`

## Security Properties

- Passwords are never stored in plaintext. The local store uses PBKDF2-HMAC-SHA256 with random salts and at least 260,000 iterations.
- Session tokens are returned once to the caller and stored only as SHA-256 hashes.
- Sessions carry an expiry timestamp; expired or logged-out tokens are rejected.
- Profile writes are scoped to the authenticated local account owner.
- Privacy export emits redacted data and omits password/session material.
- Privacy delete removes the local account, profile, and sessions, leaving only non-sensitive hashed audit tombstones.
- The identity store lives under `SOLAR_HOME/identity/local-accounts.json`, is sandboxable, and is included in `solar backup` and `solar uninstall --keep-data`.

## Channel Boundary

WeChat remains limited to the existing Apple Notes authorized-content bridge for `mp.weixin.qq.com` article URLs. This is not a WeChat account login, bot, Mini Program, clipboard, or arbitrary channel connector.

Discord remains provider-gated. The adapter reports missing provider prerequisites and refuses live routing without claiming a live pass.

## L2 Disposition

- Account Registration: still not resolved as product-account registration. Local-only registration exists for Solar-owned local privacy controls.
- Authentication & Session Security: local-only session path added and covered by production-path tests; provider auth remains external.
- User Profile Management: local profile ownership path added and covered by owner-token tests.
- Privacy / Personal Data Controls: local export, redaction, delete, backup, and uninstall retention paths are covered for Solar-owned sandbox data.
- Authorized Distribution, Knowledge Transfer & Lifecycle Closure: covered only for local backup/export/delete/uninstall lifecycle, not cloud/provider revocation.
- Wechat: adapter contract and Apple Notes bridge route only; no live account claim.
- Discord: explicit provider gate and safe refusal only; no live account claim.
