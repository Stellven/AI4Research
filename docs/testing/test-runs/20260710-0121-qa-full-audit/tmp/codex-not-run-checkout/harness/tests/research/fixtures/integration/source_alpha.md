# Alpha Source — Solar DeepResearch Smoke

Solar DeepResearch is an AI-native research operating system built on top of
the Solar Harness control plane. It introduces a first-class evidence ledger,
a structured ReportAST, and a multi-section writing pipeline.

The evidence ledger enforces three hard rules:

1. Every key claim in the body must carry at least one `evidence_id`.
2. Every evidence record must include a verifiable `span_text` over the
   underlying source.
3. Every citation span must match the surrounding claim, or the factuality
   evaluator fails the section.

ReportAST decomposes a long-form report into Chapters and Sections so that
section writers can operate within bounded character budgets (1500–4000
chars per section).
