from __future__ import annotations

import json
from pathlib import Path

from evidence import JourneyRecorder
from journey_runner import (
    action_evidence,
    run_autosci,
    runtime_evidence,
    write_code_evidence,
    write_experiment_assets,
    write_research_claims,
)


def test_p22_j08_claim_verification(repo_root: Path, tmp_path: Path, phase22_python: str) -> None:
    rec = JourneyRecorder(repo_root, "P22-J08")
    sandbox = tmp_path / "p22-j08"
    assets = write_experiment_assets(sandbox / "experiment", phase22_python)
    proc = rec.run(
        "local-python-experiment",
        [phase22_python, str(assets["runner"]), str(assets["data"]), str(assets["result"])],
        cwd=repo_root,
        timeout=60,
    )
    result_payload = json.loads(assets["result"].read_text(encoding="utf-8")) if assets["result"].exists() else {}
    runtime_path = runtime_evidence(sandbox / "experiment" / "runtime-evidence.json", proc.args, assets["result"], result_payload)
    exp_run, _ = run_autosci(
        rec,
        sandbox,
        "exp-run",
        [
            "phase22-j08-local",
            "--env",
            "local",
            "--approval-ref",
            "phase22-local-approval",
            "--allowlist-evidence",
            str(assets["allowlist"]),
            "--runtime-evidence",
            str(runtime_path),
            "--before-artifact",
            str(assets["data"]),
            "--after-artifact",
            str(assets["result"]),
            "--run-id",
            "p22-j08-exp-run",
        ],
        timeout=90,
    )
    exp_result_ev = action_evidence(exp_run, "run_experiment")
    claims = write_research_claims(
        sandbox / "claims.json",
        [
            {
                "claim_id": "claim-supported",
                "text": "The normalization variant improves exact-match accuracy by at least 20 percentage points on the local dataset.",
                "source_anchor": "phase22-local-experiment#results",
                "testability": "testable",
                "verification_status": "unverified",
                "evidence_ids": ["claim:phase22-supported"],
            },
            {
                "claim_id": "claim-overbroad",
                "text": "The method reaches 100% accuracy on all inputs and all environments.",
                "source_anchor": "phase22-local-experiment#limitations",
                "testability": "testable",
                "verification_status": "unverified",
                "evidence_ids": ["claim:phase22-overbroad"],
            },
        ],
        task_id="phase22-j08-claims",
    )
    code_a = write_code_evidence(sandbox / "code-supported.json", claim_id="claim-supported", files=[str(assets["runner"])])
    code_b = write_code_evidence(sandbox / "code-overbroad.json", claim_id="claim-overbroad", files=[str(assets["runner"])])
    rec.add_artifact(claims, "schema_valid_research_claims")
    rec.add_artifact(code_a, "supported_code_evidence")
    rec.add_artifact(code_b, "overbroad_code_evidence")
    if exp_result_ev:
        rec.add_artifact(exp_result_ev, "experiment_result_evidence")
    verify_a, _ = run_autosci(
        rec,
        sandbox,
        "exp-eval",
        [
            "claim-supported",
            "--experiment-result-evidence",
            str(exp_result_ev),
            "--claims-evidence",
            str(claims),
            "--code-evidence",
            str(code_a),
            "--run-id",
            "p22-j08-claim-a",
        ],
        timeout=90,
    )
    verify_b, _ = run_autosci(
        rec,
        sandbox,
        "exp-eval",
        [
            "claim-overbroad",
            "--experiment-result-evidence",
            str(exp_result_ev),
            "--claims-evidence",
            str(claims),
            "--code-evidence",
            str(code_b),
            "--run-id",
            "p22-j08-claim-b",
        ],
        timeout=90,
    )
    ev_a = action_evidence(verify_a, "verify_claim")
    ev_b = action_evidence(verify_b, "verify_claim")
    if ev_a:
        rec.add_artifact(ev_a, "supported_claim_verdict")
    if ev_b:
        rec.add_artifact(ev_b, "overbroad_claim_verdict")
    rec.add_assertion("experiment_result_available", exp_result_ev is not None, exp_run.get("_error"))
    rec.add_assertion("supported_claim_verified", ev_a is not None, verify_a.get("_error"))
    rec.add_assertion("overbroad_claim_verified", ev_b is not None, verify_b.get("_error"))
    verdict_a = None
    verdict_b = None
    if ev_a:
        verdict_a = json.loads(ev_a.read_text(encoding="utf-8")).get("outputs", {}).get("verdicts", [{}])[0].get("verdict")
        rec.add_assertion("supported_claim_supported", verdict_a == "supported", verdict_a)
    if ev_b:
        verdict_b = json.loads(ev_b.read_text(encoding="utf-8"))
        verdict_b_value = verdict_b.get("outputs", {}).get("verdicts", [{}])[0].get("verdict")
        rec.add_assertion("overbroad_claim_not_supported", verdict_b_value in {"not_supported", "inconclusive", "partially_supported"}, verdict_b_value)
        rec.add_assertion("supported_and_overbroad_verdicts_differ", verdict_a != verdict_b_value, {"supported": verdict_a, "overbroad": verdict_b_value})
    rec.add_l2("Workflow", "Claim & Acceptance-Criteria Comparison", "schema-valid supported and overbroad claims were checked through exp-eval", ev_a or rec.run_dir, "partial")
    limitations = []
    if not all(item["passed"] for item in rec.assertions):
        limitations.append(
            "Current exp-eval evidence does not distinguish the supported threshold claim from the deliberately overbroad all-inputs/all-environments claim."
        )
    rec.finalize("PASS" if all(item["passed"] for item in rec.assertions) else "FAIL", limitations=limitations)
