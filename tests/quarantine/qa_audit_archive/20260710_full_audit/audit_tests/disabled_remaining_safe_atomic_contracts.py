from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import socket
import subprocess
import tarfile
import zipfile
from pathlib import Path


AUDIT_ROOT = Path(__file__).resolve().parents[3]
CHECKOUT = AUDIT_ROOT / "tmp" / "codex-not-run-checkout"
HARNESS = CHECKOUT / "harness"
PYTHON = CHECKOUT / ".venv/bin/python"
BRIDGE = HARNESS / "plugins/autosci/bin/autosci_bridge.py"
SOLAR_HARNESS = HARNESS / "solar-harness.sh"


def safe_env(tmp_path: Path, *, harness_dir: Path = HARNESS) -> dict[str, str]:
    env = dict(os.environ)
    for key in list(env):
        if any(marker in key.upper() for marker in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")):
            env.pop(key, None)
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    env.update(
        {
            "HOME": str(home),
            "SOLAR_HOME": str(home / ".solar"),
            "HARNESS_DIR": str(harness_dir),
            "AUTOSCI_DISABLE_NETWORK_FETCH": "1",
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9",
        }
    )
    return env


def run(
    command: list[str],
    tmp_path: Path,
    *,
    cwd: Path = CHECKOUT,
    harness_dir: Path = HARNESS,
    timeout: int = 90,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = safe_env(tmp_path, harness_dir=harness_dir)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )


def bridge_run(action: str, tmp_path: Path, inputs: dict | None = None) -> dict:
    tmp_path.mkdir(parents=True, exist_ok=True)
    output_dir = tmp_path / "bridge-output" / action
    envelope_path = tmp_path / f"{action}.envelope.json"
    envelope = {
        "task_id": f"qa-{action}",
        "sprint_id": "qa-remaining-safe-atomic-contracts",
        "node_id": f"node-{action}",
        "mode": "fixture",
        "output_dir": str(output_dir),
        "inputs": inputs or {},
    }
    envelope_path.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
    proc = run(
        [str(PYTHON), str(BRIDGE), "run", "--action", action, "--envelope", str(envelope_path)],
        tmp_path,
        cwd=HARNESS,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def artifact_payload(result: dict, artifact_type: str) -> dict:
    artifact = next(item for item in result["evidence"]["artifacts"] if item["type"] == artifact_type)
    path = Path(artifact["path"])
    if not path.is_absolute():
        path = HARNESS / path
    return json.loads(path.read_text(encoding="utf-8"))


def tree_digest(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_wf_0024_stats_empty_corpus_returns_explicit_zero_state_without_mutation(tmp_path: Path) -> None:
    harness_copy = tmp_path / "harness"
    (harness_copy / "lib").mkdir(parents=True)
    shutil.copy2(SOLAR_HARNESS, harness_copy / "solar-harness.sh")
    shutil.copy2(HARNESS / "lib/run-state.sh", harness_copy / "lib/run-state.sh")
    shutil.copy2(HARNESS / "lib/events.sh", harness_copy / "lib/events.sh")
    before = tree_digest(harness_copy)
    proc = run(
        [str(harness_copy / "solar-harness.sh"), "stats"],
        tmp_path,
        cwd=harness_copy,
        harness_dir=harness_copy,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.strip() == "无 telemetry 数据"
    assert tree_digest(harness_copy) == before


def test_wf_0022_stats_aggregates_existing_artifacts_without_mutation(tmp_path: Path) -> None:
    harness_copy = tmp_path / "harness"
    (harness_copy / "lib").mkdir(parents=True)
    (harness_copy / "telemetry").mkdir()
    shutil.copy2(SOLAR_HARNESS, harness_copy / "solar-harness.sh")
    shutil.copy2(HARNESS / "lib/run-state.sh", harness_copy / "lib/run-state.sh")
    shutil.copy2(HARNESS / "lib/events.sh", harness_copy / "lib/events.sh")
    telemetry = harness_copy / "telemetry/runs.jsonl"
    telemetry.write_text(
        json.dumps({"verdict": "passed", "rounds": 2, "duration_sec": 10, "topology": "standard"})
        + "\n"
        + json.dumps({"verdict": "failed", "rounds": 4, "duration_sec": 20, "topology": "standard"})
        + "\n",
        encoding="utf-8",
    )
    before = tree_digest(harness_copy)
    proc = run(
        [str(harness_copy / "solar-harness.sh"), "stats"],
        tmp_path,
        cwd=harness_copy,
        harness_dir=harness_copy,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "总数: 2" in proc.stdout and "通过: 1" in proc.stdout and "失败: 1" in proc.stdout
    assert "通过率: 50.0%" in proc.stdout and "平均轮次: 3.0" in proc.stdout
    assert tree_digest(harness_copy) == before


def test_wf_0020_background_tasks_record_running_completed_failed_and_exit_codes(tmp_path: Path) -> None:
    harness_copy = tmp_path / "harness"
    (harness_copy / "lib").mkdir(parents=True)
    (harness_copy / "run/bg-tasks").mkdir(parents=True)
    work = tmp_path / "work"
    work.mkdir()
    shutil.copy2(SOLAR_HARNESS, harness_copy / "solar-harness.sh")
    shutil.copy2(HARNESS / "lib/run-state.sh", harness_copy / "lib/run-state.sh")
    shutil.copy2(HARNESS / "lib/events.sh", harness_copy / "lib/events.sh")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    tmux = fake_bin / "tmux"
    tmux.write_text(
        "#!/usr/bin/env bash\n"
        "case \"${1:-}\" in\n"
        "  has-session) exit 1 ;;\n"
        "  display-message) echo qa-bg-window; exit 0 ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    tmux.chmod(0o755)
    extra_env = {"PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"}

    created = run(
        [str(harness_copy / "solar-harness.sh"), "bg", "run", "--cwd", str(work), "--", "true"],
        tmp_path,
        cwd=harness_copy,
        harness_dir=harness_copy,
        extra_env=extra_env,
    )
    assert created.returncode == 0, created.stdout + created.stderr
    task_dir = next((harness_copy / "run/bg-tasks").iterdir())
    running_copy = task_dir / "running-observed.json"
    (task_dir / "command.sh").write_text(
        f"#!/usr/bin/env bash\ncp {shlex.quote(str(task_dir / 'status.json'))} {shlex.quote(str(running_copy))}\nexit 0\n",
        encoding="utf-8",
    )
    completed = run(
        ["bash", str(task_dir / "runner.sh")],
        tmp_path,
        cwd=work,
        harness_dir=harness_copy,
        extra_env=extra_env,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(running_copy.read_text(encoding="utf-8"))["status"] == "running"
    completed_status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
    assert completed_status["status"] == "completed" and completed_status["exit_code"] == 0

    second = run(
        [str(harness_copy / "solar-harness.sh"), "bg", "run", "--cwd", str(work), "--", "false"],
        tmp_path,
        cwd=harness_copy,
        harness_dir=harness_copy,
        extra_env=extra_env,
    )
    assert second.returncode == 0, second.stdout + second.stderr
    failed_dir = max((harness_copy / "run/bg-tasks").iterdir(), key=lambda path: path.stat().st_mtime_ns)
    failed = run(
        ["bash", str(failed_dir / "runner.sh")],
        tmp_path,
        cwd=work,
        harness_dir=harness_copy,
        extra_env=extra_env,
    )
    assert failed.returncode != 0
    failed_status = json.loads((failed_dir / "status.json").read_text(encoding="utf-8"))
    assert failed_status["status"] == "failed" and failed_status["exit_code"] != 0

    status = run(
        [str(harness_copy / "solar-harness.sh"), "bg", "status"],
        tmp_path,
        cwd=harness_copy,
        harness_dir=harness_copy,
        extra_env=extra_env,
    )
    assert status.returncode == 0
    assert "completed" in status.stdout and "failed" in status.stdout


def test_wf_0152_markdown_sections_have_stable_source_anchors(tmp_path: Path) -> None:
    paper = tmp_path / "paper.md"
    paper.write_text(
        "# QA Paper\n\n## Introduction\nGrounded introduction.\n\n## Results\nMeasured result.\n",
        encoding="utf-8",
    )
    inputs = {"paper_path": str(paper), "raw_root": str(tmp_path / "raw")}
    first = bridge_run("ingest_paper", tmp_path / "first", inputs)
    second = bridge_run("ingest_paper", tmp_path / "second", inputs)
    first_sections = first["evidence"]["outputs"]["paper"]["sections"]
    second_sections = second["evidence"]["outputs"]["paper"]["sections"]
    first_pairs = [(row["section_id"], row["source_anchor"]) for row in first_sections]
    second_pairs = [(row["section_id"], row["source_anchor"]) for row in second_sections]
    assert first_pairs == second_pairs
    assert first_pairs
    assert all(section_id and anchor.endswith(f"#{section_id}") for section_id, anchor in first_pairs)


def test_wf_0217_init_sources_scans_raw_channels_into_checkpoint_manifest(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    wiki_root = tmp_path / "wiki"
    for channel, name, content in (
        ("papers", "paper.md", "# Paper\n\nLocal paper source.\n"),
        ("notes", "note.md", "# Note\n\nLocal note source.\n"),
        ("web", "page.md", "# Web\n\nCaptured local web source.\n"),
    ):
        directory = raw_root / channel
        directory.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text(content, encoding="utf-8")
    result = bridge_run(
        "init_sources",
        tmp_path,
        {"query": "local source QA", "raw_root": str(raw_root), "wiki_root": str(wiki_root)},
    )
    manifest = artifact_payload(result, "init_discovery_prepare_manifest_json")
    manifest_text = json.dumps(manifest, sort_keys=True)
    assert all(name in manifest_text for name in ("paper.md", "note.md", "page.md"))
    assert all(channel in manifest_text for channel in ("papers", "notes", "web"))
    assert result["evidence"]["status"] == "inconclusive"
    assert "network" in " ".join(result["evidence"]["limitations"]).lower()


def test_wf_0233_pilot_run_requires_a_bounded_spec_and_required_inputs(tmp_path: Path) -> None:
    result = bridge_run("run_pilot_experiment", tmp_path, {"target": "missing-pilot-spec"})
    evidence = result["evidence"]
    text = json.dumps(evidence).lower()
    assert evidence["status"] in {"failed", "inconclusive"}
    assert "spec" in text
    assert any(marker in text for marker in ("missing dataset", "dataset is missing", "missing config", "config is missing"))
    assert not any(item.get("type") == "pilot_run_result_json" for item in evidence["artifacts"])


def test_wf_0234_pilot_run_emits_generated_code_artifact_before_execution(tmp_path: Path) -> None:
    spec = tmp_path / "experiments/pilot/qa-pilot.yaml"
    spec.parent.mkdir(parents=True)
    spec.write_text(
        "id: qa-pilot\ndataset: fixtures/data.json\ncommand: python run.py\nlimits:\n  max_minutes: 1\n",
        encoding="utf-8",
    )
    (tmp_path / "fixtures").mkdir()
    (tmp_path / "fixtures/data.json").write_text("[]\n", encoding="utf-8")
    result = bridge_run(
        "run_pilot_experiment",
        tmp_path,
        {"target": "qa-pilot", "pilot_spec": str(spec), "execute_approved_side_effect": False},
    )
    artifact_types = {item.get("type") for item in result["evidence"]["artifacts"]}
    assert "pilot_spec_snapshot" in artifact_types
    assert any(item in artifact_types for item in ("pilot_generated_code", "pilot_runner_script", "pilot_code_artifact"))
    assert not any(item in artifact_types for item in ("executor_stdout", "executor_stderr"))


def test_wf_0236_pilot_run_result_is_evidence_only_not_a_final_verdict(tmp_path: Path) -> None:
    result = bridge_run("run_pilot_experiment", tmp_path, {"target": "evidence-only", "execute_approved_side_effect": False})
    evidence = result["evidence"]
    text = json.dumps(evidence).lower()
    assert evidence["status"] == "inconclusive"
    assert "final_pilot_acceptance_ready" in text
    assert '"final_pilot_acceptance_ready": true' not in text
    assert not any(key in evidence.get("outputs", {}) for key in ("verdict", "accepted", "rejected"))


def test_wf_0237_pilot_eval_missing_result_is_typed_inconclusive(tmp_path: Path) -> None:
    result = bridge_run("evaluate_pilot_result", tmp_path, {"target": "missing-result"})
    evidence = result["evidence"]
    assert evidence["status"] == "inconclusive"
    verdicts = evidence["outputs"]["verdicts"]
    assert verdicts and verdicts[0]["verdict"] == "inconclusive"
    assert "not supplied" in verdicts[0]["basis"].lower()
    assert evidence["outputs"]["pilot_final_acceptance_boundary"]["final_pilot_acceptance_ready"] is False


def test_wf_0240_paper_plan_blocks_without_validated_idea_and_successful_experiment(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    (wiki / "ideas").mkdir(parents=True)
    (wiki / "experiments").mkdir()
    result = bridge_run("plan_report", tmp_path, {"target": "qa-paper", "wiki_root": str(wiki)})
    boundary = artifact_payload(result, "paper_plan_final_acceptance_boundary_json")
    assert boundary["final_plan_accepted"] is False
    assert boundary["idea_graph_ready"] is False
    assert "validated idea graph with succeeded experiment evidence is missing" in boundary["blocking_reasons"]


def test_wf_0105_and_wf_0242_unconfirmed_citations_are_explicit_plan_blockers(tmp_path: Path) -> None:
    source = tmp_path / "citation-source.json"
    source.write_text(
        json.dumps(
            {
                "schema": "literature_discovery.v1",
                "task_id": "qa-citation",
                "outputs": {
                    "candidates": [
                        {
                            "paper_id": "paper-qa",
                            "title": "Unconfirmed QA Citation",
                            "source_ref": "https://example.invalid/unconfirmed",
                            "source_channels": ["fixture"],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    result = bridge_run("plan_report", tmp_path, {"target": "qa-paper", "discovery_evidence": [str(source)]})
    boundary = artifact_payload(result, "paper_plan_final_acceptance_boundary_json")
    citation_map = artifact_payload(result, "citation_map_json")
    assert citation_map["citation_count"] == 1
    assert any("unconfirmed" in str(item).lower() for item in citation_map["citations"])
    assert any("unconfirmed" in reason.lower() for reason in boundary["blocking_reasons"])
    assert boundary["final_plan_accepted"] is False


def test_wf_0253_poster_html_contains_source_sections_and_no_raw_latex_or_todo(tmp_path: Path) -> None:
    paper_dir = tmp_path / "paper"
    sections = paper_dir / "sections"
    sections.mkdir(parents=True)
    (paper_dir / "main.tex").write_text(
        "\\title{Atomic QA Poster}\n\\begin{document}\n\\input{sections/intro}\n"
        "\\input{sections/method}\n\\input{sections/results}\n\\end{document}\n",
        encoding="utf-8",
    )
    (sections / "intro.tex").write_text("\\section{Introduction}\nGrounded motivation.\n", encoding="utf-8")
    (sections / "method.tex").write_text("\\section{Method}\nBounded local method.\n", encoding="utf-8")
    (sections / "results.tex").write_text("\\section{Results}\nMeasured fixture result.\n", encoding="utf-8")
    result = bridge_run(
        "build_poster",
        tmp_path,
        {"target": str(paper_dir), "paper_path": str(paper_dir), "no_figures": True, "venue": "QA 2026"},
    )
    html_artifact = next(item for item in result["evidence"]["artifacts"] if item["type"] == "poster_html")
    html_path = Path(html_artifact["path"])
    if not html_path.is_absolute():
        html_path = HARNESS / html_path
    html = html_path.read_text(encoding="utf-8")
    for expected in ("Atomic QA Poster", "Introduction", "Method", "Results", "QA 2026"):
        assert expected in html
    assert "\\begin{" not in html and "\\section{" not in html and "TODO" not in html


def test_wf_0264_reset_missing_scope_is_rejected_without_source_mutation(tmp_path: Path) -> None:
    wiki = tmp_path / "project/wiki"
    (wiki / "papers").mkdir(parents=True)
    source = wiki / "papers/keep.md"
    source.write_text("# Keep\n", encoding="utf-8")
    before = tree_digest(wiki)
    result = bridge_run("reset_plan", tmp_path, {"target": "qa-reset", "wiki_root": str(wiki)})
    assert result["evidence"]["status"] in {"failed", "inconclusive"}
    text = json.dumps(result["evidence"]).lower()
    assert "scope" in text and any(marker in text for marker in ("required", "missing", "choose"))
    assert tree_digest(wiki) == before


def test_wf_0265_reset_dry_run_lists_exact_mutations_without_mutating_source(tmp_path: Path) -> None:
    wiki = tmp_path / "project/wiki"
    (wiki / "papers").mkdir(parents=True)
    source = wiki / "papers/old.md"
    source.write_text("# Old\n", encoding="utf-8")
    before = tree_digest(wiki)
    result = bridge_run(
        "reset_plan",
        tmp_path,
        {"target": "qa-reset", "wiki_root": str(wiki), "reset_scope": "wiki"},
    )
    plan = artifact_payload(result, "reset_plan_json")
    assert any(str(path).endswith("papers/old.md") for path in plan["delete_files"])
    assert plan["status"] == "dry_run"
    assert result["evidence"]["status"] == "inconclusive"
    assert tree_digest(wiki) == before


def test_wf_0277_check_dry_run_proposes_exact_fixes_without_mutation(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    (wiki / "papers").mkdir(parents=True)
    (wiki / "graph").mkdir()
    (wiki / "papers/paper.md").write_text("# Paper\n", encoding="utf-8")
    (wiki / "graph/edges.jsonl").write_text('{"bad": "edge"}\n', encoding="utf-8")
    before = tree_digest(wiki)
    result = bridge_run(
        "check_wiki_health",
        tmp_path,
        {"target": str(wiki), "wiki_root": str(wiki), "fix": True, "dry_run": True},
    )
    evidence = result["evidence"]
    proposed = evidence["outputs"]["evolution"]["proposed_changes"]
    proposed_text = json.dumps(proposed).lower()
    assert "graph/edges.jsonl" in proposed_text
    assert all(item.get("application_state") == "proposed_only" for item in proposed)
    patch_dir_artifact = next(item for item in evidence["artifacts"] if item["type"] == "patch_candidates_directory")
    patch_dir = Path(patch_dir_artifact["path"])
    if not patch_dir.is_absolute():
        patch_dir = HARNESS / patch_dir
    assert any(path.is_file() for path in patch_dir.rglob("*"))
    assert tree_digest(wiki) == before


def test_wf_0110_and_wf_0255_unresolved_overflow_cannot_pass(tmp_path: Path) -> None:
    result = bridge_run("build_poster", tmp_path, {"target": "missing-render", "allow_compat_scaffold": True})
    validation = artifact_payload(result, "poster_validation_json")
    assert validation["overflow_probe"] == "not_run"
    assert validation["runtime_semantic"]["verified"] is False
    assert result["evidence"]["status"] == "inconclusive"
    assert not any(
        item.get("type") in {"poster_png", "provider_source_runtime_proof_manifest_json"}
        for item in result["evidence"]["artifacts"]
    )


def test_fd_0594_capability_inference_reports_missing_rule_configuration(tmp_path: Path) -> None:
    graph = tmp_path / "graph.json"
    graph.write_text(json.dumps({"nodes": [{"id": "n1", "goal": "use browser automation"}]}), encoding="utf-8")
    empty_pythonpath = tmp_path / "empty-pythonpath"
    empty_pythonpath.mkdir()
    proc = run(
        [str(PYTHON), str(HARNESS / "tools/capability_inference.py"), "enrich-graph", "--graph", str(graph)],
        tmp_path,
        extra_env={"PYTHONPATH": str(empty_pythonpath)},
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0
    payload = json.loads(combined)
    assert payload["ok"] is False
    assert any(word in payload["error"].lower() for word in ("rule", "configuration", "solar_skills"))


def test_misc_0224_status_server_exhausted_port_range_is_explicit_and_clean(tmp_path: Path) -> None:
    sockets: list[socket.socket] = []
    try:
        for port in range(8765, 8776):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))
            sock.listen(1)
            sockets.append(sock)
        proc = run(
            [str(PYTHON), str(HARNESS / "lib/symphony/status-server.py")],
            tmp_path,
            timeout=20,
            extra_env={"SOLAR_STATUS_BIND_HOST": "127.0.0.1"},
        )
        assert proc.returncode != 0
        assert "No available port in range 8765-8775" in proc.stderr
        assert not (tmp_path / "home/.solar/harness/run/status-server.port").exists()
    finally:
        for sock in sockets:
            sock.close()


def test_misc_0283_release_build_missing_version_fails_without_partial_artifacts(tmp_path: Path) -> None:
    harness_dir = tmp_path / "release-harness"
    (harness_dir / "release").mkdir(parents=True)
    shutil.copy2(HARNESS / "release/build.sh", harness_dir / "release/build.sh")
    out = tmp_path / "out"
    proc = run(
        ["bash", str(harness_dir / "release/build.sh"), "--out", str(out)],
        tmp_path,
        harness_dir=harness_dir,
    )
    assert proc.returncode != 0
    assert "No VERSION file" in proc.stderr and "--version not set" in proc.stderr
    assert not out.exists() or not any(out.iterdir())


def test_misc_0246_and_misc_0286_pipx_wheel_has_version_metadata_and_console_entrypoint(tmp_path: Path) -> None:
    wheel_dir = tmp_path / "wheelhouse"
    wheel_dir.mkdir()
    proc = run(
        [
            str(PYTHON),
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheel_dir),
            str(CHECKOUT / "distribution/pipx"),
        ],
        tmp_path,
        timeout=120,
        extra_env={"PIP_NO_INDEX": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1"},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    wheels = list(wheel_dir.glob("openjiuwen_solar-*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        names = archive.namelist()
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        entry_name = next(name for name in names if name.endswith(".dist-info/entry_points.txt"))
        metadata = archive.read(metadata_name).decode("utf-8")
        entry_points = archive.read(entry_name).decode("utf-8")
        assert "Name: openjiuwen-solar" in metadata
        assert "Version: 1.0.0rc6" in metadata
        assert "openjiuwen-solar = opensolar_cli.cli:main" in entry_points
        assert any(name == "opensolar_cli/cli.py" for name in names)


def test_wf_0027_malformed_migration_preserves_source_and_reports_failure(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle/solar-bundle-qa"
    bundle_dir.mkdir(parents=True)
    source = bundle_dir / "source-owned.txt"
    source.write_text("source remains intact\n", encoding="utf-8")
    bundle = tmp_path / "malformed.tar"
    with tarfile.open(bundle, "w") as archive:
        archive.add(bundle_dir, arcname=bundle_dir.name)
    before = hashlib.sha256(bundle.read_bytes()).hexdigest()
    proc = run(
        ["bash", str(HARNESS / "migrate/import.sh"), str(bundle), "--dry-run"],
        tmp_path,
        cwd=HARNESS,
        timeout=40,
    )
    assert proc.returncode != 0
    assert "bundle-meta.json" in proc.stdout
    assert hashlib.sha256(bundle.read_bytes()).hexdigest() == before
    assert source.read_text(encoding="utf-8") == "source remains intact\n"
    combined = (proc.stdout + proc.stderr).lower()
    assert any(marker in combined for marker in ("partial state", "rollback", "recovery state"))
