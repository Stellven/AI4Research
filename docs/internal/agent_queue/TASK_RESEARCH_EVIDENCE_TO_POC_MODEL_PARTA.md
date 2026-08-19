# Task: Controller-authorized model stages for the fixed research workflow

Status: **IN PROGRESS — SINGLE-THREADED LOCAL UAT BOUNDARY**

## User-approved scope correction (2026-08-17)

The security audit below remains the production hardening requirement, but it
is no longer the stop condition for this bounded local UAT increment. The user
explicitly directed the work to proceed single-threaded. Under that narrower
scope, Solar may trust one controller-owned authorization file beneath a
policy-owned filesystem root, execute at most one model call at a time, disable
provider fallback, and bind exact request/source/provider/model/secret-ref
metadata into the fixed workflow.

This does **not** provide a cryptographically signed, revocable, crash-safe or
concurrency-safe production grant. It must not be described that way. The
purpose of the increment is only to prove the fixed A4-A8 execution boundary in
an isolated local UAT before Docker. Production admission still requires the
signed grant and atomic reservation design recorded below.

Current bounded implementation state:

- the fixed graph accepts one controller-rooted authorization snapshot bound
  to the exact request and frozen source inventory;
- writer and reviewer routes must use different allowlisted providers and
  fallback is disabled;
- the graph and adapter enforce one-at-a-time execution and use only the exact
  named secret references;
- A4-A8 command workers are registered, but a graph binds them only when the
  authorization is valid and both exact credentials are present;
- without those credentials, A4 remains truthfully unavailable and no model
  stage is queued;
- no live provider or Docker success is claimed by this document.

This document originally froze Increment 2 after a read-only security audit.
That audit remains preserved below. Subsequent implementation is deliberately
limited to the user-approved, single-threaded local UAT boundary described
above; it is not evidence that the model-bearing stages work until the real
non-dry acceptance gate succeeds.

## Production implementation gate result

`NOT_AVAILABLE: controller_authorization_security_primitives_missing`

The existing primitives do not establish the required authority:

- `CapabilityToken.validate_for_lease()` validates expiry only. It does not authenticate an issuer or signature, consult a revocation authority, bind a ledger digest, or reserve a provider budget. Its in-memory implementation also does not enforce all revocation fields present in the JSON schema.
- `gate_ledger.append_record()` writes an unsigned, best-effort JSONL record. It has no authorization-grant kind, integrity chain, exclusive one-time consumption, or atomic call/token/cost reservation.
- `plan_validator.py` explicitly documents that a plan certificate is a content checksum, not a signature.
- The policy-pinned research trust-registry implementation visible on the separate trust-anchor PR branch is not in this base. More importantly, it validates policy-approved registry hashes and the presence of `signature_sha256` metadata; it does not verify a grant signature, provide per-run revocation, or reserve budget.
- No existing provider quota primitive implements the advertised SQLite/CAS reservation for this path. Current quota handling is health/backoff classification, not an authorization-budget lease.

Adding trusted key distribution/signature verification, a revocation authority,
and an atomic budget-consumption ledger would be a new security subsystem. That
remains required for a production claim. For the bounded local UAT only, A4-A8
may be registered when an exact controller-owned authorization snapshot and
both exact provider secrets are present; without them, the existing truthful
`not_available` behavior remains unchanged.

## Objective

Extend the accepted `research.evidence_to_poc.v1` fixed workflow so Part-A stages A4–A8 can execute through real, controller-authorized model providers while preserving the Increment 1 architecture:

- Solar owns the visible TaskGraph, state, authorization, evidence, evaluator gates, reconciliation, and dashboard lifecycle.
- AutoSci research-synthesis operators remain bounded physical work.
- Planner must not generate or replace this topology.
- A2–A8 must be exercised through the real non-dry dispatcher → operator runtime → operatord → adapter → evaluator/reconcile path before live success is claimed.
- Ambient credentials must never authorize a provider call.

## Accepted Increment 1 baseline

The following behavior is the baseline and must remain unchanged when no valid model authorization is supplied:

- The registered fixed workflow retains the visible A1–A8 Part-A topology and visible, non-executable Part-B topology.
- A1–A3 are the only registered/dispatchable physical operators.
- A4 (`evidence_synthesis`) is terminally `not_available` with reason `model_provider_authorization_not_available`.
- A5–A8 cannot dispatch after that truthful boundary.
- A1 has a real credential-free non-dry operator-runtime/evaluator/reconcile proof.
- `research.autosci.v1` and the existing 24-node workflow remain unchanged.

Increment 2 must specialize only newly instantiated runs that carry a valid controller-issued authorization. It must not mutate or “resume” old terminal Increment 1 runs.

## Read-only findings

### A4–A8 operator readiness

- `evidence_synthesis` (A4) and `report_draft` (A5) require `model_generate`.
- `independent_review` (A6) requires `review_model_generate`.
- `report_revision` (A7) can require both services during its bounded revision/re-review loop.
- `final_acceptance` (A8) is deterministic and recomputes hash-bound lineage across A3–A7; it must not receive network or secret authority.
- The operators already emit structured research artifacts and provider-usage evidence, but current same-model logic records a limitation rather than enforcing reviewer independence.

### Existing API-key service

`ResearchModelService` already provides the smallest reusable real implementation:

- OpenAI-compatible structured JSON requests;
- bounded retry/response behavior;
- request and response SHA-256 evidence;
- archived provider request/response traces.

However, `ResearchModelService.from_environment()` is not an authorization boundary. It reads ambient `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, provider/model settings, and an optional OpenAI fallback flag. `production_services_from_environment()` also supplies the same model service instance as both writer and reviewer. Increment 2 must therefore not call either environment factory on the fixed workflow model path.

### Existing Codex-session operator

`harness/tools/codex_operator.py` is not a suitable model service for this increment. It is a PM/code command runner that:

- invokes `codex exec` with a copied login session;
- consumes and emits PM-oriented Markdown rather than the research-synthesis JSON service contract;
- does not provide the required provider/model usage archive and source-ID contract;
- has no enforced writer/reviewer separation;
- is currently covered only by environment/command contract tests, not a live structured research proof.

A present `auth.json` or logged-in Codex session is not provider authorization. A Codex-session research adapter is deferred to a separate explicitly designed increment.

## Chosen path

Use exact controller-authorized API-key routes with no environment-driven fallback:

- one writer route for A4, A5, and the writer half of A7;
- one reviewer route for A6 and the reviewer half of A7;
- the writer and reviewer providers must differ;
- A8 remains deterministic and receives no provider service or secret.

Initial supported pairings are bounded to the providers already implemented by `ResearchModelService`:

- OpenRouter writer + OpenAI reviewer; or
- OpenAI writer + OpenRouter reviewer.

Different models on the same provider do not satisfy the independent-review claim. If both exact routes and secrets are not available, the run must report a truthful non-executable outcome; it must not downgrade to same-provider review or silently use another ambient key.

## Controller authorization grant

Add a schema such as `research_model_authorization_grant.v1` only after the missing trust prerequisite exists. A grant is issued by a trusted controller principal and verified against a policy-pinned issuer key or an existing equivalent trust anchor. A JSON object supplied by the caller, prompt, workflow input, or environment is never a grant. The grant contains authority and route metadata only—never secret values.

Required fields/invariants:

- exact schema/version, grant ID, issuer principal ID, issuer key ID, signature algorithm, and signature;
- signature verification over canonical grant bytes using a policy-pinned, non-caller-selected trust root;
- exact controller authorization-ledger path/digest and grant issuance record ID;
- revocation status checked at intake, reservation, provider construction, and result acceptance;
- exact `workflow_contract_id = research.evidence_to_poc.v1`;
- exact sprint/run ID, node ID, evaluation generation, captured request digest, accepted A3 artifact digest, and frozen source-pack manifest digest;
- finite issuance and expiry times; expired or revoked grants fail closed;
- separate grants for each authorized node execution; no grant is reusable across nodes, runs, or generations;
- allowed node ID exactly one of A4–A7;
- approved capability `research_model_generate`;
- `allow_network = true` and `allow_live_provider = true`;
- exact principal/role (`writer` or `reviewer`), provider, model, transport, policy-owned endpoint ID, and secret reference;
- explicit maximum request count, input/output token budget, monetary budget where measurable, timeout, and retry budget;
- `fallback_allowed = false`;
- provider values restricted to the supported allowlist;
- transport and endpoint are policy-owned constants derived from the allowlisted provider, not caller-selected URLs;
- secret references are names only and secret values are forbidden anywhere in the artifact.

A6 requires its own grant from a separate authorized reviewer principal. Its provider must differ from the actual A5 writer provider. A7 requires separately reserved writer and reviewer grants. Independence must be checked against trusted grant principals and actual provider usage, not inferred from stage labels or model names.

The controller must validate the artifact from a policy-owned authorization root. A workflow input, prompt, `--workspace-root`, or source-pack directory must not be able to select or widen that root.

Before graph publication, the controller must atomically snapshot the validated grants under the new sprint workdir, verify copied digests, and bind the in-sprint paths/digests to graph metadata and A4–A8 read scopes. The physical adapter must rehash the frozen grant immediately before reservation and service construction. External mutation after intake must have no effect; mutation of the frozen snapshot must fail before any provider call.

## Atomic one-time budget reservation

Grant validation alone is insufficient. Before constructing a provider service or resolving a secret value, the controller/dispatcher must atomically reserve the exact grant's remaining request/token/cost budget:

- one successful reservation per grant ID + run + node + generation;
- compare-and-swap or equivalent transactional exclusivity across concurrent dispatchers;
- reservation binds grant digest, authorization-ledger digest, run/node/generation, provider/model/transport/endpoint/secret ref, and the exact budgets;
- replay, concurrent double-spend, expired/revoked grant, changed ledger digest, or insufficient budget fails before provider construction;
- reservation and final consumption/refund records are durable and independently auditable;
- retry attempts consume only the explicitly reserved retry budget;
- a crash cannot make the same grant silently reusable.

The present gate ledger cannot provide these guarantees. This is the primary implementation stop.

## Secret handling

- The authorization artifact names exact secret refs; it never contains their values.
- The controller resolves values from its secret store/environment only after validating the frozen authorization artifact.
- A secret is exposed in memory only to the exact approved provider route.
- Secret values must not be serialized into the TaskGraph, queue item, operator envelope, research request/result, logs, archives, or evaluator evidence.
- Extra ambient credentials are ignored.
- A missing approved secret produces a classified, durable unavailable/blocked outcome before dispatch or provider construction.
- Redaction checks remain mandatory on all adapter and operator outputs.

## Exact execution chain

For a newly authorized run:

1. Shipped research intake captures/persists Requirement IR and selects the existing fixed workflow without Planner topology generation.
2. The controller validates and snapshots both the source pack and model authorization before publishing an executable graph.
3. The specialized graph binds A4–A8 dependencies, signed grant snapshots, source/request lineage, exact provider roles, and exact physical operator IDs.
4. Dispatcher reloads the authoritative graph, verifies intent binding, source-pack binding, authorization binding, dependency closeout receipts, and exact node readiness.
5. The dispatcher verifies revocation and atomically reserves the signed grant budget before secret resolution or provider construction.
6. The fixed envelope carries only controller-owned grant/reservation metadata, hash-bound artifact refs, and exact secret-ref names.
7. The adapter revalidates all hashes, ledger/grant/reservation bindings and constructs explicit writer and reviewer `ResearchModelService` instances from approved routes. It must not call `from_environment()` or enable provider fallback.
8. Provider request/response archives remain inside the node stage directory, are inventoried, hashed, normalized relative to the sprint workdir, and included in result/evaluator evidence.
9. The adapter verifies actual `model_provider_usage` against the authorized principal/provider/model/transport/endpoint/reservation before emitting its handoff.
10. Normal Solar evaluator/reconcile must durably advance each node. A provider unavailable result must not become a retry loop.
11. A8 loads the real hash-bound A3–A7 artifacts, uses no network/provider service, recomputes lineage and acceptance, and is reconciled by Solar.

## Source and request lineage

Provider authorization is additional authority, not a replacement for evidence lineage:

- A4 must consume the evaluator-accepted A3 artifact and the retained source-pack lineage already bound by Increment 1.
- A5 must consume the accepted A4 synthesis.
- A6 must consume the accepted A5 report and A3 validation and must bind the writer usage it reviews.
- A7 must consume accepted A3–A6 artifacts and record both revision-writer and revision-reviewer usage.
- A8 must consume current accepted A3–A7 artifacts and recompute the complete chain.
- Every inner `research_node_request.v1` must carry exact artifact IDs, schemas, paths, byte counts, and SHA-256 digests for the dependencies it reads.
- Solar evaluator snapshots must include the same dependency and authorization bytes; inner request lineage alone is insufficient.

## Independent-review acceptance

The label “independent review” may be used only when all of these are enforced:

- A5 and A6 use separately signed grants issued to distinct authorized principals;
- authorization names distinct writer and reviewer providers;
- A5 writer usage matches the authorized writer provider/model;
- A6 reviewer usage matches the authorized reviewer provider/model;
- writer and reviewer request/response archives are present and hash-valid;
- A6 explicitly binds the A5 artifact and writer usage it reviewed;
- A7 uses the writer route for revision and the reviewer route for re-review;
- final acceptance rejects provider-role mismatch, missing usage, archive tamper, or same-provider execution.

Merely adding a limitation for same-provider/model use is not sufficient.

## Expected implementation files

Likely production changes, subject to implementation review:

- prerequisite security design and implementation for trusted issuer keys, signature verification, revocation, an integrity-bound authorization ledger, and atomic grant-budget reservation — currently absent and intentionally not invented in this increment;
- `harness/schemas/evidence/research_model_authorization_grant.v1.schema.json` — exact signed grant contract after that prerequisite exists;
- `harness/lib/research_model_authorization.py` — signature/revocation/ledger validation, trusted-root import, snapshot, reservation, and binding helpers after the prerequisite exists;
- `harness/lib/workflow_intake.py` and `harness/solar-harness.sh` — typed controller-owned authorization ingestion; no prompt parsing.
- `harness/lib/fixed_research_workflow.py` — specialize newly authorized graphs while preserving current no-authorization behavior.
- `harness/config/physical-operators.json` — register A4–A8 only when their execution contracts are real; registry availability must remain truthful.
- `harness/lib/graph_node_dispatcher.py` — exact fixed-contract worker/envelope/guard handling for A4–A8.
- `harness/plugins/autosci/bin/fixed_research_node_adapter.py` — authorization revalidation, exact route construction, secret injection, provider-usage verification, and stage inventory.
- `harness/plugins/autosci/services/production_research.py` — explicit authorized-route constructor/factory with no ambient route selection or fallback; separate writer and reviewer instances.
- `harness/plugins/autosci/operators/research_synthesis/independent_review.py`, `report_revision.py`, and `final_acceptance.py` only if needed to turn provider separation from a limitation into a fail-closed invariant.

Do not add a new workflow ID, nested research runtime, Planner-generated topology, broad scheduler exception, Codex adapter, or Part-B implementation in this increment.

Historical contract mismatches found before the bounded UAT implementation:

- The contract originally allowlisted only `openai`; the current A4–A7 policy explicitly permits the two supported routes, `openai` and `openrouter`.
- The environment factory can select a provider and fallback implicitly. The fixed adapter now uses only `ResearchModelService.from_explicit_route()` and forces one attempt with no fallback.
- The environment factory aliases writer and reviewer. The fixed adapter now constructs separately authorized writer and reviewer services and requires distinct providers.
- Provider archives could escape stage authority. The fixed adapter now roots each explicit service in the exact stage directory and inventories the resulting archive evidence.
- A4–A8 were absent from the registry. They are now registered, but the graph binds A4–A7 only when the controller-rooted UAT authorization snapshot and both exact secret refs validate; A8 remains deterministic and receives no model service.
- The Codex CLI/session route remains explicitly out of scope and is not a fallback.

## Required tests

### Deterministic authorization and safety tests

- No authorization + ambient fake credentials: zero service/provider calls and exact Increment 1 terminal state.
- Caller-selected authorization root/workspace/path cannot widen controller authority.
- Reject missing, empty, directory, oversized, malformed, expired, wrong-workflow, wrong-intent/request, wrong-source-pack, unknown-provider, duplicate-role, same-provider, embedded-secret, symlink, traversal, digest-tampered, and post-snapshot-tampered authorization artifacts.
- Mutating the external authorization original after intake does not change execution; mutating the in-sprint snapshot rejects before service construction.
- Extra ambient credentials cannot change exact authorized routes.
- Missing approved secret does not call a provider and produces a durable classified state without redispatch loops.
- Forged issuer/signature, unknown issuer key, altered canonical bytes, revoked grant, expired grant, stale ledger digest, wrong run/node/generation/request/A3/source digest, and endpoint/transport mismatch all fail before reservation.
- Concurrent dispatch attempts against one grant produce exactly one reservation; replay and crash recovery never double-spend it.
- Exhausted request/token/cost/retry budget fails before provider construction.
- Provider/model/role mismatch in returned usage fails closed.
- Missing, escaped, symlinked, or digest-tampered provider archives fail closed.
- A8 receives no provider service/secret/network authority even when credentials are present.
- Authorization and dependency bytes appear in both the inner request and Solar evaluator snapshot.
- Same normalized request + same authority produces identical topology/bindings after normalizing run paths.
- Software/debug and legacy workflow routes remain unchanged.

Deterministic transport injections may test negative boundaries, but must be labelled as such and cannot support a live-success claim.

### Real non-dry acceptance

Before this increment can claim Part A works, retain evidence from an isolated, newly authorized run that executes A2–A8 through:

`registered fixed worker → operator_runtime.submit → operatord command → fixed adapter → research_node_result.v1 → Solar evaluator/reconcile`

The run must use a real retained source pack, real approved API-key routes with distinct providers, and real provider archives. It must prove:

- actual OpenAI/OpenRouter role separation;
- request, source, dependency, authorization, and provider archive hashes;
- durable PASS/accepted state for each completed node;
- A8 deterministic final decision;
- no Planner topology replacement;
- no mock/fixture data supports the live success claim.

If credentials or provider access are absent, retain the truthful environment-blocked outcome and do not claim completion.

## Stop conditions

Stop and return `NOT_AVAILABLE` or a reviewed blocker if any of the following is required:

- treating ambient credentials, environment provider settings, or a Codex login as authorization;
- accepting a caller-authored/self-attested grant or a signature hash that is not cryptographically verified;
- proceeding without an integrity-bound revocation source and atomic one-time budget reservation;
- serializing secret values into controller/operator/evidence artifacts;
- permitting provider fallback outside the exact authorization;
- using one provider for both writer and reviewer while claiming independence;
- allowing caller-selected provider endpoints or trust roots;
- provider archives cannot remain inside and be hashed by node authority;
- the authorization cannot be bound to the captured request and frozen source evidence;
- unavailable provider work would be retried indefinitely or falsely marked PASS;
- completing the path requires broad scheduler/schema semantics, changing the legacy workflows, nesting another orchestrator, or hiding A4–A8 in one opaque node;
- the only available implementation is the current unstructured Codex command operator;
- a real non-dry A2–A8 run cannot be performed and retained.

## Current verification checkpoint (2026-08-17)

The bounded implementation is ready for a real single-threaded local UAT, but
no live model-success or Docker-success claim has been made.

- Fixed-workflow focused suite: `28 passed`.
- Canonical plus installed-mirror workflow-contract suites: `284 passed`.
- Adjacent intake, dispatcher, operator-runtime, and production model-service
  suites: `67 passed`.
- Changed Python compilation, shell syntax, JSON parsing, legacy-workflow
  preservation checks, and `git diff --check` pass.
- A real non-dry credential-free chain proves A1–A3 through dispatcher,
  operator runtime, operatord, adapter, evaluator, ledger, manifest, and
  reconciliation.
- A shipped one-command intake proves ordinary research selects the fixed
  topology and submits A1 to the real operator inbox without Planner or Epic.
- A4–A8 live execution is still unverified because this environment currently
  has neither `OPENAI_API_KEY` nor `OPENROUTER_API_KEY`.

The next permitted action is a retained, real-provider, single-threaded local
UAT. Docker remains after that preflight, not before it.

## Historical Phase 1 verification boundary

This phase performed no Docker, network, or live-provider calls and made no production changes. It freezes the smallest credible implementation path and records the security prerequisite that prevents safe implementation on the current base. API-key execution, controller authorization import, provider separation, and real A2–A8 acceptance remain unverified. The next authorized work must be a separately reviewed trust-and-reservation prerequisite, not model-stage wiring.
