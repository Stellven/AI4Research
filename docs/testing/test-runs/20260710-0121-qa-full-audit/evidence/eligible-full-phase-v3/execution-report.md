# Strict eligible-feature execution report

Locked commit: `fb3f589b08e4167ac3cb0043fb3d59801a0f110b`

## Scope

Included only atomic features whose validated mapping had a semantically relevant executable test and whose feature boundary did not require approval, credentials, a live provider, network, remote execution, or a browser profile. Existing `direct`, `indirect`, and `partial` labels were candidates, not proof.

- Eligible features: 448
- Excluded features: 1669
- Unique targets attempted: 107
- Target status: {'PASS': 93, 'FAIL': 14}
- Testcase status: {'testcase_pass': 523, 'testcase_fail': 15, 'testcase_error': 3, 'testcase_skip': 1}
- Exact feature execution outcome: {'PASS': 404, 'FAIL': 44}
- Conservative feature interpretation: {'INCONCLUSIVE_EXPECTED': 402, 'FAIL': 4, 'PASS': 42}

All 448 eligible features have terminal execution evidence. Passing indirect/partial or lower-confidence mappings are `INCONCLUSIVE_EXPECTED`, because running an existing test is not proof that the whole atomic contract is covered.

One pipx target was rerun after removing inherited audit `SOLAR_HOME`/`CLAUDE_DIR`; the original failure was an audit-environment confound and is not authoritative.

## Failing targets

| Target | Test file | Failing/error cases | Evidence |
|---|---|---:|---|
| `eligible-0002` | `harness/integrations/gemini_deep_research/evidence/test_completion_evidence.py` | 1 | `evidence/eligible-full-phase-v3/target-logs/eligible-0002.stdout.txt` |
| `eligible-0006` | `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | 2 | `evidence/eligible-full-phase-v3/target-logs/eligible-0006.stdout.txt` |
| `eligible-0018` | `harness/tests/benchmark/test_terminal_bench_adapter.py` | 1 | `evidence/eligible-full-phase-v3/target-logs/eligible-0018.stdout.txt` |
| `eligible-0020` | `harness/tests/data_plane/test_mineru_canonical_sources.py` | 2 | `evidence/eligible-full-phase-v3/target-logs/eligible-0020.stdout.txt` |
| `eligible-0027` | `harness/tests/graph/test_graph_dispatch_hygiene.py` | 1 | `evidence/eligible-full-phase-v3/target-logs/eligible-0027.stdout.txt` |
| `eligible-0032` | `harness/tests/graph/test_multi_task_runner_reuse.py` | 1 | `evidence/eligible-full-phase-v3/target-logs/eligible-0032.stdout.txt` |
| `eligible-0042` | `harness/tests/integrations/test-capability-fusion-benchmark.sh` | 0 | `evidence/eligible-full-phase-v3/target-logs/eligible-0042.stdout.txt` |
| `eligible-0062` | `harness/tests/test_agent_actor_schema.py` | 2 | `evidence/eligible-full-phase-v3/target-logs/eligible-0062.stdout.txt` |
| `eligible-0066` | `harness/tests/test_autosci_priority_b_demo_contracts.py` | 1 | `evidence/eligible-full-phase-v3/target-logs/eligible-0066.stdout.txt` |
| `eligible-0069` | `harness/tests/test_codex_pm_router.py` | 1 | `evidence/eligible-full-phase-v3/target-logs/eligible-0069.stdout.txt` |
| `eligible-0073` | `harness/tests/test_epic_show.py` | 1 | `evidence/eligible-full-phase-v3/target-logs/eligible-0073.stdout.txt` |
| `eligible-0081` | `harness/tests/test_knowledge_semantic_extract_health.py` | 1 | `evidence/eligible-full-phase-v3/target-logs/eligible-0081.stdout.txt` |
| `eligible-0083` | `harness/tests/test_logical_operator_schema.py` | 3 | `evidence/eligible-full-phase-v3/target-logs/eligible-0083.stdout.txt` |
| `eligible-0106` | `harness/tests/test_youtube_migration.py` | 1 | `evidence/eligible-full-phase-v3/target-logs/eligible-0106.stdout.txt` |

Raw failures in optional local-corpus surfaces remain visible. They are not promoted to live/provider parity, and feature-level status uses exact testcase matching rather than failing every feature linked to a shared file.

## Evidence files

- `feature-execution-results.csv`: one row per eligible atomic feature
- `testcase-results.csv`: raw JUnit testcase reconciliation
- `failed-testcases.csv`: failure/error subset
- `target-results.tsv`: commands, exit codes, counts, and paths
- `target-failure-summary.csv`: one row per failing target
- `eligible-features.csv` and `excluded-features.csv`: scope decision per atomic feature
