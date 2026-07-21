# AutoSci Phase 10 Progress Log

Logged: 2026-06-18 15:06:00 EDT
Branch: `feature/autosci-solar-native`

## Scope

Phase 10 implemented fixture-mode paper to claim, method, and code evidence
mapping through Solar-native Evidence ABI artifacts. Claims remain unverified at
extraction time, methods are emitted as separate `research_method.v1` evidence,
and code mappings record explicit file/symbol anchors when available or
`mapping_status: unknown` when the repository path is unavailable.

This phase does not change scheduler behavior, product logic, report logic,
fallback behavior, scoring, routing, quota, leases, model selection, or claim
verification behavior.

## Files Changed

| Artifact group | Operation | Paths |
|---|---|---|
| Bridge actions | Updated | `harness/plugins/autosci/bin/autosci_bridge.py` |
| Method/code adapters | Updated | `harness/plugins/autosci/adapters/autosci_to_{research_method,code_evidence_map}.py` |
| Fixture envelopes | Added/updated | `harness/plugins/autosci/tests/fixtures/envelope.{extract_claims,extract_methods,map_code_evidence}.json` |
| Sample repo fixture | Added | `harness/plugins/autosci/tests/fixtures/sample_repo/bridge_fixture.py` |
| Plugin tests | Updated | `harness/plugins/autosci/tests/test_*.py` |
| Physical operators | Updated | `harness/config/physical-operators.json` |
| README | Updated | `harness/plugins/autosci/README.md` |

## Added / Updated / Used Classification

This phase reuses earlier claim-extraction work. It should not be described as
adding `ScientificClaimExtractor`, adding the `extract_claims` bridge action, or
adding the `autosci-claim-extract-worker`.

| Item | Phase 10 classification | Originally introduced | Phase 10 note |
|---|---|---|---|
| `ScientificClaimExtractor` | used | Phase 3 | Existing logical operator; no Phase 10 logical-operator addition. |
| `extract_claims` bridge action | used | Phase 4/5 path | Existing backend action; Phase 10 only reran it as part of the paper-to-claim-to-method-to-code smoke. |
| `autosci-claim-extract-worker` | used | Phase 5 | Existing physical worker; no Phase 10 worker addition. |
| `envelope.extract_claims.json` | updated | Phase 4/5 fixture | Updated canonical smoke output path to `artifacts/scientific/smoke/research_claims.json`. |
| `extract_methods` bridge action | added | Phase 10 | New action for `research_method.v1`. |
| `map_code_evidence` bridge action | added | Phase 10 | New action for `code_evidence_map.v1`. |
| `autosci-method-extract-worker` | added | Phase 10 | New physical worker for `ScientificMethodExtractor`. |
| `autosci-code-evidence-map-worker` | added | Phase 10 | New physical worker for `ScientificCodeEvidenceMapper`. |

## Backend Actions

| Action | Phase 10 classification | Evidence ABI | Note |
|---|---|---|---|
| `extract_claims` | used | `research_claims.v1` | Existing action; source-grounded fixture claims; verification remains `unverified`. |
| `extract_methods` | added | `research_method.v1` | Method/procedure evidence separate from claims. |
| `map_code_evidence` | added | `code_evidence_map.v1` | Maps to sample repo file/symbol when present; otherwise marks unknown. |

## Physical Operator Wiring

| Operator | Phase 10 classification | Status | Action |
|---|---|---|---|
| `autosci-claim-extract-worker` | used | enabled | `extract_claims` |
| `autosci-method-extract-worker` | added | enabled | `extract_methods` |
| `autosci-code-evidence-map-worker` | added | enabled | `map_code_evidence` |

## Checks Run

| Check | Status | Note |
|---|---|---|
| Solar context injection | warn | Repo-local context inject worked; Mirage source was degraded. |
| Phase 10 bridge smoke | ok | Wrote `research_claims.json`, `research_method.json`, and `code_evidence_map.json`. |
| Claims gate | ok | `claims_gate.py artifacts/scientific/smoke/research_claims.json` passed. |
| Method gate | ok | `method_gate.py artifacts/scientific/smoke/research_method.json` passed. |
| Code evidence gate | ok | `code_evidence_gate.py artifacts/scientific/smoke/code_evidence_map.json` passed. |
| Plugin tests | ok | `pytest plugins/autosci/tests`: 10 passed. |
| Operator runtime submit | ok | Method and code evidence workers completed with exit code 0. |
| Runtime method/code gates | ok | Runtime evidence artifacts passed method/code gates. |
| Evaluator regression tests | ok | `pytest tests/evaluators/scientific`: 10 passed. |
| Workflow validation | ok | Claim extraction and claim verification workflows passed `graph_scheduler.py validate`. |
| Architecture guard | ok | Claim verification strict guard passed. |
| Physical operator JSON | ok | `json.tool config/physical-operators.json` passed. |

## Caveats

- AutoSci physical operators still use the existing placeholder
  `owner_host: solar@example-host` and do not declare explicit `host_id`; this is
  the pre-existing scheduler-clean warning.
- Existing dirty/untracked files outside this Phase 10 scope were left untouched.
- Code evidence mapping is fixture-mode only; it identifies local sample files
  and does not verify scientific claims.

## SkillGen Paper Recheck

Logged: 2026-06-18 EDT

The SkillGen paper runtime check showed that Phase 10 can dispatch and write
schema-shaped artifacts, but it is not ready for promotion as a real
paper-to-claim-to-method-to-code flow.

| Issue | Status | Where seen | Recommended fix |
|---|---|---|---|
| Claims are still sample-based | error | `autosci_bridge.py` loads `sample_autosci_raw_claims.json` for `extract_claims` | Make `extract_claims` read `inputs.paper_path` and produce claims anchored to that paper. If a claim cannot be grounded, mark it non-testable or inconclusive. |
| Methods are still sample-based | error | `extract_methods` returns a hardcoded fixture method with `sample_paper.md` anchors | Extract method/procedure text from the input paper sections and use that paper's anchors. |
| Code mapping lacks relevance labels | error | `map_code_evidence` maps a file but does not explain whether it is direct, indirect, related, or unknown evidence | Add `relevance_label` and `relevance_reason` to each mapping. Use `unknown` when support cannot be proven. |
| Code evidence gate is too weak | warn | `code_evidence_gate.py` passes mappings that have files and evidence ids but no relevance label | Update the schema and gate so mapped code evidence must include a relevance label and explanation. |
| `handoff.md` is missing | error | Runtime envelope can provide `handoff_path`, but the bridge does not write the handoff file | Have the bridge write a simple handoff file listing paper, claims, methods, code mappings, unknowns, and artifact paths. |

Recommended fix order:

1. Stop hardcoded claim and method outputs.
2. Add code relevance labels and reasons.
3. Tighten the code evidence schema and gate.
4. Write `handoff.md`.
5. Add regression tests for the SkillGen paper path and malformed code mappings.

## SkillGen Paper Fix Pass

Logged: 2026-06-18 EDT

The five SkillGen recheck issues were fixed in the Phase 10 bridge, schema,
gate, and tests.

| Issue | Status | Fix |
|---|---|---|
| Claims were sample-based | ok | `extract_claims` now reads `inputs.paper_path`, uses paper section anchors, and marks descriptive claims as `not_testable` with a reason. |
| Methods were sample-based | ok | `extract_methods` now reads method-like sections from the input paper and uses that paper's anchors. |
| Code mappings lacked relevance labels | ok | `map_code_evidence` now writes `relevance_label` and `relevance_reason`; unsupported links are marked `unknown`. |
| Code evidence gate was too weak | ok | `code_evidence_map.v1` and `code_evidence_gate.py` now require relevance label and reason. |
| `handoff.md` was missing/incomplete | ok | The bridge now writes `handoff.md` when requested and includes paper, claims, methods, code evidence, unknowns, and artifact paths. |

SkillGen recheck result:

| Check | Status | Note |
|---|---|---|
| SkillGen claims | ok | Claims use `skillgen_sample_paper.md#...` anchors. |
| SkillGen methods | ok | Method uses `skillgen_sample_paper.md#method`. |
| SkillGen code evidence | ok | The sample repo mapping is `unknown` when support cannot be proven. |
| SkillGen handoff | ok | `handoff.md` includes paper, claims, methods, and code evidence sections. |
| Claims gate | ok | `research_claims.json` passed with no warnings. |
| Method gate | ok | `research_method.json` passed with no warnings. |
| Code evidence gate | ok | `code_evidence_map.json` passed with no warnings. |
| Missing anchor rejection | ok | Malformed claim without source anchor failed as expected. |
| Regression tests | ok | `pytest tests/evaluators/scientific plugins/autosci/tests`: 23 passed. |
| Architecture guard | ok | Claim extraction and claim verification graphs passed strict guard with zero warnings. |

## Completion Issue Fix Pass

Logged: 2026-06-18 16:17:31 EDT

The Phase 10 checker found two remaining completion issues after the SkillGen
fix pass. Both were addressed locally.

| Issue | Status | Fix | Verification |
|---|---|---|---|
| `code_evidence_gate.py` still accepted `mapping_status: mapped` with `files: ["N/A"]` when relevance was labeled `related`. | ok | Gate now requires mapped code evidence to include at least one concrete file path, rejects mapped evidence with unknown relevance, and requires unknown mappings to carry `unknown_reason`. | Negative probe now fails with `mapped code evidence requires at least one concrete file path`; `test_code_evidence_gate.py` covers mapped placeholder rejection and unknown placeholder acceptance. |
| `artifacts/scientific/phase10-runtime/code_evidence_map.json` was stale under the tightened schema and lacked `relevance_label` / `relevance_reason`. | ok | Refreshed the Phase 10 runtime method/code evidence artifacts through the bridge and generated `artifacts/scientific/phase10-runtime/handoff.md`. | Runtime `method_gate.py` and `code_evidence_gate.py` both passed with no warnings. |

Updated verification:

| Check | Status | Note |
|---|---|---|
| Code evidence gate regression | ok | `pytest tests/evaluators/scientific/test_code_evidence_gate.py`: 4 passed. |
| Full relevant regression | ok | `pytest plugins/autosci/tests tests/evaluators/scientific`: 26 passed. |
| Runtime method gate | ok | `method_gate.py artifacts/scientific/phase10-runtime/research_method.json` passed. |
| Runtime code evidence gate | ok | `code_evidence_gate.py artifacts/scientific/phase10-runtime/code_evidence_map.json` passed. |
| Smoke code evidence gate | ok | `code_evidence_gate.py artifacts/scientific/smoke/code_evidence_map.json` passed. |
| TaskGraph validation | ok | `scientific_claim_extraction_v1`, `scientific_claim_verification_v1`, and `scientific_research_lifecycle_full_v1` all validated with zero errors/warnings. |
| Schema/JSON checks | ok | `json.tool schemas/evidence/code_evidence_map.v1.schema.json` and `json.tool config/physical-operators.json` passed. |

## Done State

Phase 10 is complete when Solar can represent paper to claim to method to code
mapping as native typed evidence artifacts, and deterministic gates accept the
claim, method, and code evidence outputs.
