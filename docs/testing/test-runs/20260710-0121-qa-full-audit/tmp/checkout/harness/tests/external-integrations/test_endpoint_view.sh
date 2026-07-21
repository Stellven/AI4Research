#!/usr/bin/env bash
# test_endpoint_view.sh — Test /integrations and /integrations-view HTTP endpoints

set -euo pipefail
PASS=0; FAIL=0
HOST="http://127.0.0.1:8765"

check() {
    local desc="$1" result="$2"
    if [ "$result" = "ok" ]; then
        echo "  ✓ $desc"; PASS=$((PASS+1))
    else
        echo "  ✗ $desc: $result"; FAIL=$((FAIL+1))
    fi
}

echo "=== test_endpoint_view ==="

# Ensure cache is warm so endpoints respond quickly
HARNESS="${HARNESS_DIR:-$HOME/.solar/harness}"
python3 "$HARNESS/lib/external-integrations-health.py" --json > /dev/null 2>&1 || true

# T1: /integrations returns 200
JSON=$(curl -fsS --max-time 15 "$HOST/integrations" 2>/dev/null) && \
    check "/integrations returns 200" "ok" || check "/integrations returns 200" "timeout or error"

# T2: /integrations JSON includes the current expanded integration catalog.
check "/integrations has expanded integration catalog" "$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
names={i.get('name') for i in d.get('integrations',[])}
required={'Google Drive mount','camel-ai/owl','Microsoft MarkItDown MCP','agency-agents persona'}
missing=required-names
print('ok' if len(d.get('integrations',[])) >= 14 and not missing else f'got {len(d.get(\"integrations\",[]))}, missing={sorted(missing)}')
" <<< "$JSON" 2>/dev/null || echo parse-error)"

# T3: /integrations-view returns 200
VIEW=$(curl -fsS --max-time 15 "$HOST/integrations-view" 2>/dev/null) && \
    check "/integrations-view returns 200" "ok" || check "/integrations-view returns 200" "timeout or error"

# T4: /integrations-view is HTML
check "view is HTML (doctype present)" "$(python3 -c "import sys; s=sys.stdin.read(); print('ok' if '<!doctype html' in s.lower()[:200] else 'missing')" <<< "$VIEW")"

# T5: all major integration names in HTML source (server-side rendered)
check "all major integration names in HTML" "$(echo "$VIEW" | grep -ic -E 'obsidian-wiki|MinerU|QMD|mermaid|symphony|mirage|owl|[Gg]oogle|everything-claude-code|MarkItDown|agency-agents' | awk '{print ($1>=11?"ok":"got " $1)}')"

# T6: /status still works (no regression)
curl -fsS --max-time 5 "$HOST/status" > /dev/null 2>&1 && \
    check "/status endpoint not broken" "ok" || check "/status endpoint not broken" "error"

# T7: /healthz returns ok
HZ=$(curl -fsS --max-time 3 "$HOST/healthz" 2>/dev/null)
check "/healthz returns ok" "$([ "$HZ" = "ok" ] && echo ok || echo "got: $HZ")"

echo ""
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
