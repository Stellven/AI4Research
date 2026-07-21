# Survey Section Prompt Packet: ch01/sec03

- Backend: deterministic
- Round: 1
- Role: professor-grade technical survey section writer

## Task

Write or revise section '问题定义与研究边界：证据链与代表工作' from the provided evidence pack only.

## Constraints

- Use the section evidence pack as the source of truth.
- Bind important factual claims to [claim:<id>] and [evidence:<id>] tags.
- Separate architecture synthesis, evaluation limits, contradiction slots, and open problems.
- Do not invent sources, results, paper names, URLs, or benchmark numbers.
- Preserve uncertainty when evidence is weak or contradictory.

## Output Contract

- Markdown section draft.
- At least six second-level headings.
- Follow the professor-grade section template in writing_policy.section_template.
- Include Literature Lineage, Method Taxonomy, Architecture Synthesis, Comparative Positioning, Terminology Evolution, Evaluation Protocol Matrix, Evaluation And Risk Boundary, Limitations And Failure Modes, Controversy Matrix, Contradiction Slots, and Open Problems.
- All core claims must reference claim_id and evidence_id tags.

## Chapter Context

- Chapter: ch01 / General Notes
- Section Order In Chapter: 3
- Chapter Packet: /Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-phase/codex-nr-0128/pytest/test_strict_eval_fails_when_ta0/chapters/ch01/prompt_packet.md

## Professor-Grade Section Template

- Research Question
- Position
- Claim Map
- Evidence Map
- Source Map
- Literature Lineage
- Method Taxonomy
- Architecture Synthesis
- Comparative Positioning
- Terminology Evolution
- Evaluation Protocol Matrix
- Evaluation And Risk Boundary
- Limitations And Failure Modes
- Controversy Matrix
- Contradiction Slots
- Open Problems

## Source-Type Guidance

- Use benchmarks for evaluation scope, metric caveats, and comparability limits.
- Use code repositories for reproducibility, implementation cost, integration boundaries, and maintenance risk.
- Use official docs for system boundaries, APIs, deployment constraints, and supported behavior.
- Use papers for mechanisms, assumptions, experimental claims, and limits of generalization.

## Synthesis Outline

- Define the local research question and scope.
- Map claims to evidence and source types.
- Synthesize architecture mechanisms before evaluation claims.
- Compare source families instead of flattening them into citations.
- State evaluation limits and failure modes.
- End with open problems that can feed chapter-level synthesis.

## Required Claims

- cl_0
- cl_1
- cl_2
- cl_3
- cl_4
- cl_5

## Required Evidence

- ev_0
- ev_1
- ev_2
- ev_3
- ev_4
- ev_5
- ev_6

## Human Response Path

/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-phase/codex-nr-0128/pytest/test_strict_eval_fails_when_ta0/sections/ch01/sec03/human_responses/round_01.md

## Return Instructions

Write the completed Markdown section to the human response path above, then rerun the same survey command.
