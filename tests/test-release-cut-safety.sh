#!/usr/bin/env bash
# Regression: an executed public cut must import the already-verified scratch
# commit without checking out or staging the owner's development worktree.
set -eu

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/solar-release-cut-test.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

fixture="$tmp/repo"
git clone -q --no-local "$repo_dir" "$fixture"
cp "$repo_dir/scripts/release-cut.sh" "$fixture/scripts/release-cut.sh"
cp "$repo_dir/release-exclude.txt" "$fixture/release-exclude.txt"
git -C "$fixture" config user.name "Solar release test"
git -C "$fixture" config user.email "release-test@example.invalid"

mkdir -p "$tmp/bin"
printf '%s\n' '#!/usr/bin/env sh' 'exit 0' >"$tmp/bin/gitleaks"
chmod +x "$tmp/bin/gitleaks"

sentinel="$fixture/OWNER-UNTRACKED-DO-NOT-PUBLISH.txt"
printf '%s\n' 'owner scratch data' >"$sentinel"
before_branch="$(git -C "$fixture" branch --show-current)"
before_status="$(git -C "$fixture" status --porcelain=v1 --untracked-files=all)"

if ! (
    cd "$fixture"
    PATH="$tmp/bin:$PATH" bash scripts/release-cut.sh \
        --source HEAD \
        --branch release/test-safe-cut \
        --exclude-file release-exclude.txt \
        --execute
) >"$tmp/release-cut.log" 2>&1; then
    tail -80 "$tmp/release-cut.log" >&2
    echo "FAIL: release-cut execution failed before safety assertions" >&2
    exit 1
fi

after_branch="$(git -C "$fixture" branch --show-current)"
after_status="$(git -C "$fixture" status --porcelain=v1 --untracked-files=all)"

test "$after_branch" = "$before_branch" || {
    echo "FAIL: execute changed the checked-out branch: $before_branch -> $after_branch" >&2
    exit 1
}
test -f "$sentinel" || {
    echo "FAIL: execute deleted the owner's untracked file" >&2
    exit 1
}
test "$after_status" = "$before_status" || {
    echo "FAIL: execute changed the development worktree status" >&2
    printf 'before:\n%s\nafter:\n%s\n' "$before_status" "$after_status" >&2
    exit 1
}
test -z "$(git -C "$fixture" ls-tree -r --name-only release/test-safe-cut -- OWNER-UNTRACKED-DO-NOT-PUBLISH.txt)" || {
    echo "FAIL: release branch contains the owner's untracked file" >&2
    exit 1
}
test "$(git -C "$fixture" rev-list --count release/test-safe-cut)" = "1" || {
    echo "FAIL: release branch is not a single-commit orphan" >&2
    exit 1
}

echo "release-cut safety passed: verified commit imported without touching owner worktree"
