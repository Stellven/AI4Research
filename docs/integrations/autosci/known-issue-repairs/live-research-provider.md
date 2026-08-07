# Live Research Provider and State Closure Repair

Date: 2026-08-07
Baseline: `4b5af751956f8ef1d2eb6bbce8baf9088e694d00`
Branch: `codex/known-issues-live-research`

## Scope and repair

- Added the canonical `real_data_research` provider adapter. It executes one
  node at a time and requires `execute -> evidence produced -> evidence
  evaluated -> advance`; it never advances based on a pre-existing evidence
  assumption.
- Provider evidence now records source URL, provider, query, retrieval time,
  response status, and content SHA-256. The canonical run-state transaction is
  `research-run-state.json` plus its journal; no wiki or legacy state sidecar
  is written by this flow.
- A timeout, 429/5xx, or provider-unavailable outcome has a finite retry
  budget. It writes a resume token and preserves the completed-node prefix.
  A completed run is idempotent and does not call the provider again.
- Semantic Scholar retry behavior now includes bounded retry for timeout/
  transport and 5xx responses as well as 429, with attempt evidence.

## Executed evidence

| Check | Result | Evidence |
|---|---|---|
| Offline provider/state regression | PASS, 37 passed | `tests/repairs/live_research_provider/test_live_research_provider.py` plus state/storage regressions |
| Live website discovery, baseline J05 | BLOCKED | `outputs/phase22-real-journeys/p22j05-20260807T182332Z-23600/journey-result.json` |
| Live provider-adapter topic survey and synthesis | PASS | `.codex-tmp/live-research-provider-live-survey/research-run-state.json` |
| Resume after injected timeout | PASS (offline injected provider failure) | repair regression test |
| Provider failure negative case | PASS (offline injected 5xx) | repair regression test |
| J20 production journey | FAIL | `outputs/phase22-real-journeys/p22-j20-20260807T183119Z/journey-result.json` |

The live adapter run used the production `LiteratureDiscoveryService`. It
persisted four OpenAlex source records with a `200` response status and created
a report that contains the requested topic and every cited source URL.

## Remaining closure boundary

J05 anchor discovery completed, but its topic request timed out at the native
`tools/discover.py` boundary. J20 also routes through the current autosci
bin/native discovery path and received an empty shortlist, so it did not reach
direct provider-backed technical-signal or trend/gap evidence. Those bin files
are expressly outside this repair's allowed modification scope. Accordingly,
E02/E03/E04/E05/N09/T02 remain partial rather than being marked closed by the
new adapter evidence.

No credential values were printed, stored in repair evidence, or committed.
