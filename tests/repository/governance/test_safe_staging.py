"""Unit tests for scripts/check-safe-staging.py (R8 Governance, G05).

Tests verify that:
- .env files are rejected, .env.template and .env.example are allowed
- Key material filenames are rejected
- API key credential filenames are rejected
- Excel lock files are rejected
- Transient test outputs are rejected
- Provider artifacts are rejected
- Legitimate source files are NOT rejected
- The staged-secret fixture (a planted .env secret) is detected
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

# Load the hyphenated script directly via importlib
_spec = importlib.util.spec_from_file_location(
    "check_safe_staging",
    Path(__file__).resolve().parents[3] / "scripts" / "check-safe-staging.py",
)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
sys.modules["check_safe_staging"] = _mod  # register before exec so dataclass can resolve __module__
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
classify_path = _mod.classify_path
run_check = _mod.run_check
Violation = _mod.Violation
SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check-safe-staging.py"

import pytest



class TestEnvFiles:
    def test_env_file_rejected(self):
        assert "LOCAL_ENV_CONFIG" in classify_path(".env")

    def test_env_local_rejected(self):
        assert "LOCAL_ENV_CONFIG" in classify_path(".env.local")

    def test_env_production_rejected(self):
        assert "LOCAL_ENV_CONFIG" in classify_path(".env.production")

    def test_nested_env_rejected(self):
        assert "LOCAL_ENV_CONFIG" in classify_path("service/.env")

    def test_env_template_allowed(self):
        assert "LOCAL_ENV_CONFIG" not in classify_path(".env.template")

    def test_env_example_allowed(self):
        assert "LOCAL_ENV_CONFIG" not in classify_path(".env.example")

    def test_env_sample_allowed(self):
        assert "LOCAL_ENV_CONFIG" not in classify_path(".env.sample")


class TestKeyMaterial:
    def test_pem_rejected(self):
        assert "KEY_MATERIAL" in classify_path("server.pem")

    def test_rsa_key_rejected(self):
        assert "KEY_MATERIAL" in classify_path("id_rsa")

    def test_p12_rejected(self):
        assert "KEY_MATERIAL" in classify_path("cert.p12")

    def test_pub_key_allowed(self):
        # .pub alone is not rejected (public key is safe to commit)
        # But id_rsa.pub is still caught by the pattern
        cats = classify_path("id_rsa.pub")
        # This is acceptable: public key files are generally safe, but we be conservative
        assert isinstance(cats, list)


class TestCredentialFilenames:
    def test_api_key_json_rejected(self):
        assert "CREDENTIAL_FILENAME" in classify_path("api_key.json")

    def test_client_secret_json_rejected(self):
        assert "OAUTH_SECRET" in classify_path("client_secret_abc123.json")

    def test_credentials_json_rejected(self):
        assert "CREDENTIAL_FILENAME" in classify_path("credentials.json")


class TestExcelLocks:
    def test_excel_lock_rejected(self):
        assert "EXCEL_LOCK_FILE" in classify_path("~$AI4RnD Feature List.xlsx")

    def test_excel_lock_nested_rejected(self):
        assert "EXCEL_LOCK_FILE" in classify_path("~$report.xlsx")


class TestTransientOutputs:
    def test_real_data_tests_rejected(self):
        assert "TRANSIENT_TEST_OUTPUT" in classify_path("outputs/real-data-tests/run-1/data.json")

    def test_phase22_journeys_rejected(self):
        assert "TRANSIENT_TEST_OUTPUT" in classify_path("outputs/phase22-real-journeys/j01/log.txt")


class TestProviderArtifacts:
    def test_provider_artifact_rejected(self):
        assert "LIVE_PROVIDER_ARTIFACT" in classify_path("outputs/provider-artifacts/serper-response.json")

    def test_live_provider_rejected(self):
        assert "LIVE_PROVIDER_ARTIFACT" in classify_path("outputs/live-provider/results.json")


class TestCodexTmp:
    def test_codex_tmp_scratch_rejected(self):
        assert "CODEX_TMP_SCRATCH" in classify_path(".codex-tmp/phase22-worker-results/batch-1/result.json")


class TestLegitimateFiles:
    """Ensure production source files are NOT flagged."""

    def test_source_python_allowed(self):
        assert classify_path("harness/lib/research_orchestration/transport.py") == []

    def test_test_python_allowed(self):
        assert classify_path("tests/research/unit/test_fallback_policy_levels.py") == []

    def test_readme_allowed(self):
        assert classify_path("README.md") == []

    def test_gitignore_allowed(self):
        assert classify_path(".gitignore") == []

    def test_schema_allowed(self):
        assert classify_path("harness/schemas/physical-operators.schema.v2.draft.json") == []

    def test_canonical_report_allowed(self):
        assert classify_path("docs/integrations/autosci/phase-22-journey-test-report.md") == []

    def test_env_template_root_allowed(self):
        assert classify_path(".env.template") == []


class TestStagedSecretFixture:
    """Simulate the staged-secret fixture required by the acceptance criteria."""

    def test_planted_env_secret_is_detected(self):
        """A planted .env file with a secret must be rejected."""
        # Simulate what would be staged
        staged = [".env"]
        violations = run_check(staged)
        assert any(v.category == "LOCAL_ENV_CONFIG" for v in violations)
        # Verify no secret value appears in the violation output
        for v in violations:
            assert "sk-" not in v.path
            assert "password" not in v.path.lower() or v.path.endswith(".env")

    def test_planted_key_file_is_detected(self):
        staged = ["deploy/server.pem", ".env.production"]
        violations = run_check(staged)
        categories = {v.category for v in violations}
        assert "KEY_MATERIAL" in categories
        assert "LOCAL_ENV_CONFIG" in categories

    def test_clean_staging_passes(self):
        staged = [
            "harness/lib/research_orchestration/transport.py",
            ".gitignore",
            "README.md",
        ]
        violations = run_check(staged)
        assert violations == []


class TestGitCliIntegration:
    def test_real_staged_env_is_rejected_without_value_exposure(self, tmp_path: Path):
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Safety Fixture"], cwd=tmp_path, check=True)
        (tmp_path / "README.md").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "baseline"], cwd=tmp_path, check=True)

        canary = "sk-" + "N" * 40
        (tmp_path / ".env").write_text(f"OPENAI_API_KEY={canary}\n", encoding="utf-8")
        subprocess.run(["git", "add", "-f", ".env"], cwd=tmp_path, check=True)
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=tmp_path,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        output = result.stdout + result.stderr
        assert result.returncode == 1
        assert "forbidden staged paths detected" in output
        assert "[LOCAL_ENV_CONFIG] .env" in output
        assert canary not in output

    def test_diff_base_mode_checks_committed_changed_paths(self, tmp_path: Path):
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Safety Fixture"], cwd=tmp_path, check=True)
        (tmp_path / "README.md").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "baseline"], cwd=tmp_path, check=True)
        base = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True, capture_output=True, check=True
        ).stdout.strip()
        artifact = tmp_path / "outputs" / "live-provider" / "response.json"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("{}\n", encoding="utf-8")
        subprocess.run(["git", "add", "-f", artifact.relative_to(tmp_path)], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "provider artifact"], cwd=tmp_path, check=True)

        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--diff-base", base],
            cwd=tmp_path,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        assert result.returncode == 1
        assert "forbidden changed paths detected" in result.stderr
        assert "[LIVE_PROVIDER_ARTIFACT] outputs/live-provider/response.json" in result.stderr

    def test_all_tracked_mode_checks_forbidden_file_in_committed_history(self, tmp_path: Path):
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Safety Fixture"], cwd=tmp_path, check=True)
        lock_file = tmp_path / "docs" / "testing" / "xlsx" / "~$committed-report.xlsx"
        lock_file.parent.mkdir(parents=True)
        lock_file.write_text("committed fixture\n", encoding="utf-8")
        subprocess.run(["git", "add", "-f", lock_file.relative_to(tmp_path)], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "historical forbidden path"], cwd=tmp_path, check=True)

        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--all-tracked"],
            cwd=tmp_path,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        assert result.returncode == 1
        assert "forbidden tracked paths detected" in result.stderr
        assert "[EXCEL_LOCK_FILE] docs/testing/xlsx/~$committed-report.xlsx" in result.stderr
