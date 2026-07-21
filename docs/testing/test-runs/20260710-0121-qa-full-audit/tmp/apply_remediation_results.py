from __future__ import annotations

import csv
import json
import shutil
import sys
from collections import Counter
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def surface(row: dict[str, str]) -> str:
    return row["feature_path"].split(">", 1)[0].strip()


def decision(status: str, rationale: str, evidence: str) -> tuple[str, str, str]:
    return status, rationale, evidence


def decide(row: dict[str, str], direct: dict[str, dict[str, str]]) -> tuple[str, str, str] | None:
    fid = row["feature_id"]
    atomic = row["atomic_feature"]
    surf = surface(row)

    safe_atomic_evidence = "evidence/codex-not-run-phase/audit-tests/remaining-safe-atomic-contracts-final2.junit.xml"
    approved_gated_evidence = "evidence/codex-not-run-phase/gated-approved/autosci-approved-gates.junit.xml"
    approved_gated_results = {
        "WF-0006-CLEAN-START-RESETS-STALE-840E0D": (
            "PASS",
            "The approved isolated clean-start contract invoked the locked implementation function against stale hygiene, lease, assignment, and dispatch fixtures; it removed only runtime coordination state and byte-preserved sprint/log fixtures. Static routing assertions also verified both fresh-session and already-running --clean entrypoints call the reset.",
            "evidence/codex-not-run-phase/gated-approved/approved-gated-atomic-contracts.junit.xml",
        ),
        "WF-0013-PLAN-VERDICT-UPDATES-SPRINT-6F9A1D": (
            "PASS",
            "The tracked isolated control-plane suite executed plan-verdict approve on a disposable sprint and verified the approved state plus exact APPROVE verdict and human reason in history (13 assertions passed).",
            "evidence/codex-not-run-phase/gated-approved/control-plane-approved-plan-verdict.txt",
        ),
        "WF-0033-MUTATION-SYNC-EXPLICIT-PRESERVES-ACE99F": (
            "PASS",
            "The approved temporary-vault safety route explicitly invoked installation, refused to replace a user-owned real directory, preserved it as a directory, and confined the vault to a temporary path.",
            "evidence/codex-not-run-phase/gated-approved/obsidian-wiki-safety.txt",
        ),
        "WF-0204-APPROVED-WRITEBACK-UPDATES-LINKED-C80F8A": (
            "PASS",
            "The exact approved claim-writeback test supplied approval, allowlist, runtime, before/after, and execute evidence; it updated the linked idea, log, graph edge, and open-question view and emitted approval/wiki mutation proof manifests.",
            approved_gated_evidence,
        ),
        "WF-0225-PROPOSES-APPLIES-SOURCE-ADDITION-B13BB8": (
            "PASS",
            "The approved raw-add route created only the exact requested raw path from the supplied after artifact, recorded provenance hashes, rejected overwrite of an existing raw target, and emitted typed mutation evidence.",
            approved_gated_evidence,
        ),
        "WF-0226-EDITS-ONLY-REQUESTED-PAGE-8EFA8E": (
            "PASS",
            "The exact approved edit test applied the requested after artifact to a disposable wiki target and verified the resulting mutation/proof artifacts without touching external data.",
            approved_gated_evidence,
        ),
        "WF-0227-REQUIRES-EXPLICIT-CONFIRMATION-APPROVAL-FDDEE7": (
            "PASS",
            "The approved raw-delete test required approval-ref, allowlist, runtime, before/after artifacts, execute-approved, and --delete; it removed only the requested fixture target and emitted approval, side-effect, and wiki-mutation proof manifests.",
            approved_gated_evidence,
        ),
        "WF-0228-NEW-RAW-SOURCE-ADDITION-46F58A": (
            "PASS",
            "The direct approved raw-add audit asserted the exact /ingest follow-up string, a single edit_wiki_plan action, and absence of any ingest artifact or automatically executed ingest action.",
            "evidence/codex-not-run-phase/gated-approved/approved-gated-atomic-contracts.junit.xml",
        ),
        "WF-0239-APPROVED-WRITEBACK-RECORDS-PILOT-5B670A": (
            "PASS",
            "The exact approved pilot-evaluation writeback test used runtime and approval evidence, wrote the supported verdict to the disposable idea and graph, and emitted final-acceptance plus approval/wiki proof artifacts.",
            approved_gated_evidence,
        ),
        "WF-0247-ARCHIVAL-WRITEBACK-EXPLICIT-APPROVED-0CA46A": (
            "FAIL",
            "The no-approval survey contract returned exit 0 and wrote a survey page, derived_from edge, and wiki log even though the run advertised dry_run_only; the implementation performs archive mutation without an explicit approval contract.",
            "evidence/codex-not-run-phase/gated-approved/approved-gated-atomic-contracts.junit.xml",
        ),
        "WF-0266-EXECUTION-REQUIRES-EXPLICIT-APPROVAL-9BF203": (
            "PASS",
            "The approved wiki-only reset supplied an explicit scope, approval, allowlist, before evidence, and execute flag; it removed only scoped wiki artifacts, preserved raw source data, and emitted runtime/approval/side-effect/wiki proof manifests.",
            approved_gated_evidence,
        ),
        "MISC-0303-ANY-EXTERNAL-WRITE-BROWSER-1F66D8": (
            "SKIPPED_NA",
            "The feature taxonomy names a skills-md integration, but the map points to skills/solar/SKILL.md and the locked checkout contains no skills-md executable. This side-effect atom is attached to a nonexistent/stale surface.",
            "feature-entrypoint-map.csv; inventory-diff.md",
        ),
        "MISC-0308-ANY-EXTERNAL-WRITE-BROWSER-F66FD9": (
            "FAIL",
            "The office skill documents email send, reminder/task creation, Notes writes, Notion page creation, and Trello mutation but contains no explicit approval/confirmation policy; the direct policy contract therefore failed.",
            "evidence/codex-not-run-phase/gated-approved/misc-side-effect-gate-contracts.junit.xml",
        ),
        "MISC-0313-ANY-EXTERNAL-WRITE-BROWSER-AEAD47": (
            "FAIL",
            "The shipped obsidian-direct skill documents create/edit/replace operations but contains no explicit approval/confirmation boundary before mutation; the direct policy contract failed.",
            "evidence/codex-not-run-phase/gated-approved/misc-side-effect-gate-contracts.junit.xml",
        ),
        "MISC-0318-ANY-EXTERNAL-WRITE-BROWSER-DD521D": (
            "FAIL",
            "The mapped Apple Calendar skill exposes create, update, and delete commands (including recurring-series deletion) without an explicit approval/confirmation requirement; the direct policy contract failed.",
            "evidence/codex-not-run-phase/gated-approved/misc-side-effect-gate-contracts.junit.xml",
        ),
        "MISC-0328-ANY-EXTERNAL-WRITE-BROWSER-A76165": (
            "PASS",
            "The approved Obsidian integration safety test used only a disposable vault/skill target, required explicit install invocation, refused to replace a real user-owned directory, and confirmed the mutation target remained temporary.",
            "evidence/codex-not-run-phase/gated-approved/obsidian-wiki-safety.txt",
        ),
        "MISC-0333-ANY-EXTERNAL-WRITE-BROWSER-2338B6": (
            "SKIPPED_NA",
            "The mapped RAGFlow adapter surface performs retrieval/config reporting and caller-scoped local result handling; it exposes no remote write, browser-control, or send mutation action to which this generic approval atom applies.",
            "harness/lib/ragflow_adapter.py; harness/tools/ragflow_adapter.py; inventory-diff.md",
        ),
        "MISC-0338-ANY-EXTERNAL-WRITE-BROWSER-4CE79F": (
            "PASS",
            "The isolated Codex state test proved export is non-mutating and import occurs only through the explicit import subcommand; approved import created a backup, updated only the three scoped tables, rewrote portable paths, and preserved an unscoped user-owned table.",
            "evidence/codex-not-run-phase/gated-approved/misc-side-effect-gate-contracts.junit.xml",
        ),
        "MISC-0348-ANY-EXTERNAL-WRITE-BROWSER-417B43": (
            "FAIL",
            "The mapped browser automation policy returns external_action_allowed/ready when a secret exists and the browser is logged in, without any human-approval input or decision. The direct approval-policy contract failed even though the older branch test passes its weaker implementation contract.",
            "evidence/codex-not-run-phase/gated-approved/misc-side-effect-gate-contracts.junit.xml; evidence/codex-not-run-phase/gated-approved/browser-existing-policy.junit.xml",
        ),
    }
    if fid in approved_gated_results:
        return decision(*approved_gated_results[fid])
    manual_oracle_evidence = "evidence/codex-not-run-phase/gated-approved/manual-oracle-atomic-contracts.junit.xml"
    manual_oracle_results = {
        "WF-0117-RESPONSES-AVOID-FABRICATED-DATA-AA7E7B": (
            "PASS",
            "A direct rebuttal run with an unsupported reviewer concern selected the evidence-insufficient response strategy, explicitly said the evidence was not sufficient, and passed the no_fabrication/no_overpromise safety checks.",
        ),
        "WF-0134-SUGGESTIONS-CONCRETE-DO-NOT-06EE1A": (
            "PASS",
            "The direct review route preserved the target digest and returned a concrete ablation-table suggestion naming baseline, treatment, metric, and failure-mode fields.",
        ),
        "WF-0147-EACH-SEED-MODE-YIELDS-3735D8": (
            "PASS",
            "Direct topic, anchors/negative-IDs, wiki, and venue discovery fixtures each returned a ranked candidate list with non-empty source_channels, numeric ranking_score, and ranking_rationale.",
        ),
        "WF-0158-ANALYSIS-FIELDS-POPULATED-LIMITATIONS-AF402A": (
            "PASS",
            "The direct analyze_paper route populated paper id/title/source, parsed sections, summary, key concepts, and limitations against a locked local paper fixture.",
        ),
        "WF-0159-EVERY-ANALYTICAL-STATEMENT-SOURCE-F49715": (
            "PASS",
            "The analysis block carried both paper-id and source-ref evidence IDs, and every parsed analytical section had a stable source anchor.",
        ),
        "WF-0172-RETURNS-NOT-TESTABLE-INCOMPLETE-71526E": (
            "PASS",
            "Empty paper input produced a not_testable claim explicitly stating that no grounded claim was found, with a non-testable reason and evidence identifiers instead of a fabricated claim.",
        ),
        "WF-0176-REPORTS-INCOMPLETE-METHOD-EVIDENCE-E24804": (
            "FAIL",
            "For a paper containing only a Background section, extract_methods labeled it `Background protocol` and generated a procedure instead of reporting `No explicit method found`/incomplete evidence.",
        ),
        "WF-0177-GENERATED-CANDIDATES-CITE-SOURCE-FA4851": (
            "FAIL",
            "Generated ideas carried origin_evidence_ids, but the new candidate emitted no explicit gap_links, gap_ids, or source_gap_ids field required to link the candidate to the claimed research gap.",
        ),
        "WF-0191-REVIEW-EVIDENCE-ATTACHED-MARKED-270248": (
            "PASS",
            "Experiment design without Review LLM evidence explicitly recorded review_llm.status=unavailable, a not-supplied limitation, and review_llm_completed=false in the final execution boundary.",
        ),
        "WF-0203-REVIEW-LLM-DISAGREEMENT-RECORDED-885CB3": (
            "PASS",
            "A supporting experiment result paired with a revise_required independent review retained the supported evidence verdict while recording the Review LLM recommendation, review evidence ID, and independent-second-opinion limitation.",
        ),
        "WF-0243-REVIEW-EVIDENCE-ATTACHED-ABSENT-1BA315": (
            "PASS",
            "The plan_report route rejected structurally weak review evidence as invalid/inconclusive and named the missing Review LLM boundary rather than silently treating it as completed.",
        ),
        "WF-0250-RESPONSES-AVOID-FABRICATED-DATA-DFB9AB": (
            "PASS",
            "The direct draft_rebuttal action kept an unsupported concern on strategy B, explicitly acknowledged insufficient evidence, and passed no_fabrication/no_overpromise checks.",
        ),
        "WF-0287-SUGGESTIONS-CONCRETE-DO-NOT-6A47C4": (
            "PASS",
            "The direct review_artifact action emitted a specific ablation-table remediation while a before/after digest proved the reviewed target was not mutated.",
        ),
    }
    if fid in manual_oracle_results:
        status, rationale = manual_oracle_results[fid]
        return decision(status, rationale, manual_oracle_evidence)
    remaining_contract_evidence = "evidence/codex-not-run-phase/gated-approved/remaining-app-browser-provider-contracts.junit.xml"
    remaining_contract_results = {
        "WF-0422-CAPTURED-OUTPUT-HAS-SOURCE-1CDA2F": (
            "PASS",
            "A fake in-process browser probe ran through the locked submit/poll/collect entrypoints and produced a page.json with the exact final URL, non-empty start/finish timestamps, screenshot, HTML, text, metadata, and result JSON artifacts in a disposable directory.",
        ),
        "WF-0423-RETRIES-FAILS-CHECKPOINTED-STATE-089989": (
            "PASS",
            "A deterministic running-to-failed sequence persisted its terminal state, repeated polling byte-preserved the checkpoint, and repeated collection overwrote the same bounded artifact set without creating duplicate side effects.",
        ),
        "WF-0425-RUNS-RECORDS-BROWSER-AUTOMATION-FAA4C2": (
            "PASS",
            "Two identical social-browser CLI invocations with no wired pipeline returned the same typed lease-fallback exit code, browser_ready=0 status, and explicit no-pipeline message without attempting a live browser.",
        ),
        "WF-0426-CAPTURED-OUTPUT-HAS-SOURCE-6F503B": (
            "FAIL",
            "The isolated mock social-browser pipeline stored a post and JSON sidecars, but the Knowledge raw artifact omitted source_url and the queue artifact omitted a screenshot artifact binding, so URL, timestamp, and capture artifacts are not unified in the required output contract.",
        ),
        "MISC-0300-HANDLES-SUPPORTED-SOURCE-REQUEST-1A39A8": (
            "SKIPPED_NA",
            "The taxonomy names skills-md, but the locked checkout has no skills-md directory or executable and the prior map incorrectly points this row to skills/solar/SKILL.md; there is no such product surface to execute.",
        ),
        "MISC-0302-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-6ED8E4": (
            "SKIPPED_NA",
            "The taxonomy names skills-md, but the locked checkout has no skills-md provider boundary; the prior skills/solar mapping is stale and this unavailable-provider atom is not applicable to a real shipped surface.",
        ),
        "MISC-0305-HANDLES-SUPPORTED-SOURCE-REQUEST-0F0924": (
            "FAIL",
            "The shipped skills/office directory contains only SKILL.md prose and no executable dispatcher or adapter, so there is no entrypoint that accepts supported office requests or rejects unsupported ones.",
        ),
        "MISC-0307-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-5310ED": (
            "FAIL",
            "The shipped office skill has no executable provider boundary and therefore cannot emit a structured failed/inconclusive result when Himalaya, Reminders, Things, Notion, or Trello is unavailable.",
        ),
        "MISC-0310-HANDLES-SUPPORTED-SOURCE-REQUEST-28972A": (
            "PASS",
            "The Obsidian CLI created a note only inside a disposable vault for a supported request and argparse rejected an unsupported command with a non-zero process status.",
        ),
        "MISC-0312-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-CBB1BC": (
            "PASS",
            "The Obsidian CLI received a nonexistent disposable vault, exited non-zero with an explicit Vault not found reason, created no vault or fake note, and returned no fabricated data.",
        ),
        "MISC-0315-HANDLES-SUPPORTED-SOURCE-REQUEST-2B0A68": (
            "PASS",
            "The calendar adapter accepted a supported create request against a fake gog executable and returned the fixture event ID, while missing required fields and an unknown action were rejected non-zero.",
        ),
        "MISC-0317-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-5022AD": (
            "PASS",
            "With an empty PATH the calendar adapter returned non-zero structured JSON stating gog command not found; an unknown provider likewise returned non-zero typed JSON and no event data.",
        ),
        "MISC-0322-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-E5C821": (
            "PASS",
            "The mapped browser skill's structured setup.json explicitly reports setupComplete=false and names Chrome, API-key, dependency, and browser-command prerequisites as unavailable instead of reporting synthetic browser output.",
        ),
        "MISC-0327-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-AF98BB": (
            "PASS",
            "The Obsidian wiki status entrypoint ran under an isolated empty HOME and emitted valid JSON with configured=false, empty repo/vault paths, and all skill-install flags false, without creating fake integration evidence.",
        ),
        "MISC-0330-HANDLES-SUPPORTED-SOURCE-REQUEST-717B2C": (
            "PASS",
            "The RAGFlow CLI accepted a supported search request and emitted its typed offline result; argparse rejected an unsupported source choice with a non-zero status.",
        ),
        "MISC-0332-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-83BF1C": (
            "PASS",
            "With no config, base URL, key, dataset, or network, RAGFlow returned exit 2 and structured JSON with hits=[] plus ragflow:missing_base_url, proving it does not fabricate retrievals.",
        ),
        "MISC-0335-HANDLES-SUPPORTED-SOURCE-REQUEST-24C223": (
            "PASS",
            "The Codex operator accepted a non-empty dispatch through a fake isolated codex executable and wrote the exact result artifact; an empty dispatch was rejected with exit 64 and an explicit reason.",
        ),
        "MISC-0337-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-2C2F4E": (
            "FAIL",
            "When the Codex CLI is absent, codex_operator.py raises an uncaught FileNotFoundError traceback and writes no typed failed/inconclusive status artifact.",
        ),
        "MISC-0347-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-89ACF0": (
            "FAIL",
            "browser-automation/setup.json truthfully reports every prerequisite unavailable, but the mapped skill package ships no executable runtime file that can turn that state into a structured invocation failure; it is documentation-only.",
        ),
        "MISC-0375-HANDLES-SUPPORTED-SOURCE-REQUEST-5089BE": (
            "PASS",
            "The locked Gemini Deep Research ResearchRequest model accepted and round-tripped a supported user request, while rejecting blank text and an unsupported source through typed InvalidResearchRequest exceptions without provider access.",
        ),
    }
    if fid in remaining_contract_results:
        status, rationale = remaining_contract_results[fid]
        evidence = remaining_contract_evidence
        if status == "SKIPPED_NA":
            evidence = "feature-entrypoint-map.csv; inventory-diff.md"
        return decision(status, rationale, evidence)
    safe_atomic_results = {
        "WF-0020-REPORTS-RUNNING-COMPLETED-FAILED-2EE241": (
            "PASS",
            "An isolated background-task fixture observed the durable running state, then verified completed/failed terminal states and their exact exit codes; the status entrypoint listed both terminal outcomes.",
        ),
        "WF-0022-AGGREGATES-STATS-EXISTING-ARTIFACTS-C98D1A": (
            "PASS",
            "The read-only stats entrypoint aggregated two temporary telemetry records into exact totals/rate/round counts while a before/after digest proved no mutation.",
        ),
        "WF-0024-RETURNS-EMPTY-ZERO-STATE-ED18F4": (
            "PASS",
            "The isolated stats entrypoint returned the explicit no-telemetry zero state with exit 0, no fabricated counts, and no filesystem mutation.",
        ),
        "WF-0027-FAILURE-LEAVES-SOURCE-DATA-40F13A": (
            "FAIL",
            "A malformed local migration bundle was rejected and source bytes stayed intact, but the failure emitted no partial-state, rollback, or recovery-state report required by the atomic contract.",
        ),
        "WF-0105-UNCONFIRMED-CITATIONS-EXPLICIT-BLOCKERS-A7B45F": (
            "FAIL",
            "The paper-plan route accepted a source-backed but unconfirmed citation into its citation map; its final boundary blocked for other reasons but did not identify the unconfirmed citation as a blocking reason.",
        ),
        "WF-0110-OVERFLOW-REPORT-REFINEMENTS-EXPLICIT-9E7FB7": (
            "PASS",
            "With no approved browser/runtime proof, poster overflow remained `not_run`, runtime semantic verification stayed false, and the route could not produce a completed/pass result or PNG proof.",
        ),
        "WF-0152-MARKDOWN-SECTIONS-BECOME-SOURCE-4B1A70": (
            "PASS",
            "Two independent local Markdown ingests produced the same non-empty section identifiers and source anchors, each anchor ending in the corresponding stable section id.",
        ),
        "WF-0185-RESOLVES-CODE-SOURCE-RECORDS-5CE0CF": (
            "PASS",
            "The selected tracked map-code test directly exercised a missing repository source and recorded the unavailable/unknown path instead of fabricating code evidence.",
        ),
        "WF-0217-SCANS-NORMALIZES-LOCAL-SOURCES-F96B00": (
            "PASS",
            "The no-network init-sources route scanned temporary raw/papers, raw/notes, and raw/web inputs into its checkpoint preparation manifest while keeping provider fetch explicitly incomplete.",
        ),
        "WF-0233-LOADS-BOUNDED-PILOT-SPEC-059100": (
            "FAIL",
            "The pilot-run route did not load a required bounded pilot spec or reject the missing dataset/config contract; it returned generic inconclusive diagnostics instead.",
        ),
        "WF-0234-GENERATED-PILOT-CODE-RECORDED-49FB18": (
            "FAIL",
            "Even when supplied a temporary pilot YAML and dataset, the no-execution route emitted neither a pilot-spec snapshot nor generated code/runner artifact before the execution boundary.",
        ),
        "WF-0236-RUNNER-EMITS-RESULT-EVIDENCE-A54EC9": (
            "PASS",
            "The no-execution pilot runner returned typed inconclusive result evidence, kept final acceptance false, and emitted no accepted/rejected final verdict in the result outputs.",
        ),
        "WF-0237-REJECTS-MISSING-PILOT-SPEC-50DC6B": (
            "PASS",
            "Pilot evaluation with no result evidence returned a typed inconclusive verdict, an explicit not-supplied basis, and final_pilot_acceptance_ready=false.",
        ),
        "WF-0240-REJECTS-MARKS-INCOMPLETE-WHEN-39AED7": (
            "PASS",
            "Paper planning against an empty temporary idea/experiment graph kept final acceptance false and explicitly reported missing validated-idea plus succeeded-experiment evidence.",
        ),
        "WF-0242-UNCONFIRMED-CITATIONS-EXPLICIT-BLOCKERS-5D6C04": (
            "FAIL",
            "The plan-report final boundary did not list the supplied unconfirmed citation as a blocker even though the citation was present in its source map.",
        ),
        "WF-0253-POSTER-HTML-INCLUDES-REQUIRED-56B1ED": (
            "PASS",
            "The local poster pipeline generated HTML containing title, venue, introduction, method, and results content without raw LaTeX commands or TODO markers.",
        ),
        "WF-0255-OVERFLOW-REPORT-REFINEMENTS-EXPLICIT-EC42D7": (
            "PASS",
            "Unresolved/not-run overflow evidence prevented runtime verification and completed poster status; no PNG or full runtime-proof artifact was emitted.",
        ),
        "WF-0264-MISSING-INVALID-SCOPE-REJECTED-E14DB0": (
            "FAIL",
            "A reset request with no scope defaulted to `wiki` and returned completed instead of rejecting the missing scope, although the temporary wiki source bytes were preserved.",
        ),
        "WF-0265-PLAN-GENERATED-WITHOUT-MUTATION-38B119": (
            "FAIL",
            "The reset dry-run correctly listed the exact candidate deletion and preserved source bytes, but the bridge labeled the dry-run evidence `completed`, violating the requirement that a plan is not research-success evidence.",
        ),
        "WF-0277-DRY-RUN-PROPOSES-FIXES-6FC1FB": (
            "FAIL",
            "The check-wiki route preserved the malformed temporary wiki, but ignored the requested fix/dry-run semantics: it emitted no exact graph/edges.jsonl fix and left patch_candidates empty.",
        ),
        "FD-0594-LOADS-CAPABILITY-CONFIG-REGISTRY-5EF037": (
            "FAIL",
            "With capability rules unavailable, enrich-graph silently returned exit 0 and `ok: true` instead of reporting missing/invalid rule configuration.",
        ),
        "MISC-0224-PORT-CONFLICTS-DEAD-PROCESSES-FDEC82": (
            "PASS",
            "With every loopback port 8765-8775 occupied, status-server exited non-zero with the exact exhausted-range error and wrote no stale discovery port file.",
        ),
        "MISC-0246-EXPECTED-INSTALLER-PACKAGE-ARTIFACTS-C547FA": (
            "PASS",
            "The pipx package built offline into a wheel whose METADATA contained the exact project/version, whose entry_points exposed openjiuwen-solar, and whose package included opensolar_cli/cli.py.",
        ),
        "MISC-0283-FAILURES-STOP-CLEANLY-ACTIONABLE-41DB07": (
            "PASS",
            "Release packaging without VERSION/--version stopped non-zero with an exact remedy and created no partial output artifacts.",
        ),
        "MISC-0286-EXPECTED-INSTALLER-PACKAGE-ARTIFACTS-5058AB": (
            "PASS",
            "The PyPI preparation surface produced a valid offline wheel with exact name/version metadata, console entrypoint, and packaged CLI module.",
        ),
    }
    if fid in safe_atomic_results:
        status, rationale = safe_atomic_results[fid]
        evidence = safe_atomic_evidence
        if fid == "WF-0185-RESOLVES-CODE-SOURCE-RECORDS-5CE0CF":
            evidence = "evidence/codex-not-run-phase/audit-tests/remaining-autosci-selected-direct-contracts.junit.xml"
        if fid in {
            "WF-0264-MISSING-INVALID-SCOPE-REJECTED-E14DB0",
            "WF-0265-PLAN-GENERATED-WITHOUT-MUTATION-38B119",
            "WF-0277-DRY-RUN-PROPOSES-FIXES-6FC1FB",
        }:
            evidence = "evidence/codex-not-run-phase/audit-tests/reset-check-safe-atomic-contracts.junit.xml"
        return decision(status, rationale, evidence)

    if fid == "FD-0574-LOADS-CAPABILITY-CONFIG-REGISTRY-9D4BC5":
        return decision(
            "SKIPPED_NA",
            "The real capability-prefix implementation is a pure presentation formatter and does not load capability config or registry data; the spreadsheet attached a capability-inference/registry atom to the wrong entrypoint.",
            "inventory-diff.md; harness/lib/capability-prefix.sh",
        )
    if fid == "FD-0581-DUPLICATE-STALE-ENTRIES-DO-DD1FAB":
        return decision(
            "FAIL",
            "The activation proof's negative-control check did not pass (the underlying injection command errored), and the mapped proof surface does not exercise or report the spreadsheet's claimed duplicate/stale registry contract.",
            "evidence/codex-not-run-phase/audit-tests/capability-plane-direct-contracts-final.junit.xml; tmp/pytest-capability-final2/test_capability_activation_pro0/home/.solar/harness/reports/capability-activation-evidence/latest/activation-proof.json",
        )

    github_release_taxonomy = {
        "MISC-0289-ACCEPTED-FLAGS-ENV-CONFIG-57233D",
        "MISC-0290-PLATFORM-SPECIFIC-PATH-RUNS-AF1733",
        "MISC-0291-EXPECTED-INSTALLER-PACKAGE-ARTIFACTS-2CAD89",
        "MISC-0292-DRY-RUN-WRITES-NOTHING-966C17",
        "MISC-0293-FAILURES-STOP-CLEANLY-ACTIONABLE-AECCF8",
    }
    if fid in github_release_taxonomy:
        return decision(
            "SKIPPED_NA",
            "The checkout has an owner-facing GitHub release checklist but no GitHub-release-preparation executable accepting these generic installer flags/platform/dry-run contracts; the map to install.sh/get-solar.sh/install.ps1 is a stale entrypoint association.",
            "docs/RELEASE-CHECKLIST.md; inventory-diff.md",
        )

    if fid == "MISC-0129-EXPECTED-BUILD-PACKAGE-TEST-48FF27":
        return decision(
            "SKIPPED_NA",
            "The `solar ui` entrypoint is a launcher/status route and does not expose a build/package artifact command; the generic package atom is attached to the wrong UI entrypoint.",
            "evidence/codex-not-run-phase/audit-tests/cli-direct-contracts-remediation-final.junit.xml; inventory-diff.md",
        )
    if fid == "MISC-0130-PLATFORM-SPECIFIC-PATH-HEADLESS-E8A2FC":
        return decision(
            "PASS",
            "The isolated `solar ui --once` route deterministically reported the not-installed/manual-start headless state, while invalid UI options returned non-zero with usage guidance and left HOME unchanged.",
            "evidence/codex-not-run-phase/audit-tests/cli-direct-contracts-remediation-final.junit.xml",
        )

    direct_row = direct.get(fid, {})
    if direct_row.get("decision") == "DIRECT_PASS_CANDIDATE" and surf.startswith(
        ("AutoSci slash workflow:", "AutoSci bridge action workflow:", "AutoSci route action workflow:", "Bridge/route foundation:")
    ):
        return decision(
            "PASS",
            "A previously executed passed testcase was re-adjudicated at assertion level and directly matches both this atomic behavior and its concrete AutoSci surface.",
            direct_row.get("junit_evidence", "") + "; evidence/codex-not-run-phase/direct-existing-evidence-adjudication.csv",
        )

    if surf.startswith("Side-effect class:") or surf.startswith("Gate policy mode:"):
        return decision(
            "PASS",
            "The isolated gate-policy matrix directly verified strict-HITL blocking, safe-mode boundaries, approval/env opt-ins, typed decisions, and no side-effect execution for blocked routes.",
            "evidence/codex-not-run-phase/audit-tests/gate-hitl-direct-contracts.junit.xml",
        )

    model_results = {
        "WF-0016-SHOWS-PER-ROLE-MODEL-DAEEEC": (
            "PASS",
            "The isolated models-show probe listed PM/planner/builder/evaluator/lab roles and left both HOME and the caller-selected config unchanged.",
        ),
        "WF-0017-UPDATES-MODEL-CONFIG-ONLY-55333B": (
            "FAIL",
            "`models set-main opus` mutated the isolated SOLAR_USER_CONFIG even though `--apply` was not supplied.",
        ),
        "WF-0018-INVALID-MODEL-REJECTED-ALLOWED-14FEE5": (
            "FAIL",
            "The invalid alias was rejected, but the error only said `unsupported model alias` and omitted the required allowed options.",
        ),
    }
    if fid in model_results:
        status, rationale = model_results[fid]
        return decision(
            status,
            rationale,
            "evidence/codex-not-run-phase/audit-tests/remaining-core-direct-contracts-final2.junit.xml",
        )

    if surf.startswith("Benchmark workflow: runner doctor") or surf.startswith("Benchmark workflow: runner list"):
        return decision(
            "SKIPPED_NA",
            "The spreadsheet assigns a run-report contract to a discovery/doctor entrypoint. Direct probes verified the actual typed doctor/list output, but these commands do not create task/solver run reports; the atomic pairing is stale.",
            "evidence/codex-not-run-phase/audit-tests/remaining-core-direct-contracts-final2.junit.xml; inventory-diff.md",
        )
    if surf.startswith("Benchmark workflow: status_banner"):
        return decision(
            "SKIPPED_NA",
            "The status-banner entrypoint renders a bounded one-line summary from an existing report and accepts no benchmark task arguments; the generic runner atoms attached to it are stale taxonomy pairings.",
            "evidence/codex-not-run-phase/audit-tests/remaining-core-direct-contracts-final2.junit.xml; inventory-diff.md",
        )

    if surf == "Knowledge ingestion workflow: knowledge_ingest_dispatcher reconcile":
        if atomic.startswith(("Discovers candidate", "Queues documents")):
            return decision(
                "SKIPPED_NA",
                "`reconcile` compares filesystem and registry state; it does not discover or enqueue documents. The atomic behavior is attached to the wrong command.",
                "evidence/codex-not-run-phase/audit-tests/knowledge-remaining-direct-contracts-final.junit.xml; inventory-diff.md",
            )
        return decision(
            "PASS",
            "The isolated reconcile command emitted real filesystem/registry counts, coverage, missing/orphan samples, and a typed verdict without inventing progress.",
            "evidence/codex-not-run-phase/audit-tests/knowledge-remaining-direct-contracts-final.junit.xml",
        )

    if surf.startswith("Knowledge health workflow:"):
        if atomic.startswith("Separates blockers"):
            return decision(
                "FAIL",
                "The direct health/audit/circuit JSON provides status, counts, and reasons but has no separate blocker and recommendation fields required by the atomic contract.",
                "evidence/codex-not-run-phase/audit-tests/knowledge-remaining-direct-contracts-final.junit.xml",
            )
        if atomic.startswith("Does not mutate"):
            return decision(
                "FAIL",
                "The health/audit entrypoints call registry migration on open, and therefore can create or alter registry state despite the no-mutation atomic criterion.",
                "evidence/codex-not-run-phase/audit-tests/knowledge-remaining-direct-contracts-final.junit.xml",
            )

    if surf == "TaskGraph foundation: architecture guard":
        return decision(
            "PASS",
            "The isolated graph scheduler contract validated schema, required node fields, topology, cycle rejection, capability/operator assignment, and gate-aware readiness.",
            "evidence/codex-not-run-phase/remediation-shell-contract-results.csv",
        )
    if surf == "TaskGraph foundation: resume contract":
        return decision(
            "PASS",
            "Direct evidence-schema and graph-state contracts accepted typed failed/inconclusive evidence while rejecting missing provenance and overclaiming.",
            "evidence/codex-not-run-phase/audit-tests/evidence-schema-contracts.junit.xml; evidence/codex-not-run-phase/remediation-shell-contract-results.csv",
        )

    if surf.startswith("Status service: status server / dashboard API"):
        if atomic.startswith("Port conflicts"):
            return None
        return decision(
            "PASS",
            "Twenty-four isolated status-service tests validated deterministic not-running/empty states, status payload schemas, asset/API responses, and filesystem-derived dashboard projection.",
            "evidence/codex-not-run-phase/audit-tests/status-service-direct-contracts.junit.xml",
        )
    if surf.startswith("Status service: status-daemon login autostart"):
        return decision(
            "SKIPPED_ENV",
            "Login-autostart requires a real launchd/systemd user session and port lifecycle. It was not mutated in the offline isolated-HOME phase.",
            "evidence/codex-not-run-phase/audit-tests/status-service-direct-contracts.junit.xml",
        )

    if fid in {
        "WF-0028-REPORTS-INSTALL-RUNTIME-DOCTOR-6F8A0F",
        "WF-0029-RENDERS-DASHBOARD-TUI-RUNTIME-49F8F2",
        "WF-0030-HANDLES-NOT-RUNNING-RUNNING-111B58",
    }:
        return decision(
            "PASS",
            "Isolated lifecycle/UI and 24 status-service contracts directly verified deterministic install/runtime/doctor summaries plus not-running, empty, running-projection, and error payloads.",
            "evidence/codex-not-run-phase/audit-tests/cli-direct-contracts-remediation-final.junit.xml; evidence/codex-not-run-phase/audit-tests/status-service-direct-contracts.junit.xml",
        )
    if fid == "WF-0032-READ-ONLY-RETRIEVAL-RETURNS-CBA1FC":
        return decision(
            "PASS",
            "Direct local provider/knowledge fixtures returned source URLs, timestamps where supported, and explicit limitations without mutating provider or user data.",
            "evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml; evidence/codex-not-run-phase/remediation-shell-contract-results.csv",
        )

    autosci_additional_pass = {
        "WF-0183-EXTERNAL-EVIDENCE-RECORDED-EXPLICITLY-66B75E": "The scientific lifecycle smoke test directly blocked the configured publication tail when external evidence was absent and recorded that boundary.",
        "WF-0200-PIPELINE-STAGE-ADVANCEMENT-EXPLICIT-AB91FF": "The tracked research-start/monitor fixtures directly wrote pipeline artifacts and recorded explicit stage advancement rather than silently changing state.",
        "WF-0207-SIDECARS-EXPLICIT-DO-NOT-8B3D7E": "Tracked report/publication fixtures kept survey/rebuttal/poster sidecars separate from verified compile evidence and blocked implied publication.",
        "WF-0222-FETCHED-SUPPLIED-SOURCE-EVIDENCE-E8E60E": "Prefill and scheduler fixtures recorded supplied/online source evidence and kept disabled-fetch limitations visible.",
        "WF-0281-GENERATED-CONFIGS-REFERENCE-VALID-BF0135": "The same direct visualization contracts generated valid workspace graph/config artifacts with local-only paths.",
    }
    if fid in autosci_additional_pass:
        return decision(
            "PASS",
            autosci_additional_pass[fid],
            "evidence/codex-not-run-phase/autosci-shim-rerun-final-junit/codex-nr-0009.xml",
        )
    if fid == "WF-0276-REPORTS-DETERMINISTIC-STRUCTURAL-ERRORS-65ACD8":
        return decision(
            "FAIL",
            "The direct wiki/knowledge health output reports counts/status but does not classify structural errors by severity as required.",
            "evidence/codex-not-run-phase/audit-tests/knowledge-remaining-direct-contracts-final.junit.xml",
        )

    if fid == "FD-0585-DUPLICATE-STALE-ENTRIES-DO-5D2E4B":
        return decision(
            "PASS",
            "The certification suite's negative-controls stage passed: fake capability queries and unrelated injected providers were reported without corrupting the registry.",
            "evidence/codex-not-run-phase/audit-tests/capability-plane-direct-contracts-final.junit.xml; tmp/pytest-capability-final2/test_capability_certification_0/evidence/certification.json",
        )

    if surf == "Installer / packaging surface: openjiuwen-solar pipx wrapper":
        wrapper_evidence = "evidence/codex-not-run-phase/audit-tests/pipx-wrapper-direct-contracts.junit.xml"
        if fid == "MISC-0246-EXPECTED-INSTALLER-PACKAGE-ARTIFACTS-C547FA":
            return None
        if fid == "MISC-0248-FAILURES-STOP-CLEANLY-ACTIONABLE-853305":
            return decision(
                "FAIL",
                "The wrapper caches the lifecycle binary path at import time. Under a changed isolated HOME, installed-command delegation and missing-install remedies referenced the outer HOME instead of the caller's HOME (7 direct failures).",
                wrapper_evidence,
            )
        return decision(
            "PASS",
            "Direct wrapper tests validated exact argument/environment forwarding, file/legacy installer overrides, dry-run forwarding, source lookup, help warnings, and explicit Windows/WSL guidance.",
            wrapper_evidence,
        )

    if surf == "Installer / packaging surface: PyPI wrapper preparation":
        wrapper_evidence = "evidence/codex-not-run-phase/audit-tests/pipx-wrapper-direct-contracts.junit.xml"
        if atomic.startswith("Expected installer/package artifacts"):
            return None
        if atomic.startswith("Failures stop cleanly"):
            return decision(
                "FAIL",
                "Direct wrapper tests exposed import-time HOME caching, so failure remedies/delegation can point at the wrong installation when HOME changes.",
                wrapper_evidence,
            )
        return decision(
            "PASS",
            "The tracked PyPI wrapper parsed and forwarded documented flags/env, preserved dry-run behavior, and reported native Windows as unsupported with WSL/install.ps1 guidance.",
            wrapper_evidence,
        )

    if surf == "Installer / packaging surface: release checklist":
        return decision(
            "SKIPPED_NA",
            "The mapped surface is an owner-facing Markdown checklist, not an executable entrypoint. Its generic platform/artifact/dry-run/failure atoms are stale taxonomy pairings and require separate concrete commands.",
            "docs/RELEASE-CHECKLIST.md; inventory-diff.md",
        )
    if surf == "Installer / packaging surface: release packaging" and atomic.startswith("Platform-specific path"):
        return decision(
            "PASS",
            "The local macOS packaging path built a versioned tarball, checksum, and manifest entirely under the isolated audit directory.",
            "evidence/codex-not-run-phase/release-package/validation.json",
        )

    if surf == "Capability machinery: capability-scorer":
        return decision(
            "SKIPPED_NA",
            "The mapped implementation is `harness/hooks/claude/capability-scorer.sh`; this is a Claude-only surface and belongs in the excluded-scope ledger for the Codex-focused phase.",
            "evidence/codex-not-run-phase/remaining-inconclusive-blocker-classification.csv",
        )

    autosci_exact_pass = {
        "WF-0076-PIPELINE-STAGE-ADVANCEMENT-EXPLICIT-6C8A78": "Tracked exp-status tests directly asserted monitor invocation, persistent state reads, state normalization, and recorded advancement.",
        "WF-0144-GENERATED-CONFIGS-REFERENCE-VALID-29B0F3": "Tracked visualization tests generated workspace graph/config artifacts, asserted local projection paths, and kept serving behind the explicit flag boundary.",
        "WF-0184-PROMOTION-WRITEBACK-GATED-REQUIRES-213AFF": "Tracked promotion tests exercised satisfied-evidence promotion plus exact rollback/backup behavior; the gate matrix verified unapproved mutation remains blocked.",
        "WF-0210-PROPOSES-BOUNDED-CHANGES-RATIONALE-72DBD9": "The evolve-workflow bridge test directly emitted the workflow_evolution schema with reviewable bounded changes, rationale, and affected paths.",
        "WF-0221-SELECTED-FOUNDATIONS-MATCH-DOMAIN-7B3AB7": "Tracked prefill tests directly exercised catalog planning, duplicate filtering, supplied evidence, and approved application in a temporary wiki.",
        "WF-0224-ACTUAL-FOUNDATION-CREATION-REQUIRES-4DB694": "Wiki mutation runtime-proof tests directly verified completed approved writeback emits a proof manifest and incomplete writeback does not.",
        "WF-0248-REVIEWER-COMMENTS-ATOMIZED-CONCERN-698799": "Tracked rebuttal tests directly atomized reviewer inputs into concern records, including comma-separated review files.",
        "WF-0249-EACH-CONCERN-MAPS-EVIDENCE-02D494": "Tracked rebuttal tests directly mapped review findings to evidence/gap fields instead of silently dropping unmatched concerns.",
        "WF-0251-STRESS-TEST-PORTAL-SUBMISSION-6407FC": "Tracked submission-audit tests kept portal submission and runtime closure unclaimed until explicit audit evidence was present.",
        "WF-0254-BROWSER-PNG-RENDERING-APPROVAL-A01746": "Tracked poster/visualization tests verified the render/serve path stays blocked without approval and emits runtime proof when synthetically approved.",
        "WF-0283-SERVING-OPENING-BROWSER-APPROVAL-97C0A2": "Tracked visualization tests accepted the serve flag without execution, then required synthetic approval and runtime proof for the serving path.",
    }
    if fid in autosci_exact_pass:
        return decision(
            "PASS",
            autosci_exact_pass[fid],
            "evidence/codex-not-run-phase/autosci-shim-rerun-final-junit/codex-nr-0009.xml; evidence/codex-not-run-phase/audit-tests/gate-hitl-direct-contracts.junit.xml",
        )
    if fid == "WF-0041-FAILS-REPORTS-MISSING-STATE-38916C":
        return decision(
            "FAIL",
            "The direct missing-wiki `/check`-class probe returned an inconclusive summary but also created six workspace artifacts and reported a passed action, violating the no-hidden-success-artifact criterion.",
            "evidence/codex-not-run-phase/missing-wiki-direct-run.json",
        )

    cli_remediation = {
        "MISC-0077-COMMAND-PERFORMS-DOCUMENTED-BEHAVIOR-0537B7": (
            "FAIL",
            "The isolated `solar components list` command exited 0 but emitted no observable stdout or JSON, so the documented listing contract was not demonstrated.",
        ),
        "MISC-0079-FAILURE-RETURNS-NONZERO-EXPLICIT-3E9C15": (
            "PASS",
            "Invalid components usage returned a non-zero status and an explicit usage/remedy message in an isolated HOME.",
        ),
        "MISC-0080-COMMAND-SIDE-EFFECTS-SCOPED-272302": (
            "PASS",
            "The read-only components probes left the isolated HOME unchanged.",
        ),
        "MISC-0087-COMMAND-PERFORMS-DOCUMENTED-BEHAVIOR-35DEDE": (
            "PASS",
            "The isolated harness help route emitted its documented command surface.",
        ),
        "MISC-0089-FAILURE-RETURNS-NONZERO-EXPLICIT-158517": (
            "PASS",
            "An unsupported harness command returned a non-zero status and explicit guidance.",
        ),
        "MISC-0090-COMMAND-SIDE-EFFECTS-SCOPED-671843": (
            "PASS",
            "Harness help and invalid-command probes did not create or modify isolated runtime state.",
        ),
        "MISC-0107-COMMAND-PERFORMS-DOCUMENTED-BEHAVIOR-04A7DA": (
            "PASS",
            "`solar ui --once` deterministically reported the not-installed/manual-start state in an isolated HOME.",
        ),
        "MISC-0109-FAILURE-RETURNS-NONZERO-EXPLICIT-7AFF83": (
            "PASS",
            "An invalid UI option was rejected with a non-zero status and usage guidance.",
        ),
        "MISC-0110-COMMAND-SIDE-EFFECTS-SCOPED-DEBED6": (
            "PASS",
            "The UI once/error probes left the isolated HOME unchanged.",
        ),
    }
    if fid in cli_remediation:
        status, rationale = cli_remediation[fid]
        return decision(
            status,
            rationale,
            "evidence/codex-not-run-phase/audit-tests/cli-direct-contracts-remediation-final.junit.xml",
        )

    if surf.startswith("Bridge/route foundation:"):
        return decision(
            "PASS",
            "The isolated foundation contracts cross-checked all 28 route/binding records, exercised typed missing-route handling, bridge smoke/validation, and repeatable Codex skill projection.",
            "evidence/codex-not-run-phase/audit-tests/autosci-foundation-direct-contracts-final.junit.xml",
        )

    if surf.startswith("Knowledge ingestion workflow:"):
        command = surf.rsplit(" ", 1)[-1]
        evidence = "evidence/codex-not-run-phase/audit-tests/knowledge-remaining-direct-contracts-final.junit.xml"
        if command == "run-pipeline":
            return decision(
                "FAIL",
                "The direct local pipeline failed in the locked checkout: an unquoted repository path containing spaces broke semantic extraction and the pipeline then called an unavailable knowledge-health harness route.",
                evidence,
            )
        if command in {"dashboard", "drain-retry", "drain-skip", "process-queue", "status"} and atomic.startswith(
            ("Discovers candidate", "Queues documents")
        ):
            return decision(
                "SKIPPED_NA",
                f"The spreadsheet assigns `{atomic}` to `{command}`, but that command is not the discovery/queue entrypoint for this behavior; this is a stale taxonomy-to-entrypoint pairing, not an executable feature contract.",
                evidence + "; inventory-diff.md",
            )
        if command == "dashboard" and atomic.startswith("Processing emits"):
            return decision(
                "SKIPPED_NA",
                "The dashboard entrypoint renders status and does not process documents; the atomic row is a stale taxonomy-to-entrypoint pairing.",
                evidence + "; inventory-diff.md",
            )
        if command in {"drain-retry", "drain-skip"} and atomic.startswith("Status/report reflects"):
            return decision(
                "SKIPPED_NA",
                f"`{command}` drains a queue class and is not the status/report entrypoint; the atomic row is a stale taxonomy-to-entrypoint pairing.",
                evidence + "; inventory-diff.md",
            )
        knowledge_direct = {
            "coverage-report",
            "discover-sources",
            "import-legacy-extracted",
            "qmd-watermarks",
        }
        if command in knowledge_direct:
            return decision(
                "PASS",
                "The isolated dispatcher contract exercised this concrete command against a temporary registry and validated typed output plus the applicable discovery, provenance, idempotence, or report evidence.",
                evidence,
            )

    if surf.startswith("Knowledge QMD index workflow:"):
        return decision(
            "PASS",
            "Each QMD index command rejected malformed input with a non-zero status and usage evidence while the temporary registry bytes remained unchanged.",
            "evidence/codex-not-run-phase/audit-tests/knowledge-remaining-direct-contracts-final.junit.xml",
        )

    if surf.startswith("Capability machinery:"):
        evidence = "evidence/codex-not-run-phase/audit-tests/capability-plane-direct-contracts-final.junit.xml"
        if surf.startswith("Capability machinery: capability_registry"):
            return decision(
                "PASS",
                "The isolated registry contract directly exercised sync, list, successful/missing query, scorecard, and repeated-sync idempotence with typed JSON.",
                evidence,
            )
        if surf == "Capability machinery: capability_effects":
            return decision(
                "PASS",
                "The direct effects contract validated typed provider/capability evidence, a missing-sidecar failure, and byte-stable repeat execution.",
                evidence,
            )
        if surf == "Capability machinery: capability-prefix" and atomic.startswith("Performs documented"):
            return decision(
                "FAIL",
                "The tracked prefix-visibility contract fails because it invokes the removed `intent match` route; the locked intent gateway exposes capture/bind instead.",
                evidence,
            )
        if surf == "Capability machinery: capability_activation_proof" and atomic.startswith("Performs documented"):
            return decision(
                "FAIL",
                "`capability_activation_proof.py --help` ignored help semantics, executed the proof suite, wrote runtime/report state under the isolated HOME, and only 2 of 13 proof checks passed.",
                evidence,
            )
        if surf == "Capability machinery: capability_certification_suite":
            if atomic.startswith("Loads capability"):
                return decision(
                    "PASS",
                    "The fast suite parsed its configuration and produced JSON, Markdown, and evidence artifacts in the isolated directory.",
                    evidence,
                )
            if atomic.startswith("Performs documented"):
                return decision(
                    "FAIL",
                    "The fast certification suite produced artifacts but failed 5 of 10 blocking checks, including graph dispatcher, model-call runtime, capability-plane, expanded-plane, and Ruflo integration.",
                    evidence,
                )
        if surf == "Capability machinery: capability_fusion_benchmark":
            return decision(
                "PASS",
                "The isolated fusion benchmark parsed its configuration, emitted JSON/Markdown/evidence artifacts, and its fake-capability and unrelated-provider negative controls passed; separate benchmark threshold failures remain recorded against the action/result atoms.",
                evidence,
            )
        if surf == "Capability machinery: capability_inference enrich-graph" and atomic.startswith("Duplicate or stale"):
            return decision(
                "FAIL",
                "The direct enrich-graph test showed an explicit required-capability list was union-enriched with unrelated inferred capabilities, corrupting the caller-declared requirement set.",
                "evidence/codex-not-run-phase/audit-tests/benchmark-capability-direct-contracts.junit.xml",
            )
        if surf == "Capability machinery: capability_inference infer" and atomic.startswith("Duplicate or stale"):
            return decision(
                "PASS",
                "Direct inference fixtures returned typed missing-capability results without duplicating or mutating the source graph registry.",
                "evidence/codex-not-run-phase/audit-tests/benchmark-capability-direct-contracts.junit.xml",
            )

    if surf.startswith("Graph orchestration workflow:"):
        return decision(
            "PASS",
            "The isolated graph scheduler/dispatcher suites directly exercised validation, topology, readiness, batching, assignment, enqueue/drain, evaluator verdict, independent-review blocking, and graph-state preservation.",
            "evidence/codex-not-run-phase/remediation-shell-contract-results.csv",
        )

    if surf.startswith("Knowledge ingestion workflow:"):
        command = surf.rsplit(" ", 1)[-1]
        if command in {"discover-raw", "discover-vault", "submit-event"}:
            return decision(
                "PASS",
                "The isolated knowledge-ingest dispatcher contract directly verified this command against a temporary registry, including origin recording and idempotent queue/registry behavior.",
                "evidence/codex-not-run-phase/remediation-shell-contract-results.csv",
            )

    if fid in {"WF-0572-LOADS-HEALTH-SOURCES-REPORTS-4328AC", "WF-0575-LOADS-HEALTH-SOURCES-REPORTS-8D1644"}:
        return decision(
            "PASS",
            "The isolated health suite loaded a temporary registry and directly produced audit/circuit health evidence.",
            "evidence/codex-not-run-phase/remediation-shell-contract-results.csv",
        )
    if fid == "WF-0577-DOES-NOT-MUTATE-UNLESS-A2EB53":
        return decision(
            "FAIL",
            "The direct circuit-check fixture wrote the pause-state file even though this atomic criterion requires no mutation outside an explicit approved repair mode.",
            "evidence/codex-not-run-phase/remediation-shell-contract-results.csv",
        )

    benchmark_pass = {
        "WF-0398-REPORT-RECORDS-TASK-SOLVER-2ECC82",
        "WF-0399-FAILURE-EXPLICIT-PRESERVES-LOGS-E1AFF0",
        "WF-0401-EXECUTES-PLANS-BENCHMARK-ISOLATED-005506",
        "WF-0402-REPORT-RECORDS-TASK-SOLVER-0E30DF",
        "WF-0403-FAILURE-EXPLICIT-PRESERVES-LOGS-F1C3FD",
        "WF-0406-REPORT-RECORDS-TASK-SOLVER-1E0138",
        "WF-0407-FAILURE-EXPLICIT-PRESERVES-LOGS-9FE246",
        "WF-0409-EXECUTES-PLANS-BENCHMARK-ISOLATED-3F732E",
        "WF-0411-FAILURE-EXPLICIT-PRESERVES-LOGS-66514F",
        "WF-0413-EXECUTES-PLANS-BENCHMARK-ISOLATED-CF3966",
        "WF-0414-REPORT-RECORDS-TASK-SOLVER-68597E",
        "WF-0415-FAILURE-EXPLICIT-PRESERVES-LOGS-DC1F9A",
    }
    if fid in benchmark_pass:
        return decision(
            "PASS",
            "Direct benchmark schema/adapter/solver tests validated isolated planning or execution evidence, report fields, redaction, and explicit failure handling.",
            "evidence/codex-not-run-phase/audit-tests/benchmark-capability-direct-contracts.junit.xml",
        )
    if fid in {"WF-0391-FAILURE-EXPLICIT-PRESERVES-LOGS-9009F3", "WF-0405-EXECUTES-PLANS-BENCHMARK-ISOLATED-31810F"}:
        return decision(
            "FAIL",
            "A direct Terminal-Bench adapter assertion failed: prerequisite reporting drifted and an empty missing-prerequisite dry-run returned pending instead of ok.",
            "evidence/codex-not-run-phase/audit-tests/benchmark-capability-direct-contracts.junit.xml",
        )

    if fid in {"FD-0598-LOADS-CAPABILITY-CONFIG-REGISTRY-C396ED", "FD-0599-PERFORMS-DOCUMENTED-LIST-QUERY-1D051E"}:
        return decision(
            "PASS",
            "Direct capability-inference tests verified missing capabilities are inferred from the locked checkout's registry and graph inputs.",
            "evidence/codex-not-run-phase/audit-tests/benchmark-capability-direct-contracts.junit.xml",
        )
    if fid == "FD-0595-PERFORMS-DOCUMENTED-LIST-QUERY-ED4D7C":
        return decision(
            "FAIL",
            "The direct enrich-graph test showed explicitly declared required capabilities were union-enriched with unrelated capabilities.",
            "evidence/codex-not-run-phase/audit-tests/benchmark-capability-direct-contracts.junit.xml",
        )

    if surf.startswith("Research/source ingestion workflow:"):
        if "daily_arxiv recommend-llm" in surf:
            return decision(
                "SKIPPED_ENV",
                "This command requires an approved model/provider runtime; only local prepare/finalize/digest paths were exercised in the offline phase.",
                "evidence/codex-not-run-phase/autosci-shim-rerun-final-junit/codex-nr-0009.xml",
            )
        if "daily_arxiv" in surf:
            return decision(
                "PASS",
                "Existing direct AutoSci shim tests exercised local feed config, prepare, finalize, digest, evidence handoff, and explicit management states without live providers.",
                "evidence/codex-not-run-phase/autosci-shim-rerun-final-junit/codex-nr-0009.xml",
            )
        if "fetch_s2" in surf or "fetch_deepxiv" in surf or "fetch_wikipedia" in surf:
            if atomic.startswith("Output includes source refs"):
                return decision(
                    "FAIL",
                    "Direct fixture-provider output omitted at least one required query/parameter, retrieval timestamp, or limitations field.",
                    "evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml",
                )
            return decision(
                "PASS",
                "Direct provider fixtures and forced-offline executions validated supported input parsing, normalization, and explicit non-fabricating failure behavior.",
                "evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml",
            )
        if "fetch_arxiv" in surf:
            if atomic.startswith("Output includes source refs") or atomic.startswith("Errors are propagated"):
                return decision(
                    "FAIL",
                    "The direct arXiv fixture showed the tool returns a bare list and collapses provider failure to an empty successful result instead of typed failed/inconclusive evidence with limitations.",
                    "evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml",
                )
            return decision(
                "PASS",
                "The direct arXiv fixture validated supported inputs, feed parsing, deduplication, source URL, category, authors, and published timestamp.",
                "evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml",
            )
        if "rasterize_latex" in surf:
            if atomic.startswith("Accepts provider") or atomic.startswith("Errors are propagated"):
                return decision(
                    "PASS",
                    "The direct CLI contract validated required input handling and a no-write failure on missing snippet input.",
                    "evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml",
                )
            return decision(
                "SKIPPED_ENV",
                "A successful rasterization requires an installed LaTeX/PNG toolchain; only deterministic input and failure contracts were run.",
                "evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml",
            )

    if surf.startswith("Skill/integration surface:"):
        provider = surf.removeprefix("Skill/integration surface: ")
        gemini_evidence = "evidence/codex-not-run-phase/audit-tests/gemini-integration-direct-contracts.junit.xml"
        if provider == "Mempalace semantic memory MCP server":
            return decision(
                "SKIPPED_ENV",
                "The Mempalace server cannot import in the locked offline environment because its ChromaDB dependency is unavailable. Installing dependencies was outside this audit phase and no MCP behavior is claimed from static discovery.",
                "evidence/codex-not-run-phase/audit-tests/installer-component-contracts-remediated.junit.xml",
            )
        if provider == "Apple Notes ingest":
            return decision(
                "SKIPPED_ENV",
                "A behavioral Apple Notes ingest test requires a real macOS Notes database and Automation/privacy authorization. The audit did not access the user's Notes data.",
                "evidence/codex-not-run-phase/remaining-inconclusive-blocker-classification.csv",
            )
        if provider == "social browser backend":
            social_evidence = "evidence/codex-not-run-phase/audit-tests/social-browser-direct-contracts.junit.xml"
            if atomic.startswith(("Integration/skill", "Handles supported")):
                return decision(
                    "PASS",
                    "Direct backend/lease/selector tests exercised configuration discovery, supported request routing, retry budgets, and typed invalid/offline states.",
                    social_evidence,
                )
            if atomic.startswith("Unavailable external provider"):
                return decision(
                    "PASS",
                    "Forced-unavailable backend tests returned typed unavailable/fallback state rather than fabricated browser output.",
                    social_evidence,
                )
            if atomic.startswith("Any external write"):
                return decision(
                    "PASS",
                    "The isolated lease/selector tests verified no real browser/profile was opened and side-effect execution remained behind runtime approval/lease boundaries.",
                    social_evidence + "; evidence/codex-not-run-phase/audit-tests/gate-hitl-direct-contracts.junit.xml",
                )
            return decision(
                "SKIPPED_ENV",
                "Normalized live browser provenance/limitations requires an approved real browser profile/provider session; fixture-only backend evidence is not full parity.",
                social_evidence,
            )
        if provider == "ChatGPT conversation ingest":
            chatgpt_evidence = "evidence/codex-not-run-phase/infrastructure-rerun-results.tsv"
            if atomic.startswith("Handles supported"):
                return decision(
                    "PASS",
                    "The isolated tracked ingest contract parsed a local export fixture and rejected malformed input without accessing a live ChatGPT account.",
                    chatgpt_evidence,
                )
            if atomic.startswith("Unavailable external provider"):
                return decision(
                    "SKIPPED_NA",
                    "This entrypoint ingests a caller-supplied local export and does not require an external provider at execution time.",
                    chatgpt_evidence,
                )
            if atomic.startswith("Any external write"):
                return decision(
                    "PASS",
                    "The ingest contract wrote only caller-selected temporary knowledge paths and preserved source export bytes.",
                    chatgpt_evidence,
                )
        if provider == "Gemini adapter":
            if atomic.startswith("Integration/skill"):
                return decision(
                    "PASS",
                    "The locked adapter imports successfully and its tracked integration tests discover the supported adapter surface.",
                    gemini_evidence,
                )
            if atomic.startswith("Unavailable external provider"):
                return decision(
                    "SKIPPED_ENV",
                    "A real Gemini provider/session was intentionally unavailable in the offline phase; live adapter parity needs credentials and network approval.",
                    gemini_evidence,
                )
            if atomic.startswith("Any external write"):
                return decision(
                    "SKIPPED_NA",
                    "The adapter path under test invokes a provider and writes only caller-selected local result files; it exposes no remote write/send mutation action.",
                    gemini_evidence,
                )
        if provider == "Gemini enhanced search":
            if atomic.startswith("Integration/skill"):
                return decision(
                    "PASS",
                    "Tracked enhanced-search modules imported and their parser, normalization, pipeline, and task-operator contracts executed in the locked checkout.",
                    gemini_evidence,
                )
            if atomic.startswith("Handles supported"):
                return decision(
                    "FAIL",
                    "The adapter forwarding contract fails because `harness/lib/gemini_adapter.py` does not expose the expected `gemini_enhanced_search_main` symbol.",
                    gemini_evidence,
                )
            if atomic.startswith("Output includes"):
                return decision(
                    "FAIL",
                    "The normalized pipeline output includes citations and provider metadata but does not include the required limitations field.",
                    gemini_evidence,
                )
            if atomic.startswith("Unavailable external provider"):
                return decision(
                    "PASS",
                    "The direct-rewrite requirement and failure flow-control tests produced explicit errors/cooldown state instead of fabricated research output.",
                    gemini_evidence,
                )
            if atomic.startswith("Any external write"):
                return decision(
                    "SKIPPED_NA",
                    "The enhanced-search operator writes only caller-scoped local request/result artifacts and exposes no remote mutation or send action.",
                    gemini_evidence,
                )
        if provider == "Gemini Deep Research capability":
            if atomic.startswith("Integration/skill"):
                return decision(
                    "PASS",
                    "The Gemini Deep Research operator and capability are discoverable in the tracked checkout and their local request-construction surface imports successfully.",
                    gemini_evidence,
                )
            if atomic.startswith("Unavailable external provider"):
                return decision(
                    "SKIPPED_ENV",
                    "Live Gemini Deep Research requires an approved provider/browser session and was not claimed from fixture-only evidence.",
                    gemini_evidence,
                )
            if atomic.startswith("Any external write"):
                return decision(
                    "SKIPPED_NA",
                    "The capability produces caller-scoped local evidence and does not expose a remote write/send operation in the audited entrypoint.",
                    gemini_evidence,
                )
        if provider in {"Semantic Scholar fetch", "DeepXiv fetch"}:
            if atomic.startswith("Any external write"):
                return decision("SKIPPED_NA", "The audited helper is read-only and exposes no external write/browser/send operation.", "evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml")
            return decision("PASS", "Direct fixture and offline tests validated discovery/config, input, normalized provenance, limitations, and explicit unavailable-provider behavior.", "evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml")
        if provider == "Wikipedia fetch":
            if atomic.startswith("Output includes"):
                return decision("FAIL", "Completed Wikipedia provider evidence contains a source URL but omits the required retrieval timestamp and limitations field.", "evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml")
            if atomic.startswith("Any external write"):
                return decision("SKIPPED_NA", "The Wikipedia helper is read-only and exposes no external mutation path.", "evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml")
            return decision("PASS", "Direct fixture and forced-provider-failure tests validated supported inputs and explicit typed failure output.", "evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml")
        if provider == "arXiv fetch / daily arXiv":
            if atomic.startswith("Output includes") or atomic.startswith("Unavailable external provider"):
                return decision("FAIL", "The arXiv fetch helper returns a bare list and hides provider failure as an empty successful output, without typed limitations.", "evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml")
            if atomic.startswith("Any external write"):
                return decision("PASS", "The isolated gate matrix directly verified email/send and other high-risk side effects remain blocked without explicit opt-in.", "evidence/codex-not-run-phase/audit-tests/gate-hitl-direct-contracts.junit.xml")
            return decision("PASS", "Direct local feed fixtures verified supported input, normalized paper fields, deduplication, and source timestamps.", "evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml")
        if provider == "LaTeX rasterization / paper compile support":
            if atomic.startswith("Integration/skill") or atomic.startswith("Handles supported"):
                return decision("PASS", "Direct CLI parsing and invalid-input contracts were executed without writing outside the fixture directory.", "evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml")
            if atomic.startswith("Any external write"):
                return decision("PASS", "The isolated gate matrix verified compile/render side effects are blocked or synthetically approved according to the configured mode.", "evidence/codex-not-run-phase/audit-tests/gate-hitl-direct-contracts.junit.xml")
            return decision("SKIPPED_ENV", "Successful TeX-to-PNG output requires the external LaTeX/raster toolchain and was not claimed from fixture-only evidence.", "evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml")

    if surf.startswith("CLI lifecycle command:"):
        command = surf.removeprefix("CLI lifecycle command: ")
        if command in {"version", "status", "doctor", "backup", "restore", "uninstall", "update", "repair"}:
            evidence = "evidence/codex-not-run-phase/audit-tests/cli-direct-contracts-final.junit.xml"
            if command in {"update", "repair", "uninstall"}:
                evidence += "; evidence/codex-not-run-phase/remediation-shell-contract-results.csv"
            return decision("PASS", "The lifecycle command was exercised in an isolated HOME with direct output, failure, round-trip or no-mutation assertions appropriate to the atomic contract.", evidence)

    if surf.startswith("Installable component:"):
        component = surf.removeprefix("Installable component: ")
        if component in {"harness", "autosci"}:
            return decision("PASS", "Isolated installer, AutoSci closure, and minimal smoke contracts verified selection, receipt/layout, repair and uninstall preservation.", "evidence/codex-not-run-phase/audit-tests/installer-component-contracts-offline-rerun.junit.xml")
        return decision("SKIPPED_ENV", "Full component installation requires unavailable cached Bun/Python dependencies or platform service support; no live dependency download was allowed.", "evidence/codex-not-run-phase/audit-tests/installer-component-contracts-remediated.junit.xml")

    if surf.startswith("Installer / packaging surface:"):
        if "Windows" in surf or "install.ps1" in surf:
            return decision("SKIPPED_ENV", "Windows/WSL2 execution requires the target platform; only static workflow contracts were available on macOS.", "evidence/codex-not-run-phase/audit-tests/ci-workflow-contracts.junit.xml")
        if any(marker in surf for marker in ("install.sh", "install receipt", "component selection", "generated component docs", "macOS install support", "Linux install support", "get-solar.sh")):
            return decision("PASS", "Isolated installer-contract and minimal-smoke suites directly validated the local install/receipt/component/layout/idempotence/uninstall contract.", "evidence/codex-not-run-phase/audit-tests/installer-component-contracts-offline-rerun.junit.xml")

    if surf.startswith("Desktop surface:") or surf.startswith("Desktop package script:") or surf.startswith("UI surface: React status dashboard"):
        return decision("SKIPPED_ENV", "Renderer/build execution remains blocked by unavailable local Playwright/browser or renderer dependencies; static package-script discovery alone is not counted as behavioral PASS.", "evidence/codex-not-run-phase/desktop-static-logs")

    if surf.startswith("Browser workflow: social browser backend CLI"):
        if atomic.startswith("Retries/fails") or atomic.startswith("Loads or reports"):
            return decision("PASS", "Direct social-browser lease/CLI tests validated profile-state reporting, retry budgets, release behavior and typed status output.", "evidence/codex-not-run-phase/audit-tests/social-browser-direct-contracts.junit.xml")

    # Resolve the 26 prior NOT_RUN rows instead of leaving silent gates.
    if fid == "WF-0267-RESET-RESULT-REPORTS-CHANGED-E66455":
        return decision("PASS", "The existing isolated approved-reset testcase directly verified scoped mutation proofs and changed-path reporting.", "evidence/codex-not-run-phase/autosci-shim-rerun-final-junit/codex-nr-0009.xml")
    if fid == "WF-0279-FAILS-REPORTS-MISSING-STATE-8DE992":
        return decision("FAIL", "A direct missing-wiki run returned an inconclusive summary but also reported a passed action and created six workspace artifacts, violating the no-hidden-success-artifact criterion.", "evidence/codex-not-run-phase/missing-wiki-direct-run.json")
    if row.get("test_result_status") == "NOT_RUN" and surf.startswith("Skill/integration surface:"):
        if atomic.startswith("Integration/skill"):
            if "skills-obsidian" in surf:
                return decision("FAIL", "The shipped Obsidian skill manifest contains a developer-specific /home/ruslan path and is not portable.", "evidence/codex-not-run-phase/audit-tests/integration-discovery-direct-contracts.junit.xml")
            if "Mempalace" in surf:
                return decision("SKIPPED_ENV", "The MCP server cannot import because chromadb is unavailable; dependency installation was not authorized in this offline phase.", "evidence/codex-not-run-phase/audit-tests/installer-component-contracts-remediated.junit.xml")
            return decision("PASS", "The tracked skill/adapter manifest and isolated doctor/config probe directly validated discoverability and explicit missing-config guidance.", "evidence/codex-not-run-phase/audit-tests/integration-discovery-direct-contracts.junit.xml")
        if "Obsidian wiki integration" in surf and atomic.startswith("Handles supported"):
            return decision("FAIL", "The direct missing-vault probe emitted an error JSON but exited 0, so unsupported/missing input is not rejected by process status.", "evidence/codex-not-run-phase/audit-tests/integration-discovery-direct-contracts.junit.xml")
        return decision("SKIPPED_ENV", "Producing a real integration output requires an approved live app/provider/browser/vault session; discovery/config was tested but fixture-only evidence is not claimed as live output parity.", "evidence/codex-not-run-phase/audit-tests/integration-discovery-direct-contracts.junit.xml")

    return None


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    phase_path = root / "evidence/codex-not-run-phase/codex-not-run-feature-results.csv"
    main_path = root / "feature-results.csv"
    for source, backup in (
        (phase_path, phase_path.with_name("codex-not-run-feature-results.pre-remediation.csv")),
        (main_path, main_path.with_name("feature-results.pre-direct-remediation.csv")),
    ):
        if not backup.exists():
            shutil.copy2(source, backup)

    direct = {row["feature_id"]: row for row in read_csv(root / "evidence/codex-not-run-phase/direct-existing-evidence-adjudication.csv")}
    phase_rows = read_csv(phase_path)
    prior_decision_path = root / "evidence/codex-not-run-phase/remediation-feature-decisions.csv"
    prior_decisions = read_csv(prior_decision_path) if prior_decision_path.exists() else []
    decisions: list[dict[str, str]] = []
    force_redecision_ids = {
        "WF-0264-MISSING-INVALID-SCOPE-REJECTED-E14DB0",
        "WF-0265-PLAN-GENERATED-WITHOUT-MUTATION-38B119",
        "WF-0277-DRY-RUN-PROPOSES-FIXES-6FC1FB",
        "WF-0006-CLEAN-START-RESETS-STALE-840E0D",
        "WF-0013-PLAN-VERDICT-UPDATES-SPRINT-6F9A1D",
        "WF-0033-MUTATION-SYNC-EXPLICIT-PRESERVES-ACE99F",
        "WF-0204-APPROVED-WRITEBACK-UPDATES-LINKED-C80F8A",
        "WF-0225-PROPOSES-APPLIES-SOURCE-ADDITION-B13BB8",
        "WF-0226-EDITS-ONLY-REQUESTED-PAGE-8EFA8E",
        "WF-0227-REQUIRES-EXPLICIT-CONFIRMATION-APPROVAL-FDDEE7",
        "WF-0228-NEW-RAW-SOURCE-ADDITION-46F58A",
        "WF-0239-APPROVED-WRITEBACK-RECORDS-PILOT-5B670A",
        "WF-0247-ARCHIVAL-WRITEBACK-EXPLICIT-APPROVED-0CA46A",
        "WF-0266-EXECUTION-REQUIRES-EXPLICIT-APPROVAL-9BF203",
        "MISC-0303-ANY-EXTERNAL-WRITE-BROWSER-1F66D8",
        "MISC-0308-ANY-EXTERNAL-WRITE-BROWSER-F66FD9",
        "MISC-0313-ANY-EXTERNAL-WRITE-BROWSER-AEAD47",
        "MISC-0318-ANY-EXTERNAL-WRITE-BROWSER-DD521D",
        "MISC-0328-ANY-EXTERNAL-WRITE-BROWSER-A76165",
        "MISC-0333-ANY-EXTERNAL-WRITE-BROWSER-2338B6",
        "MISC-0338-ANY-EXTERNAL-WRITE-BROWSER-4CE79F",
        "MISC-0348-ANY-EXTERNAL-WRITE-BROWSER-417B43",
        "WF-0117-RESPONSES-AVOID-FABRICATED-DATA-AA7E7B",
        "WF-0134-SUGGESTIONS-CONCRETE-DO-NOT-06EE1A",
        "WF-0147-EACH-SEED-MODE-YIELDS-3735D8",
        "WF-0158-ANALYSIS-FIELDS-POPULATED-LIMITATIONS-AF402A",
        "WF-0159-EVERY-ANALYTICAL-STATEMENT-SOURCE-F49715",
        "WF-0172-RETURNS-NOT-TESTABLE-INCOMPLETE-71526E",
        "WF-0176-REPORTS-INCOMPLETE-METHOD-EVIDENCE-E24804",
        "WF-0177-GENERATED-CANDIDATES-CITE-SOURCE-FA4851",
        "WF-0191-REVIEW-EVIDENCE-ATTACHED-MARKED-270248",
        "WF-0203-REVIEW-LLM-DISAGREEMENT-RECORDED-885CB3",
        "WF-0243-REVIEW-EVIDENCE-ATTACHED-ABSENT-1BA315",
        "WF-0250-RESPONSES-AVOID-FABRICATED-DATA-DFB9AB",
        "WF-0287-SUGGESTIONS-CONCRETE-DO-NOT-6A47C4",
        "WF-0422-CAPTURED-OUTPUT-HAS-SOURCE-1CDA2F",
        "WF-0423-RETRIES-FAILS-CHECKPOINTED-STATE-089989",
        "WF-0425-RUNS-RECORDS-BROWSER-AUTOMATION-FAA4C2",
        "WF-0426-CAPTURED-OUTPUT-HAS-SOURCE-6F503B",
        "MISC-0300-HANDLES-SUPPORTED-SOURCE-REQUEST-1A39A8",
        "MISC-0302-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-6ED8E4",
        "MISC-0305-HANDLES-SUPPORTED-SOURCE-REQUEST-0F0924",
        "MISC-0307-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-5310ED",
        "MISC-0310-HANDLES-SUPPORTED-SOURCE-REQUEST-28972A",
        "MISC-0312-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-CBB1BC",
        "MISC-0315-HANDLES-SUPPORTED-SOURCE-REQUEST-2B0A68",
        "MISC-0317-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-5022AD",
        "MISC-0322-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-E5C821",
        "MISC-0327-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-AF98BB",
        "MISC-0330-HANDLES-SUPPORTED-SOURCE-REQUEST-717B2C",
        "MISC-0332-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-83BF1C",
        "MISC-0335-HANDLES-SUPPORTED-SOURCE-REQUEST-24C223",
        "MISC-0337-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-2C2F4E",
        "MISC-0347-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-89ACF0",
        "MISC-0375-HANDLES-SUPPORTED-SOURCE-REQUEST-5089BE",
    }
    for row in phase_rows:
        if row["test_result_status"] not in {"INCONCLUSIVE_EXPECTED", "NOT_RUN"} and row["feature_id"] not in force_redecision_ids:
            continue
        result = decide(row, direct)
        if not result:
            continue
        status, rationale, evidence = result
        prior = row["test_result_status"]
        row["test_result_status"] = status
        row["evidence_strength"] = "direct" if status in {"PASS", "FAIL"} else "environment_or_scope"
        row["result_rationale"] = rationale
        row["execution_evidence"] = evidence.strip("; ")
        decisions.append(
            {
                "feature_id": row["feature_id"],
                "feature_path": row["feature_path"],
                "prior_status": prior,
                "remediated_status": status,
                "rationale": rationale,
                "execution_evidence": row["execution_evidence"],
            }
        )
    write_csv(phase_path, phase_rows)

    decision_by_id = {row["feature_id"]: row for row in decisions}
    phase_by_id = {row["feature_id"]: row for row in phase_rows}
    main_rows = read_csv(main_path)
    for row in main_rows:
        remediated = decision_by_id.get(row["feature_id"])
        if not remediated:
            continue
        phase = phase_by_id[row["feature_id"]]
        row["final_result_status"] = remediated["remediated_status"]
        row["result_rationale"] = remediated["rationale"]
        row["execution_evidence"] = remediated["execution_evidence"]
        if remediated["remediated_status"] in {"PASS", "FAIL"}:
            row["coverage_status"] = "direct"
        row["mapping_confidence"] = "high"
        row["eligible_phase_execution_result"] = remediated["remediated_status"]
        row["eligible_phase_evidence"] = remediated["execution_evidence"]
        row["eligible_phase_selected_testcases"] = phase.get("selected_testcases", "")
    write_csv(main_path, main_rows)

    out = root / "evidence/codex-not-run-phase"
    combined = {row["feature_id"]: row for row in prior_decisions}
    combined.update({row["feature_id"]: row for row in decisions})
    all_decisions = list(combined.values())
    write_csv(out / "remediation-feature-decisions.csv", all_decisions)
    summary = {
        "schema": "qa.codex_not_run_remediation.v1",
        "decision_count": len(all_decisions),
        "decision_status_counts": dict(sorted(Counter(row["remediated_status"] for row in all_decisions).items())),
        "phase_status_counts": dict(sorted(Counter(row["test_result_status"] for row in phase_rows).items())),
        "main_status_counts": dict(sorted(Counter(row["final_result_status"] for row in main_rows).items())),
    }
    (out / "remediation-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
