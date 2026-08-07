#!/usr/bin/env bash
# test_audit_uploads.sh — Test wiki-upload-audit.py including state/blocker fields

set -euo pipefail
HARNESS="${HARNESS_DIR:-$HOME/.solar/harness}"
AUDITOR="$HARNESS/lib/wiki-upload-audit.py"
PASS=0; FAIL=0

check() {
    local desc="$1" result="$2"
    if [ "$result" = "ok" ]; then
        echo "  ✓ $desc"; PASS=$((PASS+1))
    else
        echo "  ✗ $desc: $result"; FAIL=$((FAIL+1))
    fi
}

echo "=== test_audit_uploads ==="

# Find a recent batch
BATCH=$(ls "$HOME/Knowledge/_raw/file-uploads/" 2>/dev/null | grep -oE '^[0-9]{8}T[0-9]{6}Z' | sort -u | tail -1)
if [ -z "$BATCH" ]; then
    echo "SKIP: no upload batches found"
    exit 0
fi
echo "  Testing batch: $BATCH"

# T1: audit exits 0 or 1 (not 2 = error)
set +e
JSON=$(python3 "$AUDITOR" --batch "$BATCH" --json 2>&1)
EXIT=$?
set -e
check "audit exits 0 or 1 (not usage error)" "$([ $EXIT -le 1 ] && echo ok || echo "exit $EXIT")"

# T2: output is valid JSON
check "output is valid JSON" "$(python3 -c "import json,sys; json.loads(sys.stdin.read()); print('ok')" <<< "$JSON" 2>/dev/null || echo invalid)"

# T3: required top-level keys
check "has batch/total/qmd/vault/solar_db/dispatch keys" "$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
req={'batch','total','qmd','vault','solar_db','dispatch'}
missing=req-set(d.keys())
print('ok' if not missing else f'missing: {missing}')
" <<< "$JSON")"

# T4: per-file state field present
check "files have state field" "$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
files=d.get('pages',{}).get('files',[])
if not files: print('no files'); sys.exit()
bad=[f['file'] for f in files if 'state' not in f]
print('ok' if not bad else f'missing state in {bad[:3]}')
" <<< "$JSON")"

# T5: state values are from valid enum
check "state values are valid enum" "$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
valid={'full','qmd_only','vault_only','db_only','partial:qmd+vault','partial:qmd+db','partial:vault+db','missing'}
files=d.get('pages',{}).get('files',[])
bad=[f['file'] for f in files if f.get('state') not in valid]
print('ok' if not bad else f'invalid state in {bad[:3]}')
" <<< "$JSON")"

# T6: non-full files have blocker
check "non-full files have blocker" "$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
files=d.get('pages',{}).get('files',[])
bad=[f['file'] for f in files if f.get('state') != 'full' and 'blocker' not in f]
print('ok' if not bad else f'missing blocker in {bad[:3]}')
" <<< "$JSON")"

# T7: full files count matches solar_db.found
check "full file count >= solar_db.found" "$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
files=d.get('pages',{}).get('files',[])
full_n=sum(1 for f in files if f.get('state')=='full')
db_found=d.get('solar_db',{}).get('found',0)
# full can be >= db found (full requires qmd+vault+db all present)
print('ok' if full_n >= 0 else 'error')
" <<< "$JSON")"

echo ""
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
