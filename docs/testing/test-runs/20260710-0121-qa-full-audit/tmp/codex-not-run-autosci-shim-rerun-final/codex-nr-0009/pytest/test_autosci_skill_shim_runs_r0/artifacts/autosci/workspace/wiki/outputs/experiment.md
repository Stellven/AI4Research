---
entity_type: "output"
entity_id: "experiment-shim-research"
title: "Experiment summary for shim-research"
run_id: "shim-research"
source_evidence: "artifacts/autosci/runs/shim-research/experiment_result.json"
managed_by: "solar-autosci-workspace-projector"
---
# Experiment Summary: `shim-research`

## Status

- Experiment id: `exp-001`
- Plan evidence status: `completed`
- Result evidence status: `completed`
- Status evidence status: `completed`
- Outcome: `supports`
- State: `completed`
- Execution mode: `fixture`
- Command run: `python3 plugins/autosci/bin/autosci_bridge.py run --action run_experiment`
- Plan evidence: `artifacts/autosci/runs/shim-research/experiment_plan.json`
- Result evidence: `artifacts/autosci/runs/shim-research/experiment_result.json`
- Status evidence: `artifacts/autosci/runs/shim-research/experiment_status.json`

## Runtime Audit Boundary

- Boundary status: `N/A`
- Stage: `N/A`
- Final runtime audit ready: `N/A`
- Stage audit ready: `N/A`
- Approval contract verified: `N/A`
- Runtime semantic verified: `N/A`
- Result collected: `N/A`
- Collection ledger recorded: `N/A`
- Live remote collection verified: `N/A`

## Metrics

| Metric | Value |
| --- | --- |
| result_json_written | True |
| evidence_jsonl_written | True |

## Logs

| Log |
| --- |
| execution_mode=fixture |
| experiment_id=exp-001 |
| command_run=python3 plugins/autosci/bin/autosci_bridge.py run --action run_experiment |
| fixture result collected |

## Artifacts

| Type | Path |
| --- | --- |
| experiment_design_final_execution_boundary_json | artifacts/autosci/runs/shim-research/experiment_design_final_execution_boundary.json |
| solar_evidence_json | artifacts/autosci/runs/shim-research/experiment_plan.json |
| experiment_run_log | artifacts/autosci/runs/shim-research/exp-001.log |
| solar_evidence_json | artifacts/autosci/runs/shim-research/experiment_result.json |
| solar_evidence_json | artifacts/autosci/runs/shim-research/experiment_status.json |

## Limitations

- Fixture experiment design is bounded to local bridge artifacts.
- Review LLM design validation was not supplied.
- Experiment design final execution readiness requires resolved target evidence, completed Review LLM validation, approval preflight, command handoff, and expected artifact handoff.
- Fixture result is deterministic and not a real benchmark run.
- Status is derived from local result evidence only.
