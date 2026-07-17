# Reflexion: Language Agents with Verbal Reinforcement Learning

- **id:** reflexion2023
- **authors:** Shinn, Cassano, Gopinath, Narasimhan, Yao
- **year:** 2023
- **venue:** NeurIPS
- **topics:** evaluator-verifier-driven-improvement, ai-research-agents

## Summary
Agents improve across trials by converting environment or evaluator feedback into
natural-language "reflections" stored in memory and used to guide subsequent attempts,
without updating model weights.

## Key claims
- An agent can self-improve by verbally reflecting on feedback from a task signal and
  retaining those reflections in an episodic memory buffer for later trials.
- This "verbal reinforcement" improves success rates on decision, reasoning, and
  coding tasks without any gradient updates.
- An explicit evaluator/verifier signal (e.g., unit tests or task success) is what
  makes the reflection loop productive rather than drifting.

## Limitations
- Depends on a usable external feedback/verifier signal; ambiguous tasks weaken it.
- Memory of reflections can accumulate noise, and gains vary widely by task type.
