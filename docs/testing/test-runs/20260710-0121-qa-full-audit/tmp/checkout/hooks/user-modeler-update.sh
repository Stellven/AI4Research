#!/bin/bash
# Solar User Profile Auto-Updater
# SessionEnd hook: 会话结束时自动更新用户画像
#
# 触发: SessionEnd
# 行为: 调用 bun user-modeler.ts 重建画像 (覆盖 ~/.solar/user-profile.json)
# 下次 SessionStart 时 user-profile-inject.sh 会读到最新数据
#
# @module solar-farm/user-modeler-update

set -u

# 消耗 stdin
cat > /dev/null 2>&1 || true

BUN="$(which bun 2>/dev/null || true)"
if [[ -z "$BUN" ]]; then
    exit 0
fi

# 静默更新，不阻塞会话结束
"$BUN" run "$HOME/.claude/core/solar-farm/user-modeler.ts" >/dev/null 2>&1 &

exit 0
