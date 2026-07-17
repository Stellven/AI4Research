# Self-Refine: Iterative Refinement with Self-Feedback

- **id:** selfrefine2023
- **authors:** Madaan, Tandon, Gupta, et al.
- **year:** 2023
- **venue:** NeurIPS
- **topics:** self-improving-llms, test-time-recursive-thinking

## Summary
A test-time method where a single LLM iteratively critiques its own output and
revises it, with no additional training, supervision, or reward model.

## Key claims
- An LLM can improve its own outputs at inference time by generating feedback on a
  draft and then revising the draft using that feedback, looped until satisfactory.
- The same frozen model plays generator, critic, and reviser; no fine-tuning or
  external verifier is required.
- Self-Refine improves output quality across diverse tasks relative to single-pass
  generation from the same model.

## Limitations
- Improvement depends on the model's own critique ability; weak self-evaluation
  bounds the gains.
- Iterative refinement increases inference cost and can stall or oscillate without a
  reliable stopping signal.
