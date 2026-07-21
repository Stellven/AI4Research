# AutoSci Research Pipeline Report

Target: `info`
Pipeline: `info`
Resume from: `setup`
Venue: `N/A`
Skip paper: `False`

## Stage State

| Order | Stage | State |
| ---: | --- | --- |
| 1 | `setup` | `pending_evidence` |
| 2 | `ingest` | `completed` |
| 3 | `discover` | `pending_evidence` |
| 4 | `ideate` | `pending_evidence` |
| 5 | `novelty-review` | `pending_evidence` |
| 6 | `experiment-design` | `pending_evidence` |
| 7 | `experiment-run` | `pending_evidence` |
| 8 | `collect` | `pending_evidence` |
| 9 | `review` | `pending_evidence` |
| 10 | `paper-plan` | `pending_evidence` |
| 11 | `paper-compile` | `pending_evidence` |

## Gate State

- Execution state: gated
- Side effects executed: false
- Workspace mutation outside generated pipeline artifacts: false
- Required before full parity: Review LLM evidence, online discovery evidence, experiment runtime evidence, collection evidence, and LaTeX/PDF compile evidence.

## Evidence Summary

- Paper exists: `True`
- Discovery completed: `False`
- External novelty completed: `False`
- Review LLM completed: `False`
- Scheduler lifecycle completed: `False`
- Experiment runtime verified: `False`
- Compile runtime verified: `False`
- Integrated PDF: `not_materialized`

## Resume Notes

- The next executable stage is recorded, but no native stage runner was launched.
- This report is intended for parity auditing and resume planning, not as research outcome evidence.
