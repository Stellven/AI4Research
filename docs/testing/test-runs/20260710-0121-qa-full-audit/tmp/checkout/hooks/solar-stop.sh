#!/bin/bash
# Solar Flow Engine - Stop Hook
# Claude 停止时进行 Gate 检查

STATE_FILE="$PWD/.solar/flow-state.json"

# 如果没有状态文件，正常放行
if [[ ! -f "$STATE_FILE" ]]; then
    echo '{"decision": "approve"}'
    exit 0
fi

# 检查是否激活
ACTIVE=$(jq -r '.active // false' "$STATE_FILE" 2>/dev/null)
if [[ "$ACTIVE" != "true" ]]; then
    echo '{"decision": "approve"}'
    exit 0
fi

# 读取状态
PHASE=$(jq -r '.flow.current_phase // "P3"' "$STATE_FILE")
# 注意：jq 的 // 操作符会把 false 当作 falsy，所以用 tostring
ANNOUNCED=$(jq -r '.agent_announcement.announced | tostring' "$STATE_FILE" 2>/dev/null)
[[ -z "$ANNOUNCED" ]] && ANNOUNCED="true"

# 检查是否已宣告
if [[ "$ANNOUNCED" == "false" ]]; then
    cat << EOF
{
  "decision": "block",
  "reason": "未完成 Agent 宣告",
  "systemMessage": "【Solar Gate】请在结束前输出 Agent 宣告，说明完成的任务和结果。"
}
EOF
    exit 0
fi

# Gate 检查
case "$PHASE" in
    "P2")
        # G1 Gate: 设计阶段完成检查
        # 检查是否有设计文档
        if ! ls docs/*DESIGN*.md &>/dev/null && ! ls docs/*design*.md &>/dev/null; then
            G1_ATTEMPTS=$(jq -r '.gate.G1_attempts // 0' "$STATE_FILE")
            NEW_ATTEMPTS=$((G1_ATTEMPTS + 1))

            # 更新尝试次数
            jq ".gate.G1_attempts = $NEW_ATTEMPTS" "$STATE_FILE" > "${STATE_FILE}.tmp" 2>/dev/null
            mv "${STATE_FILE}.tmp" "$STATE_FILE" 2>/dev/null

            if [[ $NEW_ATTEMPTS -ge 2 ]]; then
                # 超过重试次数，允许通过但警告
                cat << EOF
{
  "decision": "approve",
  "systemMessage": "【G1 Gate 警告】设计文档缺失，但已达到重试上限。建议使用 /phase next 进入下一阶段前补充设计文档。"
}
EOF
            else
                cat << EOF
{
  "decision": "block",
  "reason": "G1 Gate 未通过",
  "systemMessage": "【G1 Gate】设计阶段应输出设计文档 (docs/*_DESIGN.md)。\\n请完成设计文档，或使用 /phase next 强制进入下一阶段。\\n(尝试 $NEW_ATTEMPTS/2)"
}
EOF
            fi
            exit 0
        fi
        ;;
    "P4")
        # G2 Gate: 验证阶段完成检查
        # 可以检查测试是否通过等 (简化版本)
        ;;
esac

echo '{"decision": "approve"}'
