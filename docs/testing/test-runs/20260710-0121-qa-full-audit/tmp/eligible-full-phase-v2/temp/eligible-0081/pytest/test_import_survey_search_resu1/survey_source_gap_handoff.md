# Solar DeepResearch Survey Source Gap Handoff

你现在扮演外部搜索研究员。请联网搜索并返回可导入 Solar DeepResearch 的 Markdown。不要写最终报告，只补证据。

## Survey Brief
latent reasoning

## Current Gap
- Output dir: `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0081/pytest/test_import_survey_search_resu1`
- Sources: `16`
- Evidence: `64/8`
- Claims: `64/8`
- Required returned Source blocks: `12` minimum
- Required source types: `benchmark, code, official_doc, paper`
- Missing source types: `benchmark, code, official_doc, paper`
- Issues:
- N/A

## Query Plan

| Source Type | Min Results | Query |
|---|---:|---|
| benchmark | 3 | `latent reasoning benchmark primary source literature lineage method taxonomy evaluation protocol controversy engineering` |
| code | 3 | `latent reasoning code primary source literature lineage method taxonomy evaluation protocol controversy engineering` |
| official_doc | 3 | `latent reasoning official_doc primary source literature lineage method taxonomy evaluation protocol controversy engineering` |
| paper | 3 | `latent reasoning paper primary source literature lineage method taxonomy evaluation protocol controversy engineering` |

## Required Research Angles

每个返回源必须填写 `Research Angles:`，并且整份 `returned_sources.md` 至少覆盖以下五类。一个 source 可以覆盖多类，用逗号分隔；不要只堆链接，必须说明它补的是谱系、方法、评估、争议还是工程缺口。

| Angle Key | Meaning | Query |
|---|---|---|
| literature_lineage | 文献谱系 / Literature lineage | `latent reasoning 文献谱系 / Literature lineage primary source` |
| method_taxonomy | 方法分类 / Method taxonomy | `latent reasoning 方法分类 / Method taxonomy primary source` |
| evaluation_protocol | 评估协议 / Evaluation protocol | `latent reasoning 评估协议 / Evaluation protocol primary source` |
| controversy | 争议反证 / Controversy and negative evidence | `latent reasoning 争议反证 / Controversy and negative evidence primary source` |
| engineering | 工程部署 / Engineering and deployment | `latent reasoning 工程部署 / Engineering and deployment primary source` |

## How To Use

1. Copy the entire block under `Copy/Paste returned_sources.md Template`.
2. Ask Gemini/GPT/browser research to fill every `## Source N:` block with real sources.
3. Save the filled Markdown as `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0081/pytest/test_import_survey_search_resu1/returned_sources.md`.
4. Continue with:

```bash
solar-harness research survey-continue --output-dir "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0081/pytest/test_import_survey_search_resu1" --brief "latent reasoning" --returned-md "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0081/pytest/test_import_survey_search_resu1/returned_sources.md" --require-complete --json
```

## Rules
- Fill all 12 `## Source N:` blocks. Each block should include at least two Key Claims and enough quote/summary detail to import as evidence.
- Every source must include `Research Angles:` using one or more keys: `literature_lineage, method_taxonomy, evaluation_protocol, controversy, engineering`.
- Across the whole file, cover all five research angles at least once: literature lineage, method taxonomy, evaluation protocol, controversy/negative evidence, and engineering/deployment.
- Prefer primary/canonical sources: papers, official docs, GitHub repos, benchmarks, standards, model cards.
- Do not invent links, paper names, benchmark numbers, or quotes.
- Include contradiction/negative evidence when found.
- Keep summaries factual and citation-ready.
- Use Source Type values: `paper`, `official_doc`, `code`, `benchmark`, `dataset`, `standard`, `web`, `other`.

## Copy/Paste returned_sources.md Template

```markdown
# External Search Results: latent reasoning

## Source 1: <title>
URL: <https://...>
Publisher: <publisher or N/A>
Published: <date or N/A>
Source Type: benchmark
Research Angles: literature_lineage

Summary:
- <2-5 factual bullets covering the selected Research Angles>

Key Claims:
- <claim supported by this source>
- <claim supported by this source>

Relevant Quotes:
> <short quote or N/A>

Why this source fixes the gap:
- <which missing source type, research angle, or claim gap it covers>


## Source 2: <title>
URL: <https://...>
Publisher: <publisher or N/A>
Published: <date or N/A>
Source Type: code
Research Angles: method_taxonomy

Summary:
- <2-5 factual bullets covering the selected Research Angles>

Key Claims:
- <claim supported by this source>
- <claim supported by this source>

Relevant Quotes:
> <short quote or N/A>

Why this source fixes the gap:
- <which missing source type, research angle, or claim gap it covers>


## Source 3: <title>
URL: <https://...>
Publisher: <publisher or N/A>
Published: <date or N/A>
Source Type: official_doc
Research Angles: evaluation_protocol

Summary:
- <2-5 factual bullets covering the selected Research Angles>

Key Claims:
- <claim supported by this source>
- <claim supported by this source>

Relevant Quotes:
> <short quote or N/A>

Why this source fixes the gap:
- <which missing source type, research angle, or claim gap it covers>


## Source 4: <title>
URL: <https://...>
Publisher: <publisher or N/A>
Published: <date or N/A>
Source Type: paper
Research Angles: controversy

Summary:
- <2-5 factual bullets covering the selected Research Angles>

Key Claims:
- <claim supported by this source>
- <claim supported by this source>

Relevant Quotes:
> <short quote or N/A>

Why this source fixes the gap:
- <which missing source type, research angle, or claim gap it covers>


## Source 5: <title>
URL: <https://...>
Publisher: <publisher or N/A>
Published: <date or N/A>
Source Type: benchmark
Research Angles: engineering

Summary:
- <2-5 factual bullets covering the selected Research Angles>

Key Claims:
- <claim supported by this source>
- <claim supported by this source>

Relevant Quotes:
> <short quote or N/A>

Why this source fixes the gap:
- <which missing source type, research angle, or claim gap it covers>


## Source 6: <title>
URL: <https://...>
Publisher: <publisher or N/A>
Published: <date or N/A>
Source Type: code
Research Angles: literature_lineage

Summary:
- <2-5 factual bullets covering the selected Research Angles>

Key Claims:
- <claim supported by this source>
- <claim supported by this source>

Relevant Quotes:
> <short quote or N/A>

Why this source fixes the gap:
- <which missing source type, research angle, or claim gap it covers>


## Source 7: <title>
URL: <https://...>
Publisher: <publisher or N/A>
Published: <date or N/A>
Source Type: official_doc
Research Angles: method_taxonomy

Summary:
- <2-5 factual bullets covering the selected Research Angles>

Key Claims:
- <claim supported by this source>
- <claim supported by this source>

Relevant Quotes:
> <short quote or N/A>

Why this source fixes the gap:
- <which missing source type, research angle, or claim gap it covers>


## Source 8: <title>
URL: <https://...>
Publisher: <publisher or N/A>
Published: <date or N/A>
Source Type: paper
Research Angles: evaluation_protocol

Summary:
- <2-5 factual bullets covering the selected Research Angles>

Key Claims:
- <claim supported by this source>
- <claim supported by this source>

Relevant Quotes:
> <short quote or N/A>

Why this source fixes the gap:
- <which missing source type, research angle, or claim gap it covers>


## Source 9: <title>
URL: <https://...>
Publisher: <publisher or N/A>
Published: <date or N/A>
Source Type: benchmark
Research Angles: controversy

Summary:
- <2-5 factual bullets covering the selected Research Angles>

Key Claims:
- <claim supported by this source>
- <claim supported by this source>

Relevant Quotes:
> <short quote or N/A>

Why this source fixes the gap:
- <which missing source type, research angle, or claim gap it covers>


## Source 10: <title>
URL: <https://...>
Publisher: <publisher or N/A>
Published: <date or N/A>
Source Type: code
Research Angles: engineering

Summary:
- <2-5 factual bullets covering the selected Research Angles>

Key Claims:
- <claim supported by this source>
- <claim supported by this source>

Relevant Quotes:
> <short quote or N/A>

Why this source fixes the gap:
- <which missing source type, research angle, or claim gap it covers>


## Source 11: <title>
URL: <https://...>
Publisher: <publisher or N/A>
Published: <date or N/A>
Source Type: official_doc
Research Angles: literature_lineage

Summary:
- <2-5 factual bullets covering the selected Research Angles>

Key Claims:
- <claim supported by this source>
- <claim supported by this source>

Relevant Quotes:
> <short quote or N/A>

Why this source fixes the gap:
- <which missing source type, research angle, or claim gap it covers>


## Source 12: <title>
URL: <https://...>
Publisher: <publisher or N/A>
Published: <date or N/A>
Source Type: paper
Research Angles: method_taxonomy

Summary:
- <2-5 factual bullets covering the selected Research Angles>

Key Claims:
- <claim supported by this source>
- <claim supported by this source>

Relevant Quotes:
> <short quote or N/A>

Why this source fixes the gap:
- <which missing source type, research angle, or claim gap it covers>

```
