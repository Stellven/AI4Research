#!/bin/bash
# ================================================================
# Solar Harness — 文档结构校验器
#
# 用法: bash validate.sh <type> <file>
#   type: prd | plan | handoff | eval | contract
#
# 校验规则: 每种文档必须包含特定 section header
# 返回: 0=通过, 1=失败 (缺少的 section 输出到 stdout)
# ================================================================

TYPE="${1:?Usage: $0 <prd|plan|handoff|eval|contract> <file>}"
FILE="${2:?Usage: $0 <type> <file>}"

[[ -f "$FILE" ]] || { echo "FAIL: 文件不存在: $FILE"; exit 1; }

MISSING=()

check_section() {
  local pattern="$1" label="$2"
  if ! grep -qiE "$pattern" "$FILE" 2>/dev/null; then
    MISSING+=("$label")
  fi
}

# Capsule 8 字段校验: 支持 yaml frontmatter 或 ## Section 两种格式
CAPSULE_FIELDS=("goal" "facts_established" "changes_made" "risks" "open_questions" "required_next_action" "recursion_round" "topology")
CAPSULE_LABELS=("Goal" "Facts Established" "Changes Made" "Risks" "Open Questions" "Required Next Action" "Recursion Round" "Topology")

check_capsule_fields() {
  local i
  for i in "${!CAPSULE_FIELDS[@]}"; do
    local field="${CAPSULE_FIELDS[$i]}" label="${CAPSULE_LABELS[$i]}"
    # Format 1: yaml frontmatter (field: value)
    # Format 2: ## Section header (## Field Name / ## field_name)
    local field_title
    field_title=$(echo "$field" | sed 's/_/ /g')
    if ! grep -qiE "^${field}:|^[#]+[[:space:]]*${field_title}|^[#]+[[:space:]]*${field}" "$FILE" 2>/dev/null; then
      MISSING+=("Capsule: $label")
    fi
  done
}

case "$TYPE" in
  prd)
    # PM PRD 必须包含需求研究、拆解和架构交接字段
    check_section '^##.*背景|^##.*Context' "背景 / Context"
    check_section '^##.*问题|^##.*Problem' "用户问题 / Problem"
    check_section '^##.*目标|^##.*Goals' "用户目标 / Goals"
    check_section '^##.*用户故事|^##.*User Stories' "用户故事 / User Stories"
    check_section '^##.*需求|^##.*Requirements' "功能需求 / Requirements"
    check_section '^##.*验收|^##.*Acceptance' "验收标准 / Acceptance Criteria"
    check_section '^##.*非目标|^##.*Non-Goals' "非目标 / Non-Goals"
    check_section '^##.*约束|^##.*Constraints' "约束 / Constraints"
    check_section '^##.*风险|^##.*Risks' "风险 / Risks"
    check_section '^##.*开放问题|^##.*Open Questions' "开放问题 / Open Questions"
    check_section '^##.*架构交接|^##.*Planner Handoff' "架构交接 / Planner Handoff"
    ;;

  plan)
    # 实现计划必须包含:
    check_section '^##.*文件|^##.*Files|^##.*变更' "变更文件列表"
    check_section '^##.*方案|^##.*Design|^##.*技术|^##.*Approach' "技术方案"
    check_section '^##.*风险|^##.*Risk' "风险点"
    ;;

  handoff)
    # Handoff 文档必须包含:
    check_section '^##.*变更|^##.*文件|^##.*Changes|^##.*Files' "变更文件列表"
    check_section '^##.*Done|^##.*达成|^##.*完成' "Done 条件达成证据"
    check_section '^##.*验证|^##.*Verify|^##.*测试|^##.*Test' "验证方法"
    ;;

  eval)
    # 评估报告必须包含:
    check_section '^##.*判定|^##.*Verdict|总判定' "总判定 (PASS/FAIL)"
    check_section '^##.*Done|条件|逐条' "Done 条件逐条检查"
    check_section 'PASS|FAIL' "PASS/FAIL 标记"
    ;;

  contract)
    # 合约必须包含:
    check_section '^##.*需求' "需求描述"
    check_section '^##.*Done' "Done 定义"
    check_section '^\- \[' "可检查的 Done 条件 (- [ ] 格式)"
    ;;

  capsule_plan)
    check_section '^##.*文件|^##.*Files|^##.*变更' "变更文件列表"
    check_section '^##.*方案|^##.*Design|^##.*技术|^##.*Approach' "技术方案"
    check_section '^##.*风险|^##.*Risk' "风险点"
    check_capsule_fields
    ;;
  capsule_handoff)
    check_section '^##.*变更|^##.*文件|^##.*Changes|^##.*Files' "变更文件列表"
    check_section '^##.*Done|^##.*达成|^##.*完成' "Done 条件达成证据"
    check_section '^##.*验证|^##.*Verify|^##.*测试|^##.*Test' "验证方法"
    check_capsule_fields
    ;;
  capsule_eval)
    check_section '^##.*判定|^##.*Verdict|总判定' "总判定 (PASS/FAIL)"
    check_section '^##.*Done|条件|逐条' "Done 条件逐条检查"
    check_section 'PASS|FAIL' "PASS/FAIL 标记"
    check_capsule_fields
    ;;
  *)
    echo "FAIL: 未知类型: $TYPE (支持: prd|plan|handoff|eval|contract|capsule_plan|capsule_handoff|capsule_eval)"
    exit 1
    ;;
esac

if [[ ${#MISSING[@]} -gt 0 ]]; then
  echo "FAIL: 缺少 ${#MISSING[@]} 个必需 section:"
  for m in "${MISSING[@]}"; do
    echo "  - $m"
  done
  exit 1
else
  echo "PASS"
  exit 0
fi
