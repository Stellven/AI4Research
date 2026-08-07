#!/usr/bin/env python3
"""check-secret-scan.py — Reproducible secret scan for R8 Governance (G06, S05).

Scans tracked files, exact staged index blobs, and untracked files that would
be candidates for the next commit (respecting .gitignore).
Reports ONLY: file path, line number, rule name matched.
NEVER prints or logs the matched secret value.

Rules cover:
  - OpenAI / Anthropic / Google / Serper / GitHub API keys
  - AWS access keys and secret patterns
  - JWT tokens, Bearer tokens
  - Private key PEM blocks
  - Generic password/token assignment patterns
  - Connection strings with embedded credentials

Exit codes:
  0 = clean (no secrets found)
  1 = secrets found (paths and rule names reported, no values)
  2 = scan error
"""
from __future__ import annotations

import re
import hashlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Pattern


@dataclass(frozen=True)
class SecretRule:
    name: str
    pattern: Pattern[str]
    # Human-readable description, never logged with values
    description: str


# ── Rules ─────────────────────────────────────────────────────────────────────
# Each pattern MUST be designed so that group(0) gives the full match only;
# the scan code will deliberately NOT log group(0) or any sub-group.
_RULES: list[SecretRule] = [
    SecretRule(
        name="openai-api-key",
        pattern=re.compile(r"(?<![A-Za-z0-9_-])sk-(?!ant-)[A-Za-z0-9_-]{20,}"),
        description="OpenAI API key (sk-... but not sk-ant-...)",
    ),
    SecretRule(
        name="anthropic-api-key",
        pattern=re.compile(r"(?<![A-Za-z0-9_-])sk-ant-[A-Za-z0-9_-]{20,}"),
        description="Anthropic API key (sk-ant-...)",
    ),
    SecretRule(
        name="github-pat",
        pattern=re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
        description="GitHub Personal Access Token",
    ),
    SecretRule(
        name="aws-access-key-id",
        pattern=re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        description="AWS Access Key ID",
    ),
    SecretRule(
        name="aws-secret-access-key",
        pattern=re.compile(
            r"(?i)(aws[_-]?secret[_-]?access[_-]?key|aws[_-]?secret)[\"']?\s*[=:]\s*[\"']?[A-Za-z0-9/+]{40}\b"
        ),
        description="AWS Secret Access Key assignment",
    ),
    SecretRule(
        name="google-api-key",
        pattern=re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
        description="Google API Key (AIza...)",
    ),
    SecretRule(
        name="google-oauth-token",
        pattern=re.compile(r"\bya29\.[A-Za-z0-9_-]{20,}\b"),
        description="Google OAuth2 Access Token (ya29...)",
    ),
    SecretRule(
        name="jwt-token",
        pattern=re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
        description="JSON Web Token (eyJ...)",
    ),
    SecretRule(
        name="bearer-token",
        pattern=re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/=]{20,}\b"),
        description="Bearer token in Authorization header",
    ),
    SecretRule(
        name="private-key-pem-block",
        pattern=re.compile(r"-----BEGIN (RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
        description="PEM private key block header",
    ),
    SecretRule(
        name="generic-api-key-assignment",
        pattern=re.compile(
            r"(?i)(api[_-]?key|apikey|api[_-]?secret|access[_-]?token|"
            r"secret[_-]?key|serper[_-]?api[_-]?key)\s*[=:]\s*[\"'][A-Za-z0-9_\-./+]{12,}[\"']"
        ),
        description="Generic API key or secret assignment (key=value form)",
    ),
    SecretRule(
        name="generic-password-assignment",
        pattern=re.compile(
            r"(?i)(password|passwd|pwd)\s*[=:]\s*[\"'][^\"']{6,}[\"']"
        ),
        description="Generic password assignment (not a placeholder)",
    ),
    SecretRule(
        name="connection-string-credentials",
        pattern=re.compile(
            r"(?i)(mongodb|postgres|postgresql|mysql|redis|amqp|rabbitmq|ftp|sftp)s?://"
            r"[A-Za-z0-9._-]+:[^@\s\"']{4,}@"
        ),
        description="Connection string with embedded credentials",
    ),
]

# ── Allowlisted paths (scanners, patterns, fixtures that embed rule text) ─────
_ALLOWLISTED_PATHS: list[re.Pattern[str]] = [
    re.compile(r"scripts/check-secret-scan\.py$"),
    re.compile(r"scripts/check-privacy\.sh$"),
    re.compile(r"scripts/check-safe-staging\.py$"),
    re.compile(r"tests/test-secret-scan\.py$"),
    re.compile(r"tests/test-safe-staging\.py$"),
    re.compile(r"harness/lib/research_orchestration/transport\.py$"),
]

_PLACEHOLDER_ALLOWLIST = Path(__file__).resolve().parents[1] / ".secret-scan-allowlist"


def _known_placeholder(rule_name: str, path: str, line: str) -> bool:
    """Allow only reviewed fixture lines, pinned by rule, path, and SHA-256.

    The digest makes the exception fail closed: changing even one character in
    a reviewed placeholder causes the scanner to report it again. The file
    contains no secret values and is safe to review in CI output.
    """
    try:
        entries = {
            item.strip()
            for item in _PLACEHOLDER_ALLOWLIST.read_text(encoding="utf-8").splitlines()
            if item.strip() and not item.lstrip().startswith("#")
        }
    except OSError:
        return False
    normalized = path.replace("\\", "/")
    digest = hashlib.sha256(line.encode("utf-8")).hexdigest()
    return f"{rule_name} {digest} {normalized}" in entries

# ── Binary / large file extensions to skip ────────────────────────────────────
_SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".pdf", ".xlsx", ".xls", ".xlsm", ".docx", ".doc", ".pptx",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".whl", ".egg", ".pyc", ".pyo",
    ".exe", ".dll", ".so", ".dylib", ".a", ".o",
    ".lock", ".lockb",
    ".ndjson",  # large inspection files
    ".inspect.ndjson",
}


def _is_allowlisted(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return any(pat.search(normalized) for pat in _ALLOWLISTED_PATHS)


def _should_skip(path: str) -> bool:
    ext = Path(path).suffix.lower()
    if ext in _SKIP_EXTENSIONS:
        return True
    # Skip very large files (> 2 MB)
    try:
        if Path(path).stat().st_size > 2 * 1024 * 1024:
            return True
    except OSError:
        pass
    return False


def _list_tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True, check=False,
    )
    if result.returncode != 0:
        return []
    return [
        p for p in result.stdout.decode("utf-8", errors="replace").split("\x00") if p
    ]


def _list_staged_files() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMRT", "-z"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [
        p for p in result.stdout.decode("utf-8", errors="replace").split("\x00") if p
    ]


def _list_untracked_candidates() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [
        p for p in result.stdout.decode("utf-8", errors="replace").split("\x00") if p
    ]


def _read_staged_text(path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f":{path}"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace")


@dataclass
class ScanHit:
    rule_name: str
    path: str
    line_number: int
    # NOTE: the actual matched value is deliberately NOT stored here


def scan_text(path: str, content: str) -> list[ScanHit]:
    """Scan supplied text and return path/line/rule hits without values."""
    hits: list[ScanHit] = []
    if _is_allowlisted(path) or _should_skip(path):
        return hits
    for line_num, line in enumerate(content.splitlines(), start=1):
        for rule in _RULES:
            if rule.pattern.search(line) and not _known_placeholder(rule.name, path, line):
                hits.append(ScanHit(
                    rule_name=rule.name,
                    path=path,
                    line_number=line_num,
                ))
                break  # one hit per line per file is sufficient for triage
    return hits


def scan_file(path: str) -> list[ScanHit]:
    """Scan a working-tree file and return path/line/rule hits without values."""
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return scan_text(path, content)


def run_scan(files: list[str]) -> list[ScanHit]:
    all_hits: list[ScanHit] = []
    for path in files:
        all_hits.extend(scan_file(path))
    return all_hits


def scan_repository_candidates() -> tuple[list[ScanHit], int]:
    """Scan commit-relevant content, preferring exact staged blobs.

    A staged file is read from the index even if its working-tree version has
    changed afterward. Tracked and untracked candidates are otherwise read from
    disk. Each path is reported at most once.
    """
    tracked = set(_list_tracked_files())
    staged = set(_list_staged_files())
    untracked = set(_list_untracked_candidates())
    paths = sorted(tracked | staged | untracked)
    hits: list[ScanHit] = []
    for path in paths:
        if path in staged:
            content = _read_staged_text(path)
            if content is not None:
                hits.extend(scan_text(path, content))
                continue
        hits.extend(scan_file(path))
    return hits, len(paths)


def main() -> int:
    tracked = _list_tracked_files()
    if not tracked:
        print("check-secret-scan: no tracked files found (not a git repo?)", file=sys.stderr)
        return 2

    hits, scanned_count = scan_repository_candidates()
    if not hits:
        print(f"check-secret-scan passed: {scanned_count} tracked/staged/untracked candidate files scanned, no secrets found")
        return 0

    print(
        f"check-secret-scan FAILED: {len(hits)} potential secret(s) found in "
        f"{len(set(h.path for h in hits))} file(s):",
        file=sys.stderr,
    )
    for hit in sorted(hits, key=lambda h: (h.path, h.line_number)):
        # Report location and rule ONLY — the matched value is NEVER printed
        print(f"  [{hit.rule_name}] {hit.path}:{hit.line_number}", file=sys.stderr)

    print(
        "\nNOTE: Values are not printed. Inspect each reported location manually.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
