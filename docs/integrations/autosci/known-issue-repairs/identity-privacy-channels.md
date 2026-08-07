# Identity, privacy, and channels repair evidence

## Boundary

| Scope | Result |
| --- | --- |
| Repo-owned local service | `PASS`: registration, login, profile, logout, stale-session rejection, credential add/use/revoke, privacy lifecycle, and controlled adapter delivery are implemented. |
| Hosted account | `NOT_AVAILABLE`: the service returns `hosted_account_not_available`; it does not simulate a hosted backend. |
| Discord / WeChat live platform | `ENVIRONMENT_BLOCKED`: no real credential, account, allowlist, or operator authorization was provided. The contract deliberately does not claim live delivery. |
| Discord / WeChat repo adapter | `PASS`: a controlled local server proves authentication, delivery, one transient retry, delivery-ID deduplication, account isolation, and revoked-credential refusal. |

## Contract and safety properties

- `harness/lib/identity/service.py` requires an explicit absolute `--home`; it never derives or opens a real user home.
- Passwords, session tokens, and provider secrets are PBKDF2-hashed at rest. Audit records retain only event metadata and credential fingerprints; the service suppresses HTTP request logging so `Authorization` is not emitted.
- Profile routes are owner-only. A session for another user receives `cross_account_access`; a logged-out or expired token receives `invalid_session`.
- Credentials are provider-scoped and verified for every controlled delivery. Revocation is durable and makes an old credential fail with `revoked_credential`.
- `export` and `backup` produce redacted files only inside the explicit sandbox. `redact` operates in memory. `delete` and `uninstall` remove product-owned `primary`, `cache`, `index`, `logs`, `derived`, and `backups` surfaces.

## Executed evidence

Command (run with a worktree-local uv cache, not a user home):

```powershell
$env:UV_CACHE_DIR = (Join-Path (Get-Location) '.codex-tmp\\uv-cache')
$env:UV_TOOL_DIR = (Join-Path (Get-Location) '.codex-tmp\\uv-tools')
uv run --python 'C:\\Users\\j50058254\\AppData\\Roaming\\uv\\python\\cpython-3.11.15-windows-x86_64-none\\python.exe' --with pytest pytest tests/repairs/identity_privacy_channels/test_identity_privacy_channel_service.py -q --basetemp .codex-tmp/identity-privacy-channels-pytest --cache-clear
```

Result: `3 passed in 7.96s`.

The black-box tests start the production HTTP service in an explicit temporary sandbox and cover: hosted-account rejection; register/login/profile/logout; stale sessions; cross-user reads; credential use/revocation; controlled Discord delivery retry/dedup; external-platform limitation status; export/backup/redaction; and delete/uninstall residue checks across all six data surfaces.
