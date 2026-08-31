#!/usr/bin/env python3
"""Read-only portability inventory. Findings are risks, not universal E2E verdicts.

Reads tracked source, parses Python without executing it, and reports locations
rather than source lines or credential values. Never installs or starts services.
"""
from __future__ import annotations
import argparse
import ast
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import sys

SOURCE_SUFFIXES = {".py", ".sh", ".bash", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".ps1"}
PERSONAL_PATH = re.compile(
    r"(?:[A-Za-z]:[\\/](?:Users|demo)[\\/ ]|/home/[^/\s\"']+/|"
    r"/Users/[^/\s\"']+/|/mnt/[a-z]/(?:Users|demo)[/ ])")
HOST_ADDRESS = re.compile(r"(?:172\.19\.127\.84|(?:127\.0\.0\.1|localhost):8765)")
SECRET_PATTERNS = {
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "provider_token": re.compile(rb"\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{32,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"),
}


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def scope(path):
    if path.startswith(("tests/", "harness/tests/")) or "/fixtures/" in path:
        return "tests_or_fixtures"
    if "/vendor/" in path or "/metadata/" in path:
        return "vendor_or_archived_examples"
    if path.startswith("harness/"):
        return "harness_source"
    return "other_source"


def inspect_source(repo):
    paths = git(repo, "ls-files", "-z").decode().split("\0")
    paths = [p for p in paths if p]
    counts, findings = Counter(), []
    insensitive = {}
    for path in paths:
        collision = insensitive.setdefault(path.casefold(), path)
        if collision != path:
            findings.append({"kind": "case_collision", "path": path, "other": collision})
        if len(path) > 220:
            counts["relative_paths_over_220_chars"] += 1
        if Path(path).suffix not in SOURCE_SUFFIXES:
            continue
        counts["source_files"] += 1
        counts[scope(path)] += 1
        data = (repo / path).read_bytes()
        try:
            text = data.decode("utf-8-sig")
        except UnicodeError:
            findings.append({"kind": "non_utf8_source", "path": path})
            continue
        for line, value in enumerate(text.splitlines(), 1):
            for kind, pattern in (("personal_path", PERSONAL_PATH), ("old_backend_address", HOST_ADDRESS)):
                if pattern.search(value):
                    findings.append({"kind": kind, "path": path, "line": line, "scope": scope(path)})
        if path.endswith(".py"):
            counts["python_files"] += 1
            try:
                ast.parse(text, filename=path)
            except SyntaxError as exc:
                findings.append({"kind": "python_syntax", "path": path, "line": exc.lineno,
                                 "message": exc.msg, "scope": scope(path)})
        if path.endswith((".sh", ".bash")) and b"\r\n" in data:
            findings.append({"kind": "shell_crlf", "path": path, "scope": scope(path)})
    return {"tracked_files": len(paths), "counts": dict(counts),
            "findings_by_kind": dict(Counter(x["kind"] for x in findings)), "findings": findings}


def outgoing_secret_scan(repo):
    # The remote-tracking refs must have been refreshed before this check.
    lines = git(repo, "rev-list", "--objects", "HEAD", "--not",
                "--remotes=origin", "--remotes=stellven").decode().splitlines()
    records = [(line.split(" ", 1)[0], line.split(" ", 1)[1] if " " in line else "")
               for line in lines]
    if not records:
        return {"objects": 0, "blobs_scanned": 0, "findings": []}
    query = "\n".join(oid for oid, _ in records).encode() + b"\n"
    meta = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
        input=query, capture_output=True, check=True).stdout.decode().splitlines()
    findings, scanned = [], 0
    for (oid, path), row in zip(records, meta):
        parts = row.split()
        if len(parts) != 3 or parts[1] != "blob":
            continue
        size = int(parts[2])
        if size > 20 * 1024 * 1024:
            findings.append({"kind": "large_blob_not_scanned", "object": oid, "path": path, "bytes": size})
            continue
        content = git(repo, "cat-file", "blob", oid)
        scanned += 1
        for kind, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                findings.append({"kind": kind, "object": oid, "path": path})
    return {"objects": len(records), "blobs_scanned": scanned, "findings": findings,
            "limit": "Pattern scan only; never proves absence of every possible secret."}


def check_runtime_shells(repo, runtime):
    paths = git(repo, "ls-files", "-z", "harness").decode().split("\0")
    paths = [p for p in paths if p.endswith((".sh", ".bash"))
             and not any(part in p.split("/") for part in ("tests", "vendor", "metadata"))]
    failures = []
    for path in paths:
        target = runtime / path.removeprefix("harness/")
        check = subprocess.run(["bash", "-n", str(target)], capture_output=True, text=True)
        if check.returncode:
            failures.append({"path": path, "exit_code": check.returncode,
                             "error": check.stderr.strip()})
    return {"files": len(paths), "failures": failures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--outgoing-secrets", action="store_true")
    parser.add_argument("--runtime-shell-syntax", type=Path,
                        help="syntax-check tracked harness shell scripts at this runtime; no execution")
    args = parser.parse_args()
    result = {"repo_head": git(args.repo, "rev-parse", "HEAD").decode().strip(),
              "python": sys.version.split()[0], "source": inspect_source(args.repo),
              "acceptance_boundary": "Static inspection only; new-host install and live E2E remain untested."}
    if args.outgoing_secrets:
        result["outgoing_secrets"] = outgoing_secret_scan(args.repo)
    if args.runtime_shell_syntax:
        result["runtime_shell_syntax"] = check_runtime_shells(args.repo, args.runtime_shell_syntax)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
