# The AI Scientist: Towards Fully Automated Open-Ended Scientific Discovery

- **id:** aiscientist2024
- **authors:** Lu, Lu, Lange, Foerster, Ha, Clune (Sakana AI)
- **year:** 2024
- **venue:** arXiv preprint
- **topics:** ai-research-agents, ai-scientific-research-workbenches

## Summary
Describes an end-to-end pipeline in which LLM agents generate research ideas, run
experiments, write papers, and review them, aiming at a self-directed research loop.

## Key claims
- An LLM-driven pipeline can autonomously carry a machine-learning study from idea
  generation through experiments to a written paper and an automated review.
- An automated reviewer agent provides the evaluation signal that lets the system
  iterate on and select among generated papers.
- Fully automated open-ended discovery is presented as a step toward research agents
  that recursively improve their own outputs.

## Limitations
- Generated papers are uneven in quality and can contain errors or overclaims.
- The automated reviewer is imperfect, so the improvement signal is noisy and may
  reward superficially strong but flawed work.
