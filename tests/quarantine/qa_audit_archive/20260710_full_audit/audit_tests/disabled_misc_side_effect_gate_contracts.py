from __future__ import annotations

import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path


AUDIT_ROOT = Path(__file__).resolve().parents[3]
CHECKOUT = AUDIT_ROOT / "tmp" / "codex-not-run-checkout"


def _text(path: str) -> str:
    return (CHECKOUT / path).read_text(encoding="utf-8").lower()


def _assert_explicit_approval_policy(text: str) -> None:
    assert any(token in text for token in ("approval", "approved", "explicit confirmation", "always ask", "确认", "批准"))
    assert any(token in text for token in ("write", "create", "update", "delete", "send", "发送", "创建", "写"))


def test_office_skill_external_mutations_require_explicit_approval() -> None:
    _assert_explicit_approval_policy(_text("skills/office/SKILL.md"))


def test_obsidian_direct_mutations_require_explicit_approval() -> None:
    _assert_explicit_approval_policy(_text("skills/obsidian-direct/SKILL.md"))


def test_apple_calendar_mutations_require_explicit_approval() -> None:
    _assert_explicit_approval_policy(_text("skills/apple-calendar/SKILL.md"))


def test_browser_external_action_requires_explicit_human_approval() -> None:
    path = CHECKOUT / "harness" / "lib" / "ai_influence_youtube_report" / "automation_policy.py"
    spec = importlib.util.spec_from_file_location("audit_automation_policy", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    decision = module.decide_external_action(has_secret=True, logged_in=True, dry_run=False)
    assert decision["status"] == "blocked"
    assert "approval" in decision["reason"]


def _create_db(path: Path, value: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            "CREATE TABLE threads(id TEXT PRIMARY KEY, cwd TEXT, value TEXT);"
            "CREATE TABLE thread_dynamic_tools(id TEXT PRIMARY KEY, value TEXT);"
            "CREATE TABLE thread_goals(id TEXT PRIMARY KEY, value TEXT);"
            "CREATE TABLE user_owned(id TEXT PRIMARY KEY, value TEXT);"
        )
        conn.execute("INSERT INTO threads VALUES('t1','/source/project',?)", (value,))
        conn.execute("INSERT INTO thread_dynamic_tools VALUES('d1',?)", (value,))
        conn.execute("INSERT INTO thread_goals VALUES('g1',?)", (value,))
        conn.execute("INSERT INTO user_owned VALUES('u1','preserve')")


def test_codex_state_import_is_explicit_backs_up_and_preserves_unscoped_tables(tmp_path: Path) -> None:
    script = CHECKOUT / "harness" / "scripts" / "codex-state-portable-sync.py"
    source_db = tmp_path / "source.sqlite"
    target_db = tmp_path / "target.sqlite"
    exported = tmp_path / "state.json"
    backups = tmp_path / "backups"
    _create_db(source_db, "incoming")
    _create_db(target_db, "existing")

    export_proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "export",
            "--db",
            str(source_db),
            "--out",
            str(exported),
            "--from-prefix",
            "/source",
            "--to-prefix",
            "/portable",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert export_proc.returncode == 0, export_proc.stdout + export_proc.stderr
    with sqlite3.connect(target_db) as conn:
        assert conn.execute("SELECT value FROM threads WHERE id='t1'").fetchone()[0] == "existing"

    import_proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "import",
            "--db",
            str(target_db),
            "--input",
            str(exported),
            "--backup-dir",
            str(backups),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert import_proc.returncode == 0, import_proc.stdout + import_proc.stderr
    result = json.loads(import_proc.stdout)
    assert Path(result["backup"]).exists()
    with sqlite3.connect(target_db) as conn:
        assert conn.execute("SELECT value FROM threads WHERE id='t1'").fetchone()[0] == "incoming"
        assert conn.execute("SELECT cwd FROM threads WHERE id='t1'").fetchone()[0] == "/portable/project"
        assert conn.execute("SELECT value FROM user_owned WHERE id='u1'").fetchone()[0] == "preserve"
