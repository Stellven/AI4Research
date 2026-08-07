# Scientific reviewer independence repair

## Proof contract

`scientific_review_proof.v1` is a persisted JSON proof bundle. The reviewer accepts a bundle path, reloads that file and the reviewed artifact from disk, then reloads each cited evidence source. Each claim records:

- `claim_id` and `claim`;
- `evidence_span` (`start`, `end`, `text`);
- `source` (`source_id`, `path`, `sha256`);
- `acceptance_criterion`;
- reviewer-produced `verdict`, `verdict_reason`, `blockers`, and `residual_risk` in the normalized output.

The bundle also pins the reviewed artifact path and SHA-256. Missing citations, invalid spans, stale/tampered hashes, unsupported lexical scope, broad assertions, and a writer-provided approval are fail-closed blockers.

## Independence boundary

The review backend removes `writer_output`, `writer_verdict`, `writer_result`, and `writer_context` before constructing the reviewer request. Its output contains `reviewer_separation`, including disk reload booleans and provider identities.

When `review_llm_provider` differs from `writer.provider`, the result is `independent_provider`. Without a configured second provider, or with the same provider, it is `same_provider_limitation`; the result must not claim full provider independence. A deterministic local reviewer can check the proof but does not erase that limitation.

Novelty review persists and reloads an idea snapshot before LLM review. Claim compilation also rechecks linked persisted evidence text rather than trusting a generated `supports` relation.

## Verification

Run:

```powershell
python -m pytest tests/repairs/scientific_review tests/harness/evaluators/scientific/test_artifact_review_gate.py -q
```

The repair suite covers a supported claim, no-evidence proof, adversarial broad claim, evidence tampering, writer self-approval, provider separation, and claim-link false positives. The production `/review` bridge is exercised separately and recorded in `.codex-tmp/known-issue-repairs/scientific-review/result.json`.
