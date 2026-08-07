"""G4-lite run-3 deviation hygiene — skip-doctor contract + truthful manifests.

Two small operator-facing deviations recorded by the run-2/run-3 reports:

1. `solar-harness start <ws> --skip-doctor` skipped the PRE-start doctor but
   the coordinator-start "D7" summaries still ran doctor.sh — the operator
   observed doctor output under a flag that promises none. start_harness now
   exports SOLAR_SKIP_DOCTOR=1 and the three D7 summary sites honor it (the
   explicit `status` command's summary stays unconditional).

2. The isolated e2e scripts stamped evidence/manifest.json with the built-in
   default task (the P2-era uniqwords prompt) even when no --task was given —
   G4-lite runs submit their own prompt via /intake, so the manifest claimed
   a task the run never used ("stale uniqwords evidence manifest"). The
   manifest now records the task ONLY when --task was explicitly provided,
   plus task_provided/task_note fields.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

_HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
_REPO = _HARNESS.parent


class TestSkipDoctorContract:
    def test_start_exports_the_skip_flag(self):
        text = (_HARNESS / "solar-harness.sh").read_text(encoding="utf-8")
        assert 'export SOLAR_SKIP_DOCTOR=1' in text

    def test_d7_summaries_honor_the_skip_flag(self):
        """Every doctor --summary call in the start/coordinator path must be
        guarded; exactly one unconditional call remains (the explicit
        `status` command)."""
        text = (_HARNESS / "solar-harness.sh").read_text(encoding="utf-8")
        plain = 'bash "$HARNESS_DIR/doctor.sh" --summary 2>/dev/null || true'
        guarded = '[[ "${SOLAR_SKIP_DOCTOR:-0}" == "1" ]] || ' + plain
        assert text.count(guarded) == 3, text.count(guarded)
        assert text.count(plain) - text.count(guarded) == 1, (
            "exactly one unconditional doctor --summary (the status command) may remain"
        )


class TestManifestRecordsOnlyRealTasks:
    def test_prepare_only_manifest_is_truthful(self, tmp_path):
        """Real --prepare-only run: no --task given -> the manifest must not
        claim the built-in default task."""
        sandbox = tmp_path / "sbx"
        proc = subprocess.run(
            ["bash", str(_REPO / "scripts" / "live-codex-e2e-isolated.sh"),
             "--prepare-only", "--sandbox", str(sandbox)],
            capture_output=True, text=True, timeout=120, cwd=str(_REPO),
        )
        try:
            assert proc.returncode == 0, proc.stderr[-800:]
            manifest = json.loads((sandbox / "evidence" / "manifest.json").read_text(encoding="utf-8"))
            assert manifest.get("task") == "", manifest.get("task")
            assert manifest.get("task_provided") is False
            assert "intake" in str(manifest.get("task_note") or "")
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)

    def test_claude_variant_carries_the_same_fields(self):
        """The claude script's manifest writer ships the same truthfulness
        fields (source pin — preparing it needs live claude credentials)."""
        text = (_REPO / "scripts" / "live-claude-e2e-isolated.sh").read_text(encoding="utf-8")
        assert '"task_provided": task_explicit == "1"' in text
        assert 'task_explicit=1' in text
        # the invalid-evidence writer must still unpack exactly its 3 args
        assert "path, reason, run_id = sys.argv[1:4]" in text


class TestStartArgOrderIndependence:
    """G4 UI-rung run 4: `solar-harness start --skip-doctor` (no workdir)
    parsed the FLAG as the working directory — doctor ran, and the cockpit
    started against a garbage workdir named '--skip-doctor'. A fresh user
    typing the documented flag without a path hits the same. Start args are
    now order-independent: flags are recognized anywhere; the first
    non-flag argument is the workdir; unknown --flags never become a
    workdir. Proven through the real script via the debug-start-args probe."""

    def _parse(self, *args: str) -> dict:
        proc = subprocess.run(
            ["bash", str(_HARNESS / "solar-harness.sh"), "debug-start-args", *args],
            capture_output=True, text=True, timeout=30,
            env={**__import__("os").environ, "HARNESS_DIR": str(_HARNESS)},
        )
        assert proc.returncode == 0, proc.stderr[-400:]
        out = {}
        for part in proc.stdout.strip().split():
            if "=" in part:
                k, _, v = part.partition("=")
                out[k] = v
        return out

    def test_flag_without_workdir(self):
        parsed = self._parse("--skip-doctor")
        assert parsed.get("skip") == "--skip-doctor", parsed
        assert parsed.get("workdir") not in ("", "--skip-doctor"), parsed

    def test_workdir_then_flag(self):
        parsed = self._parse("/tmp/ws-a", "--skip-doctor")
        assert parsed.get("workdir") == "/tmp/ws-a"
        assert parsed.get("skip") == "--skip-doctor"

    def test_flag_then_workdir(self):
        parsed = self._parse("--skip-doctor", "/tmp/ws-b")
        assert parsed.get("workdir") == "/tmp/ws-b"
        assert parsed.get("skip") == "--skip-doctor"

    def test_plain_workdir_keeps_doctor(self):
        parsed = self._parse("/tmp/ws-c")
        assert parsed.get("workdir") == "/tmp/ws-c"
        assert not parsed.get("skip"), parsed
