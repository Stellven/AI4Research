# AutoSci Phase 10 Handoff

- Action: `map_code_evidence`
- Schema: `code_evidence_map.v1`
- Status: `completed`
- Result: `artifacts/scientific/smoke/map_code_evidence.result.json`
- Evidence: `artifacts/scientific/smoke/code_evidence_map.json`
- Evidence ledger: `artifacts/scientific/smoke/evidence.jsonl`

## Claims

- claim-001: testable at sample_paper.md#results - The fixture path should produce a `result.json` file and an `evidence.jsonl` ledger entry without invoking a monolithic AutoSci workflow owner.
- claim-002: not_testable at sample_paper.md#abstract - This fixture paper exists only to test Solar-native adapter boundaries.

## Methods

- method-001: Method protocol at sample_paper.md#method

## Code Evidence

- map-001: related for claim-001 in plugins/autosci/tests/fixtures/sample_repo/bridge_fixture.py
  Reason: Claim and code share terms: evidence, path.

## Limitations

- Code mapping records candidate file relevance; it is not evidence of claim verification.
