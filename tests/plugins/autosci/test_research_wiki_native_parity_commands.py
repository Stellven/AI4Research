from __future__ import annotations

import json
import subprocess
import sys
from textwrap import dedent
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
TOOL = REPO / "tools" / "research_wiki.py"


def run_tool(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def payload(proc: subprocess.CompletedProcess[str]) -> dict:
    assert proc.returncode == 0, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert isinstance(result, dict)
    return result


def write_page(path: Path, frontmatter: str, body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{dedent(frontmatter).strip()}\n---\n{dedent(body)}", encoding="utf-8")


def test_research_wiki_add_citation_and_dedup(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    payload(run_tool(tmp_path, "init", str(wiki)))
    write_page(wiki / "papers/source.md", "title: Source\nslug: source\ntags: []\nimportance: 3\n")
    write_page(wiki / "papers/target.md", "title: Target\nslug: target\ntags: []\nimportance: 3\n")

    first = payload(run_tool(tmp_path, "add-citation", str(wiki), "--from", "papers/source", "--to", "papers/target"))
    second = payload(run_tool(tmp_path, "add-citation", str(wiki), "--from", "papers/source", "--to", "papers/target"))

    assert first["status"] == "ok"
    assert second["status"] == "exists"
    citations_path = wiki / "graph" / "citations.jsonl"
    line = citations_path.read_text(encoding="utf-8").splitlines()[0]
    citations_path.write_text(line + "\n" + line + "\n", encoding="utf-8")

    deduped = payload(run_tool(tmp_path, "dedup-citations", str(wiki)))

    assert deduped["status"] == "ok"
    assert deduped["kept"] == 1
    assert deduped["removed"] == 1


def test_research_wiki_legal_and_illegal_transition(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    payload(run_tool(tmp_path, "init", str(wiki)))
    idea = wiki / "ideas" / "agentic-workflow.md"
    write_page(
        idea,
        """
        title: Agentic Workflow
        slug: agentic-workflow
        status: proposed
        origin: test
        tags: []
        priority: 3
        linked_experiments: [experiments/agentic-workflow]
        """,
    )

    legal = payload(run_tool(tmp_path, "transition", str(idea), "--to", "in_progress"))
    illegal = run_tool(tmp_path, "transition", str(idea), "--to", "validated")

    assert legal["status"] == "ok"
    assert legal["old_status"] == "proposed"
    assert legal["new_status"] == "in_progress"
    assert illegal.returncode == 1
    assert "Invalid: in_progress -> validated" in illegal.stdout


def test_research_wiki_checkpoint_save_load_clear(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    payload(run_tool(tmp_path, "init", str(wiki)))

    payload(run_tool(tmp_path, "checkpoint-save", str(wiki), "init-001", "paper-a"))
    payload(run_tool(tmp_path, "checkpoint-save", str(wiki), "init-001", "paper-b", "--failed"))
    payload(run_tool(tmp_path, "checkpoint-set-meta", str(wiki), "init-001", "stash_ref", "stash@{0}"))

    loaded = payload(run_tool(tmp_path, "checkpoint-load", str(wiki), "init-001"))
    assert loaded["exists"] is True
    assert loaded["completed"] == ["paper-a"]
    assert loaded["failed"] == ["paper-b"]
    assert loaded["metadata"]["stash_ref"] == "stash@{0}"

    payload(run_tool(tmp_path, "checkpoint-clear", str(wiki), "init-001"))
    missing = payload(run_tool(tmp_path, "checkpoint-load", str(wiki), "init-001"))
    assert missing["exists"] is False


def test_research_wiki_compile_context_and_rebuild_open_questions(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    payload(run_tool(tmp_path, "init", str(wiki)))
    write_page(
        wiki / "topics" / "agentic-science.md",
        "title: Agentic Science\ntags: []\n",
        "# Agentic Science\n\n## Open problems\n\n- How should evidence gates compose across agents?\n",
    )

    open_questions = payload(run_tool(tmp_path, "rebuild-open-questions", str(wiki)))
    context = payload(run_tool(tmp_path, "compile-context", str(wiki), "--for", "ideation", "--max-chars", "4000"))

    assert open_questions["status"] == "ok"
    assert open_questions["gaps"] == 1
    assert context["status"] == "ok"
    open_questions_text = (wiki / "graph" / "open_questions.md").read_text(encoding="utf-8")
    context_text = (wiki / "graph" / "context_brief.md").read_text(encoding="utf-8")
    assert "evidence gates compose" in open_questions_text
    assert "Open Gaps" in context_text
    assert "evidence gates compose" in context_text
