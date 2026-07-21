"""Tests for context_store.py — Context packet loading without pane-memory."""
import json
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from context_store import ContextStore

def test_save_and_load():
    with tempfile.TemporaryDirectory() as td:
        cs = ContextStore(Path(td))
        cs.save("pkt-1", {"sprint_id": "s1", "node": "n1"})
        data = cs.load("pkt-1")
        assert data["sprint_id"] == "s1"
        print("PASS: save_and_load")

def test_resolve_ref():
    with tempfile.TemporaryDirectory() as td:
        cs = ContextStore(Path(td))
        cs.save("pkt-42", {"context": "data"})
        ref = {"packet_id": "pkt-42", "path": None}
        data = cs.resolve_ref(ref)
        assert data["context"] == "data"
        print("PASS: resolve_ref")

def test_resolve_ref_missing():
    cs = ContextStore()
    assert cs.resolve_ref(None) is None
    assert cs.resolve_ref({"packet_id": "nonexistent"}) is None
    print("PASS: resolve_ref_missing")

if __name__ == "__main__":
    test_save_and_load()
    test_resolve_ref()
    test_resolve_ref_missing()
    print("\n3/3 passed")
