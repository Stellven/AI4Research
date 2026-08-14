from __future__ import annotations

import json
import subprocess
from pathlib import Path


ENTRYPOINT = Path("core/smi/code-graph.mjs")
REPO_ROOT = Path(__file__).resolve().parents[3]


def _run(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(repo_root / ENTRYPOINT), *args],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )


def _project(root: Path) -> None:
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "score.py").write_text(
        "def public_score(value: int) -> int:\n    return value * 2\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_score.py").write_text(
        "from src.score import public_score\n\ndef test_score():\n    assert public_score(2) == 4\n",
        encoding="utf-8",
    )
    (root / "src" / "rank.ts").write_text(
        "export function rankScore(value: number): number { return value * 3; }\n",
        encoding="utf-8",
    )
    (root / "tests" / "rank.test.ts").write_text(
        'import { rankScore } from "../src/rank";\n'
        'test("ranks a score", () => { if (rankScore(2) !== 6) throw new Error("bad score"); });\n',
        encoding="utf-8",
    )
    (root / "package.json").write_text(
        json.dumps({"scripts": {"test": "bun test tests/rank.test.ts"}}),
        encoding="utf-8",
    )


def test_code_graph_build_query_and_validate_production_entrypoint(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _project(project)
    graph_path = tmp_path / "code-graph.json"
    validation_path = tmp_path / "validation.json"
    query_path = tmp_path / "query.json"

    built = _run(
        REPO_ROOT,
        "build",
        "--root",
        str(project),
        "--out",
        str(graph_path),
        "--runtime-command",
        "python -m pytest tests/test_score.py",
    )
    assert built.returncode == 0, built.stderr
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    assert len(graph["graph_sha256"]) == 64
    assert {node["kind"] for node in graph["nodes"]} >= {"file", "module", "api", "function", "test", "runtime"}
    relation_types = {edge["type"] for edge in graph["edges"]}
    assert relation_types >= {
        "file_defines_module",
        "module_declares_api",
        "module_declares_function",
        "module_imports_module",
        "test_targets_module",
        "runtime_executes_module",
    }

    queried = _run(REPO_ROOT, "query", "--graph", str(graph_path), "--kind", "api", "--name", "public_score", "--out", str(query_path))
    assert queried.returncode == 0, queried.stderr
    query = json.loads(query_path.read_text(encoding="utf-8"))
    assert [node["name"] for node in query["nodes"]] == ["public_score"]

    validated = _run(
        REPO_ROOT,
        "validate",
        "--graph",
        str(graph_path),
        "--root",
        str(project),
        "--require-relation",
        "test_targets_module",
        "--require-relation",
        "runtime_executes_module",
        "--out",
        str(validation_path),
    )
    assert validated.returncode == 0, validated.stderr
    assert json.loads(validation_path.read_text(encoding="utf-8"))["valid"] is True


def test_code_graph_validation_rejects_source_and_graph_tampering(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _project(project)
    graph_path = tmp_path / "code-graph.json"
    assert _run(REPO_ROOT, "build", "--root", str(project), "--out", str(graph_path)).returncode == 0

    (project / "src" / "score.py").write_text("def changed():\n    return 0\n", encoding="utf-8")
    source_check = _run(REPO_ROOT, "validate", "--graph", str(graph_path), "--root", str(project))
    assert source_check.returncode == 2
    assert "Source hash mismatch: src/score.py" in source_check.stdout

    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    graph["edges"][0]["to"] = "module:missing"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    graph_check = _run(REPO_ROOT, "validate", "--graph", str(graph_path))
    assert graph_check.returncode == 2
    assert "Dangling edge" in graph_check.stdout
    assert "graph_sha256 does not match graph content" in graph_check.stdout
