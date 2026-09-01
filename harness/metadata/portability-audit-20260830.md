# Portability / publication-readiness audit — 2026-08-30

Audited product-source baseline: `b000106a78beed09e95c4ee3806ba7319ffa922f`.
Scope: read-only inspection of all tracked source, offline checks against the
locked runtime, and outgoing Git-object token-pattern scan. This is **not**
a clean-machine install or a universal portability certification.

## Results

| Check | Evidence / result |
| --- | --- |
| Whole tracked tree | 5,302 tracked files; source scanner included 3,113 Python/shell/TS/JS/PowerShell files (including test and archived source) |
| Python syntax | 2,232 files parsed under Python 3.12.3; no syntax errors |
| Locked-runtime shell syntax | 141 tracked non-test/non-vendor/non-metadata harness scripts checked with bash -n in the locked runtime; zero failures |
| Static path scan | 32 personal-path and 28 old-backend-address matches; triage below. No source case collisions, non-UTF8 source or shell CRLF findings in this scan |
| Runtime contract closure | 165 inventoried files, 139 valid JSON Schemas, 24 examples; migration + new handoff regressions 13/13 passed in 5.469 s (Python 3.12.3) |
| Capsule/development dependencies | All 68 registered capsule manifests, four frontend prebuild test entrypoints and the required root AutoSci tools/skills are tracked |
| Runtime frontend checks | Windows Node 22.23.2: TypeScript noEmit passed; nodeActor 19 cases, runPipeline, runUsage and statusColors checks passed. No asset build/replacement and no dev server |
| Runtime Python imports | jsonschema, pydantic, pypdf, yaml and rich present; pytest absent. unittest-based migration checks do not require pytest |
| Runtime shell/model tools | Bash 5.2.21, tmux 3.4, jq 1.7; codex-cli version probe succeeded. No model request or authentication contents read |
| Linux frontend build prerequisites | **NOT READY in default WSL PATH:** node command absent; npm resolves to a Windows installation and fails. Windows-side frontend checks are not a Linux build acceptance result |
| Outgoing history scan | After fetching origin/stellven, 49 commits unique to HEAD versus those remote refs; 545 objects / 184 blobs checked. No private-key/provider-token pattern matches, no oversized skipped blobs |
| Data/service safety | Backend/workers remained stopped; 50 session files retained; no endpoint substitution, task, new runtime, install, live E2E or /api/sprints verification |

The outgoing scan checks common token/private-key patterns only. It is not a proof
that every form of sensitive business data is absent. The two configured GitHub
repositories are public. Publishing must use an explicitly approved remote/ref;
no force-push or unrelated branch integration is permitted.

## Findings requiring a new-machine decision

| Category | Locations / consequence | Disposition |
| --- | --- | --- |
| Actual old endpoint literals | `harness/extensions/chatgpt-knowledge-capture/background.js`; `harness/integrations/solar-config-server.py`; platform_workflow_benchmark and solar-runtime-soak tools | These optional/legacy helpers still probe/open 8765. Do not run them against the locked 8767 runtime or assume they auto-detect a new endpoint. Not fixed by documentation |
| Misleading diagnostic links | external-integrations-health and the Mermaid copy-link in status-server copies | Some generated links still name 8765 although the selected server may differ. Main formal intake is not thereby proved misrouted, but those UI/helper links remain a portability issue |
| Configurable defaults | desktop/shot.js URL default; fixed_research_uat --status-url | Override explicitly if these optional tools are approved. A default is not authority to switch the user's backend |
| Personal paths outside the core pipeline | `skills/obsidian-direct/scripts/obsidian_cli.py` defaults to an old user's vault; historical `outputs/*/*.mjs` workbook scripts have old Mac paths | Do not run as new-host setup dependencies. Configure the vault / repair the relevant script if that feature is requested |
| Non-defects among pattern hits | test fixtures, Docker's declared /home/solar layout, examples/comments, WSL user-path discovery, sandbox-relative paths | Pattern matches are review candidates, not automatic product failures |
| Host tools / optional providers | No Linux Node in current WSL PATH; platform-specific external tools and authentication | Install/verify Linux Node/npm in the same environment, use tracked dependency manifests, reconfigure auth securely. Do not copy Windows node_modules or virtualenvs into Linux |
| Runtime/storage/security | File locks, Landlock, ext4 vs DrvFS, WSL networking/firewall and non-loopback auth | Must run approved new-host preflight and verify actual capabilities. Never silently relocate the runtime or disable isolation/auth to turn checks green |
| Contract implementation gaps | RequirementIR v2 template evaluator; code-defined projection/dispatch envelopes | See NEW-MACHINE-START-HERE.md. Existing JSON files/design examples do not prove each boundary is fully JSON-Schema-enforced |

The main default formal intake, its schemas and recent patches are present in Git.
That fact does **not** make every auxiliary tool portable or resolve the known
Requirement/Discovery semantic defect.

## Reproduce without creating another runtime

Run the auditor from the one approved runtime with its Python interpreter:

~~~sh
python tools/migration_portability_audit.py --repo "<source-checkout>" --runtime-shell-syntax "<approved-runtime>"
python tools/migration_closure_audit.py --repo "<source-checkout>" --git-tree HEAD --validate-schemas
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p 'test_migration*.py' -v
~~~

The portability auditor reports findings; exit 0 means the inventory completed,
not that risks are absent. Inspect its JSON findings and shell failures.
Its shell option invokes only `bash -n`; it does not execute those scripts.
Source parsing reads the checkout; the closure audit with --git-tree reads actual
Git blobs and cannot be satisfied by an untracked local file.

After an authorized fetch, add `--outgoing-secrets` to inspect blobs not reachable
from origin/stellven remote-tracking refs. Findings show file/object locations,
not credential values. Do not publish if a real secret or an unreviewed skipped
blob is found. This audit neither changes branches nor pushes.

## New-host acceptance still required

1. User-approved source/ref and runtime/data/backend identity; clean dependency
   installation, no copied credentials or old task auto-recovery.
2. Runtime Python imports plus regressions; Linux Node/npm and a real frontend
   install/typecheck/build in the chosen environment.
3. Same-runtime backend readiness with fixed port, authentication and session
   inventory verified; no fallback endpoint or embedded replacement backend.
4. User-authorized exact-prompt rapid E2E. Final run is unattended: stop/report
   on the first problem; do not rewrite artifacts, restart or silently retry.

Until those checks run on the new host, record new-host installation/E2E as
NOT_TESTED, not PASS. Do not claim “all code has no environment problems.”
