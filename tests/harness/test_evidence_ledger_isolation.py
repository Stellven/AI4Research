"""Isolation tests for the EvidenceLedger / ActorRuntime path bug (runtime audit finding).

Before the fix: ActorRuntime(harness_dir=tmp) created EvidenceLedger() with no args, which
resolved to a HARDCODED ~/.solar/harness/run/actor-evidence — leaking real-user state into
isolated runs and breaking any alternate harness root. These prove it now stays under the
provided / env harness dir.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

LIB = (Path(__file__).resolve().parents[2] / 'harness') / "lib"
sys.path.insert(0, str(LIB))


def test_actor_runtime_forwards_harness_dir_to_ledger():
    # The reviewer's exact scenario: ActorRuntime(harness_dir=tmp) must write evidence UNDER tmp,
    # not ~/.solar. Fix B forwards self.harness_dir into the default EvidenceLedger.
    import actor_runtime
    with tempfile.TemporaryDirectory() as td:
        rt = actor_runtime.ActorRuntime(harness_dir=Path(td))
        ledger_dir = Path(rt.ledger.ledger_dir)
        assert ledger_dir == Path(td) / "run" / "actor-evidence", f"ledger escaped tmp: {ledger_dir}"
        assert str(ledger_dir).startswith(td), f"ledger not under tmp: {ledger_dir}"
        # And it must NOT point at the real home harness.
        assert str(Path.home() / ".solar") not in str(ledger_dir)


def test_evidence_ledger_default_honors_harness_dir_env():
    # A default EvidenceLedger() in a process launched with HARNESS_DIR set must resolve under it.
    # Run in a FRESH subprocess so the module-level HARNESS_DIR is read with the env in place.
    with tempfile.TemporaryDirectory() as td:
        code = (
            "import sys; sys.path.insert(0, %r);"
            "import evidence_ledger as e; print(e.EvidenceLedger().ledger_dir)"
            % str(LIB)
        )
        out = subprocess.run(
            [sys.executable, "-c", code],
            env={**os.environ, "HARNESS_DIR": td},
            capture_output=True, text=True, timeout=30,
        )
        assert out.returncode == 0, f"subprocess failed: {out.stderr!r}"
        assert td in out.stdout, f"default ledger ignored HARNESS_DIR env: {out.stdout!r} / {out.stderr!r}"


def test_actor_runtime_forwards_harness_dir_to_context_store():
    # ContextStore was the other ActorRuntime-level leak: ctx packets -> ~/.solar/harness/run/context-store.
    import actor_runtime
    with tempfile.TemporaryDirectory() as td:
        rt = actor_runtime.ActorRuntime(harness_dir=Path(td))
        store_dir = Path(rt.ctx_store.store_dir)
        assert store_dir == Path(td) / "run" / "context-store", f"ctx_store escaped tmp: {store_dir}"
        assert str(Path.home() / ".solar") not in str(store_dir)


def test_hands_runtime_honors_harness_dir_env():
    # hands_runtime (sandbox executor) hardcoded ~/.solar/harness; it now honors HARNESS_DIR.
    with tempfile.TemporaryDirectory() as td:
        code = (
            "import sys; sys.path.insert(0, %r);"
            "import hands_runtime as h; print(h.HARNESS_DIR); print(h.SANDBOX_ROOT)"
            % str(LIB)
        )
        out = subprocess.run(
            [sys.executable, "-c", code],
            env={**os.environ, "HARNESS_DIR": td},
            capture_output=True, text=True, timeout=30,
        )
        assert out.returncode == 0, f"subprocess failed: {out.stderr!r}"
        assert td in out.stdout, f"hands_runtime ignored HARNESS_DIR env: {out.stdout!r} / {out.stderr!r}"
