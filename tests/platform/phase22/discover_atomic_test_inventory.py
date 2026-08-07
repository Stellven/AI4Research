"""Discover repository executable-test selectors for Phase 22 atomic mapping.

The inventory is intentionally assertion-aware for Python: it records each
pytest selector together with a compact AST-derived behavior fingerprint.  It
also enumerates JavaScript/TypeScript, shell, and PowerShell test cases using
conservative naming patterns.  Discovery never promotes a case to atomic
coverage by itself; the atomic matrix builder still requires a defensible
feature/code-surface match.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[3]
PYTHON_TEST_RE = re.compile(r"(?:^|/)(?:test[-_][^/]+|[^/]+[-_]test)\.py$")
SCRIPT_TEST_RE = re.compile(
    r"(?:^|/)(?:test[-_][^/]+|[^/]+\.test)\.(?:js|mjs|cjs|ts|sh|ps1)$",
    re.IGNORECASE,
)
JS_CASE_RE = re.compile(r"\b(?:test|it)\s*\(\s*([\"'`])(.+?)\1", re.DOTALL)
JS_FUNCTION_RE = re.compile(r"\b(?:async\s+)?function\s+(test_[A-Za-z0-9_]+)\s*\(")
SHELL_FUNCTION_RE = re.compile(r"(?m)^\s*(test[_-][A-Za-z0-9_-]+)\s*\(\s*\)\s*\{")
POWERSHELL_CASE_RE = re.compile(r"(?im)^\s*It\s+([\"'])(.+?)\1")


def repository_files() -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    candidates = completed.stdout.decode("utf-8").split("\0")
    return sorted(
        item
        for item in candidates
        if item
        and item.replace("\\", "/").startswith("tests/")
        and not item.replace("\\", "/").startswith("tests/quarantine/")
        and "/fixtures/" not in item.replace("\\", "/")
        and (ROOT / item).is_file()
    )


def compact_text(values: Iterable[str], limit: int = 4000) -> str:
    text = " ".join(" ".join(values).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def python_behavior_fingerprint(node: ast.AST) -> str:
    tokens: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Assert):
            tokens.append(ast.unparse(child.test))
        elif isinstance(child, ast.Call):
            try:
                tokens.append(ast.unparse(child.func))
            except ValueError:
                pass
        elif isinstance(child, ast.Constant) and isinstance(child.value, str):
            tokens.append(child.value)
        elif isinstance(child, ast.Attribute):
            tokens.append(child.attr)
    return compact_text(tokens)


def discover_python(relative: str, text: str) -> tuple[list[dict], str | None]:
    try:
        tree = ast.parse(text, filename=relative)
    except SyntaxError as exc:
        return [], f"{exc.msg} at line {exc.lineno}"

    cases: list[dict] = []
    for top in tree.body:
        if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef)) and top.name.startswith("test"):
            cases.append(
                {
                    "selector": f"{relative}::{top.name}",
                    "case_name": top.name,
                    "class_name": None,
                    "line": top.lineno,
                    "behavior_fingerprint": python_behavior_fingerprint(top),
                }
            )
        elif isinstance(top, ast.ClassDef):
            for child in top.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name.startswith("test"):
                    cases.append(
                        {
                            "selector": f"{relative}::{top.name}::{child.name}",
                            "case_name": child.name,
                            "class_name": top.name,
                            "line": child.lineno,
                            "behavior_fingerprint": python_behavior_fingerprint(child),
                        }
                    )
    return cases, None


def discover_script(relative: str, text: str, suffix: str) -> list[dict]:
    if suffix in {".js", ".mjs", ".cjs", ".ts"}:
        names = [match.group(2).strip() for match in JS_CASE_RE.finditer(text)]
        names.extend(match.group(1) for match in JS_FUNCTION_RE.finditer(text))
        runner = "bun" if suffix == ".ts" else "node"
    elif suffix == ".ps1":
        names = [match.group(2).strip() for match in POWERSHELL_CASE_RE.finditer(text)]
        runner = "powershell"
    else:
        names = [match.group(1) for match in SHELL_FUNCTION_RE.finditer(text)]
        runner = "bash"

    if not names:
        names = [Path(relative).stem]
    seen: set[str] = set()
    cases = []
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        cases.append(
            {
                "selector": relative if len(names) == 1 else f"{relative}::{name}",
                "case_name": name,
                "class_name": None,
                "line": None,
                "behavior_fingerprint": compact_text([name, text], limit=4000),
                "runner": runner,
            }
        )
    return cases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("atomic_test_inventory.json"),
    )
    args = parser.parse_args()

    files = []
    cases = []
    parse_errors = []
    for relative in repository_files():
        normalized = relative.replace("\\", "/")
        if not (PYTHON_TEST_RE.search(normalized) or SCRIPT_TEST_RE.search(normalized)):
            continue
        path = ROOT / relative
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            parse_errors.append({"path": normalized, "error": str(exc)})
            continue

        suffix = path.suffix.lower()
        file_record = {
            "path": normalized,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "language": "python" if suffix == ".py" else suffix.lstrip("."),
        }
        if suffix == ".py":
            discovered, error = discover_python(normalized, text)
            runner = "pytest"
            if error:
                parse_errors.append({"path": normalized, "error": error})
            elif not discovered and "if __name__" in text and "assert " in text:
                discovered = [
                    {
                        "selector": normalized,
                        "case_name": path.stem,
                        "class_name": None,
                        "line": None,
                        "behavior_fingerprint": compact_text([path.stem, text], limit=4000),
                        "runner": "python",
                    }
                ]
                runner = "python"
        else:
            discovered = discover_script(normalized, text, suffix)
            runner = discovered[0]["runner"] if discovered else "unknown"

        for case in discovered:
            case.setdefault("runner", runner)
            case["path"] = normalized
            case["language"] = file_record["language"]
            cases.append(case)
        file_record["case_count"] = len(discovered)
        file_record["runner"] = runner
        files.append(file_record)

    payload = {
        "schema": "phase22.atomic_test_inventory.v1",
        "root": ".",
        "policy": "Discovery is not coverage; each selector requires atomic semantic review.",
        "counts": {
            "files": len(files),
            "cases": len(cases),
            "parse_errors": len(parse_errors),
        },
        "files": files,
        "cases": sorted(cases, key=lambda item: item["selector"]),
        "parse_errors": parse_errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload["counts"], sort_keys=True))


if __name__ == "__main__":
    main()
