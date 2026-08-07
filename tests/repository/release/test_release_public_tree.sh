#!/usr/bin/env bash
# Regression: private operational worklogs and usage reports are never public
# release content, including newly-added files not named in the exclude list.
set -eu

repo_dir="$(cd "$(dirname "$0")/../../.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/solar-release-public-test.XXXXXX")"
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

if ! (
    cd "$fixture"
    PATH="$tmp/bin:$PATH" bash scripts/release-cut.sh \
        --source HEAD \
        --branch release/test-public-tree \
        --exclude-file release-exclude.txt \
        --execute
) >"$tmp/normal.log" 2>&1; then
    tail -80 "$tmp/normal.log" >&2
    echo "FAIL: normal public-tree cut did not pass" >&2
    exit 1
fi

for private_path in DESIGN_WORKLOG.md docs/CLAUDE_USAGE_REPORT.md; do
    test -z "$(git -C "$fixture" ls-tree -r --name-only release/test-public-tree -- "$private_path")" || {
        echo "FAIL: public release contains private operational document: $private_path" >&2
        exit 1
    }
done

printf '%s\n' '# Private session usage report' >"$fixture/docs/SESSION_USAGE_REPORT.md"
git -C "$fixture" add docs/SESSION_USAGE_REPORT.md
git -C "$fixture" commit -q -m "test fixture: plant private usage report"

if (
    cd "$fixture"
    PATH="$tmp/bin:$PATH" bash scripts/release-cut.sh \
        --source HEAD \
        --branch release/test-private-detection \
        --exclude-file release-exclude.txt
) >"$tmp/negative.log" 2>&1; then
    echo "FAIL: release gate accepted a newly planted private usage report" >&2
    exit 1
fi
grep -q "private operational" "$tmp/negative.log" || {
    tail -80 "$tmp/negative.log" >&2
    echo "FAIL: planted private report failed for an unexpected reason" >&2
    exit 1
}

echo "release public-tree privacy passed: operational reports excluded and fail closed"
