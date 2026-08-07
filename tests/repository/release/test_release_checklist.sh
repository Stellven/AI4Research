#!/usr/bin/env bash
# Contract test for the owner-only rc.9 publication instructions.
set -eu

repo_dir="$(cd "$(dirname "$0")/../../.." && pwd)"
doc="$repo_dir/docs/RELEASE-CHECKLIST.md"

grep -Fq 'VERSION=1.0.0-rc.9' "$doc"
grep -Fq 'PYPI_VERSION=1.0.0rc9' "$doc"
grep -Fq 'TAG=v1.0.0-rc.9' "$doc"
grep -Fq 'RELEASE_BRANCH=release/v1.0.0-rc.9' "$doc"
grep -Fq -- '--repo suraj-subrahmanyan/OpenSolar' "$doc"
grep -Fq 'bash tests/repository/release/test_release_cut_safety.sh' "$doc"
grep -Fq 'bash tests/repository/release/test_release_public_tree.sh' "$doc"
grep -Fiq 'do not attach' "$doc"
grep -Fiq '.dmg' "$doc"
grep -Fiq '.exe' "$doc"

if grep -Fq 'models.claude_auth_note' "$doc"; then
    echo "FAIL: checklist requires the removed Claude-only doctor field models.claude_auth_note" >&2
    exit 1
fi

grep -Fq 'runtime.selected' "$doc"
grep -Fq 'runtime.cli' "$doc"
grep -Fq 'runtime.auth' "$doc"
grep -Fq 'runtime.guidance' "$doc"
grep -Fq 'runtime.login_command' "$doc"

while IFS= read -r script; do
    [ -f "$repo_dir/$script" ] || {
        echo "FAIL: checklist references missing script: $script" >&2
        exit 1
    }
done <<EOF
$(sed -n 's/^[[:space:]]*bash \(\(scripts\|tests\)\/[^[:space:]]*\.sh\).*/\1/p' "$doc" | sort -u)
EOF

if grep -Eq 'Stellven/OpenSolar|1\.0\.0-rc\.6|1\.0\.0rc3|git switch "\$RELEASE_BRANCH"' "$doc"; then
    echo "FAIL: checklist contains a stale version, upstream target, or unsafe release-branch checkout" >&2
    exit 1
fi

echo "release checklist contract passed: rc.9, origin-only, valid gates, safe review, scoped artifacts"
