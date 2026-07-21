#!/bin/bash
# SMA Auto-Consolidate Hook
# 自动触发知识固化 (L2 → L3)
# Hook 类型: SessionEnd
#
# 功能:
# 1. 会话结束时自动调用 triggerConsolidation()
# 2. 每天首次运行时调用 cleanupExpiredTriples()

set -euo pipefail

# 配置
MEMORY_CONTROLLER="$HOME/.claude/core/sma/memory-controller.ts"
LAST_CLEANUP_FILE="$HOME/.solar/sma-last-cleanup.txt"
CLEANUP_INTERVAL_SECONDS=$((24 * 3600))  # 24 hours

# 获取当前会话 ID
# Claude Code 会话 ID 通过 PROJECT_ID 环境变量传递
SESSION_ID="${CLAUDE_PROJECT_ID:-unknown}"

# 如果会话 ID 不可用，尝试从当前目录推断
if [ "$SESSION_ID" = "unknown" ]; then
    # 从当前工作目录路径提取
    PROJECT_PATH="${PWD}"
    SESSION_ID=$(basename "$PROJECT_PATH" 2>/dev/null || echo "default")
fi

echo "🧠 SMA Auto-Consolidate Hook"
echo "Session ID: $SESSION_ID"

# 检查 memory-controller.ts 是否存在
if [ ! -f "$MEMORY_CONTROLLER" ]; then
    echo "⚠️  memory-controller.ts not found, skipping consolidation"
    exit 0
fi

# 1. 导入对话历史到 L2 session_log
echo "📝 Importing conversation history to L2..."

# 创建临时脚本导入对话历史
TEMP_IMPORT=$(mktemp /tmp/sma-import-XXXXXX.ts)
cat > "$TEMP_IMPORT" <<EOF
import { Database } from 'bun:sqlite';
import { logTurn } from '$MEMORY_CONTROLLER';
import path from 'path';
import fs from 'fs';

const sessionId = '$SESSION_ID';
const projectPath = '$HOME/.claude/projects';

// 查找当前会话的 JSONL 文件
let jsonlPath: string | null = null;
try {
  const files = fs.readdirSync(projectPath, { recursive: true, encoding: 'utf-8' });
  for (const file of files) {
    if (typeof file === 'string' && file.includes(sessionId) && file.endsWith('.jsonl')) {
      jsonlPath = path.join(projectPath, file);
      break;
    }
  }
} catch (e) {
  console.log('No JSONL file found for this session');
}

if (!jsonlPath || !fs.existsSync(jsonlPath)) {
  console.log('ℹ️  No conversation history file found, skipping import');
  process.exit(0);
}

// 读取并解析 JSONL
const content = fs.readFileSync(jsonlPath, 'utf-8');
const lines = content.trim().split('\n');
let imported = 0;

// 解析 Claude Code JSONL 格式
const userMessages: any[] = [];
const assistantMessages: any[] = [];

for (const line of lines) {
  try {
    const obj = JSON.parse(line);
    if (obj.type === 'user' && obj.message?.role === 'user') {
      userMessages.push(obj);
    } else if (obj.type === 'assistant' && obj.message?.role === 'assistant') {
      assistantMessages.push(obj);
    }
  } catch (e) {
    // 跳过无法解析的行
  }
}

// 配对用户消息和 AI 响应
const minTurns = Math.min(userMessages.length, assistantMessages.length);
for (let i = 0; i < minTurns; i++) {
  const userMsg = userMessages[i];
  const assistantMsg = assistantMessages[i];

  const userContent = userMsg.message.content;
  const assistantContent = assistantMsg.message.content;

  const userInput = typeof userContent === 'string' ? userContent : JSON.stringify(userContent);
  const aiOutput = typeof assistantContent === 'string' ? assistantContent : JSON.stringify(assistantContent);

  // 写入 session_log
  await logTurn({
    sessionId,
    turnId: i + 1,
    userInput,
    aiOutput,
    metadata: {
      timestamp: new Date(userMsg.timestamp).getTime(),
      userUuid: userMsg.uuid,
      assistantUuid: assistantMsg.uuid
    }
  });
  imported++;
}

console.log(\`✅ Imported \${imported} conversation turns to L2\`);
EOF

# 执行导入脚本
bun run "$TEMP_IMPORT" 2>&1 || echo "⚠️  Import failed, continuing..."
rm -f "$TEMP_IMPORT"

# 2. 触发知识固化 (L2 → L3)
echo "📚 Triggering knowledge consolidation..."

# 创建临时脚本
TEMP_SCRIPT=$(mktemp /tmp/sma-consolidate-XXXXXX.ts)
cat > "$TEMP_SCRIPT" <<EOF
import { triggerConsolidation } from '$MEMORY_CONTROLLER';
(async () => {
    try {
        const sessionId = '$SESSION_ID';
        const count = await triggerConsolidation(sessionId, { minTurns: 3 });
        console.log(\`✅ Consolidated \${count} knowledge triples\`);
    } catch (error: any) {
        console.error('❌ Consolidation failed:', error.message);
        process.exit(1);
    }
})();
EOF

if bun run "$TEMP_SCRIPT"; then
    echo "✅ Knowledge consolidation completed"
else
    echo "❌ Knowledge consolidation failed"
fi
rm -f "$TEMP_SCRIPT"

# 2. 定期清理过期知识 (每天一次)
CURRENT_TIME=$(date +%s)
SHOULD_CLEANUP=false

if [ -f "$LAST_CLEANUP_FILE" ]; then
    LAST_CLEANUP=$(cat "$LAST_CLEANUP_FILE")
    TIME_SINCE_CLEANUP=$((CURRENT_TIME - LAST_CLEANUP))

    if [ "$TIME_SINCE_CLEANUP" -ge "$CLEANUP_INTERVAL_SECONDS" ]; then
        SHOULD_CLEANUP=true
    fi
else
    # 首次运行，执行清理
    SHOULD_CLEANUP=true
fi

if [ "$SHOULD_CLEANUP" = true ]; then
    echo "🧹 Cleaning up expired knowledge triples..."

    TEMP_CLEANUP=$(mktemp /tmp/sma-cleanup-XXXXXX.ts)
    cat > "$TEMP_CLEANUP" <<EOF
import { cleanupExpiredTriples } from '$MEMORY_CONTROLLER';
(async () => {
    try {
        const count = await cleanupExpiredTriples(7776000, 0.7);
        console.log(\`✅ Cleaned up \${count} expired triples\`);
    } catch (error: any) {
        console.error('❌ Cleanup failed:', error.message);
        process.exit(1);
    }
})();
EOF

    if bun run "$TEMP_CLEANUP"; then
        echo "✅ Knowledge cleanup completed"
        echo "$CURRENT_TIME" > "$LAST_CLEANUP_FILE"
    else
        echo "❌ Knowledge cleanup failed"
    fi
    rm -f "$TEMP_CLEANUP"
else
    HOURS_UNTIL_NEXT=$((($CLEANUP_INTERVAL_SECONDS - TIME_SINCE_CLEANUP) / 3600))
    echo "ℹ️  Next cleanup in ~${HOURS_UNTIL_NEXT}h"
fi

echo "🎯 SMA auto-consolidation completed"
exit 0
