# Uninstalling Solar

Solar uninstalls cleanly and is receipt-driven: it removes exactly what the
installer recorded in `~/.solar/install-receipt.json`, restores your
`~/.claude/CLAUDE.md`, and leaves no residue. See [`INSTALL.md`](../INSTALL.md)
for installation.

---

## Quick uninstall

```bash
~/.solar/bin/solar uninstall --yes
```

`--yes` is required (the command refuses to run without it). This removes the
full install. To preview first, see *Dry run* below.

---

## What gets removed

`solar uninstall` performs, in order:

1. **CLAUDE.md sentinel** — removes the `<!-- BEGIN OPENSOLAR -->` … `<!-- END
   OPENSOLAR -->` block from `~/.claude/CLAUDE.md`, leaving the rest of your
   file byte-for-byte intact. If the file becomes empty, it is removed.
2. **settings.json hooks** — strips only the Solar hook entries (identified by
   the `/solar/hooks/` command-path prefix). Your own hooks and other settings
   are preserved; if nothing else remains, the file is removed.
3. **Daemons** — stops and removes any user-level service Solar registered
   (`launchctl unload` on macOS, `systemctl --user disable --now` on
   Linux/WSL2), then removes the service file. Best-effort: a missing service
   manager is not fatal.
4. **MCP servers** — runs `claude mcp remove <name>` for each server Solar
   registered (via the recorded list), when the `claude` CLI is present.
5. **Installed skills** — removes only the skill directories Solar recorded
   under `~/.claude/skills/`, then removes `~/.claude/skills` if it is empty.
6. **Kernel assets** — removes `~/.claude/solar/`, and `~/.claude` itself if it
   is now empty.
7. **Runtime root** — removes `~/.solar/` (unless `--keep-data`, below).

---

## Keep your data

```bash
~/.solar/bin/solar uninstall --yes --keep-data
```

`--keep-data` removes the installed code (`bin/`, `harness/`, `core/`,
`codex-bridge/`, `mempalace/`, `venv/`) but preserves your data under
`~/.solar/`:

- `install-receipt.json`
- `config.env` (machine config)
- `.env` (secrets, mode `0600`)
- `db/` (the runtime database)

This is the right choice if you intend to reinstall and keep your database,
configuration, and secrets.

---

## Dry run

```bash
~/.solar/bin/solar uninstall --yes --dry-run
```

Prints what would be removed (under `~/.solar` and `~/.claude/solar`) and exits
without changing anything.

---

## Back up before removing

To archive your data first (config + secrets + receipt + database):

```bash
~/.solar/bin/solar backup --out ~/solar-backup.tar.gz
# later, after reinstalling:
~/.solar/bin/solar restore ~/solar-backup.tar.gz
```

---

## Verify a clean uninstall

```bash
test ! -d ~/.solar && echo "runtime removed"
test ! -d ~/.claude/solar && echo "kernel assets removed"
# Your CLAUDE.md should match its pre-install state (sentinel block gone):
grep -c "BEGIN OPENSOLAR" ~/.claude/CLAUDE.md 2>/dev/null || echo "no sentinel"
# Daemons gone:
launchctl list 2>/dev/null | grep -i solar || echo "no launchd residue"
systemctl --user list-units 2>/dev/null | grep -i solar || echo "no systemd residue"
```

A fully clean uninstall leaves your `~/.claude/CLAUDE.md` byte-identical to its
pre-install backup, no `~/.solar`, and no Solar daemons registered.
