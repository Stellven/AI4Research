# OpenSolar Public Release Checklist

The public release is an orphan-branch cut: a single squashed public tree with
no development history. This document is the owner sign-off checklist for that
cut. Ordinary cleanup work must not execute the orphan cut, push release refs,
or create a GitHub Release.

`scripts/release-cut.sh` defaults to a dry run. A dry run verifies the public
tree and history without changing refs.

---

## 1. Automated Release Gate

Expected dry-run command:

```bash
# gitleaks must be installed and on PATH; skipped gitleaks is not verified.
bash scripts/release-cut.sh --source HEAD --exclude-file release-exclude.txt
```

Expected result before owner approval:

```text
RELEASE-GATE VERDICT: PASS
```

The exclude file is intentional:

- `release-exclude.txt` excludes the remaining parked, non-installed files that
  should not ship in the public tree.
- `release-exclude.txt` also excludes itself, so the public tree does not expose
  release-engineering internals.
- Root `CLAUDE.md` is not excluded. It must remain a public, personal-data-free
  contributor guide.

The gate must verify:

- `WORKLOG.md` and `MIGRATION_PLAN.md` are absent from the public tree and the
  single-commit public history.
- The privacy scanner finds zero owner-identifying tokens in the release tree.
- Installed payload checks pass.
- gitleaks runs over the checked tree/history using `harness/gitleaks.toml`.
  If gitleaks is not available locally, mark this item **not verified** instead
  of treating it as a pass.
- Allowlist references are present; missing required allowlist entries block the
  cut.

Useful supporting checks:

```bash
git diff --check
bash scripts/check-privacy.sh
bash scripts/check-installed-clean.sh
bash scripts/smoke-install-matrix.sh minimal
bash scripts/check-harness-plumbing.sh
```

`scripts/check-harness-plumbing.sh` is deterministic harness plumbing smoke,
not live Claude behavior. It verifies install/layout/preflight/coordinator and
dispatch artifact plumbing without consuming Claude quota.

---

## 2. Owner Manual Checks

CI and local smoke cover the normal installer lifecycle, generated kernel
structure, doctor verdicts, uninstall cleanup, and deterministic harness
plumbing. Do not re-test those manually unless a gate points to a failure.

Manual checks that still require a real user environment:

| Check | Required confirmation |
|---|---|
| Kernel load | Open `claude`, approve the one-time `@~/.claude/solar/SOLAR.md` import, and confirm the kernel loads. |
| Product Delivery harness | Run `solar-harness start <workdir>`, confirm the `solar-harness` tmux session has the Product Delivery window and expected panes, start/trust Claude in each pane, and confirm one real delegation result. |
| Claude quota/auth boundary | If Claude is rate-limited or unauthenticated, record this as manual-blocked/auth-quota-blocked. Do not mark live Claude verified. |
| Daemon start | On real macOS launchd and systemd-user Linux/WSL2, confirm the daemon starts and stays up. |
| mempalace heavy deps | Install `mempalace` without deps-light skips and run a venv import smoke. |
| Windows WSL2 | Run `install.ps1` end to end on Win11, including the one admin approval, reboot if required, and Linux lifecycle inside the provisioned WSL2 distro. |
| Release URLs | Confirm `get-solar.sh` stable channel and `install.ps1 -BootstrapUrl` point to the final public release asset. |

Current manual blockers:

- Live Claude panes and real delegation result are not verified while Claude
  quota/auth is unavailable.
- The orphan cut, release branch push, tag push, and GitHub Release remain owner
  actions only.

---

## 3. Owner Cut Procedure

Run only after the automated gate passes and the owner gives go-ahead:

```bash
bash scripts/release-cut.sh --source HEAD --branch release/v1 \
  --exclude-file release-exclude.txt --execute
```

Then the owner reviews the orphan tree, pushes only the intended release branch
and tag, and creates the GitHub Release with the finalized bootstrap assets.

---

## 4. Sign-Off

| Item | Owner | Date | Result |
|---|---|---|---|
| Release gate PASS with gitleaks actually run | | | [ ] |
| Root public docs reviewed | | | [ ] |
| Kernel load manual check | | | [ ] |
| Product Delivery live Claude + real delegation manual check | | | [ ] |
| macOS daemon check | | | [ ] |
| Linux/WSL2 daemon check | | | [ ] |
| mempalace heavy-deps check | | | [ ] |
| Win11 + WSL2 E2E | | | [ ] |
| Release URLs finalized | | | [ ] |
| Orphan cut created, reviewed, and published by owner | | | [ ] |
