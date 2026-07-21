"""golden_cases.py — Load accepted sprint artifacts as golden test cases.

Source: ``~/Knowledge/_raw/solar-harness/accepted/`` (accepted sprint files).

Each ``GoldenCase`` extracts requirement text, IR structure, contracts,
and DAG from ``.accepted.md`` files for use in GEPA fitness evaluation.
"""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Any, Optional


_ACCEPTED_DIR = Path.home() / "Knowledge" / "_raw" / "solar-harness" / "accepted"


@dataclasses.dataclass
class GoldenCase:
    """A single golden test case extracted from an accepted sprint."""

    sprint_id: str
    input: str  # requirement text
    expected_ir: dict[str, Any]
    expected_contracts: list[dict[str, Any]]
    expected_dag: dict[str, Any]


def load_golden_cases(
    limit: int = 10,
    *,
    accepted_dir: Optional[Path] = None,
) -> list[GoldenCase]:
    """Load golden cases from accepted sprint artifacts.

    Parameters
    ----------
    limit : int
        Maximum number of cases to return.
    accepted_dir : Path, optional
        Override the default accepted artifacts directory.

    Returns
    -------
    list[GoldenCase]
    """
    base = accepted_dir or _ACCEPTED_DIR
    if not base.exists():
        return []

    accepted_files = sorted(base.glob("*.accepted.md"))
    cases: list[GoldenCase] = []

    for fpath in accepted_files:
        if len(cases) >= limit:
            break
        case = _parse_accepted_file(fpath)
        if case is not None:
            cases.append(case)

    return cases


# ---------------------------------------------------------------------------
# Internal parsing helpers
# ---------------------------------------------------------------------------

def _parse_accepted_file(fpath: Path) -> Optional[GoldenCase]:
    """Parse a single .accepted.md file into a GoldenCase."""
    try:
        text = fpath.read_text(encoding="utf-8")
    except OSError:
        return None

    sprint_id = _extract_sprint_id(fpath.name)
    if not sprint_id:
        return None

    # Extract requirement text from frontmatter or body
    requirement_text = _extract_requirement_text(text)
    if not requirement_text:
        return None

    # Build expected IR from the extracted data
    expected_ir = _build_expected_ir(text, requirement_text)
    expected_contracts = _build_expected_contracts(text)
    expected_dag = _build_expected_dag(text)

    return GoldenCase(
        sprint_id=sprint_id,
        input=requirement_text,
        expected_ir=expected_ir,
        expected_contracts=expected_contracts,
        expected_dag=expected_dag,
    )


def _extract_sprint_id(filename: str) -> str:
    """Extract sprint ID from filename like 'sprint-20260414-084605.accepted.md'."""
    match = re.match(r"(sprint-\d{8}-\d{6})\.accepted\.md", filename)
    return match.group(1) if match else ""


def _extract_requirement_text(text: str) -> str:
    """Extract the requirement/user need text from the accepted file."""
    # Try to find the "需求" section (Chinese for "requirement")
    patterns = [
        r"##\s*需求\s*\n(.+?)(?=\n##|\n##\s*Done|\n##\s*范围|\Z)",
        r"##\s*User Need.*?\n(.+?)(?=\n##|\Z)",
        r"##\s*Executive Summary\s*\n\s*-\s*.*?\n(.+?)(?=\n##|\Z)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            content = match.group(1).strip()
            if content:
                return content[:2000]  # cap size

    # Fallback: use title
    title_match = re.search(r'^title:\s*"(.+?)"', text, re.MULTILINE)
    if title_match:
        return title_match.group(1)

    return ""


def _build_expected_ir(text: str, requirement_text: str) -> dict[str, Any]:
    """Build an expected IR dict from the accepted file content."""
    ir: dict[str, Any] = {
        "goal": requirement_text[:500],
    }

    # Extract Done definitions as success_metrics
    done_matches = re.findall(
        r"\*\*D\d+[^*]*\*\*:\s*(.+?)(?=\n[-*]|\n##|\Z)", text, re.DOTALL
    )
    if done_matches:
        ir["success_metrics"] = [m.strip() for m in done_matches]
    else:
        ir["success_metrics"] = []

    # Extract scope exclusions as non_goals
    scope_match = re.search(
        r"不包含:\s*\n((?:\s*[-*]\s+.+\n?)+)", text
    )
    if scope_match:
        items = re.findall(r"[-*]\s+(.+)", scope_match.group(1))
        ir["non_goals"] = items
    else:
        ir["non_goals"] = []

    return ir


def _build_expected_contracts(text: str) -> list[dict[str, Any]]:
    """Build expected contracts from the accepted file content."""
    contracts: list[dict[str, Any]] = []

    # Extract acceptance criteria from Done definitions
    done_items = re.findall(
        r"\*\*(D\d+[^*]*)\*\*:\s*(.+?)(?=\n[-*]|\n##|\Z)", text, re.DOTALL
    )
    acceptance: dict[str, str] = {}
    for label, desc in done_items:
        acceptance[label.strip()] = desc.strip()

    if acceptance:
        contracts.append({
            "goal": "",
            "policies": {
                "intake_policy": {"version": "1.0", "params": {}},
                "requirement_ir_policy": {"version": "1.0", "params": {}},
                "contract_compiler_policy": {"version": "1.0", "params": {}},
                "dag_compiler_policy": {"version": "1.0", "params": {}},
                "evidence_policy": {"version": "1.0", "params": {}},
                "handoff_policy": {"version": "1.0", "params": {}},
            },
            "acceptance": acceptance,
        })

    return contracts


def _build_expected_dag(text: str) -> dict[str, Any]:
    """Build expected DAG from the accepted file content."""
    # Extract node-like structures from Done definitions
    done_items = re.findall(
        r"\*\*(D\d+[^*]*)\*\*:\s*(.+?)(?=\n[-*]|\n##|\Z)", text, re.DOTALL
    )

    nodes: list[dict[str, Any]] = []
    for i, (label, desc) in enumerate(done_items):
        node_id = label.strip().split()[0]  # e.g., "D1"
        depends_on = []
        if i > 0:
            prev_id = done_items[i - 1][0].strip().split()[0]
            depends_on = [prev_id]

        nodes.append({
            "id": node_id,
            "goal": desc.strip()[:200],
            "depends_on": depends_on,
            "write_scope": True,
            "type": "task",
        })

    return {"nodes": nodes}
