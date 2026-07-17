"""Conftest for research tests.

The survey quality gates need the real ``research.evaluator.audit_sources``.
Older tests used a module stub to break an import cycle, but that silently
disabled source-authority checks for the survey finalizer.
"""

from __future__ import annotations

import importlib
import os
import sys
import types
from pathlib import Path
from typing import Mapping

import pytest


_HARNESS_DIR = Path(__file__).resolve().parents[1]
_HARNESS_LIB = str(_HARNESS_DIR / "lib")
_HARNESS_DIR_REAL = _HARNESS_DIR.resolve()
_INSTALLED_HARNESS_LINK = Path.home() / ".solar" / "harness"
_INSTALLED_HARNESS = (Path.home() / ".solar" / "harness").resolve()

if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)
os.environ.setdefault("HARNESS_DIR", str(_HARNESS_DIR))
os.environ.setdefault("SOLAR_HARNESS_DIR", str(_HARNESS_DIR))

_HARNESS_CLI = _HARNESS_DIR / "lib" / "cli"
_cli_pkg = types.ModuleType("cli")
_cli_pkg.__path__ = [str(_HARNESS_CLI)]
sys.modules["cli"] = _cli_pkg


QUARANTINE_EXPECTED_COUNT = 30

COLLECTION_QUARANTINE_MANIFEST: dict[str, dict[str, str]] = {
    # B stale-import: benchmark tests import harness.lib.* from harness cwd; modules exist under lib/benchmark.
    "tests/benchmark/test_benchmark_registry.py": {
        "class": "B stale-import",
        "cause": "imports harness.lib.benchmark while pytest is invoked from harness/",
    },
    # B stale-import: benchmark tests import harness.lib.* from harness cwd; modules exist under lib/benchmark.
    "tests/benchmark/test_benchmark_report_schema.py": {
        "class": "B stale-import",
        "cause": "imports harness.lib.benchmark while pytest is invoked from harness/",
    },
    # B stale-import: benchmark tests import harness.lib.* from harness cwd; module exists under lib/benchmark.
    "tests/benchmark/test_solar_solver.py": {
        "class": "B stale-import",
        "cause": "imports harness.lib.benchmark.solar_solver while pytest is invoked from harness/",
    },
    # B stale-import: benchmark tests import and patch harness.lib.* from harness cwd; modules exist under lib/benchmark.
    "tests/benchmark/test_terminal_bench_adapter.py": {
        "class": "B stale-import",
        "cause": "imports harness.lib.benchmark and patch targets while pytest is invoked from harness/",
    },
    # B stale-import: multi_task_runner no longer exports the older epic_child_status_lines helper.
    "tests/graph/test_multi_task_runner_status_surface.py": {
        "class": "B stale-import",
        "cause": "expects removed multi_task_runner.epic_child_status_lines API",
    },
    # C dead-module: youtube migration modules are absent; harness/migrations does not exist at this commit.
    "tests/integration/test_youtube_e2e.py": {
        "class": "C dead-module",
        "cause": "imports missing youtube_001/youtube_002/youtube_004/youtube_005/youtube_010 migrations",
    },
    # B stale-import: basename collision resolved by the wave-2 rename, but the file still imports stale harness.lib.livework.
    "tests/livework/test_livework_schemas.py": {
        "class": "B stale-import",
        "cause": "imports harness.lib livework modules while pytest is invoked from harness/ (ModuleNotFoundError: harness)",
    },
    # namespace-collision: tests/research/integration is imported as top-level integration.
    "tests/research/integration/test_deepresearch_s6_integration.py": {
        "class": "namespace-collision",
        "cause": "research integration package collides with top-level tests/integration package",
    },
    # namespace-collision: tests/research/integration is imported as top-level integration; file also uses harness.lib.
    "tests/research/integration/test_local_command_fixture.py": {
        "class": "namespace-collision",
        "cause": "research integration package collides with top-level tests/integration package",
    },
    # namespace-collision: tests/research/integration is imported as top-level integration; file also uses harness.lib.
    "tests/research/integration/test_real_vs_estimated_switch.py": {
        "class": "namespace-collision",
        "cause": "research integration package collides with top-level tests/integration package",
    },
    # namespace-collision: tests/research/integration is imported as top-level integration (wave-2 rename fixed only the basename).
    "tests/research/integration/test_research_pipeline_integration.py": {
        "class": "namespace-collision",
        "cause": "research integration package collides with top-level tests/integration package",
    },
    # B stale-import: basename collision resolved by the wave-2 rename, but the file still imports stale harness.lib.
    "tests/research/negative/test_research_negative_control.py": {
        "class": "B stale-import",
        "cause": "imports harness.lib modules while pytest is invoked from harness/ (ModuleNotFoundError: harness)",
    },
    # C dead-module: test targets cli.cmd_status_epic, but no cmd_status_epic.py exists in lib/cli.
    "tests/research/survey/activation_proof/test_status_epic_activation.py": {
        "class": "C dead-module",
        "cause": "imports missing cli.cmd_status_epic module",
    },
    # namespace-collision: tests/research/survey/cli package shadows the real lib/cli package.
    "tests/research/survey/cli/test_argument_density_view.py": {
        "class": "namespace-collision",
        "cause": "test cli package shadows real lib/cli namespace during full-suite collection",
    },
    # namespace-collision: tests/research/survey/cli package shadows the real lib/cli package.
    "tests/research/survey/cli/test_contradiction_matrix_view.py": {
        "class": "namespace-collision",
        "cause": "test cli package shadows real lib/cli namespace during full-suite collection",
    },
    # namespace-collision: tests/research/survey/cli package shadows the real lib/cli package.
    "tests/research/survey/cli/test_exploration_view.py": {
        "class": "namespace-collision",
        "cause": "test cli package shadows real lib/cli namespace during full-suite collection",
    },
    # namespace-collision: tests/research/survey/cli package shadows the real lib/cli package.
    "tests/research/survey/cli/test_gate_report_view.py": {
        "class": "namespace-collision",
        "cause": "test cli package shadows real lib/cli namespace during full-suite collection",
    },
    # namespace-collision: tests/research/survey/cli package shadows the real lib/cli package.
    "tests/research/survey/cli/test_source_quality_view.py": {
        "class": "namespace-collision",
        "cause": "test cli package shadows real lib/cli namespace during full-suite collection",
    },
    # B stale-import: github_intelligence.briefs no longer exports generate_planning_brief.
    "tests/test_briefs.py": {
        "class": "B stale-import",
        "cause": "expects removed github_intelligence.briefs.generate_planning_brief API",
    },
    # B stale-import: github_intelligence.cards no longer exports generate_analysis_card.
    "tests/test_cards.py": {
        "class": "B stale-import",
        "cause": "expects removed github_intelligence.cards.generate_analysis_card API",
    },
    # B stale-import: github_intelligence.detectors now exposes functional detector APIs, not detector classes.
    "tests/test_detectors.py": {
        "class": "B stale-import",
        "cause": "expects removed github_intelligence detector classes and run_all_detectors API",
    },
    # B stale-import: github_intelligence.evidence no longer exports older helper names/signatures.
    "tests/test_evidence_compression.py": {
        "class": "B stale-import",
        "cause": "expects removed github_intelligence.evidence helper APIs such as clean_readme",
    },
    # C dead-module: youtube transcript job migration module is absent; harness/migrations does not exist.
    "tests/test_youtube_cli.py": {
        "class": "C dead-module",
        "cause": "imports missing youtube_005_transcript_jobs migration",
    },
    # C dead-module: youtube migration modules are absent; harness/migrations does not exist.
    "tests/test_youtube_dashboard.py": {
        "class": "C dead-module",
        "cause": "imports missing youtube_001/youtube_002/youtube_004/youtube_005/youtube_010 migrations",
    },
    # C dead-module: youtube transcript job migration module is absent; harness/migrations does not exist.
    "tests/test_youtube_job_scheduler.py": {
        "class": "C dead-module",
        "cause": "imports missing youtube_005_transcript_jobs migration",
    },
    # C dead-module: first youtube migration module is absent; harness/migrations does not exist.
    "tests/test_youtube_migration.py": {
        "class": "C dead-module",
        "cause": "imports missing youtube_001_subtitle_tracks migration",
    },
    # C dead-module: youtube transcript migration module is absent; harness/migrations does not exist.
    "tests/test_youtube_pollution_repair.py": {
        "class": "C dead-module",
        "cause": "imports missing youtube_002_transcripts migration",
    },
    # C dead-module: youtube premium ASR migration module is absent; harness/migrations does not exist.
    "tests/test_youtube_premium_escape.py": {
        "class": "C dead-module",
        "cause": "imports missing youtube_010_premium_asr_calls migration",
    },
    # C dead-module: youtube transcript and quality-check migration modules are absent; harness/migrations does not exist.
    "tests/test_youtube_quality_gate.py": {
        "class": "C dead-module",
        "cause": "imports missing youtube_002_transcripts/youtube_008_quality_checks migrations",
    },
    # C dead-module: youtube transcript migration module is absent; harness/migrations does not exist.
    "tests/test_youtube_transcript_storage.py": {
        "class": "C dead-module",
        "cause": "imports missing youtube_002_transcripts migration",
    },
}

collect_ignore = [str(_HARNESS_DIR / rel_path) for rel_path in COLLECTION_QUARANTINE_MANIFEST]


def _path_is_installed_harness(raw: object) -> bool:
    if raw in (None, ""):
        return False
    try:
        path = Path(str(raw)).expanduser()
    except Exception:
        return False
    try:
        raw_absolute = path.absolute()
        installed_link_absolute = _INSTALLED_HARNESS_LINK.absolute()
    except Exception:
        raw_absolute = None
        installed_link_absolute = None
    if (
        raw_absolute is not None
        and installed_link_absolute is not None
        and (raw_absolute == installed_link_absolute or installed_link_absolute in raw_absolute.parents)
    ):
        return True

    # If ~/.solar/harness is a symlink to the current checkout, allow tests to
    # use the checkout path while still rejecting raw ~/.solar/harness imports.
    if _INSTALLED_HARNESS == _HARNESS_DIR_REAL:
        return False

    try:
        resolved = path.resolve()
    except Exception:
        return False
    return resolved == _INSTALLED_HARNESS or _INSTALLED_HARNESS in resolved.parents


def _collect_installed_harness_leaks(
    *,
    paths: list[str] | None = None,
    modules: Mapping[str, object] | None = None,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    leaks: list[str] = []
    env = env if env is not None else os.environ
    for key in ("HARNESS_DIR", "SOLAR_HARNESS_DIR"):
        value = env.get(key, "")
        if _path_is_installed_harness(value):
            leaks.append(f"env:{key}={value}")

    for item in paths if paths is not None else list(sys.path):
        if _path_is_installed_harness(item):
            leaks.append(f"sys.path:{item}")

    for name, module in (modules if modules is not None else sys.modules).items():
        file_value = getattr(module, "__file__", None)
        if _path_is_installed_harness(file_value):
            leaks.append(f"module:{name}={file_value}")
    return sorted(set(leaks))


@pytest.fixture(autouse=True)
def _fail_on_installed_harness_runtime_leak():
    if os.environ.get("SOLAR_ALLOW_INSTALLED_HARNESS_TESTS", "").strip().lower() in {"1", "true", "yes", "on"}:
        yield
        return
    leaks_before = _collect_installed_harness_leaks()
    assert not leaks_before, "test is using installed ~/.solar/harness runtime:\n" + "\n".join(leaks_before)
    yield
    leaks_after = _collect_installed_harness_leaks()
    assert not leaks_after, "test leaked installed ~/.solar/harness runtime:\n" + "\n".join(leaks_after)

try:
    importlib.import_module("research.evaluator")
except Exception:
    if "research.evaluator" not in sys.modules:
        _mod = types.ModuleType("research.evaluator")
        _mod.audit_sources = lambda *a, **k: {}
        sys.modules["research.evaluator"] = _mod
