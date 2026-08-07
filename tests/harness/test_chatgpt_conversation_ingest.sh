#!/usr/bin/env bash
# test-chatgpt-conversation-ingest.sh — ChatGPT export/transcript raw ingest regression
set -euo pipefail

SCRIPT="$HOME/.solar/harness/lib/chatgpt-conversation-ingest.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1 — $2"; FAIL=$((FAIL + 1)); }

echo "=== test-chatgpt-conversation-ingest.sh ==="

mkdir -p "$TMP/export" "$TMP/out"

cat > "$TMP/export/conversations.json" <<'JSON'
[
  {
    "id": "conv-1",
    "title": "Solar KB design",
    "create_time": 1778241600,
    "update_time": 1778241700,
    "mapping": {
      "u1": {
        "message": {
          "author": {"role": "user"},
          "create_time": 1778241601,
          "content": {"content_type": "text", "parts": ["怎么把 ChatGPT 问答写入知识库？"]}
        }
      },
      "a1": {
        "message": {
          "author": {"role": "assistant"},
          "create_time": 1778241602,
          "content": {"content_type": "text", "parts": ["应该先导出 conversations.json，规范化为 markdown，再进入 _raw/chatgpt 由 wiki ingest 抽取。"]}
        }
      }
    }
  }
]
JSON

json_out="$(python3 "$SCRIPT" --source "$TMP/export/conversations.json" --out-root "$TMP/out" --batch-id test-json --no-dispatch --json)"
if echo "$json_out" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["ok"] and d["conversations_written"] == 1 and d["qa_pairs_written"] == 1' 2>/dev/null; then
  pass "T1 official conversations.json imported"
else
  fail "T1" "$json_out"
fi

if grep -R "怎么把 ChatGPT 问答写入知识库" "$TMP/out/test-json" >/dev/null && \
   grep -R "wiki ingest 抽取" "$TMP/out/test-json" >/dev/null && \
   test -f "$TMP/out/test-json/manifest.json"; then
  pass "T2 markdown and manifest written"
else
  fail "T2" "expected markdown content or manifest missing"
fi

cat > "$TMP/transcript.md" <<'MD'
### User
Solar 怎么默认先查知识库？

### Assistant
在执行架构设计、技术研究和方案分析前，先运行 context inject，并把命中的上下文注入回答。
MD

text_out="$(python3 "$SCRIPT" --source "$TMP/transcript.md" --out-root "$TMP/out" --batch-id test-text --no-dispatch --json)"
if echo "$text_out" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["ok"] and d["conversations_written"] == 1 and d["qa_pairs_written"] == 1' 2>/dev/null; then
  pass "T3 markdown transcript imported"
else
  fail "T3" "$text_out"
fi

if grep -R "Solar 怎么默认先查知识库" "$TMP/out/test-text" >/dev/null; then
  pass "T4 transcript content preserved"
else
  fail "T4" "transcript markdown missing expected question"
fi

mkdir -p "$TMP/vault"
dispatch_out="$(OBSIDIAN_VAULT_PATH="$TMP/vault" HARNESS_TEST=1 python3 "$SCRIPT" --source "$TMP/transcript.md" --out-root "$TMP/out" --batch-id test-dispatch --json)"
dispatch_path="$(echo "$dispatch_out" | python3 -c 'import json,sys; d=json.load(sys.stdin); lines=[x.strip() for x in d.get("dispatch_output","").splitlines() if x.strip()]; print(lines[-1] if lines else "")' 2>/dev/null || true)"
if [[ -n "$dispatch_path" && -f "$dispatch_path" ]] && \
   grep -q "project=chatgpt" "$dispatch_path" && \
   grep -q "^status: pending" "$dispatch_path"; then
  pass "T5 default dispatch writes isolated pending wiki ingest instruction"
else
  fail "T5" "dispatch missing or invalid: $dispatch_out"
fi

stdin_out="$(printf 'User: 从当前 ChatGPT 页面复制后怎么导入？\nAssistant: 复制页面文本后通过 --source - 从标准输入导入，或者用 --clipboard 读取剪贴板。\n' | python3 "$SCRIPT" --source - --out-root "$TMP/out" --batch-id test-stdin --no-dispatch --json)"
if echo "$stdin_out" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["ok"] and d["source"] == "stdin" and d["conversations_written"] == 1' 2>/dev/null; then
  pass "T6 stdin transcript imported"
else
  fail "T6" "$stdin_out"
fi

cat > "$TMP/browser-capture.json" <<'JSON'
{
  "source": "browser",
  "url": "https://chatgpt.com/c/test",
  "title": "ChatGPT - Solar import",
  "messages": [
    {"role": "user", "text": "能不能从当前 ChatGPT 标签页直接导入？"},
    {"role": "assistant", "text": "可以，通过浏览器只读抓取当前标签页的 user/assistant 消息，然后进入知识库派单。"}
  ]
}
JSON
browser_json_out="$(python3 "$SCRIPT" --source "$TMP/browser-capture.json" --out-root "$TMP/out" --batch-id test-browser-json --no-dispatch --json)"
if echo "$browser_json_out" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["ok"] and d["conversations_written"] == 1 and d["qa_pairs_written"] == 1' 2>/dev/null; then
  pass "T7 browser capture JSON imported"
else
  fail "T7" "$browser_json_out"
fi

cat > "$TMP/browser-all.json" <<'JSON'
[
  {
    "source": "browser",
    "url": "https://chatgpt.com/c/test-1",
    "title": "ChatGPT - Tab 1",
    "messages": [
      {"role": "user", "text": "第一个 ChatGPT 标签页怎么入库？"},
      {"role": "assistant", "text": "扫描全部已打开的 ChatGPT 对话标签页，并将每个对话写成独立 markdown。"}
    ]
  },
  {
    "source": "browser",
    "url": "https://chatgpt.com/c/test-2",
    "title": "ChatGPT - Tab 2",
    "messages": [
      {"role": "user", "text": "第二个 ChatGPT 标签页也能一起导入吗？"},
      {"role": "assistant", "text": "可以，browser-all 会把同一浏览器里所有 ChatGPT conversation tab 写进同一个 batch。"}
    ]
  }
]
JSON
browser_all_out="$(python3 "$SCRIPT" --source "$TMP/browser-all.json" --out-root "$TMP/out" --batch-id test-browser-all --no-dispatch --json)"
if echo "$browser_all_out" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["ok"] and d["conversations_written"] == 2 and d["qa_pairs_written"] == 2' 2>/dev/null; then
  pass "T8 browser-all capture JSON imported"
else
  fail "T8" "$browser_all_out"
fi

cat > "$TMP/partial-browser.json" <<'JSON'
{
  "source": "browser",
  "url": "https://chatgpt.com/c/partial",
  "title": "ChatGPT - Partial",
  "messages": [
    {"role": "assistant", "text": "企业软件会从人填表的 SaaS 迁移到 agent 执行的工作流系统，核心价值从表单系统转向上下文、权限、审计和自动化控制面。"}
  ]
}
JSON
partial_out="$(python3 "$SCRIPT" --source "$TMP/partial-browser.json" --out-root "$TMP/out" --batch-id test-partial --no-dispatch --json)"
if echo "$partial_out" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["ok"] and d["conversations_written"] == 1 and d["qa_pairs_written"] == 0' 2>/dev/null && \
   grep -R "partial_transcript: true" "$TMP/out/test-partial" >/dev/null && \
   grep -R "企业软件会从人填表" "$TMP/out/test-partial" >/dev/null; then
  pass "T9 partial one-sided capture preserved"
else
  fail "T9" "$partial_out"
fi

hint_ok="$(python3 - <<'PY'
import importlib.util
from pathlib import Path
script = Path.home() / ".solar/harness/lib/chatgpt-conversation-ingest.py"
spec = importlib.util.spec_from_file_location("chatgpt_importer", script)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
hint = mod.browser_capture_hint(["chrome: AppleScript 执行 JavaScript 的功能已关闭"])
print("ok" if "Allow JavaScript from Apple Events" in hint and "conversations.json" in hint else "bad")
PY
)"
if [[ "$hint_ok" == "ok" ]]; then
  pass "T10 browser permission error has actionable hint"
else
  fail "T10" "missing actionable browser hint"
fi

cat > "$TMP/rich-browser.json" <<'JSON'
{
  "source": "chrome-extension",
  "capture_schema_version": 2,
  "url": "https://chatgpt.com/c/rich",
  "canonical_url": "https://chatgpt.com/c/rich",
  "conversation_id": "rich",
  "title": "ChatGPT - Rich Capture",
  "captured_at": "2026-05-21T10:00:00Z",
  "capture_method": "chatgpt-role-attribute",
  "content_hash": "hash-rich-capture",
  "selected_text": "关键选中文本",
  "metadata": {"site_name": "ChatGPT", "language": "zh-CN"},
  "messages": [
    {"turn_index": 1, "message_id": "m-user", "role": "user", "text": "如何保存 ChatGPT 网页？"},
    {"turn_index": 2, "message_id": "m-assistant", "role": "assistant", "text": "插件应该抓取结构化消息、来源 URL、内容 hash，并写入知识库 raw ingest。"}
  ]
}
JSON
rich_out="$(python3 "$SCRIPT" --source "$TMP/rich-browser.json" --out-root "$TMP/out" --batch-id test-rich-browser --no-dispatch --json)"
if echo "$rich_out" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["ok"] and d["conversations_written"] == 1 and d["files"][0]["content_hash"] == "hash-rich-capture"' 2>/dev/null && \
   grep -R "capture_schema_version: \"2\"" "$TMP/out/test-rich-browser" >/dev/null && \
   grep -R "content_hash: \"hash-rich-capture\"" "$TMP/out/test-rich-browser" >/dev/null && \
   grep -R "## Capture Metadata" "$TMP/out/test-rich-browser" >/dev/null && \
   grep -R "## Full Transcript" "$TMP/out/test-rich-browser" >/dev/null && \
   grep -R "m-assistant" "$TMP/out/test-rich-browser" >/dev/null; then
  pass "T11 rich browser capture metadata preserved"
else
  fail "T11" "$rich_out"
fi

if bash -n "$HOME/.solar/harness/solar-harness.sh"; then
  pass "T12 solar-harness shell syntax ok"
else
  fail "T12" "bash -n failed"
fi

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
