# Autonomous Chemical Research with Large Language Models (Coscientist)

- **id:** coscientist2023
- **authors:** Boiko, MacKnight, Kline, Gomes
- **year:** 2023
- **venue:** Nature
- **topics:** ai-scientific-research-workbenches, ai-research-agents

## Summary
Presents an LLM-driven system ("Coscientist") that plans, codes, and executes
chemistry experiments by orchestrating tools, documentation search, and lab hardware.

## Key claims
- An LLM agent equipped with tools (web/document search, code execution, lab APIs) can
  autonomously plan and carry out real chemical experiments.
- Tool use and retrieval, rather than the base model alone, are what let the system
  act reliably in a scientific workbench setting.
- The system demonstrates a research workbench where an agent closes the loop from
  design to physical execution.

## Limitations
- Demonstrated on a limited set of chemistry tasks; generality is unproven.
- Autonomous experimentation raises safety and dual-use concerns that require
  guardrails and human oversight.
