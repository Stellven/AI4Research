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

## Windows (`.exe`)
1. Run the installer. Windows SmartScreen shows *"Windows protected your PC… Publisher: Unknown."*
2. Click **More info → Run anyway**, then finish the install. Solar launches from the Start menu.

> Windows runs Solar's engine inside **WSL2**. If you haven't set it up, run `install.ps1` first
> (it installs WSL2 + the runtime and registers login-autostart).

## Linux (`.AppImage`)
```sh
chmod +x Solar-*.AppImage && ./Solar-*.AppImage
```

---
Once allowed, Solar opens normally on every launch — the runtime auto-starts in the background and the
dashboard loads. If something looks wrong, use **Help → Copy diagnostics** in the app to grab a local
(no-telemetry) report.
