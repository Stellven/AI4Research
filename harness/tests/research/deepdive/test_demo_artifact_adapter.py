"""Lane 4 — demo artifact adapter: native engine exports -> 5 RSI demo artifacts.

Red-first. The adapter consumes REAL native jsonl exports (produced by the engine's
own storage+export path via native_fixture_builder) and must NOT touch the cli.py
synthesizer (F-055 boilerplate bypass). The gate: the adapter's output passes the
copied-workspace validator scripts/validate_rsi_demo_report.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_HARNESS = _HERE.parents[2]
_LIB = _HARNESS / "lib"
for p in (str(_HERE), str(_LIB)):
    if p not in sys.path:
        sys.path.insert(0, p)

from native_fixture_builder import COMMITTED_EXPORT_FILES, build_native_export  # noqa: E402
from research import demo_artifact_adapter as adapter  # noqa: E402

COMMITTED_FIXTURE = _HERE / "fixtures" / "native_export_rsi"
REPORT_VALIDATOR = _HARNESS.parent / "scripts" / "validate_rsi_demo_report.py"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _run_validator(workspace: Path):
    return subprocess.run(
        [sys.executable, str(REPORT_VALIDATOR)],
        cwd=str(workspace), text=True, capture_output=True,
    )


# ---------------------------------------------------------------------------
# The committed fixture is exactly what the real engine export emits.
# ---------------------------------------------------------------------------

def test_committed_fixture_is_real_engine_export(tmp_path):
    regen = build_native_export(tmp_path / "regen")
    for name in COMMITTED_EXPORT_FILES:
        committed = (COMMITTED_FIXTURE / name).read_bytes()
        produced = (regen / name).read_bytes()
        assert committed == produced, f"committed fixture {name} drifted from the real engine export"


# ---------------------------------------------------------------------------
# The adapter gate: 5 demo artifacts that pass the demo validator.
# ---------------------------------------------------------------------------

def test_adapter_produces_five_demo_artifacts_and_validator_passes(tmp_path):
    manifest = adapter.adapt_native_exports(COMMITTED_FIXTURE, tmp_path)
    root = tmp_path / adapter.DEMO_ARTIFACT_ROOT
    assert manifest["ok"] is True
    for name in adapter.REQUIRED_ARTIFACTS:
        assert (root / name).is_file(), f"missing demo artifact {name}"
    proc = _run_validator(tmp_path)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "RSI demo report validated" in proc.stdout


def test_min_counts_satisfy_validator(tmp_path):
    adapter.adapt_native_exports(COMMITTED_FIXTURE, tmp_path)
    root = tmp_path / adapter.DEMO_ARTIFACT_ROOT
    sources = _read_json(root / "sources.json")
    claims = _read_json(root / "claims.json")
    assert len(sources) >= 5
    assert len(claims) >= 10


def test_every_claim_links_to_an_existing_source(tmp_path):
    adapter.adapt_native_exports(COMMITTED_FIXTURE, tmp_path)
    root = tmp_path / adapter.DEMO_ARTIFACT_ROOT
    source_ids = {s["id"] for s in _read_json(root / "sources.json")}
    claims = _read_json(root / "claims.json")
    for c in claims:
        assert c["source_id"] in source_ids, c
        assert str(c["claim_text"]).strip(), c


def test_report_derives_from_native_content_not_boilerplate(tmp_path):
    adapter.adapt_native_exports(COMMITTED_FIXTURE, tmp_path)
    root = tmp_path / adapter.DEMO_ARTIFACT_ROOT
    md = (root / "report.md").read_text(encoding="utf-8")
    html = (root / "report.html").read_text(encoding="utf-8")
    # Real section content assembled from sections.jsonl, not the cli.py synth.
    assert "Evidence Synthesis" in md
    assert "self-reflection" in md
    assert "<html" in html.lower()
    assert len(html) >= 500
    assert len(md) >= 300


def test_adapter_is_deterministic_byte_identical(tmp_path):
    a = adapter.adapt_native_exports(COMMITTED_FIXTURE, tmp_path / "a")
    b = adapter.adapt_native_exports(COMMITTED_FIXTURE, tmp_path / "b")
    for name in adapter.REQUIRED_ARTIFACTS:
        assert (Path(a["root"]) / name).read_bytes() == (Path(b["root"]) / name).read_bytes(), name


def test_unresolvable_claims_are_dropped_not_mislinked(tmp_path):
    # Remove cl_01's only evidence link -> it can no longer resolve a source.
    native = tmp_path / "native"
    native.mkdir()
    for name in COMMITTED_EXPORT_FILES:
        (native / name).write_bytes((COMMITTED_FIXTURE / name).read_bytes())
    ce_lines = (native / "claim_evidence.jsonl").read_text(encoding="utf-8").splitlines()
    kept = [ln for ln in ce_lines if json.loads(ln)["claim_id"] != "cl_01"]
    (native / "claim_evidence.jsonl").write_text("\n".join(kept) + "\n", encoding="utf-8")

    manifest = adapter.adapt_native_exports(native, tmp_path / "out")
    root = Path(manifest["root"])
    claims = _read_json(root / "claims.json")
    claim_ids = {c["claim_id"] for c in claims}
    assert "cl_01" not in claim_ids
    assert "cl_01" in manifest["dropped_claim_ids"]
    # every surviving claim still links to a valid source
    source_ids = {s["id"] for s in _read_json(root / "sources.json")}
    assert all(c["source_id"] in source_ids for c in claims)


def test_missing_required_native_file_is_reported(tmp_path):
    native = tmp_path / "native"
    native.mkdir()
    for name in COMMITTED_EXPORT_FILES:
        if name == "sources.jsonl":
            continue
        (native / name).write_bytes((COMMITTED_FIXTURE / name).read_bytes())
    with pytest.raises(adapter.NativeExportError):
        adapter.adapt_native_exports(native, tmp_path / "out")
