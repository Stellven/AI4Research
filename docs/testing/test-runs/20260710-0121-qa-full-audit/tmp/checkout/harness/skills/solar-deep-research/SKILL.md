# Solar Deep Research

> Multi-source deep research pipeline: search → extract → mine → verify → compile → evaluate

## Capabilities

| Capability | Description |
|-----------|-------------|
| `source.search` | Multi-source search across web, academic, and internal connectors |
| `evidence.extract` | Extract evidence passages with span_text and content_hash |
| `claim.mine` | Mine claims from evidence, mark key claims, compute support ratings |
| `citation.verify` | Verify citation spans match evidence, compute citation_span_accuracy |
| `report.compile` | Compile structured reports from ReportAST chapters |
| `factuality.evaluate` | Evaluate 7 quality metrics, enforce unsupported_claim_rate gate |

## Evidence

- **source.search**: `research/sources/base.py` defines `BaseSourceConnector` with `search()`. `research/sources/internal_mirage.py` provides concrete implementation via Mirage VFS.
- **evidence.extract**: `research/extractors/markdown.py` parses `.md` into `SourceDocument` with `content_hash`. Extensible to other formats.
- **claim.mine**: Schema `Claim` + `ClaimEvidenceLink` in `research/schemas.py` define the data model. Miner implementation follows DAG node R4-R5.
- **citation.verify**: `CitationSpan` schema with `span_text`, `evidence_id`, `match_status` fields. Verification logic in DAG node R7.
- **report.compile**: `ReportAST` schema with ordered sections. Compiler assembles sections without generating new content (DAG node R9).
- **factuality.evaluate**: 7-metric evaluation gate: unsupported_claim_rate, citation_span_accuracy, source_authority_score, freshness_score, contradiction_coverage, section_repetition_rate, cross_section_consistency.

## Effect

- Research capabilities are registered in `CAPABILITY_RULES` (solar_skills.py) and auto-loaded by `capability_inference.py`.
- `solar-harness capability-list` will list all 6 `research.*` capabilities.
- DAG nodes with research-related keywords auto-infer these capabilities via pattern matching.
- Activation proof verifies each capability resolves to the `solar-deep-research` provider.

## Scope

- **In scope**: Source connectors, extractors, schemas, capability registration, DAG template enforcement.
- **Out of scope**: External web search (Brave/Exa/Tavily) — deferred to S05. Academic search (OpenAlex/S2) — deferred to S05. LLM-driven claim mining — deferred to S06.

## Activation Proof

```bash
# Verify all 6 capabilities are registered
solar-harness capability-list | grep '^research\.'

# Verify pattern matching works
python3 -c "
from pathlib import Path; import sys
sys.path.insert(0, str(Path.home() / '.solar/harness/lib'))
from capability_inference import infer_capabilities
text = 'source search evidence extract claim mine citation verify report compile factuality evaluate'
matches = infer_capabilities(text)
caps = set()
for m in matches:
    caps.update(m['capabilities'])
research_caps = [c for c in caps if c.startswith('research.')]
print(f'Found {len(research_caps)} research capabilities: {sorted(research_caps)}')
assert len(research_caps) >= 6
"
```
