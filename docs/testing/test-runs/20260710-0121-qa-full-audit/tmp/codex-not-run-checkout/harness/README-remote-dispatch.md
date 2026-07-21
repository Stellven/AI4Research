# Solar Remote Dispatch

`solar-remote-dispatch` sends a local Solar Harness sprint to a remote Mac mini,
verifies file checksums before waking the remote harness, and pulls remote
evidence back to the local machine.

## Configure

Use one of these options. CLI flags override environment variables, which
override the config file.

```json
{
  "remote_user": "user",
  "remote_host": "host-or-ip",
  "remote_path": "~"
}
```

Save the config as `~/.solar/remote-config.json`, or set:

```bash
export SOLAR_REMOTE_USER=user
export SOLAR_REMOTE_HOST=host-or-ip
export SOLAR_REMOTE_PATH=~
```

## Doctor

```bash
solar-remote-dispatch doctor --json
solar-remote-dispatch doctor --host user@host --json
```

The doctor reports `ssh`, `rsync`, remote harness presence, remote version,
remote tmux session, remote panes, and last sync timestamp.

## Dispatch

```bash
solar-remote-dispatch dispatch sprint-20260510-example
solar-remote-dispatch dispatch --force --host user@host sprint-20260510-example
```

Dispatch behavior:

1. Generate a manifest for sprint files.
2. Compute SHA-256 checksums.
3. Copy files to the remote harness.
4. Verify remote checksums.
5. Wake the remote Solar Harness only after checksum verification passes.
6. Record the local dispatch in `~/.solar/state/remote-sprints.jsonl`.

Repeated dispatch of the same `sprint_id + manifest_sha256` is idempotent.
Use `--force` only when you intentionally want to re-wake the same sprint.

## Pull Status

```bash
solar-remote-dispatch pull sprint-20260510-example
solar-remote-dispatch pull --host user@host sprint-20260510-example
```

Pull fetches remote `status.json`, `events.jsonl`, `task_graph.json`,
`handoff.md`, `eval.md`, and `eval.json`. Pulled status files are annotated with
the source host and pull timestamp.

## Recovery

- If `doctor` reports SSH failure, fix network/VPN/Tailscale/firewall first.
- If checksum verification fails, do not wake the sprint. Re-run dispatch after
  fixing sync.
- If a remote pane is busy, leave the sprint queued or use the remote harness
  status UI to inspect pane ownership.
- If pull returns partial files, inspect the remote sprint directory and rerun
  `pull` after the remote evaluator finishes.

## Security

Remote dispatch copies sprint artifacts only. It must not copy API keys, OAuth
tokens, Google credentials, or `.env` secrets. Keep secrets configured
independently on each machine.
