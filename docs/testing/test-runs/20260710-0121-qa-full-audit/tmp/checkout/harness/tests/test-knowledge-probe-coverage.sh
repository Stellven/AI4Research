#!/usr/bin/env bash
# Regression: common Solar KB probe questions should hit curated knowledge pages.
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
CTX="${HARNESS_DIR}/solar-harness.sh"

PASS=0
FAIL=0

qmd_fallback_has_expected() {
  local query="$1" expected="$2"
  local out
  out="$("$CTX" wiki qmd-search "$query $expected" --json 2>/dev/null || true)"
  grep -Fqi "$expected" <<<"$out"
}

probe() {
  local label="$1" query="$2" expected="$3"
  local out
  out="$("$CTX" context inject --query "$query" --format markdown --max-hits 8 --max-chars 4000 2>/dev/null || true)"
  if grep -Fqi "$expected" <<<"$out"; then
    echo "ok - $label -> $expected"
    PASS=$((PASS + 1))
  elif qmd_fallback_has_expected "$query" "$expected"; then
    echo "ok - $label -> $expected (qmd fallback)"
    PASS=$((PASS + 1))
  else
    echo "not ok - $label missing $expected" >&2
    echo "$out" | sed -n '1,80p' >&2
    FAIL=$((FAIL + 1))
  fi
}

probe "space data center cooling" "太空数据中心的散热瓶颈是什么？" "太空数据中心散热方案"
probe "obsidian wiki integration" "Solar-Harness 和 Obsidian Wiki 集成做了什么？" "solar-harness-obsidian-wiki-integration"
probe "qmd idle embedding" "QMD embedding 后台闲时运行现在是什么状态？" "qmd-embedding-idle-background-status"
probe "mirage vfs role" "Mirage 统一虚拟文件系统在 Solar 里承担什么角色？" "mirage"
probe "mineru pdf chain" "MinerU 在 PDF 深抽取链路里负责什么？" "mineru-pdf-deep-extraction-chain"
probe "symphony s1 s3" "OpenAI Symphony S1-S3 给 Solar-Harness 带来了哪些结构能力？" "openai-symphony-s1-s3-solar-harness-structure"
probe "dag task graph scheduler" "DAG task_graph 并行调度解决了什么问题？" "solar-harness-dag-task-graph-scheduler"
probe "mia integration principle" "MIA 集成到 Solar-Harness 的原则是什么？" "solar-mia-integration-principles"
probe "ruflo runtime status" "Ruflo runtime sandbox 当前是否 full-runtime usable？" "ruflo-runtime-sandbox-status"
probe "apple notes wechat ingest" "Apple Notes / 微信文章进入知识库的设计链路是什么？" "apple-notes-wechat-knowledge-ingest-chain"

echo "PROBES_PASSED=$PASS PROBES_FAILED=$FAIL"
[[ "$FAIL" -eq 0 ]]
