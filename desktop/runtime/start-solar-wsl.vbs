' Solar — bring WSL2 up and prewarm the complete product runtime at logon, with NO visible console.
' Launched by wscript.exe (a GUI-subsystem host) so the console-subsystem wsl.exe does
' not flash a window. Run window-style 0 = hidden, async (False = don't wait).
' Any "wsl.exe -d <distro> -- ..." call boots the (cold) WSL VM; the systemctl nudge then
' starts the per-user service, which also autostarts on its own via systemd + enable-linger.
Option Explicit
Dim distro, sh, cmd
distro = "Ubuntu-24.04"
If WScript.Arguments.Count >= 1 Then distro = WScript.Arguments(0)
Set sh = CreateObject("WScript.Shell")
cmd = "set -e; mkdir -p ~/.solar/workspace ~/.solar/logs; " & _
      "systemctl --user start solar-status-server.service 2>/dev/null || true; " & _
      "env SOLAR_PRODUCT_MODE=1 SOLAR_PANE_RUNTIME=codex SOLAR_PM_DEFAULT_PROVIDERS=openai SOLAR_MULTI_TASK_DEFAULT_PROVIDERS=openai " & _
      "bash ~/.solar/harness/solar-harness.sh start ~/.solar/workspace --skip-doctor >>~/.solar/logs/prewarm.log 2>&1"
sh.Run "wsl.exe -d " & distro & " -- bash -lc """ & cmd & """", 0, False
