# OpenSolar migration handoff — 2026-08-30

## Status and scope

This change closes a source-distribution gap. It does **not** fix the open
Requirement/Discovery semantic defect or certify a new-machine end-to-end run.

Source branch: `codex/safety-before-intent-rollback-20260828`.
Audited predecessor: `27d724f3e46d3f14d5430c18a2354f40ff2345dd`.
Original recovery base: `df4e2de6acf87fcd962c1fe568a6b6181d3f09e3`.
Use the migration commit containing this document (or the later explicitly
approved successor), not the original base. The outgoing handoff prompt pins
the full migration commit. No push or remote synchronization was performed.

Old-machine identity, historical context only:

- Authoritative runtime: `D:\demo only version\harness`, equivalently
  `/mnt/d/demo only version/harness`.
- Locked backend: `http://172.19.127.84:8767/`.
- At migration: backend, Coordinator and workers stopped; 50 session status
  files remain on disk. There is no live process cwd/environment to inspect.
- Do not restart the old backend or resume old sessions for migration checks.
  Do not reuse the old address as a default on a new host.
- New machine: ask the user to approve ONE runtime root, data root, backend
  address and port before installation/startup. Report actual process cwd,
  HARNESS_DIR, SOLAR_HARNESS_DIR, listening port, URL, Git branch/commit,
  session count and Coordinator/worker state after every authorized restart.

## What is now carried by Git

118 previously runtime-only schema-tree assets were imported at their exact
relative source paths. The inventory covers all 165 schema-tree assets:
139 JSON Schema definitions, 24 synthetic examples, one YAML contract and
one shell validator. Draft definitions are retained, not activated or registered.
One historical code-evidence example was updated with the contract's three
required mapping/relevance fields, explicitly `unknown` and illustrative.

`migration-closure-20260830.json` records portable relative paths and SHA-256
after CRLF-to-LF normalization. It includes existing compiler/planner schemas
as well as the imported schemas. A deliberate schema/fixture change must update
the corresponding digest in the same commit; never regenerate hashes blindly
to mask an unexplained difference.

Recent repairs were already committed: 45 commits from the recovery base to
the audited predecessor, 61 changed paths. The audit found no missing recent
product patch. The graph_scheduler.py runtime/source difference is a comment;
two extra runtime test functions have equivalent committed canonical tests.
This is evidence for this audited repair set, not a blanket guarantee about
every historical feature or external service.

Runtime extras intentionally NOT imported:

| Extra | Disposition |
| --- | --- |
| Unreferenced static bundle index-ByAZV84d.js | Generated stale output; active index uses the tracked index-BpB4h8PF.js. |
| Old React script copies and relocated AutoSci/settings tests | Canonical tests are in tests/harness and tests/plugins/autosci. Preserve the whole source checkout, not just harness. |
| plugins/autosci/services/experiment_executor.py and operators/research_synthesis/plan_admission.py | No current source callers found; dormant historical modules, not activated by this migration. |
| capability-capsules/cap.research-report-draft.yaml | Old duplicate contract not referenced by the current capsule registry; do not register it to satisfy a stale test. |
| Sessions, artifacts, logs, backups, caches, virtualenvs, personal settings and credentials | Operational/local state, deliberately outside the new source commit. |

The core scientific schema consumers load files from
`harness/schemas/evidence`; these contracts must travel with their code.
The AutoSci installer also needs repository-root `tools/` and
`.agents/skills/`. Copying only `harness/` is not a complete source migration.

## Transfer and environment reconstruction

1. Transfer a Git bundle of this branch or another verified Git transport that
   contains the full migration commit. Do not assume the remote default branch
   contains these local commits. Do not copy this machine's dirty worktree,
   its temp files, or a virtualenv. A bundle includes reachable Git history,
   not untracked files, local auth or runtime data. Treat it as private source.
2. Clone the bundle into an empty source directory using
   `git clone -b codex/safety-before-intent-rollback-20260828 <bundle> <source>`.
   Verify `git rev-parse HEAD`, branch and clean tracked status against the
   supplied full commit. If the target repo already exists, stop and agree an
   import strategy instead of resetting or replacing it.
3. Read repository `AGENTS.md`, `README.md`, `docs/WINDOWS.md`,
   `harness/metadata/README.md`, this document and
   `harness/metadata/pre-scheduler-stabilization-log-20260829.md`.
   Windows runtime execution uses WSL2/Linux tooling; native Windows execution
   is not the verified path. This run used Python 3.12.3; recreate the env from
   tracked requirements, do not copy its system-site-packages virtualenv.
4. After user approval, use the tracked installer with an explicit
   `--solar-home` and components `harness,autosci` (kernel is a dependency).
   Review `--dry-run` first and explicitly choose `--claude-dir`,
   `--no-hooks` and `--no-mcp` as appropriate: the installer can modify user
   tool configuration, not only the runtime. Never accept a default runtime
   location without approval. Do not use fake keys as live credentials.
5. Verify dependencies and source assets offline before any backend/task start.
   Configure model/provider credentials securely on the new host; do not print
   them, put them into the prompt, commit them or transfer a credential dump.

Dependency sources, not an exact OS/package lock:

- Python 3.11+ (3.12.3 observed); Bash 4+, Git, tmux, jq. Follow the installer
  and platform documentation for OS packages and model CLI prerequisites.
- Runtime Python packages: `requirements/harness.txt`; broader development
  requirements: `requirements/autosci-solar-native-dev.txt` as appropriate.
  The new migration regressions use unittest plus runtime jsonschema, not pytest.
- React: Node/npm compatible with the checked-in package-lock, then `npm ci`,
  `npm run typecheck`, `npm run build`. Do not run the Vite dev server or
  create another backend. Prebuild scripts reference repository-root tests;
  retain the source checkout. The installed harness alone does not include
  those relocated development test files.
- Git contains the active static UI output. Source rebuild/authorized deployment
  must preserve its relationship to the selected same-runtime status server.
- Provider access, network policy, model availability and exact OS packages must
  be revalidated on the new machine; source completeness cannot guarantee them.

If historical sessions are needed, request a separate private data migration.
They are not required to begin development or create a fresh test task, and
must never be replayed automatically. Likewise, backups are not code dependencies.

## Offline checks

Run from the user-approved runtime root, with that runtime's Python interpreter.
Replace `python` below with that interpreter; do not silently use another env.

~~~sh
python tools/migration_closure_audit.py --validate-schemas
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p test_migration_closure.py -v
bash -n schemas/validate.sh
~~~

To prove the transport includes the assets, use that same runtime audit script
against the source Git tree (no second runtime or backend is created):

~~~sh
python tools/migration_closure_audit.py --repo "<source-repo>" --git-tree HEAD --validate-schemas
~~~

Before commit, `--git-tree :` audits the staged blobs; it never falls back to
untracked files. A pre-migration tree must fail because required assets are absent.

These checks prove the recorded contracts exist, match, resolve their references
offline, validate as schemas and accept their 24 examples via the production
schema helper. They do not establish scientific quality, provider connectivity,
scheduler completeness or final E2E acceptance. The old backend stayed stopped,
so /api/sprints and new-host installation were not re-tested in this change.

## Historical defect and follow-up: do not replace semantics with phrasing heuristics

The diagnosis below describes the pre-repair run. The later user-authorized
semantic-contract repair is documented in [semantic-retrieval-contract.md](semantic-retrieval-contract.md)
and the stabilization log. Do not infer a new unattended E2E PASS from this historical section.

Last unattended run:
`sprint-20260830-194438-intent-conduct-a-systematic-study-o-e7736e72`.
Final state: failed/scheduler_failed, graph revision 13:
discovery passed, ingestion failed, five later nodes cancelled.
Ingestion error: `Discovery evidence contains no candidates`.

The evidence sequence (session artifacts remain on the old machine):

1. IntentIR C3 was a preference: task_treatment equals
   `research-type end-to-end research undertaking`, while deliverable_mode
   **not_equals** `one-off answer`.
2. `lib/requirement_compiler/compiler.py::_expression_values` recursively
   extracted literals, discarding their operators. Compilation made all
   constraints positive coverage requirements; the negative literal
   `one-off answer` became required_values. This compiler is currently
   deterministic; Intent Compiler and Elastic Planner model calls are LLM-based.
3. Raw Planner generation-0 model_output assigned Discovery R2/R3 and Report
   R1/R4/R5. The original LLM ownership was not the offending rewrite.
4. `lib/elastic_planner.py::_preserve_discovery_requirement_scope` matched
   constraint_coverage broadly and appended process requirements into Discovery
   objective text under Authoritative discovery scope / Required coverage.
5. Providers returned 11 candidates, relevance retained 3; topic coverage then
   demanded workflow phrasing and emptied the shortlist. The rapid receipt used
   rapid_smoke_bypass; it is not proof that all hard gates actually executed.
   Ingestion rejected the empty artifact as it should.

Next repair should preserve typed constraint category/polarity across RequirementIR,
separate research subject from process/acceptance instructions, stop deterministic
semantic rewriting after Planner output, and ensure a required nonempty discovery
handoff fails at the producer boundary. Investigate contracts/callers before edits.
Do NOT repair this by adding the latest LLM wording to a stopword list.
The desired architecture is LLM-based semantic compilation, with deterministic
schema validation, references, freezing and scheduling—not scripted reinterpretation.

Also retained known limitations: unregistered cap.research-report-draft legacy
registry tests and evaluate_ideas fixture N/A parsing (issue-log row 37).
Do not relabel those as a new-machine environment failure.

## Retest input and operating rules

After user-authorized repairs, use rapid mode and create a fresh task with the
exact prompt below. For the final unattended run, do not edit code/artifacts,
restart, redispatch or retry after submission. Stop and report the first issue,
with evidence and an explicitly labeled hypothesis. Do not resume old tasks.

~~~text
## Prompt 1:

Please treat this task as a research-type, end-to-end research workflow rather than generating a one-off answer.

Project Name:
KV Cache Efficiency Landscape for Long-Context LLM Inference

Research Objective:
Conduct a systematic study of KV cache compression, quantization, selection, eviction, and sparsification methods for long-context large language model inference, and produce a comprehensive technical landscape report with an explicit evidence chain that is auditable and extensible for future research.
~~~

Every new fix must be portable: no machine/user/project-prompt hardcoding.
Once a runtime is locked, edit and test it first; record SHA-256 and backup before
each existing-file change, mirror only the equivalent minimal source patch,
append the issue/action/verification log and commit only owned source/test files.
Never commit runtime data, logs, backups or credentials.
Do not switch branches, pull, merge, rebase, reset or push without user permission.
Do not use a tmux session-name prefix to stop a cockpit: it previously matched
the similarly named status-server session. Verify and use an exact session ID/name.
