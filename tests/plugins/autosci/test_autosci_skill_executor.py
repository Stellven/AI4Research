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
