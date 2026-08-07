from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "harness" / "lib"))

from advanced_ai4rnd.evaluation import JudgeCalibrator, RewardModel  # noqa: E402


def test_judge_calibration_uses_heldout_fixture_and_writes_evidence(tmp_path: Path) -> None:
    heldout = [
        {"id": "heldout-a", "judge_score": 0.70, "label": 0.85},
        {"id": "heldout-b", "judge_score": 0.30, "label": 0.45},
        {"id": "heldout-c", "judge_score": 0.50, "label": 0.65},
    ]
    evidence_path = tmp_path / "calibration-evidence.json"
    calibrator = JudgeCalibrator(tmp_path / "judge-state.json")

    evidence = calibrator.calibrate(heldout, evidence_path)

    assert evidence["fixture_kind"] == "held_out"
    assert evidence["heldout_ids"] == ["heldout-a", "heldout-b", "heldout-c"]
    assert evidence["calibration"]["after_mae"] < evidence["calibration"]["before_mae"]
    assert evidence_path.exists()

    reloaded = JudgeCalibrator(tmp_path / "judge-state.json")
    assert reloaded.score(0.40) > 0.40
    persisted = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert persisted["calibration"]["method"] == "affine_bias_correction"


def test_reward_model_trains_updates_and_reloads_reference_path(tmp_path: Path) -> None:
    artifact = tmp_path / "reward-model.json"
    model = RewardModel(artifact)
    before = model.score("citation grounded answer")
    update = model.train(
        [
            {"prompt": "Need evidence", "response": "citation grounded answer", "reward": 1.0},
            {"prompt": "Need evidence", "response": "unsupported vague answer", "reward": 0.0},
        ]
    )
    after = model.score("citation grounded answer")

    assert update["reference_path"] == str(artifact)
    assert update["changed"] is True
    assert after > before
    assert artifact.exists()

    reloaded = RewardModel(artifact)
    assert reloaded.score("citation grounded answer") == after
