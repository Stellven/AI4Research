# Model Training and Policy Learning Repair

Status: repaired with CPU reference paths.

Scope:

- SFT, LoRA, DPO, GRPO, and agent RL use one `TrainingJob` contract.
- Each method keeps method-specific dataset requirements.
- Checkpoints, resume, promotion gates, and provenance hashes are enforced by the shared engine.

Evidence policy:

- The reference path uses tiny in-memory numeric fixtures and pure Python updates.
- No large model download is required.
- A result is accepted only when labeled data, preference pairs, group rewards, or trajectories are consumed as required by the method.
- Dataset, config, engine code, initial weights, result weights, and checkpoint artifacts are hashed.
- Promotion is controlled by an evaluation gate and fails closed.

Verification:

- `tests/repairs/model_training/test_reference_training_paths.py` runs one minimal CPU job per method.
- Negative tests reject invalid datasets, NaN payloads, corrupt checkpoints, and failed promotion gates.
- Resume tests load a checkpoint and skip completed steps instead of repeating from step zero.
