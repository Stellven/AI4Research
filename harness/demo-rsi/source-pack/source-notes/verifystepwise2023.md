# Let's Verify Step by Step

- **id:** verifystepwise2023
- **authors:** Lightman, Kosaraju, Burda, et al. (OpenAI)
- **year:** 2023
- **venue:** arXiv preprint
- **topics:** evaluator-verifier-driven-improvement

## Summary
Compares outcome-supervised vs. process-supervised reward models for math reasoning,
finding that rewarding each correct reasoning step trains more reliable verifiers.

## Key claims
- Process supervision — rewarding each intermediate reasoning step — trains verifiers
  that outperform outcome-only supervision at selecting correct solutions.
- A strong learned verifier used to rank many sampled solutions materially raises the
  fraction of problems solved correctly.
- Reliable step-level verification is a key ingredient for scaling
  verifier-driven self-improvement in reasoning models.

## Limitations
- Process labels are expensive to collect and were studied primarily in the math
  domain.
- A verifier can be gamed by solutions that look locally valid but are globally wrong.
