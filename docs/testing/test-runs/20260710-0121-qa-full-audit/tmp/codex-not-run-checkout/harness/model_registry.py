#!/usr/bin/env python3
"""Solar-Harness model registry helper.

All model alias, display, matrix, and footer key decisions should flow through
config/model-registry.json.  Shell callers use this tiny helper instead of
duplicating case blocks.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


HARNESS_DIR = Path(__file__).resolve().parents[1]
REGISTRY_PATH = HARNESS_DIR / "config" / "model-registry.json"


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def alias_map(reg: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for model_id, spec in (reg.get("models") or {}).items():
        out[model_id.lower()] = model_id
        for alias in spec.get("aliases") or []:
            out[str(alias).lower()] = model_id
    return out


def clean_alias(value: str) -> str:
    return str(value or "").strip().lower()


def normalize(reg: dict[str, Any], alias: str) -> str:
    value = clean_alias(alias)
    if not re.match(r"^[a-z0-9_.-]+$", value or ""):
        raise SystemExit(f"unsupported model alias: {alias or '<empty>'}")
    model_id = alias_map(reg).get(value)
    if not model_id:
        raise SystemExit(f"unsupported model alias: {alias or '<empty>'}")
    return model_id


def spec(reg: dict[str, Any], alias_or_id: str) -> dict[str, Any]:
    model_id = normalize(reg, alias_or_id)
    item = dict((reg.get("models") or {})[model_id])
    item["id"] = model_id
    return item


def matrix_items(value: str) -> list[str]:
    return [x.strip() for x in str(value or "").split(",") if x.strip()]


def validate_matrix(reg: dict[str, Any], matrix: str) -> str:
    items = matrix_items(matrix)
    if not items:
        raise SystemExit("empty lab builder matrix")
    for item in items:
        s = spec(reg, item)
        if not s.get("lab_allowed"):
            raise SystemExit(f"model not allowed in lab matrix: {item}")
    return matrix


def matrix_label(reg: dict[str, Any], matrix: str) -> str:
    ids = [spec(reg, item)["id"] for item in matrix_items(matrix)]
    labels = [(reg["models"][mid].get("label") or mid) for mid in ids]
    counts = Counter(labels)
    parts: list[str] = []
    seen: set[str] = set()
    for label in labels:
        if label in seen:
            continue
        seen.add(label)
        n = counts[label]
        parts.append(f"{n} {label}" if n > 1 else label)
    return " + ".join(parts) if parts else "N/A"


def cmd_options(reg: dict[str, Any]) -> None:
    payload = {
        "models": [
            {
                "value": (item.get("aliases") or [model_id])[0],
                "id": model_id,
                "label": item.get("label", model_id),
                "main_allowed": bool(item.get("main_allowed")),
                "lab_allowed": bool(item.get("lab_allowed")),
                "aliases": item.get("aliases") or [],
            }
            for model_id, item in (reg.get("models") or {}).items()
        ],
        "matrix_options": reg.get("matrix_options") or [],
    }
    print(json.dumps(payload, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default=str(REGISTRY_PATH))
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("normalize", "label", "short-label", "provider", "model-flag", "model-key"):
        p = sub.add_parser(name)
        p.add_argument("alias")
    p = sub.add_parser("validate-main")
    p.add_argument("alias")
    p = sub.add_parser("validate-lab-matrix")
    p.add_argument("matrix")
    p = sub.add_parser("matrix-label")
    p.add_argument("matrix")
    p = sub.add_parser("matrix-item")
    p.add_argument("matrix")
    p.add_argument("index", type=int)
    p = sub.add_parser("default")
    p.add_argument("key")
    sub.add_parser("options")
    args = ap.parse_args(argv)

    reg = load_registry(Path(args.registry))
    if args.cmd == "normalize":
        print(normalize(reg, args.alias))
    elif args.cmd == "label":
        print(spec(reg, args.alias).get("label", "N/A"))
    elif args.cmd == "short-label":
        print(spec(reg, args.alias).get("short_label", spec(reg, args.alias).get("label", "N/A")))
    elif args.cmd == "provider":
        print(spec(reg, args.alias).get("provider", ""))
    elif args.cmd == "model-flag":
        print(spec(reg, args.alias).get("model_flag", ""))
    elif args.cmd == "model-key":
        print(spec(reg, args.alias).get("model_key", normalize(reg, args.alias)))
    elif args.cmd == "validate-main":
        s = spec(reg, args.alias)
        if not s.get("main_allowed"):
            raise SystemExit(f"model not allowed on main panes: {args.alias}")
        print(s["id"])
    elif args.cmd == "validate-lab-matrix":
        print(validate_matrix(reg, args.matrix))
    elif args.cmd == "matrix-label":
        print(matrix_label(reg, args.matrix))
    elif args.cmd == "matrix-item":
        items = matrix_items(args.matrix)
        if not items:
            print("N/A")
        elif args.index < len(items):
            print(normalize(reg, items[args.index]))
        else:
            print(normalize(reg, items[-1]))
    elif args.cmd == "default":
        value = (reg.get("defaults") or {}).get(args.key)
        if value is None:
            raise SystemExit(f"unknown default: {args.key}")
        print(value)
    elif args.cmd == "options":
        cmd_options(reg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
