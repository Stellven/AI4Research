"""The seam that actually runs AutoSci.

autosci_bridge.py verifies runtime evidence and converts it; it executes
nothing. This executor runs the stage's AutoSci skill and feeds the bridge, so
its safety properties matter: it must fail closed, never synthesise a runtime
record, and never leak provider credentials into the skill subprocess.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[3] / "harness"
EXECUTOR = HARNESS / "plugins/autosci/bin/autosci_skill_executor.py"
_SPEC = importlib.util.spec_from_file_location("autosci_skill_executor", EXECUTOR)
assert _SPEC and _SPEC.loader
ex = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ex)


def _bridge_actions() -> set[str]:
    source = (HARNESS / "plugins/autosci/bin/autosci_bridge.py").read_text(encoding="utf-8")
    block = source.split("ACTIONS: dict[str, Callable", 1)[1].split("}", 1)[0]
    return {line.split('"')[1] for line in block.splitlines() if line.strip().startswith('"')}


def test_every_stage_maps_to_a_real_bridge_action() -> None:
    actions = _bridge_actions()
    for stage, (skill, action) in ex.STAGES.items():
        assert action in actions, f"stage {stage} maps to unknown bridge action {action}"
        assert skill.startswith("$"), f"stage {stage} must name an AutoSci skill invocation"


def test_part_b_stages_are_covered() -> None:
    for stage in (
        "idea_generation",
        "idea_evaluation",
        "experiment_design",
        "experiment_run",
        "experiment_monitor",
        "claim_verification",
        "report_delivery",
    ):
        assert stage in ex.STAGES


def test_fails_closed_without_an_autosci_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOLAR_AUTOSCI_HOME", raising=False)
    with pytest.raises(ex.ExecutorError, match="SOLAR_AUTOSCI_HOME is not set"):
        ex._autosci_home()


def test_fails_closed_when_the_autosci_home_is_not_a_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bogus = tmp_path / "not-a-dir"
    bogus.write_text("x", encoding="utf-8")
    monkeypatch.setenv("SOLAR_AUTOSCI_HOME", str(bogus))
    with pytest.raises(ex.ExecutorError, match="not a directory"):
        ex._autosci_home()


def test_provider_credentials_are_not_forwarded_to_the_skill(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Codex CLI authenticates from its own CODEX_HOME; an inherited API key
    would silently change the provider boundary the evidence claims."""
    for key in ex.SECRET_ENV_KEYS:
        monkeypatch.setenv(key, "must-not-propagate")
    env = ex._skill_env()
    for key in ex.SECRET_ENV_KEYS:
        assert key not in env


def test_runtime_record_carries_the_real_exit_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed skill run must be recorded as failed so the bridge fails closed.
    With no approval node ahead of execution, a synthesised success here would
    be indistinguishable from a real one."""
    home = tmp_path / "autosci"
    home.mkdir()
    # experiment_run takes an experiment slug, so the wiki has to hold one or
    # the executor fails closed before it ever reaches the skill.
    experiments = home / "wiki" / "experiments"
    experiments.mkdir(parents=True)
    (experiments / "sparse-lora-main.md").write_text(
        '---\nslug: "sparse-lora-main"\nstatus: planned\nlinked_idea: "sparse-lora"\n---\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("SOLAR_AUTOSCI_HOME", str(home))
    monkeypatch.delenv("SOLAR_AUTOSCI_STAGE_ARGUMENT", raising=False)
    # a "codex" that always fails
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "codex").write_text("#!/bin/sh\necho boom >&2\nexit 3\n", encoding="utf-8")
    (fake / "codex").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}{os.pathsep}{os.environ['PATH']}")

    record_path = tmp_path / "rec.json"
    record = ex.run_skill(
        stage="experiment_run", request="anything", record_path=record_path, timeout_seconds=30
    )
    assert record["exit_code"] == 3
    assert record["credential_contents_recorded"] is False
    # The slug came from the wiki page the previous stage would have written,
    # not from the free-text request.
    assert record["stage_argument"] == "sparse-lora-main"
    assert record["stage_argument_source"] == "wiki/experiments"
    assert record["skill_invocation"] == "$exp-run sparse-lora-main --full"
    on_disk = json.loads(record_path.read_text(encoding="utf-8"))
    assert on_disk["exit_code"] == 3
    assert Path(on_disk["stderr_path"]).read_text(encoding="utf-8").strip() == "boom"


def test_cli_reports_the_failure_as_json_and_exits_nonzero(tmp_path: Path) -> None:
    env = dict(os.environ)
    env.pop("SOLAR_AUTOSCI_HOME", None)
    envelope = tmp_path / "envelope.json"
    envelope.write_text(json.dumps({"task_id": "t", "inputs": {}}), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(EXECUTOR), "--stage", "experiment_run", "--envelope", str(envelope)],
        capture_output=True, text=True, env=env, check=False,
    )
    assert proc.returncode == 2
    assert json.loads(proc.stderr)["ok"] is False


def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "autosci"
    (home / "wiki").mkdir(parents=True)
    monkeypatch.setenv("SOLAR_AUTOSCI_HOME", str(home))
    monkeypatch.delenv("SOLAR_AUTOSCI_STAGE_ARGUMENT", raising=False)
    return home


def _page(root: Path, name: str, **fields: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    body = "---\n" + "".join(f'{k}: "{v}"\n' for k, v in fields.items()) + "---\n"
    path = root / f"{name}.md"
    path.write_text(body, encoding="utf-8")
    return path


def test_only_the_first_stage_receives_the_free_text_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """$ideate takes a topic; every later skill takes an identifier.

    Handing the original request to $exp-design was why Part B could never get
    past experiment_design: "give me a report on ..." is not an idea slug.
    """
    home = _home(tmp_path, monkeypatch)
    resolved = ex.resolve_stage_argument(
        stage="idea_evaluation", request="whether mamba beats transformers", home=home
    )

    assert resolved["argument"] == "whether mamba beats transformers"
    assert resolved["source"] == "request"


def test_experiment_design_takes_the_idea_slug_the_previous_stage_wrote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _home(tmp_path, monkeypatch)
    ideas = home / "wiki" / "ideas"
    # $ideate writes eliminated ideas too, with status: failed. Designing an
    # experiment for one of those would be a silent waste of a whole Part B run.
    _page(ideas, "rejected-idea", slug="rejected-idea", status="failed")
    _page(ideas, "surviving-idea", slug="surviving-idea", status="proposed")

    resolved = ex.resolve_stage_argument(
        stage="experiment_design", request="the original request", home=home
    )

    assert resolved["argument"] == "surviving-idea"
    assert resolved["matched_status"] == "proposed"
    assert resolved["source"] == "wiki/ideas"


def test_a_stage_whose_predecessor_produced_nothing_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No slug means no run. Never fall back to the request or invent one."""
    home = _home(tmp_path, monkeypatch)
    _page(home / "wiki" / "ideas", "only-failures", slug="only-failures", status="failed")

    with pytest.raises(ex.ExecutorError, match="no wiki/ideas page with status"):
        ex.resolve_stage_argument(stage="experiment_design", request="anything", home=home)


def test_report_delivery_needs_a_paper_plan_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _home(tmp_path, monkeypatch)

    with pytest.raises(ex.ExecutorError, match="paper-plan"):
        ex.resolve_stage_argument(stage="report_delivery", request="anything", home=home)

    outputs = home / "wiki" / "outputs"
    outputs.mkdir(parents=True)
    (outputs / "paper-plan-sparse-lora-2026-04-08.md").write_text("plan", encoding="utf-8")

    resolved = ex.resolve_stage_argument(stage="report_delivery", request="anything", home=home)
    assert resolved["argument"] == "wiki/outputs/paper-plan-sparse-lora-2026-04-08.md"


def test_an_explicit_override_wins_over_wiki_inspection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _home(tmp_path, monkeypatch)
    _page(home / "wiki" / "ideas", "from-wiki", slug="from-wiki", status="proposed")
    monkeypatch.setenv("SOLAR_AUTOSCI_STAGE_ARGUMENT", "pinned-by-caller")

    resolved = ex.resolve_stage_argument(
        stage="experiment_design", request="anything", home=home
    )

    assert resolved["argument"] == "pinned-by-caller"
    assert resolved["source"] == "explicit_override"


def test_every_interactive_skill_is_given_its_non_interactive_flag() -> None:
    """The workflow has no approval node, so nothing may pause for a human.

    A skill that stops to ask inside `codex exec` hangs until the timeout and is
    then recorded as a failure, which is truthful but useless.
    """
    assert ex.STAGE_FLAGS["idea_evaluation"] == ("--auto",)
    assert ex.STAGE_FLAGS["claim_verification"] == ("--auto",)
    assert ex.STAGE_FLAGS["experiment_monitor"] == ("--auto-advance",)
    # $exp-run defaults to deploy-only; --full deploys and collects, which is
    # what a single non-interactive stage has to do.
    assert ex.STAGE_FLAGS["experiment_run"] == ("--full",)


def test_every_stage_declares_where_its_argument_comes_from() -> None:
    assert set(ex.ARGUMENT_SOURCES) == set(ex.STAGES)


def test_the_part_b_chain_threads_identifiers_from_one_stage_to_the_next(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end over a fake AutoSci that writes the wiki pages the real skills do.

    This is the property Part B needs and never had: each stage must run against
    what the previous stage actually produced. The fake codex records the prompt
    it was given and mutates the wiki the way the real skill's contract says it
    would, so the assertions are about the chain, not about AutoSci's output.
    """
    home = _home(tmp_path, monkeypatch)
    invocations = tmp_path / "invocations.txt"

    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "codex").write_text(
        "#!/usr/bin/env python3\n"
        "import os, pathlib, sys\n"
        "prompt = sys.argv[-1]\n"
        f"pathlib.Path({str(invocations)!r}).open('a').write(prompt + '\\n')\n"
        f"wiki = pathlib.Path({str(home)!r}) / 'wiki'\n"
        "if prompt.startswith('$ideate'):\n"
        "    d = wiki / 'ideas'; d.mkdir(parents=True, exist_ok=True)\n"
        "    (d / 'mamba-vs-transformer.md').write_text(\n"
        "        '---\\nslug: \"mamba-vs-transformer\"\\nstatus: proposed\\n---\\n')\n"
        "elif prompt.startswith('$exp-design'):\n"
        "    d = wiki / 'experiments'; d.mkdir(parents=True, exist_ok=True)\n"
        "    (d / 'mamba-main.md').write_text(\n"
        "        '---\\nslug: \"mamba-main\"\\nstatus: planned\\n"
        "linked_idea: \"mamba-vs-transformer\"\\n---\\n')\n"
        "elif prompt.startswith('$exp-run'):\n"
        "    p = wiki / 'experiments' / 'mamba-main.md'\n"
        "    p.write_text(p.read_text().replace('status: planned', 'status: completed'))\n"
        "print('ok')\n",
        encoding="utf-8",
    )
    (fake / "codex").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}{os.pathsep}{os.environ['PATH']}")

    records = []
    for index, stage in enumerate(
        ("idea_evaluation", "experiment_design", "experiment_run", "claim_verification")
    ):
        records.append(
            ex.run_skill(
                stage=stage,
                request="whether mamba beats transformers",
                record_path=tmp_path / f"{index}-{stage}.json",
                timeout_seconds=30,
            )
        )

    assert [r["exit_code"] for r in records] == [0, 0, 0, 0]
    assert invocations.read_text(encoding="utf-8").splitlines() == [
        "$ideate whether mamba beats transformers --auto",
        "$exp-design mamba-vs-transformer",
        "$exp-run mamba-main --full",
        "$exp-eval mamba-main --auto",
    ]
    # claim_verification wants a finished experiment, and $exp-run is what
    # moved that page from planned to completed.
    assert records[-1]["stage_argument_source"] == "wiki/experiments"


def test_the_envelope_tells_the_bridge_which_wiki_entity_the_run_was_about() -> None:
    """Evidence must describe the run it claims to describe.

    autosci_bridge._should_resolve_wiki_state only reads the wiki when the
    envelope carries wiki_root/idea_id/experiment_id/topic and friends. A first
    real Part B run passed an envelope holding only `request`, so the bridge
    matched none of them, fell back to its fixture converter, and emitted typed
    evidence about `idea-001` while $ideate had actually written
    wiki/ideas/jepa-augmented-transmamba-long-context-abstraction.md.
    """
    record = {
        "autosci_home": "/srv/autosci",
        "stage_argument": "jepa-augmented-transmamba-long-context-abstraction",
    }

    design = ex._bridge_subject_inputs(stage="experiment_design", record=record)
    assert design["wiki_root"] == "/srv/autosci/wiki"
    assert design["idea_id"] == "jepa-augmented-transmamba-long-context-abstraction"

    run = ex._bridge_subject_inputs(
        stage="experiment_run", record={**record, "stage_argument": "mamba-main"}
    )
    assert run["experiment_id"] == "mamba-main"
    assert "idea_id" not in run

    # $ideate takes a topic, not an entity id, so name it as a topic.
    ideate = ex._bridge_subject_inputs(
        stage="idea_evaluation", record={**record, "stage_argument": "mamba versus transformers"}
    )
    assert ideate["topic"] == "mamba versus transformers"
    assert "idea_id" not in ideate


def test_every_stage_hands_the_bridge_a_wiki_resolution_trigger() -> None:
    """No stage may reach the bridge without one, or it silently uses fixtures."""
    triggers = {"wiki_root", "from_wiki", "target", "topic", "query", "idea_id", "experiment_id"}
    for stage in ex.STAGES:
        subject = ex._bridge_subject_inputs(
            stage=stage, record={"autosci_home": "/srv/autosci", "stage_argument": "some-slug"}
        )
        assert triggers & set(subject), f"{stage} would fall back to fixture evidence"


def test_the_envelope_never_claims_fixture_mode_after_a_real_skill_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unstated mode is normalized to "fixture", which fabricates evidence.

    adapters/solar_envelope_to_autosci.normalize_envelope defaults a missing
    `mode` to "fixture", and the bridge reads that as licence to skip wiki
    resolution and synthesise evaluations from convert_idea_candidate({}). The
    first live Part B run hit exactly this: $ideate wrote a real idea page and
    the typed evidence described `idea-001`.

    Supplying wiki_root and idea_id was NOT enough on its own; the fixture
    default overrode them. The executor has to state the mode as well.
    """
    home = _home(tmp_path, monkeypatch)
    _page(home / "wiki" / "ideas", "real-idea", slug="real-idea", status="proposed")
    fake = tmp_path / "bin"
    fake.mkdir()
    # Succeed, and record nothing; only the envelope handed to the bridge matters.
    (fake / "codex").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (fake / "codex").chmod(0o755)
    (fake / "bridge-stub").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    monkeypatch.setenv("PATH", f"{fake}{os.pathsep}{os.environ['PATH']}")

    envelope_path = tmp_path / "envelope.json"
    envelope_path.write_text(json.dumps({"task_id": "t", "inputs": {"request": "a topic"}}), encoding="utf-8")

    captured: dict = {}

    def fake_bridge(*, action: str, envelope_path: Path):
        captured.update(json.loads(Path(envelope_path).read_text(encoding="utf-8")))
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr(ex, "invoke_bridge", fake_bridge)

    args = ex._parser().parse_args(
        ["--stage", "experiment_design", "--envelope", str(envelope_path), "--work-dir", str(tmp_path)]
    )
    ex.execute(args)

    assert captured["mode"] != "fixture", "fixture mode makes the bridge fabricate the evidence"
    assert captured["inputs"]["idea_id"] == "real-idea"
    assert captured["inputs"]["wiki_root"] == str(home / "wiki")


def test_an_explicitly_declared_mode_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A caller that really does want a fixture run keeps it."""
    home = _home(tmp_path, monkeypatch)
    _page(home / "wiki" / "ideas", "real-idea", slug="real-idea", status="proposed")
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "codex").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (fake / "codex").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}{os.pathsep}{os.environ['PATH']}")

    envelope_path = tmp_path / "envelope.json"
    envelope_path.write_text(
        json.dumps({"task_id": "t", "mode": "fixture", "inputs": {"request": "a topic"}}),
        encoding="utf-8",
    )
    captured: dict = {}
    monkeypatch.setattr(
        ex,
        "invoke_bridge",
        lambda *, action, envelope_path: (
            captured.update(json.loads(Path(envelope_path).read_text(encoding="utf-8")))
            or subprocess.CompletedProcess(args=[], returncode=0, stdout="{}", stderr="")
        ),
    )

    args = ex._parser().parse_args(
        ["--stage", "experiment_design", "--envelope", str(envelope_path), "--work-dir", str(tmp_path)]
    )
    ex.execute(args)

    assert captured["mode"] == "fixture"


def test_a_timed_out_skill_is_never_reported_as_a_successful_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Found live: experiment_design timed out and the stage said ok=True.

    $exp-design hit its 40-minute timeout at exit 124 and wrote no experiment
    page. The bridge still returned 0, and `ok` was computed from the bridge
    alone, so the top line of the result announced success for a stage that had
    produced nothing. Only the runtime record showed the truth.
    """
    home = _home(tmp_path, monkeypatch)
    _page(home / "wiki" / "ideas", "an-idea", slug="an-idea", status="proposed")
    fake = tmp_path / "bin"
    fake.mkdir()
    # A skill that hangs past the stage timeout.
    (fake / "codex").write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
    (fake / "codex").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}{os.pathsep}{os.environ['PATH']}")
    # A bridge that is perfectly happy regardless.
    monkeypatch.setattr(
        ex,
        "invoke_bridge",
        lambda *, action, envelope_path: subprocess.CompletedProcess(
            args=[], returncode=0, stdout="{}", stderr=""
        ),
    )

    envelope_path = tmp_path / "envelope.json"
    envelope_path.write_text(json.dumps({"task_id": "t", "inputs": {"request": "x"}}), encoding="utf-8")
    args = ex._parser().parse_args(
        [
            "--stage", "experiment_design",
            "--envelope", str(envelope_path),
            "--work-dir", str(tmp_path),
            "--timeout-seconds", "1",
        ]
    )
    payload = ex.execute(args)

    assert payload["timed_out"] is True
    assert payload["skill_exit_code"] == 124
    assert payload["bridge_ok"] is True, "the bridge really did return 0; that is the point"
    assert payload["skill_ok"] is False
    assert payload["ok"] is False, "a stage that produced nothing must not report success"


def test_the_trace_records_what_the_stage_actually_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three of four defects were found by hand-reading a file. This is the file.

    A stage that succeeds and a stage that changes something are different
    facts, and both defects this session lived in the gap. The trace records
    the wiki delta, the resolved argument, and the envelope as the bridge
    received it -- the three places the faults actually hid.
    """
    home = _home(tmp_path, monkeypatch)
    _page(home / "wiki" / "ideas", "an-idea", slug="an-idea", status="proposed")
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "codex").write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib\n"
        f"d = pathlib.Path({str(home / 'wiki' / 'experiments')!r})\n"
        "d.mkdir(parents=True, exist_ok=True)\n"
        "(d / 'new-exp.md').write_text('---\\nslug: \"new-exp\"\\nstatus: planned\\n---\\n')\n",
        encoding="utf-8",
    )
    (fake / "codex").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(
        ex, "invoke_bridge",
        lambda *, action, envelope_path: subprocess.CompletedProcess(
            args=[], returncode=0, stdout="{}", stderr=""),
    )

    envelope_path = tmp_path / "envelope.json"
    envelope_path.write_text(json.dumps({"task_id": "t", "inputs": {"request": "x"}}), encoding="utf-8")
    args = ex._parser().parse_args(
        ["--stage", "experiment_design", "--envelope", str(envelope_path), "--work-dir", str(tmp_path)]
    )
    payload = ex.execute(args)

    trace = json.loads(Path(payload["trace"]).read_text(encoding="utf-8"))
    assert trace["schema"] == "solar.autosci_stage_trace.v1"
    assert trace["wiki"]["delta"]["added"] == ["experiments/new-exp.md"]
    assert trace["verdicts"]["changed_wiki"] is True
    assert trace["argument_resolution"]["source"] == "wiki/ideas"
    # The fixture-mode defect was visible only in what the bridge was handed.
    assert trace["bridge"]["envelope_as_sent"]["mode"] != "fixture"
    assert trace["bridge"]["envelope_as_sent"]["inputs"]["idea_id"] == "an-idea"
    # Wall clock is unusable on this host; duration must come from a monotonic source.
    assert isinstance(trace["skill"]["duration_seconds"], float)


def test_a_stage_that_changed_nothing_is_recorded_as_such(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The timed-out experiment_design wrote no page. That must be legible."""
    home = _home(tmp_path, monkeypatch)
    _page(home / "wiki" / "ideas", "an-idea", slug="an-idea", status="proposed")
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "codex").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (fake / "codex").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(
        ex, "invoke_bridge",
        lambda *, action, envelope_path: subprocess.CompletedProcess(
            args=[], returncode=0, stdout="{}", stderr=""),
    )

    envelope_path = tmp_path / "envelope.json"
    envelope_path.write_text(json.dumps({"task_id": "t", "inputs": {"request": "x"}}), encoding="utf-8")
    args = ex._parser().parse_args(
        ["--stage", "experiment_design", "--envelope", str(envelope_path), "--work-dir", str(tmp_path)]
    )
    payload = ex.execute(args)

    # The skill exited clean and the bridge was happy, so ok is True -- and the
    # stage still produced nothing. Both facts are recorded, separately.
    assert payload["ok"] is True
    assert payload["changed_wiki"] is False
    assert payload["wiki_delta"] == {"added": [], "removed": [], "modified": []}


def test_a_killed_skill_still_leaves_its_output_on_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 40-minute experiment_design run left a 0-byte log. This is why.

    capture_output=True holds everything in the parent's pipes until the child
    exits, so a skill killed on timeout produced no log at all, while the run
    that finished cleanly produced 4 KB. The run you cannot explain is exactly
    the one whose output you need.
    """
    home = _home(tmp_path, monkeypatch)
    _page(home / "wiki" / "ideas", "an-idea", slug="an-idea", status="proposed")
    fake = tmp_path / "bin"
    fake.mkdir()
    # Emits progress, then hangs past the stage timeout.
    (fake / "codex").write_text(
        "#!/bin/sh\necho 'stage 1: reading idea page'\necho 'stage 2: drafting blocks'\nsleep 30\n",
        encoding="utf-8",
    )
    (fake / "codex").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}{os.pathsep}{os.environ['PATH']}")

    record_path = tmp_path / "rec.json"
    record = ex.run_skill(
        stage="experiment_design", request="x", record_path=record_path, timeout_seconds=2
    )

    assert record["timed_out"] is True
    assert record["exit_code"] == 124
    streamed = Path(record["stdout_path"]).read_text(encoding="utf-8")
    assert "stage 1: reading idea page" in streamed
    assert "stage 2: drafting blocks" in streamed, "progress written before the kill must survive"
    assert "timed out after 2s" in Path(record["stderr_path"]).read_text(encoding="utf-8")


def test_autosci_progress_is_read_from_their_own_pipeline_file(tmp_path: Path) -> None:
    """$research records every stage with a duration; read it rather than guess."""
    home = tmp_path / "autosci"
    outputs = home / "wiki" / "outputs"
    outputs.mkdir(parents=True)
    (outputs / "pipeline-progress.md").write_text(
        "## Stage Summary\n"
        "| Stage | Status | Duration |\n"
        "|-------|--------|----------|\n"
        "| Stage 1: Idea Discovery | completed | 12m |\n"
        "| Gate 1: Idea Selection | passed | 0m |\n"
        "| Stage 2: Experiment Design | running | 41m |\n"
        "\n## Selected Idea\n- **Idea**: [[some-slug]]\n",
        encoding="utf-8",
    )

    progress = ex.autosci_progress(home)

    assert progress["present"] is True
    assert progress["stages"] == [
        {"stage": "Stage 1: Idea Discovery", "status": "completed", "duration": "12m"},
        {"stage": "Gate 1: Idea Selection", "status": "passed", "duration": "0m"},
        {"stage": "Stage 2: Experiment Design", "status": "running", "duration": "41m"},
    ]


def test_absent_autosci_progress_is_reported_not_invented(tmp_path: Path) -> None:
    assert ex.autosci_progress(tmp_path)["present"] is False
