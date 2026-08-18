from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path


HARNESS_ROOT = (Path(__file__).resolve().parents[3] / 'harness')
LAUNCHER = HARNESS_ROOT / "pane-launcher.sh"
HARNESS_ENTRY = HARNESS_ROOT / "solar-harness.sh"


def _run_launcher(
    tmp_path: Path,
    *,
    trust_workspace: str = "1",
    extra_flags: str = "",
) -> tuple[dict, Path]:
    harness = tmp_path / "installed-harness"
    home = tmp_path / "home"
    workspace = tmp_path / 'project with spaces and "quotes"'
    capture = tmp_path / "codex-argv.json"
    fake_codex = tmp_path / "codex"

    (harness / "lib").mkdir(parents=True)
    (harness / "personas").mkdir()
    (home / ".codex").mkdir(parents=True)
    workspace.mkdir()

    for relative in (
        "lib/codex_trust_profiles.py",
        "lib/file_lock_compat.py",
        "lib/persona-config.sh",
        "lib/capability-prefix.sh",
        "personas/pm.md",
    ):
        source = HARNESS_ROOT / relative
        destination = harness / relative
        shutil.copy2(source, destination)

    fake_codex.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "profile_name = args[args.index('--profile') + 1] if '--profile' in args else ''\n"
        "profile_path = (\n"
        "    Path(os.environ['CODEX_HOME']) / f'{profile_name}.config.toml'\n"
        "    if profile_name else None\n"
        ")\n"
        "payload = {\n"
        "    'argv': args,\n"
        "    'profile_name': profile_name,\n"
        "    'profile_path': str(profile_path) if profile_path else '',\n"
        "    'profile_contents': (\n"
        "        profile_path.read_text(encoding='utf-8') if profile_path else ''\n"
        "    ),\n"
        "}\n"
        "Path(os.environ['CODEX_ARGV_CAPTURE']).write_text(\n"
        "    json.dumps(payload), encoding='utf-8'\n"
        ")\n",
        encoding="utf-8",
    )
    fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    for key in (
        "CODEX_HOME",
        "SOLAR_CODEX_EXTRA_FLAGS",
        "SOLAR_CODEX_MODEL",
        "TMUX_PANE",
    ):
        env.pop(key, None)
    env.update(
        {
            "CODEX_ARGV_CAPTURE": str(capture),
            "CODEX_HOME": str(home / ".codex"),
            "HARNESS_DIR": str(harness),
            "HOME": str(home),
            "SHELL": shutil.which("true") or "/usr/bin/true",
            "SOLAR_CODEX_BIN": str(fake_codex),
            "SOLAR_CODEX_BYPASS": "1",
            "SOLAR_CODEX_PANE_FS_ISOLATION": "codex",
            "SOLAR_CODEX_TRUST_WORKSPACE": trust_workspace,
            "SOLAR_HARNESS_DIR": str(harness),
            "SOLAR_PANE_RUNTIME": "codex",
            "TERM": "xterm",
        }
    )
    if extra_flags:
        env["SOLAR_CODEX_EXTRA_FLAGS"] = extra_flags

    completed = subprocess.run(
        ["bash", str(LAUNCHER), "pm", str(workspace)],
        cwd=workspace,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
    return json.loads(capture.read_text(encoding="utf-8")), workspace.resolve()


def test_managed_codex_workspace_sandbox_trusts_the_exact_workspace_for_this_invocation(
    tmp_path: Path,
) -> None:
    payload, workspace = _run_launcher(tmp_path)
    argv = payload["argv"]

    expected_section = f'[projects.{json.dumps(str(workspace))}]'
    assert "--dangerously-bypass-approvals-and-sandbox" not in argv
    assert argv[argv.index("--sandbox") + 1] == "workspace-write"
    assert "--profile" in argv
    assert payload["profile_name"].startswith("solar-managed-")
    assert expected_section in payload["profile_contents"]
    assert 'trust_level = "trusted"' in payload["profile_contents"]
    assert not Path(payload["profile_path"]).exists()


def test_codex_workspace_trust_can_be_explicitly_disabled(tmp_path: Path) -> None:
    payload, workspace = _run_launcher(tmp_path, trust_workspace="0")
    argv = payload["argv"]

    project_prefix = f'projects.{json.dumps(str(workspace))}.trust_level='
    assert not any(arg.startswith(project_prefix) for arg in argv)
    assert "--profile" not in argv
    assert payload["profile_path"] == ""


def test_cockpit_propagates_the_workspace_trust_control_to_managed_panes() -> None:
    source = HARNESS_ENTRY.read_text(encoding="utf-8")
    assignment_block = source.split("pane_runtime_env_assignments()", 1)[1].split(
        "\n}", 1
    )[0]
    tmux_block = source.split("configure_tmux_pane_runtime_env()", 1)[1].split(
        "\n}", 1
    )[0]

    assert "SOLAR_CODEX_TRUST_WORKSPACE" in assignment_block
    assert "SOLAR_CODEX_TRUST_WORKSPACE" in tmux_block


def test_codex_launch_preserves_dashboard_search_and_effort_flags(tmp_path: Path) -> None:
    payload, _workspace = _run_launcher(
        tmp_path,
        extra_flags="--search -c model_reasoning_effort=high",
    )

    argv = payload["argv"]
    assert "--search" in argv
    effort = argv.index("model_reasoning_effort=high")
    assert argv[effort - 1] == "-c"
