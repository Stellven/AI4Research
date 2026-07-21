from __future__ import annotations

import ast
import csv
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from functools import lru_cache
from pathlib import Path


STOP = {
    "a", "an", "and", "any", "are", "as", "at", "be", "before", "but", "by",
    "does", "do", "for", "from", "has", "have", "if", "in", "into", "is", "it",
    "its", "no", "not", "of", "on", "only", "or", "other", "out", "reports",
    "required", "returns", "run", "runs", "state", "that", "the", "their", "to",
    "unless", "when", "where", "with", "without", "workflow", "expected", "correct",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def tokens(value: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", value.lower().replace("inconclusive", "inconclusive failed"))
    return {word for word in words if len(word) >= 3 and word not in STOP}


def junit_index(root: Path) -> dict[tuple[str, str], list[tuple[str, str]]]:
    index: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    paths = sorted(root.glob("**/*.xml"), key=lambda path: path.stat().st_mtime)
    for path in paths:
        try:
            testcases = ET.parse(path).getroot().iter("testcase")
        except ET.ParseError:
            continue
        for testcase in testcases:
            classname = testcase.attrib.get("classname", "")
            name = testcase.attrib.get("name", "")
            status = "PASS"
            if testcase.find("failure") is not None or testcase.find("error") is not None:
                status = "FAIL"
            elif testcase.find("skipped") is not None:
                status = "SKIP"
            module = classname.rsplit(".", 1)[-1]
            test_name = name.split("[", 1)[0]
            index[(module, test_name)].append((status, str(path.relative_to(root.parents[1]))))
    return index


@lru_cache(maxsize=None)
def find_test_body(path: Path, test_name: str) -> str:
    if path.suffix != ".py" or not path.exists():
        return ""
    source = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == test_name:
            return ast.get_source_segment(source, node) or ""
    return ""


def surface_tokens(feature_path: str) -> set[str]:
    surface = feature_path.split(">", 1)[0]
    payload = surface.split(":", 1)[1] if ":" in surface else surface
    generic = {
        "autosci", "bridge", "route", "action", "slash", "foundation", "surface",
        "skill", "integration", "workflow", "installer", "packaging", "research",
        "source", "ingestion", "command", "cli", "lifecycle", "component", "tool",
    }
    return tokens(payload) - generic


def candidate_for(
    reference: str,
    feature: dict[str, str],
    checkout: Path,
    results: dict[tuple[str, str], list[tuple[str, str]]],
) -> dict[str, str] | None:
    parts = [part.strip() for part in reference.split("::") if part.strip()]
    if len(parts) < 2 or not parts[0].endswith(".py"):
        return None
    relative = parts[0]
    test_name = parts[-1].split("[", 1)[0]
    if not test_name.startswith("test"):
        return None
    module = Path(relative).stem
    outcomes = results.get((module, test_name), [])
    if not outcomes:
        return None
    latest_status, evidence = outcomes[-1]
    if latest_status != "PASS":
        return None
    body = find_test_body(checkout / relative, test_name)
    if not body or not re.search(r"\bassert\b|pytest\.raises|self\.assert", body):
        return None

    atomic = tokens(feature["atomic_feature"])
    surface = surface_tokens(feature["feature_path"])
    name_path = tokens(relative + " " + test_name)
    name_body = tokens(test_name + " " + body)
    atomic_overlap = sorted(atomic & name_body)
    surface_overlap = sorted(surface & name_path)

    # A direct proof needs both the behavior and its concrete product surface.
    # Two distinctive behavior terms are sufficient; otherwise require one
    # behavior term plus two surface identifiers. This intentionally rejects
    # generic file-level PASS results.
    needed_surface = 0 if not surface else min(2, len(surface))
    direct = len(atomic_overlap) >= 2 and len(surface_overlap) >= needed_surface
    if not direct:
        return None
    return {
        "testcase": reference,
        "atomic_overlap": ";".join(atomic_overlap),
        "surface_overlap": ";".join(surface_overlap),
        "junit_evidence": evidence,
        "assertion_present": "yes",
    }


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    checkout = Path(sys.argv[2]).resolve()
    phase_rows = read_csv(root / "evidence/codex-not-run-phase/codex-not-run-feature-results.csv")
    result_index = junit_index(root / "evidence/codex-not-run-phase")
    direct_family_files = [
        "harness/plugins/autosci/tests/test_autosci_skill_shim.py",
        "harness/plugins/autosci/tests/test_phase19_parity_bridge.py",
        "harness/plugins/autosci/tests/test_bridge_smoke.py",
        "harness/plugins/autosci/tests/test_root_tool_abi.py",
        "harness/plugins/autosci/tests/test_autosci_parity_inventory_tool.py",
    ]
    family_references: list[str] = []
    for relative in direct_family_files:
        path = checkout / relative
        tree = ast.parse(path.read_text(encoding="utf-8"))
        family_references.extend(
            f"{relative}::{node.name}"
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test")
        )
    output: list[dict[str, str]] = []
    for feature in phase_rows:
        if feature["test_result_status"] != "INCONCLUSIVE_EXPECTED":
            continue
        matches = []
        references = [item for item in feature.get("selected_testcases", "").split(";") if item.strip()]
        if feature["feature_path"].startswith(
            ("AutoSci slash workflow:", "AutoSci bridge action workflow:", "AutoSci route action workflow:", "Bridge/route foundation:")
        ):
            references.extend(family_references)
        for reference in references:
            reference = reference.strip()
            if reference:
                candidate = candidate_for(reference, feature, checkout, result_index)
                if candidate:
                    matches.append(candidate)
        best = matches[0] if matches else {}
        output.append(
            {
                "feature_id": feature["feature_id"],
                "feature_path": feature["feature_path"],
                "atomic_feature": feature["atomic_feature"],
                "decision": "DIRECT_PASS_CANDIDATE" if matches else "NEEDS_NEW_DIRECT_TEST",
                "direct_testcase_count": str(len(matches)),
                "direct_testcases": "; ".join(item["testcase"] for item in matches),
                "atomic_overlap": best.get("atomic_overlap", ""),
                "surface_overlap": best.get("surface_overlap", ""),
                "junit_evidence": "; ".join(sorted({item["junit_evidence"] for item in matches})),
                "rationale": (
                    "Concrete passed testcase contains assertions and directly overlaps both the atomic behavior and product surface."
                    if matches
                    else "No previously executed passed assertion met the conservative directness threshold."
                ),
            }
        )
    target = root / "evidence/codex-not-run-phase/direct-existing-evidence-adjudication.csv"
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output[0]))
        writer.writeheader()
        writer.writerows(output)
    direct = sum(row["decision"] == "DIRECT_PASS_CANDIDATE" for row in output)
    print(f"inconclusive={len(output)} direct_pass_candidates={direct} needs_new_direct_test={len(output)-direct}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
