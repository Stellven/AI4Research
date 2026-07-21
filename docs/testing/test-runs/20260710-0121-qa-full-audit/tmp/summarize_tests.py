from __future__ import annotations

import csv
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


def testcase_path(case: ET.Element) -> str:
    if case.get("file"):
        return case.get("file", "")
    classname = case.get("classname", "")
    if classname.startswith("harness.") or classname.startswith("tests.") or classname.startswith("distribution."):
        return classname.replace(".", "/") + ".py"
    return classname


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    inputs = [
        ("scientific_evaluators", root / "evidence/pytest/scientific-evaluators-final.xml"),
        ("autosci_plugin", root / "evidence/pytest/autosci-plugin-final.xml"),
    ]
    matrix = root / "evidence/pytest-matrix-installed-home"
    inputs.extend((f"pytest_matrix:{path.stem}", path) for path in sorted(matrix.glob("*.xml")))
    rows: list[dict[str, str]] = []
    by_suite: dict[str, Counter[str]] = {}
    for suite, path in inputs:
        if not path.exists():
            continue
        tree = ET.parse(path)
        counter: Counter[str] = Counter()
        for case in tree.iter("testcase"):
            status = "PASS"
            detail = ""
            for tag, value in (("failure", "FAIL"), ("error", "ERROR"), ("skipped", "SKIPPED")):
                node = case.find(tag)
                if node is not None:
                    status = value
                    detail = (node.get("message") or node.text or "").strip().replace("\n", " ")[:1000]
                    break
            counter[status] += 1
            rows.append({
                "suite": suite,
                "test_file": testcase_path(case),
                "classname": case.get("classname", ""),
                "testcase": case.get("name", ""),
                "status": status,
                "time_seconds": case.get("time", ""),
                "detail": detail,
                "junit_path": str(path.relative_to(root)),
            })
        by_suite[suite] = counter
    out_csv = root / "evidence/testcase-results.csv"
    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["suite"])
        writer.writeheader()
        writer.writerows(rows)
    totals = Counter(row["status"] for row in rows)
    summary = {
        "scope": "authoritative final deterministic JUnit runs only; earlier confounded runs excluded",
        "totals": dict(totals),
        "suites": {name: dict(counts) for name, counts in sorted(by_suite.items())},
        "junit_inputs": [str(path.relative_to(root)) for _, path in inputs if path.exists()],
    }
    (root / "evidence/test-execution-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary["totals"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
