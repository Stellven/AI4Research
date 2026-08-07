#!/usr/bin/env python3
"""Report deterministic statistics for a JSON Lines stream."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from typing import Iterable, Mapping, Optional, Sequence


def _reject_nonstandard_constant(value: str) -> None:
    """Reject numeric constants that are accepted by Python but not by JSON."""

    raise ValueError(f"non-standard numeric constant {value}")


def count_keys(lines: Iterable[str], strict: bool = False) -> Mapping[str, object]:
    """Count top-level keys across valid JSON object rows in a JSONL stream.

    Empty lines, malformed JSON, and valid JSON values that are not objects are
    invalid rows. In strict mode the first such row raises ``ValueError``.
    """

    key_counts: Counter[str] = Counter()
    row_count = 0
    invalid_row_count = 0

    for line_no, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            invalid_row_count += 1
            if strict:
                raise ValueError(f"invalid JSON at line {line_no}: empty line")
            continue

        try:
            value = json.loads(line, parse_constant=_reject_nonstandard_constant)
        except ValueError as exc:
            invalid_row_count += 1
            if strict:
                message = getattr(exc, "msg", str(exc))
                raise ValueError(f"invalid JSON at line {line_no}: {message}") from None
            continue

        if not isinstance(value, dict):
            invalid_row_count += 1
            if strict:
                raise ValueError(f"invalid JSON object at line {line_no}: got {type(value).__name__}")
            continue

        row_count += 1
        key_counts.update(value.keys())

    sorted_keys = {
        key: key_counts[key]
        for key in sorted(key_counts)
    }
    return {
        "row_count": row_count,
        "invalid_row_count": invalid_row_count,
        "key_frequencies": sorted_keys,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Count top-level JSON keys in a JSON Lines stream."
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="Path to a JSON Lines file. Omit to read from stdin.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on first invalid JSON line.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    if args.path is None or args.path == "-":
        try:
            payload = count_keys(sys.stdin, strict=args.strict)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        return 0

    try:
        with open(args.path, "r", encoding="utf-8") as source:
            payload = count_keys(source, strict=args.strict)
    except (OSError, UnicodeError) as exc:
        print(f"jsonl_stats: cannot read input: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
