# DeepResearch Source Gap Handoff

## Audit Result
- Profile: `technical_architecture`
- Output dir: `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0085/pytest/test_source_audit_enqueue_foll0/out`
- Status: `failed`
- Source count: `1`
- Source type counts: `{"paper": 1}`
- Authority average: `0.9`
- Errors: `source_type_count_too_low:1<2, high_authority_sources_too_low:1<2`
- Warnings: `missing_recommended_source_types:benchmark,code,official_doc`

## Missing Source Types
- benchmark
- code
- official_doc

## Replacement Suggestions
- Add benchmark source for profile technical_architecture
- Add code source for profile technical_architecture
- Add official_doc source for profile technical_architecture

## Current Sources
| source_type | authority | title | url |
|---|---:|---|---|
| paper | 0.90 | Paper | https://arxiv.org/abs/2501.00001 |

## Search Tasks
- Search for `out` with source type `benchmark`. Prefer primary/canonical sources and reject SEO summaries.
- Search for `out` with source type `code`. Prefer primary/canonical sources and reject SEO summaries.
- Search for `out` with source type `official_doc`. Prefer primary/canonical sources and reject SEO summaries.

## Instructions For Gemini/GPT/Browser-Use
Find sources that close the missing source-type gaps. Return concise source blocks only. Do not write the final report. Prioritize canonical artifacts:
- `code`: GitHub repository, official implementation, reproducibility repo, release notes.
- `official_doc`: vendor/lab/project documentation, model card, official blog, standard/spec.
- `benchmark`: benchmark paper, leaderboard, evaluation suite, dataset card, official result table.
- `paper`: arXiv/OpenReview/DOI/Semantic Scholar primary paper.

## Required Return Format
```markdown
## Source 1
Title:
URL:
Source Type: paper|code|official_doc|benchmark|dataset|news|company|standard
Publisher:
Published:
Summary:
- 
Key Claims:
- 
Relevant Quotes:
> 
Why this source fixes the gap:
- 

```

## Continue Command
After saving the returned Markdown, import it with:

```bash
solar-harness research import-search <db_path> --run-id <run_id> --input-md <returned_sources.md> --continue --output-dir /Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0085/pytest/test_source_audit_enqueue_foll0/out
```
