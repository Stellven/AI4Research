#!/bin/bash
# ── osascript-notify.sh ──
# Sprint sprint-20260418-065436, D1: macOS 桌面通知
#
# 用法: osascript-notify.sh <title> <message> [sound]
# sound: Glass (默认) | Ping | Blow | Pop | Purr | none
# 容错: macOS 未授权通知时不报错

set -uo pipefail

TITLE="${1:-Solar Harness}"
MESSAGE="${2:-Notification}"
SOUND="${3:-Glass}"

if [[ "$SOUND" == "none" ]]; then
  osascript -e "display notification \"${MESSAGE}\" with title \"${TITLE}\"" 2>/dev/null || true
else
  osascript -e "display notification \"${MESSAGE}\" with title \"${TITLE}\" sound name \"${SOUND}\"" 2>/dev/null || true
fi

exit 0
