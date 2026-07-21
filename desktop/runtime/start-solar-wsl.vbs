' Solar — bring WSL2 up and start the status-server at logon, with NO visible console.
' Launched by wscript.exe (a GUI-subsystem host) so the console-subsystem wsl.exe does
' not flash a window. Run window-style 0 = hidden, async (False = don't wait).
' Any "wsl.exe -d <distro> -- ..." call boots the (cold) WSL VM; the systemctl nudge then
' starts the per-user service, which also autostarts on its own via systemd + enable-linger.
Option Explicit
Dim distro, sh
distro = "Ubuntu-24.04"
If WScript.Arguments.Count >= 1 Then distro = WScript.Arguments(0)
Set sh = CreateObject("WScript.Shell")
sh.Run "wsl.exe -d " & distro & " -- bash -lc ""systemctl --user start solar-status-server.service 2>/dev/null || true""", 0, False
