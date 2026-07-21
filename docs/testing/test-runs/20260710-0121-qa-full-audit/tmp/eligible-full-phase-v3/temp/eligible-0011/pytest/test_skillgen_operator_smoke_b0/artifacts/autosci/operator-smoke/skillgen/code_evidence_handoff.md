# AutoSci Phase 10 Handoff

- Action: `map_code_evidence`
- Schema: `code_evidence_map.v1`
- Status: `completed`
- Result: `artifacts/autosci/operator-smoke/skillgen/map_code_evidence.result.json`
- Evidence: `artifacts/autosci/operator-smoke/skillgen/code_evidence_map.json`
- Evidence ledger: `artifacts/autosci/operator-smoke/skillgen/evidence.jsonl`

## Claims

- claim-001: not_testable at skillgen_operator_smoke_paper.md#evidence-notes - This compact markdown fixture is derived from the SkillGen paper for Solar-native AutoSci operator smoke testing.
- claim-002: not_testable at skillgen_operator_smoke_paper.md#abstract - The paper introduces SKILLGEN, a multi-agent inference-time framework for synthesizing reusable, auditable agent skills from successful and failed trajectories.
- claim-003: testable at skillgen_operator_smoke_paper.md#abstract - It emphasizes contrastive induction, candidate verification, and empirical net-effect checks before deployment.

## Code Evidence

- map-001: unknown for claim-001 in artifacts/autosci/operator-smoke/skillgen/sample_repo/bridge_fixture.py
  Reason: The file exists, but the script could not prove that it supports the claim.
  Unknown: The file exists, but the script could not prove that it supports the claim.

## Limitations

- Code mapping records candidate file relevance; it is not evidence of claim verification.
