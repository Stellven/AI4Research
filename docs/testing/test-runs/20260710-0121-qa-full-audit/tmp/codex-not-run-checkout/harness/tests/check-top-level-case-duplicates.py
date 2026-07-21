#!/usr/bin/env python3
"""
check-top-level-case-duplicates.py — verify no duplicate top-level case branches.

Usage: python3 check-top-level-case-duplicates.py <shell_script>

Exit 0 if no duplicates found; exit 1 if duplicates detected.
"""
import re
import sys
from pathlib import Path


def find_top_level_case_labels(path: Path) -> dict[str, list[int]]:
    """
    Find case labels at the top-level case..esac block.
    A top-level label is a line matching /^  <word>)/ inside the outermost case block.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    # Find the outermost case statement (case "$1" in or similar)
    in_case = False
    case_depth = 0
    labels: dict[str, list[int]] = {}

    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()

        # Detect top-level case opening (case ... in, not inside a function yet)
        if re.match(r'^case\s+', line) and line.rstrip().endswith(' in'):
            if not in_case:
                in_case = True
                case_depth = 1
                continue
            else:
                case_depth += 1
                continue

        if in_case:
            # Nested case opens
            if re.match(r'\s+case\s+', line) and line.rstrip().endswith(' in'):
                case_depth += 1
                continue
            # Nested esac closes
            if re.match(r'\s*esac\b', line):
                case_depth -= 1
                if case_depth == 0:
                    in_case = False
                continue

            # Top-level labels: exactly 2-space indent + word + )
            if case_depth == 1:
                m = re.match(r'^  ([a-zA-Z][a-zA-Z0-9_-]*)\)$', line)
                if m:
                    label = m.group(1)
                    labels.setdefault(label, []).append(lineno)

    return labels


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: check-top-level-case-duplicates.py <shell_script>", file=sys.stderr)
        return 1

    script_path = Path(sys.argv[1])
    if not script_path.exists():
        print(f"file not found: {script_path}", file=sys.stderr)
        return 1

    labels = find_top_level_case_labels(script_path)
    duplicates = {label: lines for label, lines in labels.items() if len(lines) > 1}

    if duplicates:
        print(f"FAIL: found {len(duplicates)} duplicate top-level case branch(es):")
        for label, lines in sorted(duplicates.items()):
            print(f"  '{label}' appears at lines: {', '.join(map(str, lines))}")
        return 1

    total = len(labels)
    print(f"PASS: no duplicate top-level case branches ({total} unique labels)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
