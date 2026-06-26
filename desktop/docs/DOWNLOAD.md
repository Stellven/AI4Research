# Installing Solar (unsigned builds)

Solar's desktop app isn't code-signed yet, so macOS and Windows will warn the **first** time
you open it. This is expected for an unsigned app — here's how to allow it (one time).

## macOS (`.dmg`)
1. Open the `.dmg`, drag **Solar** into **Applications**.
2. First launch is blocked ("Apple could not verify… / unidentified developer"):
   - **macOS Sonoma (14) or earlier:** Control-click (right-click) **Solar** in Applications → **Open** → **Open**.
   - **macOS Sequoia (15) or later:** the right-click shortcut was removed. Open Solar once (it gets blocked), then
     go to **System Settings → Privacy & Security**, scroll to the bottom, and click **"Open Anyway"** → authenticate.
   - **Terminal escape hatch (any version):** `xattr -dr com.apple.quarantine /Applications/Solar.app`
3. You only need to do this once.

> Solar's runtime needs **Homebrew Python 3.11+** on macOS. If prompted, install it with `brew install python@3.11`.

The app starts the runtime on launch, and the in-app **Install** button now also sets up auto-start.
To enable it manually (so the runtime is already running before you open the app, and survives
logout), install the `status-daemon` component — either with the full installer:
```sh
./install.sh --components kernel,harness,status-daemon
```
or, if the runtime is already installed, the standalone helper:
```sh
bash desktop/runtime/install-macos-agent.sh   # registers the launchd LaunchAgent
```

## Windows (`.exe`)
1. Run **Solar.exe** — it's a portable app, so there's nothing to install. Windows SmartScreen
   shows *"Windows protected your PC… Publisher: Unknown."*
2. Click **More info → Run anyway**.
3. On first launch, if WSL2 isn't set up yet, Solar offers to do it for you: click **Set up Solar**,
   approve the one Windows prompt, and let your PC reboot once. Solar resumes and finishes setup
   on its own, then the dashboard opens.

> Windows runs Solar's engine inside **WSL2**, and the app installs it for you on first launch — you
> no longer need to run `install.ps1` by hand. (`install.ps1` is still available for a fully manual or
> CI/unattended install; see the repo's `docs/WINDOWS.md`.)

## Linux (`.AppImage`)
```sh
chmod +x Solar-*.AppImage && ./Solar-*.AppImage
```

The app starts the runtime on launch. To also have the runtime **auto-start at login** (so it's
already running before you open the app, and survives logout), install the `status-daemon`
component — either with the full installer:
```sh
./install.sh --components kernel,harness,status-daemon
```
or, if the runtime is already installed, the standalone helper:
```sh
bash desktop/runtime/install-linux-service.sh   # systemd --user; runs loginctl enable-linger for you
```

---
Once allowed, Solar opens normally on every launch — the runtime auto-starts in the background and the
dashboard loads. If something looks wrong, use **Help → Copy diagnostics** in the app to grab a local
(no-telemetry) report.
