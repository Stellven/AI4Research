# Wiki Health Check

Wiki root: `/private/tmp/ai4-check-missing-wiki`
Markdown pages: `0`
Missing dirs: `papers, methods, ideas, experiments, outputs, graph`
Edge errors: `0`
Native lint errors: `1`
Native lint warnings: `0`
Native lint info: `0`

## Model Evidence

Status: `unavailable`
Source: `N/A`
Answer: N/A

## Final Quality Boundary

Status: `check_final_quality_incomplete`
Final quality ready: `False`

## Findings JSON

```json
{
  "checked_roots": [
    "/private/tmp/ai4-check-missing-wiki"
  ],
  "edge_errors": [],
  "lint_report": {
    "edge_count": 0,
    "issue_counts": {
      "error": 1,
      "info": 0,
      "warn": 0
    },
    "ok": false,
    "page_count": 0,
    "returncode": 1,
    "schema": "autosci_wiki_lint_cli.v1",
    "status": "failed",
    "wiki_root": "/private/tmp/ai4-check-missing-wiki"
  },
  "markdown_page_count": 0,
  "missing_dirs": [
    "papers",
    "methods",
    "ideas",
    "experiments",
    "outputs",
    "graph"
  ],
  "model_output": {
    "checked_paths": [],
    "reason": "No model evidence or model command was supplied.",
    "status": "unavailable"
  },
  "root_exists": false,
  "target": "autosci wiki",
  "wiki_root": "/private/tmp/ai4-check-missing-wiki"
}
```
