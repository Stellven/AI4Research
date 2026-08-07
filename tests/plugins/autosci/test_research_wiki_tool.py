from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
TOOL = REPO / "tools" / "research_wiki.py"


def run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def payload(proc: subprocess.CompletedProcess[str]) -> dict:
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def test_research_wiki_tool_mutates_queries_and_rebuilds(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    (wiki / "ideas").mkdir(parents=True)
    (wiki / "experiments").mkdir()
    (wiki / "graph").mkdir()
    (wiki / "ideas/skillgen.md").write_text(
        "---\nentity_type: \"idea\"\n---\n# SkillGen Idea\n\nEvaluate generated skills with execution traces.\n",
        encoding="utf-8",
    )
    (wiki / "experiments/exp-skillgen.md").write_text(
        "# SkillGen Experiment\n\nRun generated skill benchmarks.\n",
        encoding="utf-8",
    )

    meta = payload(
        run_tool(
            "set-meta",
            "ideas/skillgen.md",
            "status=reviewed",
            "novelty_score=4",
            "--wiki-root",
            str(wiki),
            "--json",
        )
    )
    assert meta["ok"] is True
    assert meta["changed"] is True
    idea_text = (wiki / "ideas/skillgen.md").read_text(encoding="utf-8")
    assert 'status: "reviewed"' in idea_text
    assert "novelty_score: 4" in idea_text

    edge = payload(
        run_tool(
            "add-edge",
            "ideas/skillgen.md",
            "experiments/exp-skillgen.md",
            "--relation",
            "tests",
            "--edge-type",
            "experiment_link",
            "--evidence-id",
            "ev-runtime-1",
            "--wiki-root",
            str(wiki),
            "--json",
        )
    )
    assert edge["ok"] is True
    assert edge["changed"] is True
    assert "tests" in (wiki / "graph/edges.jsonl").read_text(encoding="utf-8")

    log = payload(
        run_tool(
            "log",
            "Reviewed SkillGen idea",
            "--event",
            "novelty",
            "--evidence-id",
            "ev-runtime-1",
            "--wiki-root",
            str(wiki),
            "--json",
        )
    )
    assert log["ok"] is True
    assert "Reviewed SkillGen idea" in (wiki / "log.md").read_text(encoding="utf-8")

    rebuilt = payload(run_tool("rebuild", "--wiki-root", str(wiki), "--json"))
    assert rebuilt["ok"] is True
    assert set(rebuilt["rebuilt_paths"]) == {"index.md", "graph/context_brief.md"}
    assert (wiki / "index.md").exists()
    assert (wiki / "graph/context_brief.md").exists()

    query = payload(run_tool("query", "SkillGen", "--wiki-root", str(wiki), "--json"))
    assert query["ok"] is True
    assert query["count"] >= 2
    hit_paths = {item["path"] for item in query["hits"]}
    assert {"ideas/skillgen.md", "experiments/exp-skillgen.md"}.issubset(hit_paths)

    neighbors = payload(run_tool("neighbors", "ideas/skillgen.md", "--wiki-root", str(wiki), "--json"))
    assert neighbors["ok"] is True
    assert neighbors["count"] == 1
    assert neighbors["neighbors"][0]["target"] == "experiments/exp-skillgen.md"

    resolved = payload(run_tool("resolve", "skillgen", "--wiki-root", str(wiki), "--json"))
    assert resolved["ok"] is True
    assert resolved["path"] == "ideas/skillgen.md"
    assert resolved["group"] == "ideas"
    assert resolved["status"] == "reviewed"
    assert resolved["novelty_score"] == 4
    assert resolved["frontmatter"]["entity_type"] == "idea"
    assert resolved["linked_experiments"] == ["experiments/exp-skillgen.md"]
    assert resolved["edge_count"] == 1
    assert resolved["edges"][0]["evidence_ids"] == ["ev-runtime-1"]
    assert any("Reviewed SkillGen idea" in item["text"] for item in resolved["log_matches"])

    stats = payload(run_tool("stats", "--wiki-root", str(wiki), "--json"))
    assert stats["ok"] is True
    assert stats["stats"]["page_count"] >= 4
    assert stats["stats"]["edge_count"] == 1
    assert stats["stats"]["edge_error_count"] == 0
