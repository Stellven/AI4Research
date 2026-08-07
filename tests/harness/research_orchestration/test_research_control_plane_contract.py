from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = (Path(__file__).resolve().parents[3] / 'harness')
BRIDGE = ROOT / "plugins" / "autosci" / "bin" / "autosci_bridge.py"
PARITY_FIXTURE = (Path(__file__).resolve().parents[3] / 'tests' / 'harness' / 'research_orchestration') / "fixtures" / "upstream_research_parity_contracts.json"
UPSTREAM_RUNNER = ROOT / "tools" / "autosci_upstream_parity.py"


def _run_research_cli(tmp_path: Path, *args: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(BRIDGE), "research", *args],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    assert proc.stdout, proc.stderr
    return proc.returncode, json.loads(proc.stdout)


def _contract(payload: dict) -> dict:
    path = Path(payload["task_contract_path"])
    assert path.is_file()
    return json.loads(path.read_text(encoding="utf-8"))


def test_production_entrypoint_preserves_full_prompt_url_language_format_and_constraints(tmp_path: Path) -> None:
    prompt = (
        "Analyze https://example.org/autosci-control-plane and produce a Chinese Markdown report with "
        "at least 4 traceable sources. Separate claims, evidence, and inference. "
        "Keep this sentinel: FULL_PROMPT_SENTINEL_R1_0123456789."
    )

    code, payload = _run_research_cli(
        tmp_path,
        "--prompt",
        prompt,
        "--run-id",
        "r1-url-contract",
        "--artifact-root",
        str(tmp_path),
        "--max-steps",
        "1",
    )

    assert code == 0
    assert payload["prompt"] == prompt
    assert payload["route"]["seed_kind"] == "url"
    assert payload["route"]["workflow_kind"] == "research_synthesis"
    assert payload["route"]["start_stage"] == "web_fetch"
    contract = _contract(payload)
    assert contract["user_intent"] == prompt
    assert contract["constraints"]["request_capture"]["raw_prompt"] == prompt
    assert contract["constraints"]["request_capture"]["raw_prompt_length_chars"] == len(prompt)
    assert contract["constraints"]["user_constraints"]["detected_urls"] == [
        "https://example.org/autosci-control-plane"
    ]
    assert contract["deliverable"]["language"] == "zh-CN"
    assert contract["deliverable"]["format"] == "markdown"
    assert contract["constraints"]["user_constraints"]["minimum_traceable_sources"] == 4
    assert contract["constraints"]["user_constraints"]["claim_evidence_separation_required"] is True


def test_production_entrypoint_ambiguous_request_returns_clarification_gate(tmp_path: Path) -> None:
    code, payload = _run_research_cli(
        tmp_path,
        "--prompt",
        "Research better agent memory",
        "--run-id",
        "r1-ambiguous",
        "--artifact-root",
        str(tmp_path),
        "--max-steps",
        "1",
    )

    assert code == 0
    assert payload["final_status"] == "awaiting_human"
    assert payload["current_blockers"][0]["blocker_id"] == "research_readiness_needs_clarification"
    contract = _contract(payload)
    gate = contract["constraints"]["readiness_gate"]
    assert gate["status"] == "needs_clarification"
    assert "research_goal_or_acceptance" in gate["missing_core_requirements"]
    assert gate["questions"]


def test_same_input_upstream_fixture_vs_solar_production_entrypoint_parity(tmp_path: Path) -> None:
    fixture = json.loads(PARITY_FIXTURE.read_text(encoding="utf-8"))
    pdf = ROOT / "tests" / "research_orchestration" / "fixtures" / "phase5" / "seed_portability" / "local_pdf_synthesis_seed.pdf"

    static_extra_args = {
        "topic-survey": [],
        "url-report": [],
        "pdf-ingest": ["--source", str(pdf)],
        "evidence-resume": ["--run-mode", "import_evidence"],
    }
    expected_start = {
        "topic-survey": "source_discovery",
        "url-report": "web_fetch",
        "pdf-ingest": "paper_ingest",
        "evidence-resume": "evidence_import",
    }

    for index, case in enumerate(fixture["cases"], start=1):
        case_id = case["case_id"]
        artifact_root = tmp_path / case_id
        extra_args = list(static_extra_args[case_id])
        if case_id == "evidence-resume":
            evidence = artifact_root / "prior-evidence.json"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text('{"schema":"external.test.v1","summary":"prior evidence"}\n', encoding="utf-8")
            extra_args.extend(["--import-evidence", str(evidence)])
        upstream = case["upstream_contract"]
        code, payload = _run_research_cli(
            artifact_root,
            "--prompt",
            case["prompt"],
            "--run-id",
            f"r1-parity-{index}",
            "--artifact-root",
            str(artifact_root),
            "--max-steps",
            "1",
            *extra_args,
        )
        assert code in {0, 2}
        contract = _contract(payload)
        solar_route = payload["route"]
        assert solar_route["workflow_kind"] == upstream["workflow_kind"]
        assert solar_route["start_stage"] == expected_start[case_id]
        assert contract["deliverable"]["language"] == upstream["output_language"]
        assert contract["deliverable"]["delivery_type"] == upstream["delivery_type"]
        for goal in upstream["semantic_goals"]:
            assert goal.lower().split()[0] in contract["user_intent"].lower() or goal in json.dumps(
                contract,
                ensure_ascii=False,
            )


def test_configurable_upstream_parity_runner_executes_same_prompt(tmp_path: Path) -> None:
    prompt = (
        "Analyze https://example.org/parity and produce an English Markdown report with at least 2 "
        "traceable sources. Separate claims and evidence."
    )
    fake_upstream = tmp_path / "fake_upstream.py"
    fake_upstream.write_text(
        """import argparse, json
p=argparse.ArgumentParser(); p.add_argument('--prompt', required=True); a=p.parse_args()
print(json.dumps({
  'intent': a.prompt,
  'workflow_stages': ['web_fetch', 'research_synthesis'],
  'input_type': 'url',
  'language': 'en',
  'deliverable_type': 'markdown',
  'required_evidence': ['claim_evidence_separation', 'minimum_traceable_sources:2', 'source_provenance'],
}))
""",
        encoding="utf-8",
    )
    upstream_command = json.dumps([sys.executable, str(fake_upstream), "--prompt", "{prompt}"])
    proc = subprocess.run(
        [
            sys.executable,
            str(UPSTREAM_RUNNER),
            "--prompt",
            prompt,
            "--artifact-root",
            str(tmp_path / "parity"),
            "--upstream-command-json",
            upstream_command,
        ],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    payload = json.loads(proc.stdout)
    assert proc.returncode == 0, proc.stderr
    assert payload["status"] == "PASS"
    assert all(item["match"] for item in payload["comparisons"].values())


def test_upstream_parity_runner_without_real_upstream_stays_partial(tmp_path: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(UPSTREAM_RUNNER),
            "--prompt",
            "Research local agent memory and produce an English Markdown report with 2 sources.",
            "--artifact-root",
            str(tmp_path / "partial"),
        ],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
        env={key: value for key, value in os.environ.items() if key != "SOLAR_AUTOSCI_UPSTREAM_COMMAND_JSON"},
    )
    payload = json.loads(proc.stdout)
    assert proc.returncode == 2
    assert payload["status"] == "PARTIAL"
    assert payload["reason"] == "upstream_command_not_configured"
