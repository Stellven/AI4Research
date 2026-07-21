#!/bin/bash
# ================================================================
# Solar Harness — Persona 配置共享函数 (单一真相源)
# Sprint sprint-20260502-191700 D1
#
# 用法:
#   source "$HARNESS_DIR/lib/persona-config.sh"
#   get_persona_config <planner|builder|evaluator>
#   # 输出 KEY=VALUE 行, caller 用 eval 解析
#
#   # CLI 调试接口:
#   bash persona-config.sh --print-config planner
#
# @module solar-farm/harness/lib/persona-config
# ================================================================

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
[[ -f "$HARNESS_DIR/lib/harness-config.sh" ]] && source "$HARNESS_DIR/lib/harness-config.sh"

# 从 model-config.sh 读 ZHIPU_* 变量
_source_model_config() {
  source "$HARNESS_DIR/model-config.sh" 2>/dev/null || true
  # Shared router env can hold non-Anthropic provider keys (for example
  # DEEPSEEK_API_KEY). Source it here so tmux-launched panes do not silently
  # fall back to Claude when the interactive shell env is sparse.
  source "$HOME/.solar/brain-router/.env" 2>/dev/null || true
}

_zhipu_available() {
  # SOLAR_NO_ZHIPU=1 → 强制回退到 Claude (per-pane override, 2026-05-08 GLM 1210 5次后默认 Sonnet)
  [[ "${SOLAR_NO_ZHIPU:-0}" == "1" ]] && return 1
  [[ -n "${ZHIPU_AUTH_TOKEN:-}" && -n "${ZHIPU_BASE_URL:-}" && -n "${ZHIPU_MODEL:-}" ]]
}

_zhipu_credentials_available() {
  [[ -n "${ZHIPU_AUTH_TOKEN:-}" && -n "${ZHIPU_BASE_URL:-}" && -n "${ZHIPU_MODEL:-}" ]]
}

_deepseek_auth_token() {
  source "$HOME/.solar/brain-router/.env" 2>/dev/null || true
  if [[ -n "${DEEPSEEK_API_KEY:-}" ]]; then
    printf '%s' "${DEEPSEEK_API_KEY}"
    return 0
  fi
  if [[ -f "$HOME/.config/llm-keys/deepseek" ]]; then
    tr -d '\r\n' < "$HOME/.config/llm-keys/deepseek"
    return 0
  fi
  return 1
}

_deepseek_available() {
  [[ -n "$(_deepseek_auth_token 2>/dev/null || true)" ]]
}

_gateway_compat_flags() {
  printf '%s' "--bare --tools default --strict-mcp-config --mcp-config $HARNESS_DIR/config/empty-mcp.json"
}

_zhipu_coding_plan_flags() {
  # Z.AI's official Claude Code Coding Plan setup uses ANTHROPIC_AUTH_TOKEN and
  # the Anthropic-compatible endpoint. Do not use --bare here: Claude Code's
  # bare mode authenticates with ANTHROPIC_API_KEY and presents "API Usage
  # Billing", which can bypass the Coding Plan subscription route.
  printf '%s' "--tools default --strict-mcp-config --mcp-config $HARNESS_DIR/config/empty-mcp.json"
}

_infer_auth_source_for_base_url() {
  local base_url="$1"
  case "$base_url" in
    *deepseek*) echo "deepseek" ;;
    *z.ai*|*bigmodel*) echo "zhipu" ;;
    *) echo "zhipu" ;;
  esac
}

_normalize_main_model_alias() {
  if command -v solar_model_alias_canonical >/dev/null 2>&1; then
    solar_model_alias_canonical "${1:-anthropic-sonnet}" 2>/dev/null || printf '%s' "claude-sonnet"
  else
    printf '%s' "${1:-sonnet}" | tr '[:upper:]' '[:lower:]' | xargs
  fi
}

_persona_model_alias() {
  local persona="$1"
  local default_value="${2:-anthropic-sonnet}"
  if command -v solar_persona_model >/dev/null 2>&1; then
    _normalize_main_model_alias "$(solar_persona_model "$persona" "$default_value")"
  else
    _normalize_main_model_alias "$default_value"
  fi
}

_configure_anthropic_persona_model() {
  local alias="$(_normalize_main_model_alias "${1:-anthropic-sonnet}")"
  case "$alias" in
    claude-opus)
      model_id="$alias"
      model_flag="$(solar_model_flag "$alias")"
      display_model="Claude Opus 4.8 (Anthropic)"
      ;;
    claude-sonnet)
      model_id="$alias"
      model_flag="$(solar_model_flag "$alias")"
      display_model="Claude Sonnet (Anthropic)"
      ;;
    *)
      # Unknown main-screen model aliases are unsafe for production panes.
      # Fail closed to the verified native Claude route instead of launching a
      # pane that later dies with an opaque API 400.
      model_flag="--model sonnet"
      model_id="claude-sonnet"
      display_model="Claude Sonnet (Anthropic, unknown alias '${alias}' guarded)"
      ;;
  esac
}

_configure_persona_model() {
  local alias="$(_normalize_main_model_alias "${1:-anthropic-sonnet}")"
  local display_suffix="${2:-}"
  case "$alias" in
    zhipu-glm-5.1)
      if _zhipu_credentials_available; then
        model_id="$alias"
        model_flag="$(solar_model_flag "$alias")"
        base_url="${ZHIPU_BASE_URL:-}"
        auth_token="${ZHIPU_AUTH_TOKEN:-}"
        auth_source="zhipu"
        extra_flags="$(_zhipu_coding_plan_flags)"
        display_model="GLM-5.1 (智谱${display_suffix})"
      else
        model_id="$alias"
        model_flag=""
        base_url=""
        auth_token=""
        auth_source=""
        extra_flags=""
        display_model="UNAVAILABLE: GLM-5.1 credentials missing${display_suffix}"
        launch_error="GLM-5.1 requested for persona, but ZHIPU credentials are unavailable; refusing Claude fallback"
      fi
      ;;
    zhipu-glm-4.7)
      if _zhipu_credentials_available; then
        model_id="$alias"
        model_flag="$(solar_model_flag "$alias")"
        base_url="${ZHIPU_BASE_URL:-}"
        auth_token="${ZHIPU_AUTH_TOKEN:-}"
        auth_source="zhipu"
        extra_flags="$(_zhipu_coding_plan_flags)"
        display_model="GLM-4.7 (智谱${display_suffix})"
      else
        model_id="$alias"
        model_flag=""
        base_url=""
        auth_token=""
        auth_source=""
        extra_flags=""
        display_model="UNAVAILABLE: GLM-4.7 credentials missing${display_suffix}"
        launch_error="GLM-4.7 requested for persona, but ZHIPU credentials are unavailable; refusing Claude fallback"
      fi
      ;;
    deepseek-v4-pro)
      if _deepseek_available; then
        model_id="$alias"
        model_flag="$(solar_model_flag "$alias")"
        base_url="https://api.deepseek.com/anthropic"
        auth_source="deepseek"
        extra_flags="$(_gateway_compat_flags)"
        display_model="DeepSeek V4 Pro${display_suffix}"
        auth_token="$(_deepseek_auth_token 2>/dev/null || true)"
      else
        model_id="$alias"
        model_flag=""
        base_url=""
        auth_token=""
        auth_source=""
        extra_flags=""
        display_model="UNAVAILABLE: DeepSeek credentials missing${display_suffix}"
        launch_error="DeepSeek requested for persona, but DEEPSEEK_API_KEY is unavailable; refusing Claude fallback"
      fi
      ;;
    *)
      _configure_anthropic_persona_model "$alias"
      ;;
  esac
}

_lab_builder_model_for_slot() {
  local slot="${SOLAR_BUILDER_SLOT:-lab-builder-1}"
  local slot_num="${slot##*-}"
  [[ "$slot_num" =~ ^[0-9]+$ ]] || slot_num=1

  # Model policy is config-owned. Launchers should not hardcode lab routing.
  local matrix
  if command -v solar_lab_builder_matrix >/dev/null 2>&1; then
    matrix="$(solar_lab_builder_matrix)"
  else
    echo "FATAL: missing harness config helper: $HARNESS_DIR/lib/harness-config.sh" >&2
    return 1
  fi
  local IFS=','
  local models=($matrix)
  local selected="${models[$((slot_num - 1))]:-}"
  if [[ -z "$selected" ]]; then
    local last_index=$((${#models[@]} - 1))
    if (( last_index >= 0 )); then
      selected="${models[$last_index]}"
    else
      selected="anthropic-sonnet"
    fi
  fi
  if command -v solar_model_alias_canonical >/dev/null 2>&1; then
    solar_model_alias_canonical "$selected"
  else
    printf '%s' "$selected" | tr '[:upper:]' '[:lower:]' | xargs
  fi
}

get_persona_config() {
  local persona="$1"
  _source_model_config

  local model_flag="" model_id="" base_url="" auth_token="" tool_flag="" display_model="" startup_token="" proxy_check="0" auth_source="" extra_flags="" launch_error=""
  local cn=""

  case "$persona" in
    planner)
      cn="规划者"
      _configure_persona_model "$(_persona_model_alias planner)"
      tool_flag="--allowedTools Read Bash Grep Glob"
      startup_token="solar"
      proxy_check="1"
      ;;
    builder)
      cn="建设者"
      # Main builder keeps full Claude Code interactive/MCP behavior, but its
      # model is config-owned like the other main-screen personas.
      _configure_persona_model "$(_persona_model_alias builder)"
      display_model="${display_model}, full tools"
      tool_flag=""
      startup_token=""
      proxy_check="0"
      ;;
    evaluator)
      cn="审判官"
      # Product Delivery 的 pane3 是主评审通道，优先稳定性。
      _configure_persona_model "$(_persona_model_alias evaluator)"
      tool_flag="--allowedTools Read Bash Grep Glob Write"
      startup_token=""
      proxy_check="0"
      ;;
    pm)
      cn="产品经理"
      _configure_persona_model "$(_persona_model_alias pm)"
      tool_flag="--allowedTools Read Bash Grep Glob Write"
      startup_token=""
      proxy_check="1"
      ;;
    architect)
      cn="架构师"
      _configure_persona_model "$(_persona_model_alias architect)"
      tool_flag="--allowedTools Read Bash Grep Glob Write Edit"
      startup_token=""
      proxy_check="1"
      ;;
    second-builder)
      cn="架构师(sonnet)"
      _configure_persona_model "$(_persona_model_alias second-builder)"
      tool_flag="--allowedTools Read Bash Grep Glob Write Edit"
      startup_token=""
      proxy_check="1"
      ;;
    lab-builder)
      cn="实验建设者"
      local lab_model
      lab_model="$(_lab_builder_model_for_slot)"
      if [[ "$lab_model" == "zhipu-glm-5.1" ]] && _zhipu_credentials_available; then
        model_id="$lab_model"
        model_flag="$(solar_model_flag "$lab_model")"
        base_url="${ZHIPU_BASE_URL:-}"
        auth_token="${ZHIPU_AUTH_TOKEN:-}"
        auth_source="zhipu"
        extra_flags="$(_zhipu_coding_plan_flags)"
        display_model="GLM-5.1 (智谱, ${SOLAR_BUILDER_SLOT:-lab-builder})"
      elif [[ "$lab_model" == "zhipu-glm-5.1" ]]; then
        model_id="$lab_model"
        model_flag=""
        base_url=""
        auth_token=""
        display_model="UNAVAILABLE: GLM credentials missing (${SOLAR_BUILDER_SLOT:-lab-builder})"
        launch_error="GLM requested for ${SOLAR_BUILDER_SLOT:-lab-builder}, but ZHIPU credentials are unavailable; refusing Claude fallback"
      elif [[ "$lab_model" == "zhipu-glm-4.7" ]] && _zhipu_credentials_available; then
        model_id="$lab_model"
        model_flag="$(solar_model_flag "$lab_model")"
        base_url="${ZHIPU_BASE_URL:-}"
        auth_token="${ZHIPU_AUTH_TOKEN:-}"
        auth_source="zhipu"
        extra_flags="$(_zhipu_coding_plan_flags)"
        display_model="GLM-4.7 (智谱, ${SOLAR_BUILDER_SLOT:-lab-builder})"
      elif [[ "$lab_model" == "deepseek-v4-pro" ]] && _deepseek_available; then
        model_id="$lab_model"
        model_flag="$(solar_model_flag "$lab_model")"
        base_url="https://api.deepseek.com/anthropic"
        auth_source="deepseek"
        extra_flags="$(_gateway_compat_flags)"
        display_model="DeepSeek V4 Pro (${SOLAR_BUILDER_SLOT:-lab-builder})"
        auth_token="$(_deepseek_auth_token 2>/dev/null || true)"
      elif [[ "$lab_model" == "deepseek-v4-pro" ]]; then
        model_id="$lab_model"
        model_flag=""
        base_url=""
        auth_token=""
        display_model="UNAVAILABLE: DeepSeek credentials missing (${SOLAR_BUILDER_SLOT:-lab-builder})"
        launch_error="DeepSeek requested for ${SOLAR_BUILDER_SLOT:-lab-builder}, but DEEPSEEK_API_KEY is unavailable; refusing Claude fallback"
      elif [[ "$lab_model" == "claude-opus" ]]; then
        model_id="$lab_model"
        model_flag="$(solar_model_flag "$lab_model")"
        base_url=""
        auth_token=""
        display_model="Claude Opus (Anthropic, ${SOLAR_BUILDER_SLOT:-lab-builder})"
      elif [[ "$lab_model" == "claude-sonnet" ]]; then
        model_id="$lab_model"
        model_flag="$(solar_model_flag "$lab_model")"
        base_url=""
        auth_token=""
        display_model="Claude Sonnet (Anthropic, ${SOLAR_BUILDER_SLOT:-lab-builder})"
      else
        model_id="$lab_model"
        model_flag=""
        base_url=""
        auth_token=""
        display_model="UNAVAILABLE: unknown lab model '${lab_model}' (${SOLAR_BUILDER_SLOT:-lab-builder})"
        launch_error="unknown lab model '${lab_model}' for ${SOLAR_BUILDER_SLOT:-lab-builder}; refusing Claude fallback"
      fi
      tool_flag=""
      startup_token=""
      proxy_check="0"
      ;;
    lab-evaluator)
      cn="实验审判官"
      if _zhipu_available; then
        model_flag="--model claude-opus-4-8"
        base_url="${ZHIPU_BASE_URL:-}"
        auth_token="${ZHIPU_AUTH_TOKEN:-}"
        auth_source="zhipu"
        extra_flags="$(_zhipu_coding_plan_flags)"
        display_model="GLM-5.1 (智谱)"
      else
        _configure_anthropic_persona_model "$(_persona_model_alias lab-evaluator)"
        base_url=""
        auth_token=""
      fi
      tool_flag="--allowedTools Read Bash Grep Glob Write"
      startup_token=""
      proxy_check="0"
      ;;
    observer)
      cn="观察者"
      if _zhipu_available; then
        model_flag="--model claude-opus-4-8"
        base_url="${ZHIPU_BASE_URL:-}"
        auth_token="${ZHIPU_AUTH_TOKEN:-}"
        auth_source="zhipu"
        extra_flags="$(_zhipu_coding_plan_flags)"
        display_model="GLM-5.1 (智谱)"
      else
        _configure_anthropic_persona_model "$(_persona_model_alias observer)"
        base_url=""
        auth_token=""
      fi
      tool_flag="--allowedTools Read Bash Grep Glob"
      startup_token=""
      proxy_check="0"
      ;;
    *)
      cn="$persona"
      if _zhipu_available; then
        model_flag="--model claude-opus-4-8"
        base_url="${ZHIPU_BASE_URL:-}"
        auth_token="${ZHIPU_AUTH_TOKEN:-}"
        auth_source="zhipu"
        extra_flags="$(_zhipu_coding_plan_flags)"
        display_model="GLM-5.1 (智谱)"
      else
        _configure_anthropic_persona_model "$(_persona_model_alias "$persona")"
        base_url=""
        auth_token=""
      fi
      tool_flag=""
      startup_token=""
      proxy_check="0"
      ;;
  esac

  # DeepSeek still needs Claude Code's minimal request shape. Z.AI Coding Plan
  # must stay on the official Claude Code route above.
  if [[ -n "$base_url" ]]; then
    [[ -n "$auth_source" ]] || auth_source="$(_infer_auth_source_for_base_url "$base_url")"
    if [[ "$auth_source" != "zhipu" && "${SOLAR_GATEWAY_COMPAT:-1}" != "0" && -z "$extra_flags" ]]; then
      extra_flags="$(_gateway_compat_flags)"
    fi
  fi

  # sprint-20260502-191700 follow-up: 输出加引号 (修 eval bug) + AUTH_TOKEN 不泄漏明文
  # 旧 bug 1: MODEL_FLAG=--model glm-5.1 → eval 时被 bash 当 "VAR=val command" 临时 env 跑 glm-5.1 → not found
  # 旧 bug 2: AUTH_TOKEN=明文 → --print-config 直接打印到屏幕 → 泄漏隐患
  # 修复: 单引号包裹 + AUTH_TOKEN 输出 mask (真值仍由 apply_persona_env 从 env 设置)
  local masked_token=""
  [[ -n "$auth_token" ]] && masked_token="<from-env:ZHIPU_AUTH_TOKEN>"
  echo "CN='$cn'"
  echo "MODEL_ID='$model_id'"
  echo "MODEL_FLAG='$model_flag'"
  echo "BASE_URL='$base_url'"
  echo "AUTH_TOKEN='$masked_token'"
  echo "TOOL_FLAG='$tool_flag'"
  echo "DISPLAY_MODEL='$display_model'"
  echo "STARTUP_TOKEN='$startup_token'"
  echo "PROXY_CHECK='$proxy_check'"
  echo "AUTH_SOURCE='$auth_source'"
  echo "EXTRA_FLAGS='$extra_flags'"
  echo "LAUNCH_ERROR='$launch_error'"
}

apply_persona_env() {
  local persona="$1"
  # sprint-20260502-191700 follow-up: AUTH_TOKEN 不再从 get_persona_config 传(已 mask)
  # 直接从环境变量取真值 (model-config.sh source secrets/zhipu.env 时已设置 ZHIPU_AUTH_TOKEN)
  _source_model_config

  local config
  config=$(get_persona_config "$persona")

  # 解析 KV 对 (现在带单引号,需 strip)
  local base_url proxy_check auth_source
  base_url=$(echo "$config" | grep '^BASE_URL=' | sed "s/^BASE_URL='//;s/'$//")
  proxy_check=$(echo "$config" | grep '^PROXY_CHECK=' | sed "s/^PROXY_CHECK='//;s/'$//")
  auth_source=$(echo "$config" | grep '^AUTH_SOURCE=' | sed "s/^AUTH_SOURCE='//;s/'$//")

  # 设置/清除环境变量
  if [[ -n "$base_url" ]]; then
    export ANTHROPIC_BASE_URL="$base_url"
    case "$auth_source" in
      deepseek)
        local deepseek_token=""
        deepseek_token="$(_deepseek_auth_token 2>/dev/null || true)"
        if [[ -z "$deepseek_token" ]]; then
          echo "FATAL: persona '$persona' 需要 DEEPSEEK_API_KEY 或 ~/.config/llm-keys/deepseek" >&2
          return 1
        fi
        export ANTHROPIC_AUTH_TOKEN="$deepseek_token"
        # Claude Code --bare authenticates Anthropic-compatible endpoints via
        # ANTHROPIC_API_KEY; keep AUTH_TOKEN too for older CLI compatibility.
        export ANTHROPIC_API_KEY="$deepseek_token"
        export ANTHROPIC_DEFAULT_OPUS_MODEL="${DEEPSEEK_OPUS_MODEL:-deepseek-v4-flash}"
        export ANTHROPIC_DEFAULT_SONNET_MODEL="${DEEPSEEK_SONNET_MODEL:-deepseek-v4-pro}"
        export ANTHROPIC_DEFAULT_HAIKU_MODEL="${DEEPSEEK_HAIKU_MODEL:-deepseek-v4-flash}"
        ;;
      *)
        # AUTH_TOKEN 直接从已 source 的 ZHIPU_AUTH_TOKEN 取真值,绝不从 stdout 解析
        if [[ -z "${ZHIPU_AUTH_TOKEN:-}" ]]; then
          echo "FATAL: persona '$persona' 需要 ZHIPU_AUTH_TOKEN, 但未设置" >&2
          return 1
        fi
        export ANTHROPIC_AUTH_TOKEN="$ZHIPU_AUTH_TOKEN"
        unset ANTHROPIC_API_KEY
        export ANTHROPIC_DEFAULT_OPUS_MODEL="${ZHIPU_MODEL:-glm-5.1}"
        export ANTHROPIC_DEFAULT_SONNET_MODEL="${ZHIPU_SONNET_MODEL:-glm-4.7}"
        export ANTHROPIC_DEFAULT_HAIKU_MODEL="${ZHIPU_HAIKU_MODEL:-glm-4.5-air}"
        ;;
    esac
    export API_TIMEOUT_MS="${API_TIMEOUT_MS:-3000000}"
    export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
    export CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1
    export DISABLE_NON_ESSENTIAL_MODEL_CALLS=1
  else
    unset ANTHROPIC_BASE_URL
    unset ANTHROPIC_AUTH_TOKEN
    unset ANTHROPIC_API_KEY
    unset API_TIMEOUT_MS
    unset CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC
    unset CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS
    unset DISABLE_NON_ESSENTIAL_MODEL_CALLS
    unset ANTHROPIC_DEFAULT_OPUS_MODEL
    unset ANTHROPIC_DEFAULT_SONNET_MODEL
    unset ANTHROPIC_DEFAULT_HAIKU_MODEL
  fi

  # 代理
  if [[ "$proxy_check" == "1" ]]; then
    if curl -s --connect-timeout 1 http://127.0.0.1:1082 >/dev/null 2>&1; then
      export HTTPS_PROXY="http://127.0.0.1:1082"
      export HTTP_PROXY="http://127.0.0.1:1082"
      export ALL_PROXY="http://127.0.0.1:1082"
    else
      unset HTTPS_PROXY HTTP_PROXY ALL_PROXY
    fi
  else
    unset HTTPS_PROXY HTTP_PROXY ALL_PROXY
  fi
}

# ── Brain Whisper: 从 lessons.jsonl 注入历史教训到 persona system prompt ──
inject_whisper() {
  local persona="$1"
  local lessons_file="$HOME/.solar/harness/brain/lessons.jsonl"
  [[ ! -f "$lessons_file" ]] && return 0

  python3 -c "
import json, sys

persona = sys.argv[1]
lessons_file = sys.argv[2]
results = []

persona_map = {
    'planner': ['规划者', 'planner'],
    'builder': ['建设者', 'builder'],
    'evaluator': ['审判官', 'evaluator'],
    'second-builder': ['建设者(并行)', 'second-builder', '建设者'],
    'pm': ['产品经理', 'pm'],
    'architect': ['架构师', 'architect'],
    'lab-builder': ['实验建设者', 'lab-builder'],
    'lab-evaluator': ['实验审判官', 'lab-evaluator'],
    'observer': ['观察者', 'observer'],
}

match_set = set(persona_map.get(persona, [persona]))

with open(lessons_file) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        conf = d.get('confidence', 0)
        if conf < 0.7:
            continue
        tags = d.get('tags', [])
        # role match: persona name or CN name in tags
        if match_set.intersection(tags):
            results.append(d)
        elif conf >= 0.85:
            results.append(d)

# dedupe by lesson text, keep most recent
seen = set()
deduped = []
for r in reversed(results):
    txt = r.get('lesson', '')
    if txt not in seen:
        seen.add(txt)
        deduped.append(r)

if not deduped:
    sys.exit(0)

print()
print('## 历史教训 (Brain Whisper)')
for item in reversed(deduped[:3]):
    conf = item.get('confidence', 0)
    tags_str = ','.join(item.get('tags', []))
    print(f'- [{conf:.1f}] {item.get(\"lesson\", \"\")} ({tags_str})')
" "$persona" "$lessons_file" 2>/dev/null
}

# ── Runtime Policy: 强制交互式 pane 走统一知识上下文 ─────────────────────
inject_runtime_policy() {
  local persona="$1"
  cat <<'EOF'

## Solar Runtime Context Policy (Mandatory)

你运行在 Solar-Harness pane 内。无论当前 persona 是 PM、Planner、Builder、Evaluator 还是 Lab Builder，只要收到用户直接输入、需求分析、技术研究、架构设计、调试诊断、知识库问题或 Solar/Harness 运维问题，第一步必须先调用统一知识入口：

```bash
solar-harness context inject --query "<把用户原始问题简洁转写到这里>" --format markdown
```

这个命令是默认知识库入口，背后包含 Mirage VFS + QMD solar-wiki + Obsidian Vault + Solar DB。你必须把它作为主检索路径。

硬性规则：
- 不得把 `sqlite3 ~/.solar/solar.db ...` 当作第一步或唯一知识库查询。
- 不得直接跳到 Web Search；必须先跑 `solar-harness context inject`，再按需要补充 web 或 sqlite。
- 如果 context inject 有命中，回答/brief/plan/handoff/eval 中必须体现“已使用 Solar Unified Context”，并引用关键命中来源。
- 如果 context inject 返回无命中或 degraded sources，必须说明降级，然后才能用 sqlite、grep、qmd-search、web search 作为补充。
- 直接 sqlite 查询只允许作为二级验证或精确表查询；它不能替代 Mirage/QMD/Obsidian 默认路径。
- 处理 dispatch 文件时，如果文件中已经有 `<solar-unified-context>`，可复用；如果没有，先运行上面的 context inject。
- 如果 persona 是 Evaluator/审判官，并且任务属于 sprint/node 评审，必须先运行：
  `solar-harness session evaluate <sprint_id> --json`
  然后把 session log verdict、warnings/errors 写进 eval.md。eval 不能只看最终 handoff 文件。
- 如需比较两轮/两机/两版本行为，使用：
  `solar-harness session diff <session_a> <session_b> --json`

可见性要求：
- 在最终输出或 handoff/eval 中写一行：`Knowledge Context: solar-harness context inject used`。
- 审判官 eval 中还必须写一行：`Session Log: solar-harness session evaluate used`。
- 如果未使用，必须写明失败原因；否则视为违反 Solar-Harness 默认能力使用规则。

## Definition of Done · Mandatory Completion Gate

任务没有完成，除非同时满足以下 7 条。交付不是输出代码；交付是用证据证明功能真的工作。

1. 真实调用链接入 — 所有新增/修改功能已接入真实调用链，不允许只写孤立模块。
2. 禁止硬编码 — 不允许硬编码业务数据、测试数据、路径、token、feature flag。
3. 测试必须运行 — 必须运行相关测试；如果不能运行，必须明确说明原因。
4. 执行证据齐全 — 必须给出实际执行过的命令和结果摘要；不接受“应该可以工作”。
5. Diff 自审 — 必须检查 diff，列出每个改动文件的目的。
6. 禁用乐观词 — 如果存在未完成项，禁止使用 “done / complete / implemented”。
7. 结构化收尾 — 最终回答必须分为：已完成 · 已验证 · 未验证 · 风险 · 后续待办。

硬性判定：没有证据，不许报喜；存在未验证项时只能标 `未验证` 或 `风险`，不能标完成。
EOF
}

# ── Capability Prefix Policy: pane 输出中显式标注实际能力调用 ───────────────
inject_prefix_policy() {
  local persona="$1"
  cat <<'EOF'

## Solar Harness Capability Prefix Policy (Mandatory Visibility)

你必须让用户一眼看出当前 pane 实际调用了哪些 Solar-Harness 能力。每次使用或报告下列能力前，先输出一行对应前缀：

- `[harness-knowledge]`：调用 `solar-harness context inject`、QMD、Mirage、Obsidian、Solar DB、RAGFlow。
- `[harness-intent]`：调用 intent engine、意图匹配、技能选择、capability inference。
- `[harness-skills]`：调用 skills inventory/readiness/certify/inject/effect-scan。
- `[harness-graph]`：调用 task_graph、DAG scheduler、graph node dispatch、join gate。
- `[harness-ATLAS]`：调用 ATLAS repair、失败诊断、自动修复协议。
- `[harness-autopilot]`：调用 autopilot、deadlock monitor、pane lease/queue 监控。
- `[harness-mineru]`：调用 MinerU、PDF deep extraction、document explorer。
- `[harness-ruflo]`：调用 Ruflo / Claude Flow runtime sandbox。
- `[harness-model]`：模型路由、配额、provider 切换、pane 模型状态。

输出规则：
- 不要声称调用了未实际调用的能力。
- 如果能力只是在 dispatch/context 中被注入而未执行，写 `planned` 或 `injected`，不要写 `used`。
- 如果命令输出里已经有彩色 `[harness-*]` 前缀，可以复用，不要重复刷屏。
- 最终总结中保留一行 `Harness Modules Used: ...`，列出实际用到的模块。
EOF
}

# --print-config CLI 接口
if [[ "${1:-}" == "--print-config" ]]; then
  persona="${2:?Usage: $0 --print-config <planner|builder|evaluator>}"
  get_persona_config "$persona"
fi
