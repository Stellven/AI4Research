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

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import PurePosixPath


@dataclass
class Violation:
    category: str
    path: str


def _list_staged_files() -> list[str]:
    """Return list of files currently staged in the Git index."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMRT"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        # Fall back to ls-files if not in a git context
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True, text=True, check=False,
        )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return lines


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


def main() -> int:
    staged = _list_staged_files()
    violations = run_check(staged)
    if not violations:
        print("check-safe-staging passed: no forbidden files staged")
        return 0

    print("check-safe-staging FAILED: forbidden staged files detected:", file=sys.stderr)
    for v in sorted(violations, key=lambda x: (x.category, x.path)):
        # Report category and path ONLY — never print file content or values
        print(f"  [{v.category}] {v.path}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
