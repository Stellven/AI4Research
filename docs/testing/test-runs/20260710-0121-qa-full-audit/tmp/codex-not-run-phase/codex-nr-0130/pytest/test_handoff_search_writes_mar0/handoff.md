# Solar DeepResearch Human Search Handoff

你现在扮演外部搜索研究员。请联网搜索并返回可被 Solar-Harness 导入的 Markdown。

## Research Topic
human loop topic

## Search Query
human loop query

## Research Profile
- Profile: `general`
- Required source types: N/A
- Recommended source types: N/A
- Target source types for this handoff: general
- Minimum distinct source types: 1

## Source Matrix / Query Plan

| Source Type | Min Results | Query |
|---|---:|---|
| general | 3 | `human loop query` |

## Constraints
- Prefer primary sources for each requested source type.
- Cover the Source Matrix before adding optional sources.
- Return at most 3 high-quality sources.
- Do not invent links.
- Every source must include a URL.
- Include disagreements, uncertainty, or contradictions if found.
- Keep summaries factual and citation-ready.
- Use these normalized Source Type values when possible: `paper`, `code`, `official_doc`, `benchmark`, `dataset`, `news`, `company`, `standard`, `web`, `other`.

## Solar Metadata
- Run ID: `095f0760d40fd6bda0154ccd347e43fc`
- Import target: `solar-harness research import-search`

## Required Output Format

```markdown
# External Search Results: human loop topic

## Source 1: <title>
URL: <https://...>
Publisher: <publisher or N/A>
Published: <date or N/A>
Source Type: <paper|code|official_doc|benchmark|dataset|news|company|standard|web|other>

Summary:
- <2-5 factual bullets>

Key Claims:
- <claim supported by this source>
- <claim supported by this source>

Relevant Quotes:
> <short quote or N/A>

## Source 2: <title>
URL: <https://...>
Publisher: <publisher or N/A>
Published: <date or N/A>
Source Type: <paper|code|official_doc|benchmark|dataset|news|company|standard|web|other>

Summary:
- ...

Key Claims:
- ...

Relevant Quotes:
> ...
```

## After You Return Results
The user will paste/save your Markdown and run:

```bash
solar-harness research import-search <db.sqlite> --run-id <run_id> --input-md <results.md> --continue --output-dir <out>
```
