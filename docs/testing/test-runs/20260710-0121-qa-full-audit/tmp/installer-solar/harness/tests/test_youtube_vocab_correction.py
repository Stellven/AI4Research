import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from youtube.vocab_correction import build_vocab_dictionary, apply_vocab_corrections


def test_vocab_dictionary_builds_sha_and_sync_interval():
    vocab = build_vocab_dictionary(
        [
            {"wrong": "Qwen3.6", "correct": "Qwen3", "source_kind": "model"},
            {"wrong": "Thunder OMLX", "correct": "ThunderOMLX", "source_kind": "product"},
        ]
    )
    assert len(vocab.version_sha256) == 64
    assert vocab.sync_interval_hours == 168


def test_apply_vocab_corrections_rewrites_terms():
    vocab = build_vocab_dictionary(
        [{"wrong": "Thunder OMLX", "correct": "ThunderOMLX", "source_kind": "product"}]
    )
    corrected, applied = apply_vocab_corrections("We deploy Thunder OMLX in prod.", vocab)
    assert corrected == "We deploy ThunderOMLX in prod."
    assert applied == ["ThunderOMLX"]
