#!/usr/bin/env bash
# run-all.sh — Run all external integrations tests

set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOTAL_PASS=0; TOTAL_FAIL=0

run_test() {
    local script="$1"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    bash "$script"
    local exit_code=$?
    if [ $exit_code -eq 0 ]; then
        echo "  → SUITE PASS: $(basename "$script")"
        ((TOTAL_PASS++))
    else
        echo "  → SUITE FAIL: $(basename "$script")"
        ((TOTAL_FAIL++))
    fi
}

echo "========================================"
echo " External Integrations Test Suite"
echo "========================================"

chmod +x "$DIR"/test_*.sh

run_test "$DIR/test_schema_health.sh"
run_test "$DIR/test_wording_flags.sh"
run_test "$DIR/test_audit_uploads.sh"
run_test "$DIR/test_upload_ingest_coverage.sh"
run_test "$DIR/test_endpoint_view.sh"
run_test "$DIR/../integrations/test-capability-plane-e2e.sh"
run_test "$DIR/../integrations/test-expanded-capability-plane-e2e.sh"
run_test "$DIR/../integrations/test-capability-fusion-benchmark.sh"
run_test "$DIR/../integrations/test-platform-workflow-benchmark.sh"

echo ""
echo "========================================"
echo " TOTAL: $TOTAL_PASS suites passed, $TOTAL_FAIL suites failed"
echo "========================================"
[ "$TOTAL_FAIL" -eq 0 ]
