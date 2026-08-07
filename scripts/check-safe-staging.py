#!/usr/bin/env python3
"""check-safe-staging.py — Safe Git staging check (R8 Governance, G05).

Scans the Git index for files that must never be staged:
  - .env files (real environment configs, not templates/examples)
  - Private key / certificate material
  - API key or token patterns in filenames
  - Transient test outputs (outputs/real-data-tests/, outputs/phase22-real-journeys/)
  - Live provider artifacts
  - Excel lock files (~$*.xlsx etc.)
  - codex-tmp worker scratch areas

Reports category and path only.  Never prints file content or values.
Exit 0 = clean; exit 1 = violations found.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import PurePosixPath


@dataclass
class Violation:
    category: str
    path: str


def _git_paths(args: list[str]) -> list[str]:
    """Run a NUL-delimited Git path query without exposing file contents."""
    result = subprocess.run(
        ["git", *args, "-z"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("git path query failed")
    return [
        path
        for path in result.stdout.decode("utf-8", errors="replace").split("\x00")
        if path
    ]


def _list_staged_files() -> list[str]:
    """Return list of files currently staged in the Git index."""
    return _git_paths(["diff", "--cached", "--name-only", "--diff-filter=ACMRT"])


def _list_all_tracked_files() -> list[str]:
    return _git_paths(["ls-files"])


def _list_diff_files(base: str) -> list[str]:
    return _git_paths(["diff", "--name-only", "--diff-filter=ACMRT", "--find-renames", base, "HEAD"])


def _read_paths_stdin() -> list[str]:
    raw = sys.stdin.buffer.read()
    separator = b"\x00" if b"\x00" in raw else None
    chunks = raw.split(separator) if separator else raw.splitlines()
    return [chunk.decode("utf-8", errors="replace") for chunk in chunks if chunk]


_ENV_PATTERN = re.compile(
    r"(?i)(^|/)\.env(\.[^/]+)?$"
)
_ENV_ALLOWLIST = re.compile(
    r"(?i)\.env\.(example|template|sample)$"
)
_KEY_MATERIAL = re.compile(
    r"(?i)(\.(key|pem|p12|pfx|crt|cer|der|pkcs|jks|keystore)|"
    r"(_rsa|_dsa|_ecdsa|_ed25519))(\.pub)?$"
)
_API_KEY_FILENAME = re.compile(
    r"(?i)(api[_-]?key|apikey|secret[_-]?key|access[_-]?token|"
    r"client[_-]?secret|credentials?)\.(json|txt|yaml|yml|ini|conf|cfg|env)$"
)
_OAUTH_SECRET = re.compile(
    r"(?i)(client_secret_.*\.json|.*\.googleusercontent\.com\.json)"
)
_EXCEL_LOCK = re.compile(r"^~\$")
_TRANSIENT_OUTPUT = re.compile(
    r"(?i)^outputs/(real-data-tests|phase22-real-journeys|tmp-|provider-artifacts|live-provider)/"
)
_PROVIDER_ARTIFACT = re.compile(
    r"(?i)(provider-artifacts/|live-provider-artifacts/|live-provider/|\.provider-artifact$)"
)
_CODEX_TMP = re.compile(r"^\.codex-tmp/")


def classify_path(path: str) -> list[str]:
    """Return list of violation categories for the given staged path."""
    categories: list[str] = []
    p = path.replace("\\", "/")
    basename = PurePosixPath(p).name

    # .env files (not templates or examples)
    if _ENV_PATTERN.search(p) and not _ENV_ALLOWLIST.search(p):
        categories.append("LOCAL_ENV_CONFIG")

    # Key / certificate material
    if _KEY_MATERIAL.search(basename):
        categories.append("KEY_MATERIAL")

    # API key / credential filenames
    if _API_KEY_FILENAME.search(basename):
        categories.append("CREDENTIAL_FILENAME")

    # OAuth / Google client secrets
    if _OAUTH_SECRET.search(basename):
        categories.append("OAUTH_SECRET")

    # Excel lock files
    if _EXCEL_LOCK.match(basename):
        categories.append("EXCEL_LOCK_FILE")

    # Transient outputs
    if _TRANSIENT_OUTPUT.match(p):
        categories.append("TRANSIENT_TEST_OUTPUT")

    # Provider artifacts
    if _PROVIDER_ARTIFACT.search(p):
        categories.append("LIVE_PROVIDER_ARTIFACT")

    # codex-tmp scratch
    if _CODEX_TMP.match(p):
        categories.append("CODEX_TMP_SCRATCH")

    return categories


def run_check(staged: list[str]) -> list[Violation]:
    violations: list[Violation] = []
    for path in staged:
        for cat in classify_path(path):
            violations.append(Violation(category=cat, path=path))
    return violations


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reject forbidden repository paths")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--paths-stdin", action="store_true", help="read newline- or NUL-delimited paths from stdin")
    mode.add_argument("--all-tracked", action="store_true", help="check every tracked path")
    mode.add_argument("--diff-base", metavar="COMMIT", help="check changed paths from COMMIT to HEAD")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        if args.paths_stdin:
            paths = _read_paths_stdin()
            scope = "supplied"
        elif args.all_tracked:
            paths = _list_all_tracked_files()
            scope = "tracked"
        elif args.diff_base:
            paths = _list_diff_files(args.diff_base)
            scope = "changed"
        else:
            paths = _list_staged_files()
            scope = "staged"
    except RuntimeError:
        print("check-safe-staging ERROR: unable to enumerate Git paths", file=sys.stderr)
        return 2

    violations = run_check(paths)
    if not violations:
        print(f"check-safe-staging passed: no forbidden {scope} paths")
        return 0

    print(f"check-safe-staging FAILED: forbidden {scope} paths detected:", file=sys.stderr)
    for v in sorted(violations, key=lambda x: (x.category, x.path)):
        # Report category and path ONLY — never print file content or values
        print(f"  [{v.category}] {v.path}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
