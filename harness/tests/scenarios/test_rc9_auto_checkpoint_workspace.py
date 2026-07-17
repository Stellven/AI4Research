"""RC9 regression: coordinator checkpoints must not mutate runtime-state repos.

The installed-user fixture placed ``HOME`` and ``HARNESS_DIR`` below an
unrelated git repository.  A sprint contract without a legacy ``Project:``
line made ``auto_checkpoint`` fall back to ``$HOME/.claude``; git walked to
that ancestor and committed sprint runtime artifacts.  The actual user
workspace was already durably bound in ``run/workspace-binding.json``.

The product contract is therefore:

* automatic git commits are off unless the user explicitly opts in; and
* an opted-in checkpoint can touch only the durably bound workspace.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


HARNESS = Path(__file__).resolve().parents[2]
COORDINATOR = HARNESS / "coordinator.sh"


def _git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.name", "Solar Test")
    _git(path, "config", "user.email", "solar-test@example.invalid")
    (path / "README.md").write_text("baseline\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-q", "-m", "baseline")


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    state_repo = tmp_path / "unrelated-state-repo"
    workspace = tmp_path / "user-workspace"
    _init_repo(state_repo)
    _init_repo(workspace)

    home = state_repo / "run-archive" / "run" / "home"
    harness_dir = home / ".solar" / "harness"
    sprints = harness_dir / "sprints"
    (home / ".claude").mkdir(parents=True)
    (harness_dir / "lib").mkdir(parents=True)
    (harness_dir / "run").mkdir(parents=True)
    sprints.mkdir(parents=True)
    shutil.copy2(HARNESS / "lib" / "workspace_binding.py", harness_dir / "lib")

    sid = "sprint-rc9-checkpoint"
    (sprints / f"{sid}.status.json").write_text(
        json.dumps({"id": sid, "status": "drafting"}) + "\n",
        encoding="utf-8",
    )
    (harness_dir / "run" / "workspace-binding.json").write_text(
        json.dumps({
            "schema": "solar.workspace_binding.v1",
            "workspace_root": str(workspace),
            "source": "test",
        }) + "\n",
        encoding="utf-8",
    )
    return state_repo, workspace, harness_dir, sid


def _checkpoint(home: Path, harness_dir: Path, sid: str, *, enabled: bool) -> None:
    env = {
        **os.environ,
        "HOME": str(home),
        "HARNESS_DIR": str(harness_dir),
        "COORD_NO_MAIN": "1",
        "SOLAR_AUTO_CHECKPOINT": "1" if enabled else "0",
    }
    script = f"""
set -e
source {COORDINATOR!s}
log() {{ :; }}
auto_checkpoint {sid!s} drafting
"""
    subprocess.run(["bash", "-c", script], check=True, env=env, timeout=30)


def test_checkpoint_is_off_by_default_even_below_unrelated_git_repo(tmp_path: Path) -> None:
    state_repo, workspace, harness_dir, sid = _fixture(tmp_path)
    before = _git(state_repo, "rev-list", "--count", "HEAD")

    _checkpoint(harness_dir.parents[1], harness_dir, sid, enabled=False)

    assert _git(state_repo, "rev-list", "--count", "HEAD") == before
    assert not _git(state_repo, "tag", "-l", f"checkpoint/{sid}/*")
    assert _git(workspace, "rev-list", "--count", "HEAD") == "1"


def test_opted_in_checkpoint_uses_only_bound_workspace(tmp_path: Path) -> None:
    state_repo, workspace, harness_dir, sid = _fixture(tmp_path)
    state_before = _git(state_repo, "rev-list", "--count", "HEAD")
    (workspace / "slugify.py").write_text("print('ok')\n", encoding="utf-8")

    _checkpoint(harness_dir.parents[1], harness_dir, sid, enabled=True)

    assert _git(state_repo, "rev-list", "--count", "HEAD") == state_before
    assert _git(workspace, "rev-list", "--count", "HEAD") == "2"
    assert _git(workspace, "show", "--format=", "--name-only", "HEAD") == "slugify.py"
    assert _git(workspace, "tag", "-l", f"checkpoint/{sid}/drafting/*")
    assert not _git(state_repo, "tag", "-l", f"checkpoint/{sid}/*")
