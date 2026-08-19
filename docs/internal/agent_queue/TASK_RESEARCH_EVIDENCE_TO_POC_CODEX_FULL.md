# Task: Solar-owned fixed Codex research and AutoSci PoC workflow

Status: **APPROVED FOR ISOLATED IMPLEMENTATION**

## Goal

Complete `research.evidence_to_poc.v1` as one deterministic Solar Harness
workflow. Solar owns the graph, exact worker assignment, state, evidence,
approval, evaluation, reconciliation, and final delivery. Codex agents perform
the bounded research reasoning/writing stages. AutoSci performs bounded
scientific and PoC operations. No nested scheduler or detached research
pipeline is permitted.

## Fixed topology

Part A:

1. `seed_fetch`
2. `source_discovery`
3. `source_validation`
4. `evidence_synthesis` — fresh Codex research agent
5. `report_draft` — fresh Codex writer agent
6. `independent_review` — separate fresh Codex reviewer agent
7. `report_revision` — fresh Codex revision agent
8. `final_acceptance` — deterministic Solar/AutoSci gate

Part-A-to-B boundary and Part B:

9. `poc_handoff` — deterministic accepted-evidence manifest
10. `idea_evaluation` — evidence-bound AutoSci/Codex idea selection
11. `experiment_design` — bounded benchmark plan
12. `experiment_approval` — exact plan-hash human approval gate
13. `experiment_run` — no-network sandboxed execution
14. `claim_verification` — reconcile raw benchmark results to evidence
15. `final_delivery` — package report, PoC, benchmark, verification, and limits

## Invariants

- Ordinary research selects this registered fixed workflow before Epic/Planner.
- The Planner cannot create or replace the topology.
- Every executable node has one exact `required_operator_id`; generic/fuzzy
  worker fallback is forbidden for this workflow.
- Execution is single-threaded for the initial UAT.
- A4-A7 use Codex CLI agents with fresh ephemeral contexts and schema-bound
  final responses; they do not call OpenAI/OpenRouter APIs directly.
- A1-A3 and deterministic acceptance/handoff nodes remain bounded AutoSci or
  Solar command operators.
- Part B consumes only evaluator-accepted Part-A artifacts and a manifest with
  artifact IDs, schemas, paths, SHA-256 hashes, byte counts, limitations, and
  evaluator receipts.
- Experiment execution cannot start until a human approval artifact matches
  the exact experiment-plan SHA-256 and approved scope.
- The experiment runs in a bounded no-network sandbox and retains command,
  stdout, stderr, exit code, timing, metrics, hashes, and raw results.
- A final deliverable is accepted only when Part A and Part B evidence agree.
- Legacy `research.autosci.v1`, its 24-node boundary, and the shared scheduler
  semantics remain unchanged.

## Required proof

- Contract/schema compilation and deterministic repeated topology.
- Exact worker matching for every node; wrong worker IDs queue/fail closed.
- Real non-dry Solar dispatch through operator runtime and operatord.
- Codex output-schema enforcement and separate ephemeral writer/reviewer calls.
- Source, dependency, and output tamper rejection.
- Approval negative: no approval, wrong plan hash, wrong scope, stale approval.
- Real bounded sandbox execution with retained raw evidence; no fixture result.
- Local one-run UAT from shipped intake through final delivery, including a
  truthful approval pause/resume.
- Docker/dashboard UAT only after the local run passes without manual artifact
  injection.

## Out of scope

- Generic workflow repairs.
- Planner-generated topology.
- Parallel execution for the first UAT.
- Silent/self approval.
- Production cryptographic grant infrastructure.
- Commit, push, PR, or apply-back without separate approval.

## Implementation checkpoint — 2026-08-17

- Direct OpenAI/OpenRouter API authorization code is not part of this route.
  A4-A7 have exact Codex worker IDs; A1-A3, A8, and B1-B7 use exact command
  workers. Ambient API keys are scrubbed from the Codex subscription boundary.
- The authenticated Part-A lock completed A1-A8 with accepted final evidence;
  retained evidence is under `artifacts/parta-lock-20260817-authenticated-rerun/`.
- Part B now has visible B1-B7 topology, controller-bound Part-A handoff,
  deterministic idea/plan, exact human approval request and resume, a fixed
  `unshare -Urn` no-network benchmark, raw-evidence claim reconciliation, and
  JSON/Markdown final delivery.
- A live full-profile attempt reached A7 but A8 rejected a revision that did
  not render every recorded limitation. A7 now requires a schema-bound
  preservation declaration and both the operator and outer adapter recompute
  preservation of accepted conclusions, method text, and all accumulated
  provider/reviewer limitations. A second attempt stopped before generating a
  revision because Codex rejected the response-schema `uniqueItems` keyword;
  that unsupported keyword is removed while deterministic preservation remains
  enforced by the operator.
- Every started Codex call now retains and reports a hash-bound request,
  response schema, final/failed response, event stream, and exchange record.
  Writer and reviewer calls share an ordered stage journal, so an A7 repair
  failure cannot hide the initial or failed call from the outer side-effect
  inventory. A deterministic completed-then-failed two-call boundary test
  accounts for all ten files and both usage rows.
- Obsolete direct-API tests were deleted. Current deterministic evidence:
  focused fixed/contract/model-service suite `67 passed`; canonical plus
  installed-mirror workflow-contract suites `286 passed`; no skips.
- Static Python compilation, workflow/operator/schema JSON parsing, shell
  syntax, and `git diff --check` pass.
- Remaining acceptance evidence: a corrected authenticated A1-A8+B1-B3 run,
  an attributable exact-plan human approval, then real non-dry B4-B7 and final
  delivery. No self-approval is permitted.

## B4 proof correction checkpoint — 2026-08-18

- The retained approved continuation executed the exact B4 worker and produced
  a valid user-bound `experiment_approval` plus deterministic evaluator PASS,
  but closeout failed because the generic verification capsule injected a
  `resource.github-readonly` proof. Its generated resource sidecar correctly
  reported no repository workspace, so the generic proof rejected the node.
- B4 now selects `cap.research-experiment-approval`. This capsule validates the
  controller approval artifacts, requires the secret-leak guard and the exact
  approval JSON output, and deliberately declares no repository/GitHub
  resource capsule. Generic verification nodes retain their existing resource
  obligation and still fail closed when no workspace is bound.
- The retained `WORKFLOW_CONTRACT_UNREGISTERED:research.evidence_to_poc.v1`
  event was created while the continuation command pointed `HARNESS_DIR` at an
  isolated operator harness before its shipped `config/` catalog was present.
  The repository controller CLI resolves the contract from the shipped
  registry; a regression now executes the real `approve-fixed-experiment` CLI
  with the shipped harness and asserts the attributed resume succeeds.
- The terminal failed UAT remains unchanged. B5-B7 were not executed, and a
  fresh run is required after deterministic review; the generation-1 approval
  from the failed run is not reusable authority for another generation.

## B5-B7 least-privilege and deterministic closeout checkpoint — 2026-08-18

- The later retained run under
  `artifacts/partb-uat-pause-20260818-capsulefix/` reached B5. The real
  allowlisted `unshare -Urn` benchmark completed with network disabled, exit
  code 0, 8/8 integrity checks, and integrity rate 1.0. Its raw result,
  stdout, stderr, timing, metrics, and SHA-256 evidence were retained. The run
  became terminal only because B5 still inherited a generic repository
  resource-binding proof; B6-B7 were therefore not executed in that retained
  UAT.
- B5, B6, and B7 now use three dedicated fixed-workflow capsules. They require
  the exact approved-plan/benchmark/verification/delivery evidence for their
  stage and declare no repository or GitHub resource capsule. Generic build
  and repository nodes retain their existing resource-binding requirements.
- Contract instantiation now preserves each output's `evidence_schema`. This
  is load-bearing for B6: without it the dispatcher omitted B5's secondary
  `benchmark_raw`, stdout, and stderr evidence even though the files existed.
- A real isolated non-dry B4-B7 regression now crosses the normal Solar
  dispatcher, operator runtime, operatord, deterministic evaluator, ledger,
  manifest, and reconcile boundaries. It uses the actual no-network benchmark
  and executes B1-B7 from a separately labelled controller-accepted seeded
  Part-A precondition; it does not claim that A1-A8 executed in this test.
  Separate negative controls reject noncompleted and hash-tampered experiment evidence. The retained
  deterministic run is under `artifacts/partb-deterministic-b4-b7-final/`.
- No lawful public product command was found that creates an audited new B5
  attempt/generation from the retained terminal failure while preserving the
  exact approval authority and reopening B6-B7. The retained run was therefore
  not mutated or resumed. Its successful benchmark bytes are diagnostic
  evidence, not a completed end-to-end UAT.
- Current deterministic evidence: fixed workflow `36 passed`; focused
  canonical/mirror capsule and proof suites `62 passed`; canonical plus
  installed-mirror workflow-contract suites `292 passed`. Python compilation,
  workflow/operator/schema JSON parsing, capsule YAML parsing, shell syntax,
  and `git diff --check` pass.
- Remaining acceptance evidence is a fresh shipped-intake full-profile UAT
  through B7 with a new exact-plan human approval. No additional live run was
  started in this checkpoint.

## Final evidence-authority review checkpoint — 2026-08-18

- B4 independently rehashes the current `approval_request.json` and requires
  the human approval's `approval_request_sha256` to match those exact bytes.
  A post-approval request mutation is rejected before output or handoff writes.
- B6 consumes exactly four B5 artifacts: experiment summary, raw benchmark,
  stdout, and stderr. The controller verifies each current file against its
  contract schema/path, accepted artifact-manifest file row and directory
  entry, evaluator-snapshot write row and directory entry, current SHA-256,
  consumable evaluator record, gate ledger, and closeout receipt. B6 records
  all four source references and controller digests in its verification JSON.
- B7 deterministically aggregates and deduplicates upstream limitations from
  accepted final acceptance, report revision, PoC handoff, experiment result,
  and claim verification artifacts. Each limitation retains source artifact
  ID, schema, path, and SHA-256. JSON and Markdown render the same ordered list,
  and the adapter recomputes the bundle and limitation lineage before closeout.
- The adversarial matrix covers approval-request mutation, stdout/stderr/current
  result mutation, noncompleted result, manifest-row mismatch,
  evaluator-snapshot mismatch, final limitation omission, and upstream
  limitation tamper. The non-dry test is explicitly named as B1-B7 execution
  with a seeded controller-accepted Part-A precondition. The direct benchmark
  test claims only real no-network B5 execution without controller closeout.
- Deterministic results: fixed workflow `36 passed`; focused canonical/mirror
  capsule and proof suites `62 passed`; canonical plus installed-mirror
  workflow-contract suites `292 passed`. No live or network run was started.
- Final targeted recheck after the authority negatives: `2 passed` (B4 approval
  tamper plus the real non-dry B1-B7 path). Python compilation, shell syntax,
  `git diff --check`, workflow/operator/evidence-schema JSON parsing and
  validation, and capsule-registry/capsule YAML parsing pass for the fixed
  workflow. Strict validation of the entire shared physical-operator registry
  still reports an unrelated legacy baseline entry
  (`mini-glm51-builder-3`) missing `billing_surface`; all 15 fixed-workflow
  operator entries validate against the same schema.

## Final shipped-intake local UAT entry — frozen requirements

- The UAT starts with one user-facing command and invokes the shipped
  `harness/solar-harness.sh intake` entrypoint. It must not create a graph,
  call an adapter, seed Part-A authority, or change node state directly.
- The start phase uses `execution_profile=part_a_plus_poc`, a host-authorized
  persistent source pack, one canonical persistent evidence root, the exact
  registered fixed workflow, and `max_parallel=1`.
- Progress is driven only by shipped graph-dispatch commands and the existing
  operator-runtime/operatord auto-kick. A UAT driver may poll durable graph
  state and invoke those public commands; it must not duplicate scheduling,
  evaluation, reconciliation, or approval logic.
- `start-to-approval` must stop only at the B4 human-review gate and retain the
  exact approval request. `resume-to-final` must reuse that same run and call
  the shipped exact-plan approval command before continuing to final delivery.
- Preflight must verify the Codex executable and local subscription-auth file
  without reading or printing credentials, the shipped registry/contract and
  operator files, source-pack hashes, clean isolated process/runtime state,
  and the exact repository HEAD. The manifest records allowlisted environment
  and command metadata, never secret values.
- Tests are deterministic driver/preflight tests only. They may use minimal
  generated source-pack bytes as contract inputs, but must not claim research
  success. No live provider, network, Docker, fixture-result, commit, push, or
  apply-back is allowed in this preparation increment.

### One-shot demo policy amendment

- The final demo has no B4 pause when, and only when, intake carries the typed
  policy `evidence_lineage_integrity_v1` with an attributable human actor and
  statement. Ordinary `part_a_plus_poc` without that typed policy preserves
  the existing exact-plan human-review pause.
- Workflow intake materializes the preauthorization inside the sprint and
  binds it to the current run, request SHA-256, frozen source-pack manifest,
  exact fixed runner path and current digest, network-none namespace, timeout
  ceiling 60 seconds, and the two closed capabilities. It is not a caller
  supplied approval artifact.
- After B3, the controller and B4 worker independently require the generated
  plan to remain inside the policy, including exact controller-accepted B1
  input set. They derive a plan-SHA-bound approval referencing the immutable
  preauthorization. Any policy, runner, scope, network, timeout, capability,
  run, request, source-pack, or input-set mismatch fails closed.
- The UAT's primary phase is now `start-to-final`; `start-to-approval` and
  `resume-to-final` remain available for the optional interactive secure path.

## One-shot shipped-entry preparation checkpoint — 2026-08-18

- `harness/tools/fixed_research_uat.py` is a thin public-command driver. It
  invokes only `solar-harness.sh intake` and the shipped graph-dispatch
  commands, polls the durable graph, records command stdout/stderr receipts,
  and never implements scheduling, evaluation, reconciliation, or node-state
  mutation itself.
- `start-to-final` supplies the explicit fixed policy through typed intake
  environment. The default path without that policy still pauses at the
  interactive exact-plan gate. The driver rehashes and validates the retained
  policy after intake before allowing controller ticks to continue.
- Policy validation happens before either `approval_request.json` or
  `human_approval.json` is published. Deterministic checks cover runner,
  network, timeout, capability/scope, and exact input-set expansion; changed
  controller-accepted plan bytes also fail at the evaluator-snapshot boundary.
- A shipped one-command intake regression proves the exact policy, actor,
  statement, request hash, runner digest, no-network scope, timeout, and
  capability set are persisted without an Epic/Planner detour. A real non-dry
  B1-B7 test with a separately labelled controller-accepted Part-A precondition
  passes in both interactive and one-shot policy modes.
- Evidence: driver tests `3 passed`; fixed workflow `43 passed`; canonical plus
  installed-mirror workflow-contract suites `299 passed`; focused
  canonical/mirror capsule suites `39 passed`. Python compilation, Bash syntax,
  JSON parsing/schema checks, fixed-operator schema validation (11 entries),
  capsule YAML parsing, and `git diff --check` pass.
- The broader logical/physical registry schema suite remains red on 11 legacy
  baseline defects outside this increment (including pre-existing logical
  operator roles/actors/capabilities and legacy Claude/GLM billing metadata).
  No fixed-workflow operator failed its per-entry schema validation.
- No live or network UAT was started. The next run should use a fresh persistent
  evidence root and the exact command reported at handoff.

## Governed live/hybrid retrieval and Docker/dashboard UAT — frozen phase

### User-visible outcome

- Preserve `source_pack`, and add typed `provider_discovery` and `hybrid`
  acquisition modes. The final demo uses `hybrid`: retained host-approved pack
  evidence plus at least three genuinely live, non-fixture public records.
- Only A2 may use public retrieval network access. Intake must receive the
  explicit typed policy `public_bibliographic_no_key_v1`; Solar materializes a
  controller-owned run/A2/request-bound authorization artifact. No ambient
  credential, model-stage grant, or prompt phrase authorizes retrieval.
- The existing dashboard is the UAT front door. Docker starts the shipped
  status server, and the user submits the research prompt through the real
  dashboard form/`POST /intake`; no CLI intake or pre-created sprint is allowed
  before that browser action.
- That dashboard request must select the fixed 15-node workflow, carry typed
  `hybrid` acquisition and both controller policy identifiers, run at max
  parallel one, and use fixed experiment preauthorization with no visible B4
  pause. CLI and read-only APIs may verify the resulting sprint ID and bytes,
  but may not create or replace the run.

### Existing seams to reuse

- `LiteratureDiscoveryService` already derives a bounded query from the task,
  calls Semantic Scholar, then OpenAlex and Crossref fallbacks, normalizes
  provider/source IDs, and writes a service-evidence archive.
- `source_discovery.execute` is already the A2 physical operator and
  `source_validation.execute` is already the A3 authority/relevance boundary.
- The fixed adapter already normalizes stage-local provider archives, rejects
  unreported side effects, and uses the normal research-node result ABI.
- The fixed graph's controller-owned policy artifact pattern, exact dispatcher
  binding, evaluator/ledger/manifest closeout, and one-shot experiment policy
  remain unchanged in authority model.
- Existing `/orchestration/dashboard`, `/orchestration/projection`,
  `/api/sprints`, `/api/sprints/<sid>/contract`, `/events`, and
  `/research/<sid>` status surfaces are the evidence sources for the UAT; the
  driver must capture them rather than inventing a parallel dashboard.
- The existing React prompt form already calls `submitIntake`, which posts to
  the shipped status server's `POST /intake`. The server already invokes the
  shipped Solar intake command, supplies an attributable request ID, forwards
  explicit workflow inputs, extracts the authoritative sprint ID, and the UI
  navigates to that sprint.
- The existing session view already streams `/api/sprints/<sid>/projection`
  and `/events`, periodically reconciles `/status` and the deliverable list,
  and opens allowlisted workdir artifacts through the status server. This is
  the projection surface to validate, not redesign.

### Gaps that must be closed

- The fixed workflow currently rejects every acquisition mode except
  `source_pack`, the shipped shell hardcodes that mode, and A2 always injects
  pack candidates with no discovery service and network authorization false.
- Hybrid semantics do not exist: the operator currently chooses supplied
  candidates *or* the service. It must merge and label both channels, dedupe
  deterministically, and never label pack-only fallback as live.
- The production service's final archive is aggregated. OpenAlex/Crossref raw
  bodies are discarded; Semantic Scholar has retry progress but not a complete
  common per-attempt request/response archive. Every provider attempt must
  retain provider, sanitized URL, query/id, timestamp, status, raw bytes/hash,
  retry decision, and the final normalized result inside A2's stage authority.
- Retry is not common across all three providers. Enforce a small attempt and
  total-wait budget, bounded Retry-After handling, and deterministic failover.
- A3's fallback relevance rule currently accepts any title/summary with forty
  characters. Replace it with a deterministic request-query token overlap
  score plus explicit proof; provider/source authority remains a separate
  dimension. UAT requires at least three accepted live public records.
- Discovery limitations and channel/provider lineage must be carried through
  A3-A8, B1, and B7. Provider fallback/all-provider failure must remain visible;
  no downstream stage may convert pack-only evidence into a live-success claim.
- The existing Dockerfile is a clean-install smoke image with fake keys and no
  Codex CLI UAT entry. Add a dedicated UAT image/entry that copies exact source,
  installs required runtime dependencies, mounts Codex subscription auth
  read-only into a container-private temporary home, exposes the loopback
  status server, and writes all run/dashboard evidence to a mounted directory.
- Dashboard intake currently submits only free-text `task` plus `request_id`.

## Single-threaded dashboard takeover checkpoint — 2026-08-18

- Governed retrieval now supports `source_pack`, `live_search`, and `hybrid`.
  The controller writes an A2/request/run-bound no-key authorization for
  Semantic Scholar, OpenAlex, and Crossref. Provider attempts retain request,
  raw response, metadata, response hash, retry status, and a bounded wait.
  A2 merges and labels pack/live candidates; A3 requires deterministic query
  overlap for live candidates and exposes whether the three-live-source gate
  was actually met.
- A real no-key public preflight is retained under
  `artifacts/preflight-public-retrieval-20260818/`: Semantic Scholar returned
  429 and OpenAlex returned 12 candidates, with attempt bytes/hashes retained.
  A five-paper RAG source pack frozen from the same public provider family is
  retained under `artifacts/dashboard-uat-input-20260818/source-pack` and
  validates 5 sources/5 evidence rows.
- A1-A3 now use exact least-privilege capsules:
  `cap.research-seed-snapshot`,
  `cap.research-public-source-discovery`, and
  `cap.research-source-validation`. The fixed contract is v1.3.
- The first real React dashboard submission is retained under
  `artifacts/dashboard-local-uat-20260818` with three screenshots. It exposed
  a real mixed-version launcher defect: status-server preferred an installed
  `solar` wrapper over its own `HARNESS_DIR/solar-harness.sh`, so correctly
  classified research became an Epic. Status-server now prefers its own
  harness; a stale-installed-wrapper regression passes.
- A subsequent real invocation of the dashboard intake function through the
  shipped status-server code and shipped shell created
  `sprint-20260818-145954-wf-research-evidence-to-poc-v1-612084df5346`
  under `artifacts/dashboard-intake-function-r4-20260818`. The graph is the
  fixed 15-node v1.3 contract, hybrid Part A + PoC, with exact workers and
  capsules; normal dispatch submitted A1. This proves the corrected intake
  seam without claiming an HTTP/browser or final-run success.
- Dashboard deliverables deeper than the legacy three-segment limit are now
  visible only when declared by TaskGraph write scope. This surfaces the fixed
  `final_delivery.md` while excluding an undeclared deep peer.
- Current verification: dashboard deliverables/profile/launcher `9 passed`;
  combined fixed workflow, UAT driver, dashboard, contract, production model,
  and synthesis operator suite `186 passed`; Python compilation and
  `git diff --check` pass.
- Runtime blockers are external and explicit. A fresh localhost dashboard
  start was rejected because the Codex approval service reports exhausted
  usage until 2026-08-19 23:46, and policy forbids bypassing that rejection.
  `docker` is not installed/connected in this WSL distro. Therefore corrected
  HTTP screenshot, uninterrupted live A2/A4-A7, Docker build/UAT, commit, and
  apply-back remain unverified and must not be claimed.
  It can parse a visible `/workflow ...` directive, but the normal form exposes
  no typed fixed-demo profile and the server truncates workflow input values to
  200 characters. For the demo, the server needs a narrow controller-owned
  dashboard profile that injects the exact fixed workflow ID, persistent pack
  root, `hybrid` mode, public-retrieval policy, and fixed experiment policy;
  none of those may be inferred from prompt prose.
- The shipped intake currently hardcodes `acquisition_mode=source_pack` for
  ordinary research. Dashboard environment alone therefore cannot request
  hybrid until the shell forwards the typed mode and retrieval policy.
- Fixed intake dispatches the first ready node once. The React UI polls and
  streams state but does not schedule/reconcile later nodes. The UAT driver
  currently initiates intake itself; it must instead start the status server,
  wait for the dashboard-created request/sprint, and invoke only existing
  public graph-dispatch/operatord commands for that same authoritative sprint.
- The deliverable rail scans the canonical workdir and can expose JSON,
  Markdown, logs, and reports, but its shallow depth/80-file cap and generic
  result selection have not yet been proven to surface the fixed final report,
  benchmark evidence, and final-delivery JSON/Markdown. This needs a
  projection/link regression before the Docker UAT; UI redesign is out of
  scope unless an exact existing-view defect is reproduced.

### Planned bounded implementation

1. Add controller-owned public-retrieval policy creation/validation in
   `fixed_research_workflow.py`, typed forwarding in `workflow_intake.py` and
   `solar-harness.sh`, and A2-only read scope/operator payload binding.
2. Add the exact A2 dispatcher envelope control and adapter service
   construction in `graph_node_dispatcher.py` and
   `fixed_research_node_adapter.py`; construct only
   `LiteratureDiscoveryService(stage_dir)`, never ambient model services.
3. Extend `LiteratureDiscoveryService` with common bounded attempt archives and
   deterministic S2→OpenAlex→Crossref failover; extend source discovery and
   validation operators for hybrid merge, truthful channel summaries, query
   relevance, minimum live-source policy, and limitation propagation.
4. Extend downstream deterministic lineage/limitation checks only where
   current artifacts drop those fields; do not alter shared scheduler logic.
5. Add a narrow dashboard-UAT intake profile at the existing `POST /intake`
   boundary. It forwards controller-configured typed fields into the shipped
   intake command, rejects caller attempts to widen paths/policies, and records
   the resolved non-secret profile in the intake receipt. Preserve ordinary UI
   intake and explicit `/workflow` behavior unchanged.
6. Extend `fixed_research_uat.py` with a dashboard-driven phase: start the
   shipped status server/controller environment, wait for the request ID and
   fixed sprint created by the browser, then drive only public dispatcher and
   operatord commands for that same sprint. It must not call intake. Capture
   projection/events/deliverables and prove they reference the same sprint and
   authoritative bytes.
7. Add fixed-workflow status/deliverable regressions showing all 15 nodes and
   live updates plus openable source/evidence/report/benchmark/final artifacts
   through existing APIs. Preserve React code unless this test reproduces an
   integration defect.
8. Add a dedicated Docker UAT file/entrypoint and deterministic tests. Build
   and live-run only after all offline authorization, failover, relevance,
   archive, hybrid-truth, dashboard, and negative controls are green.

### Stop conditions

- Stop rather than add a broad scheduler/network-security subsystem. This phase
  is viable only through the existing fixed A2 operator, controller artifact,
  research service, status server, and public command surfaces.
- Stop on inability to install or run the real Codex CLI in the clean image,
  inability to mount auth read-only without copying credentials into retained
  evidence, unavailable Docker network namespace support, or all three public
  providers failing within the bounded UAT budget. Record a truthful
  environment/provider failure; never substitute fixtures or pack-only success.

## Single-threaded projection/freeze checkpoint — 2026-08-18 15:18Z

- The dashboard serializer recognizes a compiler-owned fixed binding only when
  the required operator equals the selected operator, is present in physical
  execution candidates, and has an exact capsule. It no longer reports false
  missing capabilities solely because no legacy autopilot record exists.
- Dashboard node status overlays `<sid>.task_dag.state.json` on the stable
  graph. The retained sprint projects `seed_fetch` as `dispatched/active`,
  matching the scheduler ledger.
- Projection regressions: 3 passed. Final focused fixed workflow, UAT driver,
  dashboard, contract/router, synthesis operator, and model service run:
  179 passed, 105 warnings. Python, JSON, Bash, and diff checks pass.
- Reproducibility manifest:
  `artifacts/source-freeze-preflight-r7-20260818/uat/entry-manifest.json`.
  It covers 35 load-bearing files with digest
  `bbb02687099c02cdf8930624e7fd6adc2c078b3b0c74086171791a7951966984`,
  exact request digest `884547b7be72122b0133fdf957a6cd91d94db7c8b3114c565a9ab3e6d2c40231`,
  five verified source/evidence rows, and Codex executable digest
  `134063e133f0b4244fa3b251acf973d4fe4b4aeeacbdc135211bf480f59f1477`.
  Credential contents are not recorded.
- Docker remains unavailable because Docker Desktop WSL integration is not
  active. Fresh HTTP/dashboard execution remains blocked by the external
  approval/usage gate until 2026-08-19. No commit, apply-back, push, or Docker
  success is claimed.
