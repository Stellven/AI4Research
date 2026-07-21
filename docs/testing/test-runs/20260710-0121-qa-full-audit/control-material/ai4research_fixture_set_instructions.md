# Fixture Set Instructions for AI4Research Repo Testing

Use this file with `ai4research_recursive_feature_split_qa_execution.xlsx` and the QA control DOCX. The goal is to give the coding agent deterministic inputs so it can test workflows, foundations, and misc/product surfaces without depending on live services.

## Where fixtures should live

Create fixtures under the timestamped evidence directory, not in the real repo state unless the test itself requires a checked-in fixture proposal.

```text
docs/testing/test-runs/<YYYYMMDD-HHMM>-full-audit/fixtures/
  papers/
  wiki/
  providers/
  evidence/
  approvals/
  experiments/
  ui/
```

## Required fixture families

| Fixture family | Minimum files | Used for |
|---|---|---|
| Paper sources | valid Markdown paper, malformed Markdown paper, small valid PDF, malformed PDF, small LaTeX source | `/ingest`, `ingest_paper`, `analyze_paper`, source preparation, parser failures |
| Provider responses | fake arXiv JSON, fake Semantic Scholar JSON, fake DeepXiv JSON, fake Paper Copilot/venue JSON | `/discover`, `/daily-arxiv`, novelty/provider-boundary tests |
| Wiki workspace | minimal valid wiki, empty wiki, invalid graph JSONL, broken wikilinks | `/ask`, `/check`, `/visualize`, memory/graph gates |
| Evidence ABI | valid and invalid payload for each major `.v1` evidence schema | schema/gate tests |
| Approval artifacts | approval ref, allowlist evidence, before artifact, runtime evidence, after artifact | approval-gated routes and side-effect policy tests |
| Experiment artifacts | experiment plan, fake runtime log, seed result JSON, missing result directory | `/exp-design`, `/exp-run`, `/exp-status`, `/exp-eval` |
| Review evidence | fake Review LLM response, invalid Review LLM response, missing Review LLM case | `/review`, `/novelty`, `/paper-plan`, `/refine` |
| UI fixtures | sample status payloads, missing runtime payload, stalled run payload | desktop/dashboard/status server tests |

## Fixture rules

1. Every fixture must be small, deterministic, and safe to copy.
2. Fixture content must be visibly marked as fixture data, for example `fixture_source=true` or title prefix `Fixture:`.
3. Tests must not count fixture data as live provider/full parity evidence.
4. Negative fixtures are required: malformed input, missing file, bad schema, unavailable provider, missing approval.
5. Every fixture must have a short README or manifest entry explaining which feature IDs it supports.

## Suggested manifest

Create:

```text
fixtures/manifest.json
```

With this shape:

```json
{
  "schema": "ai4research_fixture_manifest.v1",
  "created_for_commit": "<git sha>",
  "fixtures": [
    {
      "id": "fixture-paper-valid-md",
      "path": "fixtures/papers/valid-paper.md",
      "supports_feature_ids": ["WF-...."],
      "kind": "paper_markdown",
      "positive_or_negative": "positive",
      "notes": "Source-anchored Markdown paper for deterministic ingestion."
    }
  ]
}
```

## How the coding agent should use fixtures

1. Build or copy fixtures before running tests.
2. Record fixture paths in `environment.json` or `fixtures/manifest.json`.
3. Link each fixture to feature IDs in the workbook-derived results.
4. When a test fails, copy the exact fixture and generated output into `failures/<feature_id>/`.
5. Do not overwrite repo fixtures unless explicitly asked to propose new checked-in tests.
