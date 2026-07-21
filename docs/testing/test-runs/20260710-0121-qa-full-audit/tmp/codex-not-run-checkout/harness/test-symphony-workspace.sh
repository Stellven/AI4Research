#!/usr/bin/env bash
# Test: workspace creation and verification
set -eu

HARNESS_DIR="$HOME/.solar/harness"
WS_MGR="$HARNESS_DIR/lib/symphony/workspace-manager.sh"
TEST_SID="sprint-test-workspace-001"

echo "=== Test: Symphony Workspace Manager ==="

# Cleanup from previous run
bash "$WS_MGR" clean "$TEST_SID" 2>/dev/null || true

# Test 1: Create workspace
echo -n "Test 1: Create workspace... "
ws_dir=$(bash "$WS_MGR" create "$TEST_SID" 2>&1)
if [[ -d "$ws_dir" ]]; then
  echo "PASS ($ws_dir)"
else
  echo "FAIL"
  exit 1
fi

# Test 2: .solar-sprint-id exists
echo -n "Test 2: .solar-sprint-id exists... "
if [[ -f "${ws_dir}/.solar-sprint-id" ]]; then
  content=$(cat "${ws_dir}/.solar-sprint-id")
  if [[ "$content" == "$TEST_SID" ]]; then
    echo "PASS"
  else
    echo "FAIL (content: $content)"
    exit 1
  fi
else
  echo "FAIL"
  exit 1
fi

# Test 3: WORKFLOW.md exists
echo -n "Test 3: WORKFLOW.md exists... "
if [[ -f "${ws_dir}/WORKFLOW.md" ]]; then
  echo "PASS"
else
  echo "FAIL"
  exit 1
fi

# Test 4: proof/ and logs/ directories exist
echo -n "Test 4: proof/ and logs/ dirs exist... "
if [[ -d "${ws_dir}/proof" ]] && [[ -d "${ws_dir}/logs" ]]; then
  echo "PASS"
else
  echo "FAIL"
  exit 1
fi

# Test 5: Workspace is NOT inside project root
echo -n "Test 5: Not inside project root... "
project_root="$HOME/.solar/harness"
if [[ "$ws_dir" != "$project_root"* ]]; then
  echo "PASS"
else
  echo "FAIL (workspace inside harness)"
  exit 1
fi

# Cleanup
bash "$WS_MGR" clean "$TEST_SID" 2>/dev/null

echo ""
echo "=== All workspace tests PASSED ==="
