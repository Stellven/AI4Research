#!/usr/bin/env bash
# Solar Harness — integrate parallel builder worktrees back into the main repo.
set -eu

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
SPRINTS_DIR="${SPRINTS_DIR:-$HARNESS_DIR/sprints}"
STATE_FILE="$HARNESS_DIR/state/parallel-builder-lab.env"

sid="${1:-}"
repo_root="${2:-${SOLAR_PARALLEL_ROOT:-}}"

if [[ -z "$sid" ]]; then
  echo "Usage: parallel-integrate.sh <sprint-id> [repo-root]" >&2
  exit 2
fi

if [[ -z "$repo_root" && -f "$STATE_FILE" ]]; then
  repo_root=$(sed -n "s/^WORK_DIR='//p" "$STATE_FILE" | sed "s/'$//" | head -1)
fi

if [[ -z "$repo_root" ]]; then
  repo_root="$(pwd)"
fi

report="$SPRINTS_DIR/${sid}.parallel-integrate.md"
mkdir -p "$SPRINTS_DIR"

write_header() {
  {
    echo "# Parallel Integrate — ${sid}"
    echo ""
    echo "- repo_root: ${repo_root}"
    echo "- started_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo ""
  } > "$report"
}

append_report() {
  printf '%s\n' "$*" >> "$report"
}

fail() {
  append_report ""
  append_report "## Result"
  append_report "FAIL: $*"
  echo "[parallel-integrate] $*" >&2
  exit 1
}

write_header

if ! command -v git >/dev/null 2>&1; then
  fail "git not found"
fi

if ! git -C "$repo_root" rev-parse --show-toplevel >/dev/null 2>&1; then
  fail "repo_root is not a git repository: $repo_root"
fi

repo_root=$(git -C "$repo_root" rev-parse --show-toplevel)

if ! git -C "$repo_root" diff --quiet -- . || ! git -C "$repo_root" diff --cached --quiet -- .; then
  fail "main repo has uncommitted changes; refusing to integrate into dirty tree"
fi

mapfile -t worktrees < <(
  git -C "$repo_root" worktree list --porcelain \
    | awk '/^worktree / {print substr($0, 10)}' \
    | grep -E '/\.worktrees/(builder|lab-builder-[0-9]+)$' \
    | sort
)

if [[ "${#worktrees[@]}" -eq 0 ]]; then
  append_report "## Result"
  append_report "NOOP: no parallel builder worktrees found"
  echo "[parallel-integrate] no builder worktrees found"
  exit 0
fi

append_report "## Worktrees"
for wt in "${worktrees[@]}"; do
  append_report "- ${wt}"
done
append_report ""
append_report "## Steps"

integrated=0
skipped=0

for wt in "${worktrees[@]}"; do
  slot=$(basename "$wt")
  branch=$(git -C "$wt" branch --show-current 2>/dev/null || true)
  if [[ -z "$branch" ]]; then
    append_report "- ${slot}: skipped, detached HEAD"
    skipped=$((skipped + 1))
    continue
  fi

  if [[ -n "$(git -C "$wt" status --porcelain)" ]]; then
    git -C "$wt" add -A
    if ! git -C "$wt" diff --cached --quiet -- .; then
      git -C "$wt" \
        -c user.name="${GIT_AUTHOR_NAME:-Solar Harness}" \
        -c user.email="${GIT_AUTHOR_EMAIL:-solar-harness@local}" \
        commit -m "harness: ${sid} ${slot} handoff" >/dev/null
      append_report "- ${slot}: committed pending work on ${branch}"
    fi
  fi

  if git -C "$repo_root" merge-base --is-ancestor "$branch" HEAD 2>/dev/null; then
    append_report "- ${slot}: skipped, ${branch} already merged"
    skipped=$((skipped + 1))
    continue
  fi

  if git -C "$repo_root" merge --no-ff --no-commit "$branch" >/tmp/solar-parallel-merge.out 2>&1; then
    git -C "$repo_root" \
      -c user.name="${GIT_AUTHOR_NAME:-Solar Harness}" \
      -c user.email="${GIT_AUTHOR_EMAIL:-solar-harness@local}" \
      commit -m "harness: integrate ${slot} for ${sid}" >/dev/null
    append_report "- ${slot}: merged ${branch}"
    integrated=$((integrated + 1))
  else
    merge_output=$(cat /tmp/solar-parallel-merge.out 2>/dev/null || true)
    git -C "$repo_root" merge --abort >/dev/null 2>&1 || true
    append_report "- ${slot}: conflict while merging ${branch}"
    append_report ""
    append_report "### Merge Output"
    append_report '```text'
    append_report "$merge_output"
    append_report '```'
    fail "merge conflict integrating ${slot}; main tree restored with git merge --abort"
  fi
done

append_report ""
append_report "## Result"
append_report "PASS: integrated=${integrated}, skipped=${skipped}"
echo "[parallel-integrate] PASS integrated=${integrated} skipped=${skipped}"
