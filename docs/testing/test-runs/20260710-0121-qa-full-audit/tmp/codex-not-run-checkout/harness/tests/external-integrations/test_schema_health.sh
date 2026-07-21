#!/usr/bin/env bash
# test_schema_health.sh — Validate health probe JSON against schema

set -euo pipefail
HARNESS="${HARNESS_DIR:-$HOME/.solar/harness}"
HEALTH="$HARNESS/lib/external-integrations-health.py"
SCHEMA="$HARNESS/schemas/integrations.schema.json"
PASS=0; FAIL=0

check() {
    local desc="$1" result="$2"
    if [ "$result" = "ok" ]; then
        echo "  ✓ $desc"; PASS=$((PASS+1))
    else
        echo "  ✗ $desc: $result"; FAIL=$((FAIL+1))
    fi
}

echo "=== test_schema_health ==="

# T1: probe outputs valid JSON
JSON=$(python3 "$HEALTH" --json 2>/dev/null) || { echo "FAIL: probe exit non-zero"; exit 1; }
check "probe outputs valid JSON" "$(python3 -c "import json,sys; json.loads(sys.stdin.read()); print('ok')" <<< "$JSON" 2>/dev/null || echo 'invalid JSON')"

# T2: required top-level keys present
check "generated_at present" "$(python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print('ok' if 'generated_at' in d else 'missing')" <<< "$JSON")"
check "summary present" "$(python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print('ok' if 'summary' in d else 'missing')" <<< "$JSON")"
check "integrations array present" "$(python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print('ok' if isinstance(d.get('integrations'), list) else 'missing')" <<< "$JSON")"

# T3: integration catalog includes the current required set.
check "required integrations present" "$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
names={i.get('name') for i in d['integrations']}
required={'Ar9av/obsidian-wiki','opendatalab/MinerU-Document-Explorer','QMD semantic search/embed','mermaid-js/mermaid','openai/symphony','strukto-ai/mirage','camel-ai/owl','Microsoft MarkItDown MCP','agency-agents persona','Google Drive mount'}
missing=required-names
print('ok' if not missing and len(d['integrations'])>=len(required) else f'missing={sorted(missing)} total={len(d[\"integrations\"])}')
" <<< "$JSON")"

# T4: every integration has all 6-state fields
check "all integrations have 6-state fields" "$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
required={'installed','configured','running','indexed','used_by_default','degraded_reason'}
for it in d['integrations']:
    missing = required - set(it.keys())
    if missing:
        print(f'missing {missing} in {it[\"name\"]}'); sys.exit()
print('ok')
" <<< "$JSON")"

# T5: status enum values
check "status values are ok/warn/error/missing" "$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
valid={'ok','warn','error','missing'}
bad=[it['name'] for it in d['integrations'] if it.get('status') not in valid]
print('ok' if not bad else f'bad status: {bad}')
" <<< "$JSON")"

# T5b: every integration has detailed health dimensions
check "all integrations have detailed health dimensions" "$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
required={'basic_available','default_available','complete_closed_loop','dead_ends'}
for it in d['integrations']:
    h=it.get('health') or {}
    missing=required-set(h)
    if missing:
        print(f'missing {missing} in {it[\"name\"]}'); sys.exit()
print('ok')
" <<< "$JSON")"

# T6: summary counts match integration statuses
check "summary counts match integrations" "$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
ints=d['integrations']
sm=d['summary']
ok_n=sum(1 for i in ints if i['status']=='ok')
warn_n=sum(1 for i in ints if i['status']=='warn')
err_n=sum(1 for i in ints if i['status']=='error')
miss_n=sum(1 for i in ints if i['status']=='missing')
if sm['ok']==ok_n and sm['warn']==warn_n and sm.get('error',0)==err_n and sm['missing']==miss_n:
    print('ok')
else:
    print(f'mismatch: summary={sm} vs computed ok={ok_n} warn={warn_n} error={err_n} miss={miss_n}')
" <<< "$JSON")"

# T7: schema file exists and is valid JSON
check "schema file exists" "$([ -f "$SCHEMA" ] && echo ok || echo missing)"
check "schema is valid JSON" "$(python3 -c "import json; json.load(open('$SCHEMA')); print('ok')" 2>/dev/null || echo invalid)"

echo ""
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
