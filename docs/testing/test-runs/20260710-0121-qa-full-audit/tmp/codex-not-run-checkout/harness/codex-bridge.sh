#!/bin/bash
# ================================================================
# Solar Harness — Codex Bridge 守护进程
#
# DEPRECATED: chain-watcher.sh 已接管全部 codex-bridge 功能。
# 老目录 ~/.solar/harness/codex-bridge/ 不再使用。
# 新目录: ~/.solar/codex-bridge/from-codex/ + to-codex/
# 请用 chain-watcher.sh 代替。
# ================================================================
echo "[codex-bridge.sh] DEPRECATED — 请用 chain-watcher.sh 代替 (v3, 全文件扫描 + 通知)" >&2
exit 0

HARNESS_DIR="$HOME/.solar/harness"
BRIDGE_DIR="$HARNESS_DIR/codex-bridge"
INBOX_DIR="$BRIDGE_DIR/inbox"
OUTBOX_DIR="$BRIDGE_DIR/outbox"
PROCESSED_DIR="$INBOX_DIR/.processed"
LEDGER_FILE="$BRIDGE_DIR/ledger.jsonl"
LOG_FILE="$HARNESS_DIR/logs/codex-bridge.log"
BUDGET_SH="$HARNESS_DIR/codex-budget.sh"

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; C='\033[0;36m'; B='\033[0;34m'; W='\033[1;37m'; N='\033[0m'
DIM='\033[2m'

log() { echo -e "${C}[codex-bridge]${N} $(date '+%H:%M:%S') $*"; }

# 半成品文件清理
cleanup() {
  log "${Y}收到退出信号，清理中...${N}"
  # 删除 outbox 中的半成品 (文件存在但 < 10 bytes)
  for f in "$OUTBOX_DIR"/*.res.md; do
    [[ -f "$f" ]] || continue
    local sz
    sz=$(wc -c < "$f" 2>/dev/null || echo 0)
    if [[ "$sz" -lt 10 ]]; then
      rm -f "$f"
      log "删除半成品: $(basename "$f")"
    fi
  done
  log "${G}清理完成，退出${N}"
  exit 0
}
trap cleanup SIGINT SIGTERM

# 解析 YAML frontmatter (简易版，不依赖 python yaml 库)
parse_frontmatter() {
  local file="$1"
  python3 -c "
import sys, json

lines = open('$file').read().split('\n')
if not lines or lines[0].strip() != '---':
    sys.exit(1)

# 找到第二个 ---
end = -1
for i in range(1, len(lines)):
    if lines[i].strip() == '---':
        end = i
        break

if end == -1:
    sys.exit(1)

# 解析简单的 YAML 键值对
meta = {}
content_start = end + 1
for line in lines[1:end]:
    if ':' not in line:
        continue
    key, val = line.split(':', 1)
    key = key.strip()
    val = val.strip()
    if key == 'context_files':
        # 收集后续的列表项
        files = []
        for sub in lines[1:end]:
            sub = sub.strip()
            if sub.startswith('- '):
                files.append(sub[2:].strip())
        meta['context_files'] = files
    else:
        meta[key] = val

# 提取 prompt 内容 (frontmatter 之后)
prompt = '\n'.join(lines[content_start:]).strip()
meta['_prompt'] = prompt

print(json.dumps(meta))
" 2>/dev/null
}

# 处理单个请求
process_request() {
  local req_file="$1"
  local req_id
  req_id=$(basename "$req_file" .req.md)

  log "处理请求: ${req_id}"

  # 解析 frontmatter
  local meta
  meta=$(parse_frontmatter "$req_file")
  if [[ -z "$meta" ]]; then
    log "${R}解析 frontmatter 失败: ${req_file}${N}"
    # 写错误响应
    echo "# Error\n\nFailed to parse request frontmatter." > "$OUTBOX_DIR/${req_id}.res.md"
    return 1
  fi

  local tier from deadline prompt context_files_str
  tier=$(echo "$meta" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tier','B'))" 2>/dev/null)
  from=$(echo "$meta" | python3 -c "import sys,json; print(json.load(sys.stdin).get('from','unknown'))" 2>/dev/null)
  deadline=$(echo "$meta" | python3 -c "import sys,json; print(json.load(sys.stdin).get('deadline_s','60'))" 2>/dev/null)
  prompt=$(echo "$meta" | python3 -c "import sys,json; print(json.load(sys.stdin).get('_prompt',''))" 2>/dev/null)
  context_files_str=$(echo "$meta" | python3 -c "
import sys, json
d = json.load(sys.stdin)
files = d.get('context_files', [])
print('\n'.join(files))
" 2>/dev/null)

  # Tier 校验
  case "$tier" in
    S|A) ;;
    B)
      log "${Y}B 级拒绝: ${req_id}${N}"
      echo "# REJECTED_BY_POLICY" > "$OUTBOX_DIR/${req_id}.res.md"
      return 0
      ;;
    *)
      log "${R}未知 tier: ${tier}${N}"
      echo "# REJECTED_BY_POLICY" > "$OUTBOX_DIR/${req_id}.res.md"
      return 0
      ;;
  esac

  # 预算检查
  if ! bash "$BUDGET_SH" check; then
    log "${R}预算耗尽: ${req_id}${N}"
    echo "# BUDGET_EXCEEDED" > "$OUTBOX_DIR/${req_id}.res.md"
    return 0
  fi

  # 构建 codex exec 参数
  local codex_args=(-s read-only --json --skip-git-repo-check)
  # 附加 context files
  while IFS= read -r cf; do
    [[ -n "$cf" ]] && [[ -f "$cf" ]] && codex_args+=(-C "$(dirname "$cf")")
  done <<< "$context_files_str"

  log "调用 codex (tier=${tier}, from=${from}, timeout=${deadline}s)..."

  local start_ts end_ts duration_ms exit_code codex_output tokens_out
  start_ts=$(python3 -c "import time; print(int(time.time()*1000))")

  # 调用 codex CLI，捕获输出
  local raw_output
  raw_output=$(codex exec "${codex_args[@]}" "$prompt" 2>>"$LOG_FILE")
  exit_code=$?

  end_ts=$(python3 -c "import time; print(int(time.time()*1000))")
  duration_ms=$(( end_ts - start_ts ))

  if [[ $exit_code -ne 0 ]]; then
    log "${R}codex 失败 (exit=${exit_code}): ${req_id}${N}"
    echo "# CODEX_ERROR\n\nExit code: ${exit_code}" > "$OUTBOX_DIR/${req_id}.res.md"
    tokens_out=0
  else
    # 从 --json 输出提取最后一条消息
    local answer
    answer=$(echo "$raw_output" | python3 -c "
import sys, json
last_msg = ''
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        ev = json.loads(line)
        if ev.get('type') == 'message' and ev.get('role') == 'assistant':
            for c in ev.get('content', []):
                if c.get('type') == 'text':
                    last_msg = c['text']
    except:
        pass
print(last_msg)
" 2>/dev/null)

    if [[ -z "$answer" ]]; then
      # fallback: 直接用 raw_output
      answer="$raw_output"
    fi

    # 写响应
    echo "$answer" > "$OUTBOX_DIR/${req_id}.res.md"
    tokens_out=$(echo "$answer" | wc -w | tr -d ' ')
    log "${G}完成: ${req_id} (${duration_ms}ms, ~${tokens_out} tokens)${N}"
  fi

  # 记账
  local ts
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  echo "{\"ts\":\"${ts}\",\"req_id\":\"${req_id}\",\"persona_from\":\"${from}\",\"tier\":\"${tier}\",\"tokens_in\":$(echo "$prompt" | wc -w | tr -d ' '),\"tokens_out\":${tokens_out},\"duration_ms\":${duration_ms},\"exit_code\":${exit_code}}" \
    >> "$LEDGER_FILE"

  # 消耗预算
  bash "$BUDGET_SH" consume "${tokens_out}" 2>/dev/null

  # 移动已处理请求
  local processed_date_dir="$PROCESSED_DIR/$(date +%Y-%m-%d)"
  mkdir -p "$processed_date_dir"
  mv "$req_file" "$processed_date_dir/" 2>/dev/null || true
}

# ── Banner ──

echo ""
echo -e "${B}╔══════════════════════════════════════════╗${N}"
echo -e "${B}║       Codex Bridge — 顾问外挂            ║${N}"
echo -e "${B}╚══════════════════════════════════════════╝${N}"
echo ""

# 版本
local_version=""
if command -v codex &>/dev/null; then
  local_version=$(codex --version 2>/dev/null || echo "unknown")
fi
echo -e "  ${C}codex-cli:${N} ${local_version}"

# 预算余量
budget_status=$(bash "$BUDGET_SH" status 2>/dev/null)
echo -e "  ${C}预算:${N}"
echo "$budget_status" | sed 's/^/    /'

# 策略
echo -e "  ${C}策略:${N} S=必调(max 4K tokens) A=可调(max 2K) B=禁调"
echo ""
echo -e "  ${DIM}Ctrl-C 退出 | monitor: solar-harness monitor${N}"
echo ""

# 日界重置
bash "$BUDGET_SH" status | grep -q "Reset:" && {
  reset_date=$(bash "$BUDGET_SH" status | grep "Reset:" | awk '{print $2}')
  today=$(date +%Y-%m-%d)
  if [[ "$reset_date" != "$today" ]]; then
    bash "$BUDGET_SH" reset 2>/dev/null
    log "日界重置完成"
  fi
}

log "启动完成，监听 ${INBOX_DIR}/"

# ── 主循环 ──

while true; do
  # 扫描 inbox
  for req_file in "$INBOX_DIR"/*.req.md; do
    [[ -f "$req_file" ]] || continue
    # 跳过 .processed 子目录中的文件
    [[ "$req_file" == *".processed"* ]] && continue
    process_request "$req_file"
  done
  sleep 1
done
