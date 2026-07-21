from __future__ import annotations

import csv
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def append_unique(path: Path, marker: str, content: str) -> None:
    text = path.read_text(encoding="utf-8")
    if marker in text:
        text = text.split(marker, 1)[0].rstrip() + "\n"
    path.write_text(text + "\n" + content.strip() + "\n", encoding="utf-8")


def md(value: str) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


ROOT = Path(sys.argv[1]).resolve()
PHASE = ROOT / "evidence" / "codex-not-run-phase"
AUDIT_TEST = "evidence/codex-not-run-phase/audit-tests/test_remaining_app_browser_provider_contracts.py"
AUDIT_EVIDENCE = "evidence/codex-not-run-phase/gated-approved/remaining-app-browser-provider-contracts.junit.xml"


CASES = {
    "WF-0422-CAPTURED-OUTPUT-HAS-SOURCE-1CDA2F": "test_browser_job_capture_unifies_source_timestamp_and_artifacts",
    "WF-0423-RETRIES-FAILS-CHECKPOINTED-STATE-089989": "test_browser_job_terminal_failure_is_checkpointed_and_idempotent",
    "WF-0425-RUNS-RECORDS-BROWSER-AUTOMATION-FAA4C2": "test_social_cli_reports_unavailable_browser_deterministically",
    "WF-0426-CAPTURED-OUTPUT-HAS-SOURCE-6F503B": "test_social_capture_output_contains_source_timestamp_and_artifacts",
    "MISC-0305-HANDLES-SUPPORTED-SOURCE-REQUEST-0F0924": "test_office_supported_and_unsupported_requests_have_executable_contract",
    "MISC-0307-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-5310ED": "test_office_missing_provider_emits_structured_failure_contract",
    "MISC-0310-HANDLES-SUPPORTED-SOURCE-REQUEST-28972A": "test_obsidian_cli_accepts_supported_input_and_rejects_unsupported",
    "MISC-0312-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-CBB1BC": "test_obsidian_cli_missing_vault_is_explicit_and_nonfabricating",
    "MISC-0315-HANDLES-SUPPORTED-SOURCE-REQUEST-2B0A68": "test_calendar_accepts_supported_request_and_rejects_bad_request",
    "MISC-0317-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-5022AD": "test_calendar_missing_or_unknown_provider_is_typed_failure",
    "MISC-0322-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-E5C821": "test_browser_skill_records_explicit_unavailable_setup_state",
    "MISC-0327-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-AF98BB": "test_obsidian_wiki_unconfigured_state_is_explicit_and_nonfabricating",
    "MISC-0330-HANDLES-SUPPORTED-SOURCE-REQUEST-717B2C": "test_ragflow_supported_and_unsupported_inputs_are_distinguished",
    "MISC-0332-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-83BF1C": "test_ragflow_unavailable_provider_is_typed_and_never_fakes_hits",
    "MISC-0335-HANDLES-SUPPORTED-SOURCE-REQUEST-24C223": "test_codex_operator_accepts_supported_dispatch_and_rejects_empty",
    "MISC-0337-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-2C2F4E": "test_codex_operator_missing_cli_emits_structured_failure",
    "MISC-0347-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-89ACF0": "test_browser_automation_unavailable_is_structured_and_nonfabricating",
    "MISC-0375-HANDLES-SUPPORTED-SOURCE-REQUEST-5089BE": "test_gemini_deep_research_accepts_supported_request_and_rejects_invalid",
}


ENTRY_FIXES = {
    "MISC-0300-HANDLES-SUPPORTED-SOURCE-REQUEST-1A39A8": (
        "NONE — stale taxonomy row; no skills-md directory or executable exists in the locked checkout",
        "NONE — prior skills/solar/SKILL.md association was incorrect",
    ),
    "MISC-0302-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-6ED8E4": (
        "NONE — stale taxonomy row; no skills-md provider boundary exists in the locked checkout",
        "NONE — prior skills/solar/SKILL.md association was incorrect",
    ),
    "MISC-0305-HANDLES-SUPPORTED-SOURCE-REQUEST-0F0924": (
        "skills/office/SKILL.md (documentation-only)",
        "skills/office/SKILL.md; no executable implementation is shipped",
    ),
    "MISC-0307-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-5310ED": (
        "skills/office/SKILL.md (documentation-only)",
        "skills/office/SKILL.md; no executable provider boundary is shipped",
    ),
    "MISC-0310-HANDLES-SUPPORTED-SOURCE-REQUEST-28972A": (
        "skills/obsidian-direct/scripts/obsidian_cli.py; skills/obsidian-direct/SKILL.md",
        "obsidian_cli.py::main; get_vault; create_note; edit_note",
    ),
    "MISC-0312-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-CBB1BC": (
        "skills/obsidian-direct/scripts/obsidian_cli.py",
        "obsidian_cli.py::get_vault; main",
    ),
    "MISC-0315-HANDLES-SUPPORTED-SOURCE-REQUEST-2B0A68": (
        "skills/apple-calendar/scripts/*.sh; skills/email-to-calendar/scripts/utils/calendar_ops.py",
        "calendar_ops.py::main; create_event; search_events; Apple Calendar command scripts",
    ),
    "MISC-0317-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-5022AD": (
        "skills/email-to-calendar/scripts/utils/calendar_ops.py; skills/apple-calendar/scripts/*.sh",
        "calendar_ops.py::_run_gog_command; search_events; create_event; update_event; delete_event",
    ),
    "MISC-0322-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-E5C821": (
        "skills/browser-automation/setup.json; skills/browser-automation/SKILL.md; skills/fast-browser-use/src/error.rs",
        "browser-automation structured setup state; fast-browser-use::BrowserError",
    ),
    "MISC-0327-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-AF98BB": (
        "harness/integrations/obsidian-wiki.sh; harness/test-obsidian-wiki-integration.sh",
        "obsidian-wiki.sh::status; test-obsidian-wiki-integration.sh",
    ),
    "MISC-0330-HANDLES-SUPPORTED-SOURCE-REQUEST-717B2C": (
        "harness/tools/ragflow_adapter.py; harness/lib/ragflow_adapter.py",
        "ragflow_adapter.py::build_parser; cmd_search; ragflow_retrieve",
    ),
    "MISC-0332-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-83BF1C": (
        "harness/tools/ragflow_adapter.py; harness/lib/ragflow_adapter.py",
        "ragflow_adapter.py::ragflow_retrieve; cmd_search",
    ),
    "MISC-0335-HANDLES-SUPPORTED-SOURCE-REQUEST-24C223": (
        "harness/tools/codex_operator.py",
        "codex_operator.py::_read_dispatch; _codex_exec_command; main",
    ),
    "MISC-0337-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-2C2F4E": (
        "harness/tools/codex_operator.py",
        "codex_operator.py::_codex_exec_command; main; subprocess.Popen boundary",
    ),
    "MISC-0347-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-89ACF0": (
        "skills/browser-automation/setup.json; skills/browser-automation/SKILL.md (no executable runtime file)",
        "structured setup state only; no invocation failure implementation",
    ),
}


DEFECT_BY_ID = {
    "WF-0247-ARCHIVAL-WRITEBACK-EXPLICIT-APPROVED-0CA46A": "D-024",
    "MISC-0308-ANY-EXTERNAL-WRITE-BROWSER-F66FD9": "D-024",
    "MISC-0313-ANY-EXTERNAL-WRITE-BROWSER-AEAD47": "D-024",
    "MISC-0318-ANY-EXTERNAL-WRITE-BROWSER-DD521D": "D-024",
    "MISC-0348-ANY-EXTERNAL-WRITE-BROWSER-417B43": "D-024",
    "WF-0041-FAILS-REPORTS-MISSING-STATE-38916C": "D-025",
    "WF-0264-MISSING-INVALID-SCOPE-REJECTED-E14DB0": "D-025",
    "WF-0265-PLAN-GENERATED-WITHOUT-MUTATION-38B119": "D-025",
    "WF-0277-DRY-RUN-PROPOSES-FIXES-6FC1FB": "D-025",
    "WF-0279-FAILS-REPORTS-MISSING-STATE-8DE992": "D-025",
    "WF-0573-SEPARATES-BLOCKERS-RECOMMENDATIONS-EF2559": "D-027",
    "WF-0574-DOES-NOT-MUTATE-UNLESS-438A74": "D-027",
    "WF-0576-SEPARATES-BLOCKERS-RECOMMENDATIONS-694C05": "D-027",
    "WF-0577-DOES-NOT-MUTATE-UNLESS-A2EB53": "D-027",
    "WF-0579-SEPARATES-BLOCKERS-RECOMMENDATIONS-5830E3": "D-027",
    "WF-0580-DOES-NOT-MUTATE-UNLESS-10CFFA": "D-027",
    "WF-0276-REPORTS-DETERMINISTIC-STRUCTURAL-ERRORS-65ACD8": "D-027",
    "MISC-0305-HANDLES-SUPPORTED-SOURCE-REQUEST-0F0924": "D-028",
    "MISC-0307-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-5310ED": "D-028",
    "MISC-0347-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-89ACF0": "D-028",
    "MISC-0337-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-2C2F4E": "D-029",
    "WF-0426-CAPTURED-OUTPUT-HAS-SOURCE-6F503B": "D-030",
    "WF-0176-REPORTS-INCOMPLETE-METHOD-EVIDENCE-E24804": "D-031",
    "WF-0177-GENERATED-CANDIDATES-CITE-SOURCE-FA4851": "D-031",
    "WF-0017-UPDATES-MODEL-CONFIG-ONLY-55333B": "D-032",
    "WF-0018-INVALID-MODEL-REJECTED-ALLOWED-14FEE5": "D-032",
}


def update_csvs() -> None:
    phase_rows = read_csv(PHASE / "codex-not-run-feature-results.csv")
    phase_by_id = {row["feature_id"]: row for row in phase_rows}
    target_ids = set(ENTRY_FIXES) | set(CASES) | {
        "MISC-0300-HANDLES-SUPPORTED-SOURCE-REQUEST-1A39A8",
        "MISC-0302-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-6ED8E4",
    }

    entry_rows = read_csv(ROOT / "feature-entrypoint-map.csv")
    for row in entry_rows:
        if row["feature_id"] in ENTRY_FIXES:
            row["discovered_entrypoints"], row["implementation_files_functions"] = ENTRY_FIXES[row["feature_id"]]
            row["mapping_confidence"] = "high"
            row["mapping_basis"] = "post-gated direct locked-checkout reconciliation; incorrect/stale associations corrected"
    write_csv(ROOT / "feature-entrypoint-map.csv", entry_rows)

    test_rows = read_csv(ROOT / "feature-existing-test-map.csv")
    for row in test_rows:
        fid = row["feature_id"]
        if fid not in target_ids:
            continue
        result = phase_by_id[fid]
        status = result["test_result_status"]
        case = CASES.get(fid, "")
        if case:
            row["existing_test_files"] = AUDIT_TEST
            row["existing_test_cases"] = case
            row["coverage_status"] = "direct"
            row["test_confidence"] = "high"
            row["direct_test_present"] = "yes"
            row["mapping_evidence"] = "Exact audit-only atomic contract executed against locked checkout"
            row["eligible_phase_selected_targets"] = AUDIT_TEST
            row["eligible_phase_selected_testcases"] = case
        else:
            row["coverage_status"] = "not-applicable"
            row["test_confidence"] = "high"
            row["direct_test_present"] = "no"
            row["mapping_evidence"] = "Locked-checkout inventory proves the named skills-md surface does not exist; prior solar mapping removed"
            row["eligible_phase_selected_targets"] = ""
            row["eligible_phase_selected_testcases"] = ""
        row["eligible_phase_execution_result"] = status
        row["eligible_phase_evidence"] = result["execution_evidence"]
        row["gap_to_confirm"] = "Promote the audit-only contract into tracked regression coverage" if case else "Remove or replace stale taxonomy row"
    write_csv(ROOT / "feature-existing-test-map.csv", test_rows)

    missing_rows = read_csv(ROOT / "missing-test-plan.csv")
    for row in missing_rows:
        fid = row["feature_id"]
        if fid not in target_ids:
            continue
        status = phase_by_id[fid]["test_result_status"]
        case = CASES.get(fid, "")
        if case:
            row["missing_test_status"] = "audit-only-direct-test-present"
            row["required_test_type"] = "promote audit atomic contract to tracked regression test"
            row["suggested_test_name"] = case
            row["fixture_needed"] = "isolated HOME/temp app/provider/browser fixture; no live credentials"
            row["command_entrypoint_to_exercise"] = ENTRY_FIXES.get(fid, (row["command_entrypoint_to_exercise"], ""))[0]
            row["expected_result"] = status
            row["recommendation"] = "Retain this audit evidence and promote the exact contract into the repository test suite; do not weaken fixture/live evidence labels."
        else:
            row["missing_test_status"] = "not-applicable-stale-taxonomy"
            row["required_test_type"] = "inventory correction"
            row["suggested_test_name"] = ""
            row["fixture_needed"] = "none"
            row["command_entrypoint_to_exercise"] = "none"
            row["expected_result"] = "SKIPPED_NA"
            row["recommendation"] = "Remove or replace the stale skills-md row after taxonomy owner review; do not map it to the unrelated solar skill."
    write_csv(ROOT / "missing-test-plan.csv", missing_rows)

    criteria_rows = read_csv(ROOT / "pass-fail-criteria.csv")
    for row in criteria_rows:
        fid = row["feature_id"]
        if fid not in target_ids:
            continue
        case = CASES.get(fid, "")
        if case:
            row["happy_path_pass_criteria"] = f"The exact `{case}` contract passes against the locked checkout in isolated fixtures and validates the complete atomic output, state, and artifact assertions; fixture proof is not live parity."
            row["negative_failure_pass_criteria"] = "Unsupported/missing app, provider, CLI, source, or input is explicit and non-fabricating; no write escapes the disposable fixture."
            row["fail_criteria"] = "FAIL when the direct atomic assertion fails, the entrypoint is missing, a traceback replaces structured failure, provenance/artifacts are incomplete, or a side effect is not bounded."
            row["expected_evidence"] = f"{AUDIT_EVIDENCE}; exact testcase {case}; command-log.tsv"
        else:
            row["happy_path_pass_criteria"] = "SKIPPED_NA only when locked-checkout inventory proves the named surface is absent and the prior association is demonstrably unrelated."
            row["negative_failure_pass_criteria"] = "Do not invent a replacement entrypoint or PASS/FAIL result for a nonexistent taxonomy surface."
            row["fail_criteria"] = "FAIL the inventory audit if a real skills-md surface exists or the row is silently mapped to an unrelated skill."
            row["expected_evidence"] = "feature-entrypoint-map.csv; inventory-diff.md"
    write_csv(ROOT / "pass-fail-criteria.csv", criteria_rows)

    main_rows = read_csv(ROOT / "feature-results.csv")
    for row in main_rows:
        defect = DEFECT_BY_ID.get(row["feature_id"])
        if defect:
            current = [item for item in row.get("defect_ids", "").split(";") if item]
            if defect not in current:
                current.append(defect)
            row["defect_ids"] = ";".join(current)
    write_csv(ROOT / "feature-results.csv", main_rows)


def update_markdown() -> None:
    defects = """
## Post-NOT_RUN and approved-gate remediation additions

The exact feature-level failures are recorded in `feature-results.csv` and `evidence/codex-not-run-phase/remediation-feature-decisions.csv`. The following group common root causes; they do not count every failed feature as a separate defect.

| ID | Severity | Surface | Finding |
|---|---|---|---|
| D-024 | P1 | Survey, office, Obsidian, Calendar, browser write gates | The survey route writes wiki/archive state without approval, and four integration skills/policies expose write-ready behavior without an explicit human approval input. Only disposable fixtures were touched. |
| D-025 | P2 | Reset/check dry-run and missing-state routes | Missing scope defaults to mutation-capable behavior, dry-run is labeled completed, requested fixes are omitted, or inconclusive runs still report passed actions/create artifacts. |
| D-026 | P2 | Provider provenance and failure contracts | Several fetch/provider outputs omit query/parameter, retrieval time, limitations, or typed provider-failure evidence; arXiv collapses failure into an empty successful list. |
| D-027 | P2 | Health/audit/circuit routes | Read-only health routes can migrate/write state and their JSON omits required blocker/recommendation or severity separation. |
| D-028 | P2 | Office and browser-automation skills | The advertised office and browser packages are documentation/setup metadata only and ship no executable request/provider boundary. |
| D-029 | P2 | Codex operator | A missing `codex` executable raises an uncaught `FileNotFoundError` traceback and emits no typed failure artifact. |
| D-030 | P2 | Social browser capture | The stored social capture does not bind source URL and screenshot evidence into the timestamped raw/queue output contract. |
| D-031 | P2 | Method extraction and idea generation | Background text is invented into a method procedure instead of marked incomplete, and generated ideas omit explicit source-gap links. |
| D-032 | P2 | Model configuration CLI | `models set-main` mutates without `--apply`, and invalid aliases omit the allowed-option remedy. |
| D-033 | P2 | Capability/intent proof routes | Capability config, activation, certification, and intent route contracts have drifted; some missing rules return `ok: true` or declared capabilities are silently union-enriched. |
| D-034 | P2 | Miscellaneous direct contracts | Component listing is silent, wrappers cache the wrong HOME, an enhanced-search symbol is absent, and a spaced path breaks the local knowledge pipeline. |
| D-035 | P3 | QA taxonomy/integration mapping | Two `skills-md` rows describe no shipped surface, and the Obsidian manifest contains a developer-specific default path. |
| D-036 | P3 | CI diagnostics | Install/CI workflows omit required uploaded diagnostics and/or `GITHUB_STEP_SUMMARY` evidence for several atomic contracts. |
| D-037 | P2 | Release dry-run | `release/build.sh --dry-run` fails under `pipefail` because the tar listing is piped through `head`; the isolated real local build succeeds. |
| D-038 | P3 | Installer hygiene | Installer regression evidence reports missing `.env.example` plus incomplete ignore protection for env/key/runtime state patterns. |

No production fix was applied. No P0 event or real unauthorized external mutation was observed during the audit.
"""
    append_unique(ROOT / "defects.md", "## Post-NOT_RUN and approved-gate remediation additions", defects)

    inventory = """
## Post-NOT_RUN inventory reconciliation

- Originally selected Codex-relevant NOT_RUN rows: 861.
- Final selected-subset outcomes: PASS 639, FAIL 72, SKIPPED_ENV 105, SKIPPED_NA 45.
- Remaining selected-subset NOT_RUN: 0.
- Remaining selected-subset INCONCLUSIVE_EXPECTED: 0.
- Explicitly excluded and archived: 576 rows — Claude 125, SciDAG 429, SciDAG+SciMem 10, SciMem 12.
- `skills-md` was confirmed absent; two rows were corrected from an erroneous `skills/solar/SKILL.md` association to `SKIPPED_NA`.
- Office and browser-automation are documentation/setup-only surfaces, not executable integrations; they are recorded as product/testability failures rather than silently skipped.
- Obsidian, Calendar, RAGFlow, Codex operator, browser job runtime, social-browser CLI, and Gemini Deep Research entrypoints were corrected to concrete locked-checkout files/functions and exercised with isolated fixtures.

Evidence: `evidence/codex-not-run-phase/remaining-blocker-summary.json`, `excluded-feature-ledger.csv`, `remediation-feature-decisions.csv`, and `gated-approved/remaining-app-browser-provider-contracts.junit.xml`.
"""
    append_unique(ROOT / "inventory-diff.md", "## Post-NOT_RUN inventory reconciliation", inventory)

    gated = """
## Approved isolated gated follow-up

The user explicitly authorized bounded gated tests in this session. The authorization was applied only to disposable HOME, sprint, wiki/vault, raw-source, SQLite, fake provider, and fake CLI/browser fixtures. It did not authorize real email, Calendar.app mutation, browser profiles, provider calls, credentials, GitHub/release mutation, or remote execution.

- AutoSci approved gate selection: 8 passed.
- Control-plane approved plan verdict: 13 assertions passed.
- Obsidian integration safety: 3 passed.
- Approved atomic gate contracts: 2 passed, 1 failed (survey archive mutated without approval).
- Miscellaneous side-effect gate contracts: 1 passed, 4 failed.
- Semantic/manual-oracle contracts: 11 passed, 2 failed.
- Remaining app/browser/provider contracts: 13 passed, 5 failed; two nonexistent `skills-md` rows were `SKIPPED_NA`.
- The 861-row selected follow-up now has zero NOT_RUN and zero INCONCLUSIVE_EXPECTED.

The 105 selected `SKIPPED_ENV` rows still require an actual platform/toolchain/provider/runtime and are not converted to PASS from fixture evidence. Any optional live phase still requires a new, target-specific approval and locally supplied credentials; secrets should not be pasted into chat.
"""
    append_unique(ROOT / "gated-and-live-test-plan.md", "## Approved isolated gated follow-up", gated)

    cnr_path = PHASE / "codex-not-run-defects.md"
    cnr = """
## Approved-gate and remaining-contract additions

| ID | Severity | Finding |
|---|---|---|
| CNR-009 | P1 | Survey archive writes wiki page/graph/log without explicit approval despite dry_run_only policy evidence. |
| CNR-010 | P2 | Office and browser-automation advertise integrations but ship no executable runtime/provider boundary. |
| CNR-011 | P2 | Social-browser capture sidecars omit unified source URL and screenshot artifact evidence. |
| CNR-012 | P2 | Missing Codex CLI produces an uncaught traceback instead of typed failed/inconclusive evidence. |
| CNR-013 | P2 | Method extraction invents a procedure from Background text and idea output lacks explicit source-gap links. |
"""
    append_unique(cnr_path, "## Approved-gate and remaining-contract additions", cnr)


def update_environment() -> None:
    path = ROOT / "environment.json"
    env = json.loads(path.read_text(encoding="utf-8"))
    env["followup_gated_completed_local"] = datetime.now().astimezone().isoformat(timespec="seconds")
    env["followup_gate_authorization"] = "user approved isolated gated tests only; no live providers or real external app/profile mutations"
    env["live_phase_executed"] = False
    path.write_text(json.dumps(env, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def junit_counts(path: Path) -> dict[str, int]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return {
        key: sum(int(float(suite.attrib.get(key, "0"))) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }


def build_report() -> None:
    rows = read_csv(ROOT / "feature-results.csv")
    phase_rows = read_csv(PHASE / "codex-not-run-feature-results.csv")
    status = Counter(row["final_result_status"] for row in rows)
    phase_status = Counter(row["test_result_status"] for row in phase_rows)
    by_part: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        by_part[row["parts"]][row["final_result_status"]] += 1
    coverage = Counter(row["coverage_status"] for row in read_csv(ROOT / "feature-existing-test-map.csv"))
    functions = read_csv(ROOT / "function-inventory.csv")
    function_classes = Counter(row.get("mapping_classification", row.get("classification", "")) for row in functions)
    env = json.loads((ROOT / "environment.json").read_text(encoding="utf-8"))
    blocker = json.loads((PHASE / "remaining-blocker-summary.json").read_text(encoding="utf-8"))
    new_junit = junit_counts(PHASE / "gated-approved" / "remaining-app-browser-provider-contracts.junit.xml")
    direct_ids = list(CASES) + [
        "MISC-0300-HANDLES-SUPPORTED-SOURCE-REQUEST-1A39A8",
        "MISC-0302-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-6ED8E4",
    ]
    by_id = {row["feature_id"]: row for row in rows}
    statuses = [
        "PASS", "FAIL", "BLOCKED_EXPECTED", "INCONCLUSIVE_EXPECTED",
        "SKIPPED_ENV", "SKIPPED_NA", "FLAKY", "NOT_RUN",
    ]

    lines = [
        "# AI4Research Full QA Audit — post-gated update",
        "",
        "## 1. Executive summary",
        "",
        "**Final verdict: NOT READY for a full-repository success or live AutoSci parity claim.** All 1,435 rows that were formerly `NOT_RUN` now have an explicit terminal classification, but 112 atomic features are confirmed FAIL and 381 previously inconclusive rows outside the targeted NOT_RUN follow-up remain inconclusive.",
        "",
        f"Overall 2,117-row status: PASS {status['PASS']}, FAIL {status['FAIL']}, BLOCKED_EXPECTED {status['BLOCKED_EXPECTED']}, INCONCLUSIVE_EXPECTED {status['INCONCLUSIVE_EXPECTED']}, SKIPPED_ENV {status['SKIPPED_ENV']}, SKIPPED_NA {status['SKIPPED_NA']}, NOT_RUN {status['NOT_RUN']}.",
        "",
        f"For the 861 Codex-relevant rows selected from the former NOT_RUN set (after excluding Claude/SciDAG/SciMem), the final result is PASS {phase_status['PASS']}, FAIL {phase_status['FAIL']}, SKIPPED_ENV {phase_status['SKIPPED_ENV']}, SKIPPED_NA {phase_status['SKIPPED_NA']}, with zero NOT_RUN and zero INCONCLUSIVE_EXPECTED. The 576 excluded rows are preserved in `excluded-feature-ledger.csv`.",
        "",
        "Tests used the local repository code at the locked SHA, from a detached isolated checkout. Production source was not modified. No live provider, real browser profile, real Calendar/email, remote machine, release, credential, or real user vault mutation was performed.",
        "",
        "## 2. Tested repo, branch, and commit",
        "",
        "| Field | Value |",
        "|---|---|",
        "| Source | `https://github.com/Stellven/AI4Research.git` |",
        "| Requested/local branch | `openJiuwen-Solar` |",
        f"| Locked/tested SHA | `{env['locked_test_sha']}` |",
        "| Code source used | Local locked checkout under this audit directory |",
        "| Production source edits | None |",
        "| Live phase | Not executed |",
        "",
        "## 3. Environment",
        "",
        f"- Platform: {env['platform']['platform']} ({env['platform']['machine']})",
        f"- Shell: {env['shell']}; Python: {env['tools']['python3']['version']}; Node: {env['tools']['node']['version']}; Bun: {env['tools']['bun']['version']}",
        f"- Git: {env['tools']['git']['version']}; tmux: {env['tools']['tmux']['version']}; jq: {env['tools']['jq']['version']}",
        "- Follow-up gate boundary: disposable local fixtures only; no live credentials/provider/network or real external-app mutation.",
        "",
        "## 4. Inventory validation result",
        "",
        "The control workbook contains 2,117 atomic rows (workflow 652, foundations 844, misc. 621). The locked checkout contains 5,259 tracked files and the generated function/module/route/script inventory contains 31,463 rows. Fifteen public production entrypoints remain classified `missing-feature-row`.",
        "",
        "Post-follow-up corrections include two nonexistent `skills-md` rows changed to `SKIPPED_NA`, concrete Obsidian/Calendar/RAGFlow/Codex/browser/Gemini entrypoints, and explicit documentation-only classifications for office and browser-automation.",
        "",
        "## 5. Feature coverage summary by part",
        "",
        "| Part | " + " | ".join(statuses) + " | Total |",
        "|---|" + "---:|" * (len(statuses) + 1),
    ]
    for part in ("workflow", "foundations", "misc."):
        count = by_part[part]
        lines.append("| " + part + " | " + " | ".join(str(count[s]) for s in statuses) + f" | {sum(count.values())} |")
    lines += [
        "",
        "`feature-results.csv` is authoritative. Coverage mapping and execution status are separate fields; a mapped test is not treated as proof unless its atomic assertions were validated.",
        "",
        "## 6. Function inventory summary",
        "",
        f"- Inventory rows: {len(functions)}",
        "- Classification counts: " + ", ".join(f"{key or 'unclassified'} {value}" for key, value in sorted(function_classes.items())),
        "- Public unmapped entrypoints: 15",
        "",
        "## 7. Test execution summary",
        "",
        "| Execution surface | Result | Interpretation |",
        "|---|---|---|",
        "| Original strict eligible phase | 93 targets passed, 14 failed; 523 tests passed, 15 failed, 3 errored, 1 skipped | Direct testcase attribution; fixture/local only. |",
        "| Approved AutoSci gated selection | 8 passed | Disposable wiki/raw/approval fixtures only. |",
        "| Control-plane plan verdict | 13 assertions passed | Approved verdict stored only in a disposable sprint. |",
        "| Approved gate atomic contracts | 2 passed, 1 failed | Survey archive bypassed approval. |",
        "| Misc side-effect gate contracts | 1 passed, 4 failed | Four surfaces lack a human approval boundary. |",
        "| Manual/oracle contracts | 11 passed, 2 failed | Exact semantic rubrics; no provider claims. |",
        f"| Remaining app/browser/provider contracts | {new_junit['tests'] - new_junit['failures'] - new_junit['errors'] - new_junit['skipped']} passed, {new_junit['failures']} failed | Fake/local providers and disposable data; no live parity. |",
        "| Selected former-NOT_RUN subset | PASS 639, FAIL 72, SKIPPED_ENV 105, SKIPPED_NA 45 | Zero unresolved status in this 861-row scope. |",
        "",
        f"`command-log.tsv` now contains {len(read_csv(ROOT / 'command-log.tsv'))} commands with working directory, exit code, timestamps, evidence paths, and linked feature IDs.",
        "",
        "## 8. Detailed feature results",
        "",
        "The complete 2,117-row result set is `feature-results.csv`. The table below records the final 20 blocker-remediation decisions from the approved isolated follow-up.",
        "",
        "| Feature ID | Result | Atomic feature | Rationale |",
        "|---|---|---|---|",
    ]
    for fid in direct_ids:
        row = by_id[fid]
        lines.append(f"| `{fid}` | {row['final_result_status']} | {md(row['atomic_feature'])} | {md(row['result_rationale'])} |")
    fail_rows = [row for row in rows if row["final_result_status"] == "FAIL"]
    lines += [
        "",
        f"### All confirmed FAIL rows ({len(fail_rows)})",
        "",
        "| Feature ID | Part | Atomic feature | Defect/evidence |",
        "|---|---|---|---|",
    ]
    for row in fail_rows:
        ref = row.get("defect_ids") or row.get("execution_evidence") or "See result rationale"
        lines.append(f"| `{row['feature_id']}` | {md(row['parts'])} | {md(row['atomic_feature'])} | {md(ref)} |")
    lines += [
        "",
        "## 9. Failures and defects",
        "",
        "| Severity | Defect groups | Summary |",
        "|---|---:|---|",
        "| P0 | 0 | No destructive/credential/remote/data-loss event was observed during isolated execution. |",
        "| P1 | 5 | Four original core failures plus the grouped approval-boundary defect D-024. |",
        "| P2 | 24 | Core/important contract drift, missing executable integrations, provider evidence, browser/Codex failure handling, packaging, and semantic gaps. |",
        "| P3 | 9 | CI/installer diagnostics, taxonomy portability, broad discovery/layout, status/documentation gaps. |",
        "| P4 | 0 | None recorded. |",
        "",
        "See `defects.md` and `evidence/codex-not-run-phase/codex-not-run-defects.md`. Feature FAIL count and defect-group count intentionally differ because multiple features share root causes.",
        "",
        "## 10. Gated, skipped, inconclusive, and live-provider-only surfaces",
        "",
        f"The selected former-NOT_RUN subset has {blocker['remaining_inconclusive']} remaining inconclusive rows. Its 105 SKIPPED_ENV rows still need real platform/toolchain/provider/runtime evidence; supplying one API key would not remove every SKIPPED_ENV because some require Windows/Linux, Playwright/renderer binaries, local corpora, or provider-specific runtimes.",
        "",
        "The overall workbook still has 381 INCONCLUSIVE_EXPECTED rows that predated the 1,435-row NOT_RUN follow-up and were not silently promoted. AutoSci remains fixture/local evidence only. Optional live requirements and authorization boundaries are in `gated-and-live-test-plan.md`.",
        "",
        "## 11. Missing tests and recommended additions",
        "",
        "Current validated mapping classes: " + ", ".join(f"{key} {value}" for key, value in sorted(coverage.items())) + ".",
        "",
        "Audit-only direct contracts should be promoted into tracked regression tests. Highest priorities are approval enforcement for survey/integration writes, structured missing-Codex handling, executable office/browser integration boundaries, unified social capture provenance/artifacts, and method/gap semantic regressions. `missing-test-plan.csv` contains the row-level plan.",
        "",
        "## 12. Final readiness verdict",
        "",
        "**NOT READY.** The follow-up successfully removed silent `NOT_RUN` and selected-scope `INCONCLUSIVE_EXPECTED` blockers, but it also confirmed 72 failures in that selected subset and 112 failures overall. Full success requires fixing and directly retesting P1/P2 defects, resolving or accepting the 381 pre-existing inconclusive rows, and separately authorizing any live provider/platform phase. Fixture evidence must not be reported as live AutoSci parity.",
    ]
    (ROOT / "final-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    update_csvs()
    update_markdown()
    update_environment()
    build_report()
    print(json.dumps({"updated": True, "root": str(ROOT)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
