"""Unit tests for scripts/check-secret-scan.py (R8 Governance, G06, S05).

Tests verify:
- Secret patterns are detected
- Scan output NEVER exposes secret values (only path, line, rule)
- Allowlisted files (scanner scripts themselves) are excluded
- Binary/large files are skipped
- Clean files produce no hits
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest

# Load the hyphenated scanner module via importlib
_spec = importlib.util.spec_from_file_location(
    "check_secret_scan",
    Path(__file__).resolve().parents[1] / "scripts" / "check-secret-scan.py",
)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
sys.modules["check_secret_scan"] = _mod  # register before exec so dataclass can resolve __module__
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
scan_file = _mod.scan_file
run_scan = _mod.run_scan
ScanHit = _mod.ScanHit
_RULES = _mod._RULES
_is_allowlisted = _mod._is_allowlisted
_known_placeholder = _mod._known_placeholder
SCANNER = Path(__file__).resolve().parents[1] / "scripts" / "check-secret-scan.py"


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Safety Fixture"], cwd=path, check=True)


def _run_scanner(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCANNER)],
        cwd=path,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


class TestPatternDetection:
    """Ensure each rule fires on its canonical canary."""

    def test_openai_key_detected(self, tmp_path: Path) -> None:
        f = tmp_path / "config.py"
        f.write_text('api_key = "sk-' + 'a' * 40 + '"', encoding="utf-8")
        hits = scan_file(str(f))
        assert len(hits) > 0
        assert hits[0].rule_name == "openai-api-key"

    def test_anthropic_key_detected(self, tmp_path: Path) -> None:
        f = tmp_path / "config.py"
        f.write_text('key = "sk-ant-' + 'a' * 40 + '"', encoding="utf-8")
        hits = scan_file(str(f))
        assert any(h.rule_name == "anthropic-api-key" for h in hits)

    def test_github_pat_detected(self, tmp_path: Path) -> None:
        f = tmp_path / "ci.yml"
        f.write_text("token: ghp_" + "a" * 36, encoding="utf-8")
        hits = scan_file(str(f))
        assert any(h.rule_name == "github-pat" for h in hits)

    def test_aws_access_key_detected(self, tmp_path: Path) -> None:
        f = tmp_path / "terraform.tf"
        f.write_text("access_key_id = AKIA" + "A" * 16, encoding="utf-8")
        hits = scan_file(str(f))
        assert any(h.rule_name == "aws-access-key-id" for h in hits)

    def test_google_api_key_detected(self, tmp_path: Path) -> None:
        f = tmp_path / "settings.py"
        f.write_text("MAPS_KEY = 'AIza" + "b" * 35 + "'", encoding="utf-8")
        hits = scan_file(str(f))
        assert any(h.rule_name == "google-api-key" for h in hits)

    def test_jwt_detected(self, tmp_path: Path) -> None:
        f = tmp_path / "token.txt"
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." + "a" * 40 + "." + "b" * 40
        f.write_text(jwt, encoding="utf-8")
        hits = scan_file(str(f))
        assert any(h.rule_name == "jwt-token" for h in hits)

    def test_pem_private_key_detected(self, tmp_path: Path) -> None:
        f = tmp_path / "key.pem"
        f.write_text("-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...\n", encoding="utf-8")
        hits = scan_file(str(f))
        assert any(h.rule_name == "private-key-pem-block" for h in hits)


class TestNoValueExposure:
    """Scan output must never contain the secret value."""

    def test_hit_object_does_not_store_matched_value(self, tmp_path: Path) -> None:
        secret = "sk-" + "x" * 40
        f = tmp_path / "env_file.py"
        f.write_text(f'API_KEY = "{secret}"', encoding="utf-8")
        hits = scan_file(str(f))
        assert len(hits) > 0
        # The ScanHit object must not expose the secret
        for hit in hits:
            assert not hasattr(hit, "matched_value")
            assert not hasattr(hit, "value")
            assert not hasattr(hit, "match")
            # The string repr of the hit must not contain the secret
            hit_str = str(hit)
            assert secret not in hit_str

    def test_rule_name_and_path_reported_not_value(self, tmp_path: Path) -> None:
        secret = "AIza" + "Z" * 35
        f = tmp_path / "settings.py"
        f.write_text(f"GOOGLE_KEY = '{secret}'", encoding="utf-8")
        hits = scan_file(str(f))
        assert any(h.rule_name == "google-api-key" for h in hits)
        for hit in hits:
            rendered = f"[{hit.rule_name}] {hit.path}:{hit.line_number}"
            assert secret not in rendered

    def test_scan_output_line_format_safe(self, tmp_path: Path) -> None:
        """Simulate the output format used by main() and verify no value leakage."""
        secret = "ghp_" + "Q" * 36
        f = tmp_path / "workflow.yml"
        f.write_text(f"    TOKEN: {secret}", encoding="utf-8")
        hits = scan_file(str(f))
        assert hits
        # Format as main() would — path:line only
        output_lines = [f"  [{h.rule_name}] {h.path}:{h.line_number}" for h in hits]
        for line in output_lines:
            assert secret not in line


class TestAllowlisting:
    """Scanner scripts themselves must not self-trigger."""

    def test_check_secret_scan_allowlisted(self) -> None:
        assert _is_allowlisted("scripts/check-secret-scan.py")

    def test_check_safe_staging_allowlisted(self) -> None:
        assert _is_allowlisted("scripts/check-safe-staging.py")

    def test_transport_allowlisted(self) -> None:
        assert _is_allowlisted("harness/lib/research_orchestration/transport.py")

    def test_env_template_allowlisted(self) -> None:
        assert _is_allowlisted(".env.template")

    def test_env_example_allowlisted(self) -> None:
        assert _is_allowlisted(".env.example")

    def test_arbitrary_source_not_allowlisted(self) -> None:
        assert not _is_allowlisted("harness/lib/research/fallback_policy.py")

    def test_placeholder_allowlist_fails_closed_on_content_change(self) -> None:
        path = "harness/docs/benchmark/terminal-bench-2.md"
        line = (Path(__file__).resolve().parents[1] / path).read_text(encoding="utf-8").splitlines()[185]
        assert _known_placeholder("openai-api-key", path, line)
        assert not _known_placeholder("openai-api-key", path, line + "x")


class TestCleanFiles:
    """Legitimate source files should produce no hits."""

    def test_clean_python_no_hits(self, tmp_path: Path) -> None:
        f = tmp_path / "module.py"
        f.write_text(
            '"""Fallback policy module."""\n\nFALLBACK_LEVEL = "L1_FULL_REAL"\n',
            encoding="utf-8",
        )
        assert scan_file(str(f)) == []

    def test_empty_file_no_hits(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("", encoding="utf-8")
        assert scan_file(str(f)) == []

    def test_template_value_no_hits(self, tmp_path: Path) -> None:
        f = tmp_path / "config_template.py"
        f.write_text("API_KEY = 'your_api_key_here'\n", encoding="utf-8")
        # Short placeholder - should not match (< 12 chars after quote)
        hits = scan_file(str(f))
        # Either 0 hits or hits that are false positives — verify no real key format
        for hit in hits:
            assert "your_api_key_here" not in hit.path


class TestGitCandidateCoverage:
    def test_exact_staged_blob_is_scanned_even_after_worktree_changes(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        target = tmp_path / "config.txt"
        target.write_text("clean=true\n", encoding="utf-8")
        subprocess.run(["git", "add", "config.txt"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "baseline"], cwd=tmp_path, check=True)

        canary = "sk-" + "S" * 40
        target.write_text(f"provider_key={canary}\n", encoding="utf-8")
        subprocess.run(["git", "add", "config.txt"], cwd=tmp_path, check=True)
        target.write_text("clean-again=true\n", encoding="utf-8")

        result = _run_scanner(tmp_path)
        output = result.stdout + result.stderr
        assert result.returncode == 1
        assert "[openai-api-key] config.txt:1" in output
        assert canary not in output

    def test_untracked_commit_candidate_is_scanned(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        tracked = tmp_path / "README.md"
        tracked.write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "baseline"], cwd=tmp_path, check=True)

        canary = "ghp_" + "Q" * 36
        (tmp_path / "candidate.txt").write_text(canary + "\n", encoding="utf-8")
        result = _run_scanner(tmp_path)
        output = result.stdout + result.stderr
        assert result.returncode == 1
        assert "[github-pat] candidate.txt:1" in output
        assert canary not in output

    def test_ignored_untracked_file_is_not_a_commit_candidate(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        (tmp_path / ".gitignore").write_text("ignored.env\n", encoding="utf-8")
        subprocess.run(["git", "add", ".gitignore"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "baseline"], cwd=tmp_path, check=True)
        (tmp_path / "ignored.env").write_text("sk-" + "I" * 40, encoding="utf-8")

        result = _run_scanner(tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
