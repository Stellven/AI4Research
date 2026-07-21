#!/bin/bash
# Post Tool Use Dispatcher - 解决 stdin 只能读一次的问题
# 原理: 把 stdin 保存到临时文件，然后传给各个子 hook

set -e

# 读取 stdin 到临时文件
TEMP_FILE=$(mktemp /tmp/post-tool-input.XXXXXX)
cat > "$TEMP_FILE"

# 按顺序调用各个 hook，每个都能读到完整数据
HOOKS_DIR="$HOME/.claude/hooks"

# 1. 遥测数据 (tel_operations)
if [ -x "$HOOKS_DIR/telemetry-hook.sh" ]; then
    cat "$TEMP_FILE" | "$HOOKS_DIR/telemetry-hook.sh" 2>/dev/null || true
fi

# 2. 轨迹记录 (evo_tool_calls)
if [ -x "$HOOKS_DIR/trajectory-db-writer.sh" ]; then
    cat "$TEMP_FILE" | "$HOOKS_DIR/trajectory-db-writer.sh" 2>/dev/null || true
fi

# 3. 反馈收集
if [ -x "$HOOKS_DIR/feedback-collector.sh" ]; then
    cat "$TEMP_FILE" | "$HOOKS_DIR/feedback-collector.sh" 2>/dev/null || true
fi

# 4. REE 注册
if [ -x "$HOOKS_DIR/ree-register-hook.sh" ]; then
    cat "$TEMP_FILE" | "$HOOKS_DIR/ree-register-hook.sh" 2>/dev/null || true
fi

# 5. Solar Post Tool
if [ -x "$HOOKS_DIR/solar-post-tool.sh" ]; then
    cat "$TEMP_FILE" | "$HOOKS_DIR/solar-post-tool.sh" 2>/dev/null || true
fi

# 6. Memory Event Capture (Layer 1: Event Sourcing)
if [ -x "$HOOKS_DIR/memory-event-capture.sh" ]; then
    cat "$TEMP_FILE" | "$HOOKS_DIR/memory-event-capture.sh" 2>/dev/null || true
fi

# 7. Observation Compression (语义观察压缩 - 借鉴 claude-mem)
if [ -x "$HOOKS_DIR/observation-compress-hook.sh" ]; then
    cat "$TEMP_FILE" | "$HOOKS_DIR/observation-compress-hook.sh" 2>/dev/null || true
fi

# 8. Task Complete Detector (任务完成检测 - STATE.md 更新提醒)
if [ -x "$HOOKS_DIR/task-complete-detector.sh" ]; then
    cat "$TEMP_FILE" | "$HOOKS_DIR/task-complete-detector.sh" 2>/dev/null || true
fi

# 9. Personality Injector (人格定时注入 - 对抗上下文稀释)
if [ -x "$HOOKS_DIR/personality-injector.sh" ]; then
    "$HOOKS_DIR/personality-injector.sh" 2>/dev/null || true
fi

# 10. Context Monitor (上下文监控 - 80%阈值触发摘要)
if [ -x "$HOOKS_DIR/context-monitor.sh" ]; then
    "$HOOKS_DIR/context-monitor.sh" 2>/dev/null || true
fi

# 11. Evolve Auto-Record (brain-router 调用后自动记录 Q-value)
if [ -x "$HOOKS_DIR/evolve-auto-record.sh" ]; then
    cat "$TEMP_FILE" | "$HOOKS_DIR/evolve-auto-record.sh" 2>/dev/null || true
fi

# 清理
rm -f "$TEMP_FILE"

exit 0
