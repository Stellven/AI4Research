# Solar Public Release Checklist

The public release is an **orphan-branch cut**: a single squashed commit of the
current tree with **no development history** ("show day 100, not the history").
This checklist is the owner's sign-off for that cut and the fresh-VM
verification that must pass before it ships.

Nothing here is executed automatically. `scripts/release-cut.sh` defaults to a
dry run that never touches refs and never pushes; the cut and the public
repo/GitHub Release are manual owner steps.

---

## Phase A — Pass the release gate (automated, repeatable)

Run the dry run (verifies the public tree + history without changing anything):

```bash
# gitleaks must be on PATH for the history scan
./scripts/release-cut.sh --source HEAD
```

The gate checks:

1. **WORKLOG.md / MIGRATION_PLAN.md** absent from the public tree AND its
   single-commit history. *(Currently PASS — both are untracked/ignored; the
   dev range `ec07779..0e2b431` that carried them tracked is dropped by the
   orphan cut.)*
2. **Personal/persona tokens ZERO** — owner-identifying home paths and account
   handles, LAN IPs, and the secretary/guardian persona proper nouns. The exact
   token set is defined in `scripts/release-cut.sh` (the `LICENSE` copyright
   name is allowlisted).
3. **Architectural names** — reported, allowlist-aware (`solar-farm`/`gstack`
   inside `harness/`+`core/` internals are the tolerated out-of-scope residue).
4. **gitleaks over full history** clean (uses `harness/gitleaks.toml`).
   *(Currently PASS.)*

### Current dry-run state (resolve before cutting)

The dry run currently returns **FAIL** on check 2 — by design, it surfaces what
must be excluded or scrubbed. As of this writing:

- **~102 personal/persona token hits** across the dev corpus: the contributor
  `CLAUDE.md`, `SPRINTS-HIGHLIGHTS.md`, `TRIGGERS.md`, the parked `rules/`
  (delegate-*, solar-protocol, mempalace-diary, …), parked `agents/`, the
  `docs/` design reports, and unshipped `hooks/`.
- **36 files** carry architectural names outside the harness/core allowlist
  (parked rules/agents/docs, the contributor `CLAUDE.md`, `kernel/base-rules.txt`
  comment, etc.).
- **Shipped-code personal residue (decide explicitly — recommend scrubbing):**
  - `core/notify/ntfy.ts` — a personal default ntfy topic embedded in core
    runtime code.
  - `core/ontology/schema.sql` — still seeds the author handle as the guardian
    identity. *(The installed copy `core/db/schema/59-ontology-v1-compat.sql`
    was already neutralized to a neutral default; this is the un-consolidated
    source.)*
  - `data/usage-stats.json` — the author's personal project paths (dev data;
    recommend exclude).
  - `harness/scripts/browser_agent_chatgpt_wrapper.py` — the author's profile
    name in a UI-detection string.

**Owner decision per item: exclude or scrub.** Two mechanisms:

- *Exclude* — list paths/globs in a file and pass `--exclude-file`:
  ```bash
  ./scripts/release-cut.sh --source HEAD --exclude-file release-exclude.txt
  ```
  Likely exclude candidates for a clean public tree: the parked dev corpus
  (`docs/` design reports, parked `agents/`, parked `rules/`, unshipped
  `hooks/`, `data/usage-stats.json`, `SPRINTS-HIGHLIGHTS.md`, `TRIGGERS.md`).
- *Scrub* — neutralize the token in place (for content that should ship, e.g.
  `core/notify/ntfy.ts`, and the contributor `CLAUDE.md` if it ships).

Re-run the dry run until it returns **PASS**.

---

## Phase B — Cut the orphan branch (owner, after go-ahead)

```bash
# Creates the local orphan branch only. Refuses unless the gate PASSES.
# Does NOT push and does NOT create any public repo or release.
./scripts/release-cut.sh --source HEAD --branch release/v1 \
    --exclude-file release-exclude.txt --execute
```

Then, manually:

1. Review the orphan tree (`git checkout release/v1`).
2. Finalize the release URLs (currently owner-pending):
   - `get-solar.sh` channel — set the `stable` tag/branch the bootstrap clones.
   - `install.ps1` `-BootstrapUrl` — the GitHub Release `get-solar.sh` asset URL.
3. Push `release/v1` (and a version tag) to the public repo.
4. Cut the **GitHub Release** with `get-solar.sh` attached as an asset.

---

## Phase C — Fresh-VM verification matrix (owner sign-off)

Run the full lifecycle on each clean target. Each row must pass end to end.

| Step | macOS | Ubuntu 24.04 | Win11 + auto-provisioned WSL2 |
|---|---|---|---|
| Clone the public release / `curl get-solar.sh` | ☐ | ☐ | ☐ (`install.ps1`) |
| Interactive install (defaults) | ☐ | ☐ | ☐ |
| `solar doctor` → verdict ok | ☐ | ☐ | ☐ |
| Open `claude`, **kernel-load**: approve the one-time `@~/.claude/solar/SOLAR.md` import; confirm kernel content loads | ☐ | ☐ | ☐ |
| Trigger a session-start hook | ☐ | ☐ | ☐ |
| **Web dashboard** serves (core-runtime) | ☐ | ☐ | ☐ |
| **daemon-start**: real `launchctl` (macOS) / `systemctl --user` (Linux/WSL2) loads + runs the daemon | ☐ | ☐ | ☐ |
| **mempalace heavy-deps**: install `mempalace` with deps NOT skipped (full chromadb + sentence-transformers venv) + a venv import smoke | ☐ | ☐ | ☐ |
| `solar update` no-op round-trip | ☐ | ☐ | ☐ |
| `solar uninstall` | ☐ | ☐ | ☐ |
| `~/.claude/CLAUDE.md` byte-identical to pre-install backup; no `~/.solar`; `launchctl list` / `systemctl --user` clean | ☐ | ☐ | ☐ |

Windows-specific (covered by the WSL2 column, called out for the owner):

- **Windows E2E**: run `install.ps1` end to end on Win11, including the single
  admin approval + one reboot (RunOnce continuation), then the lifecycle above
  inside the auto-provisioned WSL2 Ubuntu-24.04.
- Confirm `-BootstrapUrl` resolves (the GitHub Release `get-solar.sh` asset must
  exist — Phase B step 4).

> CI cannot perform these: GitHub runners lack nested virt (no live WSL2),
> have no interactive `claude` import, no user-session `launchctl`/`systemd`,
> and mempalace deps are multi-GB (CI is deps-light by ratified policy).

---

## Sign-off

| Item | Owner | Date | Result |
|---|---|---|---|
| Release gate PASS (`release-cut.sh` dry run) | | | ☐ |
| Orphan cut created + pushed; GitHub Release with `get-solar.sh` | | | ☐ |
| macOS fresh-VM matrix | | | ☐ |
| Ubuntu 24.04 fresh-VM matrix | | | ☐ |
| Win11 + WSL2 E2E | | | ☐ |
| **v1 approved for public release** | | | ☐ |
