# Wiki Health Check

Wiki root: `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/system-tmp/pytest-of-jamesyuan/pytest-1/test_autosci_skill_shim_check_0/artifacts/autosci/workspace/wiki`
Markdown pages: `1`
Missing dirs: `N/A`
Edge errors: `0`
Native lint errors: `0`
Native lint warnings: `0`
Native lint info: `1`

## Model Evidence

Status: `completed`
Source: `model-command`
Answer: The wiki has the required structural blocks and a valid source-linked graph edge.

## Final Quality Boundary

Status: `final_quality_ready`
Final quality ready: `True`

## Findings JSON

```json
{
  "checked_roots": [
    "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/system-tmp/pytest-of-jamesyuan/pytest-1/test_autosci_skill_shim_check_0/artifacts/autosci/workspace/wiki"
  ],
  "edge_errors": [],
  "lint_report": {
    "edge_count": 0,
    "issue_counts": {
      "error": 0,
      "info": 1,
      "warn": 0
    },
    "ok": true,
    "page_count": 1,
    "returncode": 0,
    "schema": "autosci_wiki_lint_cli.v1",
    "status": "completed",
    "wiki_root": "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/system-tmp/pytest-of-jamesyuan/pytest-1/test_autosci_skill_shim_check_0/artifacts/autosci/workspace/wiki"
  },
  "markdown_page_count": 1,
  "missing_dirs": [],
  "model_output": {
    "answer": "The wiki has the required structural blocks and a valid source-linked graph edge.",
    "checked_paths": [],
    "command": [
      "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/checkout/.venv/bin/python",
      "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/system-tmp/pytest-of-jamesyuan/pytest-1/test_autosci_skill_shim_check_0/check_model_command.py"
    ],
    "confidence": 0.91,
    "evidence_ids": [
      "model:wiki-health-review"
    ],
    "findings": [
      {
        "criterion": "source graph",
        "verdict": "pass"
      }
    ],
    "ideas": [],
    "invocation_mode": "command",
    "model": "test-model",
    "provider": "command",
    "request_path": "artifacts/autosci/runs/shim-check-model-command/check_wiki_health_model_request.json",
    "request_sha256": "262501c8202b8cc2e60ad323d093e7f959a8e6902f6c67fddd3cc98dbfbcad66",
    "response_path": "artifacts/autosci/runs/shim-check-model-command/check_wiki_health_model_stdout.json",
    "response_sha256": "2ca581f76a9f8cdfd378dc896e62bfe2e1f53b5816068de5892ba919df95a2eb",
    "source": "model-command",
    "status": "completed"
  },
  "root_exists": true,
  "target": "autosci wiki",
  "wiki_root": "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/system-tmp/pytest-of-jamesyuan/pytest-1/test_autosci_skill_shim_check_0/artifacts/autosci/workspace/wiki"
}
```
