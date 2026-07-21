#!/bin/bash
# ================================================================
# Solar Harness — Builder Worktree 共享逻辑
# Sprint sprint-20260502-191700 D3
#
# 初始启动和 watchdog 重启后行为一致
#
# @module solar-farm/harness/lib/worktree
# ================================================================

# 设置 builder worktree, 返回 worktree 目录路径 (写到 stdout)
# 用法: WORKTREE_DIR=$(setup_builder_worktree "$work_dir")
setup_builder_worktree() {
  local work_dir="$1"

  # 非 git 仓库 → 不用 worktree
  if ! command -v git &>/dev/null || ! git -C "$work_dir" rev-parse --git-dir &>/dev/null 2>&1; then
    echo ""
    return 0
  fi

  local slot="${SOLAR_BUILDER_SLOT:-builder}"
  slot=$(printf '%s' "$slot" | sed 's/[^A-Za-z0-9._-]/-/g')
  [[ -z "$slot" ]] && slot="builder"
  local worktree_dir="$work_dir/.worktrees/$slot"

  # 复用已有 worktree (watchdog 重启场景)
  if [[ -d "$worktree_dir" ]] && git -C "$work_dir" worktree list 2>/dev/null | grep -q "$worktree_dir"; then
    echo "$worktree_dir"
    return 0
  fi

  # 清理残留目录 (worktree 已移除但目录还在)
  if [[ -d "$worktree_dir" ]]; then
    rm -rf "$worktree_dir" 2>/dev/null || true
  fi

  # 创建新 worktree
  local branch="harness-${slot}-$(date +%Y%m%d-%H%M%S)"
  mkdir -p "$(dirname "$worktree_dir")"

  if git -C "$work_dir" worktree add "$worktree_dir" -b "$branch" >/dev/null 2>&1; then
    echo "$worktree_dir"
  else
    echo ""
  fi
}

# 清理 builder worktree (builder 退出时调用)
# 用法: cleanup_builder_worktree "$worktree_dir" "$original_work_dir"
cleanup_builder_worktree() {
  local worktree_dir="$1"
  local original_dir="$2"

  [[ -z "$worktree_dir" ]] && return 0
  [[ ! -d "$worktree_dir" ]] && return 0

  # 检查是否有未提交的更改
  if git -C "$worktree_dir" diff --quiet 2>/dev/null && git -C "$worktree_dir" diff --cached --quiet 2>/dev/null; then
    # 无更改 → 自动清理
    local branch
    branch=$(git -C "$worktree_dir" branch --show-current 2>/dev/null || echo "")
    cd /
    git -C "$original_dir" worktree remove "$worktree_dir" --force 2>/dev/null || rm -rf "$worktree_dir"
    [[ -n "$branch" ]] && git -C "$original_dir" branch -D "$branch" 2>/dev/null || true
  fi
}
