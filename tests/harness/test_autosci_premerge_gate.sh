#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON:-python3}"
if [[ -z "${GITHUB_ACTIONS:-}" && -x "harness/bin/python3" ]]; then
  PYTHON_BIN="harness/bin/python3"
fi

export PYTHONPATH="harness${PYTHONPATH:+:$PYTHONPATH}"
export SOLAR_GRAPH_BUILDER_OPERATOR_POOL="${SOLAR_GRAPH_BUILDER_OPERATOR_POOL:-0}"
export SOLAR_OPERATORD_ONCE_MAX_WAIT_SECONDS="${SOLAR_OPERATORD_ONCE_MAX_WAIT_SECONDS:-20}"
export AUTOSCI_DISABLE_NETWORK_FETCH="${AUTOSCI_DISABLE_NETWORK_FETCH:-1}"

echo "::group::AutoSci premerge syntax checks"
bash -n harness/solar-harness.sh
"$PYTHON_BIN" -m py_compile \
  harness/plugins/autosci/bin/autosci_skill_shim.py \
  tests/harness/integration/autosci_product_smoke_helpers.py \
  tests/harness/integration/test_autosci_routes_list.py \
  tests/harness/integration/test_autosci_cli_dispatch.py \
  tests/harness/integration/test_autosci_ingest_demo.py \
  tests/harness/integration/test_autosci_review_demo.py \
  tests/harness/integration/test_autosci_research_scheduler_demo.py \
  tests/harness/integration/test_autosci_artifact_root.py \
  tests/harness/test_autosci_phase_c_premerge_readiness.py \
  tests/harness/test_autosci_phase_c_unification_contracts.py
echo "::endgroup::"

echo "::group::AutoSci Phase C readiness contracts"
"$PYTHON_BIN" -m pytest -q \
  tests/harness/test_autosci_phase_c_premerge_readiness.py \
  tests/harness/test_autosci_phase_c_unification_contracts.py
echo "::endgroup::"

echo "::group::AutoSci product-level smoke tests"
"$PYTHON_BIN" -m pytest -q \
  tests/harness/integration/test_autosci_routes_list.py \
  tests/harness/integration/test_autosci_cli_dispatch.py \
  tests/harness/integration/test_autosci_ingest_demo.py \
  tests/harness/integration/test_autosci_review_demo.py \
  tests/harness/integration/test_autosci_research_scheduler_demo.py \
  tests/harness/integration/test_autosci_artifact_root.py
echo "::endgroup::"

echo "::group::AutoSci scheduler demo shim tests"
"$PYTHON_BIN" -m pytest -q \
  tests/plugins/autosci/test_autosci_skill_shim.py::test_autosci_skill_shim_research_scheduler_run_attaches_blocked_summary \
  tests/plugins/autosci/test_autosci_skill_shim.py::test_autosci_skill_shim_research_scheduler_demo_uses_multi_node_preset
echo "::endgroup::"

echo "::group::AutoSci generated artifact tracking guard"
for pattern in \
  "harness/artifacts/autosci/runs/*" \
  "harness/artifacts/autosci/operator-smoke/*" \
  "harness/artifacts/autosci/phase19/current-parity-inventory-*.json" \
  "harness/artifacts/scientific/workflow-runs/*"
do
  tracked="$(git ls-files "$pattern")"
  if [[ -n "$tracked" ]]; then
    echo "Generated artifacts are tracked for pattern: $pattern" >&2
    echo "$tracked" >&2
    exit 1
  fi
done
echo "::endgroup::"

echo "::group::Git object connectivity"
git fsck --connectivity-only --no-dangling
echo "::endgroup::"

echo "PASS AutoSci premerge gate"
