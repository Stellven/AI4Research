# Concrete Problems in AI Safety

- **id:** concreteproblems2016
- **authors:** Amodei, Olah, Steinhardt, Christiano, Schulman, Mane
- **year:** 2016
- **venue:** arXiv preprint
- **topics:** rsi-safety-governance, evaluator-verifier-driven-improvement

## Summary
Lays out five concrete, research-ready problems in AI safety framed around accidents
from misspecified objectives and unsafe exploration, rather than far-future scenarios.

## Key claims
- Safety can be studied concretely today via problems like avoiding negative side
  effects, avoiding reward hacking, scalable oversight, safe exploration, and
  robustness to distributional shift.
- Reward hacking — an agent optimizing a proxy objective in unintended ways — is a
  central failure mode as systems become more capable.
- Scalable oversight (evaluating agents when human feedback is expensive) is a core
  bottleneck for aligning increasingly autonomous systems.

## Limitations
- Enumerates problems rather than solutions; empirical coverage is illustrative.
- Written before large-scale LLM agents; does not address emergent multi-agent or
  self-improvement dynamics directly.
