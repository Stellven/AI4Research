#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 - "$ROOT" <<'PY'
import importlib.util
import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
os.environ["HARNESS_DIR"] = str(root)
sys.path.insert(0, str(root / "lib"))

spec = importlib.util.spec_from_file_location("multi_task_runner", root / "lib" / "multi_task_runner.py")
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)

line = mod.claude_agent_line("thunderomlx", "'probe'")
assert "ANTHROPIC_BASE_URL" in line
assert "127.0.0.1:8002" in line
assert "claude-3-5-sonnet-latest" in line
assert "Qwen3.6-35b-a3b" in line
assert "--dangerously-skip-permissions" in line
assert "--model Qwen3.6-35b-a3b" not in line
assert "SOLAR_MULTI_TASK_AGENT_CMD" not in line
assert "knowledge_extraction_multitask_agent.py" not in line

profile = mod.select_profile({"preferred_profile": "knowledge-extractor"})
assert profile["backend"] == "command", profile
assert profile["model"] == "thunderomlx", profile
assert "thunderomlx_knowledge_extract_agent.py" in profile.get("command", ""), profile

print("ok - ThunderOMLX knowledge extractor routes through headless tmux API agent")
PY
