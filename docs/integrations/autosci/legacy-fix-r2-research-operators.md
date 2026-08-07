# R2 Research Operators Legacy Fix

## Scope

Repair agent: OpenSolar R2 Research Operators.

Baseline: `6a96d40153b919d97a2018c8267d7796d5e3e1d5`

Branch: `codex/legacy-fix-r2-research-operators`

## Repairs

- Unified URL, local document, PDF, topic, and external evidence seeds under `autosci_seed_source_contract.v1`.
- Added PDF/source provenance, content hashes, parse proof, limitations, and final source registration boundary to paper ingestion evidence.
- Split source policy into authority, relevance, duplicate, and source-failure reasons; a failed source is rejected with explanation without crashing the accepted set.
- Added source proof, falsifiability, risk, validation, minimum experiment, and promotion decision to idea cards.
- Made review output explicitly independent of writer self-assessment and preserved reloaded artifact hashes.
- Added deliverable inspection so paper/report publication cannot pass as schema-only or file-exists-only evidence.
- Canonicalized ask/wiki and runtime evidence paths to POSIX-style cross-platform paths on Windows.
- Made JSON compatibility CLI commands reject unsupported flags with an explicit `unsupported_cli_flag` error.
- Required visualization commands to use real wiki/artifact data and added a production-path graph output check.
- Shortened selected Windows sidecar/envelope filenames used by J22 isolated journeys to avoid path-length failures while preserving schemas and artifact types.
- Downgraded claim verification when independent Review LLM evidence blocks support for overgeneralized or unsupported claims.

## Production-Path Evidence

- Chinese URL seed, English topic seed, and local PDF seed are covered in the research synthesis operator regression test.
- Local PDF ingestion parses real text and carries provenance/source boundary into final `research_paper.v1`.
- Ask/wiki retrieval path canonicalization is covered through `autosci_bridge.py run --action ask_wiki`.
- Visualize graph data reads a real wiki graph and rejects unsupported flags.

## Tests Run

- `python -m pytest -q harness/plugins/autosci/tests/research_synthesis_operators/test_research_synthesis_operators.py harness/plugins/autosci/tests/scientific_lifecycle_action_operators/test_action_delivery_operators.py harness/plugins/autosci/tests/test_paper_prepare.py harness/plugins/autosci/tests/test_source_cli_tools.py --basetemp .codex-tmp/r2-tests/regression-final-bt -o cache_dir=.codex-tmp/r2-tests/regression-final-cache`
  - Result: `96 passed in 5.69s`
- `python -m pytest -q tests/journeys/phase22/code/test_j04_paper_ingestion.py tests/journeys/phase22/code/test_j05_literature_discovery.py tests/journeys/phase22/code/test_j06_idea_generation.py tests/journeys/phase22/code/test_j09_report_delivery.py tests/journeys/phase22/code/test_j20_research_synthesis.py tests/journeys/phase22/code/test_j22_evidence_review_followup.py --basetemp .codex-tmp/r2-tests/journeys-final-bt -o cache_dir=.codex-tmp/r2-tests/journeys-final-cache`
  - Result: `4 passed, 2 skipped in 42.58s`

## Open Limitations

- J05 and J20 remained skipped in the requested journey batch under the local environment/provider gating used by those tests.
- Review independence is represented by independent invocation/context fields and reloaded artifact hashes; it is not a separate live reviewer service in this local repair batch.
- Live provider 429 behavior was not exercised because live provider calls were not authorized for this run.
