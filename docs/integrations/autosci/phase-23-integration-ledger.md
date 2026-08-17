# Phase 23 Canonical Integration Ledger

Date: 2026-08-17
Publishing branch: `openJiuwen-Solar`
Verified repair base: `bc3e9ff59d6d11d7a90fd9a2fb4052b51fc76896`

This ledger freezes the branch audit used to make `OpenSolar-Canonical` the
continuing local source of truth. A branch name or similar commit subject is
not evidence of integration. Every candidate is classified as `accepted`,
`superseded`, `obsolete`, or `rejected` using immutable hashes.

## Accepted mappings

| Candidate | Original hash | Integrated hash | Evidence |
| --- | --- | --- | --- |
| `codex/phase22-journey-closures` | `94e0de78e1e829b2896c888c2ca5d6acbae9ed2d` | `55ec2ea78f74ce157b0cec4314861a44bef2a040` | Conflict-reviewed cherry-pick preserved the Phase 22 report closure, desktop initial-navigation token, Phase 23 log, and stronger workbook assertions. |
| `upstream/stellven codex/fix-epic-activation-wip-gate` | `7c9e304c4d9a9a908e5f7deb4e95ca6fba96ea8c` | `7d7ae2a1d9f5264764b1a7eafbe499047c028ca9` | Conflict-free cherry-pick; `tests/harness/test_epic_decomposer.sh` then passed 20/20 on WSL. |
| `browser-operator-fix` profile-copy component | `a2f58054b6b633fb81aa1975b8b701ff27f87274` | `bc3e9ff59d6d11d7a90fd9a2fb4052b51fc76896` | The still-useful volatile extension/cache exclusion was ported into the newer browser runtime and covered by `test_stage_browser_profile_skips_volatile_extension_assets`. The old branch tip as a whole is superseded below. |

All three integrated hashes are ancestors of the verified repair base. The
original hashes are intentionally not treated as ancestors when their changes
were cherry-picked or ported into newer code.

## Local branch tips

`git cherry openJiuwen-Solar <tip>` returned only `-` entries for every row
marked "patch-equivalent" below. Those tips are superseded because their patch
content already exists under a different reachable commit.

| Local branch | Tip hash | Classification | Reason or replacement |
| --- | --- | --- | --- |
| `codex/known-issues-adaptive-routing` | `514437e18382cb7da419d22d056e58a14d33c0ba` | superseded | Patch-equivalent in main. |
| `codex/known-issues-advanced-optimization` | `0e1c7a1a33a6dd24f868e396664d168b113d1e0a` | superseded | Patch-equivalent in main. |
| `codex/known-issues-identity-privacy-channels` | `7f211c4010c5aeea319eb92b1b2e763ffbf91895` | superseded | Patch-equivalent in main. |
| `codex/known-issues-live-research` | `0acf93ccc7f0f4aa411e019a0c6d9971dc108d89` | superseded | Patch-equivalent in main. |
| `codex/known-issues-model-training` | `a2880cc0b532b120fb7486d6f6677a2a28590f05` | superseded | Patch-equivalent in main. |
| `codex/known-issues-research-control-plane` | `a254ac45387ce4be50986a4d785a1d01b16c7a36` | superseded | Patch-equivalent in main. |
| `codex/known-issues-reviewer-independence` | `c0629cc6426bc6720ee90a4efaed84d8d7f58b5a` | superseded | Patch-equivalent in main. |
| `codex/known-issues-runtime-platform` | `34c7682563bf750d14ea8c0eaa45e8c8bc9274cb` | superseded | Patch-equivalent in main. |
| `codex/known-issues-user-entrypoints` | `6ef6f0cd2c09f2930bc1c667134a12e1464d4c81` | superseded | Patch-equivalent in main. |
| `codex/legacy-fix-r1-control-plane` | `8b8acb7397496e62b48e5b781e933339445774b0` | superseded | Patch-equivalent in main. |
| `codex/legacy-fix-r2-research-operators` | `3bc9f20e2b675f9285b7720fd24cdaf3aafb5997` | superseded | Patch-equivalent in main. |
| `codex/legacy-fix-r3-experiment` | `c88680e49257cfd02fd520c4324cdd72a4f59fdd` | superseded | Current experiment lifecycle implementation and tests replace the old path; audited replacement baseline `32b4fc8d1`. |
| `codex/legacy-fix-r4-runtime-verification` | `182df830eb50e88e4e84f48fdda3822ce1b1afb1` | superseded | Current benchmark/runtime-verification contracts replace the old path; audited replacement baseline `d1a99171f`. |
| `codex/legacy-fix-r5-platform` | `dead34b7e1f88bdc42fed68f3d80568cccfdd1e7` | superseded | Current platform/status routes and moved tests replace the old path; audited replacement baseline `3acd97eff`. |
| `codex/legacy-fix-r6-identity` | `9a5e1390f2291bcaf5c1cbcf5a9f1bf85aed92e8` | superseded | Patch-equivalent in main. |
| `codex/legacy-fix-r7-advanced` | `34f5cb017c68690bd6930eaaa1f3d895005ad091` | superseded | Patch-equivalent in main. |
| `codex/legacy-fix-r8-governance` | `2a7aeb9af6bd83db7c149be95a303100fe9dd307` | superseded | Patch-equivalent in main. |
| `codex/p22-113-decision-artifact` | `319bc0462452908f5740a5a25d2aee11aa7f3101` | superseded | Four patch-equivalent commits are in main. |
| `codex/p22-119-runtime-deliverable` | `43e7175d4a6ba0ecb9020d397340e3f2f797de6b` | superseded | Ten patch-equivalent commits are in main. |
| `codex/p22-blocker-j21-wave2` | `aaff49986a8f3816a60e2ec4d0557c9b28d05a3d` | superseded | Two patch-equivalent commits are in main. |
| `codex/p22-blocker-poc-design-wave3` | `e46f57850b62bf17f2e5aed2f68284b4ad45a2f9` | superseded | Three patch-equivalent commits are in main. |
| `codex/p22-blocker-research-rich-wave3` | `1a723eb986cc2a50b46e53a80c5e240a7c3b0b94` | superseded | Five patch-equivalent commits are in main. |
| `codex/p22-blocker-research-wave2` | `95812f7c5fa9434c29eccfab29bb559f7369c2fb` | superseded | Patch-equivalent in main. |
| `codex/p22-j21-evidence-closure` | `7f6b5a0e3c4ee27db48f42b34d226ce8847b3de1` | superseded | Three patch-equivalent commits are in main. |
| `codex/phase01-capability-route` | `78988f85ce8fe9a79e6b92ad4da2a4a340eb2d95` | superseded | Patch-equivalent in main. |
| `codex/phase01-contracts` | `4b4cae7578ba565f49e801a3ee31f37cf1864544` | superseded | Patch-equivalent in main. |
| `codex/phase01-graph` | `44ee27c6ef531d10ed472fe548e296f0d6cabf36` | superseded | Patch-equivalent in main. |
| `codex/phase01-intent` | `787e1e965a680da69eac8e1aee29a5958ac9c4c5` | superseded | Patch-equivalent in main. |
| `codex/phase2-dispatch` | `dc58bf56c975c912621c8c5feee8d805693dc403` | superseded | Six patch-equivalent commits are in main. |
| `codex/phase2-orchestrator` | `b12efb7245c29c0983a6041c53c71636e7763c0a` | superseded | Five patch-equivalent commits are in main. |
| `codex/phase2-resilience` | `5bc14db089cdc4971fbd946b3ef5a24b9bffcc80` | superseded | Four patch-equivalent commits are in main. |
| `codex/phase2-synthesis-operators` | `94957e264ad9fd00c921da4cfacad574decb062d` | superseded | Five patch-equivalent commits are in main. |
| `codex/phase3-evidence-operators` | `e09555f7438d060547c298205d3bbbeb9bc370a7` | superseded | Patch-equivalent in main. |
| `codex/phase3-lifecycle-operators` | `9393ea2c5ebb360375dc75043703c3043abe0068` | superseded | Patch-equivalent in main. |
| `codex/phase3-runtime-route` | `fca09f838dd7dbc7ac5514a07ce167c563c54034` | superseded | Patch-equivalent in main. |
| `codex/phase4-generalization` | `026d10be2ec855573bde5feed499d8a0d62f506b` | superseded | Patch-equivalent in main. |
| `codex/phase4-lifecycle-recovery` | `78cdf00d877fa8700b30ab09c9c990e844e25fca` | superseded | Patch-equivalent in main. |
| `codex/phase5-content-diversity` | `f367116454bd4a1ff6d36566012bca2e7e8d0ff3` | superseded | Patch-equivalent in main. |
| `codex/phase5-lifecycle-recovery` | `c74195be4ede63060ea04c4a61264ad8f6e83613` | superseded | Patch-equivalent in main. |
| `codex/phase5-lifecycle-rerun-final` | `a41848fc3996ae201500f33ef1016f91b735b534` | superseded | Patch-equivalent in main. |
| `codex/phase5-platform-provider` | `22d4ad83d4ee1ef30a834090d25fad370921ef00` | superseded | Current moved tests plus `22e911dac390cd08bf5e1284faebcf91d4938aae` retain the applicable behavior without restoring obsolete paths. |
| `codex/phase5-platform-rerun-final` | `82979db091a6f3af9d22a066a04f3fe998cdc7c3` | superseded | Patch-equivalent in main. |
| `codex/phase5-seed-portability` | `205a9eb7c5f771e848c75344ea6d30b7ae5bcaad` | superseded | Patch-equivalent in main. |
| `codex/pre-baseline-integration-snapshot` | `b928e2314fe3dc2f534202f50f839f488bd29e12` | obsolete | Would restore the forbidden `real_data_research` monolith and old test locations; current capability registry explicitly rejects that architecture. |
| `codex/severity-repair-p0-experiment-20260810` | `045c418c28796ae7fbd05ca5e49a2472915e4876` | superseded | Three patch-equivalent commits are in main. |
| `codex/severity-repair-p0-orchestration-20260810` | `2ab151c9dac212e781b5f466af3dcc749d2a570d` | superseded | Patch-equivalent in main. |

## Remote-only unique tips

Each row covers the identically hashed `upstream/` and `stellven/` ref where
both exist. Remote history was reviewed by changed files and current-path
equivalence, not by commit subjects alone.

| Remote ref suffix | Tip hash | Classification | Reason or replacement |
| --- | --- | --- | --- |
| `codex/graph-eval-drain-routing` | `105701fcab371a45cc5a48204c9bcc43cf7b7acc` | superseded | Current graph dispatcher, eval drain, and entrypoint metadata implementations are later and covered by current graph tests. |
| `codex/evaluator-sidecar-closeout` | `2a2014165dfd534b4c946776370981a14623914f` | superseded | Current evaluator closeout/requeue flow replaces the sidecar-era implementation. |
| `codex/pm-router-parallelism-fix` | `2c4d44122a01ed9fef5d8180975aec46f72e0732` | superseded | Parallel PM routing behavior is already present in the current router. |
| `codex/dispatch-pool-reconcile-fix` | `383dfed94d746f550123eaf21cff71e0a8415d22` | superseded | Current PM closeout and graph dispatch reconciliation is later than this tip. |
| `docs/solar-homepage-svg-architecture` | `3bc2c98ad99de998bd9f827b2ebb10fa85567d37` | superseded | The SVG architecture files at this tip are already present in the current tree. |
| `codex/evaluator-control-plane` | `4cd64d65df648b6376a05efcf6e267f53abf5579` | superseded | Current evaluator control plane and task graph closeout are later. |
| `task/ci-pr-advisory-baseline` | `4e33426ac5a8b95c458fa9cf61308c8ff991a91c` | superseded | The CI workflow and jsonschema installation changes are already present. |
| `codex/pr13-main-conflict-resolution` | `55f9b8f7dab2a4242724227dd3d7c1c24544a676` | superseded | Current intent and PM DAG code contains the conflict-resolved behavior. |
| `codex/operator-view-status-fix` | `58af1649d2640c08d20e461507fbb8ebe31dc456` | superseded | Current pane overlay/status view includes this behavior and later changes. |
| `codex/chatgpt-report-operator` | `6904a0a5005bf98aa4a9b6f0ff9b023e9b1af809` | superseded | Current browser/ChatGPT report wrapper is a later implementation. |
| `fix/issue-7-intent-truncation` | `75235d39a992124bacc58d9e680c60bd2e60a1b6` | superseded | `git cherry` reports the fix as patch-equivalent in main. |
| `codex/tech-hotspot-auth-rate-limit-fix` | `7a4d154a73f7489b9b2b43a0a3efe73992f2df71` | superseded | Current technology hotspot browser provider contains the auth/rate-limit handling. |
| `codex/eval-quota-requeue` | `7cfc18a513a2a34f1939df3fad22dc50f1cfdd78` | superseded | Applicable quota/requeue and secret-scan behavior exists in current focused modules; the branch also carries unrelated historical commits and is not safe to merge wholesale. |
| `memrl-clean` | `8ee2861f4457ffddc0536a21918ca23d8c232336` | rejected | Unrelated product history; no approved OpenSolar fix was identified at the tip. |
| `security-fix-20260430` | `94621fccd5a427753cc79d783f2bb84ddd55b67d` | superseded | Current generic PII/secret policy and release scanning replace the older literals. |
| `codex/browser-operator-fix` | `a2f58054b6b633fb81aa1975b8b701ff27f87274` | superseded | The current browser wrapper is later; its one missing profile-copy component was accepted into `bc3e9ff59` above. |
| `codex/gpt-requirement-writer` | `a922e64033e4ea647344bff9d3e0f92d821cfdff` | obsolete | Targets actor runtime artifacts and an older requirement-writer layout that is not part of the current architecture. |
| `codex/live-dispatch-retry-visibility-fix` | `d1d19459e148cba9555ef2e990aacaec6249e97f` | superseded | Current dispatch retry state and visibility markers already cover this change. |
| `codex/runtime-drift-writepath-fix` | `d4fcc214d00dc93edee8ba3fa33cd768d0b89620` | superseded | Current runtime drift write path contains this behavior. |
| `codex/browser-webwright-bridge-clean` | `f8c7da290edea3e2fd19bfd864e32f093a676026` | superseded | Two commits are patch-equivalent in main. |

## Gate result

- Local non-ancestor refs classified: 47 of 47.
- Remote non-ancestor refs classified: 42 refs sharing 21 unique tips.
- Accepted integrated hashes reachable from `bc3e9ff59`: 3 of 3.
- Unclassified candidate fixes: 0.
- No remote push was performed.
