# Phase 22 contract-derived L2 test cases

This directory contains the cross-category validator for the Phase 22 L2 case-design manifests under `tests/workflow/`, `tests/foundation/`, and `tests/vertical/`.

The inventory covers 60 previously uncovered L2 features and expands their 180 generic core/guardrail/evidence seed tests into 490 observable atomic scenario specifications. Every included L2 has a nonblank generated contract. No contract-less L2 was included.

The JSON files remain atomic test designs: each identifies its input focus, procedure, oracle, evidence requirement, current implementation surfaces, and source seed test. They are complemented by the executable L2 audit in this directory, which binds every current L2 to a representative core probe or to an explicit no-implementation blocker.

Run the inventory validator with:

`python tests/platform/phase22/test_l2_case_specifications.py`

The validator uses only the Python standard library. A passing validator means the design inventory is structurally complete and traceable; it does not mean the underlying L2 capabilities pass.

## Executable L2 audit

`build_l2_execution_matrix.py` generates `l2_execution_matrix.json`, the complete 142-row L2-to-probe binding. `run_l2_execution_matrix.py` runs each unique probe once in an isolated temporary home and propagates its evidence to the feature-relevant L2 rows. `test_l2_execution_matrix.py` validates matrix completeness, eligibility, and runner structure.

Run the matrix validators with:

`python -m pytest -q tests/platform/phase22/test_l2_execution_matrix.py tests/platform/phase22/test_l2_case_specifications.py`

Run the executable audit with:

`python tests/platform/phase22/run_l2_execution_matrix.py --output-dir outputs/phase22_l2_execution`

The three-state result is intentionally a representative-core-test classification, not exhaustive proof of every atomic scenario:

- Class 1: a direct current implementation exists and its representative probe passed.
- Class 2: a direct current implementation exists, but its probe failed, including assertion, dependency, platform, or runner failures after a valid invocation.
- Class 3: no direct core implementation exists, so execution is blocked.

The audited 2026-07-23 checkout contains 142 L2s: 94 class 1, 38 class 2, and 10 class 3. The 132 implemented L2s map to 79 unique executable probes (58 passing and 21 failing).
