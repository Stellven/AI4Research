# AI4Research selective integration ledger

Date: 2026-08-24
Target branch: `ai4research-main`
Target baseline: `4a6f76b450ff0991327887cb1b7fc73318cd6466`
Candidate branch: `task/research-evidence-to-poc-fixed`
Candidate tip: `a8e9d31a9bb5fdde2da4b48fbaf5a95112d02a71`

## Architecture decision

The architecture note supplied by the owner is treated as design context, not
as executable instructions. Its required control flow is:

`RawIntent -> Requirement IR -> elastic planner -> direct answer | memoized DAG | new DAG -> scheduler -> evaluator`

For a planned DAG, logical operators are the nodes; contracts, capability
capsules, candidate physical operators, and physical-operator fallbacks are
planner output. The scheduler activates dependency-ready nodes. Evaluators gate
node completion against contracts.

The candidate branch deliberately implemented a different policy: all research
requests bypass the planner and instantiate a fixed 15-node workflow. Therefore
the fixed workflow is accepted only as a reusable memoized TaskGraph template
and physical execution/evidence implementation. A local follow-up adaptation
must return selection authority to the planner before this integration is
considered complete.

## Disposition rules

- `accepted`: reusable product code or regression coverage that belongs in the
  planner, TaskGraph, capsule/operator, scheduler/dispatcher, evaluator, or
  observability layers.
- `rejected`: session handoff, run narrative, or temporary task-management
  documentation. Suraj's own change audit says to exclude `docs/internal/`
  from the product commit.
- Accepted commits are cherry-picked with `-x`, retaining Suraj as author and
  recording the immutable source hash.

## Candidate ledger

| # | Source commit | Disposition | Architectural reason |
|---:|---|---|---|
| 1 | `38e64de4c20181963371999a387540463a1fde82` | accepted | Adds operator and graph lifecycle observability needed across planner, scheduler, dispatcher, and evaluator boundaries. |
| 2 | `7302ab2ba0bba261b539e0e5d1d55068d33c59fb` | accepted | Makes real E2E runs terminal and records teardown; useful journey evidence rather than topology policy. |
| 3 | `8d79c10a7d673268282aac3bdcd187fa05143c76` | accepted | Supplies the reusable research TaskGraph template, contracts, capsules, physical operators, adapters, and evaluation seams. Its automatic planner bypass is accepted only subject to the follow-up planner-authority adaptation. |
| 4 | `a82376f4d1fb86205b376e9acc120d7f440c4a27` | accepted | Adds the bounded AutoSci skill executor used as a physical-operator seam. |
| 5 | `ecbeb0d7a94a334ce6fcb897953d31d3f693b674` | accepted | Improves evidence relevance and request-tier metadata; tier output is a planner hint, not final routing authority. |
| 6 | `f30e8a311661aeaca952aa9a5f01143de9b664cf` | rejected | Session handoff and UI proposal only; no required product behavior. |
| 7 | `8a41c42c836d25a2ebfa66fc77f0cda659c208bf` | accepted | Expands governed source discovery and tier-aware prompts behind research physical operators. |
| 8 | `1eaf296b1788f6cd4b3573d3efed9aa16c578246` | rejected | Historical session narrative; source commits provide the authoritative implementation. |
| 9 | `cbce9d265b1ef8d5a5b4556f65adfc1b13722da9` | accepted | Carries stage identities through Part B so TaskGraph edges and artifacts remain traceable. |
| 10 | `f33103dd3a09791d50b4b67e67abef6a5f9ee215` | accepted | Prevents a physical operator from claiming fixture work it did not execute. |
| 11 | `ca3b283017b7888fb92b9eefd07fc9a0ff386c9b` | accepted | Enforces fail-closed timeout semantics at the physical-operator boundary. |
| 12 | `dd76aa5ccf6f0b1bf0bef0f985e0c146d61502cc` | accepted | Adds per-stage forensic evidence required for evaluator and runtime diagnosis. |
| 13 | `eafb69bd996fae9f6cc88efe2d204368e7e1e131` | accepted | Repairs sandbox interpreter access without changing planning policy. |
| 14 | `fff86a468141e91a16f1f0ee5b6b252b41220e5a` | accepted | Preserves partial operator evidence when a run is terminated. |
| 15 | `21bbeba58528c90b19f1384153447902f2ecf4af` | accepted | Adds contract-driven workflow gates and closes a relevance validation gap. |
| 16 | `a714e6b2f26d533da54c7c3b89470f5c797c3b63` | accepted | Makes validators resolve the workspace declared by the TaskGraph contract. |
| 17 | `4ecfee8c78e5f62afeb73b95d1ff9643091c1df1` | accepted | Aligns claim and sprint-root lookup with actual artifact locations. |
| 18 | `102573f3c69340a9e9e5fe90c30e6f2bac6d52ca` | accepted | Prevents an evaluator from requiring an artifact produced by a later node. |
| 19 | `a2c4981bf618046afc8d3c31a095c7edeaaec95c` | accepted | Reuses the canonical grounded-synthesis physical operator instead of duplicating it. |
| 20 | `21d92302fe891ca0d3eb8679ca96f6990021f858` | accepted | Regression coverage for the canonical grounded-synthesis binding. |
| 21 | `2d26f45c364e689ae683953b3959f482787f6d84` | accepted | Adds selectable Codex/Claude backend implementations; they are candidate physical operators, while planner/scheduler must own selection. |
| 22 | `90b516941458d7caac736992f9edb8e05b160e3c` | accepted | Adds a live run telemetry view without changing control-flow ownership. |
| 23 | `ee1f8955fe63370f80c5e5f29e5bc18da8aab2f8` | accepted | Repairs the Claude backend import seam required by accepted commit 21. |
| 24 | `caa20200f347b3d92ef6459ce7b153fcff725099` | rejected | Session handoff only. |
| 25 | `481dfd2cce107192f0bcd944a3bd874011a76120` | rejected | Historical failed-run note only. |
| 26 | `ca76f6b2871f2693e9c56a563175ec0fea0e91a0` | rejected | Historical provider-guard explanation only. |
| 27 | `1bb14c2cc3c3f5db825d7a9a341a72962902f49f` | accepted | Records the physical provider actually selected so planner intent and runtime choice can be audited. |
| 28 | `ae5db7dadf7183163e6b9e3e1348ec66274937a8` | rejected | Correction to session documentation only. |
| 29 | `adade063fc5fae8a0da7be88fe8d45c4965cc1aa` | rejected | Correction to session documentation only. |
| 30 | `b9e4c777c21ee2b3f878c76311ce65273fecb9b6` | rejected | Correction to session documentation only. |
| 31 | `6b7acb057118d93fd9fc18b1d85f88bfc917282e` | rejected | Dry-run narrative only. |
| 32 | `40c932e3f6ff1e0b499d33f61f2ef048d83c8be0` | accepted | Preserves synthesis section structure in the report artifact. |
| 33 | `ec279ea183e00e76ae8aa11d30d86e17ea1e1893` | rejected | Historical sectioning follow-up note only. |
| 34 | `8212ef26ba6682b97fd439e2ecf7eda4a74b3150` | rejected | Historical open-finding note only; later accepted fixes are authoritative. |
| 35 | `4873338d311c825b539bfd9b9bd0fe8ff15edf87` | rejected | Historical failed-gate note only; later accepted fixes are authoritative. |
| 36 | `601eed0706ed084489fa6f2e9fdbddde0574f4b5` | rejected | Historical retry-failure note only. |
| 37 | `7d6c851930a7bbb124638ad80a1d041bc73f9048` | accepted | Requires every TaskGraph stage to prove its own completion before the scheduler advances. |
| 38 | `fa43017689250a4073dd8dc9af5f7259ad4cd5cd` | rejected | Historical run narrative only. |
| 39 | `0fc36ff8df7ce54447b990556629d3fc40986f4a` | accepted | Adds native fixed-workflow forensic telemetry. |
| 40 | `319e2640511951f0ab2e50d548a31128e94fbc88` | accepted | Makes report revision evaluation use the actual node requirement. |
| 41 | `a18ac7e3588519b4bf0973f1a21a3af90ec57440` | accepted | Preserves the limitations accepted by the evaluator. |
| 42 | `886ebd51e0fc330354355abc3afdc59d2bafb338` | accepted | Prevents duplicated limitation sections across revision attempts. |
| 43 | `5f91a368a997c6c7c20c2d7956f2f13a5578c0ac` | rejected | Historical goal and blocker note only. |
| 44 | `15c6095b2023a39a0e9cb1e86534f2bbc88d7512` | accepted | Derives stage result paths from contracts and gates all 15 template nodes. |
| 45 | `2e428d0065d5cef264b67f4902456223c88d3282` | accepted | Preserves the invocation journal through resolver copying for trustworthy evidence. |
| 46 | `d93e3c5f117bd042e7e7b780da72c1ea14472aff` | rejected | Historical Part-B precondition note only. |
| 47 | `31c29c9e8b8f7abbbfa68549773b2d3658ffe090` | rejected | Historical E2E result note only; current journey evidence must be generated on this branch. |
| 48 | `d952df36f8b86d694cdea78ecc8927056feabe44` | accepted | Rejects claims unsupported by evidence at the synthesis boundary. |
| 49 | `495f5351c748dff3e424bdabb18563d594b603ad` | rejected | Historical search measurement and owner-decision note only. |
| 50 | `6b0b88c63bab176bc044cbd7b76652cf532e0a72` | rejected | Historical grounding run note only. |
| 51 | `7231486274dae761b02d69efcf1462d92c1f2f79` | accepted | Preserves semantic content without imposing brittle byte identity during revision. |
| 52 | `e7158c89a22a36eed1c99527dc23d22ed2c97238` | rejected | Agent handoff only. |
| 53 | `e7315e44c99bd625bd08f8565fd6c2b0acae707a` | rejected | Historical architectural diagnosis only; accepted operator-binding commits implement the correction. |
| 54 | `f1f2f2531ef19f96586fa733518ff8180452d3e9` | rejected | Historical binding explanation only. |
| 55 | `d45fcc158690ca0e4c7a80db0e5db75fc08dc62b` | accepted | Derives bounded model-call ceilings from physical-operator contracts. |
| 56 | `0549f15c0156564e6d049b5bab0d34d499967d37` | rejected | Historical defect narrative only. |
| 57 | `bed1858c8bdcfde2ba60a435bcda2194e763376e` | rejected | Historical E2E note only. |
| 58 | `d5adbd3782cef5feedd950c638557c57aadf118c` | rejected | Historical bridge test note only. |
| 59 | `443e30ac191c82f9baa79c3653fca1e1df84c8a6` | accepted | Makes Part B consume the actual research report through the registered AutoSci operator. |
| 60 | `b9dfa6cd253b6426ec4baf7c155b8c15bd84963c` | rejected | Historical comparison note only. |
| 61 | `96088dcc2fda491f653459788a711a199c0d6077` | accepted | Keeps synthesis-claim and AutoSci-claim identity spaces explicit and traceable. |
| 62 | `81e95f7e9008627f013308f2908086ce5190e054` | rejected | Historical trap/UAT note only. |
| 63 | `ca58238ada24d4ff99e0327e46ddf7f1d71c95cd` | accepted | Removes an incorrect single-source constraint; its session-documentation hunk will be excluded if the rejected handoff file is absent. |
| 64 | `2f7cd1e1d2a001bb4225fc974d4db8654fe63475` | rejected | Autonomous-agent brief only. |
| 65 | `a8e9d31a9bb5fdde2da4b48fbaf5a95112d02a71` | rejected | Rewrite of the autonomous-agent brief only. |

## Planned integration summary

- Accepted: 36 commits.
- Rejected: 29 commits.
- Required local adaptation after cherry-picking: remove automatic
  Requirement-IR-lane-to-fixed-workflow dispatch and expose
  `research.evidence_to_poc.v1` as a planner-selected memoized TaskGraph
  candidate.
- No push is authorized by this task.
