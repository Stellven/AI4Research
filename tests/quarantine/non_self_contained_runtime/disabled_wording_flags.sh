#!/usr/bin/env bash
# test_wording_flags.sh — Verify integration wording correctness (D6/D7/D8)

set -euo pipefail
HARNESS="${HARNESS_DIR:-$HOME/.solar/harness}"
HEALTH="$HARNESS/lib/external-integrations-health.py"
PASS=0; FAIL=0

check() {
    local desc="$1" result="$2"
    if [ "$result" = "ok" ]; then
        echo "  ✓ $desc"; PASS=$((PASS+1))
    else
        echo "  ✗ $desc: $result"; FAIL=$((FAIL+1))
    fi
}

echo "=== test_wording_flags ==="

JSON=$(python3 "$HEALTH" --json 2>/dev/null)

# D6: Mirage — sdk.kind = solar-logical, drive.state reflects either local File Provider or headless credentials.
check "Mirage sdk.kind=solar-logical" "$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
m=next((i for i in d['integrations'] if 'mirage' in i['name'].lower()), None)
if not m: print('not found'); sys.exit()
sdk=m.get('evidence',{}).get('sdk',{})
print('ok' if sdk.get('kind')=='solar-logical' else f'got {sdk}')
" <<< "$JSON")"

check "Mirage drive.state is current enum" "$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
m=next((i for i in d['integrations'] if 'mirage' in i['name'].lower()), None)
drv=m.get('evidence',{}).get('drive',{})
print('ok' if drv.get('state') in {'local_mount','credentials_missing','logical_mount'} else f'got {drv}')
" <<< "$JSON")"

# D7: Symphony — mode=dry_run_sidecar, executes_builders=False
check "Symphony mode=dry_run_sidecar" "$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
s=next((i for i in d['integrations'] if 'symphony' in i['name'].lower()), None)
ev=s.get('evidence',{})
print('ok' if ev.get('mode')=='dry_run_sidecar' else f'got {ev}')
" <<< "$JSON")"

check "Symphony executes_builders=False" "$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
s=next((i for i in d['integrations'] if 'symphony' in i['name'].lower()), None)
ev=s.get('evidence',{})
print('ok' if ev.get('executes_builders')==False else f'got {ev}')
" <<< "$JSON")"

# D8: OWL — active provider, not default coordinator.
check "OWL connection_status=active provider" "$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
o=next((i for i in d['integrations'] if 'owl' in i['name'].lower()), None)
ev=o.get('evidence',{})
print('ok' if ev.get('connection_status')=='active_capability_provider_not_default_coordinator' else f'got {ev}')
" <<< "$JSON")"

# D8: OWL used_by_default = False
check "OWL used_by_default=False" "$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
o=next((i for i in d['integrations'] if 'owl' in i['name'].lower()), None)
print('ok' if o.get('used_by_default')==False else f'got {o.get(\"used_by_default\")}')
" <<< "$JSON")"

# D8: OWL running is a bool; service presence is allowed but not required for default coordinator.
check "OWL running is bool" "$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
o=next((i for i in d['integrations'] if 'owl' in i['name'].lower()), None)
print('ok' if isinstance(o.get('running'), bool) else f'got {o.get(\"running\")}')
" <<< "$JSON")"

# D7: Symphony running = False (not running builders)
check "Symphony running=False" "$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
s=next((i for i in d['integrations'] if 'symphony' in i['name'].lower()), None)
print('ok' if s.get('running')==False else f'got {s.get(\"running\")}')
" <<< "$JSON")"

echo ""
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
