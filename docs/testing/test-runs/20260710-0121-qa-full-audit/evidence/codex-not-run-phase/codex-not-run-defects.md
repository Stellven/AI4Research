# Codex-relevant NOT_RUN defects

| ID | Severity | Surface | Finding |
|---|---|---|---|
| CNR-001 | P2 | Browser job runtime | `BrowserSessionPool` tests see only `BrowserSessionBroker`, and the real-browser probe does not create the expected daemon artifact directory. |
| CNR-002 | P2 | AutoSci setup / installer closure | Setup evidence declares `plugins/autosci/config/.env.example`, but that artifact is absent; setup routes and installer closure fail. |
| CNR-003 | P3 | CI diagnostics | `install-matrix`, `solar-ci`, and `windows-wsl2-install` provide neither upload-artifact diagnostics nor `GITHUB_STEP_SUMMARY`; six atomic CI contracts fail. |
| CNR-004 | P2 | Release packaging | `release/build.sh --dry-run` exits 1 because `tar ... | head -40` is executed under `set -o pipefail`; the real isolated build succeeds. |
| CNR-005 | P2 | PM intake | Research intake raises `KeyError: capability_capsule_id` instead of emitting a complete capsule/dispatch record. |
| CNR-006 | P2 | AutoSci PDF ingest | Exact PDF ingest contract returns `registration_incomplete` instead of `registration_ready`. |
| CNR-007 | P3 | AutoSci novelty provenance | A supplied `file://` payload reference is not canonicalized to the encoded URI when the checkout path contains spaces. |
| CNR-008 | P3 | Installer hygiene contract | Existing installer regression reports missing `.env.example` and missing `.gitignore` protection for `.env`, key/PEM, and runtime state patterns. |

No production fix was applied in this audit phase.

## Approved-gate and remaining-contract additions

| ID | Severity | Finding |
|---|---|---|
| CNR-009 | P1 | Survey archive writes wiki page/graph/log without explicit approval despite dry_run_only policy evidence. |
| CNR-010 | P2 | Office and browser-automation advertise integrations but ship no executable runtime/provider boundary. |
| CNR-011 | P2 | Social-browser capture sidecars omit unified source URL and screenshot artifact evidence. |
| CNR-012 | P2 | Missing Codex CLI produces an uncaught traceback instead of typed failed/inconclusive evidence. |
| CNR-013 | P2 | Method extraction invents a procedure from Background text and idea output lacks explicit source-gap links. |
