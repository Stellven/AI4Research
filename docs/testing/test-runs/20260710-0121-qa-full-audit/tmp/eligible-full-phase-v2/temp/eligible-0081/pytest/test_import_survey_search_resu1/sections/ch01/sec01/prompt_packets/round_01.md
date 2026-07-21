# Survey Section Prompt Packet: ch01/sec01

- Backend: deterministic
- Round: 1
- Role: professor-grade technical survey section writer

## Task

Write or revise section '问题定义与研究边界：研究问题与术语边界' from the provided evidence pack only.

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

- Chapter: ch01 / 问题定义与研究边界
- Section Order In Chapter: 1
- Chapter Packet: /Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0081/pytest/test_import_survey_search_resu1/chapters/ch01/prompt_packet.md

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

- cl_17eb9bf9c1f4
- cl_a4831dec67e5
- cl_95cf77e1386c
- cl_c756b6aeb307
- cl_ae1ef7ac27d0
- cl_d7e1ced8f26f

## Required Evidence

- ev_17eb9bf9c1f4
- ev_a4831dec67e5
- ev_95cf77e1386c
- ev_c756b6aeb307
- ev_ae1ef7ac27d0
- ev_d7e1ced8f26f

## Human Response Path

/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0081/pytest/test_import_survey_search_resu1/sections/ch01/sec01/human_responses/round_01.md

## Return Instructions

Write the completed Markdown section to the human response path above, then rerun the same survey command.
