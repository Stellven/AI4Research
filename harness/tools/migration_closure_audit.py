#!/usr/bin/env python3
"""Offline migration inventory verification; never installs or starts Solar.

Hashes normalize CRLF to LF only. --git-tree checks committed/staged blobs,
not the worktree, so an ignored/untracked local file cannot hide a missing asset.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import subprocess
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urldefrag

MANIFEST = "metadata/migration-closure-20260830.json"


def normalized_sha256(data: bytes) -> str:
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def safe_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value:
        raise ValueError(f"unsafe inventory path: {value!r}")
    return value


def filesystem_reader(root: Path):
    root = root.resolve()

    def read(path: str) -> bytes:
        target = (root / safe_path(path)).resolve()
        if not target.is_relative_to(root):
            raise ValueError(f"path escapes harness: {path}")
        return target.read_bytes()

    return read


def git_reader(repo: Path, tree: str):
    # ':' addresses the index; other values must resolve to a tree-ish.
    if tree != ":":
        subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--verify", "--end-of-options", tree + "^{tree}"],
            check=True, capture_output=True,
        )

    def read(path: str) -> bytes:
        path = "harness/" + safe_path(path)
        spec = ":" + path if tree == ":" else tree + ":" + path
        result = subprocess.run(
            ["git", "-C", str(repo), "show", spec], capture_output=True, check=False,
        )
        if result.returncode:
            raise FileNotFoundError(f"missing Git blob: {spec}")
        return result.stdout

    return read


def objects(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from objects(item)
    elif isinstance(value, list):
        for item in value:
            yield from objects(item)


def check_references(documents: dict) -> list[str]:
    """Resolve inventory-local schema IDs, paths and JSON pointers, without HTTP."""
    errors = []
    ids = {doc["$id"]: path for path, doc in documents.items()
           if isinstance(doc, dict) and "$id" in doc}
    for path, doc in documents.items():
        for obj in objects(doc):
            if "$ref" not in obj:
                continue
            ref = obj["$ref"]
            base, fragment = urldefrag(ref)
            target = path if not base else ids.get(
                base, posixpath.normpath(posixpath.join(posixpath.dirname(path), base)))
            if target not in documents:
                errors.append(f"{path}: unresolved $ref {ref}")
                continue
            value = documents[target]
            try:
                if fragment.startswith("/"):
                    for part in unquote(fragment)[1:].split("/"):
                        part = part.replace("~1", "/").replace("~0", "~")
                        value = value[int(part)] if isinstance(value, list) else value[part]
                elif fragment and not any(x.get("$anchor") == fragment for x in objects(value)):
                    raise KeyError(fragment)
            except (KeyError, TypeError, ValueError, IndexError):
                errors.append(f"{path}: unresolved fragment in $ref {ref}")
    return errors


def audit(read, validate_schemas: bool = False) -> dict:
    manifest = json.loads(read(MANIFEST))
    if manifest.get("schema") != "solar.migration_contract_inventory.v1" or not manifest.get("files"):
        raise ValueError("unsupported or empty migration inventory")
    errors, documents, seen = [], {}, set()
    for entry in manifest["files"]:
        path = safe_path(entry["path"])
        if not path.startswith("schemas/") or path in seen:
            raise ValueError(f"invalid or duplicate schema inventory entry: {path}")
        seen.add(path)
        try:
            data = read(path)
            if normalized_sha256(data) != entry["sha256_lf"]:
                errors.append(f"{path}: SHA-256 mismatch")
            if path.endswith(".json"):
                documents[path] = json.loads(data)
        except (OSError, ValueError) as exc:
            errors.append(f"{path}: {exc}")
    errors.extend(check_references(documents))
    checked = 0
    if validate_schemas:
        from jsonschema.validators import validator_for
        for path, document in documents.items():
            if isinstance(document, dict) and "$schema" in document:
                try:
                    validator_for(document).check_schema(document)
                    checked += 1
                except Exception as exc:
                    errors.append(f"{path}: invalid schema: {exc}")
    return {"ok": not errors, "files": len(seen), "json_files": len(documents),
            "schemas_validated": checked, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--repo", type=Path, help="canonical Git repository (read-only)")
    parser.add_argument("--git-tree", help="commit/ref to audit; ':' checks the Git index")
    parser.add_argument("--validate-schemas", action="store_true", help="requires jsonschema")
    args = parser.parse_args()
    if args.git_tree and not args.repo:
        parser.error("--git-tree requires --repo")
    try:
        read = git_reader(args.repo, args.git_tree) if args.git_tree else filesystem_reader(args.harness)
        result = audit(read, args.validate_schemas)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        result = {"ok": False, "errors": [str(exc)]}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
