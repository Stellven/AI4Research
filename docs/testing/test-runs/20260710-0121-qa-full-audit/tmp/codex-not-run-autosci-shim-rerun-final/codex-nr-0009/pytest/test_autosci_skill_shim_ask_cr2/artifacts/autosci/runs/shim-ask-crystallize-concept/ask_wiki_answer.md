# AutoSci Ask Wiki

Query: `What supports SkillGen?`

## Wiki Context

- `context_brief`: `present` at `artifacts/autosci/workspace/wiki/graph/context_brief.md`
- `open_questions`: `present` at `artifacts/autosci/workspace/wiki/graph/open_questions.md`
- `index`: `present` at `artifacts/autosci/workspace/wiki/index.md`
- `edges`: `present` at `artifacts/autosci/workspace/wiki/graph/edges.jsonl`

## Retrieval Sources

- [[skillgen]] `artifacts/autosci/workspace/wiki/papers/skillgen.md` score=5: # SkillGen
- [[open-questions]] `artifacts/autosci/workspace/wiki/graph/open_questions.md` score=2: - How much evidence supports SkillGen beyond a single paper?
- [[index]] `artifacts/autosci/workspace/wiki/index.md` score=2: - [skillgen](papers/skillgen.md)
- [[context-brief]] `artifacts/autosci/workspace/wiki/graph/context_brief.md` score=1: SkillGen connects generated skills, verifier checks, and runtime evidence.

## Bullet Answer

- # SkillGen Source: [[skillgen]] (`artifacts/autosci/workspace/wiki/papers/skillgen.md`).
- - How much evidence supports SkillGen beyond a single paper? Source: [[open-questions]] (`artifacts/autosci/workspace/wiki/graph/open_questions.md`).
- - [skillgen](papers/skillgen.md) Source: [[index]] (`artifacts/autosci/workspace/wiki/index.md`).
- SkillGen connects generated skills, verifier checks, and runtime evidence. Source: [[context-brief]] (`artifacts/autosci/workspace/wiki/graph/context_brief.md`).
- Model synthesis: SkillGen support is grounded in verifier-gated generated skills from the retrieved source.

## Model Synthesis

SkillGen support is grounded in verifier-gated generated skills from the retrieved source.

## Knowledge Gaps

- `matched_open_question` from `artifacts/autosci/workspace/wiki/graph/open_questions.md`: - How much evidence supports SkillGen beyond a single paper?

## Crystallize Recommendation

Crystallize recommendation: `worthwhile` - The user requested crystallize and the final answer boundary is ready.

## Confidence

- Retrieval-backed extractive answer: `completed`
- Source count: `4`
- Model evidence status: `completed`
- Final answer boundary: `final_answer_ready`
