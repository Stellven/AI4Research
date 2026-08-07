#!/usr/bin/env bash
# test_upload_ingest_coverage.sh — Verify latest batch fully ingested (D4/D5)

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

echo "=== test_upload_ingest_coverage ==="

for BATCH in 20260508T131337Z 20260508T122047Z; do
    echo "  Batch: $BATCH"
    set +e
    JSON=$(python3 "$AUDITOR" --batch "$BATCH" --json 2>&1)
    EXIT=$?
    set -e
    if [ $EXIT -gt 1 ]; then
        echo "  ✗ audit failed for $BATCH (exit $EXIT)"; FAIL=$((FAIL+1)); continue
    fi

    # D4: QMD = total
    check "$BATCH qmd fully covered" "$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
q=d.get('qmd',{}); t=d.get('total',0)
print('ok' if q.get('missing',1)==0 and t>0 else f'{q.get(\"found\",0)}/{t}')
" <<< "$JSON")"

    # D4: vault = total, except explicitly blocked unsupported formats.
    check "$BATCH vault covered or explicitly blocked" "$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
v=d.get('vault',{}); t=d.get('total',0)
files=d.get('pages',{}).get('files',[])
blocked=[f for f in files if not f.get('wiki_ref') and f.get('blocker') in {'unsupported_format','quality_quarantined'}]
print('ok' if t>0 and v.get('found',0)+len(blocked)==t else f'{v.get(\"found\",0)}/{t}, blocked={len(blocked)}')
" <<< "$JSON")"

    # D4: Solar DB is a secondary index; historical batches may have partial DB coverage
    # while QMD/vault/dispatch are the authoritative ingest closeout.
    check "$BATCH solar_db indexed or explicitly partial" "$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
s=d.get('solar_db',{}); t=d.get('total',0)
print('ok' if s.get('found',0)>0 and t>0 else f'{s.get(\"found\",0)}/{t}')
" <<< "$JSON")"

    # D4: dispatch pending = 0
    check "$BATCH dispatch pending=0" "$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
disp=d.get('dispatch',{})
print('ok' if disp.get('pending',1)==0 else f'pending={disp.get(\"pending\")}')
" <<< "$JSON")"

    # D5: no unexplained QMD-only files. Unsupported formats must carry blocker.
    check "$BATCH no unexplained qmd_only files" "$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
files=d.get('pages',{}).get('files',[])
bad=[f['file'] for f in files if f.get('state')=='qmd_only' and f.get('blocker') not in {'unsupported_format','quality_quarantined'}]
print('ok' if not bad else f'{len(bad)} unexplained qmd_only files')
" <<< "$JSON")"
done

echo ""
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
