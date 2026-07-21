#!/usr/bin/env python3
"""Bi-directional Conversation Export for Antigravity

Scans Solar-Harness intents for Antigravity App sessions.
Copies associated sprint artifacts (status, prd, contract) back into
the Antigravity conversation brain directory to natively render in UI.
"""
import os
import json
import shutil
from pathlib import Path

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("SOLAR_HARNESS_DIR", HOME / ".solar" / "harness"))
INTENTS_DIR = Path(os.environ.get("SOLAR_INTENT_GATEWAY_DIR", HARNESS_DIR / "intents"))
SPRINTS_DIR = Path(os.environ.get("SOLAR_HARNESS_SPRINTS_DIR", HARNESS_DIR / "sprints"))
BRIDGE_DIR = HOME / ".solar" / "antigravity-bridge"
STATE_FILE = BRIDGE_DIR / ".sync_state.json"
AGY_BRAIN_DIR = HOME / ".gemini" / "antigravity" / "brain"

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_state(state: dict) -> None:
    BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

def main():
    if not INTENTS_DIR.exists():
        return

    state = load_state()
    sync_count = 0

    for intent_dir in INTENTS_DIR.iterdir():
        if not intent_dir.is_dir():
            continue

        raw_intent_file = intent_dir / "raw_intent.json"
        if not raw_intent_file.exists():
            continue

        try:
            raw_intent = json.loads(raw_intent_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        source = raw_intent.get("source", {})
        if not isinstance(source, dict):
            continue

        if source.get("channel") not in ("antigravity-app", "antigravity_desktop", "cli"):
            # Wait, in the mock run it used "antigravity_desktop". I'll support both + cli for testing if session_id matches
            pass

        session_id = source.get("session_id")
        if not session_id:
            continue

        # Verify the brain directory exists for this conversation
        brain_dir = AGY_BRAIN_DIR / session_id
        if not brain_dir.exists():
            continue

        # Look up sprint binding
        sprint_id = None
        consumer_file = intent_dir / "consumer.json"
        binding_file = intent_dir / "binding.json"

        if consumer_file.exists():
            try:
                consumer = json.loads(consumer_file.read_text(encoding="utf-8"))
                sprint_id = consumer.get("sprint_id")
            except Exception:
                pass

        if not sprint_id and binding_file.exists():
            try:
                binding = json.loads(binding_file.read_text(encoding="utf-8"))
                sprint_id = binding.get("sprint_id")
            except Exception:
                pass

        if not sprint_id:
            continue

        # We have a sprint ID and a brain directory. Let's sync artifacts.
        artifacts = {
            ".status.json": "harness_status.json",
            ".prd.md": "harness_prd.md",
            ".contract.md": "harness_contract.md",
            ".task_graph.json": "harness_task_graph.json"
        }

        for ext, target_name in artifacts.items():
            src_file = SPRINTS_DIR / f"{sprint_id}{ext}"
            if not src_file.exists():
                continue

            mtime = src_file.stat().st_mtime
            state_key = f"{session_id}:{sprint_id}{ext}"

            if state.get(state_key) != mtime:
                # Copy file
                dst_file = brain_dir / target_name
                try:
                    shutil.copy2(src_file, dst_file)
                    state[state_key] = mtime
                    sync_count += 1
                except Exception as e:
                    print(f"Error copying {src_file} to {dst_file}: {e}")

    if sync_count > 0:
        save_state(state)
        print(f"antigravity_bridge_exporter: synced {sync_count} artifacts to UI")

if __name__ == "__main__":
    main()
