"""
dispatch_prompt_injector — Inject DeepResearch hard rules into research node dispatches.

When the coordinator dispatches a research node (node ID starting with "R"),
this module appends 4 non-negotiable rules to the dispatch text before it
reaches the builder pane. This is a structural enforcement layer, not a
prompt suggestion — the rules come from the S01 stop_rules document.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RESEARCH_RULES = """\

<!-- research-hard-rules (auto-injected by dispatch_prompt_injector) -->

## DeepResearch Hard Rules (Non-Negotiable)

These rules are injected automatically when a research node is dispatched.
Violation requires immediate halt and rollback to the specified recovery node.

### Rule 1: No Unsupported Claims
No key claim (`is_key=true`) in the final report may lack an `evidence_id` link.
The `unsupported_claim_rate` for key claims MUST be ≤ 5%.
**Violation → rollback to R4_claim_mining**

### Rule 2: No Missing span_text
Every citation must include the original source `span_text` — the exact quoted
passage from the source document. Citations without `span_text` are considered
unsupported and count toward the unsupported_claim_rate.
**Violation → rollback to R2_external_search**

### Rule 3: No Silent Connector Fallback
When a Source Mesh connector fails (network error, API limit, parse failure),
the system MUST NOT silently fall back to generating content from parametric
knowledge. Failed connectors must be explicitly marked as degraded.
**Violation → rollback to R2_external_search**

### Rule 4: No Single-Node 100K Report
A report exceeding 100,000 characters MUST NOT be assigned to a single DAG node
or a single builder pane invocation. Use section decomposition (30-40 sections
of 2,000-4,000 words each) via the task graph.
**Violation → rollback to R6_report_ast"""

_RULE_MARKERS = [
    "unsupported claim",
    "span_text",
    "connector",
    "100k",
]


def inject_research_rules(text: str, node_id: str) -> str:
    """Append DeepResearch hard rules to dispatch text if node_id is a research node.

    Args:
        text: The original dispatch text.
        node_id: The DAG node identifier (e.g. "R4_claim_mining", "N5").

    Returns:
        The dispatch text with research rules appended if node_id starts with "R",
        otherwise the original text unchanged.
    """
    if not node_id or not node_id.startswith("R"):
        return text

    marker = "<!-- research-hard-rules"
    if marker in text:
        return text

    return text.rstrip() + "\n" + RESEARCH_RULES + "\n"


def inject_file(dispatch_file: str | Path, node_id: str) -> bool:
    """Read a dispatch file, inject research rules if applicable, write back.

    Args:
        dispatch_file: Path to the dispatch markdown file.
        node_id: The DAG node identifier.

    Returns:
        True if rules were injected, False if skipped (non-research node or already present).
    """
    path = Path(dispatch_file)
    if not path.exists():
        return False

    original = path.read_text(encoding="utf-8")
    modified = inject_research_rules(original, node_id)

    if modified is original:
        return False

    path.write_text(modified, encoding="utf-8")
    return True


def verify_rules_present(text: str) -> list[str]:
    """Verify all 4 rule markers are present in text.

    Returns:
        List of missing marker descriptions. Empty list means all rules present.
    """
    missing = []
    for marker in _RULE_MARKERS:
        if marker.lower() not in text.lower():
            missing.append(marker)
    return missing


def main() -> None:
    """CLI entry point: inject_file <dispatch_file> <node_id>"""
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <dispatch_file> <node_id>", file=sys.stderr)
        sys.exit(1)

    dispatch_file = sys.argv[1]
    node_id = sys.argv[2]

    injected = inject_file(dispatch_file, node_id)
    if injected:
        print(f"ok: research rules injected for node {node_id}")
    else:
        print(f"skip: node {node_id} is not a research node or rules already present")
    sys.exit(0)


if __name__ == "__main__":
    main()
