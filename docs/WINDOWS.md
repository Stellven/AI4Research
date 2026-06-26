# OpenSolar on Windows (WSL2)

Native (non-WSL) Windows is out of scope. The Windows runtime path is WSL2,
auto-provisioned by `install.ps1`.

**Status: experimental.** The WSL2 path is implemented and covered by deterministic
gates (WSL-detection logic, backend contract, dashboard render) plus code review, but
full first-run verification on real Windows hardware is owner-manual. The desktop app
(`Solar.exe`) runs this same bootstrap automatically on first launch — see
[desktop/docs/DOWNLOAD.md](../desktop/docs/DOWNLOAD.md).

## Quick start

From an elevated or normal PowerShell:

```powershell
./install.ps1 --yes --components kernel,harness
```

- If WSL2 is **absent**, the script self-elevates, runs `wsl --install -d
  Ubuntu-24.04 --no-launch`, and registers a RunOnce continuation. **One
  manual step remains: approve the admin prompt and reboot once.** After the
  reboot the installer resumes automatically and finishes inside WSL.
- If WSL2 is **present**, it ensures the distro + systemd are ready and runs
  the Linux installer inside WSL with your flags passed through unchanged.

All `--*` flags and `SOLAR_*` env twins behave exactly as on macOS/Linux.

## systemd / daemons

The `daemons` component needs systemd. `install.ps1` enables it
(`/etc/wsl.conf` `[boot] systemd=true` + `wsl --shutdown`) when required. For a
daemon that survives logout, inside WSL run: `loginctl enable-linger $USER`.

## Capability table

| Capability | Status on WSL2 |
|---|---|
| kernel / rules / hooks overlay | full |
| core-runtime (daemon + web dashboard) | full |
| harness (python) | full |
| skills (md / office / obsidian / browser) | full |
| skills-calendar | unavailable (darwin-only) |
| daemons | full (systemd enabled by the installer) |

## The one manual step (release checklist)

On a clean Windows 11 host:
1. Run `install.ps1` (no WSL2 present).
2. Approve the UAC prompt.
3. Reboot when prompted (the single documented reboot).
4. Confirm the installer resumes via RunOnce and completes inside WSL.
5. `wsl -d Ubuntu-24.04 -- ~/.solar/bin/solar doctor --json` → verdict ok.

This end-to-end run is owner-held (GitHub runners lack nested virtualization).
